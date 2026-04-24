"""Centralized utilities for common operations across sw-metadata-bot.

This module consolidates repeated patterns for JSON file handling, configuration
validation, and path management. By centralizing these utilities, the codebase
becomes easier to maintain and more resistant to bugs (e.g., inconsistent error
handling).

"""

import json
import logging
from pathlib import Path
from typing import Any, TypeVar, cast

import click

logger = logging.getLogger(__name__)
T = TypeVar("T")


# =============================================================================
# JSON File Loading
# =============================================================================


def load_json_file(
    path: Path,
    required: bool = True,
    description: str = "JSON file",
) -> dict[str, Any]:
    """Load and parse a JSON file with consistent error handling.

    This utility centralizes JSON file I/O to ensure consistent error handling,
    logging, and user-friendly error messages across the codebase.

    Args:
        path: Path to the JSON file to load
        required: If True, raise an exception if file is missing.
                 If False, return empty dict when file missing.
        description: Description of the file for error messages (e.g., "configuration")

    Returns:
        Parsed JSON data as a dictionary, or {} if file missing and not required

    Raises:
        FileNotFoundError: If required=True and file does not exist
        json.JSONDecodeError: If file is not valid JSON
        ValueError: If file contents are not a dict/mapping

    Examples:
        Load required analysis report, fail if missing:
            >>> report = load_json_file(Path("report.json"), required=True)

        Load optional previous results, return {} if missing:
            >>> prev = load_json_file(Path("previous.json"), required=False)
    """
    # Convert to Path if string passed
    path = Path(path) if isinstance(path, str) else path

    # Handle missing file
    if not path.exists():
        if required:
            msg = f"Required {description} not found: {path}"
            logger.error(msg)
            raise FileNotFoundError(msg)
        logger.debug(f"Optional {description} not found: {path}, returning empty dict")
        return {}

    # Load and parse JSON
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON in {description} {path}: {exc}"
        logger.error(msg)
        raise

    # Validate it's a dict
    if not isinstance(data, dict):
        msg = (
            f"Invalid {description} format in {path}: "
            f"expected dict/object, got {type(data).__name__}"
        )
        logger.error(msg)
        raise ValueError(msg)

    return cast(dict[str, Any], data)


def load_json_file_list(
    path: Path,
    required: bool = True,
    description: str = "JSON file",
) -> list[dict[str, Any]]:
    """Load a JSON file containing a list of dictionaries.

    Useful for report files that store arrays of records.

    Args:
        path: Path to the JSON file
        required: If True, raise if file missing. If False, return empty list.
        description: File description for error messages

    Returns:
        List of dictionaries, or [] if file missing and not required

    Raises:
        FileNotFoundError: If required=True and file missing
        json.JSONDecodeError: If file is not valid JSON
        ValueError: If file contents are not a list

    Examples:
        Load run_report.json records:
            >>> records = load_json_file_list(
            ...     analysis_root / "run_report.json",
            ...     required=True,
            ...     description="run report"
            ... )
    """
    path = Path(path) if isinstance(path, str) else path

    if not path.exists():
        if required:
            msg = f"Required {description} not found: {path}"
            logger.error(msg)
            raise FileNotFoundError(msg)
        logger.debug(f"Optional {description} not found: {path}, returning empty list")
        return []

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON in {description} {path}: {exc}"
        logger.error(msg)
        raise

    if not isinstance(data, list):
        msg = (
            f"Invalid {description} format in {path}: "
            f"expected list/array, got {type(data).__name__}"
        )
        logger.error(msg)
        raise ValueError(msg)

    return cast(list[dict[str, Any]], data)


# =============================================================================
# Configuration Validation
# =============================================================================


def validate_config_field(
    config: dict[str, Any],
    field: str,
    expected_type: type | tuple[type, ...],
    error_msg: str | None = None,
) -> Any:
    """Validate that a configuration field exists and has the expected type.

    This utility centralizes the repeated pattern of checking config fields,
    reducing duplication and ensuring consistent error messages.

    Args:
        config: Configuration dictionary
        field: Field name to check
        expected_type: Expected type(s), e.g., str, (str, int), list
        error_msg: Custom error message. If None, generates one automatically.

    Returns:
        The field value if validation passes

    Raises:
        click.ClickException: If field missing or has wrong type

    Examples:
        Check that config has a list of repositories:
            >>> repos = validate_config_field(
            ...     config, "repositories", list,
            ...     error_msg="repositories must be a list of repository URLs"
            ... )

        Check for either string or Path:
            >>> output = validate_config_field(
            ...     config, "output_root", (str, Path)
            ... )
    """
    value = config.get(field)

    if not isinstance(value, expected_type):
        if error_msg:
            message = error_msg
        else:
            type_names = (
                expected_type.__name__
                if isinstance(expected_type, type)
                else " or ".join(t.__name__ for t in expected_type)
            )
            message = (
                f"Configuration field '{field}' must be {type_names}, "
                f"got {type(value).__name__}"
            )
        logger.error(message)
        raise click.ClickException(message)

    return value


def validate_config_required(
    config: dict[str, Any],
    fields: list[str],
) -> None:
    """Validate that all required fields are present in config.

    Args:
        config: Configuration dictionary
        fields: List of required field names

    Raises:
        click.ClickException: If any required field is missing

    Examples:
        >>> validate_config_required(config, ["repositories", "outputs"])
    """
    missing = [f for f in fields if f not in config]
    if missing:
        msg = f"Configuration missing required fields: {', '.join(missing)}"
        logger.error(msg)
        raise click.ClickException(msg)


# =============================================================================
# Path Management
# =============================================================================


def build_file_path_safely(
    base: Path,
    *parts: str,
    allow_parent_traversal: bool = False,
) -> Path:
    """Construct a file path safely, preventing directory traversal attacks.

    This utility prevents malicious or accidental use of ".." in path components
    to escape the intended directory. Useful when constructing paths from
    configuration or external input.

    Args:
        base: Base directory path
        *parts: Path components to append
        allow_parent_traversal: If False, raise on ".." components (recommended).
                               If True, ".." is processed normally.

    Returns:
        Constructed Path object

    Raises:
        ValueError: If allow_parent_traversal=False and ".." detected in parts

    Examples:
        Safe path construction from config:
            >>> repo_folder = build_file_path_safely(
            ...     analysis_root, sanitize_repo_name(repo_url)
            ... )

        With parent traversal check (recommended):
            >>> report_path = build_file_path_safely(
            ...     output_root, "analysis", "report.json",
            ...     allow_parent_traversal=False
            ... )
    """
    if not allow_parent_traversal:
        for part in parts:
            if ".." in part or part.startswith("/"):
                msg = f"Unsafe path component detected (potential directory traversal): {part}"
                logger.error(msg)
                raise ValueError(msg)

    path = Path(base)
    for part in parts:
        path = path / part

    return path


# =============================================================================
# Type Guards & Validators
# =============================================================================


def is_dict_with_keys(
    value: Any,
    required_keys: list[str] | None = None,
) -> bool:
    """Check if a value is a dict and optionally has required keys.

    Useful for defensive programming when parsing external data.

    Args:
        value: Value to check
        required_keys: If provided, check that all these keys exist in dict

    Returns:
        True if value is a dict (and has required keys if provided), else False

    Examples:
        >>> check_data = parse_json_response(...)
        >>> if is_dict_with_keys(check_data, ["@type", "@context"]):
        ...     process_check(check_data)
    """
    if not isinstance(value, dict):
        return False

    if required_keys is not None:
        return all(key in value for key in required_keys)

    return True


def ensure_list(value: Any) -> list[Any]:
    """Convert value to a list, handling None and single values.

    Args:
        value: Value to convert (can be None, single item, or list)

    Returns:
        List containing the value(s), or empty list if value is None

    Examples:
        >>> ids = ensure_list(record.get("check_ids"))  # Handle None gracefully
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
