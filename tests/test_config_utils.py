"""Tests for configuration and platform handling."""

import json

import click
import pytest

from sw_metadata_bot.config_utils import (
    append_opt_out_repository,
    build_explicit_config,
    detect_platform,
    export_config,
    load_config,
    validate_config,
)


def test_detect_platform_github():
    """Return 'github' for GitHub URLs."""
    assert detect_platform("https://github.com/org/repo") == "github"


def test_detect_platform_gitlab_dot_com():
    """Return 'gitlab' for GitLab.com URLs."""
    assert detect_platform("https://gitlab.com/group/repo") == "gitlab"


def test_detect_platform_self_hosted_gitlab():
    """Return 'gitlab' for self-hosted GitLab instances."""
    assert detect_platform("https://gitlab.example.org/group/repo") == "gitlab"


def test_detect_platform_unsupported():
    """Return None for URLs that do not match a known platform."""
    assert detect_platform("https://example.org/org/repo") is None


def test_load_config_validates_repositories(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"issues": {}}), encoding="utf-8")

    with pytest.raises(click.ClickException, match="repositories"):
        load_config(config_path)


def test_validate_config_allows_minimal_config(tmp_path):
    config = {"repositories": ["https://github.com/org/repo"]}
    validate_config(config)


def test_build_explicit_config_adds_defaults(tmp_path):
    config = {"repositories": ["https://github.com/org/repo"]}
    explicit = build_explicit_config(config, tmp_path / "config.json")

    assert explicit == {
        "repositories": ["https://github.com/org/repo"],
        "issues": {
            "custom_message": None,
            "generate_codemeta_if_missing": True,
            "opt_outs": [],
        },
        "outputs": {
            "root_dir": "outputs",
            "run_name": "config",
            "snapshot_tag_format": "%Y%m%d",
        },
    }


def test_export_config_defined_only(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"repositories": ["https://github.com/org/repo"]}), encoding="utf-8"
    )

    exported = export_config(config_path, explicit=False)
    assert exported == {"repositories": ["https://github.com/org/repo"]}


def test_export_config_writes_explicit_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"repositories": ["https://github.com/org/repo"]}), encoding="utf-8"
    )
    output_path = tmp_path / "exported.json"

    exported = export_config(config_path, explicit=True, output_path=output_path)
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == exported


def test_append_opt_out_repository_adds_repo_without_altering_other_fields(tmp_path):
    config_path = tmp_path / "config.json"
    config = {
        "repositories": ["https://github.com/org/repo"],
        "issues": {"custom_message": "hello"},
        "outputs": {"root_dir": "outputs"},
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    appended = append_opt_out_repository(config_path, "https://github.com/org/repo")
    assert appended is True

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert updated["issues"]["opt_outs"] == ["https://github.com/org/repo"]
    assert updated["issues"]["custom_message"] == "hello"
    assert updated["outputs"] == {"root_dir": "outputs"}


def test_append_opt_out_repository_is_idempotent(tmp_path):
    config_path = tmp_path / "config.json"
    config = {
        "repositories": ["https://github.com/org/repo"],
        "issues": {"opt_outs": ["https://github.com/org/repo"]},
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    appended = append_opt_out_repository(config_path, "https://github.com/org/repo")
    assert appended is False
    assert json.loads(config_path.read_text(encoding="utf-8"))["issues"][
        "opt_outs"
    ] == ["https://github.com/org/repo"]
