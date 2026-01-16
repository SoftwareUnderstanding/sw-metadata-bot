from .github_api import set_github_api
from .repo_api import RepoAPI
from .repo_utils import RepoType


def setup_api(repo_type: RepoType, dry_run: bool) -> RepoAPI:
    if repo_type == RepoType.GITHUB:
        return set_github_api(dry_run)
    else:
        raise NotImplementedError(
            f"API setup not implemented for repo type: {repo_type}"
        )


def create_issue(api: RepoAPI, repo_url: str, title: str, content_report: str) -> str:
    response = api.create_issue(
        repo_url=repo_url,
        title=title,
        body=content_report,
    )
    # store issue url
    issue_url = response.get("html_url", "No URL returned")
    return issue_url
