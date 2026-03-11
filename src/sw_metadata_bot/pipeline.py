"""Pipeline command to run analysis then issue creation."""

import re
from pathlib import Path

import click

from .create_issues import create_issues_command
from .metacheck_wrapper import metacheck_command

DEFAULT_INPUT_FILE = Path("assets/opt-ins.json")
DEFAULT_OPTOUT_FILE = Path("assets/opt-outs.json")
DEFAULT_OUTPUT_ROOT = Path("outputs")
SNAPSHOT_TAG_PATTERN = re.compile(r"^(\d{8})(?:_(\d+))?$")


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
    somef_output_dir, pitfalls_output_dir, analysis_output_file, issues_output_dir = (
        _resolve_run_paths(
            output_root=output_root,
            input_file=input_file,
            run_name=run_name,
            snapshot_tag=snapshot_tag,
        )
    )

    metacheck_command.main(
        args=[
            "--input",
            str(input_file),
            "--somef-output",
            str(somef_output_dir),
            "--pitfalls-output",
            str(pitfalls_output_dir),
            "--analysis-output",
            str(analysis_output_file),
        ],
        standalone_mode=False,
    )

    resolved_previous_report = previous_report
    if resolved_previous_report is None and run_name is not None:
        resolved_previous_report = find_latest_previous_report(
            output_root=output_root,
            run_name=run_name,
            current_snapshot_tag=snapshot_tag,
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

    create_issues_command.main(args=create_issues_args, standalone_mode=False)


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
