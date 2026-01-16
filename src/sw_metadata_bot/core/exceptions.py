"""Custom exceptions for sw-metadata-bot."""


class RepositoryError(Exception):
    """Base exception for repository-related errors."""

    pass


class URLParsingError(RepositoryError):
    """Raised when a repository URL cannot be parsed."""

    def __init__(self, url: str, platform: str = "unknown"):
        self.url = url
        self.platform = platform
        super().__init__(f"Failed to parse {platform} URL: {url}")


class AuthenticationError(RepositoryError):
    """Raised when authentication fails."""

    def __init__(self, platform: str, reason: str = ""):
        self.platform = platform
        self.reason = reason
        msg = f"Authentication failed for {platform}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class IssueCreationError(RepositoryError):
    """Raised when issue creation fails."""

    def __init__(self, repo_url: str, reason: str = ""):
        self.repo_url = repo_url
        self.reason = reason
        msg = f"Failed to create issue for {repo_url}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class PlatformNotSupportedError(RepositoryError):
    """Raised when a repository platform is not supported."""

    def __init__(self, platform: str, available_platforms: list[str] = None):
        self.platform = platform
        self.available_platforms = available_platforms or []
        msg = f"Platform '{platform}' is not supported"
        if self.available_platforms:
            msg += f". Supported platforms: {', '.join(self.available_platforms)}"
        super().__init__(msg)


class ConfigurationError(RepositoryError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str):
        super().__init__(f"Configuration error: {message}")


class PitfallsParsingError(RepositoryError):
    """Raised when pitfalls data cannot be parsed."""

    def __init__(self, file_path: str, reason: str = ""):
        self.file_path = file_path
        self.reason = reason
        msg = f"Failed to parse pitfalls file: {file_path}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
