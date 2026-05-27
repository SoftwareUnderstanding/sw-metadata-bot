"""Tests for the BotConfig schema and related configuration utilities."""

import json

from pydantic import ValidationError

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

CONFIG_DATA_MINIMAL = {
    "analysis": {
        "repositories": ["https://github.com/SoftwareUnderstanding/sw-metadata-bot"]
    },
}

CONFIG_DATA_INVALID = {
    "analysis": {"repositories": []},
    "issues": {
        "custom_issue_message": "This is a custom issue message.",
        "opt_outs": ["https://github.com/SoftwareUnderstanding/sw-metadata-bot"],
    },
}

CONFIG_DATA_INVALID_OPT_OUT = {
    "analysis": {
        "repositories": ["https://github.com/SoftwareUnderstanding/sw-metadata-bot"]
    },
    "issues": {
        "custom_issue_message": "This is a custom issue message.",
        "opt_outs": ["https://github/other_repo/not_in_list"],
    },
}


def test_bot_config_schema_from_json(tmp_path):
    """Test that loading a config from JSON works and that all fields are correctly parsed."""
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


def test_bot_config_schema_from_json_minimal(tmp_path):
    """Test that loading a minimal config with only required fields works and that optional fields get default values."""
    config_file = tmp_path / "config_minimal.json"
    json.dump(CONFIG_DATA_MINIMAL, config_file.open("w"), indent=4)

    config = BotConfig.from_json(config_file)

    assert (
        config.analysis.repositories == CONFIG_DATA_MINIMAL["analysis"]["repositories"]
    )
    assert config.issues.custom_issue_message is None
    assert config.issues.opt_outs == []
    assert config.outputs.output_root_dir == "outputs"
    assert config.outputs.run_name is None
    assert config.outputs.snapshot_tag_format == "%Y%m%d"


def test_bot_config_schema_from_json_invalid_repository_list_empty(tmp_path):
    """Test that if the repositories list is empty, a validation error is raised."""
    config_file = tmp_path / "config_invalid.json"
    json.dump(CONFIG_DATA_INVALID, config_file.open("w"), indent=4)

    try:
        _ = BotConfig.from_json(config_file)
        assert False, "Expected validation error for invalid config"
    except Exception as e:
        assert "Repositories list" in str(e)


def test_bot_config_schema_from_json_invalid_opt_out(tmp_path):
    """Test that if an opt-out URL is not in the repositories list, it is removed from the config and a warning is printed."""
    config_file = tmp_path / "config_invalid_opt_out.json"
    json.dump(CONFIG_DATA_INVALID_OPT_OUT, config_file.open("w"), indent=4)

    config = BotConfig.from_json(config_file)

    # The invalid opt-out should be removed from the config and a warning printed
    assert config.issues.opt_outs == []


def test_bot_config_schema_from_json_invalid_field(tmp_path):
    """Test that if the config JSON contains an unexpected field, a validation error is raised."""
    invalid_config_data = CONFIG_DATA.copy()
    invalid_config_data["unexpected_field"] = "unexpected_value"
    config_file = tmp_path / "config_invalid_field.json"
    json.dump(invalid_config_data, config_file.open("w"), indent=4)

    try:
        _ = BotConfig.from_json(config_file)
        assert False, "Expected validation error for unexpected field in config"
    except Exception as e:
        assert "unexpected_field" in str(e)


def test_bot_config_schema_from_json_invalid_type_field(tmp_path):
    import copy

    """Test that if the config JSON contains an unexpected field, a validation error is raised."""
    invalid_config_data = copy.deepcopy(CONFIG_DATA)
    invalid_config_data["analysis"]["repositories"] = "not_a_list"
    config_file = tmp_path / "config_invalid_type_field.json"
    json.dump(invalid_config_data, config_file.open("w"), indent=4)

    try:
        _ = BotConfig.from_json(config_file)
        assert False, "Expected validation error for unexpected field in config"
    except ValidationError as e:
        assert "list" in str(e)


# export tests


def test_bot_config_export_to_json(tmp_path):
    """Test that exporting config to JSON and reloading it produces the same config data (round-trip test)."""

    # load config from dict
    config = BotConfig.model_validate(CONFIG_DATA)

    config_file = tmp_path / "config_export.json"
    config.to_json(config_file, explicit=False)

    # load exported config and compare to original
    with config_file.open() as f:
        exported_data = json.load(f)
    assert exported_data == CONFIG_DATA


def test_bot_config_export_to_json_explicit(tmp_path):
    """Test that exporting config with explicit=True includes default values for optional fields."""

    # load config from dict
    config = BotConfig.model_validate(CONFIG_DATA_MINIMAL)

    config_file = tmp_path / "config_export_explicit.json"
    config.to_json(config_file, explicit=True)

    # load exported config and check that all fields are present (explicit=True should include default values)
    with config_file.open() as f:
        exported_data = json.load(f)
    # check that repositories list is correct
    assert (
        exported_data["analysis"]["repositories"]
        == CONFIG_DATA_MINIMAL["analysis"]["repositories"]
    )
    # check that default values are included for optional fields
    assert "custom_issue_message" in exported_data["issues"]
    assert "opt_outs" in exported_data["issues"]
    assert exported_data["issues"]["custom_issue_message"] is None
    assert exported_data["issues"]["opt_outs"] == []
    assert "output_root_dir" in exported_data["outputs"]
    assert "run_name" in exported_data["outputs"]
    assert "snapshot_tag_format" in exported_data["outputs"]
    assert exported_data["outputs"]["output_root_dir"] == "outputs"
    assert exported_data["outputs"]["run_name"] is None
    assert exported_data["outputs"]["snapshot_tag_format"] == "%Y%m%d"
