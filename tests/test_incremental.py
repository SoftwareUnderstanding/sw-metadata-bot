"""Tests for incremental decision engine."""

from sw_metadata_bot import incremental


def test_new_repo_creates_issue():
    """Create a new issue when no previous analysis exists."""
    decision = incremental.evaluate(
        previous_exists=False,
        unsubscribed=False,
        repo_updated=True,
        has_findings=True,
        identical_findings=False,
        previous_issue_open=False,
        codemeta_missing=False,
        previous_codemeta_missing=False,
    )
    assert decision.action == "create"
    assert decision.reason == "no_previous_analysis"


def test_unsubscribe_stops_flow():
    """Stop immediately when unsubscribe marker was found."""
    decision = incremental.evaluate(
        previous_exists=True,
        unsubscribed=True,
        repo_updated=True,
        has_findings=True,
        identical_findings=False,
        previous_issue_open=True,
        codemeta_missing=False,
        previous_codemeta_missing=False,
    )
    assert decision.action == "stop"
    assert decision.reason == "unsubscribe"


def test_identical_open_issue_stops():
    """Do not duplicate reports for identical findings on open issue."""
    decision = incremental.evaluate(
        previous_exists=True,
        unsubscribed=False,
        repo_updated=True,
        has_findings=True,
        identical_findings=True,
        previous_issue_open=True,
        codemeta_missing=False,
        previous_codemeta_missing=False,
    )
    assert decision.action == "stop"
    assert decision.reason == "identical_and_issue_open"


def test_changed_open_issue_updates_by_comment():
    """Post a comment update when findings changed and issue remains open."""
    decision = incremental.evaluate(
        previous_exists=True,
        unsubscribed=False,
        repo_updated=True,
        has_findings=True,
        identical_findings=False,
        previous_issue_open=True,
        codemeta_missing=False,
        previous_codemeta_missing=False,
    )
    assert decision.action == "comment"
    assert decision.reason == "changed_and_issue_open"


def test_no_findings_closes_open_issue():
    """Close open issue when latest analysis has no findings."""
    decision = incremental.evaluate(
        previous_exists=True,
        unsubscribed=False,
        repo_updated=True,
        has_findings=False,
        identical_findings=True,
        previous_issue_open=True,
        codemeta_missing=False,
        previous_codemeta_missing=False,
    )
    assert decision.action == "close"
    assert decision.reason == "no_findings_close_open_issue"


def test_no_findings_already_closed_issue_stops():
    """Stop without repeat action when issue was already closed in previous analysis."""
    decision = incremental.evaluate(
        previous_exists=True,
        unsubscribed=False,
        repo_updated=True,
        has_findings=False,
        identical_findings=True,
        previous_issue_open=False,
        codemeta_missing=False,
        previous_codemeta_missing=False,
    )
    assert decision.action == "stop"
    assert decision.reason == "no_findings"


def test_missing_codemeta_without_findings_creates_issue():
    """Create issue when codemeta is missing even without pitfalls/warnings."""
    decision = incremental.evaluate(
        previous_exists=True,
        unsubscribed=False,
        repo_updated=True,
        has_findings=False,
        identical_findings=True,
        previous_issue_open=False,
        codemeta_missing=True,
        previous_codemeta_missing=False,
    )
    assert decision.action == "create"
    assert decision.reason == "missing_codemeta"


def test_missing_codemeta_with_open_issue_stops_when_already_reported():
    """Avoid duplicate comments when codemeta was already missing on open issue."""
    decision = incremental.evaluate(
        previous_exists=True,
        unsubscribed=False,
        repo_updated=True,
        has_findings=False,
        identical_findings=True,
        previous_issue_open=True,
        codemeta_missing=True,
        previous_codemeta_missing=True,
    )
    assert decision.action == "stop"
    assert decision.reason == "missing_codemeta_identical_and_issue_open"
