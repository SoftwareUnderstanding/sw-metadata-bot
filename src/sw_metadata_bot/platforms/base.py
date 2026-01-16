"""Abstract base class for repository platforms."""

from abc import ABC, abstractmethod

from ..core.repository import Credentials, Issue, Repository


class RepositoryPlatform(ABC):
    """Abstract base class for repository platform implementations."""

    def __init__(self, credentials: Credentials):
        """
        Initialize the platform with credentials.

        Args:
            credentials: Credentials object containing authentication info
        """
        self.credentials = credentials

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the name of this platform (e.g., 'github', 'gitlab')."""
        pass

    @abstractmethod
    def parse_repository_url(self, url: str) -> Repository:
        """
        Parse a repository URL and return a Repository object.

        Args:
            url: The repository URL to parse

        Returns:
            Repository object with parsed details

        Raises:
            URLParsingError: If URL cannot be parsed
        """
        pass

    @abstractmethod
    def validate_credentials(self) -> bool:
        """
        Validate that the credentials are valid for this platform.

        Returns:
            True if credentials are valid

        Raises:
            AuthenticationError: If credentials are invalid
        """
        pass

    @abstractmethod
    def create_issue(self, repository: Repository, title: str, body: str) -> Issue:
        """
        Create an issue in the specified repository.

        Args:
            repository: The Repository object where to create the issue
            title: The issue title
            body: The issue body/description

        Returns:
            Issue object with the created issue details

        Raises:
            IssueCreationError: If issue creation fails
        """
        pass

    def get_repository_info(self, repository: Repository) -> dict:
        """
        Get additional information about a repository (optional).

        Args:
            repository: The Repository object

        Returns:
            Dictionary with repository metadata

        Note:
            Override this method in subclass if needed
        """
        return {}

    def supports_dry_run(self) -> bool:
        """
        Check if this platform supports dry-run mode.

        Returns:
            True if dry-run is supported

        Note:
            Override this method if platform has special requirements
        """
        return True
