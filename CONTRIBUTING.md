# Contributing Guide

Developer and maintainer steps to install, configure, and run sw-metadata-bot.

## What the bot does

- Run pitfalls detection using [RSMetaCheck package](https://github.com/SoftwareUnderstanding/RsMetaCheck)
- Handle analysis for multiple repositories
- Create repository centric output subfolders

## Prerequisites

- Python 3.10, 3.11, or 3.12
- GitHub or GitLab personal access token with permission to create issues
- Optional: [`uv`](https://docs.astral.sh/uv) (recommended)

## Install

### Use the package CLI

After cloning this project, set up the python environnment with uv:

```bash
uv sync
```

This will create the virtual environnment, download the dependencies and build the package locally.

### Use this package as dependency

With `uv` (recommended):

```bash
uv add sw-metadata-bot
```

Or with pip
With `pip`:

```bash
pip install sw-metadata-bot
```

The package metadata also exposes standard extras for release builds:

```bash
pip install "sw-metadata-bot[docs]"
pip install "sw-metadata-bot[test]"
pip install "sw-metadata-bot[dev]"
```

## Configure authentication

Export your tokens (only set what you need):

```bash
export GITHUB_API_TOKEN=ghp_xxxxxxxxxxxx      # GitHub.com
export GITLAB_API_TOKEN=glpat_xxxxxxxxxxxx    # GitLab.com
```

Convenient one-liner to load a `.env` file:

```bash
set -a; source .env; set +a
```

Example `.env`:

```bash
GITHUB_API_TOKEN=ghp_xxxxxxxxxxxx
GITLAB_API_TOKEN=glpat_xxxxxxxxxxxx
```

## Run complete pipeline

### Create configuration file

The pipeline now uses a single configuration file as its source of truth for:

- repository list `"repositories"`
- custom issue message `"custom_message"`
- inline opt-outs `"opt_outs"`
- output root `"root_dir"`
- run name `"run_name"`
- default snapshot-tag format `"snapshot_tag_format"`

Example config:

```json
{
  "repositories": [
    "https://github.com/SoftwareUnderstanding/sw-metadata-bot",
    "https://github.com/SoftwareUnderstanding/RsMetaCheck"
  ],
  "issues": {
    "custom_message": "This is a issue created for testing purposes. Several metadata issues were identified and could be addressed.",
    "opt_outs": [
    ]
  },
  "outputs": {
    "root_dir": "assets",
    "run_name": "example_run",
    "snapshot_tag_format": "%Y%m%d"
  }
}
```

`opt-out` lists the repositories for which issues won't be submitted but the repository is still analysed and part of the result outputs.

### Run analysis

To run the bot, start with analysis.

```bash
uv run sw-metadata-bot run-analysis \
  --config-file assets/ossr_list_url.json
```

You can override the generated snapshot tag when needed.

```bash
uv run sw-metadata-bot run-analysis \
  --config-file <path_to_your_config.json> \
  --snapshot-tag <example_suffix>
```

Output structure using the example config file provided:

```text
assets/
└── example_run/
  └── <snapshot_tag>/
    ├── analysis_results.json
    ├── config.json
    ├── run_report.json
    ├── github_com_softwareunderstanding_sw_metadata_bot/
    │   ├── issue_report.md
    │   ├── pitfall.jsonld
    │   ├── report.json
    │   └── somef_output.json
    └── github_com_softwareunderstanding_rsmetacheck/
      ├── issue_report.md
      ├── pitfall.jsonld
      ├── report.json
      └── somef_output.json
```

- `assets/`: output root selected by `"root_dir": "assets"` in the config.
- `example_run/`: run namespace selected by `"run_name": "example_run"`; this keeps outputs from different campaigns separated.
- `<snapshot_tag>/`: one analysis snapshot folder, usually generated from `"snapshot_tag_format": "%Y%m%d"` unless you override it with `--snapshot-tag`.
- `analysis_results.json`: global analysis summary for the full run, including the repositories that were evaluated and metadata such as commit identifiers.
- `config.json`: a copy of the effective configuration used for this snapshot, stored for reproducibility.
- `run_report.json`: top-level decision report for the whole batch, with counters and one record per repository.
- `github_com_softwareunderstanding_sw_metadata_bot/`: per-repository folder for `https://github.com/SoftwareUnderstanding/sw-metadata-bot`; repository URLs are sanitized to lowercase folder names.
- `github_com_softwareunderstanding_rsmetacheck/`: per-repository folder for `https://github.com/SoftwareUnderstanding/RsMetaCheck`; it contains the same artifact set as the other repository folder.
- `issue_report.md`: human-readable markdown report that can be reviewed before publication and reused as issue content.
- `pitfall.jsonld`: raw RSMetacheck JSON-LD output for the repository, including detected checks and evidence.
- `report.json`: machine-readable per-repository report summarizing findings, action/decision, identifiers, and links to generated artifacts.
- `somef_output.json`: raw SOMEF metadata extraction output used as input for the analysis pipeline.

The exact repository folder names depend on the repository URLs in your config, but the files created inside each repository folder follow this same pattern.

### Publish

If you want to submit the analysis to the actual repositories, you can publish from an existing analysis snapshot (no new analysis is generated):

```bash
uv run sw-metadata-bot publish \
  --analysis-root outputs/ossr/<snapshot_tag>
```

This requires setting up environment variables `GITHUB_API_TOKEN` / `GITLAB_API_TOKEN` with working tokens.
We recommend creating a `.env` file.
You can use the `uv run sw-metadata-bot verify-tokens` command to test them after set up.

## Troubleshooting

- **Auth failed / 401**: Check `GITHUB_API_TOKEN` / `GITLAB_API_TOKEN` are exported and valid.
- **403 / 404 on issue creation**: You need write/triage permissions on the repository. Test with repos you own first.
- **Platform not supported**: Repo must be GitHub or GitLab (self-hosted GitLab is auto-detected).
- **Review before posting**: Inspect snapshot reports after `run-analysis`, then run `publish` on the selected analysis root.

## Supported platforms

- GitHub.com
- Gitlab.com

Self-hosted GitLab instances are supported when you provide a token for the target host (not been tested yet).
Run the bot against your own organization or repositories where you have permission to open and manage issues.
