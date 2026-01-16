"""Pitfalls data analysis and processing."""

import json
from pathlib import Path

from ..core.exceptions import PitfallsParsingError


class PitfallsAnalyzer:
    """Handles loading and analyzing pitfalls data from JSON-LD files."""

    @staticmethod
    def load_pitfalls(file_path: Path) -> dict:
        """Load pitfalls from a JSON-LD file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            raise PitfallsParsingError(str(file_path), f"Invalid JSON: {e}")
        except IOError as e:
            raise PitfallsParsingError(str(file_path), f"File error: {e}")

    @staticmethod
    def get_repository_url(pitfalls_data: dict) -> str:
        """Extract repository URL from pitfalls data."""
        url = pitfalls_data.get("assessedSoftware", {}).get("url", "")
        if not url:
            raise PitfallsParsingError(
                "unknown", "assessedSoftware.url not found in pitfalls data"
            )
        return url

    @staticmethod
    def get_pitfalls_list(pitfalls_data: dict) -> list[dict]:
        """Extract the list of pitfalls from pitfalls data."""
        checks = pitfalls_data.get("checks", [])
        if not isinstance(checks, list):
            raise PitfallsParsingError(
                "unknown", "checks field is not a list in pitfalls data"
            )
        return checks

    @staticmethod
    def get_date_created(pitfalls_data: dict) -> str:
        """Extract the dateCreated from pitfalls data."""
        return pitfalls_data.get("dateCreated", "Unknown Date")

    @staticmethod
    def get_version_info() -> dict[str, str]:
        """Retrieve metacheck and SOMEF version information."""
        try:
            from importlib.metadata import version

            import somef

            return {
                "metacheck_version": version("metacheck"),
                "somef_version": somef.__version__,
            }
        except Exception as e:
            return {
                "metacheck_version": "Unknown",
                "somef_version": "Unknown",
                "error": str(e),
            }

    @staticmethod
    def is_pitfall(check: dict) -> bool:
        """Determine if a check is a pitfall (vs warning)."""
        check_id = check.get("checkId", "").lower()
        return "p" in check_id

    @staticmethod
    def classify_checks(pitfalls_data: dict) -> tuple[list[dict], list[dict]]:
        """Separate checks into pitfalls and warnings."""
        checks = PitfallsAnalyzer.get_pitfalls_list(pitfalls_data)
        pitfalls = [c for c in checks if PitfallsAnalyzer.is_pitfall(c)]
        warnings = [c for c in checks if not PitfallsAnalyzer.is_pitfall(c)]
        return pitfalls, warnings
