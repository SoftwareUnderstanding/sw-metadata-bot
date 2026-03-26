Installation
============

Requirements
------------

- Python 3.11 or 3.12
- uv (recommended) or pip

Using uv (recommended)
----------------------

.. code-block:: bash

   uv add git+https://github.com/SoftwareUnderstanding/sw-metadata-bot

Using pip
---------

.. code-block:: bash

   pip install git+https://github.com/codemetasoft/sw-metadata-bot.git

From source
-----------

.. code-block:: bash

   git clone https://github.com/SoftwareUnderstanding/sw-metadata-bot.git
   cd sw-metadata-bot
   uv sync
   uv run sw-metadata-bot --help
