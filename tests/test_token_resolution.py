"""Tests for API token resolution precedence."""

from sw_metadata_bot.github_api import GitHubAPI
from sw_metadata_bot.gitlab_api import GitLabAPI


def test_github_explicit_token_has_priority(monkeypatch, tmp_path):
    """Explicit constructor token should override env and .env values."""
    monkeypatch.setenv("GITHUB_API_TOKEN", "from-env")
    (tmp_path / ".env").write_text("GITHUB_API_TOKEN=from-dotenv\n")
    monkeypatch.chdir(tmp_path)

    api = GitHubAPI(token="from-explicit", dry_run=False)
    assert api.token == "from-explicit"


def test_github_env_token_has_priority_over_dotenv(monkeypatch, tmp_path):
    """Environment variable should be preferred over .env fallback."""
    monkeypatch.setenv("GITHUB_API_TOKEN", "from-env")
    (tmp_path / ".env").write_text("GITHUB_API_TOKEN=from-dotenv\n")
    monkeypatch.chdir(tmp_path)

    api = GitHubAPI(dry_run=False)
    assert api.token == "from-env"


def test_github_dotenv_fallback(monkeypatch, tmp_path):
    """Use .env token when no explicit token and no env var are set."""
    monkeypatch.delenv("GITHUB_API_TOKEN", raising=False)
    (tmp_path / ".env").write_text("GITHUB_API_TOKEN=from-dotenv\n")
    monkeypatch.chdir(tmp_path)

    api = GitHubAPI(dry_run=False)
    assert api.token == "from-dotenv"


def test_gitlab_dotenv_fallback(monkeypatch, tmp_path):
    """Use .env token for GitLab when no env var is set."""
    monkeypatch.delenv("GITLAB_API_TOKEN", raising=False)
    (tmp_path / ".env").write_text("GITLAB_API_TOKEN=from-dotenv\n")
    monkeypatch.chdir(tmp_path)

    api = GitLabAPI(dry_run=False)
    assert api.token == "from-dotenv"


def test_missing_token_raises_outside_dry_run(monkeypatch, tmp_path):
    """Non-dry-run mode should still raise when token cannot be resolved."""
    monkeypatch.delenv("GITHUB_API_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)

    try:
        GitHubAPI(dry_run=False)
    except ValueError as exc:
        assert "GITHUB_API_TOKEN required" in str(exc)
    else:
        raise AssertionError("Expected ValueError when token is missing")
