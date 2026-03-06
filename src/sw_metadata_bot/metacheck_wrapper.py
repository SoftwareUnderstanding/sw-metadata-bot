"""Wrapper for metacheck CLI to integrate with sw-metadata-bot."""

import json
import re
import sys
import tempfile
from pathlib import Path

import click
from metacheck import cli as metacheck_cli

DEFAULT_OPT_OUTS_FILE = Path(".opt-outs")


def _pattern_to_regex(pattern: str) -> re.Pattern:
    """Compile an opt-outs pattern into a regex.

    Entries may be plain URLs (exact match) or patterns using ``*`` as a
    wildcard (e.g. ``https://github.com/MyOrg/*``).  The pattern is first
    escaped with :func:`re.escape` so that URL characters such as ``.`` and
    ``/`` are treated as literals, then the escaped form of ``*`` (``\\*``) is
    replaced with ``.*`` to restore wildcard behaviour.

    :param pattern: An opt-outs entry after trailing-slash stripping.
    :return: Compiled regex pattern for ``re.fullmatch``.
    """
    escaped = re.escape(pattern)
    regex = escaped.replace(r"\*", ".*")
    return re.compile(regex)


def _is_opted_out(url: str, patterns: list[str]) -> bool:
    """Return True if *url* matches any opt-outs pattern.

    :param url: Repository URL to test (trailing slash already stripped).
    :param patterns: List of raw opt-outs entries from the opt-outs file.
    :return: True when url matches at least one pattern.
    """
    normalized = url.strip().rstrip("/")
    for pattern in patterns:
        try:
            if re.fullmatch(_pattern_to_regex(pattern.strip().rstrip("/")), normalized):
                return True
        except re.error as exc:
            click.echo(
                f"Warning: invalid opt-outs pattern ignored ({pattern!r}): {exc}",
                err=True,
            )
    return False


def _filter_opt_out_repos(input_path: str, opt_outs_file: Path) -> str:
    """Return a temp file path with opted-out repos removed from the input JSON.

    Each entry in the opt-outs ``repositories`` list is treated as a pattern
    where ``*`` acts as a wildcard (e.g. ``https://github.com/MyOrg/*``).
    Full Python regex syntax is also accepted.

    :param input_path: Path to the input JSON file containing repository list.
    :param opt_outs_file: Path to the JSON file containing opted-out repos.
    :return: Path to a temporary filtered JSON file.
    :raises click.ClickException: If opt-outs file has invalid format.
    """
    with open(opt_outs_file, encoding="utf-8") as f:
        opt_outs_data = json.load(f)

    opted_out = opt_outs_data.get("repositories", [])
    if not isinstance(opted_out, list):
        raise click.ClickException(
            f"Invalid format in {opt_outs_file}: 'repositories' must be a list"
        )
    patterns = [url for url in opted_out if isinstance(url, str)]

    with open(input_path, encoding="utf-8") as f:
        input_data = json.load(f)

    original_repos = input_data.get("repositories", [])
    filtered_repos = [
        url
        for url in original_repos
        if isinstance(url, str) and not _is_opted_out(url, patterns)
    ]

    skipped = len(original_repos) - len(filtered_repos)
    if skipped > 0:
        click.echo(
            f"Opt-outs: skipping {skipped} opted-out "
            f"{'repository' if skipped == 1 else 'repositories'} from analysis."
        )

    filtered_data = {**input_data, "repositories": filtered_repos}

    tmp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(filtered_data, tmp_file)
    tmp_file.flush()
    tmp_file.close()
    return tmp_file.name


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
@click.option(
    "--opt-outs",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_OPT_OUTS_FILE,
    show_default=True,
    help=(
        "JSON file listing repositories (or patterns) to exclude from analysis. "
        "Defaults to .opt-outs in the current directory; "
        "silently ignored when the file does not exist."
    ),
)
def metacheck_command(
    input, skip_somef, pitfalls_output, analysis_output, threshold, opt_outs
):
    """Run metacheck to detect metadata pitfalls in repositories."""
    # Apply opt-outs filtering when input is a JSON file (not a single URL)
    effective_input = input.strip()
    tmp_input_path = None
    if opt_outs is not None and opt_outs.is_file() and Path(effective_input).is_file():
        tmp_input_path = _filter_opt_out_repos(effective_input, opt_outs)
        effective_input = tmp_input_path

    # Convert click arguments to sys.argv format for metacheck's argparse
    argv = ["metacheck"]

    # Add input files
    argv.extend(["--input", effective_input])

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
        if tmp_input_path is not None:
            Path(tmp_input_path).unlink(missing_ok=True)
