Installation
============

Requirements
------------

- Python 3.10, 3.11, or 3.12
- uv (recommended) or pip

Install from PyPI
-----------------

Using uv (recommended)
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   uv add sw-metadata-bot

Using pip
~~~~~~~~~

.. code-block:: bash

   pip install sw-metadata-bot

Optional extras for documentation, tests, and development tooling are exposed
through the package metadata:

.. code-block:: bash

   pip install "sw-metadata-bot[docs]"
   pip install "sw-metadata-bot[test]"
   pip install "sw-metadata-bot[dev]"

From source for contributors
----------------------------

.. code-block:: bash

   git clone https://github.com/SoftwareUnderstanding/sw-metadata-bot.git
   cd sw-metadata-bot
   uv sync
   uv run sw-metadata-bot --help

For local development with the optional dependency sets declared in
``pyproject.toml``:

.. code-block:: bash

   pip install -e ".[dev,test,docs]"
