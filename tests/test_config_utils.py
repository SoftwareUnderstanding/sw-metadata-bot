"""Tests for platform detection helper."""

from sw_metadata_bot.config_utils import detect_platform


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
