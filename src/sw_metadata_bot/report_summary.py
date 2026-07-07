import json
from collections import Counter
from pathlib import Path

import click

from . import constants
from .reporting import RunReport, load_report


@click.command()
@click.option(
    "--analysis-root",
    type=click.Path(exists=True, dir_okay=True, path_type=Path),
    default=None,
    help="Previous run_report.json used for incremental issue handling.",
)
def summarize_report_command(analysis_root: Path):
    """Summarize report.json file and save the summary file in the analysis root folder."""
    summary = summarize_analysis_folder(analysis_root)

    save_summary_report(analysis_root, summary)


def summarize_report(report: RunReport) -> dict[str, object]:
    """Build a compact summary for plotting and comparison."""
    repository_count = len(report.records)

    pitfalls_by_id: Counter[str] = Counter()
    warnings_by_id: Counter[str] = Counter()
    total_pitfalls = 0
    total_warnings = 0
    issues_created = 0
    actions: Counter[str] = Counter()
    reason_codes: Counter[str] = Counter()
    reason_codes_by_action: dict[str, Counter[str]] = {}

    for record in report.records:
        for pitfall_id in record.pitfalls_ids:
            pitfalls_by_id[pitfall_id] += 1
        for warning_id in record.warnings_ids:
            warnings_by_id[warning_id] += 1

        total_pitfalls += int(record.pitfalls_count or 0)
        total_warnings += int(record.warnings_count or 0)

        if record.action == constants.ACTION_CREATED:
            issues_created += 1

        if record.action is not None:
            actions[record.action] += 1
            reason_codes_by_action.setdefault(record.action, Counter())

        if record.reason_code is not None:
            reason_codes[record.reason_code] += 1
            if record.action is not None:
                reason_codes_by_action[record.action][record.reason_code] += 1

    reason_code_percentages_by_action: dict[str, dict[str, float]] = {}
    for action_name, counter in reason_codes_by_action.items():
        total_for_action = sum(counter.values())
        if total_for_action == 0:
            reason_code_percentages_by_action[action_name] = {}
            continue
        reason_code_percentages_by_action[action_name] = {
            reason_code: (count / total_for_action) * 100.0
            for reason_code, count in sorted(counter.items())
        }

    return {
        "repository_count": repository_count,
        "pitfalls_by_id": dict(sorted(pitfalls_by_id.items())),
        "warnings_by_id": dict(sorted(warnings_by_id.items())),
        "total_pitfalls": total_pitfalls,
        "total_warnings": total_warnings,
        "issues_created": issues_created,
        "actions": dict(sorted(actions.items())),
        "reason_codes": dict(sorted(reason_codes.items())),
        "reason_codes_by_action": {
            action_name: dict(sorted(counter.items()))
            for action_name, counter in sorted(reason_codes_by_action.items())
        },
        "reason_code_percentages_by_action": {
            action_name: dict(sorted(percentages.items()))
            for action_name, percentages in sorted(
                reason_code_percentages_by_action.items()
            )
        },
        "pitfalls_per_repository": (
            total_pitfalls / repository_count if repository_count else 0.0
        ),
        "warnings_per_repository": (
            total_warnings / repository_count if repository_count else 0.0
        ),
        "issues_created_per_repository": (
            issues_created / repository_count if repository_count else 0.0
        ),
    }


def summarize_analysis_folder(analysis_folder: Path | str) -> dict[str, object]:
    """Load run_report.json from an analysis directory and summarize it."""
    analysis_path = Path(analysis_folder)
    report_path = analysis_path / constants.FILENAME_RUN_REPORT
    if analysis_path.is_file():
        report_path = analysis_path

    return summarize_report(load_report(report_path))


def save_summary_report(analysis_folder: Path, summary_data: dict):
    """Save summary of the analysis"""
    if summary_data:
        summary_path = analysis_folder / constants.FILENAME_REPORT_SUMMARY
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
    else:
        print("Error: No summary info")


if __name__ == "__main__":
    analysis_root = Path("./outputs/ossr/20260702/")

    summary = summarize_analysis_folder(analysis_root)

    save_summary_report(analysis_root, summary)
