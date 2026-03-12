"""Pipeline command to run analysis then issue creation."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import click
import requests

from .create_issues import create_issues_command
from .history import load_previous_report
from .metacheck_wrapper import metacheck_command

DEFAULT_INPUT_FILE = Path("assets/opt-ins.json")
DEFAULT_OPTOUT_FILE = Path("assets/opt-outs.json")
DEFAULT_OUTPUT_ROOT = Path("outputs")
SNAPSHOT_TAG_PATTERN = re.compile(r"^(\d{8})(?:_(\d+))?$")
SNAPSHOT_INCREMENT_PATTERN = re.compile(r"^(.+?)_(\d+)$")


def _normalize_repo_url(url: str) -> str:
    """Normalize repository URL for cross-report matching."""
    return url.strip().rstrip("/")


def _load_repositories_from_input(input_file: Path) -> list[str] | None:
    """Load repositories from input JSON file, preserving order and uniqueness.

    Returns None when input does not expose a valid repositories list.
    """
    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    repositories = data.get("repositories") if isinstance(data, dict) else None
    if not isinstance(repositories, list):
        return None

    seen: set[str] = set()
    ordered: list[str] = []
    for item in repositories:
        if not isinstance(item, str):
            continue
        normalized = _normalize_repo_url(item)
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _extract_previous_commit(record: dict) -> str | None:
    """Return previous commit id from report records with compatibility fallback."""
    current_commit = record.get("current_commit_id")
    if isinstance(current_commit, str) and current_commit:
        return current_commit

    legacy_commit = record.get("commit_id")
    if isinstance(legacy_commit, str) and legacy_commit:
        return legacy_commit

    return None


def _is_supported_for_commit_skip(repo_url: str) -> bool:
    """Return whether pre-analysis commit lookup is supported for a repo URL."""
    return "github.com" in repo_url.lower()


def _parse_github_repo(repo_url: str) -> tuple[str, str] | None:
    """Parse owner/repo from a GitHub repository URL."""
    match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", repo_url, re.IGNORECASE)
    if match is None:
        return None
    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    return owner, repo


def _get_repo_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit for a GitHub repository."""
    parsed = _parse_github_repo(repo_url)
    if parsed is None:
        return None

    owner, repo = parsed
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    response = requests.get(url, params={"per_page": 1}, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    sha = first.get("sha")
    return str(sha) if isinstance(sha, str) and sha else None


def _build_repo_not_updated_record(
    repo_url: str,
    current_commit_id: str | None,
    previous_commit_id: str | None,
) -> dict[str, object]:
    """Build report record for repositories skipped before analysis."""
    platform = "github" if "github.com" in repo_url.lower() else None
    return {
        "repo_url": repo_url,
        "platform": platform,
        "pitfalls_count": 0,
        "warnings_count": 0,
        "issue_url": None,
        "analysis_date": "not-run",
        "sw_metadata_bot_version": "unknown",
        "rsmetacheck_version": "unknown",
        "pitfalls_ids": [],
        "warnings_ids": [],
        "action": "skipped",
        "reason_code": "repo_not_updated",
        "findings_signature": "",
        "current_commit_id": current_commit_id,
        "previous_commit_id": previous_commit_id,
        "dry_run": False,
        "issue_persistence": "none",
    }


def _merge_pre_skipped_records(
    report_file: Path,
    skipped_records: list[dict[str, object]],
) -> None:
    """Merge pre-analysis skipped records into create-issues report output."""
    if not skipped_records:
        return

    with open(report_file, encoding="utf-8") as f:
        report = json.load(f)

    records = report.get("records")
    if not isinstance(records, list):
        records = []
    records = [*skipped_records, *records]
    report["records"] = records

    counters = report.get("counters")
    if not isinstance(counters, dict):
        counters = {}
    counters["skipped"] = int(counters.get("skipped", 0)) + len(skipped_records)
    counters["total"] = int(counters.get("total", 0)) + len(skipped_records)
    report["counters"] = counters

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def _write_pre_skipped_only_report(
    report_file: Path,
    *,
    dry_run: bool,
    analysis_summary_file: Path,
    previous_report_source: Path | None,
    skipped_records: list[dict[str, object]],
) -> None:
    """Write report.json when all repositories are skipped before analysis."""
    report_file.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": dry_run,
            "analysis_summary_file": str(analysis_summary_file),
            "previous_report_source": (
                str(previous_report_source)
                if previous_report_source is not None
                else None
            ),
        },
        "counters": {
            "total": len(skipped_records),
            "created": 0,
            "simulated": 0,
            "updated_by_comment": 0,
            "closed": 0,
            "skipped": len(skipped_records),
            "failed": 0,
        },
        "records": skipped_records,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def _resolve_unique_snapshot_tag(
    run_root: Path, snapshot_tag: str | None
) -> str | None:
    """Return a non-colliding snapshot tag by adding or incrementing numeric suffixes."""
    if snapshot_tag is None:
        return None

    candidate_path = run_root / snapshot_tag
    if not candidate_path.exists():
        return snapshot_tag

    match = SNAPSHOT_INCREMENT_PATTERN.fullmatch(snapshot_tag)
    if match is None:
        base_tag = snapshot_tag
        suffix = 2
    else:
        base_tag = match.group(1)
        suffix = int(match.group(2)) + 1

    while True:
        candidate = f"{base_tag}_{suffix}"
        if not (run_root / candidate).exists():
            return candidate
        suffix += 1


def _resolve_run_paths(
    output_root: Path,
    input_file: Path,
    run_name: str | None,
    snapshot_tag: str | None,
) -> tuple[Path, Path, Path, Path]:
    """Compute dedicated output paths for a pipeline run."""
    run_folder_name = run_name if run_name else input_file.stem
    run_root = output_root / run_folder_name

    if snapshot_tag:
        run_root = run_root / snapshot_tag

    somef_output_dir = run_root / "somef_outputs"
    pitfalls_output_dir = run_root / "pitfalls_outputs"
    analysis_output_file = run_root / "analysis_results.json"
    issues_output_dir = run_root / "issues_out"

    return (
        somef_output_dir,
        pitfalls_output_dir,
        analysis_output_file,
        issues_output_dir,
    )


def _snapshot_sort_key(snapshot_tag: str) -> tuple[str, int] | None:
    """Return sortable key for snapshot tags matching YYYYMMDD or YYYYMMDD_N."""
    match = SNAPSHOT_TAG_PATTERN.fullmatch(snapshot_tag)
    if match is None:
        return None
    date_part, suffix_part = match.group(1), match.group(2)
    suffix = int(suffix_part) if suffix_part is not None else 0
    return (date_part, suffix)


def find_latest_previous_report(
    output_root: Path,
    run_name: str,
    current_snapshot_tag: str | None,
) -> Path | None:
    """Find latest previous report.json from same run folder."""
    run_root = output_root / run_name
    if not run_root.exists() or not run_root.is_dir():
        return None

    candidates: list[tuple[tuple[str, int], Path]] = []
    for child in run_root.iterdir():
        if not child.is_dir():
            continue
        key = _snapshot_sort_key(child.name)
        if key is None:
            continue
        if current_snapshot_tag is not None and child.name == current_snapshot_tag:
            continue

        report_path = child / "issues_out" / "report.json"
        if report_path.exists():
            candidates.append((key, report_path))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def run_pipeline(
    input_file: Path,
    opt_outs_file: Path,
    output_root: Path,
    dry_run: bool,
    run_name: str | None,
    snapshot_tag: str | None,
    previous_report: Path | None,
) -> None:
    """Run analysis and issue creation for a repository list."""
    run_folder_name = run_name if run_name else input_file.stem
    run_root = output_root / run_folder_name
    resolved_snapshot_tag = _resolve_unique_snapshot_tag(
        run_root=run_root,
        snapshot_tag=snapshot_tag,
    )

    somef_output_dir, pitfalls_output_dir, analysis_output_file, issues_output_dir = (
        _resolve_run_paths(
            output_root=output_root,
            input_file=input_file,
            run_name=run_name,
            snapshot_tag=resolved_snapshot_tag,
        )
    )

    resolved_previous_report = previous_report
    if resolved_previous_report is None and run_name is not None:
        resolved_previous_report = find_latest_previous_report(
            output_root=output_root,
            run_name=run_name,
            current_snapshot_tag=resolved_snapshot_tag,
        )

    repositories = _load_repositories_from_input(input_file)
    previous_records = load_previous_report(resolved_previous_report)
    repositories_to_analyze: list[str] | None = repositories
    pre_skipped_records: list[dict[str, object]] = []

    if repositories is not None and previous_records:
        repositories_to_analyze = []
        for repo_url in repositories:
            previous = previous_records.get(_normalize_repo_url(repo_url))
            if previous is None:
                repositories_to_analyze.append(repo_url)
                continue

            previous_commit_id = _extract_previous_commit(previous)
            if (
                previous_commit_id is None
                or previous_commit_id == "Unknown"
                or not _is_supported_for_commit_skip(repo_url)
            ):
                repositories_to_analyze.append(repo_url)
                continue

            try:
                current_commit_id = _get_repo_head_commit(repo_url)
            except Exception:
                repositories_to_analyze.append(repo_url)
                continue

            if (
                current_commit_id is not None
                and current_commit_id != "Unknown"
                and current_commit_id == previous_commit_id
            ):
                pre_skipped_records.append(
                    _build_repo_not_updated_record(
                        repo_url=repo_url,
                        current_commit_id=current_commit_id,
                        previous_commit_id=previous_commit_id,
                    )
                )
                continue

            repositories_to_analyze.append(repo_url)

    analysis_input_file = input_file
    temp_input_file: Path | None = None
    if repositories_to_analyze is not None and repositories is not None:
        if repositories_to_analyze:
            with NamedTemporaryFile(
                mode="w",
                suffix=".json",
                prefix="pipeline_filtered_",
                delete=False,
                encoding="utf-8",
            ) as temp_file:
                json.dump(
                    {"repositories": repositories_to_analyze}, temp_file, indent=2
                )
                temp_input_file = Path(temp_file.name)
                analysis_input_file = temp_input_file
        else:
            analysis_input_file = input_file

    ran_analysis = True
    if repositories_to_analyze is not None and not repositories_to_analyze:
        ran_analysis = False
    else:
        metacheck_command.main(
            args=[
                "--input",
                str(analysis_input_file),
                "--somef-output",
                str(somef_output_dir),
                "--pitfalls-output",
                str(pitfalls_output_dir),
                "--analysis-output",
                str(analysis_output_file),
            ],
            standalone_mode=False,
        )

    create_issues_args = [
        "--pitfalls-output-dir",
        str(pitfalls_output_dir),
        "--issues-dir",
        str(issues_output_dir),
        "--opt-outs-file",
        str(opt_outs_file),
        "--issue-config-file",
        str(input_file),  # Use default config
        "--analysis-summary-file",
        str(analysis_output_file),
    ]

    if resolved_previous_report is not None:
        create_issues_args.extend(["--previous-report", str(resolved_previous_report)])

    if dry_run:
        create_issues_args.append("--dry-run")

    if ran_analysis:
        create_issues_command.main(args=create_issues_args, standalone_mode=False)

    report_file = issues_output_dir / "report.json"
    if ran_analysis and pre_skipped_records:
        _merge_pre_skipped_records(
            report_file=report_file, skipped_records=pre_skipped_records
        )
    elif not ran_analysis:
        _write_pre_skipped_only_report(
            report_file=report_file,
            dry_run=dry_run,
            analysis_summary_file=analysis_output_file,
            previous_report_source=resolved_previous_report,
            skipped_records=pre_skipped_records,
        )

    if temp_input_file is not None and temp_input_file.exists():
        temp_input_file.unlink()


@click.command()
@click.option(
    "--input-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=DEFAULT_INPUT_FILE,
    show_default=True,
    help="Repository-list JSON input file.",
)
@click.option(
    "--opt-outs-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=DEFAULT_OPTOUT_FILE,
    show_default=True,
    help="JSON file listing repositories to exclude from issue creation.",
)
@click.option(
    "--output-root",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=DEFAULT_OUTPUT_ROOT,
    show_default=True,
    help="Root output directory where run folders are created.",
)
@click.option(
    "--run-name",
    type=str,
    default=None,
    help="Custom folder name under output root. Defaults to input file stem.",
)
@click.option(
    "--snapshot-tag",
    type=str,
    default=None,
    help="Optional snapshot suffix folder (for example 2026-03).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run issue creation in dry-run mode without posting issues.",
)
@click.option(
    "--previous-report",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Previous report.json used for incremental issue handling.",
)
def run_pipeline_command(
    input_file: Path,
    opt_outs_file: Path,
    output_root: Path,
    run_name: str | None,
    snapshot_tag: str | None,
    dry_run: bool,
    previous_report: Path | None,
) -> None:
    """Run full pipeline: metacheck analysis then issue creation."""
    run_pipeline(
        input_file=input_file,
        opt_outs_file=opt_outs_file,
        output_root=output_root,
        dry_run=dry_run,
        run_name=run_name,
        snapshot_tag=snapshot_tag,
        previous_report=previous_report,
    )
