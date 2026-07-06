# sw-metadata-bot

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19468976.svg)](https://doi.org/10.5281/zenodo.19468976)
[![SWH](https://archive.softwareheritage.org/badge/swh:1:dir:9f3d474c040158cc675e8db135767e0d2d3fba7b/)](https://archive.softwareheritage.org/swh:1:dir:9f3d474c040158cc675e8db135767e0d2d3fba7b;origin=https://github.com/SoftwareUnderstanding/sw-metadata-bot;visit=swh:1:snp:03da984544982fdf5aa1f556012b917250f1e4c3;anchor=swh:1:rev:fc64150edf2e35f045cf3858d81b00ca6e7f6e68)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.3-blue.svg)](https://github.com/SoftwareUnderstanding/sw-metadata-bot/releases)
[![Python 3.11--3.12](https://img.shields.io/badge/python-3.11--3.12-blue.svg)](https://www.python.org/downloads/)
[![CI (build)](https://github.com/SoftwareUnderstanding/sw-metadata-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/SoftwareUnderstanding/sw-metadata-bot/actions/workflows/ci.yml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
![coverage](coverage.svg)
![interrogate](interrogate_badge.svg)
[![RsMetaCheck Validation](https://github.com/SoftwareUnderstanding/sw-metadata-bot/actions/workflows/rsmetacheck.yml/badge.svg)](https://github.com/SoftwareUnderstanding/sw-metadata-bot/actions/workflows/rsmetacheck.yml)

An automated bot that analyzes repository metadata quality and creates issues with improvement suggestions.

Part of the [CodeMetaSoft](https://w3id.org/codemetasoft) project to improve research software metadata quality.

[![Subscribe](https://img.shields.io/badge/subscribe%20to%20the%20bot-blue?style=for-the-badge)](https://github.com/SoftwareUnderstanding/sw-metadata-bot/issues/new?template=subscribe.yml)

---

## 📋 What This Bot Does

If you received an issue from this bot, it means your repository's metadata was automatically analyzed and some improvements were detected on the main default branch.

The issue contains:

- **Pitfalls**: Critical metadata issues that should be fixed
- **Warnings**: Metadata improvements that are recommended
- **Suggestions**: Specific recommendations on how to fix each issue
- **Codemeta.json generation**: if your repo does not contain any `codemeta.json` file, the bot suggests one.  

### Example Issues You Might See

```md
### [P002](https://w3id.org/rsmetacheck/catalog/#P002)
**Evidence:** P002 detected: LICENSE file contains unreplaced template placeholders

**Suggestion:** Update the copyright section with accurate names, organizations, and the current year. Personalizing this section ensures clarity and legal accuracy.
```

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

The bot is handling self-hosted gitlab platform but requires providing a token to this server (and not gitlab.com).

---

## 📝 License

See [LICENSE](LICENSE) file.
