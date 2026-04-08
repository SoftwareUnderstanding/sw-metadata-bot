"""Tests for conftest module - shared pytest fixtures."""

import pytest


def pytest_addoption(parser):
    """Add options to control optional integration test execution."""
    parser.addoption(
        "--run-integration-gitlab",
        action="store_true",
        default=False,
        help="Run tests marked with integration_gitlab (requires GITLAB_API_TOKEN).",
    )


def pytest_collection_modifyitems(config, items):
    """Skip GitLab integration tests unless explicitly requested."""
    if config.getoption("--run-integration-gitlab"):
        return

    skip_integration = pytest.mark.skip(
        reason="need --run-integration-gitlab option to run"
    )
    for item in items:
        if "integration_gitlab" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def tmp_config_file(tmp_path):
    """Create a temporary config file for testing."""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"test": "value"}')
    return config_file
