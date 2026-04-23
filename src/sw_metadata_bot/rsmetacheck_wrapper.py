"""Wrapper for rsmetacheck CLI to integrate with sw-metadata-bot."""

import sys

import click
from rsmetacheck import cli as rsmetacheck_cli


def run_rsmetacheck(
    *,
    input_source: str,
    skip_somef: bool = False,
    somef_output: str = "somef_outputs",
    pitfalls_output: str = "pitfalls_outputs",
    analysis_output: str = "analysis_results.json",
    threshold: float = 0.8,
    generate_codemeta: bool = False,
) -> None:
    """Run rsmetacheck CLI by constructing and forwarding argv."""
    argv = ["rsmetacheck"]

    argv.extend(["--input", input_source.strip()])
    argv.extend(["--somef-output", somef_output])
    argv.extend(["--pitfalls-output", pitfalls_output])
    argv.extend(["--analysis-output", analysis_output])
    argv.extend(["--threshold", str(threshold)])

    if skip_somef:
        argv.append("--skip-somef")
    if generate_codemeta:
        argv.append("--generate-codemeta")

    # jsonld output also includes non-detected checks when verbose is enabled.
    argv.append("--verbose")

    original_argv = sys.argv
    try:
        sys.argv = argv
        rsmetacheck_cli()
    finally:
        sys.argv = original_argv


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
@click.option(
    "--generate-codemeta",
    is_flag=True,
    default=False,
    help="Generate a codemeta.json suggestion from SOMEF output when no codemeta.json is detected.",
)
def rsmetacheck_command(
    input,
    skip_somef,
    somef_output,
    pitfalls_output,
    analysis_output,
    threshold,
    generate_codemeta,
):
    """Run rsmetacheck to detect metadata pitfalls in repositories."""
    run_rsmetacheck(
        input_source=input,
        skip_somef=skip_somef,
        somef_output=somef_output,
        pitfalls_output=pitfalls_output,
        analysis_output=analysis_output,
        threshold=threshold,
        generate_codemeta=generate_codemeta,
    )
