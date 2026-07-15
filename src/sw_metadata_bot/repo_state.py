"""Repository-state helpers for the new repo-centric output layout."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import constants
from .config.config_utils import sanitize_repo_name


def resolve_repo_state_paths(output_root: Path, repo_url: str) -> dict[str, Path]:
    """Compute the persistent repository state paths for a given repository."""
    repo_folder = output_root / sanitize_repo_name(repo_url)
    return {
        "repo_folder": repo_folder,
        "event_log": repo_folder / constants.FILENAME_EVENT_LOG,
        "current_state": repo_folder / constants.FILENAME_CURRENT_STATE,
        "analyses_folder": repo_folder / constants.DIRNAME_ANALYSES,
        "issues_folder": repo_folder / constants.DIRNAME_ISSUES,
    }


def ensure_repo_state_dirs(paths: dict[str, Path]) -> None:
    """Create the repository state folder and its analysis/issue subfolders."""
    paths["repo_folder"].mkdir(parents=True, exist_ok=True)
    paths["analyses_folder"].mkdir(parents=True, exist_ok=True)
    paths["issues_folder"].mkdir(parents=True, exist_ok=True)


def append_event_log(repo_folder: Path, event: dict[str, Any]) -> None:
    """Append a JSON event to the repository audit log."""
    event_log_path = repo_folder / constants.FILENAME_EVENT_LOG
    event["timestamp"] = event.get(
        "timestamp",
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    event_json = json.dumps(event, sort_keys=True)
    repo_folder.mkdir(parents=True, exist_ok=True)
    with open(event_log_path, "a", encoding="utf-8") as handle:
        handle.write(event_json + "\n")


def write_current_state(repo_folder: Path, state: dict[str, Any]) -> None:
    """Write the latest repository state cache."""
    current_state_path = repo_folder / constants.FILENAME_CURRENT_STATE
    repo_folder.mkdir(parents=True, exist_ok=True)
    with open(current_state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def normalize_issue_id(issue_url: str) -> int | None:
    """Extract an integer issue ID from an issue URL if available."""
    try:
        path = urlparse(issue_url).path.rstrip("/")
        candidate = Path(path).name
        return int(candidate)
    except (ValueError, TypeError):
        return None


def issue_metadata_path(repo_folder: Path, issue_id: int) -> Path:
    """Return the path to a per-issue metadata file."""
    return repo_folder / constants.DIRNAME_ISSUES / f"issue_{issue_id}.json"


def save_issue_metadata(repo_folder: Path, issue_data: dict[str, Any]) -> Path | None:
    """Persist issue lifecycle metadata into the issues directory."""
    issue_url = issue_data.get("url")
    if not isinstance(issue_url, str) or not issue_url:
        return None

    issue_id = normalize_issue_id(issue_url)
    if issue_id is None:
        return None

    issue_path = issue_metadata_path(repo_folder, issue_id)
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(issue_path, "w", encoding="utf-8") as handle:
        json.dump(issue_data, handle, indent=2)
    return issue_path


def build_analysis_archive_path(repo_folder: Path, commit_id: str | None) -> Path:
    """Return a stable analysis archive path for a given commit or timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_commit = commit_id.replace("/", "_") if commit_id else timestamp
    return repo_folder / constants.DIRNAME_ANALYSES / f"{safe_commit}_analysis.json"


def build_analysis_archive_payload(
    repo_folder: Path, record: dict[str, Any]
) -> dict[str, Any]:
    """Build an analysis archive payload from a report record and available artifacts."""
    archive: dict[str, Any] = {
        "schema_version": 1,
        "repo_url": record.get("repo_url"),
        "analysis_date": record.get("analysis_date"),
        "commit_id": record.get("current_commit_id"),
        "action": record.get("action"),
        "reason_code": record.get("reason_code"),
        "issue_url": record.get("issue_url"),
        "issue_persistence": record.get("issue_persistence"),
        "codemeta_status": record.get("codemeta_status"),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    def _load_json(path: Path) -> Any:
        """simple inline json loader"""
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return None

    pitfall_path = repo_folder / constants.FILENAME_PITFALL
    somef_path = repo_folder / constants.FILENAME_SOMEF_OUTPUT
    codemeta_status_path = repo_folder / constants.FILENAME_CODEMETA_STATUS
    issue_report_path = repo_folder / constants.FILENAME_ISSUE_REPORT

    archive["pitfalls"] = _load_json(pitfall_path)
    archive["somef_output"] = _load_json(somef_path)
    archive["codemeta_status"] = _load_json(codemeta_status_path)
    if issue_report_path.exists():
        archive["issue_report"] = issue_report_path.read_text(encoding="utf-8")
    else:
        archive["issue_report"] = None

    return archive


def write_analysis_archive(repo_folder: Path, record: dict[str, Any]) -> Path:
    """Persist a single analysis archive under the analyses directory."""
    archive_path = build_analysis_archive_path(
        repo_folder, record.get("current_commit_id")
    )
    archive_payload = build_analysis_archive_payload(repo_folder, record)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with open(archive_path, "w", encoding="utf-8") as handle:
        json.dump(archive_payload, handle, indent=2)
    return archive_path


def build_analysis_current_state(record: dict[str, Any]) -> dict[str, Any]:
    """Build the current-state payload from a report record."""
    state = {
        "schema_version": 1,
        "repo_url": record.get("repo_url"),
        "analysis_date": record.get("analysis_date"),
        "commit_id": record.get("current_commit_id"),
        "action": record.get("action"),
        "issue_url": record.get("issue_url"),
        "issue_persistence": record.get("issue_persistence"),
        "codemeta_status": record.get("codemeta_status"),
        "analysis_file": record.get("file"),
        "last_updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return state
