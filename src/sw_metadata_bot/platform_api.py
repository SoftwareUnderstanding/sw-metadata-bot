"""Shared issue API behaviors for GitHub and GitLab clients.

This module centralizes common API operations used by platform-specific clients:
- reading issues
- reading issue comments
- posting comments
- closing issues

Platform-specific clients remain responsible for URL parsing, endpoint
construction, auth headers, and dry-run fallback payloads.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import requests


class IssueAPIBase(ABC):
    """Common issue lifecycle operations shared by platform API clients."""

    dry_run: bool

    @abstractmethod
    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers, including auth details where needed."""

    @abstractmethod
    def _issue_api_url(self, issue_url: str) -> str:
        """Return platform API endpoint URL for a specific issue."""

    @abstractmethod
    def _issue_comments_api_url(self, issue_url: str) -> str:
        """Return platform API endpoint URL for issue comments/notes."""

    @abstractmethod
    def _dry_run_issue_fallback(self, issue_url: str) -> dict[str, Any]:
        """Return fallback issue payload when dry-run fetch fails."""

    @abstractmethod
    def _close_issue_request(self, issue_url: str) -> tuple[str, str, dict[str, str]]:
        """Return close request tuple: (method, url, payload)."""

    @abstractmethod
    def _comment_body_from_item(self, item: dict[str, Any]) -> str:
        """Extract comment text field from one API list item."""

    def get_issue(self, issue_url: str) -> dict[str, Any]:
        """Fetch issue details from the platform API."""
        url = self._issue_api_url(issue_url)
        headers = self._build_headers()

        if self.dry_run:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                return (
                    data
                    if isinstance(data, dict)
                    else self._dry_run_issue_fallback(issue_url)
                )
            except Exception:
                return self._dry_run_issue_fallback(issue_url)

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Issue API response must be a JSON object")
        return data

    def get_issue_comments(self, issue_url: str) -> list[str]:
        """Fetch issue comments/notes and return text bodies."""
        url = self._issue_comments_api_url(issue_url)
        headers = self._build_headers()

        if self.dry_run:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, list):
                    return []
                return [
                    self._comment_body_from_item(item)
                    for item in data
                    if isinstance(item, dict)
                ]
            except Exception:
                return []

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return []
        return [
            self._comment_body_from_item(item)
            for item in data
            if isinstance(item, dict)
        ]

    def add_issue_comment(self, issue_url: str, body: str) -> None:
        """Add a comment to an issue."""
        if self.dry_run:
            return

        url = self._issue_comments_api_url(issue_url)
        headers = self._build_headers()
        response = requests.post(url, json={"body": body}, headers=headers, timeout=10)
        response.raise_for_status()

    def close_issue(self, issue_url: str) -> None:
        """Close an existing issue."""
        if self.dry_run:
            return

        method, url, payload = self._close_issue_request(issue_url)
        headers = self._build_headers()

        if method.upper() == "PATCH":
            response = requests.patch(url, json=payload, headers=headers, timeout=10)
        elif method.upper() == "PUT":
            response = requests.put(url, json=payload, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unsupported close issue method: {method}")

        response.raise_for_status()
