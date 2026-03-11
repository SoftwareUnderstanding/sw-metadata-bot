"""Decision engine for incremental issue lifecycle handling."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    """Decision outcome for a repository in incremental mode."""

    action: str
    reason: str


def evaluate(
    *,
    previous_exists: bool,
    unsubscribed: bool,
    repo_updated: bool,
    has_findings: bool,
    identical_findings: bool,
    previous_issue_open: bool,
) -> Decision:
    """Evaluate the configured decision tree and return action + reason."""
    if not previous_exists:
        return Decision(action="create", reason="no_previous_analysis")

    if unsubscribed:
        return Decision(action="stop", reason="unsubscribe")

    if not repo_updated:
        return Decision(action="stop", reason="repo_not_updated")

    if not has_findings:
        if previous_issue_open:
            return Decision(action="close", reason="no_findings_close_open_issue")
        return Decision(action="stop", reason="no_findings")

    if identical_findings:
        if previous_issue_open:
            return Decision(action="stop", reason="identical_and_issue_open")
        return Decision(action="create", reason="identical_but_issue_closed")

    if previous_issue_open:
        return Decision(action="comment", reason="changed_and_issue_open")

    return Decision(action="create", reason="changed_and_issue_closed")
