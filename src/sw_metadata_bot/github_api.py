"""GitHub API client."""

from typing import Any
from urllib.parse import ParseResult, urlparse

import requests

from .platform_api import IssueAPIBase
from .token_resolver import resolve_token


class GitHubAPI(IssueAPIBase):
    """Simple GitHub API client."""

    def __init__(self, token: str | None = None, dry_run: bool = False):
        """Initialize GitHub API client."""
        self.token = resolve_token(
            explicit_token=token,
            env_var_name="GITHUB_API_TOKEN",
            dry_run=dry_run,
        )
        self.dry_run = dry_run
        self.base_url = "https://api.github.com"

    @staticmethod
    def parse_repo_url(url: str) -> tuple[str, str]:
        """
        Parse GitHub URL to extract owner and repo.

        Returns:
            Tuple of (owner, repo_name)
        """
        parsed = urlparse(url)
        if parsed.netloc != "github.com":
            raise ValueError(f"Not a GitHub URL: {url}")

        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid GitHub URL format: {url}")

        owner, repo = parts[0], parts[1].removesuffix(".git")
        return owner, repo

    def check_auth(self) -> bool:
        """Check whether authentication works."""
        if self.dry_run:
            return True

        try:
            response = requests.get(
                f"{self.base_url}/user",
                headers={"Authorization": f"token {self.token}"},
                timeout=10,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"GitHub auth failed: {e}")
            return False

    def verify_auth(self) -> dict:
        """
        Verify authentication and return detailed information.

        Returns:
            Dictionary with authentication details including user, scopes, and permissions.
        """
        result = {
            "platform": "GitHub",
            "token_set": bool(self.token),
            "authenticated": False,
            "has_issues_permission": False,
            "has_contents_permission": False,
            "user": None,
            "scopes": [],
            "errors": [],
        }

        if not self.token:
            result["errors"].append("GitHub token not set")
            return result

        if self.dry_run:
            result["authenticated"] = True
            result["user"] = "dry-run-mode"
            result["has_issues_permission"] = True
            result["has_contents_permission"] = True
            return result

        try:
            response = requests.get(
                f"{self.base_url}/user",
                headers={"Authorization": f"token {self.token}"},
                timeout=10,
            )

            if response.status_code == 401:
                result["errors"].append("Invalid token (401 Unauthorized)")
                return result

            if response.status_code == 403:
                result["errors"].append("Token forbidden (403 Forbidden)")
                return result

            response.raise_for_status()

            result["authenticated"] = True
            user_data = response.json()
            result["user"] = user_data.get("login")

            # Check token permissions via X-OAuth-Scopes header
            scopes = response.headers.get("X-OAuth-Scopes", "").split(", ")
            scopes = [s.strip() for s in scopes if s.strip()]
            result["scopes"] = scopes

            # Check for required permissions
            if "repo" in scopes or "public_repo" in scopes:
                result["has_issues_permission"] = True
                result["has_contents_permission"] = True
            else:
                # Check individual scopes
                if "issues" in scopes or "write:issues" in scopes:
                    result["has_issues_permission"] = True
                if "read:repo_hook" in scopes or "repo" in scopes:
                    result["has_contents_permission"] = True

        except Exception as e:
            result["errors"].append(f"Error verifying GitHub token: {str(e)}")

        return result

    def create_issue(self, repo_url: str, title: str, body: str) -> str:
        """
        Create an issue on GitHub.

        Returns:
            URL of created issue (or fake URL in dry-run mode)
        """
        owner, repo = self.parse_repo_url(repo_url)

        if self.dry_run:
            return f"https://github.com/{owner}/{repo}/issues/0"

        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        data = {"title": title, "body": body}
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        response = requests.post(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()

        return response.json()["html_url"]

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with optional auth token."""
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def _issue_api_url(self, issue_url: str) -> str:
        """Build API URL for a GitHub issue."""
        owner, repo, issue_number = self.parse_issue_url(issue_url)
        return f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"

    def _issue_comments_api_url(self, issue_url: str) -> str:
        """Build API URL for GitHub issue comments."""
        owner, repo, issue_number = self.parse_issue_url(issue_url)
        return f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"

    def _dry_run_issue_fallback(self, issue_url: str) -> dict[str, Any]:
        """Return fallback issue payload for dry-run mode."""
        owner, repo, issue_number = self.parse_issue_url(issue_url)
        return {
            "state": "open",
            "html_url": issue_url,
            "number": issue_number,
            "repository_url": f"https://github.com/{owner}/{repo}",
        }

    def _close_issue_request(self, issue_url: str) -> tuple[str, str, dict[str, str]]:
        """Return HTTP request shape for closing a GitHub issue."""
        return "PATCH", self._issue_api_url(issue_url), {"state": "closed"}

    def _comment_body_from_item(self, item: dict[str, Any]) -> str:
        """Extract comment body from one GitHub comment payload."""
        return str(item.get("body", ""))

    @staticmethod
    def parse_issue_url(issue_url: str) -> tuple[str, str, int]:
        """Parse a GitHub issue URL and return owner/repo/number."""
        parsed: ParseResult = urlparse(issue_url)
        if parsed.netloc != "github.com":
            raise ValueError(f"Not a GitHub issue URL: {issue_url}")

        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4 or parts[2] != "issues":
            raise ValueError(f"Invalid GitHub issue URL format: {issue_url}")

        owner, repo = parts[0], parts[1].removesuffix(".git")
        issue_number = int(parts[3])
        return owner, repo, issue_number
