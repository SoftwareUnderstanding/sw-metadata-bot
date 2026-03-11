"""Tests for pipeline module."""

from click.testing import CliRunner

from sw_metadata_bot import pipeline


def test_resolve_run_paths_defaults():
    """Use input stem when run_name and snapshot_tag are not provided."""
    pitfalls_output_dir, analysis_output_file, issues_output_dir = (
        pipeline._resolve_run_paths(
            output_root=pipeline.Path("outputs"),
            input_file=pipeline.Path("assets/opt-ins.json"),
            run_name=None,
            snapshot_tag=None,
        )
    )

    assert pitfalls_output_dir == pipeline.Path("outputs/opt-ins/pitfalls_outputs")
    assert analysis_output_file == pipeline.Path(
        "outputs/opt-ins/analysis_results.json"
    )
    assert issues_output_dir == pipeline.Path("outputs/opt-ins/issues_out")


def test_resolve_run_paths_with_run_name_and_snapshot():
    """Use custom run_name and nested snapshot folder when provided."""
    pitfalls_output_dir, analysis_output_file, issues_output_dir = (
        pipeline._resolve_run_paths(
            output_root=pipeline.Path("outputs"),
            input_file=pipeline.Path("assets/ignored.json"),
            run_name="ossr-run",
            snapshot_tag="2026-03",
        )
    )

    assert pitfalls_output_dir == pipeline.Path(
        "outputs/ossr-run/2026-03/pitfalls_outputs"
    )
    assert analysis_output_file == pipeline.Path(
        "outputs/ossr-run/2026-03/analysis_results.json"
    )
    assert issues_output_dir == pipeline.Path("outputs/ossr-run/2026-03/issues_out")


def test_run_pipeline_invokes_commands_with_expected_args(monkeypatch, tmp_path):
    """Invoke metacheck and create-issues with the expected computed arguments."""
    calls: dict[str, dict] = {}

    def fake_metacheck_main(*, args, standalone_mode):
        calls["metacheck"] = {"args": args, "standalone_mode": standalone_mode}

    def fake_create_issues_main(*, args, standalone_mode):
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
        previous_created_report=None,
    )

    assert calls["metacheck"]["standalone_mode"] is False
    assert calls["metacheck"]["args"] == [
        "--input",
        str(input_file),
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
        return None

    def fake_create_issues_main(*, args, standalone_mode):
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
        previous_created_report=None,
    )

    assert captured_args["args"][-1] == "--dry-run"


def test_run_pipeline_command_forwards_to_run_pipeline(monkeypatch, tmp_path):
    """CLI wrapper passes parsed values to run_pipeline()."""
    captured: dict[str, object] = {}

    def fake_run_pipeline(**kwargs):
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
            "--previous-created-report",
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
        "previous_created_report": opt_outs_file,
    }
