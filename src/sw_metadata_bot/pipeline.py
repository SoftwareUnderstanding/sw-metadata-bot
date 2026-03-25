"""Pipeline command to run analysis workflows."""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import click

from . import history, incremental, pitfalls
from .check_parsing import extract_check_ids
from .commit_lookup import (
    get_generic_git_head_commit,
    get_github_head_commit,
    get_gitlab_head_commit,
    is_commit_hash,
    parse_github_repo,
    resolve_gitlab_project_path,
)
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


def _parse_github_repo(repo_url: str) -> tuple[str, str] | None:
    """Parse owner/repo from a GitHub repository URL."""
    return parse_github_repo(repo_url)


def _resolve_gitlab_project_path(repo_url: str) -> tuple[str, str] | None:
    """Parse host and project path for GitLab repositories."""
    return resolve_gitlab_project_path(repo_url)


def _is_commit_hash(value: str) -> bool:
    """Return True if value looks like a commit hash."""
    return is_commit_hash(value)


def _get_github_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit from GitHub API."""
    return get_github_head_commit(repo_url)


def _get_gitlab_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit from GitLab API for gitlab* hosts."""
    return get_gitlab_head_commit(repo_url)


def _get_generic_git_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit via git ls-remote as generic fallback."""
    return get_generic_git_head_commit(repo_url)


def _get_repo_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit using API-first and git fallback strategies."""
    resolvers = (
        _get_github_head_commit,
        _get_gitlab_head_commit,
        _get_generic_git_head_commit,
    )
    for resolver in resolvers:
        try:
            commit_id = resolver(repo_url)
        except Exception:
            commit_id = None
        if isinstance(commit_id, str) and commit_id:
            return commit_id
    return None


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


def _resolve_per_repo_paths(analysis_root: Path, repo_url: str) -> dict[str, Path]:
    """Compute per-repository output paths within the analysis root."""
    sanitized_name = sanitize_repo_name(repo_url)
    repo_folder = analysis_root / sanitized_name

    return {
        "repo_folder": repo_folder,
        "somef_output": repo_folder / "somef_output.json",
        "pitfall_output": repo_folder / "pitfall.jsonld",
        "issue_report": repo_folder / "issue_report.md",
        "report": repo_folder / "report.json",
    }


def _copy_previous_repo_artifacts(
    previous_repo_folder: Path, current_repo_folder: Path
) -> None:
    """Copy previous snapshot repository artifacts into current snapshot folder."""
    current_repo_folder.mkdir(parents=True, exist_ok=True)
    for name in (
        "somef_output.json",
        "pitfall.jsonld",
        "issue_report.md",
        "report.json",
    ):
        src = previous_repo_folder / name
        if src.exists():
            shutil.copy2(src, current_repo_folder / name)


def _load_previous_repo_record(
    previous_snapshot_root: Path | None, repo_url: str
) -> dict | None:
    """Load previous per-repo record from previous snapshot if available."""
    if previous_snapshot_root is None:
        return None

    repo_folder = previous_snapshot_root / sanitize_repo_name(repo_url)
    report_path = repo_folder / "report.json"
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, list) and records:
            record = records[0]
            if isinstance(record, dict):
                return record

    run_report = previous_snapshot_root / "run_report.json"
    if run_report.exists():
        with open(run_report, encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, list):
            normalized = _normalize_repo_url(repo_url)
            for record in records:
                if not isinstance(record, dict):
                    continue
                value = record.get("repo_url")
                if isinstance(value, str) and _normalize_repo_url(value) == normalized:
                    return record

    return None


def _standardize_metacheck_outputs(repo_folder: Path) -> None:
    """Normalize metacheck output names to stable per-repo filenames."""
    repo_folder.mkdir(parents=True, exist_ok=True)

    pitfall_target = repo_folder / "pitfall.jsonld"
    if not pitfall_target.exists():
        pitfall_candidates = list((repo_folder / "pitfalls_outputs").glob("*.jsonld"))
        if not pitfall_candidates:
            pitfall_candidates = list(repo_folder.glob("*_pitfalls.jsonld"))
        if pitfall_candidates:
            shutil.move(str(pitfall_candidates[0]), str(pitfall_target))

    somef_target = repo_folder / "somef_output.json"
    if not somef_target.exists():
        somef_candidates = list((repo_folder / "somef_outputs").glob("*.json"))
        if not somef_candidates:
            somef_candidates = [
                path
                for path in repo_folder.glob("*.json")
                if path.name
                not in {
                    "report.json",
                    "analysis_results.json",
                    "config.json",
                    "run_report.json",
                }
                and not path.name.startswith("metacheck_")
            ]
        if somef_candidates:
            shutil.move(str(somef_candidates[0]), str(somef_target))

    for legacy_dir in (repo_folder / "somef_outputs", repo_folder / "pitfalls_outputs"):
        if legacy_dir.exists() and legacy_dir.is_dir():
            shutil.rmtree(legacy_dir)


def _run_metacheck_for_repo(repo_url: str, repo_folder: Path) -> None:
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

    metacheck_command.main(
        args=[
            "--input",
            repo_url,
            "--somef-output",
            str(repo_folder),
            "--pitfalls-output",
            str(repo_folder),
            "--analysis-output",
            str(temp_analysis_file),
        ],
        standalone_mode=False,
    )

    if temp_analysis_file is not None and temp_analysis_file.exists():
        temp_analysis_file.unlink()

    _standardize_metacheck_outputs(repo_folder)


def _build_analysis_counters(records: list[dict[str, object]]) -> dict[str, int]:
    """Build analysis-stage decision counters from report records."""
    return {
        "total": len(records),
        "decision_create": sum(
            1 for r in records if r.get("action") == "simulated_created"
        ),
        "decision_comment": sum(
            1 for r in records if r.get("action") == "updated_by_comment"
        ),
        "decision_close": sum(1 for r in records if r.get("action") == "closed"),
        "decision_skip": sum(1 for r in records if r.get("action") == "skipped"),
        "failed_analysis": sum(1 for r in records if r.get("action") == "failed"),
    }


def _build_analysis_run_report(
    records: list[dict[str, object]],
    *,
    dry_run: bool,
    analysis_summary_file: Path,
    previous_report: Path | None,
) -> dict[str, object]:
    """Build run-level report payload from analysis decision records."""
    return {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": dry_run,
            "analysis_summary_file": str(analysis_summary_file),
            "previous_report_source": (
                str(previous_report) if previous_report is not None else None
            ),
        },
        "counters": _build_analysis_counters(records),
        "records": records,
    }


def _detect_platform_from_repo_url(repo_url: str) -> str | None:
    """Detect publish platform from repository URL."""
    lowered = repo_url.lower()
    if "github.com" in lowered:
        return "github"
    if "gitlab" in lowered:
        return "gitlab"
    return None


def _is_previous_issue_open(previous_record: dict[str, object]) -> bool:
    """Infer whether previous issue was open from stored metadata only."""
    state_value = previous_record.get("previous_issue_state")
    state = str(state_value).lower() if isinstance(state_value, str) else ""
    if state in {"open", "opened"}:
        return True
    if state in {"closed", "close"}:
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


def _build_record_entry(
    *,
    repo_url: str,
    platform: str | None,
    pitfalls_count: int,
    warnings_count: int,
    analysis_date: str,
    metacheck_version: str,
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
    error: str | None = None,
) -> dict[str, object]:
    """Build a per-repository analysis record payload."""
    entry: dict[str, object] = {
        "repo_url": repo_url,
        "platform": platform,
        "pitfalls_count": pitfalls_count,
        "warnings_count": warnings_count,
        "issue_url": issue_url,
        "analysis_date": analysis_date,
        "sw_metadata_bot_version": pitfalls.__version__,
        "rsmetacheck_version": metacheck_version,
        "pitfalls_ids": pitfalls_ids,
        "warnings_ids": warnings_ids,
        "action": action,
        "reason_code": reason_code,
        "findings_signature": findings_signature,
        "dry_run": dry_run,
        "issue_persistence": issue_persistence,
        "file": str(file_path),
    }
    if current_commit_id is not None:
        entry["current_commit_id"] = current_commit_id
    if previous_commit_id is not None:
        entry["previous_commit_id"] = previous_commit_id
    if previous_issue_url is not None:
        entry["previous_issue_url"] = previous_issue_url
    if previous_issue_state is not None:
        entry["previous_issue_state"] = previous_issue_state
    if error is not None:
        entry["error"] = error
    return entry


def _write_analysis_repo_report(
    repo_folder: Path,
    record: dict[str, object],
    *,
    dry_run: bool,
    analysis_summary_file: Path,
    previous_report: Path | None,
) -> None:
    """Write per-repository analysis report using analysis-stage counters."""
    report = {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": dry_run,
            "analysis_summary_file": str(analysis_summary_file),
            "previous_report_source": (
                str(previous_report) if previous_report is not None else None
            ),
        },
        "counters": _build_analysis_counters([record]),
        "records": [record],
    }
    report_file = repo_folder / "report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def _create_analysis_record(
    *,
    repo_url: str,
    repo_folder: Path,
    previous_record: dict[str, object] | None,
    current_commit_id: str | None,
    dry_run: bool,
    custom_message: str | None,
) -> dict[str, object]:
    """Create a decision record for a repository without platform API calls."""
    pitfall_file = repo_folder / "pitfall.jsonld"
    if not pitfall_file.exists():
        return _build_record_entry(
            repo_url=repo_url,
            platform=_detect_platform_from_repo_url(repo_url),
            pitfalls_count=0,
            warnings_count=0,
            analysis_date="unknown",
            metacheck_version="unknown",
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
        data = pitfalls.load_pitfalls(pitfall_file)
        detected_repo_url = pitfalls.get_repository_url(data)
        if detected_repo_url:
            repo_url = detected_repo_url
        pitfalls_list = pitfalls.get_pitfalls_list(data)
        warnings_list = pitfalls.get_warnings_list(data)
        pitfalls_count = len(pitfalls_list)
        warnings_count = len(warnings_list)
        checks = data.get("checks", [])
        check_ids = extract_check_ids(checks if isinstance(checks, list) else [])
        pitfalls_ids, warnings_ids = check_ids
        analysis_date = str(data.get("dateCreated", "unknown"))
        metacheck_version = str(data.get("schemaVersion", "unknown"))
        current_signature = history.findings_signature(pitfalls_ids, warnings_ids)
        has_findings = (pitfalls_count + warnings_count) > 0

        if has_findings:
            formatted = pitfalls.format_report(repo_url, data)
            issue_body = pitfalls.create_issue_body(formatted, custom_message)
            (repo_folder / "issue_report.md").write_text(issue_body, encoding="utf-8")

        platform = _detect_platform_from_repo_url(repo_url)
        previous_issue_url: str | None = None
        previous_issue_state: str | None = None
        previous_commit_id: str | None = None
        previous_signature = ""
        previous_exists = previous_record is not None
        previous_issue_open = False
        repo_updated = True

        if previous_record is not None:
            issue_url_value = previous_record.get("issue_url")
            if not isinstance(issue_url_value, str) or not issue_url_value:
                issue_url_value = previous_record.get("previous_issue_url")
            previous_issue_url = (
                str(issue_url_value) if isinstance(issue_url_value, str) else None
            )

            previous_state_value = previous_record.get("previous_issue_state")
            if isinstance(previous_state_value, str) and previous_state_value:
                previous_issue_state = previous_state_value

            previous_commit_id = _extract_previous_commit(previous_record)
            previous_signature = history.findings_signature(
                previous_record.get("pitfalls_ids"),
                previous_record.get("warnings_ids"),
            )
            previous_issue_open = _is_previous_issue_open(previous_record)

            if (
                previous_commit_id
                and current_commit_id
                and previous_commit_id != "Unknown"
                and current_commit_id != "Unknown"
            ):
                repo_updated = previous_commit_id != current_commit_id

        decision = incremental.evaluate(
            previous_exists=previous_exists,
            unsubscribed=False,
            repo_updated=repo_updated,
            has_findings=has_findings,
            identical_findings=current_signature == previous_signature,
            previous_issue_open=previous_issue_open,
        )

        if decision.action == "create":
            return _build_record_entry(
                repo_url=repo_url,
                platform=platform,
                pitfalls_count=pitfalls_count,
                warnings_count=warnings_count,
                analysis_date=analysis_date,
                metacheck_version=metacheck_version,
                pitfalls_ids=pitfalls_ids,
                warnings_ids=warnings_ids,
                action="simulated_created",
                reason_code=decision.reason,
                findings_signature=current_signature,
                current_commit_id=current_commit_id,
                previous_commit_id=previous_commit_id,
                previous_issue_url=previous_issue_url,
                previous_issue_state=previous_issue_state,
                dry_run=dry_run,
                issue_persistence="simulated",
                issue_url=None,
                file_path=pitfall_file,
            )

        if decision.action == "comment":
            return _build_record_entry(
                repo_url=repo_url,
                platform=platform,
                pitfalls_count=pitfalls_count,
                warnings_count=warnings_count,
                analysis_date=analysis_date,
                metacheck_version=metacheck_version,
                pitfalls_ids=pitfalls_ids,
                warnings_ids=warnings_ids,
                action="updated_by_comment",
                reason_code=decision.reason,
                findings_signature=current_signature,
                current_commit_id=current_commit_id,
                previous_commit_id=previous_commit_id,
                previous_issue_url=previous_issue_url,
                previous_issue_state=previous_issue_state,
                dry_run=dry_run,
                issue_persistence="simulated",
                issue_url=previous_issue_url,
                file_path=pitfall_file,
            )

        if decision.action == "close":
            return _build_record_entry(
                repo_url=repo_url,
                platform=platform,
                pitfalls_count=pitfalls_count,
                warnings_count=warnings_count,
                analysis_date=analysis_date,
                metacheck_version=metacheck_version,
                pitfalls_ids=pitfalls_ids,
                warnings_ids=warnings_ids,
                action="closed",
                reason_code=decision.reason,
                findings_signature=current_signature,
                current_commit_id=current_commit_id,
                previous_commit_id=previous_commit_id,
                previous_issue_url=previous_issue_url,
                previous_issue_state=previous_issue_state,
                dry_run=dry_run,
                issue_persistence="simulated",
                issue_url=previous_issue_url,
                file_path=pitfall_file,
            )

        return _build_record_entry(
            repo_url=repo_url,
            platform=platform,
            pitfalls_count=pitfalls_count,
            warnings_count=warnings_count,
            analysis_date=analysis_date,
            metacheck_version=metacheck_version,
            pitfalls_ids=pitfalls_ids,
            warnings_ids=warnings_ids,
            action="skipped",
            reason_code=decision.reason,
            findings_signature=current_signature,
            current_commit_id=current_commit_id,
            previous_commit_id=previous_commit_id,
            previous_issue_url=previous_issue_url,
            previous_issue_state=previous_issue_state,
            dry_run=dry_run,
            issue_persistence="none",
            issue_url=None,
            file_path=pitfall_file,
        )
    except Exception as exc:
        return _build_record_entry(
            repo_url=repo_url,
            platform=_detect_platform_from_repo_url(repo_url),
            pitfalls_count=0,
            warnings_count=0,
            analysis_date="unknown",
            metacheck_version="unknown",
            pitfalls_ids=[],
            warnings_ids=[],
            action="failed",
            reason_code="exception",
            findings_signature="",
            current_commit_id=current_commit_id,
            previous_commit_id=(
                _extract_previous_commit(previous_record)
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
        per_repo = _resolve_per_repo_paths(analysis_root, repo_url)
        repo_folder = per_repo["repo_folder"]
        repo_folder.mkdir(parents=True, exist_ok=True)

        previous_record = _load_previous_repo_record(previous_snapshot_root, repo_url)
        previous_commit_id = (
            _extract_previous_commit(previous_record) if previous_record else None
        )

        try:
            current_commit_id = _get_repo_head_commit(repo_url)
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
                _copy_previous_repo_artifacts(previous_repo_folder, repo_folder)
                reused_previous = True

        if not reused_previous:
            _run_metacheck_for_repo(repo_url, repo_folder)

        normalized_repo = _normalize_repo_url(repo_url)
        if normalized_repo in opt_out_repos:
            record = {
                "repo_url": repo_url,
                "platform": _detect_platform_from_repo_url(repo_url),
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
            record = _create_analysis_record(
                repo_url=repo_url,
                repo_folder=repo_folder,
                previous_record=previous_record,
                current_commit_id=current_commit_id,
                dry_run=dry_run,
                custom_message=custom_message,
            )

        _write_analysis_repo_report(
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

    run_report = _build_analysis_run_report(
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
