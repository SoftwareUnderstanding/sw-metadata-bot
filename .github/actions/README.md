# SW Metadata Bot - GitHub Action

A GitHub Action to automatically analyze repository metadata quality and create issues with improvement suggestions.

Part of the [CodeMetaSoft](https://w3id.org/codemetasoft) project to improve research software metadata quality.

## Features

- **Automated Metadata Analysis**: Detects metadata pitfalls using the metacheck tool
- **Issue Generation**: Creates detailed issues with improvement suggestions
- **Dry-run Support**: Review generated issues before they're posted
- **Flexible Input**: Analyze single repositories or process batch files
- **Artifact Support**: Save and review analysis results

## Available Actions

### `run-pipeline` (recommended)

Run the full config-first pipeline (`metacheck` + `create-issues`) in one step.

```yaml
uses: codemetasoft/sw-metadata-bot/.github/actions/run-pipeline@v1
with:
  community-config-file: 'assets/ossr_list_url.json' # Required
  snapshot-tag: '20260312'                           # Optional
  dry-run: 'true'                                    # Optional (default: true)
  previous-report: ''                                # Optional
```

### `metacheck-analysis`

Legacy split action for analysis-only workflows.

Run metadata analysis on repositories to detect pitfalls.

```yaml
uses: codemetasoft/sw-metadata-bot/.github/actions/metacheck-analysis@v1
with:
  input: 'path/to/repos.json'  # Required: URL or JSON file
  pitfalls-output: 'pitfalls'   # Optional: Output directory (default: pitfalls_outputs)
  analysis-output: 'results.json' # Optional: Output file (default: analysis_results.json)
  skip-somef: 'false'           # Optional: Skip SoMEF execution (default: false)
  threshold: '0.8'              # Optional: SoMEF confidence threshold (default: 0.8)
```

**Outputs:**

- `pitfalls-output-dir`: Path to directory with pitfalls JSON-LD files
- `analysis-output-file`: Path to analysis summary JSON file

### `create-issues`

Legacy split action for issue handling only.

Create GitHub/GitLab issues based on analysis results.

```yaml
uses: codemetasoft/sw-metadata-bot/.github/actions/create-issues@v1
with:
  pitfalls-output-dir: 'pitfalls'  # Required: Directory with pitfalls files
  community-config-file: 'assets/ossr_list_url.json' # Required
  analysis-summary-file: 'analysis_results.json'      # Optional
  previous-report: ''                                 # Optional
  issues-dir: 'issues'             # Optional: Output directory (default: issues_output)
  dry-run: 'true'                  # Optional: Dry-run mode (default: true)
  log-level: 'INFO'                # Optional: Logging level (default: INFO)
```

**Outputs:**

- `issues-dir`: Path to directory with generated issue files

## Usage Examples

### Example 1: Analyze and Review Issues (Dry-run)

```yaml
name: Metadata Analysis
on:
  schedule:
    - cron: '0 0 * * 1'  # Weekly on Monday
  workflow_dispatch:

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run full pipeline
        uses: codemetasoft/sw-metadata-bot/.github/actions/run-pipeline@v1
        with:
          community-config-file: 'assets/ossr_list_url.json'
          dry-run: 'true'

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: analysis-results
          path: |
            issues_output/
            analysis_results.json
```

### Example 2: Analyze Single Repository

```yaml
- name: Analyze single repo
  uses: codemetasoft/sw-metadata-bot/.github/actions/metacheck-analysis@v1
  with:
    input: 'https://github.com/my-org/my-repo'
    pitfalls-output: 'my-repo-analysis'
```

### Example 3: Create Issues in Production

```yaml
- name: Create issues
  uses: codemetasoft/sw-metadata-bot/.github/actions/create-issues@v1
  with:
    pitfalls-output-dir: 'pitfalls'
    community-config-file: 'assets/ossr_list_url.json'
    dry-run: 'false'  # Actually create issues
    log-level: 'DEBUG'
```

## Input File Format

For batch analysis, provide a JSON file with repository URLs:

```json
[
  "https://github.com/owner/repo1",
  "https://github.com/owner/repo2",
  "https://gitlab.com/group/repo3"
]
```

## Generated Output

### Analysis Results (`analysis_results.json`)

Summary statistics and metadata quality metrics.

### Pitfalls Files (`pitfalls_outputs/`)

JSON-LD files containing detailed metadata issues detected for each repository.

### Issues Files (`issues_output/`)

Generated issue bodies ready to be posted to repositories. Each file corresponds to a repository that needs improvements.

## Authentication

When creating actual issues (dry-run: false):

- **GitHub**: Set `GITHUB_TOKEN` environment variable
- **GitLab**: Set `GITLAB_TOKEN` environment variable

```yaml
- name: Create issues
  uses: codemetasoft/sw-metadata-bot/.github/actions/create-issues@v1
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
  with:
    pitfalls-output-dir: 'pitfalls'
    community-config-file: 'assets/ossr_list_url.json'
    dry-run: 'false'
```

## Requirements

- Python 3.10+
- The action installs all dependencies via `uv`

## License

MIT

## Questions?

For issues, suggestions, or questions about the bot:

- GitHub: [codemetasoft/sw-metadata-bot](https://github.com/codemetasoft/sw-metadata-bot)
- Documentation: [CodeMetaSoft](https://w3id.org/codemetasoft)
