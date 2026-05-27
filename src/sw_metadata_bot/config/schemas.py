import json
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
    generate_codemeta_if_missing: Optional[bool] = True

    @field_validator("repositories", mode="after")
    @classmethod
    def validate_repositories(cls, v):
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

    output_root_dir: Optional[Path] = Path(DEFAULT_OUTPUT_ROOT)
    run_name: Optional[str] = None
    snapshot_tag_format: Optional[str] = DEFAULT_SNAPSHOT_TAG_FORMAT


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
