from enum import Enum


class RepoType(Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    GITLAB_SELF_HOSTED = "self-hosted gitlab"
    BITBUCKET = "bitbucket"
    UNKNOWN = "unknown"


def get_repo_type(repo: str) -> RepoType:
    """
    Determine the type of repository based on its URL.

    Parameters
    ----------
    repo : str
        The URL of the repository.

    Returns
    -------
    RepoType
        The type of the repository. Possible values are:
        - RepoType.GITHUB for GitHub repositories
        - RepoType.GITLAB for GitLab repositories
        - RepoType.GITLAB_SELF_HOSTED for self-hosted GitLab repositories
        - RepoType.BITBUCKET for Bitbucket repositories
        - RepoType.UNKNOWN if the repository type cannot be determined
    """
    repo_mapping = {
        "github.com": RepoType.GITHUB,
        "gitlab.com": RepoType.GITLAB,
        "bitbucket.org": RepoType.BITBUCKET,
        "git.astron.nl": RepoType.GITLAB_SELF_HOSTED,
        "git.ligo.org": RepoType.GITLAB_SELF_HOSTED,
    }

    for key, repo_type in repo_mapping.items():
        if key in repo:
            return repo_type

    if "gitlab" in repo and "gitlab.com" not in repo:
        return RepoType.GITLAB_SELF_HOSTED

    return RepoType.UNKNOWN


def format_repo_url(repo_url: str) -> str:
    """
    Format the repository URL to a standard format.

    Parameters
    ----------
    repo_url : str
        The repository URL to format.

    Returns
    -------
    str
        The formatted repository URL.
    """
    if repo_url.startswith("+git") or repo_url.startswith("git+"):
        repo_url = repo_url[4:]
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    return repo_url
