#!/bin/sh

# This script updates the version
# Usage: ./update_version_package.sh patch|minor|major
# return error if no argument is provided
if [ -z "$1" ]; then
  echo "Error: No version type provided. Please specify 'patch', 'minor', or 'major'."
  exit 1
fi

# update files
uv run python tools/release/update_version_package.py $1

# update the uv.lock file
uv sync

# retrieve new version
NEW_VERSION=$(uv run python -c "from importlib.metadata import version; print(version('sw-metadata-bot'))")
echo "Updated version to $NEW_VERSION"  
# commit the changes
git add pyproject.toml codemeta.json uv.lock
git commit -m "Update version to $NEW_VERSION"