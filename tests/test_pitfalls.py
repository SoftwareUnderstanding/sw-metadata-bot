"""Tests for pitfalls module."""

import json
import tempfile
from pathlib import Path

import pytest

from sw_metadata_bot.pitfalls import (
    create_issue_body,
    format_report,
    get_pitfalls_list,
    get_repository_url,
    get_rsmetacheck_version,
    get_warnings_list,
    load_pitfalls,
)


@pytest.fixture
def sample_data():
    """Provide sample pitfalls data for testing."""
    return {
        "assessedSoftware": {"url": "https://github.com/example/repo"},
        "checks": [
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#P001",
                "process": "Pitfall process description",
                "evidence": "Evidence of pitfall",
                "suggestion": "How to fix this",
                "output": "true",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#P002",
                "process": "Another pitfall",
                "evidence": "More evidence",
                "output": "true",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#W001",
                "evidence": "Warning evidence",
                "suggestion": "Warning suggestion",
                "output": "true",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#W002",
                "evidence": "Another warning",
                "output": "true",
            },
        ],
    }


@pytest.fixture
def temp_jsonld_file(sample_data):
    """Create a temporary JSON-LD file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonld", delete=False) as f:
        json.dump(sample_data, f)
        temp_path = Path(f.name)
    yield temp_path
    temp_path.unlink()


def test_get_repository_url(sample_data):
    """Test extracting repository URL from data."""
    url = get_repository_url(sample_data)
    assert url == "https://github.com/example/repo"


def test_get_repository_url_empty():
    """Test extracting URL from empty data."""
    url = get_repository_url({})
    assert url == ""


def test_get_pitfalls_list(sample_data):
    """Test filtering pitfalls from checks."""
    pitfalls = get_pitfalls_list(sample_data)
    assert len(pitfalls) == 2
    assert pitfalls[0]["pitfall"].endswith("#P001")
    assert pitfalls[1]["pitfall"].endswith("#P002")


def test_get_warnings_list(sample_data):
    """Test filtering warnings from checks."""
    warnings = get_warnings_list(sample_data)
    assert len(warnings) == 2
    assert warnings[0]["pitfall"].endswith("#W001")
    assert warnings[1]["pitfall"].endswith("#W002")


def test_get_lists_from_hashed_check_ids():
    """Test filtering when checkId is hashed but pitfall URLs are present."""
    data = {
        "checks": [
            {
                "checkId": "694a7a7c5a16db39412fac70b6d27fbadc7222b1d8ae57ff061cc6c87e6d8edc",
                "pitfall": "https://w3id.org/metacheck/catalog/#P001",
                "evidence": "P001 detected: codemeta.json version 'unknown' does not match release version '2.2.0'",
                "output": "true",
            },
            {
                "checkId": "95e131ef79871959cfd0f1ae06dd502d6c160851b0cd5b40844818858c0b22c4",
                "pitfall": "https://w3id.org/metacheck/catalog/#W001",
                "evidence": "W001 detected: pyproject.toml contains software requirements without versions.",
                "output": "true",
            },
            {
                "checkId": "7c48a13e4d4ef33a608362bd2142616ca01aa2b528b457e51016034a151d058e",
                "pitfall": "https://w3id.org/metacheck/catalog/#W004",
                "evidence": "W004 detected: codemeta.json Programming languages without versions: Python",
                "output": "true",
            },
        ]
    }

    pitfalls = get_pitfalls_list(data)
    warnings = get_warnings_list(data)

    assert len(pitfalls) == 1
    assert len(warnings) == 2


def test_get_pitfalls_list_empty():
    """Test pitfalls extraction from empty data."""
    pitfalls = get_pitfalls_list({})
    assert pitfalls == []


@pytest.mark.parametrize(
    ("filename", "expected_pitfalls", "expected_warnings"),
    [
        ("example_pitfall_1.jsonld", {"P001", "P002", "P009"}, {"W001", "W003"}),
        ("example_pitfall_2.jsonld", {"P002", "P014"}, {"W003", "W004"}),
        ("example_pitfall_3.jsonld", {"P001"}, {"W001", "W002", "W004"}),
        ("example_pitfall_4.jsonld", {"P001", "P006"}, set()),
        ("example_pitfall_5.jsonld", set(), {"W002", "W004"}),
    ],
)
def test_existing_metacheck_analysis_jsonld_files(
    filename, expected_pitfalls, expected_warnings
):
    """Test parsing of existing metacheck analysis JSON-LD files."""
    base_path = Path(__file__).resolve().parents[1]
    data = load_pitfalls(
        base_path / "assets" / "existing_metacheck_analysis" / filename
    )

    pitfalls = get_pitfalls_list(data)
    warnings = get_warnings_list(data)

    pitfall_codes = {item["pitfall"].split("#")[-1] for item in pitfalls}
    warning_codes = {item["pitfall"].split("#")[-1] for item in warnings}

    assert pitfall_codes == expected_pitfalls
    assert warning_codes == expected_warnings


def test_format_report(sample_data):
    """Test report formatting."""
    report = format_report("https://github.com/example/repo", sample_data)

    assert "# Metadata Quality Report" in report
    assert "https://github.com/example/repo" in report
    assert "Pitfalls" in report
    assert "Warnings" in report
    assert "P001" in report
    assert "P002" in report
    assert "W001" in report
    assert "W002" in report


def test_format_report_with_suggestions(sample_data):
    """Test that suggestions are included in report."""
    report = format_report("https://github.com/example/repo", sample_data)

    assert "How to fix this" in report
    assert "Warning suggestion" in report


def test_format_report_no_pitfalls():
    """Test report with no pitfalls."""
    data = {
        "assessedSoftware": {"url": "https://github.com/test/repo"},
        "checks": [
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#W001",
                "evidence": "A warning",
                "output": "true",
            }
        ],
    }
    report = format_report("https://github.com/test/repo", data)

    assert "🔴 Pitfalls (0)" not in report
    assert "⚠️ Warnings (1)" in report


def test_create_issue_body(sample_data):
    """Test issue body creation."""
    report = format_report("https://github.com/example/repo", sample_data)
    issue_body = create_issue_body(report)

    assert "CodeMetaSoft" in issue_body
    assert "sw-metadata-bot" in issue_body
    assert report in issue_body
    assert "unsubscribe" in issue_body


def test_get_pitfalls_list_verbose_mode_filters_by_output():
    """Only output true checks are treated as pitfalls."""
    data = {
        "checks": [
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#P001",
                "output": "true",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#P002",
                "output": "false",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#W001",
                "output": "true",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#P003",
            },
        ]
    }

    pitfalls = get_pitfalls_list(data)

    assert len(pitfalls) == 1
    assert pitfalls[0]["pitfall"].endswith("#P001")


def test_get_warnings_list_verbose_mode_filters_by_output():
    """Only output true checks are treated as warnings."""
    data = {
        "checks": [
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#W001",
                "output": "true",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#W002",
                "output": "false",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#P001",
                "output": "true",
            },
            {
                "pitfall": "https://w3id.org/metacheck/catalog/#W003",
            },
        ]
    }

    warnings = get_warnings_list(data)

    assert len(warnings) == 1
    assert warnings[0]["pitfall"].endswith("#W001")


def test_get_lists_missing_output_are_excluded_in_strict_mode():
    """Checks without output key are excluded in strict mode."""
    data = {
        "checks": [
            {"pitfall": "https://w3id.org/metacheck/catalog/#P001"},
            {"pitfall": "https://w3id.org/metacheck/catalog/#W001"},
        ]
    }

    pitfalls = get_pitfalls_list(data)
    warnings = get_warnings_list(data)

    assert pitfalls == []
    assert warnings == []


def test_get_rsmetacheck_version_reads_checking_software_dict():
    """Read version from checkingSoftware dictionary in newer schemas."""
    data = {
        "checkingSoftware": {
            "name": "RSMetacheck",
            "softwareVersion": "0.3.0",
        }
    }

    assert get_rsmetacheck_version(data) == "0.3.0"
