"""Create issues command - main logic."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import click

from . import github_api, gitlab_api, history, incremental, pitfalls
from .check_parsing import extract_check_ids
from .config_utils import (
    append_opt_out_repository,
    get_custom_message,
    get_opt_out_repositories,
    load_config,
)

logger = logging.getLogger(__name__)


class IssueClientProtocol(Protocol):
    """Shared methods used by both GitHub and GitLab issue clients."""

    def create_issue(self, repo_url: str, title: str, body: str) -> str:
        """Create an issue on the target platform and return its URL."""
        ...

    def get_issue(self, issue_url: str) -> dict:
        """Fetch issue metadata for a platform issue URL."""
        ...

    def get_issue_comments(self, issue_url: str) -> list[str]:
        """Return issue comments as plain text bodies."""
        ...

    def add_issue_comment(self, issue_url: str, body: str) -> None:
        """Post a comment to the specified issue URL."""
        ...

    def close_issue(self, issue_url: str) -> None:
        """Close the issue addressed by the specified URL."""
        ...


def detect_platform(url: str) -> str:
    """Detect platform (GitHub, GitLab, etc.) from repository URL."""
    url = url.lower()
    if "github.com" in url:
        return "github"
    elif "gitlab.com" in url:
        return "gitlab.com"
    elif "gitlab" in url:
        return "gitlab"
    else:
        raise ValueError(f"Unsupported repository platform in URL: {url}")


def _normalize_repo_url(url: str) -> str:
    """Normalize repository URL for matching between datasets."""
    return url.strip().rstrip("/")


def _load_analysis_commit_map(analysis_summary_file: Path | None) -> dict[str, str]:
    """Load repo URL -> commit_id map from metacheck analysis summary file."""
    if analysis_summary_file is None or not analysis_summary_file.exists():
        return {}

    with open(analysis_summary_file, encoding="utf-8") as f:
        data = json.load(f)

    summary = data.get("summary", {}) if isinstance(data, dict) else {}
    evaluated = summary.get("evaluated_repositories", {})
    if not isinstance(evaluated, dict):
        return {}

    commit_map: dict[str, str] = {}
    for item in evaluated.values():
        if not isinstance(item, dict):
            continue
        repo_url = item.get("url")
        commit_id = item.get("commit_id")
        if isinstance(repo_url, str) and isinstance(commit_id, str):
            commit_map[_normalize_repo_url(repo_url)] = commit_id

    return commit_map


def _discover_pitfalls_files(
    analysis_root: Path | None,
    pitfalls_output_dir: Path | None,
) -> list[tuple[Path, Path | None]]:
    """Discover pitfalls JSON-LD files using per-repo structure or flat directory.

    Returns list of tuples: (pitfalls_file_path, per_repo_issues_dir or None)
    where per_repo_issues_dir is set if using per-repo structure.

    Args:
        analysis_root: Root analysis directory with per-repo structure
        pitfalls_output_dir: Fallback flat directory for backwards compatibility

    Returns:
        List of (pitfalls_file, per_repo_issues_dir) tuples
    """
    discovered: list[tuple[Path, Path | None]] = []

    # Try per-repo discovery first
    if analysis_root is not None and analysis_root.exists():
        # Look for pitfall.jsonld (new layout) in each repo subfolder
        for repo_folder in sorted(analysis_root.iterdir()):
            if not repo_folder.is_dir():
                continue
            # Skip system/cache folders
            if repo_folder.name.startswith("."):
                continue

            pitfalls_file = repo_folder / "pitfall.jsonld"
            if not pitfalls_file.exists():
                pitfalls_file = repo_folder / "pitfalls_output.jsonld"
            if pitfalls_file.exists():
                per_repo_issues_dir = repo_folder
                discovered.append((pitfalls_file, per_repo_issues_dir))

    # Fall back to flat directory if no per-repo structure found
    if not discovered and pitfalls_output_dir is not None:
        if pitfalls_output_dir.exists():
            # Look for any .jsonld files in the flat directory
            flat_files = sorted(pitfalls_output_dir.glob("*.jsonld"))
            for f in flat_files:
                discovered.append((f, None))

    return discovered


def _is_unsubscribe_comment(comment: str) -> bool:
    """Return True when a comment is exactly the unsubscribe keyword."""
    return comment.strip().lower() == "unsubscribe"


def _is_issue_open(platform: str, issue_data: dict) -> bool:
    """Platform-specific issue open-state check."""
    state = str(issue_data.get("state", "")).lower()
    if platform == "github":
        return state == "open"
    return state == "opened"


def _get_or_create_client(
    platform: str,
    dry_run: bool,
    github: github_api.GitHubAPI | None,
    gitlab: gitlab_api.GitLabAPI | None,
) -> tuple[
    github_api.GitHubAPI | None,
    gitlab_api.GitLabAPI | None,
    IssueClientProtocol,
]:
    """Create or reuse API client for a platform and return unified client object."""
    if platform == "github":
        github_client = (
            github if github is not None else github_api.GitHubAPI(dry_run=dry_run)
        )
        return github_client, gitlab, github_client

    if platform == "gitlab.com":
        gitlab_client = (
            gitlab if gitlab is not None else gitlab_api.GitLabAPI(dry_run=dry_run)
        )
        return github, gitlab_client, gitlab_client

    raise ValueError(f"Unsupported platform: {platform}")


def _extract_check_ids(checks: list[dict]) -> tuple[list[str], list[str]]:
    """Extract unique pitfall and warning codes from checks."""
    return extract_check_ids(checks)


def _safe_get_metacheck_version(data: dict) -> str:
    """Get metacheck version without failing issue reporting."""
    try:
        return pitfalls.get_metacheck_version(data)
    except Exception:
        return "unknown"


def _get_analysis_date(data: dict) -> str:
    """Get analysis date from pitfalls payload."""
    return str(data.get("dateCreated", "unknown"))


def _build_counters(records: list[dict[str, object]]) -> dict[str, int]:
    """Build counters from report records."""
    return {
        "total": len(records),
        "created": sum(1 for r in records if r.get("action") == "created"),
        "simulated": sum(1 for r in records if r.get("action") == "simulated_created"),
        "updated_by_comment": sum(
            1 for r in records if r.get("action") == "updated_by_comment"
        ),
        "closed": sum(1 for r in records if r.get("action") == "closed"),
        "skipped": sum(1 for r in records if r.get("action") == "skipped"),
        "failed": sum(1 for r in records if r.get("action") == "failed"),
    }


def _write_repo_report(
    repo_dir: Path,
    record: dict[str, object],
    *,
    dry_run: bool,
    analysis_summary_file: Path | None,
    previous_report: Path | None,
) -> None:
    """Write per-repository report.json containing a single record."""
    report = {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": dry_run,
            "analysis_summary_file": (
                str(analysis_summary_file)
                if analysis_summary_file is not None
                else None
            ),
            "previous_report_source": (
                str(previous_report) if previous_report is not None else None
            ),
        },
        "counters": _build_counters([record]),
        "records": [record],
    }
    report_file = repo_dir / "report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def _build_report_entry(
    *,
    repo_url: str | None,
    platform: str | None,
    pitfalls_count: int | None,
    warnings_count: int | None,
    issue_url: str | None,
    analysis_date: str,
    bot_version: str,
    metacheck_version: str,
    pitfalls_ids: list[str] | None,
    warnings_ids: list[str] | None,
    action: str | None = None,
    reason_code: str | None = None,
    previous_issue_url: str | None = None,
    previous_issue_state: str | None = None,
    findings_signature: str | None = None,
    current_commit_id: str | None = None,
    previous_commit_id: str | None = None,
    unsubscribe_detected: bool | None = None,
    dry_run: bool | None = None,
    issue_persistence: str | None = None,
    simulated_issue_url: str | None = None,
    file_path: Path | None = None,
    error: str | None = None,
) -> dict[str, object]:
    """Build a report entry with common metadata and optional fields."""
    entry: dict[str, object] = {
        "repo_url": repo_url,
        "platform": platform,
        "pitfalls_count": pitfalls_count,
        "warnings_count": warnings_count,
        "issue_url": issue_url,
        "analysis_date": analysis_date,
        "sw_metadata_bot_version": bot_version,
        "rsmetacheck_version": metacheck_version,
        "pitfalls_ids": pitfalls_ids or [],
        "warnings_ids": warnings_ids or [],
    }
    if action is not None:
        entry["action"] = action
    if reason_code is not None:
        entry["reason_code"] = reason_code
    if previous_issue_url is not None:
        entry["previous_issue_url"] = previous_issue_url
    if previous_issue_state is not None:
        entry["previous_issue_state"] = previous_issue_state
    if findings_signature is not None:
        entry["findings_signature"] = findings_signature
    if current_commit_id is not None:
        entry["current_commit_id"] = current_commit_id
    if previous_commit_id is not None:
        entry["previous_commit_id"] = previous_commit_id
    if unsubscribe_detected is not None:
        entry["unsubscribe_detected"] = unsubscribe_detected
    if dry_run is not None:
        entry["dry_run"] = dry_run
    if issue_persistence is not None:
        entry["issue_persistence"] = issue_persistence
    if simulated_issue_url is not None:
        entry["simulated_issue_url"] = simulated_issue_url
    if file_path is not None:
        entry["file"] = str(file_path)
    if error is not None:
        entry["error"] = error

    return entry


@click.command()
@click.option(
    "--analysis-root",
    type=click.Path(exists=False, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Root analysis directory with per-repo structure (new format). If provided, --pitfalls-output-dir is ignored.",
)
@click.option(
    "--pitfalls-output-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=False,
    help="Directory containing pitfalls JSON-LD files from metacheck analysis (backward compat).",
)
@click.option(
    "--issues-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path.cwd(),
    help="Directory to save issue bodies and reports.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate issue creation without actually posting to repositories.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Logging level.",
)
@click.option(
    "--config-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Unified JSON configuration file.",
)
@click.option(
    "--analysis-summary-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Analysis summary JSON file (for commit-aware incremental handling).",
)
@click.option(
    "--previous-report",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Previous report.json to enable incremental issue handling.",
)
def create_issues_command(
    analysis_root: Path | None,
    pitfalls_output_dir: Path | None,
    issues_dir: Path,
    dry_run: bool,
    log_level: str,
    config_file: Path,
    analysis_summary_file: Path | None,
    previous_report: Path | None,
):
    """
    Create issues in repositories based on metadata analysis results.

    This command processes pitfalls files generated by the metacheck tool
    and creates corresponding issues in the analyzed repositories.
    """
    # Setup logging
    logging.basicConfig(
        level=log_level.upper(),
        format="%(levelname)s: %(message)s",
    )

    # Create output directory (legacy flat mode)
    issues_dir.mkdir(parents=True, exist_ok=True)

    # Initialize API clients
    github, gitlab = None, None

    mode = "DRY RUN" if dry_run else "PRODUCTION"
    click.echo(f"\n{'=' * 60}")
    click.echo(f"Creating issues [{mode}]")
    click.echo(f"{'=' * 60}\n")

    config = load_config(config_file)
    custom_message = get_custom_message(config)
    previous_records = history.load_previous_report(previous_report)

    if analysis_summary_file is None:
        # Try to find analysis_results.json in likely locations
        if analysis_root is not None and analysis_root.exists():
            fallback_summary = analysis_root.parent / "analysis_results.json"
            if not fallback_summary.exists():
                fallback_summary = analysis_root / "analysis_results.json"
        elif pitfalls_output_dir is not None and pitfalls_output_dir.exists():
            fallback_summary = pitfalls_output_dir.parent / "analysis_results.json"
        else:
            fallback_summary = None

        if fallback_summary is not None and fallback_summary.exists():
            analysis_summary_file = fallback_summary

    current_commit_map = _load_analysis_commit_map(analysis_summary_file)

    opt_out_repos = get_opt_out_repositories(config)
    click.echo(
        f"Loaded {len(opt_out_repos)} opt-out repositories from: {config_file}\n"
    )

    # Find pitfalls files using per-repo discovery or fallback to flat directory
    pitfalls_files_with_issues_dir = _discover_pitfalls_files(
        analysis_root=analysis_root,
        pitfalls_output_dir=pitfalls_output_dir,
    )

    if not pitfalls_files_with_issues_dir:
        error_msg = f"No pitfalls files found in {analysis_root or pitfalls_output_dir}"
        click.echo(error_msg, err=True)
        return

    click.echo(
        f"Found {len(pitfalls_files_with_issues_dir)} pitfalls files to process\n"
    )

    using_per_repo_mode = all(
        per_repo_dir is not None for _, per_repo_dir in pitfalls_files_with_issues_dir
    )

    # Process each file
    records: list[dict[str, object]] = []
    bot_version = pitfalls.__version__

    for i, (file_path, per_repo_issues_dir) in enumerate(
        pitfalls_files_with_issues_dir, 1
    ):
        click.echo(
            f"[{i}/{len(pitfalls_files_with_issues_dir)}] Processing: {file_path.name}"
        )

        repo_url: str | None = None
        platform: str | None = None
        pitfalls_count: int | None = None
        warnings_count: int | None = None
        analysis_date: str = "unknown"
        metacheck_version: str = "unknown"
        pitfalls_ids: list[str] | None = None
        warnings_ids: list[str] | None = None
        current_commit_id: str | None = None
        previous_commit_id: str | None = None
        previous_issue_url: str | None = None
        previous_issue_state: str | None = None
        unsubscribe_detected = False

        # Use per-repo issues dir if available, otherwise use the global issues_dir
        current_issues_dir = per_repo_issues_dir if per_repo_issues_dir else issues_dir

        # Create issues directory for this repo/batch
        current_issues_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Load pitfalls
            data = pitfalls.load_pitfalls(file_path)
            repo_url = pitfalls.get_repository_url(data)
            pitfalls_list = pitfalls.get_pitfalls_list(data)
            warnings_list = pitfalls.get_warnings_list(data)
            pitfalls_count = len(pitfalls_list)
            warnings_count = len(warnings_list)
            analysis_date = _get_analysis_date(data)
            metacheck_version = _safe_get_metacheck_version(data)
            pitfalls_ids, warnings_ids = _extract_check_ids(data.get("checks", []))
            click.echo(f"  Repository: {repo_url}")

            normalized_repo = _normalize_repo_url(repo_url)
            current_commit_id = current_commit_map.get(normalized_repo)

            current_signature = history.findings_signature(pitfalls_ids, warnings_ids)
            has_findings = bool((pitfalls_count or 0) + (warnings_count or 0))

            if normalized_repo in opt_out_repos:
                click.echo("  ↷ Skipped: repository is in opt-outs list")
                records.append(
                    _build_report_entry(
                        repo_url=repo_url,
                        platform=platform,
                        pitfalls_count=pitfalls_count,
                        warnings_count=warnings_count,
                        issue_url=None,
                        analysis_date=analysis_date,
                        bot_version=bot_version,
                        metacheck_version=metacheck_version,
                        pitfalls_ids=pitfalls_ids,
                        warnings_ids=warnings_ids,
                        action="skipped",
                        reason_code="in_opt_out_list",
                        findings_signature=current_signature,
                        current_commit_id=current_commit_id,
                        dry_run=dry_run,
                        issue_persistence="none",
                        file_path=file_path,
                    )
                )
                click.echo()
                continue

            previous = previous_records.get(normalized_repo)
            platform = detect_platform(repo_url)
            previous_exists = previous is not None
            previous_signature = ""
            previous_issue_open = False
            repo_updated = True

            if previous_exists:
                previous_data = previous if previous is not None else {}
                previous_issue_url = str(previous_data.get("issue_url", "") or "")
                if not previous_issue_url:
                    previous_issue_url = str(
                        previous_data.get("previous_issue_url", "") or ""
                    )
                previous_commit_value = previous_data.get("current_commit_id")
                if previous_commit_value is None:
                    previous_commit_value = previous_data.get("commit_id")
                previous_commit_id = (
                    str(previous_commit_value)
                    if previous_commit_value is not None
                    else None
                )
                previous_signature = history.findings_signature(
                    previous_data.get("pitfalls_ids"),
                    previous_data.get("warnings_ids"),
                )

                if (
                    platform == "github"
                    and previous_commit_id
                    and current_commit_id
                    and previous_commit_id != "Unknown"
                    and current_commit_id != "Unknown"
                ):
                    repo_updated = previous_commit_id != current_commit_id

                if previous_issue_url:
                    previous_issue_persistence = previous_data.get("issue_persistence")
                    is_simulated_issue = previous_issue_persistence == "simulated"

                    if not is_simulated_issue:
                        github, gitlab, issue_client = _get_or_create_client(
                            platform,
                            dry_run,
                            github,
                            gitlab,
                        )
                        issue_data = issue_client.get_issue(previous_issue_url)
                        previous_issue_state = str(issue_data.get("state", ""))
                        previous_issue_open = _is_issue_open(platform, issue_data)
                        comments = issue_client.get_issue_comments(previous_issue_url)
                        unsubscribe_detected = any(
                            _is_unsubscribe_comment(comment) for comment in comments
                        )
                    else:
                        previous_issue_state = previous_data.get(
                            "previous_issue_state", ""
                        )
                        previous_issue_open = False

            # Unsubscribe acts like dry-run publication suppression, not hard stop.
            effective_dry_run = dry_run or unsubscribe_detected
            reason_override = "unsubscribe" if unsubscribe_detected else None

            decision = incremental.evaluate(
                previous_exists=previous_exists,
                unsubscribed=False,
                repo_updated=repo_updated,
                has_findings=has_findings,
                identical_findings=current_signature == previous_signature,
                previous_issue_open=previous_issue_open,
            )

            if decision.action == "stop":
                if decision.reason == "unsubscribe":
                    added_to_opt_out = append_opt_out_repository(config_file, repo_url)
                    if added_to_opt_out:
                        opt_out_repos.add(normalized_repo)
                    click.echo("  ↷ Skipped: unsubscribe detected in previous issue")
                else:
                    click.echo(f"  ↷ Skipped: {decision.reason}")

                record = _build_report_entry(
                    repo_url=repo_url,
                    platform=platform,
                    pitfalls_count=pitfalls_count,
                    warnings_count=warnings_count,
                    issue_url=None,
                    analysis_date=analysis_date,
                    bot_version=bot_version,
                    metacheck_version=metacheck_version,
                    pitfalls_ids=pitfalls_ids,
                    warnings_ids=warnings_ids,
                    action="skipped",
                    reason_code=reason_override or decision.reason,
                    previous_issue_url=previous_issue_url,
                    previous_issue_state=previous_issue_state,
                    findings_signature=current_signature,
                    current_commit_id=current_commit_id,
                    previous_commit_id=previous_commit_id,
                    unsubscribe_detected=unsubscribe_detected,
                    dry_run=effective_dry_run,
                    issue_persistence="none",
                    file_path=file_path,
                )
                records.append(record)
                if per_repo_issues_dir is not None:
                    _write_repo_report(
                        per_repo_issues_dir,
                        record,
                        dry_run=effective_dry_run,
                        analysis_summary_file=analysis_summary_file,
                        previous_report=previous_report,
                    )
                click.echo()
                continue

            if decision.action == "comment" and previous_issue_url:
                github, gitlab, issue_client = _get_or_create_client(
                    platform,
                    effective_dry_run,
                    github,
                    gitlab,
                )

                report = pitfalls.format_report(repo_url, data)
                body = pitfalls.create_issue_body(report, custom_message)
                issue_client.add_issue_comment(
                    previous_issue_url,
                    f"New analysis detected updated findings.\n\n{body}",
                )
                click.echo(f"  ✓ Issue updated by comment: {previous_issue_url}")

                record = _build_report_entry(
                    repo_url=repo_url,
                    platform=platform,
                    pitfalls_count=pitfalls_count,
                    warnings_count=warnings_count,
                    issue_url=previous_issue_url,
                    analysis_date=analysis_date,
                    bot_version=bot_version,
                    metacheck_version=metacheck_version,
                    pitfalls_ids=pitfalls_ids,
                    warnings_ids=warnings_ids,
                    action="updated_by_comment",
                    reason_code=reason_override or decision.reason,
                    previous_issue_url=previous_issue_url,
                    previous_issue_state=previous_issue_state,
                    findings_signature=current_signature,
                    current_commit_id=current_commit_id,
                    previous_commit_id=previous_commit_id,
                    dry_run=effective_dry_run,
                    issue_persistence="simulated" if effective_dry_run else "none",
                    file_path=file_path,
                )
                records.append(record)
                if per_repo_issues_dir is not None:
                    _write_repo_report(
                        per_repo_issues_dir,
                        record,
                        dry_run=effective_dry_run,
                        analysis_summary_file=analysis_summary_file,
                        previous_report=previous_report,
                    )
                click.echo()
                continue

            if decision.action == "close" and previous_issue_url:
                github, gitlab, issue_client = _get_or_create_client(
                    platform,
                    effective_dry_run,
                    github,
                    gitlab,
                )
                issue_client.add_issue_comment(
                    previous_issue_url,
                    "The latest analysis no longer reports metadata pitfalls/warnings. "
                    "Closing this issue.",
                )
                issue_client.close_issue(previous_issue_url)
                click.echo(f"  ✓ Issue closed: {previous_issue_url}")

                record = _build_report_entry(
                    repo_url=repo_url,
                    platform=platform,
                    pitfalls_count=pitfalls_count,
                    warnings_count=warnings_count,
                    issue_url=previous_issue_url,
                    analysis_date=analysis_date,
                    bot_version=bot_version,
                    metacheck_version=metacheck_version,
                    pitfalls_ids=pitfalls_ids,
                    warnings_ids=warnings_ids,
                    action="closed",
                    reason_code=reason_override or decision.reason,
                    previous_issue_url=previous_issue_url,
                    previous_issue_state=previous_issue_state,
                    findings_signature=current_signature,
                    current_commit_id=current_commit_id,
                    previous_commit_id=previous_commit_id,
                    dry_run=effective_dry_run,
                    issue_persistence="simulated" if effective_dry_run else "none",
                    file_path=file_path,
                )
                records.append(record)
                if per_repo_issues_dir is not None:
                    _write_repo_report(
                        per_repo_issues_dir,
                        record,
                        dry_run=effective_dry_run,
                        analysis_summary_file=analysis_summary_file,
                        previous_report=previous_report,
                    )
                click.echo()
                continue

            # Generate issue content
            report = pitfalls.format_report(repo_url, data)
            body = pitfalls.create_issue_body(report, custom_message)

            # Save issue body
            body_file = current_issues_dir / "issue_report.md"
            with open(body_file, "w", encoding="utf-8") as f:
                f.write(body)
            click.echo(f"  Issue body saved to: {body_file}")

            # Create issue
            click.echo(f"  Detected platform: {platform}")
            title = "Automated Metadata Quality Report from CodeMetaSoft"

            if platform == "github":
                github, gitlab, issue_client = _get_or_create_client(
                    platform,
                    effective_dry_run,
                    github,
                    gitlab,
                )
                issue_url = issue_client.create_issue(repo_url, title, body)
            elif platform == "gitlab.com":
                github, gitlab, issue_client = _get_or_create_client(
                    platform,
                    effective_dry_run,
                    github,
                    gitlab,
                )
                issue_url = issue_client.create_issue(repo_url, title, body)
            else:
                raise ValueError(f"Unsupported platform: {platform}")

            is_simulated = effective_dry_run
            if is_simulated:
                click.echo(f"  ✓ Issue simulated: {issue_url}")
            else:
                click.echo(f"  ✓ Issue created: {issue_url}")

            record = _build_report_entry(
                repo_url=repo_url,
                platform=platform,
                pitfalls_count=pitfalls_count,
                warnings_count=warnings_count,
                issue_url=None if is_simulated else issue_url,
                analysis_date=analysis_date,
                bot_version=bot_version,
                metacheck_version=metacheck_version,
                pitfalls_ids=pitfalls_ids,
                warnings_ids=warnings_ids,
                action="simulated_created" if is_simulated else "created",
                reason_code=reason_override or decision.reason,
                previous_issue_url=previous_issue_url,
                previous_issue_state=previous_issue_state,
                findings_signature=current_signature,
                current_commit_id=current_commit_id,
                previous_commit_id=previous_commit_id,
                dry_run=effective_dry_run,
                issue_persistence="simulated" if is_simulated else "posted",
                simulated_issue_url=issue_url if is_simulated else None,
                file_path=file_path,
            )
            records.append(record)
            if per_repo_issues_dir is not None:
                _write_repo_report(
                    per_repo_issues_dir,
                    record,
                    dry_run=effective_dry_run,
                    analysis_summary_file=analysis_summary_file,
                    previous_report=previous_report,
                )

        except Exception as e:
            click.echo(f"  ✗ Error: {e}", err=True)
            record = _build_report_entry(
                repo_url=repo_url,
                platform=platform,
                pitfalls_count=pitfalls_count,
                warnings_count=warnings_count,
                issue_url=None,
                analysis_date=analysis_date,
                bot_version=bot_version,
                metacheck_version=metacheck_version,
                pitfalls_ids=pitfalls_ids,
                warnings_ids=warnings_ids,
                action="failed",
                reason_code="exception",
                dry_run=dry_run,
                issue_persistence="none",
                file_path=file_path,
                error=str(e),
            )
            records.append(record)
            if per_repo_issues_dir is not None:
                _write_repo_report(
                    per_repo_issues_dir,
                    record,
                    dry_run=dry_run,
                    analysis_summary_file=analysis_summary_file,
                    previous_report=previous_report,
                )

        click.echo()

    counters = _build_counters(records)

    report = {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": dry_run,
            "analysis_summary_file": (
                str(analysis_summary_file)
                if analysis_summary_file is not None
                else None
            ),
            "previous_report_source": (
                str(previous_report) if previous_report is not None else None
            ),
        },
        "counters": counters,
        "records": records,
    }
    if not using_per_repo_mode:
        report_file = issues_dir / "report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        click.echo(f"Run report: {report_file}")

    # Display summary
    click.echo(f"\n{'=' * 60}")
    click.echo(
        "Summary: "
        f"Created {counters['created']} | "
        f"Simulated {counters['simulated']} | "
        f"Updated {counters['updated_by_comment']} | "
        f"Closed {counters['closed']} | "
        f"Skipped {counters['skipped']} | "
        f"Failed {counters['failed']}"
    )
    click.echo(f"{'=' * 60}\n")

    if counters["failed"]:
        click.echo(f"⚠️  {counters['failed']} issues failed to process.", err=True)
        return 1

    return 0
