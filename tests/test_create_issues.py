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
    assert "Summary: Created 0 | Skipped 0 | Failed 1" in result.output

    failed_report_path = issues_dir / "failed_issues_report.json"
    assert failed_report_path.exists()

    failed = json.loads(failed_report_path.read_text())
    assert len(failed) == 1
    assert failed[0]["repo_url"] == "https://gitlab.example.org/example/repo"
    assert failed[0]["pitfalls_count"] == 1
    assert failed[0]["warnings_count"] == 1
    assert failed[0]["platform"] == "gitlab"
    assert failed[0]["analysis_date"] == "2026-03-05T15:57:03Z"
    assert failed[0]["sw_metadata_bot_version"]
    assert failed[0]["rsmetacheck_version"]
    assert failed[0]["file"].endswith("sample.jsonld")
    assert failed[0]["pitfalls_ids"] == ["P001"]
    assert failed[0]["warnings_ids"] == ["W002"]
    assert "Unsupported platform" in failed[0]["error"]


def test_create_issues_cli_created_report_contains_analysis_fields(tmp_path):
    """Created report contains metadata and pitfall/warning details."""
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
    assert "Summary: Created 1 | Skipped 0 | Failed 0" in result.output

    created_report_path = issues_dir / "created_issues_report.json"
    assert created_report_path.exists()

    created = json.loads(created_report_path.read_text())
    assert len(created) == 1
    assert created[0]["repo_url"] == "https://github.com/example/repo"
    assert created[0]["platform"] == "github"
    assert created[0]["issue_url"] == "https://github.com/example/repo/issues/0"
    assert created[0]["pitfalls_count"] == 1
    assert created[0]["warnings_count"] == 1
    assert created[0]["analysis_date"] == "2026-03-05T15:55:22Z"
    assert created[0]["sw_metadata_bot_version"]
    assert created[0]["rsmetacheck_version"]
    assert created[0]["pitfalls_ids"] == ["P001"]
    assert created[0]["warnings_ids"] == ["W004"]


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

    previous_report = tmp_path / "previous_created_issues_report.json"
    previous_report.write_text(
        json.dumps(
            [
                {
                    "repo_url": "https://github.com/example/repo",
                    "issue_url": "https://github.com/example/repo/issues/7",
                    "pitfalls_ids": ["P001"],
                    "warnings_ids": [],
                }
            ]
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
            "--previous-created-report",
            str(previous_report),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Summary: Created 0 | Skipped 1 | Failed 0" in result.output

    skipped = json.loads((issues_dir / "skipped_issues_report.json").read_text())
    assert skipped[0]["repo_url"] == "https://github.com/example/repo"
    assert skipped[0]["reason"] == "identical_and_issue_open"

    actions = json.loads((issues_dir / "actions_report.json").read_text())
    assert actions[0]["action"] == "stop"
    assert actions[0]["reason"] == "identical_and_issue_open"
