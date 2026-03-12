Usage
=====

Command Line Interface
----------------------

The bot provides three main commands:

Analyze Repository Metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Analyze a repository's metadata using RSMetaCheck:

.. code-block:: bash

   sw-metadata-bot metacheck --repository-url https://github.com/example/repo

Options:

- ``--repository-url``: URL of the repository to analyze (required)
- ``--output-file``: Path to save the analysis results (JSON-LD format)

Create Issues
~~~~~~~~~~~~~

Create issues from metacheck JSON-LD outputs:

.. code-block:: bash

   sw-metadata-bot create-issues \
     --pitfalls-output-dir pitfalls_outputs \
     --issues-dir issues_out \
     --community-config-file assets/ossr_list_url.json \
     --dry-run

Options:

- ``--pitfalls-output-dir``: Directory containing the JSON-LD files produced by ``metacheck``
- ``--issues-dir``: Directory where issue bodies and ``report.json`` are written
- ``--community-config-file``: Community configuration file containing issue message and inline opt-outs
- ``--dry-run``: Preview the issues without creating them

Run Complete Pipeline
~~~~~~~~~~~~~~~~~~~~~

Run analysis and issue creation from a single community configuration file:

.. code-block:: bash

   sw-metadata-bot run-pipeline \
     --community-config-file assets/ossr_list_url.json \
     --dry-run

Options:

- ``--community-config-file``: Unified campaign configuration with repositories, issue settings, and output layout
- ``--snapshot-tag``: Optional snapshot folder override; otherwise the config default is used
- ``--previous-report``: Optional previous ``report.json`` for incremental issue handling
- ``--dry-run``: Generate outputs without posting issues

Example Workflow
----------------

1. Prepare a community configuration file listing repositories, issue settings, and outputs.

   .. code-block:: bash

      cat assets/ossr_list_url.json

2. Run the full pipeline in dry-run mode:

   .. code-block:: bash

      sw-metadata-bot run-pipeline --community-config-file assets/ossr_list_url.json --dry-run

3. Review the generated files under the configured output directory.

4. Post issues by re-running without ``--dry-run``:

   .. code-block:: bash

      sw-metadata-bot run-pipeline --community-config-file assets/ossr_list_url.json
