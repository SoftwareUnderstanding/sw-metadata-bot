import click

from .configuration import configure
from .issue_creator import create_issue
from .metacheck_wrapper import metacheck_command


@click.group()
def cli():
    """RSMetaCheck bot for pushing issues with existing repository metadata."""
    pass


cli.add_command(metacheck_command, name="metacheck")
cli.add_command(configure, name="configure")
cli.add_command(create_issue, name="create-issue")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
