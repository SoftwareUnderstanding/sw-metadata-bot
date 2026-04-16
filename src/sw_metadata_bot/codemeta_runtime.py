"""Codemeta detection and suggestion helpers based on SoMEF outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CODEMETA_CONTEXT_URL = "https://w3id.org/codemeta/3.0"


def _first_value(somef_data: dict[str, Any], key: str) -> Any | None:
    """Return the first extracted SOMEF value for a key if available."""
    entries = somef_data.get(key)
    if not isinstance(entries, list) or not entries:
        return None

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if isinstance(result, dict) and "value" in result:
            return result.get("value")

    return None


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


def generate_codemeta_from_somef(
    repo_url: str, somef_data: dict[str, Any]
) -> dict[str, Any]:
    """Build a codemeta-like payload from SOMEF extracted metadata."""
    generated: dict[str, Any] = {
        "@context": CODEMETA_CONTEXT_URL,
        "@type": "SoftwareSourceCode",
        "codeRepository": str(_first_value(somef_data, "code_repository") or repo_url),
        "name": str(
            _first_value(somef_data, "name") or repo_url.rstrip("/").split("/")[-1]
        ),
    }

    description = _first_value(somef_data, "description")
    if isinstance(description, str) and description:
        generated["description"] = description

    license_value = _first_value(somef_data, "license")
    if isinstance(license_value, str) and license_value:
        generated["license"] = license_value

    issue_tracker = _first_value(somef_data, "issue_tracker")
    if isinstance(issue_tracker, str) and issue_tracker:
        generated["issueTracker"] = issue_tracker

    download_url = _first_value(somef_data, "download_url")
    if isinstance(download_url, str) and download_url:
        generated["downloadUrl"] = download_url

    programming_languages = somef_data.get("programming_languages")
    if isinstance(programming_languages, list):
        languages: list[str] = []
        for entry in programming_languages:
            if not isinstance(entry, dict):
                continue
            result = entry.get("result")
            if not isinstance(result, dict):
                continue
            value = result.get("value")
            if isinstance(value, str) and value:
                languages.append(value)
        if languages:
            generated["programmingLanguage"] = sorted(set(languages))

    keywords = _first_value(somef_data, "keywords")
    if isinstance(keywords, list):
        generated["keywords"] = [value for value in keywords if isinstance(value, str)]
    elif isinstance(keywords, str) and keywords:
        generated["keywords"] = [
            part.strip() for part in keywords.split(",") if part.strip()
        ]

    generated["dateModified"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return generated


def load_codemeta_status(repo_folder: Path) -> dict[str, Any]:
    """Load codemeta status file if present, else return default absent status."""
    status_file = repo_folder / "codemeta_status.json"
    if not status_file.exists():
        return {
            "status": "unknown",
            "missing": False,
            "generated": False,
            "reason": "status_file_missing",
        }

    with open(status_file, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return {
            "status": "unknown",
            "missing": False,
            "generated": False,
            "reason": "invalid_status_payload",
        }

    return data


def evaluate_and_persist_codemeta_status(
    *,
    repo_url: str,
    repo_folder: Path,
    generate_if_missing: bool,
) -> dict[str, Any]:
    """Detect codemeta presence from SOMEF output and optionally generate suggestion."""
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
        with open(somef_file, encoding="utf-8") as f:
            somef_data = json.load(f)
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

        if generate_if_missing:
            generated_payload = generate_codemeta_from_somef(repo_url, somef_data)
            with open(generated_file, "w", encoding="utf-8") as f:
                json.dump(generated_payload, f, indent=2)
            status["generated"] = True
            status["generated_file"] = generated_file.name
        elif generated_file.exists():
            generated_file.unlink()

    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)

    return status
