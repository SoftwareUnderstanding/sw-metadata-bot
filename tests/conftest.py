"""Tests for conftest module - shared pytest fixtures."""

import pytest


@pytest.fixture
def tmp_config_file(tmp_path):
    """Create a temporary config file for testing."""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"test": "value"}')
    return config_file
