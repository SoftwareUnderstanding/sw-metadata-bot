"""Tests for pipeline module."""

import json
from pathlib import Path

from click.testing import CliRunner

from sw_metadata_bot import analysis_runtime, commit_lookup, pipeline
from sw_metadata_bot import publish as publish_module


def _write_config(tmp_path, **overrides):
    """Write a minimal config and return its path."""
    config = {
        "repositories": ["https://github.com/example/repo"],
        "issues": {"custom_message": None, "opt_outs": []},
        "outputs": {
            "root_dir": str(tmp_path / "outputs"),
            "run_name": "batch-a",
            "snapshot_tag_format": "%Y%m%d",
        },
    }
    config.update(overrides)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return config_path


def test_resolve_per_repo_paths_uses_analysis_root(tmp_path):
    """Per-repo paths are nested directly under analysis root with stable filenames."""
    analysis_root = tmp_path / "outputs" / "ossr" / "20260325"

    paths = analysis_runtime.resolve_per_repo_paths(
        analysis_root=analysis_root,
        repo_url="https://github.com/example/repo",
    )

    repo_root = analysis_root / "github_com_example_repo"
    assert paths["repo_folder"] == repo_root
    assert paths["somef_output"] == repo_root / "somef_output.json"
    assert paths["pitfall_output"] == repo_root / "pitfall.jsonld"
    assert paths["issue_report"] == repo_root / "issue_report.md"
    assert paths["report"] == repo_root / "report.json"


def test_resolve_output_root_relative_uses_project_root(tmp_path):
    """Resolve relative output root from project root rather than config directory."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\n")
    config_dir = tmp_path / "assets"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    config = {
        "repositories": [],
        "outputs": {"root_dir": "assets"},
    }
    config_path.write_text(json.dumps(config))

    resolved_output_root = pipeline.resolve_output_root(config, config_path)

    assert resolved_output_root == tmp_path / "assets"


def test_resolve_output_root_keeps_absolute_path(tmp_path):
    """Keep absolute output root unchanged."""
    config_path = tmp_path / "config.json"
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


def test_run_pipeline_invokes_metacheck_and_writes_reports(monkeypatch, tmp_path):
    """Invoke metacheck with expected args and write analysis reports per snapshot."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Capture metacheck invocation arguments for assertions."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)

    output_root = tmp_path / "outputs"
    config = _write_config(
        tmp_path,
        repositories=["https://github.com/example/repo"],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    pipeline.run_pipeline(
        config_file=config,
        dry_run=False,
        snapshot_tag="202603",
        previous_report=None,
    )

    assert calls["metacheck"]["standalone_mode"] is False
    assert calls["metacheck"]["args"][0:2] == [
        "--input",
        "https://github.com/example/repo",
    ]
    assert calls["metacheck"]["args"][2] == "--somef-output"
    assert calls["metacheck"]["args"][3].endswith("/202603/github_com_example_repo")
    assert calls["metacheck"]["args"][4] == "--pitfalls-output"
    assert calls["metacheck"]["args"][5].endswith("/202603/github_com_example_repo")

    run_report_path = output_root / "batch-a" / "202603" / "run_report.json"
    assert run_report_path.exists()
    run_report = json.loads(run_report_path.read_text())
    assert run_report["run_metadata"]["analysis_summary_file"].endswith(
        "/202603/analysis_results.json"
    )


def test_run_pipeline_marks_run_report_dry_run(monkeypatch, tmp_path):
    """Persist dry-run mode in run report metadata."""

    def fake_metacheck_main(*, args, standalone_mode):
        """Accept metacheck invocation without side effects."""
        return None

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)

    output_root = tmp_path / "outputs"
    config = _write_config(
        tmp_path,
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    pipeline.run_pipeline(
        config_file=config,
        dry_run=True,
        snapshot_tag=None,
        previous_report=None,
    )

    run_report_path = output_root / "batch-a" / "run_report.json"
    assert run_report_path.exists()
    run_report = json.loads(run_report_path.read_text())
    assert run_report["run_metadata"]["dry_run"] is True


def test_run_analysis_command_forwards_to_run_pipeline(monkeypatch, tmp_path):
    """run-analysis CLI wrapper forwards arguments and enforces dry-run mode."""
    captured: dict[str, object] = {}

    def fake_run_pipeline(**kwargs):
        """Capture keyword arguments passed by CLI wrapper."""
        captured.update(kwargs)

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run_pipeline)

    config = _write_config(
        tmp_path,
        outputs={
            "root_dir": str(tmp_path / "results"),
            "run_name": "custom-run",
            "snapshot_tag_format": None,
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        pipeline.run_analysis_command,
        [
            "--config-file",
            str(config),
            "--snapshot-tag",
            "2026-03",
            "--previous-report",
            str(config),
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "config_file": config,
        "dry_run": True,
        "snapshot_tag": "2026-03",
        "previous_report": config,
    }


def test_publish_command_forwards_to_publish_analysis(monkeypatch, tmp_path):
    """publish CLI wrapper passes the analysis root to publish executor."""
    captured: dict[str, Path] = {}

    def fake_publish_analysis(analysis_root: Path) -> None:
        captured["analysis_root"] = analysis_root

    monkeypatch.setattr(publish_module, "publish_analysis", fake_publish_analysis)

    analysis_root = tmp_path / "outputs" / "ossr" / "20260325"
    analysis_root.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        publish_module.publish_command,
        [
            "--analysis-root",
            str(analysis_root),
        ],
    )

    assert result.exit_code == 0
    assert captured["analysis_root"] == analysis_root


def test_find_latest_previous_report_prefers_latest_snapshot(tmp_path):
    """Select latest report by snapshot tag with optional numeric suffix."""
    output_root = tmp_path / "outputs"
    run_name = "ossr"

    r1 = output_root / run_name / "20260310"
    r2 = output_root / run_name / "20260311"
    r3 = output_root / run_name / "20260311_2"
    r1.mkdir(parents=True)
    r2.mkdir(parents=True)
    r3.mkdir(parents=True)
    (r1 / "run_report.json").write_text("{}")
    (r2 / "run_report.json").write_text("{}")
    (r3 / "run_report.json").write_text("{}")

    found = pipeline.find_latest_previous_report(
        output_root=output_root,
        run_name=run_name,
        current_snapshot_tag="20260312",
    )

    assert found == r3 / "run_report.json"


def test_run_pipeline_auto_discovers_previous_report(monkeypatch, tmp_path):
    """Auto-discover previous report when option is not provided."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Capture metacheck invocation to keep test side-effect free."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)

    output_root = tmp_path / "outputs"
    config = _write_config(
        tmp_path,
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    previous_snapshot = output_root / "batch-a" / "20260310"
    previous_snapshot.mkdir(parents=True)
    (previous_snapshot / "run_report.json").write_text("{}")

    pipeline.run_pipeline(
        config_file=config,
        dry_run=False,
        snapshot_tag="20260311",
        previous_report=None,
    )

    report_path = output_root / "batch-a" / "20260311" / "run_report.json"
    assert report_path.exists()
    report_data = json.loads(report_path.read_text())
    assert report_data["run_metadata"]["previous_report_source"] == str(
        previous_snapshot / "run_report.json"
    )


def test_run_pipeline_uses_incremented_snapshot_tag_on_collision(monkeypatch, tmp_path):
    """Write outputs under incremented snapshot tag when requested one already exists."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Capture metacheck invocation arguments for assertions."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)

    output_root = tmp_path / "outputs"
    config = _write_config(
        tmp_path,
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    (output_root / "batch-a" / "X").mkdir(parents=True)

    pipeline.run_pipeline(
        config_file=config,
        dry_run=False,
        snapshot_tag="X",
        previous_report=None,
    )

    assert calls["metacheck"]["args"][0:2] == [
        "--input",
        "https://github.com/example/repo",
    ]
    assert calls["metacheck"]["args"][2] == "--somef-output"
    assert calls["metacheck"]["args"][3].endswith(
        "/batch-a/X_2/github_com_example_repo"
    )


def test_sanitize_repo_name_handles_non_standard_url_path():
    """Convert mixed host/path/hyphen URL inputs to deterministic snake-style names."""
    value = pipeline.sanitize_repo_name(
        "https://atlas.cern/updates/press-statement/13-tev-open-data"
    )

    assert value == "atlas_cern_updates_press_statement_13_tev_open_data"


def test_get_gitlab_head_commit_uses_gitlab_api(monkeypatch):
    """Resolve GitLab HEAD commit through GitLab API endpoint."""

    class DummyResponse:
        def __init__(self):
            self._data = [{"id": "a" * 40}]

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def fake_get(url, params, timeout):
        assert url.startswith("https://gitlab.com/api/v4/projects/")
        assert params == {"per_page": 1}
        assert timeout == 10
        return DummyResponse()

    monkeypatch.setattr(commit_lookup.requests, "get", fake_get)

    commit_id = commit_lookup.get_gitlab_head_commit("https://gitlab.com/example/repo")

    assert commit_id == "a" * 40


def test_get_repo_head_commit_falls_back_to_generic_git(monkeypatch):
    """Use generic git fallback when API-specific commit lookups are unavailable."""
    monkeypatch.setattr(commit_lookup, "get_github_head_commit", lambda repo_url: None)
    monkeypatch.setattr(commit_lookup, "get_gitlab_head_commit", lambda repo_url: None)
    monkeypatch.setattr(
        commit_lookup,
        "get_generic_git_head_commit",
        lambda repo_url: "b" * 40,
    )

    commit_id = commit_lookup.get_repo_head_commit("https://git.astron.nl/ro/lofar")

    assert commit_id == "b" * 40


def test_run_pipeline_skips_analysis_when_all_repos_unchanged(monkeypatch, tmp_path):
    """Skip metacheck and write skipped-only report when all repos are unchanged."""
    called = {"metacheck": False}

    def fake_metacheck_main(*, args, standalone_mode):
        """Track unexpected metacheck invocation."""
        called["metacheck"] = True

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(
        commit_lookup, "get_repo_head_commit", lambda repo_url: "abc123"
    )

    output_root = tmp_path / "outputs"
    config = _write_config(
        tmp_path,
        repositories=["https://github.com/example/repo"],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    prev_root = output_root / "batch-a" / "20260310"
    prev_repo = prev_root / "github_com_example_repo"
    prev_repo.mkdir(parents=True)
    (prev_repo / "somef_output.json").write_text("{}")
    (prev_repo / "pitfall.jsonld").write_text(
        json.dumps(
            {
                "assessedSoftware": {"url": "https://github.com/example/repo"},
                "checks": [],
            }
        )
    )
    (prev_repo / "report.json").write_text(
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
    (prev_root / "run_report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "current_commit_id": "abc123",
                    }
                ]
            }
        )
    )

    pipeline.run_pipeline(
        config_file=config,
        dry_run=False,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert called["metacheck"] is False

    report_path = (
        output_root / "batch-a" / "20260311" / "github_com_example_repo" / "report.json"
    )
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["records"][0]["action"] == "skipped"
    assert report["records"][0]["reason_code"] == "repo_not_updated"


def test_run_pipeline_merges_pre_skipped_with_analyzed_results(monkeypatch, tmp_path):
    """Keep unchanged repos skipped while analyzing changed repositories."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Capture metacheck args and create minimal per-repo metacheck outputs."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}
        repo_folder = Path(args[5])
        repo_folder.mkdir(parents=True, exist_ok=True)
        (repo_folder / "pitfall.jsonld").write_text(
            json.dumps(
                {
                    "assessedSoftware": {"url": "https://github.com/example/new-repo"},
                    "schemaVersion": "0.2.1",
                    "dateCreated": "2026-03-11T00:00:00Z",
                    "checks": [
                        {"pitfall": "https://w3id.org/rsmetacheck/catalog/#W001"}
                    ],
                }
            )
        )
        (repo_folder / "somef_output.json").write_text("{}")

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)

    def fake_get_head(repo_url: str) -> str | None:
        """Return deterministic commit hash for unchanged repo."""
        if repo_url == "https://github.com/example/old-repo":
            return "abc123"
        return "def456"

    monkeypatch.setattr(commit_lookup, "get_repo_head_commit", fake_get_head)

    output_root = tmp_path / "outputs"
    config = _write_config(
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

    prev_root = output_root / "batch-a" / "20260310"
    prev_repo = prev_root / "github_com_example_old_repo"
    prev_repo.mkdir(parents=True)
    (prev_repo / "somef_output.json").write_text("{}")
    (prev_repo / "pitfall.jsonld").write_text(
        json.dumps(
            {
                "assessedSoftware": {"url": "https://github.com/example/old-repo"},
                "checks": [],
            }
        )
    )
    (prev_repo / "report.json").write_text(
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
    (prev_root / "run_report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/old-repo",
                        "current_commit_id": "abc123",
                    }
                ]
            }
        )
    )

    pipeline.run_pipeline(
        config_file=config,
        dry_run=False,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert calls["metacheck"]["args"][1] == "https://github.com/example/new-repo"

    old_repo_report = (
        output_root
        / "batch-a"
        / "20260311"
        / "github_com_example_old_repo"
        / "report.json"
    )
    new_repo_report = (
        output_root
        / "batch-a"
        / "20260311"
        / "github_com_example_new_repo"
        / "report.json"
    )
    assert old_repo_report.exists()
    assert new_repo_report.exists()
    old_data = json.loads(old_repo_report.read_text())
    new_data = json.loads(new_repo_report.read_text())
    assert old_data["records"][0]["reason_code"] == "repo_not_updated"
    assert new_data["records"][0]["reason_code"] in {
        "no_previous_analysis",
        "changed_and_issue_closed",
    }


def test_run_pipeline_uses_config_snapshot_default(monkeypatch, tmp_path):
    """Use outputs.snapshot_tag_format when no CLI snapshot tag is provided."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        """Record the call arguments for metacheck."""
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)

    output_root = tmp_path / "outputs"
    config = _write_config(
        tmp_path,
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": "%Y%m%d",
        },
    )

    pipeline.run_pipeline(
        config_file=config,
        dry_run=False,
        snapshot_tag=None,
        previous_report=None,
    )

    args = calls["metacheck"]["args"]
    expected_snapshot = pipeline.resolve_snapshot_tag(
        pipeline.load_config(config), None
    )
    assert "/batch-a/" in args[3]
    assert args[3].endswith(f"/{expected_snapshot}/github_com_example_repo")


def test_run_pipeline_skips_analysis_from_previous_dry_run_commit(
    monkeypatch, tmp_path
):
    """Skip analysis when previous report is simulated but commit hash is unchanged."""
    called = {"metacheck": False}

    def fake_metacheck_main(*, args, standalone_mode):
        """Mark metacheck as called."""
        called["metacheck"] = True

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(
        commit_lookup, "get_repo_head_commit", lambda repo_url: "abc123"
    )

    output_root = tmp_path / "outputs"
    config = _write_config(
        tmp_path,
        repositories=["https://github.com/example/repo"],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    prev_root = output_root / "batch-a" / "20260310"
    prev_repo = prev_root / "github_com_example_repo"
    prev_repo.mkdir(parents=True)
    (prev_repo / "somef_output.json").write_text("{}")
    (prev_repo / "pitfall.jsonld").write_text(
        json.dumps(
            {
                "assessedSoftware": {"url": "https://github.com/example/repo"},
                "checks": [],
            }
        )
    )
    (prev_repo / "report.json").write_text(
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
    (prev_root / "run_report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "current_commit_id": "abc123",
                    }
                ]
            }
        )
    )

    pipeline.run_pipeline(
        config_file=config,
        dry_run=True,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert called["metacheck"] is False

    report_path = (
        output_root / "batch-a" / "20260311" / "github_com_example_repo" / "report.json"
    )
    assert report_path.exists()


def test_run_pipeline_unchanged_repo_does_not_update_opt_out(monkeypatch, tmp_path):
    """Analysis-only mode does not perform unsubscribe API checks or mutate opt-outs."""
    called = {"metacheck": False}

    def fake_metacheck_main(*, args, standalone_mode):
        """Mark metacheck as called."""
        called["metacheck"] = True

    monkeypatch.setattr(pipeline.metacheck_command, "main", fake_metacheck_main)
    monkeypatch.setattr(
        commit_lookup, "get_repo_head_commit", lambda repo_url: "abc123"
    )

    output_root = tmp_path / "outputs"
    config = _write_config(
        tmp_path,
        repositories=["https://github.com/example/repo"],
        outputs={
            "root_dir": str(output_root),
            "run_name": "batch-a",
            "snapshot_tag_format": None,
        },
    )

    prev_root = output_root / "batch-a" / "20260310"
    prev_repo = prev_root / "github_com_example_repo"
    prev_repo.mkdir(parents=True)
    (prev_repo / "somef_output.json").write_text("{}")
    (prev_repo / "pitfall.jsonld").write_text(
        json.dumps(
            {
                "assessedSoftware": {"url": "https://github.com/example/repo"},
                "checks": [],
            }
        )
    )
    (prev_repo / "report.json").write_text(
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
    (prev_root / "run_report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "current_commit_id": "abc123",
                        "previous_issue_url": "https://github.com/example/repo/issues/7",
                    }
                ]
            }
        )
    )

    pipeline.run_pipeline(
        config_file=config,
        dry_run=True,
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert called["metacheck"] is False

    report_path = (
        output_root / "batch-a" / "20260311" / "github_com_example_repo" / "report.json"
    )
    assert report_path.exists()

    updated_config = json.loads(config.read_text())
    assert updated_config["issues"]["opt_outs"] == []
