"""Wrapper for metacheck CLI to integrate with sw-metadata-bot."""

import sys

import click
from metacheck import cli as metacheck_cli


@click.command()
@click.option(
    "--input",
    multiple=False,
    required=True,
    help="Repository URL or JSON file path containing repositories to analyze.",
)
@click.option(
    "--skip-somef",
    is_flag=True,
    default=False,
    help="Skip SoMEF execution and analyze existing SoMEF output files directly.",
)
@click.option(
    "--pitfalls-output",
    default="pitfalls_outputs",
    help="Directory to store pitfall JSON-LD files.",
)
@click.option(
    "--analysis-output",
    default="analysis_results.json",
    help="File path for summary results.",
)
@click.option(
    "--threshold",
    type=float,
    default=0.8,
    help="SoMEF confidence threshold (default: 0.8).",
)
def metacheck_command(input, skip_somef, pitfalls_output, analysis_output, threshold):
    """Run metacheck to detect metadata pitfalls in repositories."""
    # Convert click arguments to sys.argv format for metacheck's argparse
    argv = ["metacheck"]

    # Add input files
    argv.extend(["--input", input.strip()])

    if skip_somef:
        argv.append("--skip-somef")

    argv.extend(["--pitfalls-output", pitfalls_output])
    argv.extend(["--analysis-output", analysis_output])
    argv.extend(["--threshold", str(threshold)])

    # Call metacheck CLI with modified sys.argv
    original_argv = sys.argv
    try:
        sys.argv = argv
        metacheck_cli()
    finally:
        sys.argv = original_argv
