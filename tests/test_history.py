"""Tests for history helper module."""

import json

from sw_metadata_bot import history


def test_load_previous_report_indexes_only_posted_by_repo(tmp_path):
    """Index only posted records by normalized repository URL."""
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/org/repo/",
                        "issue_url": "x",
                        "issue_persistence": "posted",
                    },
                    {
                        "repo_url": "https://gitlab.com/group/proj",
                        "issue_url": "y",
                        "issue_persistence": "simulated",
                    },
                ]
            }
        )
    )

    result = history.load_previous_report(report_path)

    assert set(result.keys()) == {"https://github.com/org/repo"}


def test_load_previous_report_handles_missing_file(tmp_path):
    """Return empty mapping when previous report file is absent."""
    missing = tmp_path / "missing.json"
    assert history.load_previous_report(missing) == {}


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
