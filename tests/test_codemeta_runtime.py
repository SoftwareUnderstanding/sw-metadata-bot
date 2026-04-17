"""Tests for codemeta runtime helpers."""

import json

from sw_metadata_bot.codemeta_runtime import (
    codemeta_detected_in_somef,
    evaluate_and_persist_codemeta_status,
)


def test_codemeta_detected_in_somef_sources():
    """Detect codemeta.json when SOMEF source points to codemeta file."""
    data = {
        "name": [
            {
                "result": {"value": "demo"},
                "source": "https://raw.githubusercontent.com/org/repo/main/codemeta.json",
            }
        ]
    }

    assert codemeta_detected_in_somef(data) is True


def test_evaluate_and_persist_codemeta_status_missing_without_generated(tmp_path):
    """Persist missing status when no codemeta is detected and no generated file exists."""
    repo_folder = tmp_path / "repo"
    repo_folder.mkdir(parents=True, exist_ok=True)
    (repo_folder / "somef_output.json").write_text(
        json.dumps(
            {
                "name": [{"result": {"value": "demo"}}],
                "description": [{"result": {"value": "A demo repository"}}],
                "code_repository": [
                    {"result": {"value": "https://github.com/org/repo"}}
                ],
            }
        )
    )

    status = evaluate_and_persist_codemeta_status(
        repo_url="https://github.com/org/repo",
        repo_folder=repo_folder,
        generate_if_missing=True,
    )

    assert status["status"] == "missing"
    assert status["missing"] is True
    assert status["generated"] is False
    assert (repo_folder / "codemeta_status.json").exists()
    assert not (repo_folder / "codemeta_generated.json").exists()


def test_evaluate_and_persist_codemeta_status_generated_file_present(tmp_path):
    """Mark generated=True when codemeta_generated.json already exists (placed by rsmetacheck)."""
    repo_folder = tmp_path / "repo"
    repo_folder.mkdir(parents=True, exist_ok=True)
    (repo_folder / "somef_output.json").write_text(
        json.dumps({"name": [{"result": {"value": "demo"}}]})
    )
    (repo_folder / "codemeta_generated.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/3.0", "name": "demo"})
    )

    status = evaluate_and_persist_codemeta_status(
        repo_url="https://github.com/org/repo",
        repo_folder=repo_folder,
        generate_if_missing=True,
    )

    assert status["status"] == "missing"
    assert status["generated"] is True
    assert (repo_folder / "codemeta_generated.json").exists()


def test_evaluate_and_persist_codemeta_status_cleans_up_when_flag_off(tmp_path):
    """Remove stale codemeta_generated.json when generate_if_missing is False."""
    repo_folder = tmp_path / "repo"
    repo_folder.mkdir(parents=True, exist_ok=True)
    (repo_folder / "somef_output.json").write_text(
        json.dumps({"name": [{"result": {"value": "demo"}}]})
    )
    (repo_folder / "codemeta_generated.json").write_text("{}")

    status = evaluate_and_persist_codemeta_status(
        repo_url="https://github.com/org/repo",
        repo_folder=repo_folder,
        generate_if_missing=False,
    )

    assert status["generated"] is False
    assert not (repo_folder / "codemeta_generated.json").exists()
