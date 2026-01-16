"""Data Transfer Objects (DTOs) for core entities."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Repository:
    """Represents a repository across different platforms."""

    url: str
    platform: str  # "github", "gitlab", "gitlab_self_hosted"
    owner: str
    name: str
    instance_url: Optional[str] = None  # For self-hosted instances

    def __str__(self) -> str:
        return self.url

    @property
    def display_name(self) -> str:
        """Return owner/name format for display."""
        return f"{self.owner}/{self.name}"


@dataclass
class Credentials:
    """Represents authentication credentials for a platform."""

    platform: str  # "github", "gitlab"
    token: str
    instance_url: Optional[str] = None  # For self-hosted GitLab

    def __repr__(self) -> str:
        # Don't show the actual token in repr
        return f"Credentials(platform={self.platform}, token=***)"


@dataclass
class Issue:
    """Represents an issue created in a repository."""

    title: str
    body: str
    url: Optional[str] = None  # Set after successful creation
    repository_url: Optional[str] = None
    platform: Optional[str] = None
    created_at: Optional[str] = None

    @property
    def is_created(self) -> bool:
        """Check if the issue was successfully created."""
        return self.url is not None
