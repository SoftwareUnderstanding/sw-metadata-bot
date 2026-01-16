from pathlib import Path


def load_pitfalls(file_path: Path):
    """Load pitfalls from a JSON-LD file."""
    import json

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def get_analysis_version_info():
    """Retrieve metacheck and SOMEF version information."""
    from importlib.metadata import version

    import somef

    return {
        "metacheck_version": version("metacheck"),
        "somef_version": somef.__version__,
    }


def get_url_from_pitfalls_data(pitfalls_data) -> str:
    """Extract repository URL from pitfalls data."""
    return pitfalls_data.get("assessedSoftware", {}).get("url", "Unknown URL")


def get_pitfalls_list(pitfalls_data) -> list[dict]:
    """Extract the list of pitfalls from pitfalls data."""
    return pitfalls_data.get("checks", [])


def get_date_created(pitfalls_data) -> str:
    """Extract the dateCreated from pitfalls data."""
    return pitfalls_data.get("dateCreated", "Unknown Date")


def check_is_pitfall(pitfall: dict) -> bool:
    """Check if a given pitfall dictionary represents an actual pitfall."""
    return "p" in pitfall.get("checkId", "").lower()
