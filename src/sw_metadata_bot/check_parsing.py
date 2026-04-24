"""Shared parsing helpers for RSMetacheck check identifiers.

RSMetacheck evaluates each repository against a catalog of checks for metadata
quality. Checks are identified by a code: P#### for Pitfalls (high-priority issues
that indicate missing or invalid metadata) or W#### for Warnings (informational
checks or best-practice recommendations). The #### segment is a 3-4 digit code
within each category.

Example check codes:
- P001: Repository lacks codemeta.json file
- W001: Incomplete metadata field descriptions
- P042: Missing license information

See constants.py for related definitions (CHECK_TYPE_*, CHECK_CODE_REGEX_PATTERN).
"""

import re

from . import constants

CHECK_CODE_PATTERN = re.compile(constants.CHECK_CODE_REGEX_PATTERN, re.IGNORECASE)


def get_check_catalog_id(check: dict) -> str:
    """Return full RSMetacheck catalog ID URL for a check when available.

    Preferred source is the new schema key ``assessesIndicator.@id`` when it
    points to the RSMetacheck catalog. For backward compatibility, this falls
    back to the legacy ``pitfall`` key.
    """
    indicator_id = str(check.get("assessesIndicator", {}).get("@id", ""))
    if (
        indicator_id
        and "catalog" in indicator_id
        and CHECK_CODE_PATTERN.search(indicator_id)
    ):
        return indicator_id

    return str(check.get("pitfall", ""))


def get_short_check_code(check: dict) -> str:
    """Return short check code such as P001 or W004."""
    full_id = get_check_catalog_id(check)
    if not full_id:
        return ""

    match = CHECK_CODE_PATTERN.search(full_id)
    if match is None:
        return ""

    return match.group(1).upper()


def is_check_reported(check: dict) -> bool:
    """Return True only when a check is explicitly reported by metacheck.

    Verbose metacheck output marks each evaluated check with an ``output`` key.
    Only values representing true are considered reported findings.
    """
    output = check.get("output")
    return str(output).lower() == "true"


def extract_check_ids(checks: list[dict]) -> tuple[list[str], list[str]]:
    """Extract ordered unique pitfall and warning codes from check entries."""
    pitfall_ids: list[str] = []
    warning_ids: list[str] = []

    for check in checks:
        if not is_check_reported(check):
            continue

        code = get_short_check_code(check)
        if not code:
            continue

        if code.startswith("P") and code not in pitfall_ids:
            pitfall_ids.append(code)
        elif code.startswith("W") and code not in warning_ids:
            warning_ids.append(code)

    return pitfall_ids, warning_ids
