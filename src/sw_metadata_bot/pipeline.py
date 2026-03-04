"""Pipeline command to run analysis then issue creation."""

from pathlib import Path

import click

from .create_issues import create_issues_command
from .metacheck_wrapper import metacheck_command

DEFAULT_INPUT_FILE = Path("assets/opt-ins.json")
DEFAULT_OPTOUT_FILE = Path("assets/opt-outs.json")
DEFAULT_OUTPUT_ROOT = Path("outputs")


def _resolve_run_paths(
    output_root: Path,
    input_file: Path,
    run_name: str | None,
    snapshot_tag: str | None,
) -> tuple[Path, Path, Path]:
    """Compute dedicated output paths for a pipeline run."""
    run_folder_name = run_name if run_name else input_file.stem
    run_root = output_root / run_folder_name

    if snapshot_tag:
        run_root = run_root / snapshot_tag

    pitfalls_output_dir = run_root / "pitfalls_outputs"
    analysis_output_file = run_root / "analysis_results.json"
    issues_output_dir = run_root / "issues_out"

    return pitfalls_output_dir, analysis_output_file, issues_output_dir


def run_pipeline(
    input_file: Path,
    opt_outs_file: Path,
    output_root: Path,
    dry_run: bool,
    run_name: str | None,
    snapshot_tag: str | None,
) -> None:
    """Run analysis and issue creation for a repository list."""
    pitfalls_output_dir, analysis_output_file, issues_output_dir = _resolve_run_paths(
        output_root=output_root,
        input_file=input_file,
        run_name=run_name,
        snapshot_tag=snapshot_tag,
    )

    metacheck_command.main(
        args=[
            "--input",
            str(input_file),
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
    ]

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
def run_pipeline_command(
    input_file: Path,
    opt_outs_file: Path,
    output_root: Path,
    run_name: str | None,
    snapshot_tag: str | None,
    dry_run: bool,
) -> None:
    """Run full pipeline: metacheck analysis then issue creation."""
    run_pipeline(
        input_file=input_file,
        opt_outs_file=opt_outs_file,
        output_root=output_root,
        dry_run=dry_run,
        run_name=run_name,
        snapshot_tag=snapshot_tag,
    )
