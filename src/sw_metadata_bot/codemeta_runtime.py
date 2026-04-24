"""Codemeta detection and suggestion helpers based on SoMEF outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import utils


def _iter_sources(entry: dict[str, Any]) -> list[str]:
    """Collect normalized source links from a SOMEF extraction entry."""
    source = entry.get("source")
    if isinstance(source, str):
        return [source]
    if isinstance(source, list):
        return [item for item in source if isinstance(item, str)]
    return []


def codemeta_detected_in_somef(somef_data: dict[str, Any]) -> bool:
    """Return True when SOMEF evidence indicates a root codemeta.json file."""
    for value in somef_data.values():
        if not isinstance(value, list):
            continue

        for entry in value:
            if not isinstance(entry, dict):
                continue
            sources = _iter_sources(entry)
            for source in sources:
                if source.lower().endswith("/codemeta.json"):
                    return True

    return False


def load_codemeta_status(repo_folder: Path) -> dict[str, Any]:
    """Load codemeta status file if present, else return default absent status."""
    status_file = repo_folder / "codemeta_status.json"
    try:
        data = utils.load_json_file(
            status_file, required=False, description="codemeta status"
        )
        return data
    except ValueError:
        return {
            "status": "unknown",
            "missing": False,
            "generated": False,
            "reason": "invalid_status_payload",
        }

    return {
        "status": "unknown",
        "missing": False,
        "generated": False,
        "reason": "status_file_missing",
    }


def evaluate_and_persist_codemeta_status(
    *,
    repo_url: str,
    repo_folder: Path,
    generate_if_missing: bool,
) -> dict[str, Any]:
    """Detect codemeta presence from SOMEF output sources and record status.

    The optional generated codemeta payload is created by rsmetacheck and
    normalized to ``codemeta_generated.json`` by standardization helpers.
    """
    status_file = repo_folder / "codemeta_status.json"
    generated_file = repo_folder / "codemeta_generated.json"
    somef_file = repo_folder / "somef_output.json"

    status: dict[str, Any] = {
        "status": "unknown",
        "missing": False,
        "generated": False,
        "generate_if_missing": bool(generate_if_missing),
        "source": "somef_output.json",
    }

    if not somef_file.exists():
        status["reason"] = "missing_somef_output"
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
        return status

    try:
        somef_data = utils.load_json_file(
            somef_file, required=True, description="SOMEF output"
        )
    except Exception as exc:
        status["reason"] = "invalid_somef_output"
        status["error"] = str(exc)
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
        return status

    if not isinstance(somef_data, dict):
        status["reason"] = "unexpected_somef_schema"
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
        return status

    codemeta_present = codemeta_detected_in_somef(somef_data)
    if codemeta_present:
        status["status"] = "present"
        status["missing"] = False
        status["reason"] = "detected_in_somef_sources"
        if generated_file.exists():
            generated_file.unlink()
    else:
        status["status"] = "missing"
        status["missing"] = True
        status["reason"] = "not_detected_in_somef_sources"

        if not generate_if_missing and generated_file.exists():
            generated_file.unlink()

    if generated_file.exists():
        status["generated"] = True
        status["generated_file"] = generated_file.name

    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)

    return status
