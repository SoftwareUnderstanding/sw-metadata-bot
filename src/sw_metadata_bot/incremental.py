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
    codemeta_missing: bool,
    previous_codemeta_missing: bool,
) -> Decision:
    """Evaluate the configured decision tree and return action + reason."""
    if not previous_exists:
        return Decision(action="create", reason="no_previous_analysis")

    if unsubscribed:
        return Decision(action="stop", reason="unsubscribe")

    if not repo_updated:
        return Decision(action="stop", reason="repo_not_updated")

    if codemeta_missing and not has_findings:
        if previous_issue_open and previous_codemeta_missing:
            return Decision(
                action="stop",
                reason="missing_codemeta_identical_and_issue_open",
            )
        if previous_issue_open:
            return Decision(
                action="comment",
                reason="missing_codemeta_changed_and_issue_open",
            )
        return Decision(action="create", reason="missing_codemeta")

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
