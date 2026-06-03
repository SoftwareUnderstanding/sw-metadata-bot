"""configurations schemas for the bot, defined using Pydantic models for validation and parsing of config files."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..constants import DEFAULT_OUTPUT_ROOT, DEFAULT_SNAPSHOT_TAG_FORMAT


class AnalysisConfig(BaseModel):
    """Configuration fields relevant to analysis and reporting.
    repositories is a list of repository URLs that the bot will analyze. Each URL should be in a standard format (e.g., https://github.com/user/repo.git).
    generate_codemeta_if_missing is a boolean flag that indicates whether the bot should attempt to generate a codemeta.json file for repositories that are missing one. If set to True, the bot will use available metadata and heuristics to create a codemeta.json file, which can help improve the quality of the analysis and reporting. If set to False, the bot will skip repositories that do not have a codemeta.json file, potentially resulting in less comprehensive analysis.
    """

    repositories: list[str]
    generate_codemeta_if_missing: bool = True

    @field_validator("repositories", mode="after")
    @classmethod
    def validate_repositories(cls, v):
        """Check that repositories list is not empty"""
        if not v:
            raise ValueError("Repositories list cannot be empty")
        return v


class IssueConfig(BaseModel):
    """Configuration fields relevant to issue publishing.
    custom_message allows users to specify a custom message template for issues, which can include placeholders for dynamic content such as repository name, check results, etc. If not provided, a default message will be used.
    opt_outs is a list of repository URLs that should be excluded from issue creation, even if they are included in the main repositories list. This allows users to selectively opt out of issue creation
    """

    custom_issue_message: Optional[str] = None
    opt_outs: Optional[list[str]] = Field(default_factory=list)


class OutputConfig(BaseModel):
    """Configuration fields relevant to output generation.
    output_root_dir specifies the root directory where the bot will save its output files, such as analysis reports and generated codemeta.json files. If not provided, it defaults to "outputs".""
    run_name is an optional identifier for the current run, which can be used to create a subdirectory within the output root directory. This allows users to organize outputs from different runs separately. If not provided, outputs will be saved directly under the root directory.
    snapshot_tag_format is an optional string that defines the format for snapshot tags used in output filenames. This can include placeholders for dynamic content such as timestamps or repository names. If not provided, it defaults to a standard format defined in constants.py.
    """

    output_root_dir: Optional[str] = DEFAULT_OUTPUT_ROOT
    run_name: Optional[str] = None
    snapshot_tag_format: Optional[str] = DEFAULT_SNAPSHOT_TAG_FORMAT

    @field_validator("snapshot_tag_format", mode="after")
    @classmethod
    def validate_snapshot_tag_format(cls, v):
        """Check that snapshot_tag_format is a valid string format handled by strftime."""
        if v is None:
            return v
        if not isinstance(v, str) or not v.strip():
            raise ValueError("snapshot_tag_format must be a non-empty string or null")
        # Test that the format string can be used with strftime
        try:
            from datetime import datetime

            datetime.now().strftime(v)
        except Exception as e:
            raise ValueError(f"Invalid snapshot_tag_format: {e}")
        return v


class BotConfig(BaseModel):
    """Top-level configuration model for the bot."""

    version: str = "1.0.0"
    analysis: AnalysisConfig
    # Optional sections in configuration
    issues: IssueConfig = Field(default_factory=IssueConfig)
    outputs: OutputConfig = Field(default_factory=OutputConfig)

    @model_validator(mode="after")
    def validate_opt_outs(self) -> "BotConfig":
        """Validate that opt-out repository URLs parts of the repositories list.
        If any opt-out URL is not in the repositories list, remove it from the config and log a warning."""
        valid_opt_outs = []
        if not self.issues.opt_outs:
            return self
        for url in self.issues.opt_outs:
            if url not in self.analysis.repositories:
                print(
                    f"Warning: Opt-out URL '{url}' is not in the repositories list and will be ignored."
                )
            else:
                valid_opt_outs.append(url)
        self.issues.opt_outs = valid_opt_outs

        return self

    @classmethod
    def from_json(cls, path: Path) -> "BotConfig":
        """Load configuration from a JSON file and validate it against the schema.
        The extra="forbid" option in model validation ensures that any unexpected fields in the config will raise a validation error, helping catch typos and misconfigurations early.
        """
        with path.open() as f:
            data = json.load(f)
        # extra forbid ensures that any unexpected fields in the config will raise a validation error, helping catch typos and misconfigurations early.
        return cls.model_validate(data, extra="forbid")

    def to_json(
        self,
        path: Path,
        explicit: bool = False,
    ) -> None:
        """Save configuration to a JSON file.
        If explicit is True, only fields that were explicitly set (not default values) will be included in the output JSON. This can help reduce clutter and make the config easier to read by omitting fields that are using default values.
        """
        data = self.model_dump(exclude_unset=not explicit)
        with path.open("w") as f:
            json.dump(data, f, indent=4)

    def get_repositories(self) -> list[str]:
        """Return the list of repositories to analyze, excluding any opt-outs."""
        return self.analysis.repositories

    def get_issue_opt_outs(self) -> list[str]:
        """Return the list of repositories that are opted out of issue creation."""
        if self.issues.opt_outs is None:
            return []
        return self.issues.opt_outs

    def get_generate_codemeta_if_missing(self) -> bool:
        """Return whether to generate codemeta.json if missing, defaulting to True."""
        return self.analysis.generate_codemeta_if_missing

    def get_custom_issue_message(self) -> Optional[str]:
        """Return the custom issue message template, or None if not set."""
        return self.issues.custom_issue_message

    def get_output_root_dir(self) -> str:
        """Return the configured output root directory."""
        return self.outputs.output_root_dir or DEFAULT_OUTPUT_ROOT

    def get_snapshot_tag_format(self) -> str:
        """Return the configured snapshot tag format."""
        return self.outputs.snapshot_tag_format or DEFAULT_SNAPSHOT_TAG_FORMAT

    def get_run_name(self) -> str:
        """Return the configured run name, or empty string if not set."""
        return self.outputs.run_name or ""

    def add_opt_out_repository(self, repo_url: str) -> bool:
        """Add a repository URL to the opt-out list for issue creation. Returns True if the URL was added, False if it was already in the opt-out list."""
        if repo_url not in self.analysis.repositories:
            print(
                f"Warning: Cannot add '{repo_url}' to opt-out list because it is not in the repositories list."
            )
            return False
            # create empty list if opt_outs is None (should not happen due to default_factory, but linters may not recognize it)
        if self.issues.opt_outs is None:
            self.issues.opt_outs = []
        if repo_url in self.issues.opt_outs:
            print(f"Repository '{repo_url}' is already in the opt-out list.")
            return False
        self.issues.opt_outs.append(repo_url)
        return True

    def resolve_snapshot_tag(self, explicit_snapshot_tag: Optional[str] = None) -> str:
        """Resolve the snapshot tag to use for output files.
        If an explicit snapshot tag is provided, it takes precedence. Otherwise, the snapshot tag is generated based on the current timestamp and the configured format."""
        snapshot_tag_format = self.get_snapshot_tag_format()
        if explicit_snapshot_tag is not None:
            return explicit_snapshot_tag
        return datetime.now(timezone.utc).strftime(snapshot_tag_format)
