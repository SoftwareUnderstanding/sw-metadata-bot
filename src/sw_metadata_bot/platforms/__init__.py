"""Platforms module initialization and registry."""

from .base import RepositoryPlatform
from .github import GitHubAPI
from .gitlab import GitLabAPI

__all__ = ["RepositoryPlatform", "GitHubAPI", "GitLabAPI"]
