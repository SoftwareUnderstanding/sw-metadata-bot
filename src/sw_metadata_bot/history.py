"""Helpers for loading and querying previous issue reports."""

import json
from pathlib import Path


def normalize_repo_url(url: str) -> str:
    """Normalize repository URL for matching across report files."""
    return url.strip().rstrip("/")


def load_previous_report(report_path: Path | None) -> dict[str, dict]:
    """Load unified report.json and index actionable entries by repo URL."""
    if report_path is None or not report_path.exists():
        return {}

    with open(report_path, encoding="utf-8") as f:
        raw = json.load(f)

    records = raw.get("records") if isinstance(raw, dict) else None
    if not isinstance(records, list):
        return {}

    by_repo: dict[str, dict] = {}
    for item in records:
        if not isinstance(item, dict):
            continue

        issue_persistence = item.get("issue_persistence")
        issue_url = item.get("issue_url")
        if (
            issue_persistence != "posted"
            or not isinstance(issue_url, str)
            or not issue_url
        ):
            continue

        repo_url = item.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url.strip():
            continue
        by_repo[normalize_repo_url(repo_url)] = item

    return by_repo


def findings_signature(
    pitfall_ids: list[str] | None, warning_ids: list[str] | None
) -> str:
    """Build a deterministic findings signature from pitfall and warning IDs."""
    values = set(pitfall_ids or []) | set(warning_ids or [])
    return "|".join(sorted(values))
