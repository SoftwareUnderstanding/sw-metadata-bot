"""Tests for __init__ module."""

from sw_metadata_bot import __version__


def test_version_is_set():
    """Test that __version__ is set."""
    assert __version__ is not None
    assert isinstance(__version__, str)


def test_version_format():
    """Test that version follows expected format."""
    # Version could be 'unknown' during development
    # or a proper version string like 0.1.0
    assert __version__ in ("unknown",) or "." in __version__
