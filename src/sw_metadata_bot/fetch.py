"""Fetch previously created issues and retrieve unsubscribe comment."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import click

from . import constants, github_api, gitlab_api
from .config.config_utils import (
    append_opt_out_to_config,
    detect_platform,
    sanitize_repo_name,
)
from .reporting import load_report, write_report_file


def _now_utc_iso() -> str:
    """Return a UTC timestamp suitable for report persistence."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_unsubscribe_comment(comment: str) -> bool:
    """Return True when a comment is exactly the unsubscribe keyword."""
    return comment.strip().lower() == "unsubscribe"


def _issue_url_for_fetch(record: dict[str, object]) -> str | None:
    """Return the primary issue URL used for fetch operations."""
    current = record.get("issue_url")
    if isinstance(current, str) and current:
        return current
    return None


def _detect_platform_for_fetch(repo_url: str, record: dict[str, object]) -> str | None:
    """Resolve platform for fetch from record metadata and repository URL."""
    value = record.get("platform")
    if isinstance(value, str) and value:
        if value in {"github", "gitlab", "gitlab.com"}:
            return value

    return detect_platform(repo_url)


def _issue_is_closed(issue_data: dict[str, object] | None) -> bool:
    """Return True when issue data indicates the issue is closed."""
    if not isinstance(issue_data, dict):
        return False
    state_value = issue_data.get("state")
    return isinstance(state_value, str) and state_value.strip().lower() == "closed"


def _resolve_input_config_path(
    input_config_value: object, analysis_root: Path
) -> Path | None:
    """Resolve the original input config file path from run metadata."""
    if not isinstance(input_config_value, str) or not input_config_value:
        return None

    input_config_path = Path(input_config_value)
    if not input_config_path.is_absolute():
        input_config_path = analysis_root.parent / input_config_path
    return input_config_path


def _write_per_repo_report(
    analysis_root: Path,
    record: dict[str, object],
    analysis_summary_file: Path | None,
    previous_report: Path | None,
) -> None:
    """Persist a single-record per-repo report alongside repository artifacts."""
    repo_url = record.get("repo_url")
    if not isinstance(repo_url, str) or not repo_url:
        return

    write_report_file(
        report_file=analysis_root
        / sanitize_repo_name(repo_url)
        / constants.FILENAME_REPORT,
        records=[record],
        dry_run=False,
        run_root=analysis_root.parent,
        analysis_summary_file=analysis_summary_file,
        previous_report=previous_report,
    )


def _save_fetch_diff(analysis_root: Path, records: list[dict[str, object]]) -> None:
    """Persist a diff report containing all changed fetch records."""
    diff_payload = {
        "generated_at": _now_utc_iso(),
        "record_count": len(records),
        "records": records,
    }
    fetch_diff_file = analysis_root / constants.FILENAME_FETCH_DIFF
    with open(fetch_diff_file, "w", encoding="utf-8") as handle:
        json.dump(diff_payload, handle, indent=2)


def fetch_analysis(
    analysis_root: Path,
    github_client: github_api.GitHubAPI | None = None,
    gitlab_client: gitlab_api.GitLabAPI | None = None,
) -> None:
    """Fetch status from previously created issues for an existing analysis snapshot."""
    run_report_file = analysis_root / constants.FILENAME_RUN_REPORT
    run_report = load_report(run_report_file)

    run_metadata = (
        run_report.run_metadata if isinstance(run_report.run_metadata, dict) else {}
    )
    analysis_summary_value = run_metadata.get("analysis_summary_file")
    previous_report_value = run_metadata.get("previous_report_source")
    input_config_value = run_metadata.get("input_config_file")

    analysis_summary_file = (
        Path(analysis_summary_value)
        if isinstance(analysis_summary_value, str)
        else None
    )
    previous_report = (
        Path(previous_report_value) if isinstance(previous_report_value, str) else None
    )
    input_config_file = _resolve_input_config_path(input_config_value, analysis_root)

    github_client_instance = github_client
    gitlab_client_instance = gitlab_client

    def issue_client_for_platform(platform: str):
        """get appropriate API"""
        nonlocal github_client_instance, gitlab_client_instance
        if platform == "github":
            if github_client_instance is None:
                github_client_instance = github_api.GitHubAPI(dry_run=False)
            return github_client_instance

        if platform in {"gitlab", "gitlab.com"}:
            if gitlab_client_instance is None:
                gitlab_client_instance = gitlab_api.GitLabAPI(dry_run=False)
            return gitlab_client_instance

        return None

    updated_records: list[dict[str, object]] = []
    fetch_diff_records: list[dict[str, object]] = []

    for record_info in run_report.records:
        record = (
            record_info.to_dict()
            if hasattr(record_info, "to_dict")
            else dict(record_info)
        )
        repo_url = record.get("repo_url")
        issue_url = _issue_url_for_fetch(record)

        if not isinstance(repo_url, str) or not repo_url or not issue_url:
            updated_records.append(record)
            _write_per_repo_report(
                analysis_root,
                record,
                analysis_summary_file,
                previous_report,
            )
            continue

        platform = _detect_platform_for_fetch(repo_url, record)
        if platform is None:
            updated_records.append(record)
            _write_per_repo_report(
                analysis_root,
                record,
                analysis_summary_file,
                previous_report,
            )
            continue

        issue_client = issue_client_for_platform(platform)
        if issue_client is None:
            updated_records.append(record)
            _write_per_repo_report(
                analysis_root,
                record,
                analysis_summary_file,
                previous_report,
            )
            continue

        try:
            comments = issue_client.get_issue_comments(issue_url)
            unsubscribe_detected = any(
                _is_unsubscribe_comment(comment) for comment in comments
            )
            issue_data = issue_client.get_issue(issue_url)
            issue_closed = _issue_is_closed(issue_data)

            if unsubscribe_detected:
                record["unsubscribe_detected"] = True
                record["reason_code"] = constants.REASON_CODE_UNSUBSCRIBE
                config_file = analysis_root / constants.FILENAME_CONFIG_SNAPSHOT
                if config_file.exists():
                    append_opt_out_to_config(config_file, repo_url, explicit=False)
                if input_config_file is not None and input_config_file.exists():
                    append_opt_out_to_config(
                        input_config_file, repo_url, explicit=False
                    )

            if issue_closed:
                record["previous_issue_state"] = "closed"

            if unsubscribe_detected or issue_closed:
                fetch_diff_records.append(record)

        except Exception as exc:
            record["error"] = str(exc)
            record["fetch_error"] = True
            fetch_diff_records.append(record)

        updated_records.append(record)
        _write_per_repo_report(
            analysis_root,
            record,
            analysis_summary_file,
            previous_report,
        )

    _save_fetch_diff(analysis_root, fetch_diff_records)
    run_report_payload = write_report_file(
        report_file=run_report_file,
        records=updated_records,
        dry_run=False,
        run_root=analysis_root.parent,
        analysis_summary_file=analysis_summary_file,
        previous_report=previous_report,
        input_config_file=input_config_file,
    )

    run_metadata_candidate = run_report_payload.get("run_metadata")
    if isinstance(run_metadata_candidate, dict):
        run_metadata_written = cast(dict[str, object], run_metadata_candidate)
    else:
        run_metadata_written = {}
        run_report_payload["run_metadata"] = run_metadata_written

    run_metadata_written["fetched_at"] = _now_utc_iso()
    run_metadata_written["fetch_diff_count"] = len(fetch_diff_records)

    with open(run_report_file, "w", encoding="utf-8") as handle:
        json.dump(run_report_payload, handle, indent=2)


@click.command()
@click.option(
    "--analysis-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Existing analysis snapshot folder containing run_report.json.",
)
def fetch_command(analysis_root: Path) -> None:
    """Retrieve status from previously created issues by a previous analysis."""
    fetch_analysis(analysis_root)
