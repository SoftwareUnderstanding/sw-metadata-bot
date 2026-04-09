"""Tests for publish module."""

import json
from datetime import datetime, timedelta, timezone

from click.testing import CliRunner

from sw_metadata_bot import publish as publish_module
from sw_metadata_bot.publish import publish_command

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeIssueClient:
    """Configurable test double for GitHub/GitLab API clients."""

    def __init__(self, comments_for=None):
        """Initialize the fake client with an optional comments_for function to simulate existing issue comments."""
        self.created: list[tuple[str, str, str]] = []
        self.commented: list[str] = []
        self.closed: list[str] = []
        self._comments_for = comments_for or (lambda url: [])

    def create_issue(self, repo_url: str, title: str, body: str) -> str:
        """Create issue method that records the created issue and returns a simulated issue URL."""
        self.created.append((repo_url, title, body))
        return f"{repo_url}/issues/99"

    def get_issue(self, issue_url: str) -> dict:
        """Get issue method that returns a dummy open issue to allow publish to proceed."""
        return {"state": "open"}

    def get_issue_comments(self, issue_url: str) -> list[str]:
        """Get issue comments method that returns comments based on the provided comments_for function."""
        return self._comments_for(issue_url)

    def add_issue_comment(self, issue_url: str, body: str) -> None:
        """Add issue comment method that records the commented issue URL."""
        self.commented.append(issue_url)

    def close_issue(self, issue_url: str) -> None:
        """Close issue method that records the closed issue URL."""
        self.closed.append(issue_url)


def _patch_clients(monkeypatch, github_client, gitlab_client=None):
    """Monkeypatch GitHubAPI and GitLabAPI constructors to return fakes."""
    monkeypatch.setattr(
        publish_module.github_api,
        "GitHubAPI",
        lambda dry_run=False: github_client,
    )
    if gitlab_client is not None:
        monkeypatch.setattr(
            publish_module.gitlab_api,
            "GitLabAPI",
            lambda dry_run=False: gitlab_client,
        )


def _write_run_report(snapshot_dir, records, run_metadata=None):
    """Write a minimal run_report.json for testing."""
    payload = {"records": records}
    if run_metadata:
        payload["run_metadata"] = run_metadata
    (snapshot_dir / "run_report.json").write_text(json.dumps(payload))


def _write_issue_report(snapshot_dir, repo_url, body="Issue body text"):
    """Write a per-repo issue_report.md so publish can find the body."""
    from sw_metadata_bot.config_utils import sanitize_repo_name

    repo_folder = snapshot_dir / sanitize_repo_name(repo_url)
    repo_folder.mkdir(parents=True, exist_ok=True)
    (repo_folder / "issue_report.md").write_text(body)


# ---------------------------------------------------------------------------
# simulated_created → created
# ---------------------------------------------------------------------------


def test_publish_simulated_created_becomes_created(tmp_path, monkeypatch):
    """publish promotes a simulated_created record to created by calling the API."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "simulated_created",
                "platform": "github",
                "dry_run": True,
                "simulated_issue_url": f"{repo_url}/issues/0",
                "issue_persistence": "simulated",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    fake = _FakeIssueClient()
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    assert len(fake.created) == 1
    assert fake.created[0][0] == repo_url

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "created"
    assert record["issue_url"] == f"{repo_url}/issues/99"
    assert record["issue_persistence"] == "posted"
    assert record.get("dry_run") is False
    assert "simulated_issue_url" not in record


def test_publish_updated_by_comment_posts_comment(tmp_path, monkeypatch):
    """publish calls add_issue_comment for updated_by_comment records."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"
    issue_url = f"{repo_url}/issues/5"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "updated_by_comment",
                "platform": "github",
                "issue_url": issue_url,
                "dry_run": True,
                "issue_persistence": "simulated",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    fake = _FakeIssueClient()
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    assert issue_url in fake.commented

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "updated_by_comment"
    assert record["issue_persistence"] == "posted"
    assert record.get("dry_run") is False


def test_publish_closed_closes_issue(tmp_path, monkeypatch):
    """publish closes the issue for closed records."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"
    issue_url = f"{repo_url}/issues/7"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "closed",
                "platform": "github",
                "issue_url": issue_url,
                "dry_run": True,
                "issue_persistence": "simulated",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    fake = _FakeIssueClient()
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    assert issue_url in fake.closed
    assert issue_url in fake.commented  # closing comment was posted

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "closed"
    assert record["issue_persistence"] == "posted"
    assert record.get("dry_run") is False


def test_publish_skipped_record_preserved(tmp_path, monkeypatch):
    """publish preserves skipped records unchanged."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "skipped",
                "platform": "github",
                "reason_code": "identical_and_issue_open",
                "dry_run": True,
            }
        ],
    )

    fake = _FakeIssueClient()
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    assert not fake.created
    assert not fake.commented

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "skipped"
    assert record["reason_code"] == "identical_and_issue_open"


def test_publish_already_published_records_skipped_for_idempotency(
    tmp_path, monkeypatch
):
    """publish leaves dry_run=False records untouched (idempotency guard)."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"
    issue_url = f"{repo_url}/issues/1"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "created",
                "platform": "github",
                "issue_url": issue_url,
                "dry_run": False,
                "issue_persistence": "posted",
            }
        ],
    )

    fake = _FakeIssueClient()
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    assert not fake.created
    assert not fake.commented

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    assert report["run_metadata"]["idempotency_skipped_records"] == 1


def test_publish_unsubscribe_detected_during_publish(tmp_path, monkeypatch):
    """publish detects unsubscribe comment and skips the action."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"
    issue_url = f"{repo_url}/issues/3"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "updated_by_comment",
                "platform": "github",
                "issue_url": issue_url,
                "dry_run": True,
                "issue_persistence": "simulated",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    fake = _FakeIssueClient(comments_for=lambda url: ["unsubscribe"])
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    assert not fake.commented  # no comment was posted

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "skipped"
    assert record["reason_code"] == "unsubscribe"


def test_publish_api_error_marks_record_as_failed(tmp_path, monkeypatch):
    """publish catches API errors and records them as failed with error message."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "simulated_created",
                "platform": "github",
                "dry_run": True,
                "issue_persistence": "simulated",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    class _BrokenClient:
        """API client that raises an exception for create_issue to simulate an API failure."""

        def create_issue(self, *a, **k):
            """Create issue method that raises a RuntimeError to simulate API failure."""
            raise RuntimeError("API unavailable")

        def get_issue(self, *a, **k):
            """Get issue method that returns a dummy open issue to allow publish to proceed to create_issue."""
            return {"state": "open"}

        def get_issue_comments(self, *a, **k):
            """Get issue comments method that returns an empty list to allow publish to proceed without detecting unsubscribe."""
            return []

        def add_issue_comment(self, *a, **k):
            """fake add_issue_comment that does nothing since the API is broken."""
            pass

        def close_issue(self, *a, **k):
            """fake close_issue that does nothing since the API is broken."""
            pass

    _patch_clients(monkeypatch, _BrokenClient())

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "failed"
    assert record["reason_code"] == "publish_exception"
    assert "API unavailable" in record["error"]
    assert record["dry_run"] is True
    assert record["is_transient_error"] is True
    assert record["retry_attempt"] == 1
    assert record["retry_after_seconds"] > 0
    assert record["last_publish_action"] == "simulated_created"


def test_publish_failed_record_not_retried_without_flag(tmp_path, monkeypatch):
    """publish keeps failed records untouched unless --retry-failed is set."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "failed",
                "platform": "github",
                "dry_run": True,
                "issue_persistence": "simulated",
                "error": "429 Too Many Requests",
                "is_transient_error": True,
                "retry_after_seconds": 1,
                "retry_attempt": 1,
                "failed_at": "2026-04-09T00:00:00Z",
                "last_publish_action": "simulated_created",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    fake = _FakeIssueClient()
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    assert not fake.created

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "failed"
    assert record["retry_attempt"] == 1
    assert report["run_metadata"]["failed_retry_skipped_records"] == 1


def test_publish_retry_failed_retries_transient_record(tmp_path, monkeypatch):
    """publish retries eligible transient failed records when --retry-failed is set."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"

    failed_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "failed",
                "platform": "github",
                "dry_run": True,
                "issue_persistence": "simulated",
                "error": "429 Too Many Requests",
                "is_transient_error": True,
                "retry_after_seconds": 60,
                "retry_attempt": 1,
                "failed_at": failed_at,
                "last_publish_action": "simulated_created",
                "simulated_issue_url": f"{repo_url}/issues/0",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    fake = _FakeIssueClient()
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(
        publish_command,
        ["--analysis-root", str(snapshot_dir), "--retry-failed"],
    )

    assert result.exit_code == 0, result.output
    assert len(fake.created) == 1

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "created"
    assert record["dry_run"] is False
    assert "error" not in record
    assert "retry_attempt" not in record


def test_publish_retry_failed_skips_non_transient_record(tmp_path, monkeypatch):
    """publish does not retry failed records classified as non-transient."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "failed",
                "platform": "github",
                "dry_run": True,
                "issue_persistence": "simulated",
                "error": "403 Forbidden",
                "is_transient_error": False,
                "retry_after_seconds": 0,
                "retry_attempt": 1,
                "failed_at": "2026-04-09T00:00:00Z",
                "last_publish_action": "simulated_created",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    fake = _FakeIssueClient()
    _patch_clients(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(
        publish_command,
        ["--analysis-root", str(snapshot_dir), "--retry-failed"],
    )

    assert result.exit_code == 0, result.output
    assert not fake.created

    report = json.loads((snapshot_dir / "run_report.json").read_text())
    record = report["records"][0]
    assert record["action"] == "failed"
    assert report["run_metadata"]["failed_retry_skipped_records"] == 1


def test_publish_run_report_contains_published_at(tmp_path, monkeypatch):
    """publish writes published_at timestamp to the run report."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://github.com/example/repo"

    _write_run_report(
        snapshot_dir,
        records=[{"repo_url": repo_url, "action": "skipped", "dry_run": True}],
    )

    _patch_clients(monkeypatch, _FakeIssueClient())

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    report = json.loads((snapshot_dir / "run_report.json").read_text())
    assert "published_at" in report["run_metadata"]


def test_publish_missing_run_report_exits_with_error(tmp_path):
    """publish exits with a ClickException when run_report.json is missing."""
    snapshot_dir = tmp_path / "empty_snapshot"
    snapshot_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code != 0


def test_publish_gitlab_simulated_created_uses_gitlab_client(tmp_path, monkeypatch):
    """publish routes GitLab repos to the GitLab client."""
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    repo_url = "https://gitlab.com/example/repo"

    _write_run_report(
        snapshot_dir,
        records=[
            {
                "repo_url": repo_url,
                "action": "simulated_created",
                "platform": "gitlab",
                "dry_run": True,
                "issue_persistence": "simulated",
            }
        ],
    )
    _write_issue_report(snapshot_dir, repo_url)

    github_fake = _FakeIssueClient()
    gitlab_fake = _FakeIssueClient()
    _patch_clients(monkeypatch, github_fake, gitlab_fake)

    runner = CliRunner()
    result = runner.invoke(publish_command, ["--analysis-root", str(snapshot_dir)])

    assert result.exit_code == 0, result.output
    assert not github_fake.created
    assert len(gitlab_fake.created) == 1
    assert gitlab_fake.created[0][0] == repo_url
