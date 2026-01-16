"""Create issues command - main entry point for issue creation."""

import json
import logging
from pathlib import Path
from typing import Optional

import click

from ..config import PlatformFactory
from ..core import PitfallsAnalyzer, RepositoryError
from ..utils import IssueTemplate, ReportFormatter

logger = logging.getLogger(__name__)


class IssueCreator:
    """Orchestrates the issue creation workflow."""

    def __init__(self, dry_run: bool = False):
        """
        Initialize the issue creator.

        Args:
            dry_run: If True, simulate operations without making actual API calls
        """
        self.factory = PlatformFactory()
        self.factory.set_dry_run(dry_run)
        self.dry_run = dry_run
        self.analyzer = PitfallsAnalyzer()
        self.issues_created = []
        self.issues_failed = []

    def process_pitfalls_file(
        self,
        pitfalls_file: Path,
        output_dir: Path,
        save_body: bool = True,
    ) -> Optional[dict]:
        """
        Process a single pitfalls file and create an issue.

        Args:
            pitfalls_file: Path to the pitfalls JSON-LD file
            output_dir: Directory to save issue bodies
            save_body: If True, save the generated issue body to file

        Returns:
            Dictionary with issue creation result or None if failed
        """
        try:
            # Load and validate pitfalls data
            pitfalls_data = self.analyzer.load_pitfalls(pitfalls_file)

            # Extract repository information
            repo_url = self.analyzer.get_repository_url(pitfalls_data)
            click.echo(f"  Repository: {repo_url}")

            # Generate report and issue body
            report_content = ReportFormatter.format_pitfalls_report(
                repo_url, pitfalls_data
            )
            issue_body = IssueTemplate.create_issue_body(report_content)

            # Optionally save issue body for reference
            if save_body:
                body_file = output_dir / f"issue_body_{pitfalls_file.stem}.md"
                with open(body_file, "w", encoding="utf-8") as f:
                    f.write(issue_body)
                click.echo(f"  Issue body saved to: {body_file}")

            # Create platform instance and issue
            platform = self.factory.create_platform_from_url(repo_url)
            repository = platform.parse_repository_url(repo_url)

            issue_title = "Automated Metadata Quality Report from CodeMetaSoft"
            issue = platform.create_issue(repository, issue_title, issue_body)

            # Record success
            result = {
                "status": "created" if issue.url else "dry_run",
                "repo_url": repo_url,
                "issue_url": issue.url or f"{repo_url}/issues/0",
                "platform": platform.platform_name,
                "dry_run": self.dry_run,
                "created_at": ReportFormatter.get_current_timestamp(),
                "pitfalls_count": len(self.analyzer.get_pitfalls_list(pitfalls_data)),
            }

            self.issues_created.append(result)
            click.echo(f"  ✓ Issue created: {result['issue_url']}")
            return result

        except RepositoryError as e:
            self._handle_error(pitfalls_file, str(e))
            return None
        except Exception as e:
            self._handle_error(pitfalls_file, f"Unexpected error: {e}")
            return None

    def _handle_error(self, pitfalls_file: Path, error_msg: str) -> None:
        """Record and log an error."""
        error_record = {
            "file": str(pitfalls_file),
            "error": error_msg,
            "timestamp": ReportFormatter.get_current_timestamp(),
        }
        self.issues_failed.append(error_record)
        click.echo(f"  ✗ Error: {error_msg}", err=True)

    def save_report(
        self,
        output_dir: Path,
        created_issues_file: str = "created_issues_report.json",
        failed_issues_file: str = "failed_issues_report.json",
    ) -> None:
        """
        Save creation results to JSON files.

        Args:
            output_dir: Directory to save reports
            created_issues_file: Filename for successful creations
            failed_issues_file: Filename for failures
        """
        created_file = output_dir / created_issues_file
        with open(created_file, "w", encoding="utf-8") as f:
            json.dump(self.issues_created, f, indent=2)
        click.echo(f"Created issues report: {created_file}")

        if self.issues_failed:
            failed_file = output_dir / failed_issues_file
            with open(failed_file, "w", encoding="utf-8") as f:
                json.dump(self.issues_failed, f, indent=2)
            click.echo(f"Failed issues report: {failed_file}")

    @property
    def summary(self) -> str:
        """Get a summary of the operation."""
        return (
            f"Created: {len(self.issues_created)} | Failed: {len(self.issues_failed)}"
        )


@click.command()
@click.option(
    "--pitfalls-output-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Directory containing pitfalls JSON-LD files from metacheck analysis.",
)
@click.option(
    "--issues-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path.cwd(),
    help="Directory to save issue bodies and reports.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate issue creation without actually posting to repositories.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Logging level.",
)
def create_issues_command(
    pitfalls_output_dir: Path,
    issues_dir: Path,
    dry_run: bool,
    log_level: str,
):
    """
    Create issues in repositories based on metadata analysis results.

    This command processes pitfalls files generated by the metacheck tool
    and creates corresponding issues in the analyzed repositories.
    """
    # Setup logging
    logging.basicConfig(
        level=log_level.upper(),
        format="%(levelname)s: %(message)s",
    )

    # Create output directory
    issues_dir.mkdir(parents=True, exist_ok=True)

    # Initialize creator
    creator = IssueCreator(dry_run=dry_run)
    mode = "DRY RUN" if dry_run else "PRODUCTION"
    click.echo(f"\n{'=' * 60}")
    click.echo(f"Creating issues [{mode}]")
    click.echo(f"{'=' * 60}\n")

    # Find pitfalls files
    pitfalls_files = sorted(pitfalls_output_dir.glob("*.jsonld"))
    if not pitfalls_files:
        click.echo(
            f"No pitfalls files found in {pitfalls_output_dir}",
            err=True,
        )
        return

    click.echo(f"Found {len(pitfalls_files)} pitfalls files to process\n")

    # Process each file
    for i, pitfalls_file in enumerate(pitfalls_files, 1):
        click.echo(f"[{i}/{len(pitfalls_files)}] Processing: {pitfalls_file.name}")
        creator.process_pitfalls_file(pitfalls_file, issues_dir)
        click.echo()

    # Save reports
    creator.save_report(issues_dir)

    # Display summary
    click.echo(f"{'=' * 60}")
    click.echo(f"Summary: {creator.summary}")
    click.echo(f"{'=' * 60}\n")

    if creator.issues_failed:
        click.echo(
            f"⚠️  {len(creator.issues_failed)} issues failed to create.", err=True
        )
        return 1

    return 0
