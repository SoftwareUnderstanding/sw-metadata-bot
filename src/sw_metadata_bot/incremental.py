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
    """Evaluate the configured decision tree and return action + reason.

    This function implements a cascading decision tree that determines whether to
    create a new issue, update an existing one with a comment, close it, or stop
    (skip). The logic prioritizes certain conditions to prevent unnecessary noise.

        Decision Tree (evaluated in order)::

                1. NO PREVIOUS ANALYSIS
                     action="create" (first-time analysis, always create issue)

                2. UNSUBSCRIBE DETECTED
                     action="stop" (user explicitly unsubscribed, respect their choice)

                3. REPOSITORY NOT UPDATED
                     action="stop" (no changes since last analysis, skip)

                4. MISSING CODEMETA WITHOUT OTHER FINDINGS
                     Check if codemeta status changed:
                     - If issue open AND codemeta status unchanged:
                         action="stop" (already reported, issue still relevant)
                     - If issue open AND codemeta status changed:
                         action="comment" (report that codemeta was added/removed)
                     - If no issue open:
                         action="create" (new codemeta issue)

                5. NO FINDINGS (REPO IS CLEAN)
                     - If issue is open:
                         action="close" (metadata quality improved, close issue)
                     - If no issue:
                         action="stop" (nothing to report)

                6. FINDINGS IDENTICAL TO PREVIOUS
                     Check issue state:
                     - If issue open:
                         action="stop" (same issue already posted)
                     - If issue closed:
                         action="create" (quality got worse again after improvements)

                7. FINDINGS CHANGED (DEFAULT CASE)
                     Check issue state:
                     - If issue open:
                         action="comment" (update existing issue with new findings)
                     - If no issue:
                         return "create" (quality changed while issue is closed)

    Args:
        previous_exists: Whether a previous analysis snapshot exists
        unsubscribed: Whether unsubscribe comment detected on existing issue
        repo_updated: Whether repository has new commits since last analysis
        has_findings: Whether current analysis found metadata issues
        identical_findings: Whether findings are identical to previous run
        previous_issue_open: Whether previously opened issue is still open
        codemeta_missing: Whether codemeta.json is missing in current analysis
        previous_codemeta_missing: Whether codemeta.json was missing in previous analysis

    Returns:
        Decision object with action and reason explaining the choice

    Note:
        For research software: This decision tree is intentionally conservative,
        favoring skipping unnecessary issues over creating duplicate noise. Changes
        to this logic should be discussed as they affect user experience.
    """
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
