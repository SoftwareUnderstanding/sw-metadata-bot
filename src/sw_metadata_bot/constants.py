"""Centralized constants for sw-metadata-bot configuration and workflow.

This module defines all magic strings, field names, action values, and other
constants used throughout the codebase. Centralizing these here prevents
duplication and makes it easy to find and update values consistently.
"""

# =============================================================================
# Issue Publishing Action Names
# =============================================================================
# These represent the different states an analysis record can transition through
# during the publish workflow. Used in publish.py and reporting.py.

ACTION_FAILED = "failed"
"""Issue publication failed; will be retried or marked as permanent failure."""

ACTION_SKIPPED = "skipped"
"""Issue not created or updated (e.g., no new findings, unsubscribe detected)."""

ACTION_SIMULATED_CREATED = "simulated_created"
"""Dry-run mode: issue creation simulated but not actually posted."""

ACTION_CREATED = "created"
"""Issue successfully created on GitHub/GitLab."""

ACTION_UPDATED_BY_COMMENT = "updated_by_comment"
"""Updated existing issue by posting a new comment with latest findings."""

ACTION_CLOSED = "closed"
"""Issue closed because latest analysis found no pitfalls/warnings."""

# Action set for easy membership testing
PUBLISH_ACTIONS = frozenset(
    {
        ACTION_FAILED,
        ACTION_SKIPPED,
        ACTION_SIMULATED_CREATED,
        ACTION_CREATED,
        ACTION_UPDATED_BY_COMMENT,
        ACTION_CLOSED,
    }
)

# Actions that indicate successful issue posting (not dry-run, not failed)
SUCCESSFUL_PUBLISH_ACTIONS = frozenset(
    {
        ACTION_CREATED,
        ACTION_UPDATED_BY_COMMENT,
        ACTION_CLOSED,
    }
)


# =============================================================================
# Version Field Names
# =============================================================================
# These field names are used in analysis records to track software versions.
# Multiple names exist for backward compatibility with older analysis runs.

VERSION_FIELD_BOT = "sw_metadata_bot_version"
"""Canonical field name for sw-metadata-bot version in analysis records."""

VERSION_FIELD_BOT_LEGACY = "bot_version"
"""Legacy/deprecated field name for bot version (used in analysis_runtime.py parameter names)."""

VERSION_FIELD_RSMETACHECK = "rsmetacheck_version"
"""Field name for RSMetacheck/metacheck version (the analyzer tool version)."""

# Version fields that may appear in parsed records from older runs
VERSION_FIELDS_ALL = frozenset(
    {
        VERSION_FIELD_BOT,
        VERSION_FIELD_BOT_LEGACY,
        VERSION_FIELD_RSMETACHECK,
    }
)


# =============================================================================
# Output File Names & Paths
# =============================================================================
# Standard file names for analysis outputs and reports within snapshot directories.
# Used to identify important files when filtering and organizing analysis artifacts.

FILENAME_SOMEF_OUTPUT = "somef_output.json"
"""SOMEF tool output: structured metadata extracted from repository."""

FILENAME_PITFALL = "pitfall.jsonld"
"""JSON-LD format pitfalls/warnings from RSMetacheck analysis."""

FILENAME_REPORT = "report.json"
"""Per-repository unified report: single-record list with analysis results."""

FILENAME_ISSUE_REPORT = "issue_report.md"
"""Markdown issue body: human-readable summary of findings."""

FILENAME_CODEMETA_STATUS = "codemeta_status.json"
"""Codemeta existence check result: whether repository has codemeta.json."""

FILENAME_CODEMETA_GENERATED = "codemeta_generated.json"
"""Generated codemeta.json (if create-on-missing flag enabled)."""

FILENAME_RUN_REPORT = "run_report.json"
"""Snapshot-level unified report: list of all repository records in snapshot."""

FILENAME_ANALYSIS_RESULTS = "analysis_results.json"
"""Analysis summary: overall statistics and per-repo evaluation results."""

FILENAME_CONFIG_SNAPSHOT = "config.json"
"""Snapshot of input configuration used for this analysis run."""

# File blacklist: files to exclude when standardizing metacheck output directories
# Used in standardize_metacheck_outputs() to filter unwanted artifacts
METACHECK_OUTPUT_BLACKLIST = frozenset(
    {
        FILENAME_REPORT,
        FILENAME_ANALYSIS_RESULTS,
        FILENAME_RUN_REPORT,
        FILENAME_CONFIG_SNAPSHOT,
    }
)
"""Files to exclude when cleaning up metacheck output directories."""


# =============================================================================
# Check Code Patterns (RSMetacheck Format)
# =============================================================================
# RSMetacheck check codes follow a specific naming convention:
# P#### = Pitfall (data quality issue, e.g., P001 = missing codemeta.json)
# W#### = Warning (informational issue, e.g., W001 = incomplete metadata fields)
# Where #### is a 3-4 digit catalog ID within each category.

CHECK_TYPE_PITFALL = "P"
"""Check type prefix for pitfalls (high-priority issues)."""

CHECK_TYPE_WARNING = "W"
"""Check type prefix for warnings (informational/best-practice issues)."""

CHECK_TYPES = frozenset({CHECK_TYPE_PITFALL, CHECK_TYPE_WARNING})
"""Valid check type prefixes."""

# Regex pattern matching check codes (used in check_parsing.py)
# Matches strings like "P001", "W004", "p123" (case-insensitive).
# Pattern: # (literal hash) followed by P or W + 1-4 digits, at end of string.
CHECK_CODE_REGEX_PATTERN = r"#([PW]\d+)$"
"""Regex pattern for extracting check codes (e.g., extracts 'P001' from '#P001')."""


# =============================================================================
# Configuration Keys
# =============================================================================
# Standard keys used in config.json for accessing configuration values.
# Centralizing these reduces typos and makes refactoring easier.

CONFIG_KEY_REPOSITORIES = "repositories"
"""Config section: list of repository URLs to analyze."""

CONFIG_KEY_OUTPUTS = "outputs"
"""Config section: output directory configuration."""

CONFIG_KEY_COMMUNITY = "community"
"""Config section: community-specific settings."""

CONFIG_KEY_COMMUNITY_NAME = "name"
"""Community name (used to name output directory if not specified)."""

CONFIG_KEY_CUSTOM_MESSAGE = "custom_message"
"""Custom message to append to GitHub/GitLab issues."""

CONFIG_KEY_OPT_OUT_REPOSITORIES = "opt_out_repositories"
"""Repositories to skip analysis (legacy format)."""

CONFIG_KEY_SKIP_LIST = "skip_list"
"""Skip list configuration (newer format for incremental runs)."""

# Config sections for outputs directory structure
CONFIG_KEY_OUTPUTS_ROOT_DIR = "root_dir"
CONFIG_KEY_OUTPUTS_RUN_NAME = "run_name"
CONFIG_KEY_OUTPUTS_SNAPSHOT_TAG = "snapshot_tag"
CONFIG_KEY_OUTPUTS_SNAPSHOT_TAG_FORMAT = "snapshot_tag_format"


# =============================================================================
# Reason Codes (for record skipping/errors)
# =============================================================================
# Reason codes explain why an analysis record was skipped, failed, or takes
# a specific action. Used in publish.py and analysis_runtime.py.

REASON_CODE_UNSUBSCRIBE = "unsubscribe"
"""Record skipped because unsubscribe comment detected on issue."""

REASON_CODE_MISSING_RETRY_ACTION = "missing_retry_action"
"""Failed record cannot be retried (no original action stored)."""

REASON_CODE_PUBLISH_EXCEPTION = "publish_exception"
"""Publication failed due to exception (network, auth, API error)."""

REASON_CODE_OPT_OUT = "opt_out"
"""Repository opted out of analysis."""

REASON_CODE_MISSING_COMMIT = "missing_commit"
"""Cannot determine current commit for incremental analysis."""

REASON_CODE_COMMIT_UNCHANGED = "commit_unchanged"
"""Repository has not changed since last analysis."""


# =============================================================================
# Platform Identifiers
# =============================================================================
# Platform names as used in repo URLs and configuration.

PLATFORM_GITHUB = "github"
"""GitHub platform identifier."""

PLATFORM_GITLAB = "gitlab"
"""GitLab platform identifier."""

PLATFORM_GITLAB_COM = "gitlab.com"
"""GitLab.com platform identifier (variant)."""

# Platform set for easy validation
PLATFORMS = frozenset(
    {
        PLATFORM_GITHUB,
        PLATFORM_GITLAB,
        PLATFORM_GITLAB_COM,
    }
)


# =============================================================================
# Utilities
# =============================================================================


def is_valid_action(action: str) -> bool:
    """Check if a string is a valid publish action."""
    return action in PUBLISH_ACTIONS


def is_successful_action(action: str) -> bool:
    """Check if a publish action represents successful issue posting."""
    return action in SUCCESSFUL_PUBLISH_ACTIONS


def is_valid_platform(platform: str) -> bool:
    """Check if a string is a recognized platform identifier."""
    return platform in PLATFORMS
