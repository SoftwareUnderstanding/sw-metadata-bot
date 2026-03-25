"""Repository head commit lookup utilities."""

import re
import subprocess
from urllib.parse import quote, urlparse

import requests


def parse_github_repo(repo_url: str) -> tuple[str, str] | None:
    """Parse owner/repo from a GitHub repository URL."""
    match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", repo_url, re.IGNORECASE)
    if match is None:
        return None
    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    return owner, repo


def resolve_gitlab_project_path(repo_url: str) -> tuple[str, str] | None:
    """Parse host and project path for GitLab repositories."""
    parsed = urlparse(repo_url)
    host = parsed.netloc
    if not host or "gitlab" not in host.lower():
        return None

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None

    parts[-1] = parts[-1].removesuffix(".git")
    project_path = "/".join(parts)
    if not project_path:
        return None
    return host, project_path


def is_commit_hash(value: str) -> bool:
    """Return True if value looks like a commit hash."""
    return bool(re.fullmatch(r"[0-9a-fA-F]{7,64}", value.strip()))


def get_github_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit from GitHub API."""
    parsed = parse_github_repo(repo_url)
    if parsed is None:
        return None

    owner, repo = parsed
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    response = requests.get(url, params={"per_page": 1}, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not data:
        return None

    first = data[0]
    if not isinstance(first, dict):
        return None
    sha = first.get("sha")
    if not isinstance(sha, str) or not sha:
        return None
    return sha if is_commit_hash(sha) else None


def get_gitlab_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit from GitLab API for gitlab* hosts."""
    parsed = resolve_gitlab_project_path(repo_url)
    if parsed is None:
        return None

    host, project_path = parsed
    encoded_project = quote(project_path, safe="")
    url = f"https://{host}/api/v4/projects/{encoded_project}/repository/commits"
    response = requests.get(url, params={"per_page": 1}, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not data:
        return None

    first = data[0]
    if not isinstance(first, dict):
        return None

    commit_id = first.get("id")
    if not isinstance(commit_id, str) or not commit_id:
        return None
    return commit_id if is_commit_hash(commit_id) else None


def get_generic_git_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit via git ls-remote as generic fallback."""
    result = subprocess.run(
        ["git", "ls-remote", repo_url, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        return None

    first_line = result.stdout.strip().splitlines()
    if not first_line:
        return None

    first_field = first_line[0].split()[0] if first_line[0].split() else ""
    if not first_field:
        return None
    return first_field if is_commit_hash(first_field) else None


def get_repo_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit using API-first and git fallback strategies."""
    resolvers = (
        get_github_head_commit,
        get_gitlab_head_commit,
        get_generic_git_head_commit,
    )
    for resolver in resolvers:
        try:
            commit_id = resolver(repo_url)
        except Exception:
            commit_id = None
        if isinstance(commit_id, str) and commit_id:
            return commit_id
    return None
