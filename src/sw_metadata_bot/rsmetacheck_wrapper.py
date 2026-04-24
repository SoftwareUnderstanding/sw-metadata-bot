"""Wrapper for rsmetacheck CLI to integrate with sw-metadata-bot."""

import sys

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
