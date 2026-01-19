# Quickstart

Self-contained steps to install, configure, and run `sw-metadata-bot`.

## What the bot does

- Reads pitfalls JSON-LD files produced by RSMetaCheck
- Generates an issue body (pitfalls, warnings, suggestions)
- Creates one issue per repository on GitHub or GitLab (cloud or self-hosted)
- Supports dry-run mode so you can review before posting

## Prerequisites

- Python 3.11 or 3.12
- GitHub or GitLab personal access token with permission to create issues
- RSMetaCheck analysis output (pitfalls `*.jsonld` files)
- Optional: `uv` (recommended) https://docs.astral.sh/uv

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
uv add git+https://github.com/SoftwareUnderstanding/sw-metadata-bot
```

Or with pip
With `pip`:
```bash
pip install git+https://github.com/codemetasoft/sw-metadata-bot.git
```

## Configure authentication

Export your tokens (only set what you need):

```bash
export GITHUB_API_TOKEN=ghp_xxxxxxxxxxxx      # GitHub
export GITLAB_API_TOKEN=glpat_xxxxxxxxxxxx    # GitLab (cloud or self-hosted)
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

## Produce analysis data (if you don't have it yet)

Use the bundled metacheck wrapper to create pitfalls outputs:

```bash
uv run sw-metadata-bot metacheck \
  --input https://github.com/owner/repo \
  --pitfalls-output pitfalls_outputs \
  --analysis-output analysis_results.json
```

This produces `pitfalls_outputs/*.jsonld`, which the bot consumes. 
You can also provide a json file as input listing mulitple repositories you want to analyse (see `assets/example_list_repo.json`).

## Create issues

Always start with dry-run: this will generate the issue content and save it locally without creating the actual issue on github.com.

```bash
uv run sw-metadata-bot create-issues \
  --pitfalls-output-dir ./pitfalls_outputs \
  --issues-dir ./issues_out \
  --dry-run
```

Post real issues (remove `--dry-run`):

```bash
uv run sw-metadata-bot create-issues \
  --pitfalls-output-dir ./pitfalls_outputs \
  --issues-dir ./issues_out
```

Key options:

- `--pitfalls-output-dir` : Directory containing `*.jsonld` analysis files
- `--issues-dir`          : Where to store generated issue bodies and reports
- `--dry-run`             : Generate content without posting

## Minimal examples (Python)

Detect platform and create issue (dry-run):

```python
from pathlib import Path
from sw_metadata_bot import pitfalls, github_api, create_issues

# Load pitfalls data
data = pitfalls.load_pitfalls(Path("pitfalls_outputs/repo.jsonld"))
repo_url = pitfalls.get_repository_url(data)

# Detect platform
platform_type = create_issues.detect_platform(repo_url)
print(f"Platform: {platform_type}")

# Generate issue content
report = pitfalls.format_report(repo_url, data)
body = pitfalls.create_issue_body(report)

# Create issue (dry-run mode)
github = github_api.GitHubAPI(dry_run=True)
issue_url = github.create_issue(repo_url, "Metadata Quality Report", body)
print(f"Issue URL: {issue_url}")
```

## Troubleshooting

- **Auth failed / 401**: Check `GITHUB_API_TOKEN` / `GITLAB_API_TOKEN` are exported and valid.
- **403 / 404 on issue creation**: You need write/triage permissions on the repository. Test with repos you own first.
- **Platform not supported**: Repo must be GitHub or GitLab (self-hosted GitLab is auto-detected).
- **No pitfalls found**: Ensure `--pitfalls-output-dir` points to metacheck JSON-LD outputs.
- **Review before posting**: Always run with `--dry-run` first and inspect files in `--issues-dir`.

## Supported platforms

- GitHub.com
- Gitlab.com (not tested yet)
