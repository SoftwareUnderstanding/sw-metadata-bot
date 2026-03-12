"""Helpers for the unified community configuration file."""

import json
from datetime import datetime, timezone
from pathlib import Path

import click

DEFAULT_OUTPUT_ROOT = Path("outputs")
DEFAULT_SNAPSHOT_TAG_FORMAT = "%Y%m%d"
PROJECT_ROOT_MARKERS = ("pyproject.toml", ".git")


def _normalize_repo_url(url: str) -> str:
    """Normalize repository URLs for matching and persistence."""
    return url.strip().rstrip("/")


def load_community_config(config_path: Path) -> dict:
    """Load and validate a unified community configuration file."""
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise click.ClickException(
            f"Invalid format in {config_path}: top-level JSON value must be an object"
        )

    repositories = data.get("repositories")
    if not isinstance(repositories, list):
        raise click.ClickException(
            f"Invalid format in {config_path}: 'repositories' must be a list"
        )

    return data


def get_repositories(config: dict) -> list[str]:
    """Return normalized repositories preserving order and uniqueness."""
    repositories = config.get("repositories", [])
    if not isinstance(repositories, list):
        raise click.ClickException(
            "Invalid community config: 'repositories' must be a list"
        )

    seen: set[str] = set()
    ordered: list[str] = []
    for item in repositories:
        if not isinstance(item, str):
            continue
        normalized = _normalize_repo_url(item)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def get_custom_message(config: dict) -> str | None:
    """Return the configured issue custom message if present."""
    issues = config.get("issues", {})
    if not isinstance(issues, dict):
        raise click.ClickException(
            "Invalid community config: 'issues' must be an object"
        )

    custom_message = issues.get("custom_message")
    if custom_message is None:
        return None
    if not isinstance(custom_message, str):
        raise click.ClickException(
            "Invalid community config: 'issues.custom_message' must be a string"
        )
    return custom_message


def get_opt_out_repositories(config: dict) -> set[str]:
    """Return normalized repository URLs configured as inline opt-outs."""
    issues = config.get("issues", {})
    if not isinstance(issues, dict):
        raise click.ClickException(
            "Invalid community config: 'issues' must be an object"
        )

    opt_outs = issues.get("opt_outs", [])
    if not isinstance(opt_outs, list):
        raise click.ClickException(
            "Invalid community config: 'issues.opt_outs' must be a list"
        )

    return {_normalize_repo_url(url) for url in opt_outs if isinstance(url, str)}


def append_opt_out_repository(config_path: Path, repo_url: str) -> bool:
    """Persist a repository to the inline opt-outs list when not already present."""
    data = load_community_config(config_path)
    issues = data.setdefault("issues", {})
    if not isinstance(issues, dict):
        raise click.ClickException(
            "Invalid community config: 'issues' must be an object"
        )

    opt_outs = issues.setdefault("opt_outs", [])
    if not isinstance(opt_outs, list):
        raise click.ClickException(
            "Invalid community config: 'issues.opt_outs' must be a list"
        )

    normalized_repo = _normalize_repo_url(repo_url)
    normalized_existing = {
        _normalize_repo_url(url) for url in opt_outs if isinstance(url, str)
    }
    if normalized_repo in normalized_existing:
        return False

    opt_outs.append(normalized_repo)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True


def _find_project_root(config_path: Path) -> Path:
    """Return the nearest ancestor that looks like the project root."""
    resolved_config_path = config_path.resolve()
    for candidate in (resolved_config_path.parent, *resolved_config_path.parents):
        if any((candidate / marker).exists() for marker in PROJECT_ROOT_MARKERS):
            return candidate
    return Path.cwd().resolve()


def resolve_output_root(config: dict, config_path: Path) -> Path:
    """Return the configured output root, resolving relative paths from project root."""
    outputs = config.get("outputs", {})
    if not isinstance(outputs, dict):
        raise click.ClickException(
            "Invalid community config: 'outputs' must be an object"
        )

    root_dir = outputs.get("root_dir", str(DEFAULT_OUTPUT_ROOT))
    if not isinstance(root_dir, str) or not root_dir.strip():
        raise click.ClickException(
            "Invalid community config: 'outputs.root_dir' must be a non-empty string"
        )

    root_path = Path(root_dir)
    if not root_path.is_absolute():
        root_path = _find_project_root(config_path) / root_path
    return root_path


def resolve_run_name(config: dict, config_path: Path) -> str:
    """Return the configured run name or a sensible default."""
    outputs = config.get("outputs", {})
    if not isinstance(outputs, dict):
        raise click.ClickException(
            "Invalid community config: 'outputs' must be an object"
        )

    run_name = outputs.get("run_name")
    if run_name is not None:
        if not isinstance(run_name, str) or not run_name.strip():
            raise click.ClickException(
                "Invalid community config: 'outputs.run_name' must be a non-empty string"
            )
        return run_name

    community = config.get("community", {})
    if community is not None and not isinstance(community, dict):
        raise click.ClickException(
            "Invalid community config: 'community' must be an object"
        )

    community_name = community.get("name") if isinstance(community, dict) else None
    if isinstance(community_name, str) and community_name.strip():
        return community_name

    return config_path.stem


def resolve_snapshot_tag(
    config: dict,
    explicit_snapshot_tag: str | None,
) -> str | None:
    """Resolve the snapshot tag from CLI override or config defaults."""
    if explicit_snapshot_tag is not None:
        return explicit_snapshot_tag

    outputs = config.get("outputs", {})
    if not isinstance(outputs, dict):
        raise click.ClickException(
            "Invalid community config: 'outputs' must be an object"
        )

    snapshot_tag_format = outputs.get(
        "snapshot_tag_format", DEFAULT_SNAPSHOT_TAG_FORMAT
    )
    if snapshot_tag_format is None:
        return None
    if not isinstance(snapshot_tag_format, str) or not snapshot_tag_format.strip():
        raise click.ClickException(
            "Invalid community config: 'outputs.snapshot_tag_format' must be a string or null"
        )

    return datetime.now(timezone.utc).strftime(snapshot_tag_format)
