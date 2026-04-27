"""Utility function to update version in all relevant files in the current package"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

import tomllib


def get_project_root() -> Path:
    """Return the project root directory containing metadata files."""
    script_path = Path(__file__).resolve()
    for candidate in script_path.parents:
        if (candidate / "pyproject.toml").exists() and (
            candidate / "codemeta.json"
        ).exists():
            return candidate
    raise FileNotFoundError("Could not locate project root containing pyproject.toml")


def get_pyproject_path() -> Path:
    """Return the path to the pyproject.toml file."""
    return get_project_root() / "pyproject.toml"


def get_codemeta_path() -> Path:
    """Return the path to the codemeta.json file."""
    return get_project_root() / "codemeta.json"


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
    with get_pyproject_path().open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    return pyproject


def get_codemeta_dict() -> dict:
    """Read the codemeta.json file and return its contents as a dictionary"""
    with get_codemeta_path().open("r", encoding="utf-8") as codemeta_file:
        codemeta = json.load(codemeta_file)
    return codemeta


def update_pyproject_file(new_version: str) -> None:
    """Update the version in the pyproject.toml file"""
    pyproject_path = get_pyproject_path()
    pyproject_text = pyproject_path.read_text(encoding="utf-8")

    project_section_match = re.search(
        r"(?ms)^\[project\]\n(?P<body>.*?)(?=^\[|\Z)", pyproject_text
    )
    if project_section_match is None:
        raise ValueError("Could not find [project] section in pyproject.toml")

    project_body = project_section_match.group("body")
    updated_body, replacement_count = re.subn(
        r'(?m)^version\s*=\s*"[^"]+"$',
        f'version = "{new_version}"',
        project_body,
        count=1,
    )
    if replacement_count != 1:
        raise ValueError("Could not update project.version in pyproject.toml")

    updated_text = (
        pyproject_text[: project_section_match.start("body")]
        + updated_body
        + pyproject_text[project_section_match.end("body") :]
    )
    pyproject_path.write_text(updated_text, encoding="utf-8")


def update_codemeta_file(new_version: str) -> None:
    """Update the version in the codemeta.json file"""
    codemeta = get_codemeta_dict()
    codemeta["version"] = new_version
    codemeta["dateModified"] = date.today().isoformat()
    with get_codemeta_path().open("w", encoding="utf-8") as codemeta_file:
        json.dump(codemeta, codemeta_file, indent=2)


def update_readme_file(new_version: str) -> None:
    """Update the version in the README.md file if it contains a version badge"""
    readme_path = get_project_root() / "README.md"
    if not readme_path.exists():
        return

    readme_text = readme_path.read_text(encoding="utf-8")
    updated_text, replacement_count = re.subn(
        r"(img\.shields\.io/badge/version-)(\d+\.\d+\.\d+)(-)",
        rf"\g<1>{new_version}\g<3>",
        readme_text,
        count=1,
    )
    if replacement_count > 0:
        readme_path.write_text(updated_text, encoding="utf-8")


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


def check_args(args: argparse.Namespace) -> None:
    """Check if the provided arguments are valid"""
    if args.type not in ["major", "minor", "patch"]:
        raise ValueError(f"Invalid version increment type: {args.type}")


def main():
    """Main function to update version in all relevant files"""
    args = arg_parse()
    check_args(args)
    print(f"Updating version with {args.type} increment...")
    pyproject = get_pyproject_dict()
    current_version = pyproject["project"]["version"]
    new_version = increment_version(current_version, args.type)
    update_pyproject_file(new_version)
    update_codemeta_file(new_version)
    update_readme_file(new_version)
    print(f"Version updated from {current_version} to {new_version}")


if __name__ == "__main__":
    main()
