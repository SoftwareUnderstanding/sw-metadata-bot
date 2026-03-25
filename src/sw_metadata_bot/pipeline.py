"""Pipeline command to run analysis then issue creation."""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import click
import requests

from . import github_api, gitlab_api, pitfalls
from .config_utils import (
    append_opt_out_repository,
    copy_config_to_analysis_root,
    get_custom_message,
    get_repositories,
    load_config,
    resolve_output_root,
    resolve_run_name,
    resolve_snapshot_tag,
    sanitize_repo_name,
)
from .create_issues import create_issues_command
from .metacheck_wrapper import metacheck_command

SNAPSHOT_TAG_PATTERN = re.compile(r"^(\d{8})(?:_(\d+))?$")
SNAPSHOT_INCREMENT_PATTERN = re.compile(r"^(.+?)_(\d+)$")


def _normalize_repo_url(url: str) -> str:
    """Normalize repository URL for cross-report matching."""
    return url.strip().rstrip("/")


def _extract_previous_commit(record: dict) -> str | None:
    """Return previous commit id from report records with compatibility fallback."""
    current_commit = record.get("current_commit_id")
    if isinstance(current_commit, str) and current_commit:
        return current_commit

    legacy_commit = record.get("commit_id")
    if isinstance(legacy_commit, str) and legacy_commit:
        return legacy_commit

    return None


def _is_unsubscribe_comment(comment: str) -> bool:
    """Return True when a comment is exactly the unsubscribe keyword."""
    return comment.strip().lower() == "unsubscribe"


def _detect_unsubscribe_in_previous_issue(issue_url: str, dry_run: bool) -> bool:
    """Check whether previous issue comments include an unsubscribe request."""
    client = github_api.GitHubAPI(dry_run=dry_run)
    comments = client.get_issue_comments(issue_url)
    return any(_is_unsubscribe_comment(comment) for comment in comments)


def _is_supported_for_commit_skip(repo_url: str) -> bool:
    """Return whether pre-analysis commit lookup is supported for a repo URL."""
    return "github.com" in repo_url.lower()


def _parse_github_repo(repo_url: str) -> tuple[str, str] | None:
    """Parse owner/repo from a GitHub repository URL."""
    match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)$", repo_url, re.IGNORECASE)
    if match is None:
        return None
    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    return owner, repo


def _get_repo_head_commit(repo_url: str) -> str | None:
    """Fetch current head commit for a GitHub repository."""
    parsed = _parse_github_repo(repo_url)
    if parsed is None:
        return None

    owner, repo = parsed
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    response = requests.get(url, params={"per_page": 1}, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    sha = first.get("sha")
    return str(sha) if isinstance(sha, str) and sha else None


def _resolve_unique_snapshot_tag(
    run_root: Path, snapshot_tag: str | None
) -> str | None:
    """Return a non-colliding snapshot tag by adding or incrementing numeric suffixes."""
    if snapshot_tag is None:
        return None

    candidate_path = run_root / snapshot_tag
    if not candidate_path.exists():
        return snapshot_tag

    match = SNAPSHOT_INCREMENT_PATTERN.fullmatch(snapshot_tag)
    if match is None:
        base_tag = snapshot_tag
        suffix = 2
    else:
        base_tag = match.group(1)
        suffix = int(match.group(2)) + 1

    while True:
        candidate = f"{base_tag}_{suffix}"
        if not (run_root / candidate).exists():
            return candidate
        suffix += 1


def _snapshot_sort_key(snapshot_tag: str) -> tuple[str, int] | None:
    """Return sortable key for snapshot tags matching YYYYMMDD or YYYYMMDD_N."""
    match = SNAPSHOT_TAG_PATTERN.fullmatch(snapshot_tag)
    if match is None:
        return None
    date_part, suffix_part = match.group(1), match.group(2)
    suffix = int(suffix_part) if suffix_part is not None else 0
    return (date_part, suffix)


def _find_latest_previous_snapshot_root(
    output_root: Path,
    run_name: str,
    current_snapshot_tag: str | None,
) -> Path | None:
    """Find latest previous snapshot root from same run folder."""
    run_root = output_root / run_name
    if not run_root.exists() or not run_root.is_dir():
        return None

    candidates: list[tuple[tuple[str, int], Path]] = []
    for child in run_root.iterdir():
        if not child.is_dir():
            continue
        key = _snapshot_sort_key(child.name)
        if key is None:
            continue
        if current_snapshot_tag is not None and child.name == current_snapshot_tag:
            continue

        has_new_layout = any(
            candidate.is_dir() and (candidate / "report.json").exists()
            for candidate in child.iterdir()
        )
        has_old_layout = (child / "issues_out" / "report.json").exists()
        has_run_report = (child / "run_report.json").exists()
        if has_new_layout or has_old_layout or has_run_report:
            candidates.append((key, child))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def find_latest_previous_report(
    output_root: Path,
    run_name: str,
    current_snapshot_tag: str | None,
) -> Path | None:
    """Find latest previous report path from same run folder."""
    snapshot_root = _find_latest_previous_snapshot_root(
        output_root=output_root,
        run_name=run_name,
        current_snapshot_tag=current_snapshot_tag,
    )
    if snapshot_root is None:
        return None

    run_report = snapshot_root / "run_report.json"
    if run_report.exists():
        return run_report

    legacy_report = snapshot_root / "issues_out" / "report.json"
    if legacy_report.exists():
        return legacy_report

    return None


def _snapshot_root_from_report_path(report_path: Path | None) -> Path | None:
    """Resolve snapshot root directory from a report file path."""
    if report_path is None:
        return None
    if report_path.name == "run_report.json":
        return report_path.parent
    if report_path.name == "report.json" and report_path.parent.name == "issues_out":
        return report_path.parent.parent
    if report_path.name == "report.json":
        return report_path.parent.parent
    return report_path.parent


def _resolve_per_repo_paths(analysis_root: Path, repo_url: str) -> dict[str, Path]:
    """Compute per-repository output paths within the analysis root."""
    sanitized_name = sanitize_repo_name(repo_url)
    repo_folder = analysis_root / sanitized_name

    return {
        "repo_folder": repo_folder,
        "somef_output": repo_folder / "somef_output.json",
        "pitfall_output": repo_folder / "pitfall.jsonld",
        "issue_report": repo_folder / "issue_report.md",
        "report": repo_folder / "report.json",
    }


def _copy_previous_repo_artifacts(
    previous_repo_folder: Path, current_repo_folder: Path
) -> None:
    """Copy previous snapshot repository artifacts into current snapshot folder."""
    current_repo_folder.mkdir(parents=True, exist_ok=True)
    for name in (
        "somef_output.json",
        "pitfall.jsonld",
        "issue_report.md",
        "report.json",
    ):
        src = previous_repo_folder / name
        if src.exists():
            shutil.copy2(src, current_repo_folder / name)


def _load_previous_repo_record(
    previous_snapshot_root: Path | None, repo_url: str
) -> dict | None:
    """Load previous per-repo record from previous snapshot if available."""
    if previous_snapshot_root is None:
        return None

    repo_folder = previous_snapshot_root / sanitize_repo_name(repo_url)
    report_path = repo_folder / "report.json"
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, list) and records:
            record = records[0]
            if isinstance(record, dict):
                return record

    run_report = previous_snapshot_root / "run_report.json"
    if run_report.exists():
        with open(run_report, encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, list):
            normalized = _normalize_repo_url(repo_url)
            for record in records:
                if not isinstance(record, dict):
                    continue
                value = record.get("repo_url")
                if isinstance(value, str) and _normalize_repo_url(value) == normalized:
                    return record

    return None


def _standardize_metacheck_outputs(repo_folder: Path) -> None:
    """Normalize metacheck output names to stable per-repo filenames."""
    repo_folder.mkdir(parents=True, exist_ok=True)

    pitfall_target = repo_folder / "pitfall.jsonld"
    if not pitfall_target.exists():
        pitfall_candidates = list((repo_folder / "pitfalls_outputs").glob("*.jsonld"))
        if not pitfall_candidates:
            pitfall_candidates = list(repo_folder.glob("*_pitfalls.jsonld"))
        if pitfall_candidates:
            shutil.move(str(pitfall_candidates[0]), str(pitfall_target))

    somef_target = repo_folder / "somef_output.json"
    if not somef_target.exists():
        somef_candidates = list((repo_folder / "somef_outputs").glob("*.json"))
        if not somef_candidates:
            somef_candidates = [
                path
                for path in repo_folder.glob("*.json")
                if path.name
                not in {
                    "report.json",
                    "analysis_results.json",
                    "config.json",
                    "run_report.json",
                }
                and not path.name.startswith("metacheck_")
            ]
        if somef_candidates:
            shutil.move(str(somef_candidates[0]), str(somef_target))

    for legacy_dir in (repo_folder / "somef_outputs", repo_folder / "pitfalls_outputs"):
        if legacy_dir.exists() and legacy_dir.is_dir():
            shutil.rmtree(legacy_dir)


def _run_metacheck_for_repo(repo_url: str, repo_folder: Path) -> None:
    """Run metacheck for a single repository URL into its own folder."""
    repo_folder.mkdir(parents=True, exist_ok=True)
    temp_analysis_file: Path | None = None
    with NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="metacheck_repo_",
        delete=False,
        encoding="utf-8",
    ) as temp_file:
        temp_analysis_file = Path(temp_file.name)

    metacheck_command.main(
        args=[
            "--input",
            repo_url,
            "--somef-output",
            str(repo_folder),
            "--pitfalls-output",
            str(repo_folder),
            "--analysis-output",
            str(temp_analysis_file),
        ],
        standalone_mode=False,
    )

    if temp_analysis_file is not None and temp_analysis_file.exists():
        temp_analysis_file.unlink()

    _standardize_metacheck_outputs(repo_folder)


def _build_run_report(
    records: list[dict[str, object]], *, dry_run: bool, analysis_summary_file: Path
) -> dict[str, object]:
    """Build run-level report payload from per-repo records."""
    counters = {
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
    return {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": dry_run,
            "analysis_summary_file": str(analysis_summary_file),
        },
        "counters": counters,
        "records": records,
    }


def _collect_per_repo_records(analysis_root: Path) -> list[dict[str, object]]:
    """Collect one report record per repository folder."""
    records: list[dict[str, object]] = []
    if not analysis_root.exists():
        return records

    for repo_folder in sorted(analysis_root.iterdir()):
        if not repo_folder.is_dir():
            continue
        report_path = repo_folder / "report.json"
        if not report_path.exists():
            continue
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
        report_records = data.get("records") if isinstance(data, dict) else None
        if isinstance(report_records, list) and report_records:
            first = report_records[0]
            if isinstance(first, dict):
                records.append(first)

    return records


def _build_counters(records: list[dict[str, object]]) -> dict[str, int]:
    """Build counters from report records."""
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
        return value
    if "github.com" in repo_url.lower():
        return "github"
    if "gitlab.com" in repo_url.lower():
        return "gitlab.com"
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


def run_pipeline(
    config_file: Path,
    dry_run: bool,
    snapshot_tag: str | None,
    previous_report: Path | None,
) -> None:
    """Run analysis and issue creation for a configuration."""
    config = load_config(config_file)
    repositories = get_repositories(config)
    output_root = resolve_output_root(config, config_file)
    run_folder_name = resolve_run_name(config, config_file)
    requested_snapshot_tag = resolve_snapshot_tag(config, snapshot_tag)

    run_root = output_root / run_folder_name
    resolved_snapshot_tag = _resolve_unique_snapshot_tag(
        run_root=run_root,
        snapshot_tag=requested_snapshot_tag,
    )

    analysis_root = (
        run_root / resolved_snapshot_tag if resolved_snapshot_tag else run_root
    )
    analysis_output_file = analysis_root / "analysis_results.json"

    copy_config_to_analysis_root(config_file, analysis_root)
    analysis_root.mkdir(parents=True, exist_ok=True)

    resolved_previous_report = previous_report
    if resolved_previous_report is None:
        resolved_previous_report = find_latest_previous_report(
            output_root=output_root,
            run_name=run_folder_name,
            current_snapshot_tag=resolved_snapshot_tag,
        )
    previous_snapshot_root = _snapshot_root_from_report_path(resolved_previous_report)

    evaluated_repositories: dict[str, dict[str, str]] = {}

    for repo_url in repositories:
        per_repo = _resolve_per_repo_paths(analysis_root, repo_url)
        repo_folder = per_repo["repo_folder"]
        repo_folder.mkdir(parents=True, exist_ok=True)

        previous_record = _load_previous_repo_record(previous_snapshot_root, repo_url)
        previous_commit_id = (
            _extract_previous_commit(previous_record) if previous_record else None
        )

        current_commit_id: str | None = None
        if _is_supported_for_commit_skip(repo_url):
            try:
                current_commit_id = _get_repo_head_commit(repo_url)
            except Exception:
                current_commit_id = None

        reused_previous = False
        if (
            previous_snapshot_root is not None
            and previous_record is not None
            and previous_commit_id
            and current_commit_id
            and previous_commit_id != "Unknown"
            and current_commit_id != "Unknown"
            and current_commit_id == previous_commit_id
        ):
            previous_repo_folder = previous_snapshot_root / sanitize_repo_name(repo_url)
            if previous_repo_folder.exists():
                _copy_previous_repo_artifacts(previous_repo_folder, repo_folder)
                reused_previous = True

                previous_issue_url = previous_record.get("issue_url")
                if not isinstance(previous_issue_url, str) or not previous_issue_url:
                    previous_issue_url = previous_record.get("previous_issue_url")
                if isinstance(previous_issue_url, str) and previous_issue_url:
                    try:
                        if _detect_unsubscribe_in_previous_issue(
                            previous_issue_url, dry_run
                        ):
                            append_opt_out_repository(config_file, repo_url)
                    except Exception:
                        pass

        if not reused_previous:
            _run_metacheck_for_repo(repo_url, repo_folder)

        evaluated_repositories[sanitize_repo_name(repo_url)] = {
            "url": repo_url,
            "commit_id": current_commit_id or "Unknown",
        }

    analysis_summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {"evaluated_repositories": evaluated_repositories},
    }
    with open(analysis_output_file, "w", encoding="utf-8") as f:
        json.dump(analysis_summary, f, indent=2)

    create_issues_args = [
        "--analysis-root",
        str(analysis_root),
        "--config-file",
        str(config_file),
        "--analysis-summary-file",
        str(analysis_output_file),
    ]
    if resolved_previous_report is not None:
        create_issues_args.extend(["--previous-report", str(resolved_previous_report)])
    if dry_run:
        create_issues_args.append("--dry-run")

    create_issues_command.main(args=create_issues_args, standalone_mode=False)

    run_records = _collect_per_repo_records(analysis_root)
    run_report = _build_run_report(
        run_records,
        dry_run=dry_run,
        analysis_summary_file=analysis_output_file,
    )
    run_report_file = analysis_root / "run_report.json"
    with open(run_report_file, "w", encoding="utf-8") as f:
        json.dump(run_report, f, indent=2)


@click.command()
@click.option(
    "--config-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Unified JSON configuration file.",
)
@click.option(
    "--snapshot-tag",
    type=str,
    default=None,
    help="Optional snapshot suffix folder (for example 2026-03).",
)
@click.option(
    "--previous-report",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Previous run_report.json used for incremental issue handling.",
)
def run_analysis_command(
    config_file: Path,
    snapshot_tag: str | None,
    previous_report: Path | None,
) -> None:
    """Run analysis and compute issue lifecycle decisions in dry-run mode."""
    run_pipeline(
        config_file=config_file,
        dry_run=True,
        snapshot_tag=snapshot_tag,
        previous_report=previous_report,
    )


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
