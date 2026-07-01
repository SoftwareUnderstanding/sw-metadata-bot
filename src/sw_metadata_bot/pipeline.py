"""Pipeline command to run analysis workflows."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import click

from sw_metadata_bot.config.schemas import BotConfig

from . import __version__, analysis_runtime, commit_lookup, constants
from .config.config_utils import detect_platform, sanitize_repo_name
from .reporting import RecordAnalysis, RecordLifecycle, build_record_entry

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
            candidate.is_dir() and (candidate / constants.FILENAME_REPORT).exists()
            for candidate in child.iterdir()
        )
        has_run_report = (child / constants.FILENAME_RUN_REPORT).exists()
        if has_new_layout or has_run_report:
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

    run_report = snapshot_root / constants.FILENAME_RUN_REPORT
    if run_report.exists():
        return run_report

    return None


def _snapshot_root_from_report_path(report_path: Path | None) -> Path | None:
    """Resolve snapshot root directory from a report file path."""
    if report_path is None:
        return None
    return report_path.parent


def run_pipeline(
    config_file: Path,
    dry_run: bool,
    snapshot_tag: str | None,
    previous_report: Path | None,
    force_analysis: bool = False,
) -> None:
    """Run analysis and write issue decision records without API side effects.

    When force_analysis is True, the pipeline will bypass artifact reuse for
    unchanged repositories and treat them as if the repository was updated.
    """
    # Ensure the provided config path is absolute and resolvable so we can
    # persist a resolvable `input_config_file` in run metadata.
    config_file = config_file.resolve()
    config = BotConfig.from_json(config_file)

    repositories = config.get_repositories()
    # get rsmetacheck options from the main config file
    rsmetacheck_config_file = config.get_rsmetacheck_config_file()
    rsmetacheck_config_profile = config.get_rsmetacheck_config_profile()
    custom_message = config.get_custom_issue_message()
    generate_codemeta_if_missing = config.get_generate_codemeta_if_missing()
    opt_out_repos = config.get_issue_opt_outs()
    output_root = Path(config.get_output_root_dir())
    run_folder_name = config.get_run_name()
    requested_snapshot_tag = config.resolve_snapshot_tag(snapshot_tag)

    run_root = output_root / run_folder_name
    run_root.mkdir(parents=True, exist_ok=True)
    resolved_snapshot_tag = _resolve_unique_snapshot_tag(
        run_root=run_root,
        snapshot_tag=requested_snapshot_tag,
    )

    analysis_root = (
        run_root / resolved_snapshot_tag if resolved_snapshot_tag else run_root
    )
    analysis_root.mkdir(parents=True, exist_ok=True)
    config_analysis_path = analysis_root / constants.FILENAME_CONFIG_SNAPSHOT
    analysis_report_path = analysis_root / constants.FILENAME_ANALYSIS_RESULTS
    config.to_json(config_analysis_path, explicit=True)

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

        try:
            reused_previous = False
            if not force_analysis and (
                previous_snapshot_root is not None
                and previous_record is not None
                and previous_commit_id
                and current_commit_id
                and previous_commit_id != "Unknown"
                and current_commit_id != "Unknown"
                and current_commit_id == previous_commit_id
            ):
                previous_repo_folder = previous_snapshot_root / sanitize_repo_name(
                    repo_url
                )
                if previous_repo_folder.exists():
                    analysis_runtime.copy_previous_repo_artifacts(
                        previous_repo_folder, repo_folder
                    )
                    reused_previous = True

            if not reused_previous:
                analysis_runtime.run_metacheck_for_repo(
                    repo_url,
                    repo_folder,
                    generate_codemeta_if_missing=generate_codemeta_if_missing,
                    rsmetacheck_config_file=rsmetacheck_config_file,
                    rsmetacheck_config_profile=rsmetacheck_config_profile,
                )

            normalized_repo = analysis_runtime.normalize_repo_url(repo_url)
            if normalized_repo in opt_out_repos:
                record = build_record_entry(
                    run_root=run_root,
                    repo_url=repo_url,
                    platform=detect_platform(repo_url),
                    analysis=RecordAnalysis(
                        analysis_date=datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        bot_version=__version__,
                        rsmetacheck_version="unknown",
                        pitfalls_count=0,
                        warnings_count=0,
                        pitfalls_ids=[],
                        warnings_ids=[],
                    ),
                    lifecycle=RecordLifecycle(
                        action="skipped",
                        reason_code="in_opt_out_list",
                        current_commit_id=current_commit_id,
                        dry_run=dry_run,
                        issue_persistence="none",
                        file_path=repo_folder / "pitfall.jsonld",
                    ),
                )
            else:
                record = analysis_runtime.create_analysis_record(
                    run_root=run_root,
                    repo_url=repo_url,
                    repo_folder=repo_folder,
                    previous_record=previous_record,
                    current_commit_id=current_commit_id,
                    dry_run=dry_run,
                    custom_message=custom_message,
                    force_analysis=force_analysis,
                )

            analysis_runtime.write_analysis_repo_report(
                repo_folder,
                record,
                dry_run=dry_run,
                run_root=run_root,
                analysis_summary_file=analysis_report_path,
                previous_report=resolved_previous_report,
            )
        except Exception as exc:
            record = build_record_entry(
                run_root=run_root,
                repo_url=repo_url,
                platform=detect_platform(repo_url),
                analysis=RecordAnalysis(
                    analysis_date="unknown",
                    bot_version=__version__,
                    rsmetacheck_version="unknown",
                    pitfalls_count=0,
                    warnings_count=0,
                    pitfalls_ids=[],
                    warnings_ids=[],
                ),
                lifecycle=RecordLifecycle(
                    action="failed",
                    reason_code="exception",
                    findings_signature="",
                    current_commit_id=current_commit_id,
                    previous_commit_id=(
                        analysis_runtime.extract_previous_commit(previous_record)
                        if previous_record is not None
                        else None
                    ),
                    dry_run=dry_run,
                    issue_persistence="none",
                    issue_url=None,
                    file_path=repo_folder / constants.FILENAME_PITFALL,
                    error=str(exc),
                ),
            )
            try:
                analysis_runtime.write_analysis_repo_report(
                    repo_folder,
                    record,
                    dry_run=dry_run,
                    run_root=run_root,
                    analysis_summary_file=analysis_report_path,
                    previous_report=resolved_previous_report,
                )
            except Exception:
                pass

        run_records.append(record)

        evaluated_repositories[sanitize_repo_name(repo_url)] = {
            "url": repo_url,
            "commit_id": current_commit_id or "Unknown",
        }

    analysis_summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {"evaluated_repositories": evaluated_repositories},
    }
    with open(analysis_report_path, "w", encoding="utf-8") as f:
        json.dump(analysis_summary, f, indent=2)

    run_report = analysis_runtime.build_analysis_run_report(
        run_records,
        dry_run=dry_run,
        run_root=run_root,
        analysis_summary_file=analysis_report_path,
        previous_report=resolved_previous_report,
        input_config_file=config_file,
    )
    run_report_file = analysis_root / constants.FILENAME_RUN_REPORT
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
@click.option(
    "--force-analysis",
    is_flag=True,
    default=False,
    help="Force analysis even when the repository commit id is unchanged.",
)
def run_analysis_command(
    config_file: Path,
    snapshot_tag: str | None,
    previous_report: Path | None,
    force_analysis: bool,
) -> None:
    """Run analysis and compute issue lifecycle decisions in dry-run mode."""
    run_pipeline(
        config_file=config_file,
        dry_run=True,
        snapshot_tag=snapshot_tag,
        previous_report=previous_report,
        force_analysis=force_analysis,
    )
