Usage
=====

Command Line Interface
----------------------

The bot provides two main commands:

Analyze Repository Metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Analyze a repository's metadata using RSMetaCheck:

.. code-block:: bash

   sw-metadata-bot metacheck --repository-url https://github.com/example/repo

Options:

- ``--repository-url``: URL of the repository to analyze (required)
- ``--output-file``: Path to save the analysis results (JSON-LD format)

Create GitHub Issues
~~~~~~~~~~~~~~~~~~~~

Create issues based on analysis results:

.. code-block:: bash

   sw-metadata-bot create-issues --input-file results.jsonld --token YOUR_GITHUB_TOKEN

Options:

- ``--input-file``: Path to the analysis results file (required)
- ``--token``: GitHub personal access token (required)
- ``--dry-run``: Preview the issues without creating them

Example Workflow
----------------

1. Analyze a repository:

   .. code-block:: bash

      sw-metadata-bot metacheck --repository-url https://github.com/example/repo --output-file analysis.jsonld

2. Review the analysis results in ``analysis.jsonld``

3. Create issues:

   .. code-block:: bash

      sw-metadata-bot create-issues --input-file analysis.jsonld --token ghp_YOUR_TOKEN

4. Or preview issues without creating them:

   .. code-block:: bash

      sw-metadata-bot create-issues --input-file analysis.jsonld --token ghp_YOUR_TOKEN --dry-run
