# sw-metadata-bot

A repository to keep the code of the RSMetaCheck bot for pushing issues with existing repository metadata

## Description

### Goal of the bot

Contact maintainers and developpers about our pitfalls and warnings analysis about metadata.
We want to start a discussion about the actual state of the quality of the given repository (possibly against others or standards).
Ideally, we would like to point out what should be modified to fix the actual pitfalls and warnings detected.

### Current approach

Based on the RS Metacheck package analysis, this bot creates an issue in the repository host provider to present:

- the detected pitfalls and warnings
- suggestions to fix these pitfalls and warnings.

### What is out of the scope of this project

This repository is not actually doing the evaluation of the metadata quality. It is using the analysis provided by the RsMetacheck package.
