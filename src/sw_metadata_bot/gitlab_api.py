"""GitLab API client."""

from urllib.parse import urlparse

import requests

from .token_resolver import resolve_token


class GitLabAPI:
    """Simple GitLab API client."""

    def __init__(self, token: str | None = None, dry_run: bool = False):
        """Initialize GitLab API client."""
        self.token = resolve_token(
            explicit_token=token,
            env_var_name="GITLAB_API_TOKEN",
            dry_run=dry_run,
        )
        self.dry_run = dry_run

    @staticmethod
    def parse_url(url: str) -> tuple[str, str, str]:
        """
        Parse GitLab URL to extract host, owner, and repo.

        Returns:
            Tuple of (host, owner, repo_name)
        """
        parsed = urlparse(url)
        host = parsed.netloc

        if not host or "gitlab" not in host.lower():
            raise ValueError(f"Not a GitLab URL: {url}")

        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid GitLab URL format: {url}")

        owner, repo = parts[0], parts[1].removesuffix(".git")
        return host, owner, repo

    def get_base_url(self, host: str) -> str:
        """Get API base URL for GitLab host."""
        return f"https://{host}/api/v4"

    def test_auth(self, host: str = "gitlab.com") -> bool:
        """Test if authentication works."""
        if self.dry_run:
            return True

        try:
            base_url = self.get_base_url(host)
            response = requests.get(
                f"{base_url}/user",
                headers={"PRIVATE-TOKEN": self.token},
                timeout=10,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"GitLab auth failed: {e}")
            return False

    def verify_auth(self, host: str = "gitlab.com") -> dict:
        """
        Verify authentication and return detailed information.

        Returns:
            Dictionary with authentication details including user, scopes, and permissions.
        """
        result = {
            "platform": "GitLab",
            "host": host,
            "token_set": bool(self.token),
            "authenticated": False,
            "has_issues_permission": False,
            "has_contents_permission": False,
            "user": None,
            "scopes": [],
            "errors": [],
        }

        if not self.token:
            result["errors"].append("GitLab token not set")
            return result

        if self.dry_run:
            result["authenticated"] = True
            result["user"] = "dry-run-mode"
            result["has_issues_permission"] = True
            result["has_contents_permission"] = True
            return result

        try:
            base_url = self.get_base_url(host)

            # Test basic authentication
            response = requests.get(
                f"{base_url}/user",
                headers={"PRIVATE-TOKEN": self.token},
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
            result["user"] = user_data.get("username")

            # GitLab doesn't expose token scopes via API like GitHub does
            # Instead, we test specific permissions by making test API calls

            # Test read_repository permission (can list user projects)
            try:
                test_response = requests.get(
                    f"{base_url}/projects",
                    headers={"PRIVATE-TOKEN": self.token},
                    params={"membership": "true", "per_page": 1},
                    timeout=10,
                )
                if test_response.status_code == 200:
                    result["has_contents_permission"] = True
            except Exception:
                pass

            # Test api/write permission (can we access issues endpoint)
            # Note: We can't actually test write without creating an issue
            # But read access to issues endpoint suggests api scope
            try:
                test_response = requests.get(
                    f"{base_url}/issues",
                    headers={"PRIVATE-TOKEN": self.token},
                    params={"scope": "assigned_to_me", "per_page": 1},
                    timeout=10,
                )
                if test_response.status_code == 200:
                    result["has_issues_permission"] = True
            except Exception:
                pass

            # Add note about GitLab scope detection
            if not result["scopes"]:
                result["scopes"] = ["(GitLab doesn't expose token scopes via API)"]
                if result["has_contents_permission"]:
                    result["scopes"].append("✓ can read repositories")
                if result["has_issues_permission"]:
                    result["scopes"].append("✓ can access issues")

        except Exception as e:
            result["errors"].append(f"Error verifying GitLab token: {str(e)}")

        return result

    def create_issue(self, repo_url: str, title: str, body: str) -> str:
        """
        Create an issue on GitLab.

        Returns:
            URL of created issue (or fake URL in dry-run mode)
        """
        host, owner, repo = self.parse_url(repo_url)
        project_id = f"{owner}/{repo}"

        if self.dry_run:
            return f"https://{host}/{owner}/{repo}/-/issues/0"

        base_url = self.get_base_url(host)
        url = f"{base_url}/projects/{requests.utils.quote(project_id, safe='')}/issues"
        data = {"title": title, "description": body}
        headers = {"PRIVATE-TOKEN": self.token}

        response = requests.post(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()

        return response.json()["web_url"]

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with optional private token."""
        headers: dict[str, str] = {}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        return headers

    @staticmethod
    def parse_issue_url(issue_url: str) -> tuple[str, str, str, int]:
        """Parse a GitLab issue URL and return host/owner/repo/iid."""
        parsed = urlparse(issue_url)
        host = parsed.netloc
        if not host:
            raise ValueError(f"Invalid GitLab issue URL: {issue_url}")

        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4:
            raise ValueError(f"Invalid GitLab issue URL format: {issue_url}")

        owner = parts[0]
        repo = parts[1].removesuffix(".git")
        issue_number_str = ""

        if len(parts) >= 5 and parts[2] == "-" and parts[3] == "issues":
            issue_number_str = parts[4]
        elif parts[2] == "issues":
            issue_number_str = parts[3]
        else:
            raise ValueError(f"Invalid GitLab issue URL format: {issue_url}")

        return host, owner, repo, int(issue_number_str)

    def get_issue(self, issue_url: str) -> dict:
        """Fetch issue details from GitLab."""
        host, owner, repo, issue_iid = self.parse_issue_url(issue_url)

        base_url = self.get_base_url(host)
        project_id = requests.utils.quote(f"{owner}/{repo}", safe="")
        url = f"{base_url}/projects/{project_id}/issues/{issue_iid}"
        headers = self._build_headers()
        if self.dry_run:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                return response.json()
            except Exception:
                return {
                    "state": "opened",
                    "web_url": issue_url,
                    "iid": issue_iid,
                    "project": f"{owner}/{repo}",
                }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_issue_comments(self, issue_url: str) -> list[str]:
        """Fetch issue comments and return note bodies."""
        host, owner, repo, issue_iid = self.parse_issue_url(issue_url)

        base_url = self.get_base_url(host)
        project_id = requests.utils.quote(f"{owner}/{repo}", safe="")
        url = f"{base_url}/projects/{project_id}/issues/{issue_iid}/notes"
        headers = self._build_headers()
        if self.dry_run:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                return [
                    str(item.get("body", "")) for item in data if isinstance(item, dict)
                ]
            except Exception:
                return []

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return [str(item.get("body", "")) for item in data if isinstance(item, dict)]

    def add_issue_comment(self, issue_url: str, body: str) -> None:
        """Add a comment to an issue."""
        if self.dry_run:
            return

        host, owner, repo, issue_iid = self.parse_issue_url(issue_url)
        base_url = self.get_base_url(host)
        project_id = requests.utils.quote(f"{owner}/{repo}", safe="")
        url = f"{base_url}/projects/{project_id}/issues/{issue_iid}/notes"
        headers = {"PRIVATE-TOKEN": self.token}
        response = requests.post(url, json={"body": body}, headers=headers, timeout=10)
        response.raise_for_status()

    def close_issue(self, issue_url: str) -> None:
        """Close an existing issue."""
        if self.dry_run:
            return

        host, owner, repo, issue_iid = self.parse_issue_url(issue_url)
        base_url = self.get_base_url(host)
        project_id = requests.utils.quote(f"{owner}/{repo}", safe="")
        url = f"{base_url}/projects/{project_id}/issues/{issue_iid}"
        headers = {"PRIVATE-TOKEN": self.token}
        response = requests.put(
            url,
            json={"state_event": "close"},
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
