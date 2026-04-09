"""Publish issues from an existing analysis snapshot."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import click

from . import github_api, gitlab_api, pitfalls
from .config_utils import (
    detect_platform,
    get_custom_message,
    load_config,
    sanitize_repo_name,
)
from .reporting import build_counters, write_report_file

MAX_PUBLISH_RETRY_ATTEMPTS = 3


def _is_unsubscribe_comment(comment: str) -> bool:
    """Return True when a comment is exactly the unsubscribe keyword."""
    return comment.strip().lower() == "unsubscribe"


def _now_utc_iso() -> str:
    """Return a UTC timestamp suitable for report persistence."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_datetime(value: object) -> datetime | None:
    """Parse an ISO UTC timestamp persisted in publish records."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _retry_after_seconds_from_error(error_text: str) -> int:
    """Infer a retry delay from a publish error string."""
    lowered = error_text.lower()
    if "429" in lowered or "rate limit" in lowered or "too many requests" in lowered:
        return 300
    if (
        "timeout" in lowered
        or "temporarily unavailable" in lowered
        or "connection" in lowered
    ):
        return 60
    if any(code in lowered for code in ["500", "502", "503", "504"]):
        return 120
    return 30


def _is_transient_publish_error(error_text: str) -> bool:
    """Return True when the error likely represents a transient API failure."""
    lowered = error_text.lower()
    if any(code in lowered for code in ["401", "403", "404"]):
        return False
    if "unauthorized" in lowered or "forbidden" in lowered or "not found" in lowered:
        return False
    if "invalid token" in lowered or "insufficient" in lowered:
        return False
    return True


def _clear_failure_metadata(record: dict[str, object]) -> None:
    """Remove retry/failure bookkeeping after a successful publish action."""
    record.pop("error", None)
    record.pop("retry_attempt", None)
    record.pop("is_transient_error", None)
    record.pop("retry_after_seconds", None)
    record.pop("failed_at", None)


def _resolve_retry_action(record: dict[str, object]) -> str | None:
    """Resolve the original action to re-attempt for a failed publish record."""
    last_publish_action = record.get("last_publish_action")
    if isinstance(last_publish_action, str) and last_publish_action:
        return last_publish_action

    # Backward-compatible fallback for failed records created before retry metadata.
    simulated_issue_url = record.get("simulated_issue_url")
    if isinstance(simulated_issue_url, str) and simulated_issue_url:
        return "simulated_created"
    return None


def _can_retry_failed_record(record: dict[str, object]) -> bool:
    """Return True when a failed record is eligible for a new publish attempt."""
    if record.get("is_transient_error") is False:
        return False

    retry_attempt = record.get("retry_attempt")
    attempt_count = retry_attempt if isinstance(retry_attempt, int) else 0
    if attempt_count >= MAX_PUBLISH_RETRY_ATTEMPTS:
        return False

    retry_after_value = record.get("retry_after_seconds")
    retry_after_seconds = retry_after_value if isinstance(retry_after_value, int) else 0
    failed_at = _parse_utc_datetime(record.get("failed_at"))
    if failed_at is None or retry_after_seconds <= 0:
        return True

    return datetime.now(timezone.utc) >= failed_at + timedelta(
        seconds=retry_after_seconds
    )


def _build_counters(records: list[dict[str, object]]) -> dict[str, int]:
    """Build publish outcome counters from report records."""
    return build_counters(records)


def _detect_platform_for_publish(repo_url: str, record: dict[str, object]) -> str:
    """Resolve platform for publish from record metadata and repository URL."""
    value = record.get("platform")
    if isinstance(value, str) and value:
        if value in {"github", "gitlab", "gitlab.com"}:
            return value

    platform = detect_platform(repo_url)
    if platform is None:
        raise click.ClickException(f"Unsupported platform for repository: {repo_url}")
    return platform


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
    analysis_summary_file: Path | None,
    previous_report: Path | None,
) -> None:
    """Persist a single-record per-repo report alongside repository artifacts."""
    repo_url = record.get("repo_url")
    if not isinstance(repo_url, str) or not repo_url:
        return

    write_report_file(
        report_file=analysis_root / sanitize_repo_name(repo_url) / "report.json",
        records=[record],
        dry_run=False,
        run_root=analysis_root.parent,
        analysis_summary_file=analysis_summary_file,
        previous_report=previous_report,
    )


def publish_analysis(analysis_root: Path, retry_failed: bool = False) -> None:
    """Publish issues from an existing analysis snapshot without re-running analysis."""
    run_report_file = analysis_root / "run_report.json"
    if not run_report_file.exists():
        raise click.ClickException(f"Missing run_report.json in {analysis_root}")

    with open(run_report_file, encoding="utf-8") as f:
        run_report = json.load(f)

    run_metadata = (
        run_report.get("run_metadata") if isinstance(run_report, dict) else None
    )
    if not isinstance(run_metadata, dict):
        run_metadata = {}
    analysis_summary_value = run_metadata.get("analysis_summary_file")
    previous_report_value = run_metadata.get("previous_report_source")
    analysis_summary_file = (
        Path(analysis_summary_value)
        if isinstance(analysis_summary_value, str)
        else None
    )
    previous_report = (
        Path(previous_report_value) if isinstance(previous_report_value, str) else None
    )

    records = run_report.get("records") if isinstance(run_report, dict) else None
    if not isinstance(records, list):
        raise click.ClickException(
            f"Invalid run_report.json format in {run_report_file}: records must be a list"
        )

    github_client: github_api.GitHubAPI | None = None
    gitlab_client: gitlab_api.GitLabAPI | None = None

    def issue_client_for_platform(platform: str):
        """Return lazily initialized issue client for the requested platform."""
        nonlocal github_client, gitlab_client
        if platform == "github":
            if github_client is None:
                github_client = github_api.GitHubAPI(dry_run=False)
            return github_client

        if platform in {"gitlab", "gitlab.com"}:
            if gitlab_client is None:
                gitlab_client = gitlab_api.GitLabAPI(dry_run=False)
            return gitlab_client

        raise click.ClickException(f"Unsupported platform for publish: {platform}")

    updated_records: list[dict[str, object]] = []
    skipped_published = 0
    skipped_failed_retry = 0
    for raw_record in records:
        if not isinstance(raw_record, dict):
            continue

        record = dict(raw_record)
        repo_url = record.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url:
            updated_records.append(record)
            continue

        if record.get("dry_run") is False and record.get("action") != "failed":
            skipped_published += 1
            updated_records.append(record)
            continue

        action = str(record.get("action", ""))
        if action == "failed":
            if not retry_failed:
                skipped_failed_retry += 1
                updated_records.append(record)
                continue

            if not _can_retry_failed_record(record):
                skipped_failed_retry += 1
                updated_records.append(record)
                continue

            retry_action = _resolve_retry_action(record)
            if retry_action is None:
                skipped_failed_retry += 1
                record["reason_code"] = "missing_retry_action"
                updated_records.append(record)
                continue

            action = retry_action
            record["action"] = retry_action

        platform = _detect_platform_for_publish(repo_url, record)
        issue_url = _issue_url_for_publish(record)
        attempted_action = action

        try:
            if action in {"updated_by_comment", "closed"}:
                if not issue_url:
                    raise click.ClickException(
                        f"Missing issue URL for publish action {action}: {repo_url}"
                    )

                issue_client = issue_client_for_platform(platform)
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
                        analysis_summary_file,
                        previous_report,
                    )
                    continue

            if action == "simulated_created":
                body = _load_publish_body(analysis_root, repo_url)
                title = "Automated Metadata Quality Report from CodeMetaSoft"
                issue_client = issue_client_for_platform(platform)
                created_url = issue_client.create_issue(repo_url, title, body)

                record["action"] = "created"
                record["issue_url"] = created_url
                record["dry_run"] = False
                record["issue_persistence"] = "posted"
                record.pop("simulated_issue_url", None)
                _clear_failure_metadata(record)

            elif action == "updated_by_comment":
                if not issue_url:
                    raise click.ClickException(
                        f"Missing previous issue URL for repo: {repo_url}"
                    )

                body = _load_publish_body(analysis_root, repo_url)
                issue_client = issue_client_for_platform(platform)
                issue_client.add_issue_comment(
                    issue_url,
                    f"New analysis detected updated findings.\n\n{body}",
                )

                record["issue_url"] = issue_url
                record["dry_run"] = False
                record["issue_persistence"] = "posted"
                record.pop("simulated_issue_url", None)
                _clear_failure_metadata(record)

            elif action == "closed":
                if not issue_url:
                    raise click.ClickException(
                        f"Missing previous issue URL for repo: {repo_url}"
                    )

                issue_client = issue_client_for_platform(platform)
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
                _clear_failure_metadata(record)

            elif action == "skipped":
                record["dry_run"] = False
                record["issue_persistence"] = "none"
                record.pop("simulated_issue_url", None)
                _clear_failure_metadata(record)

            else:
                if attempted_action == "failed":
                    skipped_failed_retry += 1
                else:
                    record["dry_run"] = False
                    record.pop("simulated_issue_url", None)
                    _clear_failure_metadata(record)

        except Exception as exc:
            record["action"] = "failed"
            record["reason_code"] = "publish_exception"
            error_text = str(exc)
            record["error"] = error_text
            record["dry_run"] = True
            record["is_transient_error"] = _is_transient_publish_error(error_text)
            record["retry_after_seconds"] = _retry_after_seconds_from_error(error_text)
            previous_retry_attempt = record.get("retry_attempt")
            retry_attempt = (
                previous_retry_attempt + 1
                if isinstance(previous_retry_attempt, int)
                else 1
            )
            record["retry_attempt"] = retry_attempt
            record["failed_at"] = _now_utc_iso()
            if attempted_action and attempted_action != "failed":
                record["last_publish_action"] = attempted_action

        updated_records.append(record)
        _write_per_repo_report(
            analysis_root,
            record,
            analysis_summary_file,
            previous_report,
        )

    run_report = write_report_file(
        report_file=run_report_file,
        records=updated_records,
        dry_run=False,
        run_root=analysis_root.parent,
        analysis_summary_file=analysis_summary_file,
        previous_report=previous_report,
    )
    run_metadata_candidate = run_report.get("run_metadata")
    if isinstance(run_metadata_candidate, dict):
        run_metadata_written = cast(dict[str, object], run_metadata_candidate)
    else:
        run_metadata_written = {}
        run_report["run_metadata"] = run_metadata_written

    run_metadata_written["published_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    run_metadata_written["idempotency_skipped_records"] = skipped_published
    run_metadata_written["failed_retry_skipped_records"] = skipped_failed_retry
    with open(run_report_file, "w", encoding="utf-8") as f:
        json.dump(run_report, f, indent=2)


@click.command()
@click.option(
    "--analysis-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Existing analysis snapshot folder containing run_report.json.",
)
@click.option(
    "--retry-failed",
    is_flag=True,
    default=False,
    help="Retry records previously marked as failed when they are eligible for retry.",
)
def publish_command(analysis_root: Path, retry_failed: bool) -> None:
    """Publish issues using precomputed decisions from an analysis snapshot."""
    publish_analysis(analysis_root, retry_failed=retry_failed)
