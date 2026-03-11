"""Pitfalls data loading and parsing."""

import json
from datetime import datetime
from pathlib import Path

from . import __version__
from .check_parsing import get_check_catalog_id, get_short_check_code


def load_pitfalls(file_path: Path) -> dict:
    """Load pitfalls from JSON-LD file."""
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


def get_repository_url(data: dict) -> str:
    """Extract repository URL from pitfalls data."""
    return data.get("assessedSoftware", {}).get("url", "")


def _get_check_code(check: dict) -> str:
    """Extract full check catalog ID from a check entry."""
    return get_check_catalog_id(check)


def _get_short_check_code(check_full_id: str) -> str:
    """Extract short check code (e.g. P001/W004) from full check ID."""
    return check_full_id.split("#")[-1]


def get_pitfalls_list(data: dict) -> list[dict]:
    """Get list of pitfall checks from data."""
    return [
        check
        for check in data.get("checks", [])
        if get_short_check_code(check).startswith("P")
    ]


def get_warnings_list(data: dict) -> list[dict]:
    """Get list of warning checks from data."""
    return [
        check
        for check in data.get("checks", [])
        if get_short_check_code(check).startswith("W")
    ]


def get_metacheck_version(data: dict) -> str:
    """Get the version of RSMetacheck used for analysis.

    New schema (0.2.1+): Version is in checkingSoftware.softwareVersion
    Falls back to "unknown" if not found.
    """
    # New schema: checkingSoftware.softwareVersion
    version_from_checking = data.get("checkingSoftware", {}).get("softwareVersion", "")
    if version_from_checking:
        return version_from_checking

    # If not found in schema, return unknown
    return "unknown"


def format_report(repo_url: str, data: dict) -> str:
    """Format pitfalls data into a readable report."""
    pitfalls = get_pitfalls_list(data)
    warnings = get_warnings_list(data)

    report = "# Metadata Quality Report\n\n"
    report += f"**Repository:** {repo_url}\n"
    report += f"**Analysis Date:** {datetime.now().strftime('%Y-%m-%d')}\n"
    report += f"**sw-metadata-bot version:** {__version__}\n"
    report += f"**RSMetacheck version:** {get_metacheck_version(data)}\n\n"

    if pitfalls:
        report += f"## 🔴 Pitfalls ({len(pitfalls)})\n\n"
        for p in pitfalls:
            full_pitfall_id = _get_check_code(p)
            short_code = _get_short_check_code(full_pitfall_id)
            report += f"### [{short_code}]({full_pitfall_id})\n"
            report += f"**Evidence:** {p.get('evidence', 'No details')}\n\n"
            if p.get("suggestion"):
                report += f"**Suggestion:** {p['suggestion']}\n\n"

    if warnings:
        report += f"## ⚠️ Warnings ({len(warnings)})\n\n"
        for w in warnings:
            full_warning_id = _get_check_code(w)
            short_code = _get_short_check_code(full_warning_id)
            report += f"### [{short_code}]({full_warning_id})\n"
            report += f"**Evidence:** {w.get('evidence', 'No details')}\n\n"
            if w.get("suggestion"):
                report += f"**Suggestion:** {w['suggestion']}\n\n"

    return report


DEFAULT_GREETINGS = """\
Hi maintainers,
Your repository is part of our metadata quality improvement initiative. We've automatically analyzed your repository's metadata and discovered some issues that could be fixed.
"""

ISSUE_TEMPLATE = """\
{greetings}

This automated issue includes:
- Detected metadata pitfalls and warnings
- Suggestions for fixing each issue

## Context
This analysis is performed by the [CodeMetaSoft](https://w3id.org/codemetasoft) project to help improve research software quality.

This is a first initiative aimed at identifying and reporting metadata quality issues across research software repositories. 
At this stage, we only provide diagnostics and recommendations. 
In future iterations, we plan to propose automated fixes for the detected issues to further simplify the improvement process and reduce manual effort.

Each pitfall and warning is identified by a unique code (e.g. P001 for pitfalls, W004 for warnings) that corresponds to specific metadata quality issues.
You can find more details about these checks and how to address them in the [RSMetacheck catalog](https://github.com/SoftwareUnderstanding/RSMetacheck/blob/main/catalog.md).


{report}
---

This report was generated automatically by [sw-metadata-bot](https://github.com/SoftwareUnderstanding/sw-metadata-bot).

If you're not interested in participating, please comment "unsubscribe" and we will remove your repository from our list.
"""


def create_issue_body(report: str, custom_message: str | None = None) -> str:
    """Wrap report in issue template using optional custom message or default greetings."""
    if not custom_message:
        custom_message = DEFAULT_GREETINGS

    body = ISSUE_TEMPLATE.format(report=report, greetings=custom_message)

    return body
