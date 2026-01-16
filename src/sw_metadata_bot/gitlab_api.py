"""GitLab API client."""

import os
from urllib.parse import urlparse

import requests


class GitLabAPI:
    """Simple GitLab API client."""

    def __init__(self, token: str | None = None, dry_run: bool = False):
        """Initialize GitLab API client."""
        self.token = token or os.getenv("GITLAB_API_TOKEN")
        self.dry_run = dry_run

        if not self.token and not dry_run:
            raise ValueError("GITLAB_API_TOKEN required (set in .env or environment)")

    @staticmethod
    def parse_url(url: str) -> tuple[str, str, str]:
        """
        Parse GitLab URL to extract host, owner, and repo.

        Returns:
            Tuple of (host, owner, repo_name)
        """
        parsed = urlparse(url)
        host = parsed.netloc

        if not host or "gitlab" not in host.lower():
            raise ValueError(f"Not a GitLab URL: {url}")

        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid GitLab URL format: {url}")

        owner, repo = parts[0], parts[1].removesuffix(".git")
        return host, owner, repo

    def get_base_url(self, host: str) -> str:
        """Get API base URL for GitLab host."""
        return f"https://{host}/api/v4"

    def test_auth(self, host: str = "gitlab.com") -> bool:
        """Test if authentication works."""
        if self.dry_run:
            return True

        try:
            base_url = self.get_base_url(host)
            response = requests.get(
                f"{base_url}/user",
                headers={"PRIVATE-TOKEN": self.token},
                timeout=10,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"GitLab auth failed: {e}")
            return False

    def create_issue(self, repo_url: str, title: str, body: str) -> str:
        """
        Create an issue on GitLab.

        Returns:
            URL of created issue (or fake URL in dry-run mode)
        """
        host, owner, repo = self.parse_url(repo_url)
        project_id = f"{owner}/{repo}"

        if self.dry_run:
            return f"https://{host}/{owner}/{repo}/-/issues/0"

        base_url = self.get_base_url(host)
        url = f"{base_url}/projects/{requests.utils.quote(project_id, safe='')}/issues"
        data = {"title": title, "description": body, "labels": "bot"}
        headers = {"PRIVATE-TOKEN": self.token}

        response = requests.post(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()

        return response.json()["web_url"]
