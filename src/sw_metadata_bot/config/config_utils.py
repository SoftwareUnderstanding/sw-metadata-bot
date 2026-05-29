"""Helpers for the unified configuration file."""

from pathlib import Path

import click

from sw_metadata_bot.config.schemas import BotConfig

from .. import constants


def normalize_repo_url(url: str) -> str:
    """Normalize repository URLs for matching and persistence."""
    return url.strip().rstrip("/")


def detect_platform(url: str) -> str | None:
    """Detect publishing platform from repository URL.

    Returns ``"github"`` for GitHub URLs, ``"gitlab"`` for any GitLab URL,
    or ``None`` when the URL does not match a known platform.
    """
    lowered = url.lower()
    if "github.com" in lowered:
        return "github"
    if "gitlab" in lowered:
        return "gitlab"
    return None


def sanitize_repo_name(repo_url: str) -> str:
    """Sanitize repository URL to a safe folder name format.

    Uses a generic URL-safe transformation so non-standard URLs still map to
    deterministic folder names.

    Args:
        repo_url: Repository URL or identifier string

    Returns:
        Sanitized folder name (lowercase, underscores only)
    """
    import re

    normalized = normalize_repo_url(repo_url)
    no_scheme = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", normalized)
    no_git_suffix = re.sub(r"\.git$", "", no_scheme, flags=re.IGNORECASE)
    sanitized = re.sub(r"[./-]", "_", no_git_suffix)
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", sanitized)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_").lower()

    if not sanitized:
        raise click.ClickException(f"Unable to sanitize repository URL: {repo_url}")

    return sanitized


def _find_project_root(config_path: Path) -> Path:
    """Return the nearest ancestor that looks like the project root.
    This expects the config file to be located somewhere within the project directory structure, and looks for common project root markers (e.g., .git, pyproject.toml) in the config file's parent directories. If no markers are found, it defaults to the current working directory."""
    resolved_config_path = config_path.resolve()
    for candidate in (resolved_config_path.parent, *resolved_config_path.parents):
        if any(
            (candidate / marker).exists() for marker in constants.PROJECT_ROOT_MARKERS
        ):
            return candidate
    return Path.cwd().resolve()


def resolve_output_root(output_root_dir: str, config_path: Path) -> Path:
    """Return the configured output root, resolving relative paths from project root."""
    root_path = Path(output_root_dir)
    if not root_path.is_absolute():
        root_path = _find_project_root(config_path) / root_path
    return root_path


def resolve_run_name(run_name: str | None, config_path: Path) -> str:
    """Return the configured run name or a sensible default.
    If run_name is provided in the config, it is used directly. Otherwise, the default is derived from the config file name (without extension).
    """
    if run_name is not None:
        if not isinstance(run_name, str) or not run_name.strip():
            raise click.ClickException(
                "Invalid config: 'outputs.run_name' must be a non-empty string"
            )
        return run_name

    return config_path.stem


def append_opt_out_to_config(config_file: Path, repo_url: str, explicit: bool) -> None:
    """Helper to append a repository URL to the config's opt-out list from file."""
    normalized_url = normalize_repo_url(repo_url)

    config = BotConfig.from_json(config_file)
    is_new_repo_added = config.add_opt_out_repository(normalized_url)
    if is_new_repo_added:
        config.to_json(config_file, explicit=explicit)
