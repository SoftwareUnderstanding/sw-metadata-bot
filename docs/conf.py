import os
import sys
from importlib import import_module
from pathlib import Path

try:
    tomllib = import_module("tomllib")
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback for doc builds
    tomllib = import_module("tomli")

# Ensure src is on the path for autodoc
DOCS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DOCS_DIR.parent
sys.path.insert(0, os.path.abspath(str(PROJECT_ROOT / "src")))

with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
    pyproject = tomllib.load(pyproject_file)

project_metadata = pyproject["project"]
doc_metadata = pyproject.get("tool", {}).get("sw_metadata_bot", {}).get("docs", {})

author_names = [
    entry["name"]
    for entry in project_metadata.get("authors", [])
    if isinstance(entry, dict) and entry.get("name")
]
author = ", ".join(author_names)
version = project_metadata["version"]
release = version
copyright_start_year = doc_metadata.get("copyright_year", "2026")

# Project information
project = project_metadata["name"]
copyright = f"{copyright_start_year}–present, {author}"

# Extensions
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.mermaid",
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
html_css_files = ["custom.css"]
html_title = f"{project} {release}"
html_theme_options = {
    "sidebar_hide_name": False,
}
