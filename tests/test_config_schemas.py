"""Tests for the BotConfig schema and related configuration utilities."""

import json

from sw_metadata_bot.config.schemas import BotConfig

CONFIG_DATA = {
    "analysis": {
        "repositories": ["https://github.com/SoftwareUnderstanding/sw-metadata-bot"]
    },
    "issues": {
        "custom_issue_message": "This is a custom issue message.",
        "opt_outs": [],
    },
    "outputs": {
        "output_root_dir": "custom_outputs",
        "run_name": "test_run",
        "snapshot_tag_format": "custom_snapshot_{timestamp}",
    },
}


def test_bot_config_schema_from_json(tmp_path):
    config_file = tmp_path / "config.json"
    json.dump(CONFIG_DATA, config_file.open("w"), indent=4)

    config = BotConfig.from_json(config_file)

    assert config.analysis.repositories == CONFIG_DATA["analysis"]["repositories"]
    assert (
        config.issues.custom_issue_message
        == CONFIG_DATA["issues"]["custom_issue_message"]
    )
    assert config.issues.opt_outs == CONFIG_DATA["issues"]["opt_outs"]
    assert config.outputs.output_root_dir == CONFIG_DATA["outputs"]["output_root_dir"]
    assert config.outputs.run_name == CONFIG_DATA["outputs"]["run_name"]
    assert (
        config.outputs.snapshot_tag_format
        == CONFIG_DATA["outputs"]["snapshot_tag_format"]
    )
