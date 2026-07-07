import json

from sw_metadata_bot.report_summary import summarize_analysis_folder
from sw_metadata_bot.reporting import load_report


def test_load_report_and_summarize_analysis_folder(tmp_path):
    report_file = tmp_path / "run_report.json"
    report_file.write_text(
        json.dumps(
            {
                "run_metadata": {"dry_run": False},
                "counters": {"total": 3},
                "records": [
                    {
                        "repo_url": "https://github.com/example/one",
                        "platform": "github",
                        "pitfalls_count": 2,
                        "warnings_count": 3,
                        "pitfalls_ids": ["P001", "P002"],
                        "warnings_ids": ["W001"],
                        "action": "created",
                        "reason_code": "missing_codemeta",
                    },
                    {
                        "repo_url": "https://github.com/example/two",
                        "platform": "github",
                        "pitfalls_count": 1,
                        "warnings_count": 2,
                        "pitfalls_ids": ["P001"],
                        "warnings_ids": ["W001", "W002"],
                        "action": "skipped",
                        "reason_code": "same_repository",
                    },
                    {
                        "repo_url": "https://github.com/example/three",
                        "platform": "github",
                        "pitfalls_count": 0,
                        "warnings_count": 1,
                        "pitfalls_ids": [],
                        "warnings_ids": ["W002"],
                        "action": "skipped",
                        "reason_code": "same_analysis",
                    },
                ],
            }
        )
    )

    report = load_report(report_file)
    summary = summarize_analysis_folder(tmp_path)

    assert report.run_metadata["dry_run"] is False
    assert report.records[0].pitfalls_ids == ("P001", "P002")

    assert summary["repository_count"] == 3
    assert summary["pitfalls_by_id"] == {"P001": 2, "P002": 1}
    assert summary["warnings_by_id"] == {"W001": 2, "W002": 2}
    assert summary["total_pitfalls"] == 3
    assert summary["total_warnings"] == 6
    assert summary["issues_created"] == 1
    assert summary["actions"] == {"created": 1, "skipped": 2}
    assert summary["reason_codes"] == {
        "missing_codemeta": 1,
        "same_analysis": 1,
        "same_repository": 1,
    }
    assert summary["reason_codes_by_action"] == {
        "created": {"missing_codemeta": 1},
        "skipped": {"same_analysis": 1, "same_repository": 1},
    }
    assert summary["reason_code_percentages_by_action"] == {
        "created": {"missing_codemeta": 100.0},
        "skipped": {"same_analysis": 50.0, "same_repository": 50.0},
    }
