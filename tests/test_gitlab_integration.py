"""GitLab integration tests that exercise real API authentication."""

import os

import pytest

from sw_metadata_bot.gitlab_api import GitLabAPI


@pytest.mark.integration_gitlab
def test_gitlab_token_authentication_smoke():
    """Validate that the configured GitLab token authenticates against gitlab.com."""
    token = os.getenv("GITLAB_API_TOKEN")
    if not token:
        pytest.skip("GITLAB_API_TOKEN is not set")

    api = GitLabAPI(dry_run=False)
    assert api.check_auth("gitlab.com") is True
