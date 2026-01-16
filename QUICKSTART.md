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
With `uv` (recommended):
```bash
uv add git+https://github.com/codemetasoft/sw-metadata-bot.git
```

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
```
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
Always start with dry-run:
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
Detect platform:
```python
from sw_metadata_bot.config import RepositoryTypeDetector
print(RepositoryTypeDetector.detect("https://github.com/owner/repo"))
```

Create an issue (dry-run):
```python
from pathlib import Path
from sw_metadata_bot.config import PlatformFactory
from sw_metadata_bot.core import PitfallsAnalyzer
from sw_metadata_bot.utils import ReportFormatter, IssueTemplate

factory = PlatformFactory()
factory.set_dry_run(True)

pitfalls = PitfallsAnalyzer().load_pitfalls(Path("pitfalls_outputs/repo.jsonld"))
repo_url = PitfallsAnalyzer().get_repository_url(pitfalls)
report = ReportFormatter.format_pitfalls_report(repo_url, pitfalls)
issue_body = IssueTemplate.create_issue_body(report)

platform = factory.create_platform_from_url(repo_url)
repository = platform.parse_repository_url(repo_url)
issue = platform.create_issue(repository, "Metadata Quality Report", issue_body)
print(issue.url)
```

## Troubleshooting
- **Auth failed / 401**: Check `GITHUB_API_TOKEN` / `GITLAB_API_TOKEN` are exported and valid.
- **Platform not supported**: Repo must be GitHub or GitLab (self-hosted GitLab is auto-detected).
- **No pitfalls found**: Ensure `--pitfalls-output-dir` points to metacheck JSON-LD outputs.
- **Review before posting**: Always run with `--dry-run` first and inspect files in `--issues-dir`.

## Supported platforms
- GitHub.com
- GitLab.com
- Self-hosted GitLab instances
