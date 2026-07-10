"""Tests for fetch module."""

import json
from pathlib import Path

from click.testing import CliRunner

from sw_metadata_bot import fetch as fetch_module
from sw_metadata_bot.config.schemas import BotConfig


class _FakeIssueClient:
    """Test double for GitHub/GitLab issue API clients."""

    def __init__(self, comments_for=None):
        self._comments_for = comments_for or (lambda url: [])

    def get_issue(self, issue_url: str) -> dict[str, object]:
        return {"state": "open"}

    def get_issue_comments(self, issue_url: str) -> list[str]:
        return self._comments_for(issue_url)


def _write_run_report(snapshot_dir: Path, records, run_metadata=None) -> None:
    payload = {"records": records}
    if run_metadata is not None:
        payload["run_metadata"] = run_metadata
    (snapshot_dir / "run_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_config(config_path: Path, repo_url: str) -> None:
    config_data = {
        "analysis": {"repositories": [repo_url]},
        "issues": {"opt_outs": []},
        "outputs": {
            "output_root_dir": "outputs",
            "run_name": "batch",
            "snapshot_tag_format": "%Y%m%d",
        },
    }
    config = BotConfig.model_validate(config_data)
    config.to_json(config_path)


def test_fetch_command_forwards_to_fetch_analysis(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_fetch_analysis(analysis_root: Path) -> None:
        captured["analysis_root"] = analysis_root

    monkeypatch.setattr(fetch_module, "fetch_analysis", fake_fetch_analysis)

    analysis_root = tmp_path / "outputs" / "ossr" / "20260325"
    analysis_root.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        fetch_module.fetch_command,
        ["--analysis-root", str(analysis_root)],
    )

    assert result.exit_code == 0
    assert captured["analysis_root"] == analysis_root


def test_fetch_unsubscribe_detected_updates_configs(tmp_path, monkeypatch):
    repo_url = "https://github.com/example/repo"
    analysis_root = tmp_path / "outputs" / "ossr" / "20260325"
    analysis_root.mkdir(parents=True)

    _write_run_report(
        analysis_root,
        records=[
            {
                "repo_url": repo_url,
                "platform": "github",
                "issue_url": f"{repo_url}/issues/1",
                "action": "created",
                "dry_run": False,
                "issue_persistence": "posted",
            }
        ],
        run_metadata={"input_config_file": "config.json"},
    )
    input_config_path = analysis_root / "config.json"
    _write_config(input_config_path, repo_url)
    _write_config(analysis_root / "config.json", repo_url)

    fake_client = _FakeIssueClient(comments_for=lambda url: ["unsubscribe"])
    monkeypatch.setattr(
        fetch_module.github_api, "GitHubAPI", lambda dry_run=False: fake_client
    )

    fetch_module.fetch_analysis(analysis_root)

    updated_run_report = json.loads(
        (analysis_root / "run_report.json").read_text(encoding="utf-8")
    )
    assert updated_run_report["records"][0]["unsubscribe_detected"] is True
    assert updated_run_report["records"][0]["reason_code"] == "unsubscribe"
    assert updated_run_report["run_metadata"]["fetch_diff_count"] == 1
    assert (analysis_root / "fetch_diff.json").exists()

    snapshot_config = BotConfig.from_json(analysis_root / "config.json")
    assert repo_url in snapshot_config.get_issue_opt_outs()
    original_config = BotConfig.from_json(input_config_path)
    assert repo_url in original_config.get_issue_opt_outs()


def test_fetch_skips_unknown_platform_gracefully(tmp_path):
    repo_url = "https://unknown.example.com/example/repo"
    analysis_root = tmp_path / "outputs" / "ossr" / "20260325"
    analysis_root.mkdir(parents=True)

    _write_run_report(
        analysis_root,
        records=[
            {
                "repo_url": repo_url,
                "platform": "unknown",
                "issue_url": "https://unknown.example.com/example/repo/issues/1",
            }
        ],
    )

    fetch_module.fetch_analysis(analysis_root)

    updated_run_report = json.loads(
        (analysis_root / "run_report.json").read_text(encoding="utf-8")
    )
    assert updated_run_report["records"][0]["platform"] == "unknown"
    assert updated_run_report["run_metadata"]["fetch_diff_count"] == 0
    assert (analysis_root / "fetch_diff.json").exists()
