"""Publish issues from an existing analysis snapshot."""

import json
from datetime import datetime, timezone
from pathlib import Path

import click

from . import github_api, gitlab_api, pitfalls
from .config_utils import get_custom_message, load_config, sanitize_repo_name


def _is_unsubscribe_comment(comment: str) -> bool:
    """Return True when a comment is exactly the unsubscribe keyword."""
    return comment.strip().lower() == "unsubscribe"


def _build_counters(records: list[dict[str, object]]) -> dict[str, int]:
    """Build publish outcome counters from report records."""
    return {
        "total": len(records),
        "created": sum(1 for r in records if r.get("action") == "created"),
        "simulated": sum(1 for r in records if r.get("action") == "simulated_created"),
        "updated_by_comment": sum(
            1 for r in records if r.get("action") == "updated_by_comment"
        ),
        "closed": sum(1 for r in records if r.get("action") == "closed"),
        "skipped": sum(1 for r in records if r.get("action") == "skipped"),
        "failed": sum(1 for r in records if r.get("action") == "failed"),
    }


def _detect_platform_for_publish(repo_url: str, record: dict[str, object]) -> str:
    """Resolve platform for publish from record metadata and repository URL."""
    value = record.get("platform")
    if isinstance(value, str) and value:
        if value in {"github", "gitlab", "gitlab.com"}:
            return value

    lowered = repo_url.lower()
    if "github.com" in lowered:
        return "github"
    if "gitlab" in lowered:
        return "gitlab"
    raise click.ClickException(f"Unsupported platform for repository: {repo_url}")


def _load_publish_body(analysis_root: Path, repo_url: str) -> str:
    """Load issue body from report file, with pitfall-based fallback if needed."""
    repo_folder = analysis_root / sanitize_repo_name(repo_url)
    issue_report_file = repo_folder / "issue_report.md"
    if issue_report_file.exists():
        return issue_report_file.read_text(encoding="utf-8")

    pitfall_file = repo_folder / "pitfall.jsonld"
    if not pitfall_file.exists():
        raise click.ClickException(
            f"Missing issue body and pitfall file for repository: {repo_url}"
        )

    data = pitfalls.load_pitfalls(pitfall_file)
    config_file = analysis_root / "config.json"
    custom_message = None
    if config_file.exists():
        custom_message = get_custom_message(load_config(config_file))
    report = pitfalls.format_report(repo_url, data)
    return pitfalls.create_issue_body(report, custom_message)


def _issue_url_for_publish(record: dict[str, object]) -> str | None:
    """Return best available issue URL from record lineage fields."""
    current = record.get("issue_url")
    if isinstance(current, str) and current:
        return current
    previous = record.get("previous_issue_url")
    if isinstance(previous, str) and previous:
        return previous
    simulated = record.get("simulated_issue_url")
    if isinstance(simulated, str) and simulated:
        return simulated
    return None


def _write_per_repo_report(
    analysis_root: Path,
    record: dict[str, object],
    analysis_summary_file: str | None,
) -> None:
    """Persist a single-record per-repo report alongside repository artifacts."""
    repo_url = record.get("repo_url")
    if not isinstance(repo_url, str) or not repo_url:
        return

    report_path = analysis_root / sanitize_repo_name(repo_url) / "report.json"
    run_metadata: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": False,
        "analysis_summary_file": analysis_summary_file,
    }
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            existing = json.load(f)
        existing_meta = (
            existing.get("run_metadata") if isinstance(existing, dict) else None
        )
        if isinstance(existing_meta, dict):
            run_metadata.update(existing_meta)
            run_metadata["generated_at"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            run_metadata["dry_run"] = False

    payload = {
        "run_metadata": run_metadata,
        "counters": _build_counters([record]),
        "records": [record],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def publish_analysis(analysis_root: Path) -> None:
    """Publish issues from an existing analysis snapshot without re-running analysis."""
    run_report_file = analysis_root / "run_report.json"
    if not run_report_file.exists():
        raise click.ClickException(f"Missing run_report.json in {analysis_root}")

    with open(run_report_file, encoding="utf-8") as f:
        run_report = json.load(f)

    records = run_report.get("records") if isinstance(run_report, dict) else None
    if not isinstance(records, list):
        raise click.ClickException(
            f"Invalid run_report.json format in {run_report_file}: records must be a list"
        )

    github_client = github_api.GitHubAPI(dry_run=False)
    gitlab_client = gitlab_api.GitLabAPI(dry_run=False)

    updated_records: list[dict[str, object]] = []
    skipped_published = 0
    for raw_record in records:
        if not isinstance(raw_record, dict):
            continue

        record = dict(raw_record)
        repo_url = record.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url:
            updated_records.append(record)
            continue

        if record.get("dry_run") is False:
            skipped_published += 1
            updated_records.append(record)
            continue

        action = str(record.get("action", ""))
        platform = _detect_platform_for_publish(repo_url, record)
        issue_url = _issue_url_for_publish(record)

        try:
            if action in {"updated_by_comment", "closed"}:
                if not issue_url:
                    raise click.ClickException(
                        f"Missing issue URL for publish action {action}: {repo_url}"
                    )

                issue_client = github_client if platform == "github" else gitlab_client
                comments = issue_client.get_issue_comments(issue_url)
                unsubscribe_detected = any(
                    _is_unsubscribe_comment(comment) for comment in comments
                )
                if unsubscribe_detected:
                    record["action"] = "skipped"
                    record["reason_code"] = "unsubscribe"
                    record["unsubscribe_detected"] = True
                    record["dry_run"] = False
                    record["issue_persistence"] = "none"
                    record.pop("simulated_issue_url", None)
                    updated_records.append(record)
                    analysis_summary_value = run_report.get("run_metadata", {}).get(
                        "analysis_summary_file"
                    )
                    _write_per_repo_report(
                        analysis_root,
                        record,
                        (
                            analysis_summary_value
                            if isinstance(analysis_summary_value, str)
                            else None
                        ),
                    )
                    continue

            if action == "simulated_created":
                body = _load_publish_body(analysis_root, repo_url)
                title = "Automated Metadata Quality Report from CodeMetaSoft"
                issue_client = github_client if platform == "github" else gitlab_client
                created_url = issue_client.create_issue(repo_url, title, body)

                record["action"] = "created"
                record["issue_url"] = created_url
                record["dry_run"] = False
                record["issue_persistence"] = "posted"
                record.pop("simulated_issue_url", None)

            elif action == "updated_by_comment":
                if not issue_url:
                    raise click.ClickException(
                        f"Missing previous issue URL for repo: {repo_url}"
                    )

                body = _load_publish_body(analysis_root, repo_url)
                issue_client = github_client if platform == "github" else gitlab_client
                issue_client.add_issue_comment(
                    issue_url,
                    f"New analysis detected updated findings.\n\n{body}",
                )

                record["issue_url"] = issue_url
                record["dry_run"] = False
                record["issue_persistence"] = "posted"
                record.pop("simulated_issue_url", None)

            elif action == "closed":
                if not issue_url:
                    raise click.ClickException(
                        f"Missing previous issue URL for repo: {repo_url}"
                    )

                issue_client = github_client if platform == "github" else gitlab_client
                issue_client.add_issue_comment(
                    issue_url,
                    "The latest analysis no longer reports metadata pitfalls/warnings. "
                    "Closing this issue.",
                )
                issue_client.close_issue(issue_url)

                record["issue_url"] = issue_url
                record["previous_issue_state"] = "closed"
                record["dry_run"] = False
                record["issue_persistence"] = "posted"
                record.pop("simulated_issue_url", None)

            elif action == "skipped":
                record["dry_run"] = False
                record["issue_persistence"] = "none"
                record.pop("simulated_issue_url", None)

            else:
                record["dry_run"] = False
                record.pop("simulated_issue_url", None)

        except Exception as exc:
            record["action"] = "failed"
            record["reason_code"] = "publish_exception"
            record["error"] = str(exc)

        updated_records.append(record)
        analysis_summary_value = run_report.get("run_metadata", {}).get(
            "analysis_summary_file"
        )
        _write_per_repo_report(
            analysis_root,
            record,
            analysis_summary_value if isinstance(analysis_summary_value, str) else None,
        )

    run_report["records"] = updated_records
    run_report["counters"] = _build_counters(updated_records)
    run_metadata = (
        run_report.get("run_metadata") if isinstance(run_report, dict) else None
    )
    if not isinstance(run_metadata, dict):
        run_metadata = {}
        run_report["run_metadata"] = run_metadata
    run_metadata["dry_run"] = False
    run_metadata["published_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    run_metadata["idempotency_skipped_records"] = skipped_published

    with open(run_report_file, "w", encoding="utf-8") as f:
        json.dump(run_report, f, indent=2)


@click.command()
@click.option(
    "--analysis-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Existing analysis snapshot folder containing run_report.json.",
)
def publish_command(analysis_root: Path) -> None:
    """Publish issues using precomputed decisions from an analysis snapshot."""
    publish_analysis(analysis_root)
