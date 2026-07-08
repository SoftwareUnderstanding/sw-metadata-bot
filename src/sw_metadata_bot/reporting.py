"""Shared report serialization helpers for all workflow stages."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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


@dataclass(frozen=True)
class ReportRecord:
    """Normalized representation of a single repository report record."""

    repo_url: str | None = None
    platform: str | None = None
    pitfalls_count: int | None = None
    warnings_count: int | None = None
    issue_url: str | None = None
    analysis_date: str | None = None
    sw_metadata_bot_version: str | None = None
    rsmetacheck_version: str | None = None
    pitfalls_ids: tuple[str, ...] = ()
    warnings_ids: tuple[str, ...] = ()
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
    file_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the record to the JSON payload shape used by report files."""
        return {
            "repo_url": self.repo_url,
            "platform": self.platform,
            "pitfalls_count": self.pitfalls_count,
            "warnings_count": self.warnings_count,
            "issue_url": self.issue_url,
            "analysis_date": self.analysis_date,
            "sw_metadata_bot_version": self.sw_metadata_bot_version,
            "rsmetacheck_version": self.rsmetacheck_version,
            "pitfalls_ids": list(self.pitfalls_ids),
            "warnings_ids": list(self.warnings_ids),
            "action": self.action,
            "reason_code": self.reason_code,
            "previous_issue_url": self.previous_issue_url,
            "previous_issue_state": self.previous_issue_state,
            "findings_signature": self.findings_signature,
            "current_commit_id": self.current_commit_id,
            "previous_commit_id": self.previous_commit_id,
            "unsubscribe_detected": self.unsubscribe_detected,
            "dry_run": self.dry_run,
            "issue_persistence": self.issue_persistence,
            "simulated_issue_url": self.simulated_issue_url,
            "codemeta_generated": self.codemeta_generated,
            "codemeta_status": self.codemeta_status,
            "file": self.file_path,
            "error": self.error,
        }

    def get_tool_metadata(self) -> "ToolMetadata":
        """Retrieve tool versions information"""
        sw_metadata_bot_version = (
            self.sw_metadata_bot_version if not None else "unknown"
        )
        rsmetacheck_version = self.rsmetacheck_version if not None else "unknown"
        return ToolMetadata(sw_metadata_bot_version, rsmetacheck_version)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReportRecord":
        """Create a report record from a dictionary payload."""
        return cls(
            repo_url=data.get("repo_url"),
            platform=data.get("platform"),
            pitfalls_count=data.get("pitfalls_count"),
            warnings_count=data.get("warnings_count"),
            issue_url=data.get("issue_url"),
            analysis_date=data.get("analysis_date"),
            sw_metadata_bot_version=data.get("sw_metadata_bot_version"),
            rsmetacheck_version=data.get("rsmetacheck_version"),
            pitfalls_ids=tuple(data.get("pitfalls_ids") or ()),
            warnings_ids=tuple(data.get("warnings_ids") or ()),
            action=data.get("action"),
            reason_code=data.get("reason_code"),
            previous_issue_url=data.get("previous_issue_url"),
            previous_issue_state=data.get("previous_issue_state"),
            findings_signature=data.get("findings_signature"),
            current_commit_id=data.get("current_commit_id"),
            previous_commit_id=data.get("previous_commit_id"),
            unsubscribe_detected=data.get("unsubscribe_detected"),
            dry_run=data.get("dry_run"),
            issue_persistence=data.get("issue_persistence"),
            simulated_issue_url=data.get("simulated_issue_url"),
            codemeta_generated=data.get("codemeta_generated"),
            codemeta_status=data.get("codemeta_status"),
            file_path=data.get("file"),
            error=data.get("error"),
        )


@dataclass(frozen=True)
class ToolMetadata:
    """Intermediate class to represent the sw-metadata-bot metadata"""

    sw_metadata_bot_version: str = "unknown"
    rs_metacheck_version: str = "unknown"

    def to_dict(self):
        """Convert to dict"""
        return {
            "sw_metadata_bot_version": self.sw_metadata_bot_version,
            "rsmetacheck_version": self.rs_metacheck_version,
        }


@dataclass(frozen=True)
class RunReport:
    """Structured representation of a run_report.json payload."""

    run_metadata: dict[str, Any]
    counters: dict[str, int]
    records: tuple[ReportRecord]

    def to_payload(self) -> dict[str, Any]:
        """Serialize the report to the JSON payload shape used on disk."""
        return {
            "run_metadata": self.run_metadata,
            "counters": self.counters,
            "records": [record.to_dict() for record in self.records],
        }

    def get_tool_metadata(self) -> "ToolMetadata":
        """Retrieve metadata from the first ReportRecord.
        Requires record and that the first record to be set correctly.
        """
        if self.records:
            sample_record: ReportRecord = self.records[0]
            return sample_record.get_tool_metadata()
        else:
            return ToolMetadata()


def relative_to_run_root(path: Path | None, run_root: Path) -> str | None:
    """Return a run-root-relative path string.

    Accepts both absolute and relative input paths.
    Relative paths are resolved against the current working directory before
    comparing against run_root.
    """
    if path is None:
        return None

    if not path.is_absolute():
        path = path.resolve()

    try:
        return str(path.relative_to(run_root))
    except ValueError:
        return str(path)


def _normalize_record(record: dict[str, object] | ReportRecord) -> dict[str, object]:
    """Return a JSON-serializable representation of a record."""
    if isinstance(record, ReportRecord):
        return record.to_dict()
    if isinstance(record, dict):
        return dict(record)
    raise TypeError(f"Unsupported report record type: {type(record)!r}")


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
        "skipped": sum(
            1 for r in records if r.get("action") == constants.ACTION_SKIPPED
        ),
        "failed": sum(1 for r in records if r.get("action") == constants.ACTION_FAILED),
    }


def build_run_metadata(
    *,
    dry_run: bool,
    run_root: Path,
    analysis_summary_file: Path | None,
    previous_report: Path | None,
    input_config_file: Path | None = None,
) -> dict[str, object]:
    """Build run metadata with normalized relative paths."""
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": dry_run,
        "analysis_summary_file": relative_to_run_root(analysis_summary_file, run_root),
        "previous_report_source": relative_to_run_root(previous_report, run_root),
        "input_config_file": relative_to_run_root(input_config_file, run_root),
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


def load_report(report_file: Path | str) -> RunReport:
    """Load a run_report.json payload and return a normalized report object."""
    report_path = Path(report_file)
    with open(report_path, encoding="utf-8") as handle:
        payload = json.load(handle)

    records = tuple(
        ReportRecord.from_dict(record) if isinstance(record, dict) else record
        for record in payload.get("records", [])
    )
    return RunReport(
        run_metadata=payload.get("run_metadata", {}),
        counters=payload.get("counters", {}),
        records=records,
    )


def write_report_file(
    *,
    report_file: Path,
    records: list[dict[str, object]],
    dry_run: bool,
    run_root: Path,
    analysis_summary_file: Path | None,
    previous_report: Path | None,
    input_config_file: Path | None = None,
) -> dict[str, object]:
    """Write a report payload to disk and return the payload."""
    normalized_records: list[dict[str, object]] = []
    for record in records:
        normalized_record = _normalize_record(record)
        if isinstance(normalized_record, dict):
            normalized_record.setdefault("unsubscribe_detected", False)
        normalized_records.append(normalized_record)

    payload = {
        "run_metadata": build_run_metadata(
            dry_run=dry_run,
            run_root=run_root,
            analysis_summary_file=analysis_summary_file,
            previous_report=previous_report,
            input_config_file=input_config_file,
        ),
        "counters": build_counters(normalized_records),
        "records": normalized_records,
    }
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload
