"""Tests for history helper module."""

import json

from sw_metadata_bot import history


def test_load_previous_created_report_indexes_by_repo(tmp_path):
    """Index previous report entries by normalized repository URL."""
    report_path = tmp_path / "created_issues_report.json"
    report_path.write_text(
        json.dumps(
            [
                {"repo_url": "https://github.com/org/repo/", "issue_url": "x"},
                {"repo_url": "https://gitlab.com/group/proj", "issue_url": "y"},
            ]
        )
    )

    result = history.load_previous_created_report(report_path)

    assert set(result.keys()) == {
        "https://github.com/org/repo",
        "https://gitlab.com/group/proj",
    }


def test_load_previous_created_report_handles_missing_file(tmp_path):
    """Return empty mapping when previous report file is absent."""
    missing = tmp_path / "missing.json"
    assert history.load_previous_created_report(missing) == {}


def test_findings_signature_is_deterministic_and_unique():
    """Use sorted unique IDs when creating signatures."""
    first = history.findings_signature(["P002", "P001"], ["W004", "W004"])
    second = history.findings_signature(["P001"], ["W004", "P002"])

    assert first == "P001|P002|W004"
    assert first == second


def test_findings_signature_different():
    """Different sets of IDs should yield different signatures."""
    sig1 = history.findings_signature(["P001"], ["W001"])
    sig2 = history.findings_signature(["P002"], ["W001"])
    sig3 = history.findings_signature(["P001"], ["W002"])

    assert sig1 != sig2
    assert sig1 != sig3
    assert sig2 != sig3
