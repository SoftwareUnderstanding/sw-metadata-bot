"""Tests for pipeline module."""

import json
from pathlib import Path

from click.testing import CliRunner

from sw_metadata_bot import pipeline


def _write_community_config(tmp_path, **overrides):
    """Write a minimal community config and return its path."""
    config = {
        "community": {"name": "ossr"},
        "repositories": ["https://github.com/example/repo"],
        "issues": {"custom_message": None, "opt_outs": []},
        "outputs": {
            "root_dir": str(tmp_path / "outputs"),
            "run_name": "batch-a",
            "snapshot_tag_format": "%Y%m%d",
        },
    }
    config.update(overrides)
    config_path = tmp_path / "community.json"
    config_path.write_text(json.dumps(config))
    return config_path


def test_resolve_run_paths_defaults():
    """Use input stem when run_name and snapshot_tag are not provided."""
    somef_output, pitfalls_output_dir, analysis_output_file, issues_output_dir = (
        pipeline._resolve_run_paths(
            output_root=Path("outputs"),
            run_name="opt-ins",
            snapshot_tag=None,
        )
    )

    assert somef_output == Path("outputs/opt-ins/somef_outputs")
    assert pitfalls_output_dir == Path("outputs/opt-ins/pitfalls_outputs")
    assert analysis_output_file == Path("outputs/opt-ins/analysis_results.json")
    assert issues_output_dir == Path("outputs/opt-ins/issues_out")


def test_resolve_run_paths_with_run_name_and_snapshot():
    """Use custom run_name and nested snapshot folder when provided."""
    somef_output, pitfalls_output_dir, analysis_output_file, issues_output_dir = (
        pipeline._resolve_run_paths(
            output_root=Path("outputs"),
            run_name="ossr-run",
            snapshot_tag="2026-03",
        )
    )

    assert somef_output == Path("outputs/ossr-run/2026-03/somef_outputs")
    assert pitfalls_output_dir == Path("outputs/ossr-run/2026-03/pitfalls_outputs")
    assert analysis_output_file == Path(
        "outputs/ossr-run/2026-03/analysis_results.json"
    )
    assert issues_output_dir == Path("outputs/ossr-run/2026-03/issues_out")


def test_resolve_output_root_relative_uses_project_root(tmp_path):
    """Resolve relative output root from project root rather than config directory."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\n")
    config_dir = tmp_path / "assets"
    config_dir.mkdir()
    config_path = config_dir / "community.json"
    config = {
        "repositories": [],
        "outputs": {"root_dir": "assets"},
    }
    config_path.write_text(json.dumps(config))

    resolved_output_root = pipeline.resolve_output_root(config, config_path)

    assert resolved_output_root == tmp_path / "assets"


def test_resolve_output_root_keeps_absolute_path(tmp_path):
    """Keep absolute output root unchanged."""
    config_path = tmp_path / "community.json"
    absolute_output_root = tmp_path / "custom-output"
    config = {
        "repositories": [],
        "outputs": {"root_dir": str(absolute_output_root)},
    }
    config_path.write_text(json.dumps(config))

    resolved_output_root = pipeline.resolve_output_root(config, config_path)

    assert resolved_output_root == absolute_output_root


def test_resolve_unique_snapshot_tag_uses_requested_when_missing(tmp_path):
    """Keep requested snapshot tag when the target directory does not exist."""
    run_root = tmp_path / "outputs" / "batch-a"

    resolved = pipeline._resolve_unique_snapshot_tag(
        run_root=run_root, snapshot_tag="X"
    )

    assert resolved == "X"


def test_resolve_unique_snapshot_tag_increments_for_existing_base(tmp_path):
    """Use X_2 when X already exists, and continue to next available suffix."""
    run_root = tmp_path / "outputs" / "batch-a"
    (run_root / "X").mkdir(parents=True)
    (run_root / "X_2").mkdir(parents=True)

    resolved = pipeline._resolve_unique_snapshot_tag(
        run_root=run_root, snapshot_tag="X"
    )

    assert resolved == "X_3"


def test_resolve_unique_snapshot_tag_increments_existing_suffixed_tag(tmp_path):
    """Use the next numeric suffix when the requested suffixed tag already exists."""
    run_root = tmp_path / "outputs" / "batch-a"
    (run_root / "X_4").mkdir(parents=True)

    resolved = pipeline._resolve_unique_snapshot_tag(
        run_root=run_root,
        snapshot_tag="X_4",
    )

    assert resolved == "X_5"


def test_run_pipeline_invokes_commands_with_expected_args(monkeypatch, tmp_path):
    """Invoke metacheck and create-issues with the expected computed arguments."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Capture metacheck invocation arguments for assertions."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}
        filtered_input = Path(args[1])
        calls["filtered_repos"] = json.loads(filtered_input.read_text())["repositories"]

    def fake_create_issues_main(*, args, standalone_mode):
        """Capture create-issues invocation arguments for assertions."""
        calls["create_issues"] = {"args": args, "standalone_mode": standalone_mode}

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(
        pipeline.create_issues_command,
        "main",
        fake_create_issues_main,
    )

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        repositories=["https://github.com/example/repo"],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=False,
        snapshot_tag="202603",
        previous_report=None,
    )

    assert calls["metacheck"]["standalone_mode"] is False
    assert calls["metacheck"]["args"] == [
        "--input",
        calls["metacheck"]["args"][1],
        "--somef-output",
        str(output_root / "batch-a" / "202603" / "somef_outputs"),
        "--pitfalls-output",
        str(output_root / "batch-a" / "202603" / "pitfalls_outputs"),
        "--analysis-output",
        str(output_root / "batch-a" / "202603" / "analysis_results.json"),
    ]
    assert calls["filtered_repos"] == ["https://github.com/example/repo"]

    assert calls["create_issues"]["standalone_mode"] is False
    assert calls["create_issues"]["args"] == [
        "--pitfalls-output-dir",
        str(output_root / "batch-a" / "202603" / "pitfalls_outputs"),
        "--issues-dir",
        str(output_root / "batch-a" / "202603" / "issues_out"),
        "--community-config-file",
        str(community_config),
        "--analysis-summary-file",
        str(output_root / "batch-a" / "202603" / "analysis_results.json"),
    ]


def test_run_pipeline_appends_dry_run_flag(monkeypatch, tmp_path):
    """Append --dry-run when dry_run=True."""
    captured_args: dict[str, list[str]] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Accept metacheck invocation without side effects."""
        return None

    def fake_create_issues_main(*, args, standalone_mode):
        """Capture create-issues arguments to verify dry-run flag propagation."""
        captured_args["args"] = args

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(pipeline.create_issues_command, "main", fake_create_issues_main)

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=True,
        snapshot_tag=None,
        previous_report=None,
    )

    assert captured_args["args"][-1] == "--dry-run"


def test_run_pipeline_command_forwards_to_run_pipeline(monkeypatch, tmp_path):
    """CLI wrapper passes parsed values to run_pipeline()."""
    captured: dict[str, object] = {}

    def fake_run_pipeline(**kwargs):
        """Capture keyword arguments passed by CLI wrapper."""
        captured.update(kwargs)

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run_pipeline)

    community_config = _write_community_config(
        tmp_path,
        outputs={
            "root_dir": str(tmp_path / "results"),
            "run_name": "custom-run",
            "snapshot_tag_format": None,
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        pipeline.run_pipeline_command,
        [
            "--community-config-file",
            str(community_config),
            "--snapshot-tag",
            "2026-03",
            "--dry-run",
            "--previous-report",
            str(community_config),
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "community_config_file": community_config,
        "dry_run": True,
        "snapshot_tag": "2026-03",
        "previous_report": community_config,
    }


def test_find_latest_previous_report_prefers_latest_snapshot(tmp_path):
    """Select latest report by snapshot tag with optional numeric suffix."""
    output_root = tmp_path / "outputs"
    run_name = "ossr"

    r1 = output_root / run_name / "20260310" / "issues_out"
    r2 = output_root / run_name / "20260311" / "issues_out"
    r3 = output_root / run_name / "20260311_2" / "issues_out"
    r1.mkdir(parents=True)
    r2.mkdir(parents=True)
    r3.mkdir(parents=True)
    (r1 / "report.json").write_text("{}")
    (r2 / "report.json").write_text("{}")
    (r3 / "report.json").write_text("{}")

    found = pipeline.find_latest_previous_report(
        output_root=output_root,
        run_name=run_name,
        current_snapshot_tag="20260312",
    )

    assert found == r3 / "report.json"


def test_run_pipeline_auto_discovers_previous_report(monkeypatch, tmp_path):
    """Auto-discover previous report when option is not provided."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Capture metacheck invocation to keep test side-effect free."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}

    def fake_create_issues_main(*, args, standalone_mode):
        """Capture create-issues invocation and discovered report arguments."""
        calls["create_issues"] = {"args": args, "standalone_mode": standalone_mode}

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(pipeline.create_issues_command, "main", fake_create_issues_main)

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    previous_report = output_root / "batch-a" / "20260310" / "issues_out"
    previous_report.mkdir(parents=True)
    (previous_report / "report.json").write_text("{}")

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=False,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert "--previous-report" in calls["create_issues"]["args"]
    idx = calls["create_issues"]["args"].index("--previous-report")
    assert calls["create_issues"]["args"][idx + 1] == str(
        previous_report / "report.json"
    )


def test_run_pipeline_uses_incremented_snapshot_tag_on_collision(monkeypatch, tmp_path):
    """Write outputs under incremented snapshot tag when requested one already exists."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Capture metacheck invocation arguments for assertions."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}

    def fake_create_issues_main(*, args, standalone_mode):
        """Capture create-issues invocation arguments for assertions."""
        calls["create_issues"] = {"args": args, "standalone_mode": standalone_mode}

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(
        pipeline.create_issues_command,
        "main",
        fake_create_issues_main,
    )

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    (output_root / "batch-a" / "X").mkdir(parents=True)

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=False,
        snapshot_tag="X",
        previous_report=None,
    )

    assert calls["metacheck"]["args"] == [
        "--input",
        calls["metacheck"]["args"][1],
        "--somef-output",
        str(output_root / "batch-a" / "X_2" / "somef_outputs"),
        "--pitfalls-output",
        str(output_root / "batch-a" / "X_2" / "pitfalls_outputs"),
        "--analysis-output",
        str(output_root / "batch-a" / "X_2" / "analysis_results.json"),
    ]


def test_run_pipeline_skips_analysis_when_all_repos_unchanged(monkeypatch, tmp_path):
    """Skip metacheck and write skipped-only report when all repos are unchanged."""
    called = {"metacheck": False, "create_issues": False}

    def fake_metacheck_main(*, args, standalone_mode):
        """Track unexpected metacheck invocation."""
        called["metacheck"] = True

    def fake_create_issues_main(*, args, standalone_mode):
        """Track unexpected create-issues invocation."""
        called["create_issues"] = True

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(pipeline.create_issues_command, "main", fake_create_issues_main)
    monkeypatch.setattr(pipeline, "_get_repo_head_commit", lambda repo_url: "abc123")

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        repositories=["https://github.com/example/repo"],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    prev_dir = output_root / "batch-a" / "20260310" / "issues_out"
    prev_dir.mkdir(parents=True)
    (prev_dir / "report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "issue_url": "https://github.com/example/repo/issues/7",
                        "issue_persistence": "posted",
                        "current_commit_id": "abc123",
                    }
                ]
            }
        )
    )

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=False,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert called["metacheck"] is False
    assert called["create_issues"] is False

    report_path = output_root / "batch-a" / "20260311" / "issues_out" / "report.json"
    report = json.loads(report_path.read_text())
    assert report["counters"]["total"] == 1
    assert report["counters"]["skipped"] == 1
    assert report["records"][0]["reason_code"] == "repo_not_updated"


def test_run_pipeline_merges_pre_skipped_with_analyzed_results(monkeypatch, tmp_path):
    """Merge unchanged pre-skipped records with create-issues output for mixed lists."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Capture metacheck args for filtered-input assertions."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}
        filtered_input = Path(args[1])
        calls["filtered_repos"] = json.loads(filtered_input.read_text())["repositories"]

    def fake_create_issues_main(*, args, standalone_mode):
        """Write minimal report.json representing analyzed subset results."""
        calls["create_issues"] = {"args": args, "standalone_mode": standalone_mode}
        issues_dir = Path(args[args.index("--issues-dir") + 1])
        issues_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "run_metadata": {
                "generated_at": "2026-03-11T00:00:00Z",
                "dry_run": False,
                "analysis_summary_file": None,
                "previous_report_source": None,
            },
            "counters": {
                "total": 1,
                "created": 1,
                "simulated": 0,
                "updated_by_comment": 0,
                "closed": 0,
                "skipped": 0,
                "failed": 0,
            },
            "records": [
                {
                    "repo_url": "https://github.com/example/new-repo",
                    "action": "created",
                    "reason_code": "no_previous_analysis",
                }
            ],
        }
        (issues_dir / "report.json").write_text(json.dumps(report))

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(pipeline.create_issues_command, "main", fake_create_issues_main)

    def fake_get_head(repo_url: str) -> str | None:
        """Return deterministic commit hash for unchanged repo."""
        if repo_url == "https://github.com/example/old-repo":
            return "abc123"
        return "def456"

    monkeypatch.setattr(pipeline, "_get_repo_head_commit", fake_get_head)

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        repositories=[
            "https://github.com/example/old-repo",
            "https://github.com/example/new-repo",
        ],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    prev_dir = output_root / "batch-a" / "20260310" / "issues_out"
    prev_dir.mkdir(parents=True)
    (prev_dir / "report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/old-repo",
                        "issue_url": "https://github.com/example/old-repo/issues/7",
                        "issue_persistence": "posted",
                        "current_commit_id": "abc123",
                    }
                ]
            }
        )
    )

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=False,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert calls["filtered_repos"] == ["https://github.com/example/new-repo"]

    report_path = output_root / "batch-a" / "20260311" / "issues_out" / "report.json"
    report = json.loads(report_path.read_text())
    assert report["counters"]["total"] == 2
    assert report["counters"]["created"] == 1
    assert report["counters"]["skipped"] == 1
    assert report["records"][0]["repo_url"] == "https://github.com/example/old-repo"
    assert report["records"][0]["reason_code"] == "repo_not_updated"


def test_run_pipeline_uses_config_snapshot_default(monkeypatch, tmp_path):
    """Use outputs.snapshot_tag_format when no CLI snapshot tag is provided."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Record the call arguments for metacheck."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}

    def fake_create_issues_main(*, args, standalone_mode):
        """Record the call arguments for create_issues."""
        calls["create_issues"] = {"args": args, "standalone_mode": standalone_mode}

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(pipeline.create_issues_command, "main", fake_create_issues_main)

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": "%Y%m%d",
        },
    )

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=False,
        snapshot_tag=None,
        previous_report=None,
    )

    args = calls["metacheck"]["args"]
    expected_snapshot = pipeline.resolve_snapshot_tag(
        pipeline.load_community_config(community_config), None
    )
    assert args[3] == str(output_root / "batch-a" / expected_snapshot / "somef_outputs")


def test_run_pipeline_skips_analysis_from_previous_dry_run_commit(
    monkeypatch, tmp_path
):
    """Skip analysis when previous report is simulated but commit hash is unchanged."""
    called = {"metacheck": False, "create_issues": False}

    def fake_metacheck_main(*, args, standalone_mode):
        """Mark metacheck as called."""
        called["metacheck"] = True

    def fake_create_issues_main(*, args, standalone_mode):
        """Mark create_issues as called."""
        called["create_issues"] = True

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(pipeline.create_issues_command, "main", fake_create_issues_main)
    monkeypatch.setattr(pipeline, "_get_repo_head_commit", lambda repo_url: "abc123")

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        repositories=["https://github.com/example/repo"],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    prev_dir = output_root / "batch-a" / "20260310" / "issues_out"
    prev_dir.mkdir(parents=True)
    (prev_dir / "report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "issue_persistence": "simulated",
                        "current_commit_id": "abc123",
                    }
                ]
            }
        )
    )

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=True,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert called["metacheck"] is False
    assert called["create_issues"] is False

    report_path = output_root / "batch-a" / "20260311" / "issues_out" / "report.json"
    report = json.loads(report_path.read_text())
    assert report["records"][0]["reason_code"] == "repo_not_updated"


def test_run_pipeline_unchanged_repo_unsubscribe_updates_opt_out(monkeypatch, tmp_path):
    """Detect unsubscribe during pre-skip for unchanged repos and persist opt-out."""
    called = {"metacheck": False, "create_issues": False}

    def fake_metacheck_main(*, args, standalone_mode):
        """Mark metacheck as called."""
        called["metacheck"] = True

    def fake_create_issues_main(*, args, standalone_mode):
        """Mark create_issues as called."""
        called["create_issues"] = True

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(pipeline.create_issues_command, "main", fake_create_issues_main)
    monkeypatch.setattr(pipeline, "_get_repo_head_commit", lambda repo_url: "abc123")
    monkeypatch.setattr(
        pipeline,
        "_detect_unsubscribe_in_previous_issue",
        lambda issue_url, dry_run: True,
    )

    output_root = tmp_path / "outputs"
    community_config = _write_community_config(
        tmp_path,
        repositories=["https://github.com/example/repo"],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    prev_dir = output_root / "batch-a" / "20260310" / "issues_out"
    prev_dir.mkdir(parents=True)
    (prev_dir / "report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "issue_persistence": "none",
                        "previous_issue_url": "https://github.com/example/repo/issues/7",
                        "current_commit_id": "abc123",
                    }
                ]
            }
        )
    )

    pipeline.run_pipeline(
        community_config_file=community_config,
        dry_run=True,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert called["metacheck"] is False
    assert called["create_issues"] is False

    report_path = output_root / "batch-a" / "20260311" / "issues_out" / "report.json"
    report = json.loads(report_path.read_text())
    assert report["records"][0]["reason_code"] == "unsubscribe"

    updated_config = json.loads(community_config.read_text())
    assert updated_config["issues"]["opt_outs"] == ["https://github.com/example/repo"]
