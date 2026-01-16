"""Pitfalls data loading and parsing."""

import json
from datetime import datetime
from pathlib import Path


def load_pitfalls(file_path: Path) -> dict:
    """Load pitfalls from JSON-LD file."""
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


def get_repository_url(data: dict) -> str:
    """Extract repository URL from pitfalls data."""
    return data.get("assessedSoftware", {}).get("url", "")


def get_pitfalls_list(data: dict) -> list[dict]:
    """Get list of pitfall checks from data."""
    return [
        check
        for check in data.get("checks", [])
        if check.get("checkId", "").startswith("E")
    ]


def get_warnings_list(data: dict) -> list[dict]:
    """Get list of warning checks from data."""
    return [
        check
        for check in data.get("checks", [])
        if check.get("checkId", "").startswith("W")
    ]


def format_report(repo_url: str, data: dict) -> str:
    """Format pitfalls data into a readable report."""
    pitfalls = get_pitfalls_list(data)
    warnings = get_warnings_list(data)

    report = "# Metadata Quality Report\n\n"
    report += f"**Repository:** {repo_url}\n"
    report += f"**Analysis Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"

    if pitfalls:
        report += f"## 🔴 Critical Issues ({len(pitfalls)})\n\n"
        for p in pitfalls:
            report += f"### {p['checkId']}\n"
            report += f"{p.get('evidence', 'No details')}\n\n"
            if p.get("suggestion"):
                report += f"**Suggestion:** {p['suggestion']}\n\n"

    if warnings:
        report += f"## ⚠️ Warnings ({len(warnings)})\n\n"
        for w in warnings:
            report += f"### {w['checkId']}\n"
            report += f"{w.get('evidence', 'No details')}\n\n"
            if w.get("suggestion"):
                report += f"**Suggestion:** {w['suggestion']}\n\n"

    report += "---\n"
    report += "This report was generated automatically by [sw-metadata-bot](https://github.com/codemetasoft/sw-metadata-bot).\n"

    return report


def create_issue_body(report: str) -> str:
    """Wrap report in issue template."""
    body = "👋 Hello! This is an automated metadata quality report.\n\n"
    body += report
    body += "\n\n"
    body += "## How to respond\n\n"
    body += "- **Fix the issues** and close this issue with a comment\n"
    body += "- **Have questions?** Comment below and we'll help\n"
    body += "- **Not interested?** Comment 'unsubscribe' to opt out\n"

    return body
