"""Tests for the version update utility."""

import importlib.util
import json
from pathlib import Path


def _load_updater_module():
    """Load the release utility module without relying on package import paths."""
    module_path = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "release"
        / "update_version_package.py"
    )
    spec = importlib.util.spec_from_file_location("update_version_package", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


updater = _load_updater_module()


def test_increment_version_patch():
    """Increment patch versions without changing major or minor numbers."""
    assert updater.increment_version("1.2.3", "patch") == "1.2.4"


def test_update_pyproject_file_updates_project_version_only(tmp_path, monkeypatch):
    """Update only the version line in the [project] section."""
    pyproject_text = """[build-system]
requires = [\"setuptools>=69\", \"wheel\"]

[project]
# preserve this comment
name = \"example\"
version = \"0.4.0\"
description = \"Example package\"

[tool.example]
version = \"leave-me-alone\"
"""
    (tmp_path / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        updater,
        "__file__",
        str(tmp_path / "tools" / "release" / "update_version_package.py"),
    )

    updater.update_pyproject_file("0.5.0")

    updated_text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        '# preserve this comment\nname = "example"\nversion = "0.5.0"' in updated_text
    )
    assert 'version = "leave-me-alone"' in updated_text
    assert updated_text.count('version = "0.5.0"') == 1


def test_update_pyproject_file_fails_without_project_version(tmp_path, monkeypatch):
    """Raise a clear error if the [project] section has no version entry."""
    pyproject_text = """[project]
name = \"example\"
"""
    (tmp_path / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        updater,
        "__file__",
        str(tmp_path / "tools" / "release" / "update_version_package.py"),
    )

    try:
        updater.update_pyproject_file("0.5.0")
    except ValueError as exc:
        assert str(exc) == "Could not update project.version in pyproject.toml"
    else:
        raise AssertionError("Expected update_pyproject_file() to raise ValueError")


def test_update_codemeta_file_updates_version_and_date(tmp_path, monkeypatch):
    """Update codemeta version and refresh the modified timestamp."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "0.4.0"\n', encoding="utf-8"
    )
    (tmp_path / "codemeta.json").write_text(
        json.dumps({"version": "0.4.0", "dateModified": "2026-01-01T00:00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        updater,
        "__file__",
        str(tmp_path / "tools" / "release" / "update_version_package.py"),
    )

    updater.update_codemeta_file("0.5.0")

    updated_codemeta = json.loads(
        (tmp_path / "codemeta.json").read_text(encoding="utf-8")
    )
    assert updated_codemeta["version"] == "0.5.0"
    assert updated_codemeta["dateModified"] != "2026-01-01T00:00:00"
