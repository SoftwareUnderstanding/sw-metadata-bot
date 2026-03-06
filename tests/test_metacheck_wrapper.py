"""Tests for metacheck_wrapper module."""

import json
import os

import click
import pytest

from sw_metadata_bot import metacheck_wrapper


def test_filter_blacklisted_repos_removes_matching_urls(tmp_path):
    """Repos in the blacklist are excluded from the filtered input file."""
    input_file = tmp_path / "repos.json"
    input_file.write_text(
        json.dumps(
            {
                "repositories": [
                    "https://github.com/org/keep-me",
                    "https://github.com/org/blacklisted",
                    "https://gitlab.com/group/also-blacklisted/",
                ]
            }
        )
    )

    blacklist_file = tmp_path / "blacklist.json"
    blacklist_file.write_text(
        json.dumps(
            {
                "repositories": [
                    "https://github.com/org/blacklisted",
                    "https://gitlab.com/group/also-blacklisted",
                ]
            }
        )
    )

    filtered_path = metacheck_wrapper._filter_blacklisted_repos(
        str(input_file), blacklist_file
    )

    try:
        with open(filtered_path, encoding="utf-8") as f:
            filtered_data = json.load(f)

        assert filtered_data["repositories"] == ["https://github.com/org/keep-me"]
    finally:
        os.unlink(filtered_path)


def test_filter_blacklisted_repos_preserves_extra_keys(tmp_path):
    """Non-repositories keys in the input file are preserved after filtering."""
    input_file = tmp_path / "repos.json"
    input_file.write_text(
        json.dumps(
            {
                "repositories": ["https://github.com/org/keep", "https://github.com/org/skip"],
                "custom_message": "hello",
            }
        )
    )

    blacklist_file = tmp_path / "blacklist.json"
    blacklist_file.write_text(
        json.dumps({"repositories": ["https://github.com/org/skip"]})
    )

    filtered_path = metacheck_wrapper._filter_blacklisted_repos(
        str(input_file), blacklist_file
    )

    try:
        with open(filtered_path, encoding="utf-8") as f:
            filtered_data = json.load(f)

        assert filtered_data["repositories"] == ["https://github.com/org/keep"]
        assert filtered_data["custom_message"] == "hello"
    finally:
        os.unlink(filtered_path)


def test_filter_blacklisted_repos_empty_blacklist_keeps_all(tmp_path):
    """Empty blacklist leaves the repository list unchanged."""
    input_file = tmp_path / "repos.json"
    repos = ["https://github.com/org/a", "https://github.com/org/b"]
    input_file.write_text(json.dumps({"repositories": repos}))

    blacklist_file = tmp_path / "blacklist.json"
    blacklist_file.write_text(json.dumps({"repositories": []}))

    filtered_path = metacheck_wrapper._filter_blacklisted_repos(
        str(input_file), blacklist_file
    )

    try:
        with open(filtered_path, encoding="utf-8") as f:
            filtered_data = json.load(f)

        assert filtered_data["repositories"] == repos
    finally:
        os.unlink(filtered_path)


def test_filter_blacklisted_repos_invalid_blacklist_format_raises(tmp_path):
    """Invalid 'repositories' type in blacklist file raises ClickException."""
    input_file = tmp_path / "repos.json"
    input_file.write_text(json.dumps({"repositories": ["https://github.com/org/a"]}))

    blacklist_file = tmp_path / "blacklist.json"
    blacklist_file.write_text(json.dumps({"repositories": "not-a-list"}))

    with pytest.raises(click.ClickException, match="repositories' must be a list"):
        metacheck_wrapper._filter_blacklisted_repos(str(input_file), blacklist_file)
