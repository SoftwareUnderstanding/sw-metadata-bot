"""Tests for configuration and platform handling."""

from sw_metadata_bot.config.config_utils import (
    detect_platform,
    normalize_repo_url,
    sanitize_repo_name,
)


def test_detect_platform_github():
    """Return 'github' for GitHub URLs."""
    assert detect_platform("https://github.com/org/repo") == "github"


def test_detect_platform_gitlab_dot_com():
    """Return 'gitlab' for GitLab.com URLs."""
    assert detect_platform("https://gitlab.com/group/repo") == "gitlab"


def test_detect_platform_self_hosted_gitlab():
    """Return 'gitlab' for self-hosted GitLab instances."""
    assert detect_platform("https://gitlab.example.org/group/repo") == "gitlab"


def test_detect_platform_unsupported():
    """Return None for URLs that do not match a known platform."""
    assert detect_platform("https://example.org/org/repo") is None


def test_sanitize_repo_name():
    """Sanitize repository URLs to safe folder names."""
    assert sanitize_repo_name("https://github.com/org/repo") == "github_com_org_repo"


def test_sanitize_repo_name_with_git_suffix():
    """Remove .git suffix when sanitizing repository URLs."""
    assert (
        sanitize_repo_name("https://github.com/org/repo.git") == "github_com_org_repo"
    )


def test_normalize_repo_url():
    """Normalize repository URLs by stripping whitespace and trailing slashes."""
    assert (
        normalize_repo_url("https://github.com/org/repo/")
        == "https://github.com/org/repo"
    )
    assert (
        normalize_repo_url(" https://github.com/org/repo ")
        == "https://github.com/org/repo"
    )


# def test_resolve_output_root():
#     """Resolve output root directory from config or default."""
#     assert resolve_output_root(None) == "outputs"
#     assert resolve_output_root("custom_outputs") == "custom_outputs"


# def test_resolve_run_name():
#     """Resolve run name from config or default."""
#     assert resolve_run_name(None) is None
#     assert resolve_run_name("custom_run") == "custom_run"
