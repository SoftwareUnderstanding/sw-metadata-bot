"""CLI entry point for sw-metadata-bot."""

import click

from .create_issues import create_issues_command
from .metacheck_wrapper import metacheck_command
from .pipeline import run_pipeline_command
from .verify_tokens import verify_tokens_command


@click.group()
def cli():
    """RSMetaCheck bot for pushing issues with existing repository metadata."""
    pass


cli.add_command(metacheck_command, name="metacheck")
cli.add_command(create_issues_command, name="create-issues")
cli.add_command(verify_tokens_command, name="verify-tokens")
cli.add_command(run_pipeline_command, name="run-pipeline")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
