#!/bin/sh
# Before running this script, please use `uv version --bump <part>` to bump the version, which will automatically update the version in pyproject.toml and uv.lock.

# usecases:
# - new dev for a patch: `uv version --bump patch --bump dev`
# - set tag to stable (remove dev suffix): `uv version --bump stable`
# - new patch for a stable release: `uv version --bump patch`
# - new minor release: `uv version --bump minor`
# - new major release: `uv version --bump major`

# This script aims to replace the version in metadata files with the version from uv. 
# It also updates the dateModified field in codemeta.json and the version badge in README.md. 
# Finally, it commits the changes to git.

## Currently handles:
# - codemeta.json: updates the version and dateModified fields
# - README.md: updates the version badge
# - Citation.cff: updates the version field

NEW_VERSION=$(uv version | cut -d' ' -f2)
TODAY=$(date +%Y-%m-%d)

# Update codemeta.json
uv run python -c "
import json
with open('codemeta.json', 'r') as f:
    data = json.load(f)
data['version'] = '$NEW_VERSION'
data['softwareVersion'] = '$NEW_VERSION'
data['dateModified'] = '$TODAY'
with open('codemeta.json', 'w') as f:
    json.dump(data, f, indent=2)
"
echo "Update version and dateModified in codemeta.json"

# Update README.md
sed -i "s|badge/version-[^)]*-|badge/version-$NEW_VERSION-|g" README.md
echo "Update badge version in README.md"

# update the CITATION.cff file
sed -i "s/^version: .*/version: $NEW_VERSION/" CITATION.cff
echo "Update version in CITATION.cff"
sed -i "s/^date-released: .*/date-released: $TODAY/" CITATION.cff
echo "Update date-released in CITATION.cff"

# update the uv.lock file
uv sync

echo "Updated version to $NEW_VERSION"