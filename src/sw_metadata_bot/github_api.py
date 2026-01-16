"""GitHub API client."""

import os
from urllib.parse import urlparse

import requests


class GitHubAPI:
    """Simple GitHub API client."""

    def __init__(self, token: str | None = None, dry_run: bool = False):
        """Initialize GitHub API client."""
        self.token = token or os.getenv("GITHUB_API_TOKEN")
        self.dry_run = dry_run
        self.base_url = "https://api.github.com"

        if not self.token and not dry_run:
            raise ValueError("GITHUB_API_TOKEN required (set in .env or environment)")

    @staticmethod
    def parse_url(url: str) -> tuple[str, str]:
        """
        Parse GitHub URL to extract owner and repo.

        Returns:
            Tuple of (owner, repo_name)
        """
        parsed = urlparse(url)
        if parsed.netloc != "github.com":
            raise ValueError(f"Not a GitHub URL: {url}")

        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid GitHub URL format: {url}")

        owner, repo = parts[0], parts[1].removesuffix(".git")
        return owner, repo

    def test_auth(self) -> bool:
        """Test if authentication works."""
        if self.dry_run:
            return True

        try:
            response = requests.get(
                f"{self.base_url}/user",
                headers={"Authorization": f"token {self.token}"},
                timeout=10,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"GitHub auth failed: {e}")
            return False

    def create_issue(self, repo_url: str, title: str, body: str) -> str:
        """
        Create an issue on GitHub.

        Returns:
            URL of created issue (or fake URL in dry-run mode)
        """
        owner, repo = self.parse_url(repo_url)

        if self.dry_run:
            return f"https://github.com/{owner}/{repo}/issues/0"

        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        data = {"title": title, "body": body, "labels": ["bot"]}
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        response = requests.post(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()

        return response.json()["html_url"]
