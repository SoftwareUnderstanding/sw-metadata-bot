"""Unit tests for GitLab API helpers."""

import pytest

from sw_metadata_bot.gitlab_api import GitLabAPI


@pytest.mark.parametrize(
    ("repo_url", "expected_namespace"),
    [
        ("https://gitlab.com/owner/repo", "owner"),
        ("https://gitlab.com/group/subgroup/repo", "group/subgroup"),
    ],
)
def test_parse_repo_url_supports_single_and_nested_groups(repo_url, expected_namespace):
    """Parse GitLab repository URLs with either a single owner or a nested group path."""
    host, namespace, repo = GitLabAPI.parse_repo_url(repo_url)

    assert host == "gitlab.com"
    assert namespace == expected_namespace
    assert repo == "repo"
