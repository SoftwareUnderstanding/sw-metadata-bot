# Command to run OSSR analysis on a list of repositories and optionally publish issues.

# Usage: ./ossr_analysis.sh

OSSR_CONFIG_FILE="assets/ossr_list_url.json"


echo "Running OSSR analysis with configuration from $OSSR_CONFIG_FILE and snapshot tag $SNAPSHOT_TAG."

uv run sw-metadata-bot run-analysis \
--config-file "$OSSR_CONFIG_FILE"

echo "Do you want to publish issues from this analysis? (y/n)"
read -r publish_issues
if [[ "$publish_issues" == "y" ]]; then
    uv run sw-metadata-bot publish --analysis-root "$ANALYSIS_ROOT"
else
    echo "Publish step skipped."
fi