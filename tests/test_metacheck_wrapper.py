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

    blacklist = tmp_path / "blacklist.json"
    blacklist.write_text(
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
        str(input_file), blacklist
    )

    try:
        with open(filtered_path, encoding="utf-8") as f:
            filtered_data = json.load(f)

        assert filtered_data["repositories"] == ["https://github.com/org/keep-me"]
    finally:
        os.unlink(filtered_path)


def test_filter_blacklisted_repos_wildcard_pattern(tmp_path):
    """Glob-style wildcard patterns match all repos in an organisation."""
    input_file = tmp_path / "repos.json"
    input_file.write_text(
        json.dumps(
            {
                "repositories": [
                    "https://github.com/SoftwareUnderstanding/repo-a",
                    "https://github.com/SoftwareUnderstanding/repo-b",
                    "https://github.com/other-org/keep-me",
                ]
            }
        )
    )

    blacklist = tmp_path / "blacklist.json"
    blacklist.write_text(
        json.dumps({"repositories": ["https://github.com/SoftwareUnderstanding/*"]})
    )

    filtered_path = metacheck_wrapper._filter_blacklisted_repos(
        str(input_file), blacklist
    )

    try:
        with open(filtered_path, encoding="utf-8") as f:
            filtered_data = json.load(f)

        assert filtered_data["repositories"] == ["https://github.com/other-org/keep-me"]
    finally:
        os.unlink(filtered_path)


def test_filter_blacklisted_repos_wildcard_suffix(tmp_path):
    """Wildcard suffix on a prefix matches repos whose name starts with the prefix."""
    input_file = tmp_path / "repos.json"
    input_file.write_text(
        json.dumps(
            {
                "repositories": [
                    "https://github.com/org/skip-123",
                    "https://github.com/org/skip-456",
                    "https://github.com/org/keep-me",
                ]
            }
        )
    )

    blacklist = tmp_path / "blacklist.json"
    blacklist.write_text(
        json.dumps({"repositories": ["https://github.com/org/skip-*"]})
    )

    filtered_path = metacheck_wrapper._filter_blacklisted_repos(
        str(input_file), blacklist
    )

    try:
        with open(filtered_path, encoding="utf-8") as f:
            filtered_data = json.load(f)

        assert filtered_data["repositories"] == ["https://github.com/org/keep-me"]
    finally:
        os.unlink(filtered_path)


def test_filter_blacklisted_repos_dot_in_url_is_literal(tmp_path):
    """Dots in URLs are treated as literals, not regex 'any character'."""
    input_file = tmp_path / "repos.json"
    input_file.write_text(
        json.dumps(
            {
                "repositories": [
                    "https://github.com/org/repo",
                    "https://githubXcom/org/repo",  # dot replaced by X
                ]
            }
        )
    )

    blacklist = tmp_path / "blacklist.json"
    blacklist.write_text(
        json.dumps({"repositories": ["https://github.com/org/repo"]})
    )

    filtered_path = metacheck_wrapper._filter_blacklisted_repos(
        str(input_file), blacklist
    )

    try:
        with open(filtered_path, encoding="utf-8") as f:
            filtered_data = json.load(f)

        # Only the exact-match URL is removed; the X-variant is kept
        assert filtered_data["repositories"] == ["https://githubXcom/org/repo"]
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

    blacklist = tmp_path / "blacklist.json"
    blacklist.write_text(
        json.dumps({"repositories": ["https://github.com/org/skip"]})
    )

    filtered_path = metacheck_wrapper._filter_blacklisted_repos(
        str(input_file), blacklist
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

    blacklist = tmp_path / "blacklist.json"
    blacklist.write_text(json.dumps({"repositories": []}))

    filtered_path = metacheck_wrapper._filter_blacklisted_repos(
        str(input_file), blacklist
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

    blacklist = tmp_path / "blacklist.json"
    blacklist.write_text(json.dumps({"repositories": "not-a-list"}))

    with pytest.raises(click.ClickException, match="repositories' must be a list"):
        metacheck_wrapper._filter_blacklisted_repos(str(input_file), blacklist)


def test_is_blacklisted_wildcard():
    """Wildcard pattern matches repos in the specified organisation."""
    patterns = ["https://github.com/MyOrg/*"]
    assert metacheck_wrapper._is_blacklisted("https://github.com/MyOrg/repo-a", patterns)
    assert metacheck_wrapper._is_blacklisted("https://github.com/MyOrg/repo-b", patterns)
    assert not metacheck_wrapper._is_blacklisted("https://github.com/OtherOrg/repo", patterns)


def test_is_blacklisted_exact_url():
    """Exact URL (no regex) is matched correctly."""
    patterns = ["https://github.com/org/repo"]
    assert metacheck_wrapper._is_blacklisted("https://github.com/org/repo", patterns)
    assert metacheck_wrapper._is_blacklisted("https://github.com/org/repo/", patterns)
    assert not metacheck_wrapper._is_blacklisted("https://github.com/org/other", patterns)


def test_is_blacklisted_trailing_slash_normalization():
    """Trailing slashes are stripped before matching."""
    patterns = ["https://github.com/org/repo/"]
    assert metacheck_wrapper._is_blacklisted("https://github.com/org/repo", patterns)


def test_missing_default_blacklist_is_silently_skipped(tmp_path, monkeypatch):
    """When the default .blacklist file is absent, no filtering is applied."""
    monkeypatch.chdir(tmp_path)  # ensure no .blacklist exists in CWD

    def fake_metacheck_cli():
        pass

    monkeypatch.setattr(metacheck_wrapper, "metacheck_cli", fake_metacheck_cli)

    input_file = tmp_path / "repos.json"
    input_file.write_text(json.dumps({"repositories": ["https://github.com/org/a"]}))

    # Invoke directly without providing --blacklist; default .blacklist does not exist
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(
        metacheck_wrapper.metacheck_command,
        [
            "--input",
            str(input_file),
            "--pitfalls-output",
            str(tmp_path / "out"),
            "--analysis-output",
            str(tmp_path / "results.json"),
        ],
    )
    # Should not error due to missing default .blacklist
    assert "Error" not in result.output
    assert result.exit_code == 0
