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
    get_warnings_list,
)


@pytest.fixture
def sample_data():
    """Provide sample pitfalls data for testing."""
    return {
        "assessedSoftware": {"url": "https://github.com/example/repo"},
        "checks": [
            {
                "checkId": "P001",
                "process": "Pitfall process description",
                "evidence": "Evidence of pitfall",
                "suggestion": "How to fix this",
            },
            {
                "checkId": "P002",
                "process": "Another pitfall",
                "evidence": "More evidence",
            },
            {
                "checkId": "W001",
                "evidence": "Warning evidence",
                "suggestion": "Warning suggestion",
            },
            {
                "checkId": "W002",
                "evidence": "Another warning",
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
    assert pitfalls[0]["checkId"] == "P001"
    assert pitfalls[1]["checkId"] == "P002"


def test_get_warnings_list(sample_data):
    """Test filtering warnings from checks."""
    warnings = get_warnings_list(sample_data)
    assert len(warnings) == 2
    assert warnings[0]["checkId"] == "W001"
    assert warnings[1]["checkId"] == "W002"


def test_get_pitfalls_list_empty():
    """Test pitfalls extraction from empty data."""
    pitfalls = get_pitfalls_list({})
    assert pitfalls == []


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
        "checks": [{"checkId": "W001", "evidence": "A warning"}],
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
