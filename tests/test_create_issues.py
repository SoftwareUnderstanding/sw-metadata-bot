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
    """Unified report stores failed action with analysis details."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    pitfalls_payload = {
        "dateCreated": "2026-03-05T15:57:03Z",
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
    assert "Failed 1" in result.output

    report_path = issues_dir / "report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text())
    assert report["counters"]["failed"] == 1
    failed = report["records"][0]
    assert failed["repo_url"] == "https://gitlab.example.org/example/repo"
    assert failed["pitfalls_count"] == 1
    assert failed["warnings_count"] == 1
    assert failed["platform"] == "gitlab"
    assert failed["analysis_date"] == "2026-03-05T15:57:03Z"
    assert failed["sw_metadata_bot_version"]
    assert failed["rsmetacheck_version"]
    assert failed["file"].endswith("sample.jsonld")
    assert failed["pitfalls_ids"] == ["P001"]
    assert failed["warnings_ids"] == ["W002"]
    assert failed["action"] == "failed"
    assert "Unsupported platform" in failed["error"]


def test_create_issues_cli_created_report_contains_analysis_fields(tmp_path):
    """Unified report stores simulated_created records for dry-run creation."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    pitfalls_payload = {
        "dateCreated": "2026-03-05T15:55:22Z",
        "assessedSoftware": {"url": "https://github.com/example/repo"},
        "checks": [
            {
                "checkId": "hash1",
                "pitfall": "https://w3id.org/rsmetacheck/catalog/#P001",
                "evidence": "P001 detected: missing metadata",
                "suggestion": "Provide metadata",
            },
            {
                "checkId": "hash2",
                "pitfall": "https://w3id.org/rsmetacheck/catalog/#W004",
                "evidence": "W004 detected: no language version",
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
    assert "Simulated 1" in result.output

    report_path = issues_dir / "report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text())
    assert report["counters"]["created"] == 0
    assert report["counters"]["simulated"] == 1

    created = report["records"][0]
    assert created["repo_url"] == "https://github.com/example/repo"
    assert created["platform"] == "github"
    assert created["issue_url"] is None
    assert created["simulated_issue_url"] == "https://github.com/example/repo/issues/0"
    assert created["pitfalls_count"] == 1
    assert created["warnings_count"] == 1
    assert created["analysis_date"] == "2026-03-05T15:55:22Z"
    assert created["sw_metadata_bot_version"]
    assert created["rsmetacheck_version"]
    assert created["pitfalls_ids"] == ["P001"]
    assert created["warnings_ids"] == ["W004"]
    assert created["action"] == "simulated_created"
    assert created["issue_persistence"] == "simulated"


def test_create_issues_cli_extracts_ids_from_new_schema(tmp_path):
    """Populate report IDs when checks use assessesIndicator.@id schema."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    pitfalls_payload = {
        "dateCreated": "2026-03-11T13:51:04Z",
        "assessedSoftware": {"url": "https://github.com/example/repo"},
        "checks": [
            {
                "checkId": "hash-w",
                "assessesIndicator": {
                    "@id": "https://w3id.org/rsmetacheck/catalog/#W004"
                },
                "evidence": "W004 detected",
            },
            {
                "checkId": "hash-p",
                "assessesIndicator": {
                    "@id": "https://w3id.org/rsmetacheck/catalog/#P001"
                },
                "evidence": "P001 detected",
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

    report = json.loads((issues_dir / "report.json").read_text())
    record = report["records"][0]
    assert record["pitfalls_ids"] == ["P001"]
    assert record["warnings_ids"] == ["W004"]


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


def test_create_issues_incremental_identical_open_issue_skips(tmp_path):
    """Skip creation when previous findings are identical and previous issue is open."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    pitfalls_payload = {
        "dateCreated": "2026-03-05T15:55:22Z",
        "assessedSoftware": {"url": "https://github.com/example/repo"},
        "checks": [
            {
                "checkId": "hash1",
                "pitfall": "https://w3id.org/rsmetacheck/catalog/#P001",
                "evidence": "P001 detected: missing metadata",
            }
        ],
    }
    (pitfalls_dir / "sample.jsonld").write_text(json.dumps(pitfalls_payload))

    previous_report = tmp_path / "previous_report.json"
    previous_report.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "issue_url": "https://github.com/example/repo/issues/7",
                        "pitfalls_ids": ["P001"],
                        "warnings_ids": [],
                        "issue_persistence": "posted",
                    }
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--previous-report",
            str(previous_report),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Skipped 1" in result.output

    report = json.loads((issues_dir / "report.json").read_text())
    assert report["counters"]["skipped"] == 1
    assert report["records"][0]["repo_url"] == "https://github.com/example/repo"
    assert report["records"][0]["action"] == "skipped"
    assert report["records"][0]["reason_code"] == "identical_and_issue_open"
