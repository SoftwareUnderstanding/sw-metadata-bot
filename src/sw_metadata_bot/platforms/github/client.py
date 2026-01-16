"""GitHub platform implementation."""

from urllib.parse import urlparse

import requests

from ...core.exceptions import AuthenticationError, IssueCreationError, URLParsingError
from ...core.repository import Credentials, Issue, Repository
from ..base import RepositoryPlatform


class GitHubURLParser:
    """Parser for GitHub repository URLs."""

    @staticmethod
    def parse(url: str) -> tuple[str, str]:
        """
        Parse a GitHub repository URL.

        Args:
            url: GitHub repository URL (e.g., "https://github.com/owner/repo")

        Returns:
            Tuple of (owner, repo_name)

        Raises:
            URLParsingError: If URL is not a valid GitHub URL
        """
        parsed = urlparse(url)

        if parsed.netloc != "github.com":
            raise URLParsingError(url, platform="GitHub")

        # Remove leading slash and split path
        path_parts = parsed.path.strip("/").split("/")

        if len(path_parts) < 2:
            raise URLParsingError(url, platform="GitHub")

        owner = path_parts[0]
        repo = path_parts[1]

        # Remove .git suffix if present
        if repo.endswith(".git"):
            repo = repo[:-4]

        return owner, repo


class GitHubAPI(RepositoryPlatform):
    """GitHub API implementation."""

    API_BASE_URL = "https://api.github.com"

    def __init__(
        self,
        credentials: Credentials,
        dry_run: bool = False,
    ):
        """Initialize GitHub API client."""
        super().__init__(credentials)
        self.dry_run = dry_run
        self.headers = self._build_headers()

    def _build_headers(self) -> dict:
        """Build request headers with authentication."""
        return {
            "Authorization": f"token {self.credentials.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    @property
    def platform_name(self) -> str:
        """Return platform name."""
        return "github"

    def parse_repository_url(self, url: str) -> Repository:
        """Parse a GitHub repository URL."""
        owner, repo = GitHubURLParser.parse(url)
        return Repository(
            url=url,
            platform="github",
            owner=owner,
            name=repo,
        )

    def validate_credentials(self) -> bool:
        """Validate GitHub credentials."""
        try:
            response = requests.get(
                f"{self.API_BASE_URL}/user",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            user = response.json()
            return bool(user.get("login"))
        except requests.exceptions.RequestException as e:
            raise AuthenticationError(
                platform="GitHub",
                reason=f"Failed to validate token: {e}",
            )

    def create_issue(self, repository: Repository, title: str, body: str) -> Issue:
        """Create an issue on GitHub."""
        if self.dry_run:
            return Issue(
                title=title,
                body=body,
                url=f"https://github.com/{repository.owner}/{repository.name}/issues/0",
                repository_url=repository.url,
                platform="github",
            )

        try:
            issues_url = (
                f"{self.API_BASE_URL}/repos/{repository.owner}/{repository.name}/issues"
            )
            data = {
                "title": title,
                "body": body,
                "labels": ["bot"],
            }

            response = requests.post(
                issues_url,
                json=data,
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()

            issue_data = response.json()
            return Issue(
                title=title,
                body=body,
                url=issue_data.get("html_url"),
                repository_url=repository.url,
                platform="github",
            )
        except requests.exceptions.RequestException as e:
            raise IssueCreationError(
                repository.url,
                reason=f"GitHub API error: {e}",
            )
