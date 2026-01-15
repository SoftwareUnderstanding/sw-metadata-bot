from urllib.parse import urlparse

import requests

from .repo_api import RepoAPI


def parse_github_url(repo_url: str) -> tuple[str, str]:
    """
    Parse a GitHub repository URL to extract owner and repository name.

    Args:
        repo_url: GitHub repository URL (e.g., "https://github.com/owner/repo")

    Returns:
        Tuple of (owner, repo_name)

    Raises:
        ValueError: If the URL is not a valid GitHub repository URL
    """
    parsed = urlparse(repo_url)

    if parsed.netloc != "github.com":
        raise ValueError(f"Not a GitHub URL: {repo_url}")

    # Remove leading slash and split path
    path_parts = parsed.path.strip("/").split("/")

    if len(path_parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    owner = path_parts[0]
    repo = path_parts[1]

    # Remove .git suffix if present
    if repo.endswith(".git"):
        repo = repo[:-4]

    return owner, repo


class GitHubAPI(RepoAPI):
    def __init__(self, token: str = "", dry_run: bool = False) -> None:
        super().__init__(token, dry_run)
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def test_authentication(self):
        """Test if the token is valid."""
        url = "https://api.github.com/user"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            user = response.json()
            print(f"Authenticated as: {user['login']}")
            return True
        else:
            print(f"Authentication failed: {response.status_code}")
            print(response.json())
            return False

    @staticmethod
    def get_repo_info(repo_url: str) -> str:
        # Implementation for fetching repository info from GitHub
        owner, repo = parse_github_url(repo_url)
        url = f"https://api.github.com/repos/{owner}/{repo}"
        return url

    def create_issue(self, repo_url: str, title: str, body: str) -> dict:
        url = GitHubAPI.get_repo_info(repo_url)
        issues_url = f"{url}/issues"
        print(f"Creating issue at {issues_url}")

        # Implementation for creating an issue on GitHub
        full_body = body
        labels = ["bot"]
        data = {
            "title": title,
            "body": full_body,
            "labels": labels,
        }

        if self.dry_run:
            print(f"[DRY RUN] Would create issue with title: {title}")
            return {
                "title": title,
                "body": full_body,
                "labels": labels,
                "html_url": f"{issues_url}/dry-run-issue",
            }

        # if no dry run, proceed to create the issue
        response = requests.post(issues_url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()

    # def create_pull_request(
    #     self, repo_url: str, title: str, body: str, head: str, base: str
    # ) -> dict:
    #     # Implementation for creating a pull request on GitHub
    #     pass


def set_github_api(dry_run: bool) -> GitHubAPI:
    import os

    from dotenv import load_dotenv

    load_dotenv()
    token = os.getenv("GITHUB_API_TOKEN")
    if not token:
        raise ValueError("GITHUB_API_TOKEN not found in environment variables")

    api = GitHubAPI(token=token, dry_run=dry_run)

    if not api.test_authentication():
        raise ValueError("Invalid GitHub API token")
    return api


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    token = os.getenv("GITHUB_API_TOKEN")
    if not token:
        raise ValueError("GITHUB_API_TOKEN not found in environment variables")

    api = GitHubAPI(token=token, dry_run=False)

    api.test_authentication()

    EXAMPLE_REPO_URL = "https://github.com/francoto/indicators"

    try:
        result = api.create_issue(
            EXAMPLE_REPO_URL,
            "Test Issue",
            "This is a test issue created via the GitHub API.",
        )
        print(f"Issue created successfully: {result['html_url']}")
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error: {e}")
        print(f"Error: {e}")
