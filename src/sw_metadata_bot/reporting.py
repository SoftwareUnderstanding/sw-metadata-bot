"""Shared report serialization helpers for all workflow stages."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import constants


@dataclass(frozen=True)
class RecordAnalysis:
    """Core analysis fields persisted for each repository record."""

    analysis_date: str
    bot_version: str
    rsmetacheck_version: str
    pitfalls_count: int | None
    warnings_count: int | None
    pitfalls_ids: list[str] | None = None
    warnings_ids: list[str] | None = None


@dataclass(frozen=True)
class RecordLifecycle:
    """Optional lifecycle and enrichment fields for repository records."""

    issue_url: str | None = None
    action: str | None = None
    reason_code: str | None = None
    previous_issue_url: str | None = None
    previous_issue_state: str | None = None
    findings_signature: str | None = None
    current_commit_id: str | None = None
    previous_commit_id: str | None = None
    unsubscribe_detected: bool | None = None
    dry_run: bool | None = None
    issue_persistence: str | None = None
    simulated_issue_url: str | None = None
    codemeta_generated: bool | None = None
    codemeta_status: str | None = None
    file_path: Path | None = None
    error: str | None = None


def relative_to_run_root(path: Path | None, run_root: Path) -> str | None:
    """Return a run-root-relative path string.

    Accepts both absolute and already-relative input paths. Absolute paths must
    be inside run_root; otherwise Path.relative_to raises ValueError.
    """
    if path is None:
        return None
    if path.is_absolute():
        return str(path.relative_to(run_root))
    return str(path)


def build_counters(records: list[dict[str, object]]) -> dict[str, int]:
    """Build unified counters from report records."""
    return {
        "total": len(records),
        "created": sum(
            1 for r in records if r.get("action") == constants.ACTION_CREATED
        ),
        "simulated": sum(
            1 for r in records if r.get("action") == constants.ACTION_SIMULATED_CREATED
        ),
        "updated_by_comment": sum(
            1 for r in records if r.get("action") == constants.ACTION_UPDATED_BY_COMMENT
        ),
        "closed": sum(1 for r in records if r.get("action") == constants.ACTION_CLOSED),
        "skipped": sum(1 for r in records if r.get("action") == "skipped"),
        "failed": sum(1 for r in records if r.get("action") == "failed"),
    }


def build_run_metadata(
    *,
    dry_run: bool,
    run_root: Path,
    analysis_summary_file: Path | None,
    previous_report: Path | None,
) -> dict[str, object]:
    """Build run metadata with normalized relative paths."""
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": dry_run,
        "analysis_summary_file": relative_to_run_root(analysis_summary_file, run_root),
        "previous_report_source": relative_to_run_root(previous_report, run_root),
    }


def build_record_entry(
    *,
    run_root: Path,
    repo_url: str | None,
    platform: str | None,
    analysis: RecordAnalysis,
    lifecycle: RecordLifecycle | None = None,
) -> dict[str, object]:
    """Build a report record with optional shared fields."""
    lifecycle_data = lifecycle if lifecycle is not None else RecordLifecycle()

    entry: dict[str, object] = {
        "repo_url": repo_url,
        "platform": platform,
        "pitfalls_count": analysis.pitfalls_count,
        "warnings_count": analysis.warnings_count,
        "issue_url": lifecycle_data.issue_url,
        "analysis_date": analysis.analysis_date,
        "sw_metadata_bot_version": analysis.bot_version,
        "rsmetacheck_version": analysis.rsmetacheck_version,
        "pitfalls_ids": analysis.pitfalls_ids or [],
        "warnings_ids": analysis.warnings_ids or [],
    }

    if lifecycle_data.action is not None:
        entry["action"] = lifecycle_data.action
    if lifecycle_data.reason_code is not None:
        entry["reason_code"] = lifecycle_data.reason_code
    if lifecycle_data.previous_issue_url is not None:
        entry["previous_issue_url"] = lifecycle_data.previous_issue_url
    if lifecycle_data.previous_issue_state is not None:
        entry["previous_issue_state"] = lifecycle_data.previous_issue_state
    if lifecycle_data.findings_signature is not None:
        entry["findings_signature"] = lifecycle_data.findings_signature
    if lifecycle_data.current_commit_id is not None:
        entry["current_commit_id"] = lifecycle_data.current_commit_id
    if lifecycle_data.previous_commit_id is not None:
        entry["previous_commit_id"] = lifecycle_data.previous_commit_id
    if lifecycle_data.unsubscribe_detected is not None:
        entry["unsubscribe_detected"] = lifecycle_data.unsubscribe_detected
    if lifecycle_data.dry_run is not None:
        entry["dry_run"] = lifecycle_data.dry_run
    if lifecycle_data.issue_persistence is not None:
        entry["issue_persistence"] = lifecycle_data.issue_persistence
    if lifecycle_data.simulated_issue_url is not None:
        entry["simulated_issue_url"] = lifecycle_data.simulated_issue_url
    if lifecycle_data.codemeta_generated is not None:
        entry["codemeta_generated"] = lifecycle_data.codemeta_generated
    if lifecycle_data.codemeta_status is not None:
        entry["codemeta_status"] = lifecycle_data.codemeta_status
    if lifecycle_data.file_path is not None:
        entry["file"] = relative_to_run_root(lifecycle_data.file_path, run_root)
    if lifecycle_data.error is not None:
        entry["error"] = lifecycle_data.error

    return entry


def write_report_file(
    *,
    report_file: Path,
    records: list[dict[str, object]],
    dry_run: bool,
    run_root: Path,
    analysis_summary_file: Path | None,
    previous_report: Path | None,
) -> dict[str, object]:
    """Write a report payload to disk and return the payload."""
    payload = {
        "run_metadata": build_run_metadata(
            dry_run=dry_run,
            run_root=run_root,
            analysis_summary_file=analysis_summary_file,
            previous_report=previous_report,
        ),
        "counters": build_counters(records),
        "records": records,
    }
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload
