"""Pipeline command to run analysis then issue creation."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import click
import requests

from . import github_api, history
from .community_config import (
    append_opt_out_repository,
    get_repositories,
    load_community_config,
    resolve_output_root,
    resolve_run_name,
    resolve_snapshot_tag,
)
from .create_issues import create_issues_command
from .metacheck_wrapper import metacheck_command

SNAPSHOT_TAG_PATTERN = re.compile(r"^(\d{8})(?:_(\d+))?$")
SNAPSHOT_INCREMENT_PATTERN = re.compile(r"^(.+?)_(\d+)$")


def _normalize_repo_url(url: str) -> str:
    """Normalize repository URL for cross-report matching."""
    return url.strip().rstrip("/")


def _extract_previous_commit(record: dict) -> str | None:
    """Return previous commit id from report records with compatibility fallback."""
    current_commit = record.get("current_commit_id")
    if isinstance(current_commit, str) and current_commit:
        return current_commit

    legacy_commit = record.get("commit_id")
    if isinstance(legacy_commit, str) and legacy_commit:
        return legacy_commit

    return None


def _is_supported_for_commit_skip(repo_url: str) -> bool:
    """Return whether pre-analysis commit lookup is supported for a repo URL."""
    return "github.com" in repo_url.lower()


def _parse_github_repo(repo_url: str) -> tuple[str, str] | None:
    """Parse owner/repo from a GitHub repository URL."""
    match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", repo_url, re.IGNORECASE)
    if match is None:
        return None
    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    return owner, repo


def _get_repo_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit for a GitHub repository."""
    parsed = _parse_github_repo(repo_url)
    if parsed is None:
        return None

    owner, repo = parsed
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    response = requests.get(url, params={"per_page": 1}, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    sha = first.get("sha")
    return str(sha) if isinstance(sha, str) and sha else None


def _build_repo_not_updated_record(
    repo_url: str,
    current_commit_id: str | None,
    previous_commit_id: str | None,
    *,
    dry_run: bool,
    reason_code: str = "repo_not_updated",
    previous_issue_url: str | None = None,
    unsubscribe_detected: bool = False,
) -> dict[str, object]:
    """Build report record for repositories skipped before analysis."""
    platform = "github" if "github.com" in repo_url.lower() else None
    record: dict[str, object] = {
        "repo_url": repo_url,
        "platform": platform,
        "pitfalls_count": 0,
        "warnings_count": 0,
        "issue_url": None,
        "analysis_date": "not-run",
        "sw_metadata_bot_version": "unknown",
        "rsmetacheck_version": "unknown",
        "pitfalls_ids": [],
        "warnings_ids": [],
        "action": "skipped",
        "reason_code": reason_code,
        "findings_signature": "",
        "current_commit_id": current_commit_id,
        "previous_commit_id": previous_commit_id,
        "dry_run": dry_run,
        "issue_persistence": "none",
    }
    if previous_issue_url:
        record["previous_issue_url"] = previous_issue_url
    if unsubscribe_detected:
        record["unsubscribe_detected"] = True
    return record


def _is_unsubscribe_comment(comment: str) -> bool:
    """Return True when a comment is exactly the unsubscribe keyword."""
    return comment.strip().lower() == "unsubscribe"


def _detect_unsubscribe_in_previous_issue(issue_url: str, dry_run: bool) -> bool:
    """Check whether previous issue comments include an unsubscribe request."""
    client = github_api.GitHubAPI(dry_run=dry_run)
    comments = client.get_issue_comments(issue_url)
    return any(_is_unsubscribe_comment(comment) for comment in comments)


def _merge_pre_skipped_records(
    report_file: Path,
    skipped_records: list[dict[str, object]],
) -> None:
    """Merge pre-analysis skipped records into create-issues report output."""
    if not skipped_records:
        return

    with open(report_file, encoding="utf-8") as f:
        report = json.load(f)

    records = report.get("records")
    if not isinstance(records, list):
        records = []
    records = [*skipped_records, *records]
    report["records"] = records

    counters = report.get("counters")
    if not isinstance(counters, dict):
        counters = {}
    counters["skipped"] = int(counters.get("skipped", 0)) + len(skipped_records)
    counters["total"] = int(counters.get("total", 0)) + len(skipped_records)
    report["counters"] = counters

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def _write_pre_skipped_only_report(
    report_file: Path,
    *,
    dry_run: bool,
    analysis_summary_file: Path,
    previous_report_source: Path | None,
    skipped_records: list[dict[str, object]],
) -> None:
    """Write report.json when all repositories are skipped before analysis."""
    report_file.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": dry_run,
            "analysis_summary_file": str(analysis_summary_file),
            "previous_report_source": (
                str(previous_report_source)
                if previous_report_source is not None
                else None
            ),
        },
        "counters": {
            "total": len(skipped_records),
            "created": 0,
            "simulated": 0,
            "updated_by_comment": 0,
            "closed": 0,
            "skipped": len(skipped_records),
            "failed": 0,
        },
        "records": skipped_records,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def _resolve_unique_snapshot_tag(
    run_root: Path, snapshot_tag: str | None
) -> str | None:
    """Return a non-colliding snapshot tag by adding or incrementing numeric suffixes."""
    if snapshot_tag is None:
        return None

    candidate_path = run_root / snapshot_tag
    if not candidate_path.exists():
        return snapshot_tag

    match = SNAPSHOT_INCREMENT_PATTERN.fullmatch(snapshot_tag)
    if match is None:
        base_tag = snapshot_tag
        suffix = 2
    else:
        base_tag = match.group(1)
        suffix = int(match.group(2)) + 1

    while True:
        candidate = f"{base_tag}_{suffix}"
        if not (run_root / candidate).exists():
            return candidate
        suffix += 1


def _resolve_run_paths(
    output_root: Path,
    run_name: str,
    snapshot_tag: str | None,
) -> tuple[Path, Path, Path, Path]:
    """Compute dedicated output paths for a pipeline run."""
    run_root = output_root / run_name

    if snapshot_tag:
        run_root = run_root / snapshot_tag

    somef_output_dir = run_root / "somef_outputs"
    pitfalls_output_dir = run_root / "pitfalls_outputs"
    analysis_output_file = run_root / "analysis_results.json"
    issues_output_dir = run_root / "issues_out"

    return (
        somef_output_dir,
        pitfalls_output_dir,
        analysis_output_file,
        issues_output_dir,
    )


def _snapshot_sort_key(snapshot_tag: str) -> tuple[str, int] | None:
    """Return sortable key for snapshot tags matching YYYYMMDD or YYYYMMDD_N."""
    match = SNAPSHOT_TAG_PATTERN.fullmatch(snapshot_tag)
    if match is None:
        return None
    date_part, suffix_part = match.group(1), match.group(2)
    suffix = int(suffix_part) if suffix_part is not None else 0
    return (date_part, suffix)


def find_latest_previous_report(
    output_root: Path,
    run_name: str,
    current_snapshot_tag: str | None,
) -> Path | None:
    """Find latest previous report.json from same run folder."""
    run_root = output_root / run_name
    if not run_root.exists() or not run_root.is_dir():
        return None

    candidates: list[tuple[tuple[str, int], Path]] = []
    for child in run_root.iterdir():
        if not child.is_dir():
            continue
        key = _snapshot_sort_key(child.name)
        if key is None:
            continue
        if current_snapshot_tag is not None and child.name == current_snapshot_tag:
            continue

        report_path = child / "issues_out" / "report.json"
        if report_path.exists():
            candidates.append((key, report_path))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def run_pipeline(
    community_config_file: Path,
    dry_run: bool,
    snapshot_tag: str | None,
    previous_report: Path | None,
) -> None:
    """Run analysis and issue creation for a community configuration."""
    community_config = load_community_config(community_config_file)
    repositories = get_repositories(community_config)
    output_root = resolve_output_root(community_config, community_config_file)
    run_folder_name = resolve_run_name(community_config, community_config_file)
    requested_snapshot_tag = resolve_snapshot_tag(community_config, snapshot_tag)

    run_root = output_root / run_folder_name
    resolved_snapshot_tag = _resolve_unique_snapshot_tag(
        run_root=run_root,
        snapshot_tag=requested_snapshot_tag,
    )

    somef_output_dir, pitfalls_output_dir, analysis_output_file, issues_output_dir = (
        _resolve_run_paths(
            output_root=output_root,
            run_name=run_folder_name,
            snapshot_tag=resolved_snapshot_tag,
        )
    )

    resolved_previous_report = previous_report
    if resolved_previous_report is None:
        resolved_previous_report = find_latest_previous_report(
            output_root=output_root,
            run_name=run_folder_name,
            current_snapshot_tag=resolved_snapshot_tag,
        )

    previous_commit_records = history.load_previous_commit_report(
        resolved_previous_report
    )
    previous_issue_records = history.load_previous_report(resolved_previous_report)
    repositories_to_analyze = repositories
    pre_skipped_records: list[dict[str, object]] = []

    if previous_commit_records:
        repositories_to_analyze = []
        for repo_url in repositories:
            normalized_repo = _normalize_repo_url(repo_url)
            previous = previous_commit_records.get(normalized_repo)
            if previous is None:
                repositories_to_analyze.append(repo_url)
                continue

            previous_commit_id = _extract_previous_commit(previous)
            if (
                previous_commit_id is None
                or previous_commit_id == "Unknown"
                or not _is_supported_for_commit_skip(repo_url)
            ):
                repositories_to_analyze.append(repo_url)
                continue

            try:
                current_commit_id = _get_repo_head_commit(repo_url)
            except Exception:
                repositories_to_analyze.append(repo_url)
                continue

            if (
                current_commit_id is not None
                and current_commit_id != "Unknown"
                and current_commit_id == previous_commit_id
            ):
                previous_issue = previous_issue_records.get(normalized_repo)
                previous_issue_url = None
                if previous_issue is not None:
                    value = previous_issue.get("issue_url")
                    if isinstance(value, str) and value:
                        previous_issue_url = value

                if previous_issue_url:
                    try:
                        unsubscribe_detected = _detect_unsubscribe_in_previous_issue(
                            issue_url=previous_issue_url,
                            dry_run=dry_run,
                        )
                    except Exception:
                        unsubscribe_detected = False

                    if unsubscribe_detected:
                        append_opt_out_repository(community_config_file, repo_url)
                        pre_skipped_records.append(
                            _build_repo_not_updated_record(
                                repo_url=repo_url,
                                current_commit_id=current_commit_id,
                                previous_commit_id=previous_commit_id,
                                dry_run=dry_run,
                                reason_code="unsubscribe",
                                previous_issue_url=previous_issue_url,
                                unsubscribe_detected=True,
                            )
                        )
                        continue

                pre_skipped_records.append(
                    _build_repo_not_updated_record(
                        repo_url=repo_url,
                        current_commit_id=current_commit_id,
                        previous_commit_id=previous_commit_id,
                        dry_run=dry_run,
                        previous_issue_url=previous_issue_url,
                    )
                )
                continue

            repositories_to_analyze.append(repo_url)

    analysis_input_file: Path | None = None
    temp_input_file: Path | None = None
    if repositories_to_analyze:
        with NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="pipeline_filtered_",
            delete=False,
            encoding="utf-8",
        ) as temp_file:
            json.dump({"repositories": repositories_to_analyze}, temp_file, indent=2)
            temp_input_file = Path(temp_file.name)
            analysis_input_file = temp_input_file

    ran_analysis = True
    if not repositories_to_analyze:
        ran_analysis = False
    else:
        metacheck_command.main(
            args=[
                "--input",
                str(analysis_input_file),
                "--somef-output",
                str(somef_output_dir),
                "--pitfalls-output",
                str(pitfalls_output_dir),
                "--analysis-output",
                str(analysis_output_file),
            ],
            standalone_mode=False,
        )

    create_issues_args = [
        "--pitfalls-output-dir",
        str(pitfalls_output_dir),
        "--issues-dir",
        str(issues_output_dir),
        "--community-config-file",
        str(community_config_file),
        "--analysis-summary-file",
        str(analysis_output_file),
    ]

    if resolved_previous_report is not None:
        create_issues_args.extend(["--previous-report", str(resolved_previous_report)])

    if dry_run:
        create_issues_args.append("--dry-run")

    if ran_analysis:
        create_issues_command.main(args=create_issues_args, standalone_mode=False)

    report_file = issues_output_dir / "report.json"
    if ran_analysis and pre_skipped_records:
        _merge_pre_skipped_records(
            report_file=report_file, skipped_records=pre_skipped_records
        )
    elif not ran_analysis:
        _write_pre_skipped_only_report(
            report_file=report_file,
            dry_run=dry_run,
            analysis_summary_file=analysis_output_file,
            previous_report_source=resolved_previous_report,
            skipped_records=pre_skipped_records,
        )

    if temp_input_file is not None and temp_input_file.exists():
        temp_input_file.unlink()


@click.command()
@click.option(
    "--community-config-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Unified community JSON configuration file.",
)
@click.option(
    "--snapshot-tag",
    type=str,
    default=None,
    help="Optional snapshot suffix folder (for example 2026-03).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run issue creation in dry-run mode without posting issues.",
)
@click.option(
    "--previous-report",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Previous report.json used for incremental issue handling.",
)
def run_pipeline_command(
    community_config_file: Path,
    snapshot_tag: str | None,
    dry_run: bool,
    previous_report: Path | None,
) -> None:
    """Run full pipeline: metacheck analysis then issue creation."""
    run_pipeline(
        community_config_file=community_config_file,
        dry_run=dry_run,
        snapshot_tag=snapshot_tag,
        previous_report=previous_report,
    )
