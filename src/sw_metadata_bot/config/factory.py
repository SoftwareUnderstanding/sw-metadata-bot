"""Platform registry and factory for creating platform instances."""

import os
from typing import Dict, Optional

from ..core import ConfigurationError, Credentials
from ..platforms import GitHubAPI, GitLabAPI, RepositoryPlatform
from ..platforms.gitlab import GitLabURLParser


class RepositoryTypeDetector:
    """Detects repository platform from URL."""

    # Mapping of domain patterns to platform types
    PLATFORM_MAPPING = {
        "github.com": "github",
        "gitlab.com": "gitlab",
        "bitbucket.org": "bitbucket",  # For future support
    }

    # Known self-hosted GitLab instances
    KNOWN_SELF_HOSTED = {
        "git.astron.nl": "gitlab_self_hosted",
        "git.ligo.org": "gitlab_self_hosted",
    }

    @staticmethod
    def detect(url: str) -> str:
        """
        Detect the platform type from a repository URL.

        Args:
            url: The repository URL

        Returns:
            Platform type string: "github", "gitlab", "gitlab_self_hosted", etc.

        Raises:
            ConfigurationError: If platform cannot be detected
        """
        # Check known domains
        for domain, platform in RepositoryTypeDetector.PLATFORM_MAPPING.items():
            if domain in url:
                return platform

        # Check known self-hosted instances
        for domain, platform in RepositoryTypeDetector.KNOWN_SELF_HOSTED.items():
            if domain in url:
                return platform

        # Generic gitlab detection for unknown self-hosted instances
        if "gitlab" in url.lower() and "gitlab.com" not in url:
            return "gitlab_self_hosted"

        raise ConfigurationError(
            f"Could not detect platform from URL: {url}. "
            f"Supported platforms: github, gitlab, gitlab_self_hosted"
        )


class PlatformRegistry:
    """Registry for managing platform implementations."""

    def __init__(self):
        """Initialize the platform registry."""
        self._platforms: Dict[str, type] = {
            "github": GitHubAPI,
            "gitlab": GitLabAPI,
            "gitlab_self_hosted": GitLabAPI,
        }

        self._dry_run = False
        self._credentials_cache: Dict[str, Credentials] = {}

    def register_platform(self, platform_name: str, platform_class: type) -> None:
        """
        Register a new platform implementation.

        Args:
            platform_name: Name of the platform
            platform_class: Class implementing RepositoryPlatform
        """
        if not issubclass(platform_class, RepositoryPlatform):
            raise TypeError(f"{platform_class} must inherit from RepositoryPlatform")
        self._platforms[platform_name] = platform_class

    def set_dry_run(self, dry_run: bool) -> None:
        """Set dry-run mode for all future platform instances."""
        self._dry_run = dry_run

    def get_platform(
        self, platform_name: str, credentials: Credentials
    ) -> RepositoryPlatform:
        """
        Get a platform instance.

        Args:
            platform_name: Name of the platform ("github", "gitlab", etc.)
            credentials: Credentials for authentication

        Returns:
            Instance of the specified platform

        Raises:
            ConfigurationError: If platform is not registered
        """
        if platform_name not in self._platforms:
            available = ", ".join(self._platforms.keys())
            raise ConfigurationError(
                f"Platform '{platform_name}' not found. Available: {available}"
            )

        platform_class = self._platforms[platform_name]

        # Handle platform-specific initialization
        if platform_name == "gitlab_self_hosted":
            return platform_class(
                credentials=credentials,
                dry_run=self._dry_run,
                is_self_hosted=True,
            )
        else:
            return platform_class(credentials=credentials, dry_run=self._dry_run)

    @property
    def available_platforms(self) -> list[str]:
        """Get list of available platform names."""
        return list(self._platforms.keys())


class CredentialsManager:
    """Manages credentials for different platforms."""

    def __init__(self):
        """Initialize the credentials manager."""
        self._env_var_mapping = {
            "github": "GITHUB_API_TOKEN",
            "gitlab": "GITLAB_API_TOKEN",
            "gitlab_self_hosted": "GITLAB_API_TOKEN",  # Same token type
        }

    def get_credentials_from_env(
        self,
        platform: str,
        instance_url: Optional[str] = None,
    ) -> Credentials:
        """
        Get credentials from environment variables.

        Args:
            platform: The platform type
            instance_url: For self-hosted instances, the base URL

        Returns:
            Credentials object

        Raises:
            ConfigurationError: If required credentials not found
        """
        env_var = self._env_var_mapping.get(platform)
        if not env_var:
            raise ConfigurationError(f"Unknown platform: {platform}")

        token = os.getenv(env_var)
        if not token:
            raise ConfigurationError(
                f"Token not found in environment variable {env_var}"
            )

        return Credentials(
            platform=platform,
            token=token,
            instance_url=instance_url,
        )

    def get_credentials(
        self,
        platform: str,
        token: Optional[str] = None,
        instance_url: Optional[str] = None,
    ) -> Credentials:
        """
        Get credentials from provided token or environment.

        Args:
            platform: The platform type
            token: Optional explicit token (if not provided, uses environment)
            instance_url: For self-hosted instances, the base URL

        Returns:
            Credentials object
        """
        if token:
            return Credentials(
                platform=platform,
                token=token,
                instance_url=instance_url,
            )

        return self.get_credentials_from_env(platform, instance_url)


class PlatformFactory:
    """Factory for creating platform instances."""

    def __init__(self):
        """Initialize the factory."""
        self.registry = PlatformRegistry()
        self.credentials_manager = CredentialsManager()

    def set_dry_run(self, dry_run: bool) -> None:
        """Set dry-run mode."""
        self.registry.set_dry_run(dry_run)

    def create_platform_from_url(
        self,
        url: str,
        token: Optional[str] = None,
    ) -> RepositoryPlatform:
        """
        Create a platform instance based on repository URL.

        Args:
            url: Repository URL
            token: Optional explicit token

        Returns:
            Platform instance

        Raises:
            ConfigurationError: If platform cannot be created
        """
        platform_name = RepositoryTypeDetector.detect(url)

        # For self-hosted GitLab, extract instance URL
        instance_url = None
        if platform_name == "gitlab_self_hosted":
            try:
                _, _, instance_url = GitLabURLParser.parse(url, platform_name)
            except Exception:
                # If parsing fails, extract from URL manually
                from urllib.parse import urlparse

                parsed = urlparse(url)
                instance_url = f"{parsed.scheme}://{parsed.netloc}"

        credentials = self.credentials_manager.get_credentials(
            platform_name,
            token=token,
            instance_url=instance_url,
        )

        return self.registry.get_platform(platform_name, credentials)

    def create_platform(
        self,
        platform_name: str,
        token: Optional[str] = None,
        instance_url: Optional[str] = None,
    ) -> RepositoryPlatform:
        """
        Create a platform instance by explicit platform name.

        Args:
            platform_name: Name of the platform
            token: Optional explicit token
            instance_url: Optional instance URL for self-hosted

        Returns:
            Platform instance

        Raises:
            ConfigurationError: If platform cannot be created
        """
        credentials = self.credentials_manager.get_credentials(
            platform_name,
            token=token,
            instance_url=instance_url,
        )

        return self.registry.get_platform(platform_name, credentials)

    @property
    def available_platforms(self) -> list[str]:
        """Get list of supported platforms."""
        return self.registry.available_platforms
