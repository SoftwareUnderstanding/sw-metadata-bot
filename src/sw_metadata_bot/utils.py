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
