"""
post.py — prism_post_review tool.

Phase 3: stub — validates inputs and returns a dry_run result.
Phase 8: will call GitHub MCP create_pull_request_review with inline
         comments anchored to the correct diff positions.
"""

from __future__ import annotations


def run_post_review(args: dict) -> dict:
    """
    Phase 3 stub.

    Expected args:
        pr_url   (str)   — GitHub PR URL
        findings (list)  — findings array from prism_analyze_pr
        summary  (str)   — review body text
        dry_run  (bool)  — if True (default), do not post; just validate
    """
    pr_url   = args.get("pr_url", "")
    findings = args.get("findings", [])
    dry_run  = args.get("dry_run", True)

    if not pr_url:
        return {"ok": False, "error": "pr_url is required"}

    return {
        "status":         "not_implemented",
        "dry_run":        dry_run,
        "pr_url":         pr_url,
        "findings_count": len(findings),
        "message":        (
            "prism_post_review is a Phase 8 feature. "
            "GitHub comment posting will be available after Phase 8 is implemented."
        ),
    }
