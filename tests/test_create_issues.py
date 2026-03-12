"""Tests for create_issues command module."""

import json

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


class _FakeIssueClient:
    """Configurable test double for issue client operations."""

    def __init__(self, comments_for=None):
        """Set up with an optional callable returning comments by issue URL."""
        self.commented: list[str] = []
        self._comments_for = comments_for or (lambda url: [])

    def create_issue(self, repo_url: str, title: str, body: str) -> str:
        """Return a synthetic issue URL."""
        return f"{repo_url}/issues/0"

    def get_issue(self, issue_url: str) -> dict:
        """Return an open issue stub."""
        return {"state": "open"}

    def get_issue_comments(self, issue_url: str) -> list[str]:
        """Return comments from the configured callback."""
        return self._comments_for(issue_url)

    def add_issue_comment(self, issue_url: str, body: str) -> None:
        """Record the commented issue URL."""
        self.commented.append(issue_url)

    def close_issue(self, issue_url: str) -> None:
        """No-op stub."""
        return None


def _patch_issue_client(monkeypatch, client: _FakeIssueClient) -> None:
    """Monkeypatch _get_or_create_client to return the given fake client."""
    monkeypatch.setattr(
        create_issues,
        "_get_or_create_client",
        lambda platform, dry_run, github, gitlab: (client, None, client),
    )


def _write_community_config(tmp_path, **overrides):
    """Write a minimal community config and return its path."""
    config = {
        "community": {"name": "ossr"},
        "repositories": ["https://github.com/example/repo"],
        "issues": {"custom_message": None, "opt_outs": []},
        "outputs": {"root_dir": "outputs", "run_name": "ossr"},
    }
    config.update(overrides)
    config_path = tmp_path / "community.json"
    config_path.write_text(json.dumps(config))
    return config_path


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
    community_config = _write_community_config(tmp_path)
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--community-config-file",
            str(community_config),
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
    community_config = _write_community_config(tmp_path)
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--community-config-file",
            str(community_config),
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
    community_config = _write_community_config(tmp_path)
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--community-config-file",
            str(community_config),
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
    community_config = _write_community_config(tmp_path)
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--community-config-file",
            str(community_config),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "No pitfalls files found" in result.output


def test_create_issues_incremental_identical_open_issue_skips(tmp_path, monkeypatch):
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

    fake_client = _FakeIssueClient()
    _patch_issue_client(monkeypatch, fake_client)

    runner = CliRunner()
    community_config = _write_community_config(tmp_path)
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--community-config-file",
            str(community_config),
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


def test_create_issues_incremental_uses_current_commit_id_field(tmp_path, monkeypatch):
    """Skip as not-updated when previous report stores current_commit_id."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    pitfalls_payload = {
        "dateCreated": "2026-03-11T13:51:04Z",
        "assessedSoftware": {"url": "https://github.com/example/repo"},
        "checks": [
            {
                "checkId": "hash-p",
                "assessesIndicator": {
                    "@id": "https://w3id.org/rsmetacheck/catalog/#P001"
                },
                "evidence": "P001 detected",
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
                        "current_commit_id": "abc123",
                    }
                ]
            }
        )
    )

    analysis_summary = tmp_path / "analysis_results.json"
    analysis_summary.write_text(
        json.dumps(
            {
                "summary": {
                    "evaluated_repositories": {
                        "example/repo": {
                            "url": "https://github.com/example/repo",
                            "commit_id": "abc123",
                        }
                    }
                }
            }
        )
    )

    fake_client = _FakeIssueClient()
    _patch_issue_client(monkeypatch, fake_client)

    runner = CliRunner()
    community_config = _write_community_config(tmp_path)
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--community-config-file",
            str(community_config),
            "--previous-report",
            str(previous_report),
            "--analysis-summary-file",
            str(analysis_summary),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0

    report = json.loads((issues_dir / "report.json").read_text())
    assert report["counters"]["skipped"] == 1
    assert report["records"][0]["reason_code"] == "repo_not_updated"


def test_create_issues_mixed_repo_decisions_same_changed_unsubscribe(
    tmp_path, monkeypatch
):
    """Handle mixed repositories: unchanged commit, changed findings, and unsubscribe."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    payload_same = {
        "dateCreated": "2026-03-11T13:51:04Z",
        "assessedSoftware": {"url": "https://github.com/example/repo-same"},
        "checks": [
            {
                "assessesIndicator": {
                    "@id": "https://w3id.org/rsmetacheck/catalog/#P001"
                },
                "evidence": "P001 detected",
            }
        ],
    }
    payload_changed = {
        "dateCreated": "2026-03-11T13:51:04Z",
        "assessedSoftware": {"url": "https://github.com/example/repo-changed"},
        "checks": [
            {
                "assessesIndicator": {
                    "@id": "https://w3id.org/rsmetacheck/catalog/#P001"
                },
                "evidence": "P001 detected",
            },
            {
                "assessesIndicator": {
                    "@id": "https://w3id.org/rsmetacheck/catalog/#W004"
                },
                "evidence": "W004 detected",
            },
        ],
    }
    payload_unsub = {
        "dateCreated": "2026-03-11T13:51:04Z",
        "assessedSoftware": {"url": "https://github.com/example/repo-unsub"},
        "checks": [
            {
                "assessesIndicator": {
                    "@id": "https://w3id.org/rsmetacheck/catalog/#P001"
                },
                "evidence": "P001 detected",
            }
        ],
    }

    (pitfalls_dir / "a_same.jsonld").write_text(json.dumps(payload_same))
    (pitfalls_dir / "b_changed.jsonld").write_text(json.dumps(payload_changed))
    (pitfalls_dir / "c_unsub.jsonld").write_text(json.dumps(payload_unsub))

    previous_report = tmp_path / "previous_report.json"
    previous_report.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo-same",
                        "issue_url": "https://github.com/example/repo-same/issues/1",
                        "pitfalls_ids": ["P001"],
                        "warnings_ids": [],
                        "issue_persistence": "posted",
                        "current_commit_id": "abc123",
                    },
                    {
                        "repo_url": "https://github.com/example/repo-changed",
                        "issue_url": "https://github.com/example/repo-changed/issues/2",
                        "pitfalls_ids": ["P001"],
                        "warnings_ids": [],
                        "issue_persistence": "posted",
                        "current_commit_id": "old222",
                    },
                    {
                        "repo_url": "https://github.com/example/repo-unsub",
                        "issue_url": "https://github.com/example/repo-unsub/issues/3",
                        "pitfalls_ids": ["P001"],
                        "warnings_ids": [],
                        "issue_persistence": "posted",
                        "current_commit_id": "old333",
                    },
                ]
            }
        )
    )

    analysis_summary = tmp_path / "analysis_results.json"
    analysis_summary.write_text(
        json.dumps(
            {
                "summary": {
                    "evaluated_repositories": {
                        "same": {
                            "url": "https://github.com/example/repo-same",
                            "commit_id": "abc123",
                        },
                        "changed": {
                            "url": "https://github.com/example/repo-changed",
                            "commit_id": "new222",
                        },
                        "unsub": {
                            "url": "https://github.com/example/repo-unsub",
                            "commit_id": "new333",
                        },
                    }
                }
            }
        )
    )

    fake_client = _FakeIssueClient(
        comments_for=lambda url: ["unsubscribe"] if url.endswith("/3") else []
    )
    community_config = _write_community_config(tmp_path)
    _patch_issue_client(monkeypatch, fake_client)

    runner = CliRunner()
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--community-config-file",
            str(community_config),
            "--previous-report",
            str(previous_report),
            "--analysis-summary-file",
            str(analysis_summary),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0

    report = json.loads((issues_dir / "report.json").read_text())
    by_repo = {record["repo_url"]: record for record in report["records"]}

    assert (
        by_repo["https://github.com/example/repo-same"]["reason_code"]
        == "repo_not_updated"
    )
    assert by_repo["https://github.com/example/repo-same"]["action"] == "skipped"

    assert (
        by_repo["https://github.com/example/repo-changed"]["reason_code"]
        == "changed_and_issue_open"
    )
    assert (
        by_repo["https://github.com/example/repo-changed"]["action"]
        == "updated_by_comment"
    )

    assert (
        by_repo["https://github.com/example/repo-unsub"]["reason_code"] == "unsubscribe"
    )
    assert by_repo["https://github.com/example/repo-unsub"]["action"] == "skipped"

    updated_config = json.loads(community_config.read_text())
    assert updated_config["issues"]["opt_outs"] == [
        "https://github.com/example/repo-unsub"
    ]


def test_create_issues_uses_previous_issue_url_lineage_in_dry_run(
    tmp_path, monkeypatch
):
    """Detect unsubscribe when previous report carries previous_issue_url only."""
    pitfalls_dir = tmp_path / "pitfalls"
    pitfalls_dir.mkdir()
    issues_dir = tmp_path / "issues"

    payload = {
        "dateCreated": "2026-03-12T13:57:53Z",
        "assessedSoftware": {"url": "https://github.com/example/repo"},
        "checks": [
            {
                "assessesIndicator": {
                    "@id": "https://w3id.org/rsmetacheck/catalog/#W004"
                },
                "evidence": "W004 detected",
            }
        ],
    }
    (pitfalls_dir / "sample.jsonld").write_text(json.dumps(payload))

    previous_report = tmp_path / "previous_report.json"
    previous_report.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "previous_issue_url": "https://github.com/example/repo/issues/7",
                        "issue_persistence": "none",
                        "pitfalls_ids": [],
                        "warnings_ids": ["W004"],
                    }
                ]
            }
        )
    )

    fake_client = _FakeIssueClient(comments_for=lambda url: ["unsubscribe"])
    community_config = _write_community_config(tmp_path)
    _patch_issue_client(monkeypatch, fake_client)

    runner = CliRunner()
    result = runner.invoke(
        create_issues.create_issues_command,
        [
            "--pitfalls-output-dir",
            str(pitfalls_dir),
            "--issues-dir",
            str(issues_dir),
            "--community-config-file",
            str(community_config),
            "--previous-report",
            str(previous_report),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    report = json.loads((issues_dir / "report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "skipped"
    assert record["reason_code"] == "unsubscribe"
