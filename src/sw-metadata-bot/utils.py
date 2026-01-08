from ..repo_utils import RepoType
from .github_api import GitHubAPI
from .repo_api import RepoAPI


def setup_api(repo_type: RepoType, dry_run: bool) -> RepoAPI:
    if repo_type == RepoType.GITHUB:
        import os

        from dotenv import load_dotenv

        load_dotenv()
        token = os.getenv("GITHUB_API_TOKEN")
        if not token:
            raise ValueError("GITHUB_API_TOKEN not found in environment variables")

        api = GitHubAPI(token=token, dry_run=dry_run)

        api.test_authentication()
        return api
    else:
        raise NotImplementedError(f"API setup not implemented for repo type: {repo_type}")


def create_issue(api: RepoAPI, repo_url: str, content_report: str) -> str:
    response = api.create_issue(
        repo_url=repo_url,
        title="[OSSR RS Quality Checks] Automated Analysis Report",
        body=content_report,
    )
    # store issue url
    issue_url = response.get("html_url", "No URL returned")
    return issue_url
