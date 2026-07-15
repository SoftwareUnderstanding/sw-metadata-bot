import json

from conversion.convert_legacy_outputs import convert_legacy_output_tree


def test_convert_legacy_output_tree_creates_repo_state_layout(tmp_path):
    legacy_snapshot = tmp_path / "outputs" / "batch-a" / "202603"
    repo_dir = legacy_snapshot / "github_com_example_repo"
    repo_dir.mkdir(parents=True)

    (repo_dir / "pitfall.jsonld").write_text('{"@type": "Pitfall"}', encoding="utf-8")
    (repo_dir / "somef_output.json").write_text(
        '{"somef_provenance": "legacy"}', encoding="utf-8"
    )
    (repo_dir / "report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "repo_url": "https://github.com/example/repo",
                        "action": "simulated_created",
                        "current_commit_id": "abc123",
                        "codemeta_status": "present",
                        "file": "202603/github_com_example_repo/pitfall.jsonld",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (legacy_snapshot / "run_report.json").write_text(
        json.dumps({"records": [], "run_metadata": {}}),
        encoding="utf-8",
    )

    converted = convert_legacy_output_tree(
        legacy_snapshot, target_root=tmp_path / "outputs" / "batch-a"
    )

    assert converted == [legacy_snapshot]

    converted_repo = tmp_path / "outputs" / "batch-a" / "github_com_example_repo"
    assert converted_repo.exists()
    assert (converted_repo / "pitfall.jsonld").exists()
    assert (converted_repo / "somef_output.json").exists()
    assert (converted_repo / "report.json").exists()
    assert (converted_repo / "current-state.json").exists()
    assert (converted_repo / "event-log.jsonl").exists()
    assert (tmp_path / "outputs" / "batch-a" / "run_report.json").exists()
