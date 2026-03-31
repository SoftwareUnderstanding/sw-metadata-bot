# sw-metadata-bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.1-blue.svg)](https://github.com/SoftwareUnderstanding/sw-metadata-bot/releases)
[![Python 3.10--3.12](https://img.shields.io/badge/python-3.10--3.12-blue.svg)](https://www.python.org/downloads/)
[![CI (build)](https://github.com/SoftwareUnderstanding/sw-metadata-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/SoftwareUnderstanding/sw-metadata-bot/actions/workflows/ci.yml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
![coverage](coverage.svg)
![interrogate](interrogate_badge.svg)

An automated bot that analyzes repository metadata quality and creates issues with improvement suggestions.

Part of the [CodeMetaSoft](https://w3id.org/codemetasoft) project to improve research software metadata quality.

---

## 📋 What This Bot Does

If you received an issue from this bot, it means your repository's metadata was automatically analyzed and some improvements were detected.

The issue contains:

- **Pitfalls**: Critical metadata issues that should be fixed
- **Warnings**: Metadata improvements that are recommended
- **Suggestions**: Specific recommendations on how to fix each issue

### Example Issues You Might See

- Missing or incomplete `LICENSE` file
- No `CITATION.cff` file (for software citation)
- Incomplete or missing `README` sections
- Missing repository metadata (topics, description, etc.)
- Outdated dependencies
- Missing software documentation

---

## 💬 How to Respond

### If You Agree with the Suggestions

Fix the identified issues and **close the issue** with a comment explaining what you fixed. Your improvements help your software become more discoverable and citable!

### If You Disagree or Have Questions

Feel free to **comment on the issue**. We're happy to discuss the suggestions and help clarify what's needed.

### If You're Not Interested

Simply comment **"unsubscribe"** on the issue and we'll remove your repository from future analysis.

---

## 🔍 What Analysis Is Used

This bot uses [RSMetaCheck](https://github.com/SoftwareUnderstanding/RsMetaCheck), which analyzes:

- Software metadata completeness
- Citation and documentation quality
- Repository structure and best practices

The bot **does not**:

- Modify your code or files
- Make pull requests
- Have access to your repository secrets

---

## 📚 Learn More

- [CodeMetaSoft Project](https://w3id.org/codemetasoft) - About the initiative
- [RSMetaCheck](https://github.com/SoftwareUnderstanding/RsMetaCheck) - The analysis tool
- [Citation File Format](https://citation-file-format.github.io/) - How to add CITATION.cff

---

## 🛠️ For Maintainers Running This Bot

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and usage instructions.

The pipeline is config driven: one JSON file defines the repository list, issue message, inline opt-outs, and output layout.

Supported platforms:

- ✅ GitHub.com
- ✅ Gitlab.com

Future:

- Self-hosted GitLab instances

---

## 📝 License

See [LICENSE](LICENSE) file.
