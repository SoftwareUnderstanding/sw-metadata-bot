"""Utility function to update version in all relevant files in the current package"""

import json
from datetime import datetime
from importlib import import_module
from pathlib import Path

try:
    tomllib = import_module("tomllib")
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback for doc builds
    tomllib = import_module("tomli")

import argparse


def arg_parse() -> argparse.Namespace:
    """Parse command line arguments for version update."""
    parser = argparse.ArgumentParser(
        description="Update version in pyproject.toml and codemeta.json"
    )
    parser.add_argument(
        "type",
        choices=["major", "minor", "patch"],
        help="Type of version increment (major, minor, patch)",
    )
    return parser.parse_args()


def get_pyproject_dict() -> dict:
    """Read the pyproject.toml file and return its contents as a dictionary"""
    with (Path(__file__).parent / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    return pyproject


def get_codemeta_dict() -> dict:
    """Read the codemeta.json file and return its contents as a dictionary"""
    with (Path(__file__).parent / "codemeta.json").open(
        "r", encoding="utf-8"
    ) as codemeta_file:
        codemeta = json.load(codemeta_file)
    return codemeta


def update_pyproject_file(new_version: str) -> None:
    """Update the version in the pyproject.toml file"""
    pyproject = get_pyproject_dict()
    pyproject["project"]["version"] = new_version
    with (Path(__file__).parent / "pyproject.toml").open(
        "w", encoding="utf-8"
    ) as pyproject_file:
        pyproject_file.write(tomllib.dumps(pyproject))


def update_codemeta_file(new_version: str) -> None:
    """Update the version in the codemeta.json file"""
    codemeta = get_codemeta_dict()
    codemeta["version"] = new_version
    codemeta["dateModified"] = datetime.now().isoformat()
    with (Path(__file__).parent / "codemeta.json").open(
        "w", encoding="utf-8"
    ) as codemeta_file:
        json.dump(codemeta, codemeta_file, indent=2)


def increment_version(version: str, type: str) -> str:
    """Increment version string based on type (major, minor, patch)"""
    major, minor, patch = map(int, version.split("."))
    if type == "patch":
        patch += 1
    elif type == "minor":
        minor += 1
        patch = 0
    elif type == "major":
        major += 1
        minor = 0
        patch = 0
    return f"{major}.{minor}.{patch}"


def main():
    """Main function to update version in all relevant files"""
    args = arg_parse()
    pyproject = get_pyproject_dict()
    current_version = pyproject["project"]["version"]
    new_version = increment_version(current_version, args.type)
    update_pyproject_file(new_version)
    update_codemeta_file(new_version)
    print(f"Version updated from {current_version} to {new_version}")
