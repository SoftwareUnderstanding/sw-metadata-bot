"""Convert legacy snapshot-based output trees into the repo-centric state layout."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from sw_metadata_bot import constants, repo_state
from sw_metadata_bot.config.config_utils import sanitize_repo_name


def _iter_legacy_repo_dirs(snapshot_root: Path) -> list[Path]:
    """Return repository directories inside a legacy snapshot root."""
    if not snapshot_root.exists():
        return []

    repo_dirs = [
        child
        for child in snapshot_root.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    ]
    return sorted(repo_dirs)


def _load_json_if_present(path: Path) -> Any | None:
    """Load JSON from disk when present, otherwise return None."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None


def _copy_if_present(source: Path, destination: Path) -> None:
    """Copy a file to the destination when it exists."""
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def convert_legacy_output_tree(
    snapshot_root: Path, *, target_root: Path | None = None
) -> list[Path]:
    """Convert a legacy snapshot root into repo-centric state folders.

    The converter copies repository artifacts from legacy per-repo directories into
    a new layout rooted at ``target_root``. It also writes current-state and
    event-log files for each converted repository and mirrors the legacy
    run_report.json into the target root when present.
    """
    snapshot_root = snapshot_root.resolve()
    target_root = (target_root or snapshot_root).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    converted: list[Path] = []
    for repo_dir in _iter_legacy_repo_dirs(snapshot_root):
        repo_name = sanitize_repo_name(repo_dir.name)
        repo_folder = target_root / repo_name
        repo_paths = repo_state.resolve_repo_state_paths(
            target_root, f"https://example.invalid/{repo_name}"
        )
        repo_paths["repo_folder"].mkdir(parents=True, exist_ok=True)
        repo_state.ensure_repo_state_dirs(repo_paths)

        for filename in (
            constants.FILENAME_PITFALL,
            constants.FILENAME_SOMEF_OUTPUT,
            constants.FILENAME_REPORT,
            constants.FILENAME_ISSUE_REPORT,
            constants.FILENAME_CODEMETA_STATUS,
            constants.FILENAME_CODEMETA_GENERATED,
        ):
            _copy_if_present(repo_dir / filename, repo_folder / filename)

        legacy_report = _load_json_if_present(repo_dir / constants.FILENAME_REPORT)
        if isinstance(legacy_report, dict):
            records = legacy_report.get("records")
            if isinstance(records, list) and records:
                record = records[0]
                if isinstance(record, dict):
                    repo_state.write_current_state(
                        repo_folder, repo_state.build_analysis_current_state(record)
                    )
                    repo_state.append_event_log(
                        repo_folder,
                        {
                            "event": "analysis_completed",
                            "commit_id": record.get("current_commit_id") or "unknown",
                            "analysis_file": str(
                                (repo_folder / constants.DIRNAME_ANALYSES).relative_to(
                                    repo_folder
                                )
                            ),
                        },
                    )

        converted.append(snapshot_root)

    legacy_run_report = snapshot_root / constants.FILENAME_RUN_REPORT
    if legacy_run_report.exists():
        target_run_report = target_root / constants.FILENAME_RUN_REPORT
        shutil.copy2(legacy_run_report, target_run_report)

    return converted


def main() -> None:
    """CLI entry point for the conversion utility."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "snapshot_root", type=Path, help="Legacy snapshot root to convert"
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=None,
        help="Destination root for the converted repo-centric layout",
    )
    args = parser.parse_args()

    convert_legacy_output_tree(args.snapshot_root, target_root=args.target_root)


if __name__ == "__main__":
    main()
