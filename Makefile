
.PHONY: rsmetacheck-run clean

# arguments


# Run rsmetacheck via the `uv` runner and place outputs under assets/example_analysis/
rsmetacheck-run:
	@mkdir -p assets/example_analysis
	@echo "Running: uv run rsmetacheck --input https://github.com/SoftwareUnderstanding/rsmetacheck --analysis-output assets/example_analysis/"
	@uv run rsmetacheck --input https://github.com/SoftwareUnderstanding/rsmetacheck --somef-output assets/example_analysis/somef/ --pitfalls-output assets/example_analysis/pitfalls/ --analysis-output assets/example_analysis/rsmetacheck_analysis.json

clean:
	@rm -rf assets/example_analysis
	@echo "Cleaned assets/example_analysis"
