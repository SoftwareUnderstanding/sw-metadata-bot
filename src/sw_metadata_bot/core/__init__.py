"""Core module initialization."""

from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    IssueCreationError,
    PitfallsParsingError,
    PlatformNotSupportedError,
    RepositoryError,
    URLParsingError,
)
from .pitfalls_analyzer import PitfallsAnalyzer
from .repository import Credentials, Issue, Repository

__all__ = [
    "Repository",
    "Credentials",
    "Issue",
    "PitfallsAnalyzer",
    "RepositoryError",
    "URLParsingError",
    "AuthenticationError",
    "IssueCreationError",
    "PlatformNotSupportedError",
    "ConfigurationError",
    "PitfallsParsingError",
]
