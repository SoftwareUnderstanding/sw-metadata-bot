"""Tests for create_issues command module."""

import json

import click
from click.testing import CliRunner

from sw_metadata_bot import create_issues


def test_detect_platform_variants():
    """Detect supported platforms from repository URLs."""
    assert create_issues.detect_platform("https://github.com/org/repo") == "github"
    assert (
        create_issues.detect_platform("https://gitlab.com/group/repo") == "gitlab.com"
    )
    assert (
        create_issues.detect_platform("https://gitlab.example.org/group/repo")
        == "gitlab"
    )


def test_detect_platform_unsupported():
    """Raise for unsupported platforms."""
    try:
        create_issues.detect_platform("https://example.org/org/repo")
    except ValueError as exc:
        assert "Unsupported repository platform" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported platform")


def test_load_repository_list_normalizes_and_filters(tmp_path):
    """Normalize URLs and ignore non-string entries."""
    file_path = tmp_path / "opt-outs.json"
    file_path.write_text(
        json.dumps(
            {
                "repositories": [
                    "https://github.com/a/b/",
                    "https://gitlab.com/x/y",
                    123,
                    None,
                ]
            }
        )
    )

    result = create_issues._load_repository_list(file_path)

    assert result == {"https://github.com/a/b", "https://gitlab.com/x/y"}


def test_load_repository_list_invalid_format_raises(tmp_path):
    """Reject invalid repositories format."""
    file_path = tmp_path / "opt-outs.json"
    file_path.write_text(json.dumps({"repositories": "not-a-list"}))

    try:
        create_issues._load_repository_list(file_path)
    except click.ClickException as exc:
        assert "repositories' must be a list" in str(exc)
    else:
        raise AssertionError("Expected ClickException for invalid repositories format")


def test_create_issues_cli_failed_report_contains_analysis_fields(tmp_path):
    """Failed report contains analysis details when issue creation fails."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    pitfalls_payload = {
        "assessedSoftware": {"url": "https://gitlab.example.org/example/repo"},
        "checks": [
            {
                "checkId": "hash1",
                "pitfall": "https://w3id.org/rsmetacheck/catalog/#P001",
                "evidence": "P001 detected: missing metadata",
            },
            {
                "checkId": "hash2",
                "pitfall": "https://w3id.org/rsmetacheck/catalog/#W002",
                "evidence": "W002 detected: missing version pin",
            },
        ],
    }
    (pitfalls_dir / "sample.jsonld").write_text(json.dumps(pitfalls_payload))

    runner = CliRunner()
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Summary: Created 0 | Skipped 0 | Failed 1" in result.output

    failed_report_path = issues_dir / "failed_issues_report.json"
    assert failed_report_path.exists()

    failed = json.loads(failed_report_path.read_text())
    assert len(failed) == 1
    assert failed[0]["repo_url"] == "https://gitlab.example.org/example/repo"
    assert failed[0]["pitfalls_count"] == 1
    assert failed[0]["warnings_count"] == 1
    assert failed[0]["platform"] == "gitlab"
    assert "Unsupported platform" in failed[0]["error"]


def test_create_issues_cli_empty_dir(tmp_path):
    """Handle empty pitfalls directory gracefully."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    runner = CliRunner()
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "No pitfalls files found" in result.output
