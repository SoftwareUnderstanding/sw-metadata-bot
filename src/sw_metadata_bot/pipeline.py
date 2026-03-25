"""Pipeline command to run analysis workflows."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import click

from . import analysis_runtime, commit_lookup, pitfalls
from .config_utils import (
    copy_config_to_analysis_root,
    get_custom_message,
    get_opt_out_repositories,
    get_repositories,
    load_config,
    resolve_output_root,
    resolve_run_name,
    resolve_snapshot_tag,
    sanitize_repo_name,
)
from .metacheck_wrapper import metacheck_command

SNAPSHOT_TAG_PATTERN = re.compile(r"^(\d{8})(?:_(\d+))?$")
SNAPSHOT_INCREMENT_PATTERN = re.compile(r"^(.+?)_(\d+)$")


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


def _snapshot_sort_key(snapshot_tag: str) -> tuple[str, int] | None:
    """Return sortable key for snapshot tags matching YYYYMMDD or YYYYMMDD_N."""
    match = SNAPSHOT_TAG_PATTERN.fullmatch(snapshot_tag)
    if match is None:
        return None
    date_part, suffix_part = match.group(1), match.group(2)
    suffix = int(suffix_part) if suffix_part is not None else 0
    return (date_part, suffix)


def _find_latest_previous_snapshot_root(
    output_root: Path,
    run_name: str,
    current_snapshot_tag: str | None,
) -> Path | None:
    """Find latest previous snapshot root from same run folder."""
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

        has_new_layout = any(
            candidate.is_dir() and (candidate / "report.json").exists()
            for candidate in child.iterdir()
        )
        has_old_layout = (child / "issues_out" / "report.json").exists()
        has_run_report = (child / "run_report.json").exists()
        if has_new_layout or has_old_layout or has_run_report:
            candidates.append((key, child))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def find_latest_previous_report(
    output_root: Path,
    run_name: str,
    current_snapshot_tag: str | None,
) -> Path | None:
    """Find latest previous report path from same run folder."""
    snapshot_root = _find_latest_previous_snapshot_root(
        output_root=output_root,
        run_name=run_name,
        current_snapshot_tag=current_snapshot_tag,
    )
    if snapshot_root is None:
        return None

    run_report = snapshot_root / "run_report.json"
    if run_report.exists():
        return run_report

    legacy_report = snapshot_root / "issues_out" / "report.json"
    if legacy_report.exists():
        return legacy_report

    return None


def _snapshot_root_from_report_path(report_path: Path | None) -> Path | None:
    """Resolve snapshot root directory from a report file path."""
    if report_path is None:
        return None
    if report_path.name == "run_report.json":
        return report_path.parent
    if report_path.name == "report.json" and report_path.parent.name == "issues_out":
        return report_path.parent.parent
    if report_path.name == "report.json":
        return report_path.parent.parent
    return report_path.parent


def run_pipeline(
    config_file: Path,
    dry_run: bool,
    snapshot_tag: str | None,
    previous_report: Path | None,
) -> None:
    """Run analysis and write issue decision records without API side effects."""
    config = load_config(config_file)
    repositories = get_repositories(config)
    custom_message = get_custom_message(config)
    opt_out_repos = get_opt_out_repositories(config)
    output_root = resolve_output_root(config, config_file)
    run_folder_name = resolve_run_name(config, config_file)
    requested_snapshot_tag = resolve_snapshot_tag(config, snapshot_tag)

    run_root = output_root / run_folder_name
    resolved_snapshot_tag = _resolve_unique_snapshot_tag(
        run_root=run_root,
        snapshot_tag=requested_snapshot_tag,
    )

    analysis_root = (
        run_root / resolved_snapshot_tag if resolved_snapshot_tag else run_root
    )
    analysis_output_file = analysis_root / "analysis_results.json"

    copy_config_to_analysis_root(config_file, analysis_root)
    analysis_root.mkdir(parents=True, exist_ok=True)

    resolved_previous_report = previous_report
    if resolved_previous_report is None:
        resolved_previous_report = find_latest_previous_report(
            output_root=output_root,
            run_name=run_folder_name,
            current_snapshot_tag=resolved_snapshot_tag,
        )
    previous_snapshot_root = _snapshot_root_from_report_path(resolved_previous_report)

    evaluated_repositories: dict[str, dict[str, str]] = {}
    run_records: list[dict[str, object]] = []

    for repo_url in repositories:
        per_repo = analysis_runtime.resolve_per_repo_paths(analysis_root, repo_url)
        repo_folder = per_repo["repo_folder"]
        repo_folder.mkdir(parents=True, exist_ok=True)

        previous_record = analysis_runtime.load_previous_repo_record(
            previous_snapshot_root, repo_url
        )
        previous_commit_id = (
            analysis_runtime.extract_previous_commit(previous_record)
            if previous_record
            else None
        )

        try:
            current_commit_id = commit_lookup.get_repo_head_commit(repo_url)
        except Exception:
            current_commit_id = None

        reused_previous = False
        if (
            previous_snapshot_root is not None
            and previous_record is not None
            and previous_commit_id
            and current_commit_id
            and previous_commit_id != "Unknown"
            and current_commit_id != "Unknown"
            and current_commit_id == previous_commit_id
        ):
            previous_repo_folder = previous_snapshot_root / sanitize_repo_name(repo_url)
            if previous_repo_folder.exists():
                analysis_runtime.copy_previous_repo_artifacts(
                    previous_repo_folder, repo_folder
                )
                reused_previous = True

        if not reused_previous:
            analysis_runtime.run_metacheck_for_repo(
                repo_url, repo_folder, metacheck_command
            )

        normalized_repo = analysis_runtime.normalize_repo_url(repo_url)
        if normalized_repo in opt_out_repos:
            record = {
                "repo_url": repo_url,
                "platform": analysis_runtime.detect_platform_from_repo_url(repo_url),
                "pitfalls_count": 0,
                "warnings_count": 0,
                "issue_url": None,
                "analysis_date": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "sw_metadata_bot_version": pitfalls.__version__,
                "rsmetacheck_version": "unknown",
                "pitfalls_ids": [],
                "warnings_ids": [],
                "action": "skipped",
                "reason_code": "in_opt_out_list",
                "dry_run": dry_run,
                "issue_persistence": "none",
                "current_commit_id": current_commit_id,
                "file": str(repo_folder / "pitfall.jsonld"),
            }
        else:
            record = analysis_runtime.create_analysis_record(
                repo_url=repo_url,
                repo_folder=repo_folder,
                previous_record=previous_record,
                current_commit_id=current_commit_id,
                dry_run=dry_run,
                custom_message=custom_message,
            )

        analysis_runtime.write_analysis_repo_report(
            repo_folder,
            record,
            dry_run=dry_run,
            analysis_summary_file=analysis_output_file,
            previous_report=resolved_previous_report,
        )
        run_records.append(record)

        evaluated_repositories[sanitize_repo_name(repo_url)] = {
            "url": repo_url,
            "commit_id": current_commit_id or "Unknown",
        }

    analysis_summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {"evaluated_repositories": evaluated_repositories},
    }
    with open(analysis_output_file, "w", encoding="utf-8") as f:
        json.dump(analysis_summary, f, indent=2)

    run_report = analysis_runtime.build_analysis_run_report(
        run_records,
        dry_run=dry_run,
        analysis_summary_file=analysis_output_file,
        previous_report=resolved_previous_report,
    )
    run_report_file = analysis_root / "run_report.json"
    with open(run_report_file, "w", encoding="utf-8") as f:
        json.dump(run_report, f, indent=2)


@click.command()
@click.option(
    "--config-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Unified JSON configuration file.",
)
@click.option(
    "--snapshot-tag",
    type=str,
    default=None,
    help="Optional snapshot suffix folder (for example 2026-03).",
)
@click.option(
    "--previous-report",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Previous run_report.json used for incremental issue handling.",
)
def run_analysis_command(
    config_file: Path,
    snapshot_tag: str | None,
    previous_report: Path | None,
) -> None:
    """Run analysis and compute issue lifecycle decisions in dry-run mode."""
    run_pipeline(
        config_file=config_file,
        dry_run=True,
        snapshot_tag=snapshot_tag,
        previous_report=previous_report,
    )
