"""Create issues command - main logic."""

import json
import logging
from pathlib import Path
from typing import Protocol

import click

from . import github_api, gitlab_api, history, incremental, pitfalls

logger = logging.getLogger(__name__)


class IssueClientProtocol(Protocol):
    """Shared methods used by both GitHub and GitLab issue clients."""

    def create_issue(self, repo_url: str, title: str, body: str) -> str: ...
    def get_issue(self, issue_url: str) -> dict: ...
    def get_issue_comments(self, issue_url: str) -> list[str]: ...
    def add_issue_comment(self, issue_url: str, body: str) -> None: ...
    def close_issue(self, issue_url: str) -> None: ...


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


def _append_opt_out_repo(opt_outs_file: Path | None, repo_url: str) -> bool:
    """Append repository URL to the configured opt-out file if missing."""
    if opt_outs_file is None:
        return False

    with open(opt_outs_file, encoding="utf-8") as f:
        data = json.load(f)

    repositories = data.get("repositories", [])
    if not isinstance(repositories, list):
        raise click.ClickException(
            f"Invalid format in {opt_outs_file}: 'repositories' must be a list"
        )

    normalized_existing = {
        _normalize_repo_url(url) for url in repositories if isinstance(url, str)
    }
    normalized_repo = _normalize_repo_url(repo_url)
    if normalized_repo in normalized_existing:
        return False

    repositories.append(normalized_repo)
    data["repositories"] = repositories
    with open(opt_outs_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True


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


def load_config(config_path: Path | None) -> dict:
    """Load issue configuration from JSON file."""
    if config_path is None:
        return {"custom_message": None}
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def _load_repository_list(file_path: Path) -> set[str]:
    """Load repository URLs from a JSON file with a 'repositories' key."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    repositories = data.get("repositories", [])
    if not isinstance(repositories, list):
        raise click.ClickException(
            f"Invalid format in {file_path}: 'repositories' must be a list"
        )

    return {_normalize_repo_url(url) for url in repositories if isinstance(url, str)}


def _extract_check_ids(checks: list[dict]) -> tuple[list[str], list[str]]:
    """Extract unique pitfall and warning codes from checks."""
    pitfall_ids: list[str] = []
    warning_ids: list[str] = []

    for check in checks:
        pitfall_url = str(check.get("pitfall", ""))
        code = pitfall_url.split("#")[-1] if "#" in pitfall_url else pitfall_url
        if not code:
            continue

        if code.startswith("P") and code not in pitfall_ids:
            pitfall_ids.append(code)
        elif code.startswith("W") and code not in warning_ids:
            warning_ids.append(code)

    return pitfall_ids, warning_ids


def _safe_get_metacheck_version(data: dict) -> str:
    """Get metacheck version without failing issue reporting."""
    try:
        return pitfalls.get_metacheck_version(data)
    except Exception:
        return "unknown"


def _get_analysis_date(data: dict) -> str:
    """Get analysis date from pitfalls payload."""
    return str(data.get("dateCreated", "unknown"))


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
    reason: str | None = None,
    previous_issue_url: str | None = None,
    previous_issue_state: str | None = None,
    findings_signature: str | None = None,
    current_commit_id: str | None = None,
    previous_commit_id: str | None = None,
    unsubscribe_detected: bool | None = None,
    file_path: Path | None = None,
    error: str | None = None,
) -> dict[str, object]:
    """Build a report entry with common metadata and optional fields."""
    entry: dict[str, object] = {
        "repo_url": repo_url,
        "platform": platform,
        "pitfalls_count": pitfalls_count,
        "warnings_count": warnings_count,
        "analysis_date": analysis_date,
        "sw_metadata_bot_version": bot_version,
        "rsmetacheck_version": metacheck_version,
        "pitfalls_ids": pitfalls_ids or [],
        "warnings_ids": warnings_ids or [],
    }

    if issue_url is not None:
        entry["issue_url"] = issue_url
    if action is not None:
        entry["action"] = action
    if reason is not None:
        entry["reason"] = reason
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
    if file_path is not None:
        entry["file"] = str(file_path)
    if error is not None:
        entry["error"] = error

    return entry


@click.command()
@click.option(
    "--pitfalls-output-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Directory containing pitfalls JSON-LD files from metacheck analysis.",
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
    "--opt-outs-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="JSON file containing repositories to exclude from issue creation.",
)
@click.option(
    "--issue-config-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="JSON file containing issue configuration.",
)
@click.option(
    "--analysis-summary-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Analysis summary JSON file (for commit-aware incremental handling).",
)
@click.option(
    "--previous-created-report",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Previous created_issues_report.json to enable incremental issue handling.",
)
def create_issues_command(
    pitfalls_output_dir: Path,
    issues_dir: Path,
    dry_run: bool,
    log_level: str,
    opt_outs_file: Path | None,
    issue_config_file: Path | None,
    analysis_summary_file: Path | None,
    previous_created_report: Path | None,
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

    # Create output directory
    issues_dir.mkdir(parents=True, exist_ok=True)

    # Initialize API clients
    github, gitlab = None, None

    mode = "DRY RUN" if dry_run else "PRODUCTION"
    click.echo(f"\n{'=' * 60}")
    click.echo(f"Creating issues [{mode}]")
    click.echo(f"{'=' * 60}\n")

    issue_config = load_config(issue_config_file)
    previous_records = history.load_previous_created_report(previous_created_report)

    if analysis_summary_file is None:
        fallback_summary = pitfalls_output_dir.parent / "analysis_results.json"
        analysis_summary_file = fallback_summary if fallback_summary.exists() else None
    current_commit_map = _load_analysis_commit_map(analysis_summary_file)

    opt_out_repos: set[str] = set()
    if opt_outs_file is not None:
        opt_out_repos = _load_repository_list(opt_outs_file)
        click.echo(
            f"Loaded {len(opt_out_repos)} opt-out repositories from: {opt_outs_file}\n"
        )

    # Find pitfalls files
    pitfalls_files = sorted(pitfalls_output_dir.glob("*.jsonld"))
    if not pitfalls_files:
        click.echo(f"No pitfalls files found in {pitfalls_output_dir}", err=True)
        return

    click.echo(f"Found {len(pitfalls_files)} pitfalls files to process\n")

    # Process each file
    created = []
    failed = []
    skipped = []
    action_report = []
    bot_version = pitfalls.__version__

    for i, file_path in enumerate(pitfalls_files, 1):
        click.echo(f"[{i}/{len(pitfalls_files)}] Processing: {file_path.name}")

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
                skipped.append({"repo_url": repo_url, "file": str(file_path)})
                action_report.append(
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
                        action="stop",
                        reason="in_opt_out_list",
                        findings_signature=current_signature,
                        current_commit_id=current_commit_id,
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
                previous_commit_id = (
                    str(previous_data.get("commit_id"))
                    if previous_data.get("commit_id") is not None
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

            decision = incremental.evaluate(
                previous_exists=previous_exists,
                unsubscribed=unsubscribe_detected,
                repo_updated=repo_updated,
                has_findings=has_findings,
                identical_findings=current_signature == previous_signature,
                previous_issue_open=previous_issue_open,
            )

            if decision.action == "stop":
                if decision.reason == "unsubscribe":
                    added_to_opt_out = _append_opt_out_repo(opt_outs_file, repo_url)
                    if added_to_opt_out:
                        opt_out_repos.add(normalized_repo)
                    click.echo("  ↷ Skipped: unsubscribe detected in previous issue")
                else:
                    click.echo(f"  ↷ Skipped: {decision.reason}")

                skipped.append(
                    {
                        "repo_url": repo_url,
                        "file": str(file_path),
                        "reason": decision.reason,
                    }
                )
                action_report.append(
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
                        action=decision.action,
                        reason=decision.reason,
                        previous_issue_url=previous_issue_url,
                        previous_issue_state=previous_issue_state,
                        findings_signature=current_signature,
                        current_commit_id=current_commit_id,
                        previous_commit_id=previous_commit_id,
                        unsubscribe_detected=unsubscribe_detected,
                    )
                )
                click.echo()
                continue

            if decision.action == "comment" and previous_issue_url:
                github, gitlab, issue_client = _get_or_create_client(
                    platform,
                    dry_run,
                    github,
                    gitlab,
                )

                report = pitfalls.format_report(repo_url, data)
                body = pitfalls.create_issue_body(
                    report, issue_config.get("custom_message")
                )
                issue_client.add_issue_comment(
                    previous_issue_url,
                    f"New analysis detected updated findings.\n\n{body}",
                )
                click.echo(f"  ✓ Issue updated by comment: {previous_issue_url}")

                action_report.append(
                    _build_report_entry(
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
                        action=decision.action,
                        reason=decision.reason,
                        previous_issue_url=previous_issue_url,
                        previous_issue_state=previous_issue_state,
                        findings_signature=current_signature,
                        current_commit_id=current_commit_id,
                        previous_commit_id=previous_commit_id,
                    )
                )
                click.echo()
                continue

            if decision.action == "close" and previous_issue_url:
                github, gitlab, issue_client = _get_or_create_client(
                    platform,
                    dry_run,
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

                action_report.append(
                    _build_report_entry(
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
                        action=decision.action,
                        reason=decision.reason,
                        previous_issue_url=previous_issue_url,
                        previous_issue_state=previous_issue_state,
                        findings_signature=current_signature,
                        current_commit_id=current_commit_id,
                        previous_commit_id=previous_commit_id,
                    )
                )
                click.echo()
                continue

            # Generate issue content
            report = pitfalls.format_report(repo_url, data)
            body = pitfalls.create_issue_body(
                report, issue_config.get("custom_message")
            )

            # Save issue body
            body_file = issues_dir / f"issue_body_{file_path.stem}.md"
            with open(body_file, "w", encoding="utf-8") as f:
                f.write(body)
            click.echo(f"  Issue body saved to: {body_file}")

            # Create issue
            click.echo(f"  Detected platform: {platform}")
            title = "Automated Metadata Quality Report from CodeMetaSoft"

            if platform == "github":
                github, gitlab, issue_client = _get_or_create_client(
                    platform,
                    dry_run,
                    github,
                    gitlab,
                )
                issue_url = issue_client.create_issue(repo_url, title, body)
            elif platform == "gitlab.com":
                github, gitlab, issue_client = _get_or_create_client(
                    platform,
                    dry_run,
                    github,
                    gitlab,
                )
                issue_url = issue_client.create_issue(repo_url, title, body)
            else:
                raise ValueError(f"Unsupported platform: {platform}")

            click.echo(f"  ✓ Issue created: {issue_url}")

            created.append(
                _build_report_entry(
                    repo_url=repo_url,
                    platform=platform,
                    pitfalls_count=pitfalls_count,
                    warnings_count=warnings_count,
                    issue_url=issue_url,
                    analysis_date=analysis_date,
                    bot_version=bot_version,
                    metacheck_version=metacheck_version,
                    pitfalls_ids=pitfalls_ids,
                    warnings_ids=warnings_ids,
                    action="create",
                    reason=decision.reason,
                    previous_issue_url=previous_issue_url,
                    previous_issue_state=previous_issue_state,
                    findings_signature=current_signature,
                    current_commit_id=current_commit_id,
                    previous_commit_id=previous_commit_id,
                )
            )
            action_report.append(created[-1])

        except Exception as e:
            click.echo(f"  ✗ Error: {e}", err=True)
            failed.append(
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
                    file_path=file_path,
                    error=str(e),
                )
            )

        click.echo()

    # Save reports
    with open(issues_dir / "created_issues_report.json", "w") as f:
        json.dump(created, f, indent=2)
    click.echo(f"Created issues report: {issues_dir / 'created_issues_report.json'}")

    if failed:
        with open(issues_dir / "failed_issues_report.json", "w") as f:
            json.dump(failed, f, indent=2)
        click.echo(f"Failed issues report: {issues_dir / 'failed_issues_report.json'}")

    if skipped:
        with open(issues_dir / "skipped_issues_report.json", "w") as f:
            json.dump(skipped, f, indent=2)
        click.echo(
            f"Skipped issues report: {issues_dir / 'skipped_issues_report.json'}"
        )

    with open(issues_dir / "actions_report.json", "w") as f:
        json.dump(action_report, f, indent=2)
    click.echo(f"Actions report: {issues_dir / 'actions_report.json'}")

    # Display summary
    click.echo(f"\n{'=' * 60}")
    click.echo(
        f"Summary: Created {len(created)} | Skipped {len(skipped)} | Failed {len(failed)}"
    )
    click.echo(f"{'=' * 60}\n")

    if failed:
        click.echo(f"⚠️  {len(failed)} issues failed to create.", err=True)
        return 1

    return 0
