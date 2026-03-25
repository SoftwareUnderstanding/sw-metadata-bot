"""Helpers for loading and querying previous issue reports."""

import json
from pathlib import Path


def normalize_repo_url(url: str) -> str:
    """Normalize repository URL for matching across report files."""
    return url.strip().rstrip("/")


def _read_report_records(report_path: Path | None) -> list[dict]:
    """Read records array from unified report.json with graceful fallback."""
    if report_path is None or not report_path.exists():
        return []

    with open(report_path, encoding="utf-8") as f:
        raw = json.load(f)

    records = raw.get("records") if isinstance(raw, dict) else None
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _extract_issue_reference(record: dict) -> str | None:
    """Return a reusable issue URL from current, previous, or simulated issue fields.

    Prioritizes actual posted issues, then falls back to simulated URLs
    so that dry-run records become valid for incremental analysis.
    """
    issue_url = record.get("issue_url")
    if isinstance(issue_url, str) and issue_url:
        issue_persistence = record.get("issue_persistence")
        if issue_persistence == "posted":
            return issue_url

    previous_issue_url = record.get("previous_issue_url")
    if isinstance(previous_issue_url, str) and previous_issue_url:
        return previous_issue_url

    simulated_issue_url = record.get("simulated_issue_url")
    if isinstance(simulated_issue_url, str) and simulated_issue_url:
        return simulated_issue_url

    return None


def load_previous_report(report_path: Path | None) -> dict[str, dict]:
    """Load report.json and index issue-lifecycle entries by repository URL."""
    records = _read_report_records(report_path)

    by_repo: dict[str, dict] = {}
    for item in records:
        issue_reference = _extract_issue_reference(item)
        if issue_reference is None:
            continue

        repo_url = item.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url.strip():
            continue

        normalized_repo = normalize_repo_url(repo_url)
        enriched = dict(item)
        if not isinstance(enriched.get("issue_url"), str) or not enriched.get(
            "issue_url"
        ):
            enriched["issue_url"] = issue_reference
        by_repo[normalized_repo] = enriched

    return by_repo


def load_previous_commit_report(report_path: Path | None) -> dict[str, dict]:
    """Load report.json and index entries by repository for commit-based pre-skip."""
    records = _read_report_records(report_path)

    by_repo: dict[str, dict] = {}
    for item in records:
        repo_url = item.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url.strip():
            continue

        current_commit_id = item.get("current_commit_id")
        legacy_commit_id = item.get("commit_id")
        if not (
            (isinstance(current_commit_id, str) and current_commit_id)
            or (isinstance(legacy_commit_id, str) and legacy_commit_id)
        ):
            continue

        by_repo[normalize_repo_url(repo_url)] = item

    return by_repo


def findings_signature(
    pitfall_ids: list[str] | None, warning_ids: list[str] | None
) -> str:
    """Build a deterministic findings signature from pitfall and warning IDs."""
    values = set(pitfall_ids or []) | set(warning_ids or [])
    return "|".join(sorted(values))
