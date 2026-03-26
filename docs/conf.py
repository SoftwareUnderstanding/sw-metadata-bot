import os
import sys

# Ensure src is on the path for autodoc
sys.path.insert(0, os.path.abspath("../src"))

# Project information
project = "sw-metadata-bot"
author = "Tom François"
copyright = "2026, Tom François"
release = "0.1.1"
version = "0.1"

# Extensions
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}
autodoc_typehints = "description"

# Napoleon settings for Google/NumPy style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "requests": ("https://requests.readthedocs.io/en/latest/", None),
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# HTML output
html_theme = "furo"
html_static_path = ["_static"]
html_title = f"{project} {release}"
html_theme_options = {
    "sidebar_hide_name": False,
}
