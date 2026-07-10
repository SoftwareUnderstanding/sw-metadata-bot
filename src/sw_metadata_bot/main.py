"""CLI entry point for sw-metadata-bot."""

import click

from .pipeline import run_analysis_command
from .publish import publish_command, simulate_publish_command
from .report_summary import summarize_report_command
from .verify_tokens import verify_tokens_command
from .fetch import fetch_command


@click.group()
def cli():
    """RSMetaCheck bot for metadata issue lifecycle.

    Recommended workflow:
        1) Run analysis and review outputs.
        2) Publish if you are satisfied with the analysis decisions.
    """
    pass


cli.add_command(verify_tokens_command, name="verify-tokens")
cli.add_command(run_analysis_command, name="run-analysis")
cli.add_command(publish_command, name="publish")
cli.add_command(simulate_publish_command, name="simulate-publish")
cli.add_command(summarize_report_command, name="report-summary")
cli.add_command(fetch_command, name="fetch")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
