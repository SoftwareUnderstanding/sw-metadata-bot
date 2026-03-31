Welcome to sw-metadata-bot's documentation
==========================================

An automated bot that analyzes repository metadata quality and creates issues with improvement suggestions.

Part of the `CodeMetaSoft <https://w3id.org/codemetasoft>`_ project.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   usage
   api

Quick Start
-----------

Install from PyPI:

.. code-block:: bash

   pip install sw-metadata-bot

Run analysis with a campaign configuration file:

.. code-block:: bash

   sw-metadata-bot run-analysis --config-file path/to/config.json

Review the generated snapshot, then publish the approved results:

.. code-block:: bash

   sw-metadata-bot publish --analysis-root outputs/<run_name>/<snapshot_tag>

For installation choices, configuration examples, and token setup, see
:doc:`installation` and :doc:`usage`.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
