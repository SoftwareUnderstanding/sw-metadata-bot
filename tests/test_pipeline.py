"""Tests for pipeline module."""

from pathlib import Path

from click.testing import CliRunner

from sw_metadata_bot import pipeline


def test_resolve_run_paths_defaults():
    """Use input stem when run_name and snapshot_tag are not provided."""
    somef_output, pitfalls_output_dir, analysis_output_file, issues_output_dir = (
        pipeline._resolve_run_paths(
            output_root=Path("outputs"),
            input_file=Path("assets/opt-ins.json"),
            run_name=None,
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
            input_file=Path("assets/ignored.json"),
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


def test_run_pipeline_invokes_commands_with_expected_args(monkeypatch, tmp_path):
    """Invoke metacheck and create-issues with the expected computed arguments."""
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

    input_file = tmp_path / "opt-ins.json"
    opt_outs_file = tmp_path / "opt-outs.json"
    output_root = tmp_path / "outputs"
    input_file.write_text("{}")
    opt_outs_file.write_text("{}")

    pipeline.run_pipeline(
        input_file=input_file,
        opt_outs_file=opt_outs_file,
        output_root=output_root,
        dry_run=False,
        run_name="batch-a",
        snapshot_tag="202603",
        previous_report=None,
    )

    assert calls["metacheck"]["standalone_mode"] is False
    assert calls["metacheck"]["args"] == [
        "--input",
        str(input_file),
        "--somef-output",
        str(output_root / "batch-a" / "202603" / "somef_outputs"),
        "--pitfalls-output",
        str(output_root / "batch-a" / "202603" / "pitfalls_outputs"),
        "--analysis-output",
        str(output_root / "batch-a" / "202603" / "analysis_results.json"),
    ]

    assert calls["create_issues"]["standalone_mode"] is False
    assert calls["create_issues"]["args"] == [
        "--pitfalls-output-dir",
        str(output_root / "batch-a" / "202603" / "pitfalls_outputs"),
        "--issues-dir",
        str(output_root / "batch-a" / "202603" / "issues_out"),
        "--opt-outs-file",
        str(opt_outs_file),
        "--issue-config-file",
        str(input_file),
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

    input_file = tmp_path / "opt-ins.json"
    opt_outs_file = tmp_path / "opt-outs.json"
    output_root = tmp_path / "outputs"
    input_file.write_text("{}")
    opt_outs_file.write_text("{}")

    pipeline.run_pipeline(
        input_file=input_file,
        opt_outs_file=opt_outs_file,
        output_root=output_root,
        dry_run=True,
        run_name=None,
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

    input_file = tmp_path / "repos.json"
    opt_outs_file = tmp_path / "opt-outs.json"
    output_root = tmp_path / "results"
    input_file.write_text('{"repositories": []}')
    opt_outs_file.write_text('{"repositories": []}')

    runner = CliRunner()
    result = runner.invoke(
        pipeline.run_pipeline_command,
        [
            "--input-file",
            str(input_file),
            "--opt-outs-file",
            str(opt_outs_file),
            "--output-root",
            str(output_root),
            "--run-name",
            "custom-run",
            "--snapshot-tag",
            "2026-03",
            "--dry-run",
            "--previous-report",
            str(opt_outs_file),
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "input_file": input_file,
        "opt_outs_file": opt_outs_file,
        "output_root": output_root,
        "dry_run": True,
        "run_name": "custom-run",
        "snapshot_tag": "2026-03",
        "previous_report": opt_outs_file,
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

    input_file = tmp_path / "opt-ins.json"
    opt_outs_file = tmp_path / "opt-outs.json"
    output_root = tmp_path / "outputs"
    input_file.write_text("{}")
    opt_outs_file.write_text("{}")

    previous_report = output_root / "batch-a" / "20260310" / "issues_out"
    previous_report.mkdir(parents=True)
    (previous_report / "report.json").write_text("{}")

    pipeline.run_pipeline(
        input_file=input_file,
        opt_outs_file=opt_outs_file,
        output_root=output_root,
        dry_run=False,
        run_name="batch-a",
        snapshot_tag="20260311",
        previous_report=None,
    )

    assert "--previous-report" in calls["create_issues"]["args"]
    idx = calls["create_issues"]["args"].index("--previous-report")
    assert calls["create_issues"]["args"][idx + 1] == str(
        previous_report / "report.json"
    )
