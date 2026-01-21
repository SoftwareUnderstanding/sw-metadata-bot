import os
import sys

project = "sw-metadata-bot"
author = "Tom François"

# Ensure src is on the path for autodoc
sys.path.insert(0, os.path.abspath("../src"))

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]

templates_path = ["_templates"]
exclude_patterns = []

html_theme = "furo"
html_static_path = ["_static"]
