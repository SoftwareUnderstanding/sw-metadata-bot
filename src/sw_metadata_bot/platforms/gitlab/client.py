"""GitLab platform implementation (stub for future development)."""

from typing import Optional
from urllib.parse import urlparse

import requests

from ...core.exceptions import AuthenticationError, IssueCreationError, URLParsingError
from ...core.repository import Credentials, Issue, Repository
from ..base import RepositoryPlatform


class GitLabURLParser:
    """Parser for GitLab repository URLs."""

    @staticmethod
    def parse(url: str, platform: str = "gitlab") -> tuple[str, str, Optional[str]]:
        """
        Parse a GitLab repository URL.

        Args:
            url: GitLab repository URL
            platform: Either "gitlab" for gitlab.com or "gitlab_self_hosted"

        Returns:
            Tuple of (owner, repo_name, instance_url)
            For gitlab.com, instance_url is None
            For self-hosted, instance_url is the base URL

        Raises:
            URLParsingError: If URL is not a valid GitLab URL
        """
        parsed = urlparse(url)
        netloc = parsed.netloc

        # Determine instance URL
        instance_url: Optional[str] = None
        if platform == "gitlab":
            if netloc != "gitlab.com":
                raise URLParsingError(url, platform="GitLab")
        else:  # self-hosted
            instance_url = f"{parsed.scheme}://{netloc}"

        # Parse path: /owner/repo or /namespace/subnamespace/repo
        path_parts = parsed.path.strip("/").split("/")

        if len(path_parts) < 2:
            raise URLParsingError(url, platform="GitLab")

        # For now, treat first part as owner, second as repo
        # In production, you'd handle nested groups/subgroups
        owner = "/".join(path_parts[:-1])
        repo = path_parts[-1]

        # Remove .git suffix if present
        if repo.endswith(".git"):
            repo = repo[:-4]

        return owner, repo, instance_url


class GitLabAPI(RepositoryPlatform):
    """GitLab API implementation (for gitlab.com and self-hosted)."""

    def __init__(
        self,
        credentials: Credentials,
        dry_run: bool = False,
        is_self_hosted: bool = False,
    ):
        """
        Initialize GitLab API client.

        Args:
            credentials: Credentials object with token and optional instance_url
            dry_run: If True, simulate operations without making actual API calls
            is_self_hosted: If True, treats this as a self-hosted GitLab instance
        """
        super().__init__(credentials)
        self.dry_run = dry_run
        self.is_self_hosted = is_self_hosted

        # Determine base URL
        if is_self_hosted and credentials.instance_url:
            self.base_url = credentials.instance_url.rstrip("/")
        else:
            self.base_url = "https://gitlab.com"

        self.api_base = f"{self.base_url}/api/v4"
        self.headers = self._build_headers()

    def _build_headers(self) -> dict:
        """Build request headers with authentication."""
        return {
            "PRIVATE-TOKEN": self.credentials.token,
            "Content-Type": "application/json",
        }

    @property
    def platform_name(self) -> str:
        """Return platform name."""
        return "gitlab_self_hosted" if self.is_self_hosted else "gitlab"

    def parse_repository_url(self, url: str) -> Repository:
        """Parse a GitLab repository URL."""
        platform = "gitlab_self_hosted" if self.is_self_hosted else "gitlab"
        owner, repo, instance_url = GitLabURLParser.parse(url, platform)

        return Repository(
            url=url,
            platform=platform,
            owner=owner,
            name=repo,
            instance_url=instance_url,
        )

    def validate_credentials(self) -> bool:
        """Validate GitLab credentials."""
        try:
            response = requests.get(
                f"{self.api_base}/user",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            user = response.json()
            return bool(user.get("username"))
        except requests.exceptions.RequestException as e:
            raise AuthenticationError(
                platform=self.platform_name,
                reason=f"Failed to validate token: {e}",
            )

    def create_issue(self, repository: Repository, title: str, body: str) -> Issue:
        """Create an issue on GitLab."""
        if self.dry_run:
            return Issue(
                title=title,
                body=body,
                url=f"{self.base_url}/{repository.owner}/{repository.name}/-/issues/0",
                repository_url=repository.url,
                platform=self.platform_name,
            )

        try:
            # GitLab uses URL-encoded project identifiers
            # For simplicity, using owner/name format (would need encoding for special chars)
            project_id = f"{repository.owner}%2F{repository.name}"

            issues_url = f"{self.api_base}/projects/{project_id}/issues"
            data = {
                "title": title,
                "description": body,
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
                url=issue_data.get("web_url"),
                repository_url=repository.url,
                platform=self.platform_name,
            )
        except requests.exceptions.RequestException as e:
            raise IssueCreationError(
                repository.url,
                reason=f"GitLab API error: {e}",
            )
