"""
Issue templates and formatting functions for repository host issues.
"""

ISSUE_TEMPLATE = """
Hi,

Your repository is part of the ESCAPE OSSR.
We are currently running a project to help repository maintainers detect and fix metadata issues. 
Your repository has been selected for our preliminary phase. You will find below a report containing some issues we have automatically detected and how to fix them.

Roadmap:
- This automated analysis will be turned into a GitHub action you can add to your repository to auto-detect future issues
- GitHub action will be improved with automated fixes

If you are not interested, you may comment "unsubscribe" to this issue and we will remove your repository from our list.

To know more about the CodeMetaSoft project: https://w3id.org/codemetasoft

---

# Analysis Report

{report_content}
"""


def format_issue_body(report_content: str) -> str:
    return ISSUE_TEMPLATE.format(report_content=report_content)
