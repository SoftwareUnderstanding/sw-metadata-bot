"""Low-level analysis workflow helpers for pipeline orchestration."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from . import __version__, constants, history, incremental, pitfalls, utils
from .check_parsing import extract_check_ids
from .codemeta_runtime import evaluate_and_persist_codemeta_status, load_codemeta_status
from .config_utils import detect_platform, normalize_repo_url, sanitize_repo_name
from .reporting import (
    RecordAnalysis,
    RecordLifecycle,
    build_counters,
    build_run_metadata,
    write_report_file,
)
from .reporting import build_record_entry as build_shared_record_entry
from .rsmetacheck_wrapper import run_rsmetacheck


@dataclass(frozen=True)
class CurrentAnalysisContext:
    """Parsed current-analysis state needed to build a decision record."""

    repo_url: str
    pitfall_file: Path
    data: dict[str, Any]
    pitfalls_count: int
    warnings_count: int
    pitfalls_ids: list[str]
    warnings_ids: list[str]
    analysis_date: str
    rsmetacheck_version: str
    findings_signature: str
    has_findings: bool
    codemeta_status: str
    codemeta_missing: bool
    codemeta_generated: bool
    generated_codemeta: dict[str, Any] | None


@dataclass(frozen=True)
class PreviousAnalysisContext:
    """Previous-analysis state needed for incremental decision making."""

    previous_exists: bool
    previous_issue_url: str | None
    previous_issue_state: str | None
    previous_commit_id: str | None
    previous_signature: str
    previous_issue_open: bool
    previous_codemeta_missing: bool
    repo_updated: bool


def _load_generated_codemeta(repo_folder: Path) -> dict[str, Any] | None:
    """Load generated codemeta payload when rsmetacheck created one."""
    generated_codemeta_file = repo_folder / constants.FILENAME_CODEMETA_GENERATED
    if not generated_codemeta_file.exists():
        return None

    with open(generated_codemeta_file, encoding="utf-8") as f:
        loaded_generated = json.load(f)

    return loaded_generated if isinstance(loaded_generated, dict) else None


def _load_current_analysis_context(
    repo_url: str,
    repo_folder: Path,
) -> CurrentAnalysisContext:
    """Load the current repository analysis outputs into a typed context."""
    pitfall_file = repo_folder / constants.FILENAME_PITFALL
    data = pitfalls.load_pitfalls(pitfall_file)

    detected_repo_url = pitfalls.get_repository_url(data)
    resolved_repo_url = detected_repo_url if detected_repo_url else repo_url

    pitfalls_list = pitfalls.get_pitfalls_list(data)
    warnings_list = pitfalls.get_warnings_list(data)
    pitfalls_count = len(pitfalls_list)
    warnings_count = len(warnings_list)

    checks = data.get("checks", [])
    pitfalls_ids, warnings_ids = extract_check_ids(
        checks if isinstance(checks, list) else []
    )
    findings_signature = history.findings_signature(pitfalls_ids, warnings_ids)

    codemeta_status_data = load_codemeta_status(repo_folder)
    codemeta_status_raw = codemeta_status_data.get("status")
    codemeta_status = (
        codemeta_status_raw if isinstance(codemeta_status_raw, str) else "unknown"
    )

    return CurrentAnalysisContext(
        repo_url=resolved_repo_url,
        pitfall_file=pitfall_file,
        data=data,
        pitfalls_count=pitfalls_count,
        warnings_count=warnings_count,
        pitfalls_ids=pitfalls_ids,
        warnings_ids=warnings_ids,
        analysis_date=str(data.get("dateCreated", "unknown")),
        rsmetacheck_version=pitfalls.get_rsmetacheck_version(data),
        findings_signature=findings_signature,
        has_findings=(pitfalls_count + warnings_count) > 0,
        codemeta_status=codemeta_status,
        codemeta_missing=codemeta_status == "missing",
        codemeta_generated=bool(codemeta_status_data.get("generated", False)),
        generated_codemeta=_load_generated_codemeta(repo_folder),
    )


def _load_previous_analysis_context(
    previous_record: dict[str, object] | None,
    current_commit_id: str | None,
) -> PreviousAnalysisContext:
    """Load previous-analysis state used by the incremental decision tree."""
    if previous_record is None:
        return PreviousAnalysisContext(
            previous_exists=False,
            previous_issue_url=None,
            previous_issue_state=None,
            previous_commit_id=None,
            previous_signature="",
            previous_issue_open=False,
            previous_codemeta_missing=False,
            repo_updated=True,
        )

    issue_url_value = previous_record.get("issue_url")
    if not isinstance(issue_url_value, str) or not issue_url_value:
        issue_url_value = previous_record.get("previous_issue_url")
    previous_issue_url = (
        str(issue_url_value) if isinstance(issue_url_value, str) else None
    )

    previous_state_value = previous_record.get("previous_issue_state")
    previous_issue_state = (
        previous_state_value
        if isinstance(previous_state_value, str) and previous_state_value
        else None
    )

    previous_commit_id = extract_previous_commit(previous_record)
    previous_pitfalls_ids = previous_record.get("pitfalls_ids")
    previous_warnings_ids = previous_record.get("warnings_ids")
    previous_signature = history.findings_signature(
        (
            [value for value in previous_pitfalls_ids if isinstance(value, str)]
            if isinstance(previous_pitfalls_ids, list)
            else None
        ),
        (
            [value for value in previous_warnings_ids if isinstance(value, str)]
            if isinstance(previous_warnings_ids, list)
            else None
        ),
    )

    previous_codemeta_status_raw = previous_record.get("codemeta_status")
    previous_codemeta_missing = (
        isinstance(previous_codemeta_status_raw, str)
        and previous_codemeta_status_raw == "missing"
    )

    repo_updated = True
    if (
        previous_commit_id
        and current_commit_id
        and previous_commit_id != "Unknown"
        and current_commit_id != "Unknown"
    ):
        repo_updated = previous_commit_id != current_commit_id

    return PreviousAnalysisContext(
        previous_exists=True,
        previous_issue_url=previous_issue_url,
        previous_issue_state=previous_issue_state,
        previous_commit_id=previous_commit_id,
        previous_signature=previous_signature,
        previous_issue_open=is_previous_issue_open(previous_record),
        previous_codemeta_missing=previous_codemeta_missing,
        repo_updated=repo_updated,
    )


def _build_decision_record(
    *,
    run_root: Path,
    repo_url: str,
    platform: str | None,
    current_analysis: CurrentAnalysisContext,
    previous_analysis: PreviousAnalysisContext,
    current_commit_id: str | None,
    dry_run: bool,
    action: str,
    reason_code: str,
) -> dict[str, object]:
    """Build the persisted analysis record for a resolved incremental action."""
    issue_url = None
    issue_persistence = "none"

    if action == "simulated_created":
        issue_persistence = "simulated"
    elif action in {"updated_by_comment", "closed"}:
        issue_persistence = "simulated"
        issue_url = previous_analysis.previous_issue_url

    return build_shared_record_entry(
        run_root=run_root,
        repo_url=repo_url,
        platform=platform,
        analysis=RecordAnalysis(
            analysis_date=current_analysis.analysis_date,
            bot_version=__version__,
            rsmetacheck_version=current_analysis.rsmetacheck_version,
            pitfalls_count=current_analysis.pitfalls_count,
            warnings_count=current_analysis.warnings_count,
            pitfalls_ids=current_analysis.pitfalls_ids,
            warnings_ids=current_analysis.warnings_ids,
        ),
        lifecycle=RecordLifecycle(
            issue_url=issue_url,
            action=action,
            reason_code=reason_code,
            previous_issue_url=previous_analysis.previous_issue_url,
            previous_issue_state=previous_analysis.previous_issue_state,
            findings_signature=current_analysis.findings_signature,
            current_commit_id=current_commit_id,
            previous_commit_id=previous_analysis.previous_commit_id,
            dry_run=dry_run,
            issue_persistence=issue_persistence,
            codemeta_generated=current_analysis.codemeta_generated,
            codemeta_status=current_analysis.codemeta_status,
            file_path=current_analysis.pitfall_file,
        ),
    )


def extract_previous_commit(record: dict) -> str | None:
    """Return previous commit id from report records with compatibility fallback."""
    current_commit = record.get("current_commit_id")
    if isinstance(current_commit, str) and current_commit:
        return current_commit

    legacy_commit = record.get("commit_id")
    if isinstance(legacy_commit, str) and legacy_commit:
        return legacy_commit

    return None


def resolve_per_repo_paths(analysis_root: Path, repo_url: str) -> dict[str, Path]:
    """Compute per-repository output paths within the analysis root."""
    sanitized_name = sanitize_repo_name(repo_url)
    repo_folder = analysis_root / sanitized_name

    return {
        "repo_folder": repo_folder,
        "somef_output": repo_folder / constants.FILENAME_SOMEF_OUTPUT,
        "pitfall_output": repo_folder / constants.FILENAME_PITFALL,
        "issue_report": repo_folder / constants.FILENAME_ISSUE_REPORT,
        "codemeta_status": repo_folder / constants.FILENAME_CODEMETA_STATUS,
        "codemeta_generated": repo_folder / constants.FILENAME_CODEMETA_GENERATED,
        "report": repo_folder / constants.FILENAME_REPORT,
    }


def copy_previous_repo_artifacts(
    previous_repo_folder: Path, current_repo_folder: Path
) -> None:
    """Copy previous snapshot repository artifacts into current snapshot folder."""
    current_repo_folder.mkdir(parents=True, exist_ok=True)
    for name in (
        constants.FILENAME_SOMEF_OUTPUT,
        constants.FILENAME_PITFALL,
        constants.FILENAME_ISSUE_REPORT,
        constants.FILENAME_CODEMETA_STATUS,
        constants.FILENAME_CODEMETA_GENERATED,
        constants.FILENAME_REPORT,
    ):
        src = previous_repo_folder / name
        if src.exists():
            shutil.copy2(src, current_repo_folder / name)


def load_previous_repo_record(
    previous_snapshot_root: Path | None, repo_url: str
) -> dict | None:
    """Load previous per-repo record from previous snapshot if available."""
    if previous_snapshot_root is None:
        return None

    repo_folder = previous_snapshot_root / sanitize_repo_name(repo_url)
    report_path = repo_folder / constants.FILENAME_REPORT
    try:
        data = utils.load_json_file(
            report_path, required=False, description="previous report"
        )
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, list) and records:
            record = records[0]
            if isinstance(record, dict):
                return record
    except (ValueError, json.JSONDecodeError):
        pass

    run_report = previous_snapshot_root / constants.FILENAME_RUN_REPORT
    try:
        data = utils.load_json_file(
            run_report, required=False, description="previous run report"
        )
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, list):
            normalized = normalize_repo_url(repo_url)
            for record in records:
                if not isinstance(record, dict):
                    continue
                value = record.get("repo_url")
                if isinstance(value, str) and normalize_repo_url(value) == normalized:
                    return record
    except (ValueError, json.JSONDecodeError):
        pass

    return None


def standardize_metacheck_outputs(repo_folder: Path) -> None:
    """Normalize metacheck output names to stable per-repo filenames.

    RSMetacheck outputs multiple artifacts with varying names depending on tool
    version and configuration. This function consolidates them into a standard
    naming scheme for consistent downstream processing.

        Normalization Strategy (for research software clarity):

        - Pitfalls (JSON-LD): Often named with repository name or timestamp.
            Standardized to ``pitfall.jsonld``.
        - SOMEF output: Can be nested in subdirectories or root.
            Standardized to ``somef_output.json``.
        - Generated codemeta: Created by rsmetacheck if metadata is missing.
            Standardized to ``codemeta_generated.json``.

    File Discovery Uses Fallback Strategy:
    1. Try explicit subdirectory (metacheck's preferred location)
    2. Fall back to glob patterns if subdirectory empty
    3. Apply heuristics (payload inspection) to disambiguate similar files

    This defensive approach handles different metacheck versions gracefully
    without failing when directory structure differs from expectations.
    """

    def _load_json_object(path: Path) -> dict[str, Any] | None:
        """Load a JSON file and return a dict payload when possible."""
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
        except Exception:
            return None
        return loaded if isinstance(loaded, dict) else None

    def _looks_like_somef_payload(path: Path) -> bool:
        """Identify SOMEF extraction payloads by their provenance key."""
        payload = _load_json_object(path)
        return isinstance(payload, dict) and "somef_provenance" in payload

    def _looks_like_codemeta_payload(path: Path) -> bool:
        """Identify codemeta-like payloads by context/type keys."""
        payload = _load_json_object(path)
        if not isinstance(payload, dict):
            return False
        if "@context" not in payload or "@type" not in payload:
            return False
        context_value = payload.get("@context")
        if isinstance(context_value, str):
            return "codemeta" in context_value.lower()
        if isinstance(context_value, list):
            return any(
                isinstance(item, str) and "codemeta" in item.lower()
                for item in context_value
            )
        return False

    repo_folder.mkdir(parents=True, exist_ok=True)

    # PITFALLS: JSON-LD format from rsmetacheck. Try subdirectory first, then root.
    pitfall_target = repo_folder / "pitfall.jsonld"
    if not pitfall_target.exists():
        pitfall_candidates = list((repo_folder / "pitfalls_outputs").glob("*.jsonld"))
        if not pitfall_candidates:
            # Fallback: search root for legacy naming patterns
            pitfall_candidates = list(repo_folder.glob("*_pitfalls.jsonld"))
        if pitfall_candidates:
            shutil.move(str(pitfall_candidates[0]), str(pitfall_target))

    # CODEMETA GENERATED: If rsmetacheck generated metadata (flag enabled)
    codemeta_generated_target = repo_folder / "codemeta_generated.json"
    if not codemeta_generated_target.exists():
        # First, look for explicitly-named generated codemeta by SOMEF
        codemeta_named_candidates = list(
            repo_folder.glob("*somef_generated_codemeta*.json")
        )
        if codemeta_named_candidates:
            shutil.move(
                str(codemeta_named_candidates[0]), str(codemeta_generated_target)
            )

    somef_target = repo_folder / "somef_output.json"
    # Defensive: If somef_output.json exists but looks like codemeta (swapped),
    # move it to the codemeta target location
    if somef_target.exists() and _looks_like_codemeta_payload(somef_target):
        if not codemeta_generated_target.exists():
            shutil.move(str(somef_target), str(codemeta_generated_target))

    # SOMEF OUTPUT: SOMEF metadata extraction results. Try subdirectory first.
    if not somef_target.exists():
        # Try subdirectory (metacheck's preferred location)
        somef_candidates = [
            path
            for path in (repo_folder / "somef_outputs").glob("*.json")
            if _looks_like_somef_payload(path)
        ]
        if not somef_candidates:
            # Fallback: search root for JSON files that look like SOMEF output.
            # Exclude report files and files starting with "metacheck_" to avoid
            # false positives (they're not SOMEF outputs).
            somef_candidates = [
                path
                for path in repo_folder.glob("*.json")
                if path.name
                not in {
                    constants.FILENAME_REPORT,
                    constants.FILENAME_ANALYSIS_RESULTS,
                    constants.FILENAME_CONFIG_SNAPSHOT,
                    constants.FILENAME_RUN_REPORT,
                    constants.FILENAME_CODEMETA_STATUS,
                    constants.FILENAME_CODEMETA_GENERATED,
                }
                and not path.name.startswith("metacheck_")
                and _looks_like_somef_payload(path)
            ]
        if somef_candidates:
            shutil.move(str(somef_candidates[0]), str(somef_target))

    # CLEANUP: Remove legacy subdirectories that were used as intermediate locations
    for legacy_dir in (repo_folder / "somef_outputs", repo_folder / "pitfalls_outputs"):
        if legacy_dir.exists() and legacy_dir.is_dir():
            shutil.rmtree(legacy_dir)

    # FALLBACK CODEMETA: If still no codemeta_generated, search for codemeta files
    # in root that weren't already matched (e.g., uploaded by user or legacy runs)
    if not codemeta_generated_target.exists():
        codemeta_candidates = [
            path
            for path in repo_folder.glob("*.json")
            if path.name
            not in {
                constants.FILENAME_SOMEF_OUTPUT,
                constants.FILENAME_CODEMETA_STATUS,
                constants.FILENAME_REPORT,
                constants.FILENAME_ANALYSIS_RESULTS,
                constants.FILENAME_CONFIG_SNAPSHOT,
                constants.FILENAME_RUN_REPORT,
            }
            and _looks_like_codemeta_payload(path)
        ]
        if codemeta_candidates:
            shutil.move(str(codemeta_candidates[0]), str(codemeta_generated_target))


def run_metacheck_for_repo(
    repo_url: str,
    repo_folder: Path,
    *,
    generate_codemeta_if_missing: bool,
) -> None:
    """Run metacheck for a single repository URL into its own folder."""
    repo_folder.mkdir(parents=True, exist_ok=True)
    temp_analysis_file: Path | None = None
    with NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="metacheck_repo_",
        delete=False,
        encoding="utf-8",
    ) as temp_file:
        temp_analysis_file = Path(temp_file.name)

    run_rsmetacheck(
        input_source=repo_url,
        somef_output=str(repo_folder),
        pitfalls_output=str(repo_folder),
        analysis_output=str(temp_analysis_file),
        generate_codemeta=generate_codemeta_if_missing,
    )

    if temp_analysis_file is not None and temp_analysis_file.exists():
        temp_analysis_file.unlink()

    standardize_metacheck_outputs(repo_folder)
    evaluate_and_persist_codemeta_status(
        repo_url=repo_url,
        repo_folder=repo_folder,
        generate_if_missing=generate_codemeta_if_missing,
    )


def build_analysis_counters(records: list[dict[str, object]]) -> dict[str, int]:
    """Build analysis counters using the unified report schema."""
    return build_counters(records)


def build_analysis_run_report(
    records: list[dict[str, object]],
    *,
    dry_run: bool,
    run_root: Path,
    analysis_summary_file: Path,
    previous_report: Path | None,
) -> dict[str, object]:
    """Build run-level report payload from analysis decision records."""
    return {
        "run_metadata": build_run_metadata(
            dry_run=dry_run,
            run_root=run_root,
            analysis_summary_file=analysis_summary_file,
            previous_report=previous_report,
        ),
        "counters": build_analysis_counters(records),
        "records": records,
    }


def detect_repo_platform(repo_url: str) -> str | None:
    """Detect publish platform from a repository URL."""
    return detect_platform(repo_url)


def is_previous_issue_open(previous_record: dict[str, object]) -> bool:
    """Infer whether previous issue was open from stored metadata only."""
    state_value = previous_record.get("previous_issue_state")
    state = str(state_value).lower() if isinstance(state_value, str) else ""
    if state in {"open", "opened"}:
        return True
    if state in {"closed", "close"}:
        return False

    # If the previous analysis already closed the issue, treat it as closed
    # regardless of whether previous_issue_state was persisted.
    if previous_record.get("action") == "closed":
        return False

    issue_url = previous_record.get("issue_url") or previous_record.get(
        "previous_issue_url"
    )
    if not isinstance(issue_url, str) or not issue_url:
        return False

    issue_persistence = previous_record.get("issue_persistence")
    if issue_persistence == "simulated":
        return False

    return True


def build_record_entry(
    *,
    run_root: Path,
    repo_url: str,
    platform: str | None,
    pitfalls_count: int,
    warnings_count: int,
    analysis_date: str,
    rsmetacheck_version: str,
    pitfalls_ids: list[str],
    warnings_ids: list[str],
    action: str,
    reason_code: str,
    findings_signature: str,
    current_commit_id: str | None,
    previous_commit_id: str | None,
    previous_issue_url: str | None,
    previous_issue_state: str | None,
    dry_run: bool,
    issue_persistence: str,
    issue_url: str | None,
    file_path: Path,
    codemeta_generated: bool | None = None,
    codemeta_status: str | None = None,
    error: str | None = None,
) -> dict[str, object]:
    """Build a per-repository analysis record payload."""
    return build_shared_record_entry(
        run_root=run_root,
        repo_url=repo_url,
        platform=platform,
        analysis=RecordAnalysis(
            analysis_date=analysis_date,
            bot_version=__version__,
            rsmetacheck_version=rsmetacheck_version,
            pitfalls_count=pitfalls_count,
            warnings_count=warnings_count,
            pitfalls_ids=pitfalls_ids,
            warnings_ids=warnings_ids,
        ),
        lifecycle=RecordLifecycle(
            issue_url=issue_url,
            action=action,
            reason_code=reason_code,
            previous_issue_url=previous_issue_url,
            previous_issue_state=previous_issue_state,
            findings_signature=findings_signature,
            current_commit_id=current_commit_id,
            previous_commit_id=previous_commit_id,
            dry_run=dry_run,
            issue_persistence=issue_persistence,
            codemeta_generated=codemeta_generated,
            codemeta_status=codemeta_status,
            file_path=file_path,
            error=error,
        ),
    )


def write_analysis_repo_report(
    repo_folder: Path,
    record: dict[str, object],
    *,
    dry_run: bool,
    run_root: Path,
    analysis_summary_file: Path,
    previous_report: Path | None,
) -> None:
    """Write per-repository analysis report using analysis-stage counters."""
    write_report_file(
        report_file=repo_folder / constants.FILENAME_REPORT,
        records=[record],
        dry_run=dry_run,
        run_root=run_root,
        analysis_summary_file=analysis_summary_file,
        previous_report=previous_report,
    )


def create_analysis_record(
    *,
    run_root: Path,
    repo_url: str,
    repo_folder: Path,
    previous_record: dict[str, object] | None,
    current_commit_id: str | None,
    dry_run: bool,
    custom_message: str | None,
) -> dict[str, object]:
    """Create a decision record for a repository without platform API calls."""
    pitfall_file = repo_folder / constants.FILENAME_PITFALL
    if not pitfall_file.exists():
        return build_record_entry(
            run_root=run_root,
            repo_url=repo_url,
            platform=detect_repo_platform(repo_url),
            pitfalls_count=0,
            warnings_count=0,
            analysis_date="unknown",
            rsmetacheck_version="unknown",
            pitfalls_ids=[],
            warnings_ids=[],
            action="failed",
            reason_code="missing_pitfall_file",
            findings_signature="",
            current_commit_id=current_commit_id,
            previous_commit_id=None,
            previous_issue_url=None,
            previous_issue_state=None,
            dry_run=dry_run,
            issue_persistence="none",
            issue_url=None,
            file_path=pitfall_file,
            error=f"Missing pitfall file: {pitfall_file}",
        )

    try:
        current_analysis = _load_current_analysis_context(repo_url, repo_folder)
        repo_url = current_analysis.repo_url

        if current_analysis.has_findings or current_analysis.codemeta_missing:
            formatted = pitfalls.format_report(
                repo_url,
                current_analysis.data,
                codemeta_missing=current_analysis.codemeta_missing,
                generated_codemeta=current_analysis.generated_codemeta,
            )
            issue_body = pitfalls.create_issue_body(formatted, custom_message)
            (repo_folder / constants.FILENAME_ISSUE_REPORT).write_text(
                issue_body, encoding="utf-8"
            )

        platform = detect_repo_platform(repo_url)
        previous_analysis = _load_previous_analysis_context(
            previous_record, current_commit_id
        )

        decision = incremental.evaluate(
            previous_exists=previous_analysis.previous_exists,
            unsubscribed=False,
            repo_updated=previous_analysis.repo_updated,
            has_findings=current_analysis.has_findings,
            identical_findings=(
                current_analysis.findings_signature
                == previous_analysis.previous_signature
            ),
            previous_issue_open=previous_analysis.previous_issue_open,
            codemeta_missing=current_analysis.codemeta_missing,
            previous_codemeta_missing=previous_analysis.previous_codemeta_missing,
        )

        if decision.action == "create":
            return _build_decision_record(
                run_root=run_root,
                repo_url=repo_url,
                platform=platform,
                current_analysis=current_analysis,
                previous_analysis=previous_analysis,
                current_commit_id=current_commit_id,
                dry_run=dry_run,
                action="simulated_created",
                reason_code=decision.reason,
            )

        if decision.action == "comment":
            return _build_decision_record(
                run_root=run_root,
                repo_url=repo_url,
                platform=platform,
                current_analysis=current_analysis,
                previous_analysis=previous_analysis,
                current_commit_id=current_commit_id,
                dry_run=dry_run,
                action="updated_by_comment",
                reason_code=decision.reason,
            )

        if decision.action == "close":
            return _build_decision_record(
                run_root=run_root,
                repo_url=repo_url,
                platform=platform,
                current_analysis=current_analysis,
                previous_analysis=previous_analysis,
                current_commit_id=current_commit_id,
                dry_run=dry_run,
                action="closed",
                reason_code=decision.reason,
            )

        return _build_decision_record(
            run_root=run_root,
            repo_url=repo_url,
            platform=platform,
            current_analysis=current_analysis,
            previous_analysis=previous_analysis,
            current_commit_id=current_commit_id,
            dry_run=dry_run,
            action="skipped",
            reason_code=decision.reason,
        )
    except Exception as exc:
        return build_record_entry(
            run_root=run_root,
            repo_url=repo_url,
            platform=detect_repo_platform(repo_url),
            pitfalls_count=0,
            warnings_count=0,
            analysis_date="unknown",
            rsmetacheck_version="unknown",
            pitfalls_ids=[],
            warnings_ids=[],
            action="failed",
            reason_code="exception",
            findings_signature="",
            current_commit_id=current_commit_id,
            previous_commit_id=(
                extract_previous_commit(previous_record)
                if previous_record is not None
                else None
            ),
            previous_issue_url=None,
            previous_issue_state=None,
            dry_run=dry_run,
            issue_persistence="none",
            issue_url=None,
            file_path=pitfall_file,
            error=str(exc),
        )
