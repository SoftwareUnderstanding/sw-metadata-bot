"""Helpers for loading and querying previous issue reports."""

import json
from pathlib import Path


def normalize_repo_url(url: str) -> str:
    """Normalize repository URL for matching across report files."""
    return url.strip().rstrip("/")


def load_previous_created_report(report_path: Path | None) -> dict[str, dict]:
    """Load a created_issues_report-like JSON and index by normalized repo URL."""
    if report_path is None or not report_path.exists():
        return {}

    with open(report_path, encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        return {}

    by_repo: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
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
