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
    "--somef-output",
    default="somef_outputs",
    help="Directory to store SoMEF output files.",
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
def rsmetacheck_command(
    input, skip_somef, somef_output, pitfalls_output, analysis_output, threshold
):
    """Run rsmetacheck to detect metadata pitfalls in repositories."""
    # Convert click arguments to sys.argv format for rsmetacheck's argparse
    argv = ["rsmetacheck"]

    # Add input files
    argv.extend(["--input", input.strip()])

    if skip_somef:
        argv.append("--skip-somef")
    argv.extend(["--somef-output", somef_output])
    argv.extend(["--pitfalls-output", pitfalls_output])
    argv.extend(["--analysis-output", analysis_output])
    argv.extend(["--threshold", str(threshold)])

    # Add verbose flag for more detailed output from metacheck
    # jsonld file will also contains pitfalls and warnings that have not been detected.
    argv.extend(["--verbose"])

    # Call metacheck CLI with modified sys.argv
    original_argv = sys.argv
    try:
        sys.argv = argv
        metacheck_cli()
    finally:
        sys.argv = original_argv
