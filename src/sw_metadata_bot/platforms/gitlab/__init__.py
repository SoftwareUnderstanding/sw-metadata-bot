"""GitLab platform module initialization."""

from .client import GitLabAPI, GitLabURLParser

__all__ = ["GitLabAPI", "GitLabURLParser"]
