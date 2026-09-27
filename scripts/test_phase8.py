"""
test_phase8.py — Verify Phase 8 GitHub PR review posting, diff mapping, and safety gate.
"""

import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from prism_mcp.tools.post import run_post_review, format_review_comment, format_review_body

def main():
    print("=" * 60)
    print("PRISM Phase 8 Verification: GitHub PR Review Posting")
    print("=" * 60)

    # Findings matching actual files in pallets/flask/pull/5000
    mock_findings = [
        {
            "severity": "Blocker",
            "category": "security",
            "file": ".github/workflows/flaskr-ci.yaml",
            "line_start": 12,
            "line_end": 15,
            "title": "Unpinned GitHub Action version in workflow step",
            "explanation": "GitHub Actions should use immutable SHA pinning rather than mutable branch/major tags to prevent supply-chain attacks.",
            "suggestion": "- uses: actions/checkout@v3  # Pin to full commit SHA",
            "citation": "OWASP A06:2021 Vulnerable and Outdated Components",
        },
        {
            "severity": "Major",
            "category": "maintainability",
            "file": ".github/workflows/flaskr-ci.yaml",
            "line_start": 999,  # line out of diff range — tests line snapping to nearest diff line!
            "line_end": 1005,
            "title": "Redundant workflow trigger configuration",
            "explanation": "Workflow triggers overlap between pull_request and push branches.",
            "suggestion": "branches: [ main ]",
            "citation": "Code smell: Redundant Configuration",
        },
    ]

    pr_url = "https://github.com/pallets/flask/pull/5000"

    # Test 1: Dry run on external PR (pallets/flask/pull/5000)
    print("\n[TEST 1] Dry-run simulation on real PR (pallets/flask/pull/5000)...")
    res1 = run_post_review({
        "pr_url": pr_url,
        "findings": mock_findings,
        "summary": "This PR adds automated GitHub Actions workflows for continuous integration testing and publishing.",
        "dry_run": True,
    })

    print(f"Status: {res1.get('status')} | OK: {res1.get('ok')}")
    print(f"Message: {res1.get('message')}")
    print(f"Inline comments count: {res1.get('inline_comments_count')}")
    print(f"Commit SHA: {res1.get('commit_id')}")

    assert res1.get("ok") is True, f"Dry run failed: {res1.get('error')}"
    assert res1.get("inline_comments_count") == 2, f"Expected 2 inline comments, got {res1.get('inline_comments_count')}"

    comments = res1.get("formatted_comments", [])
    for idx, c in enumerate(comments):
        print(f"\n  Comment #{idx+1}:")
        print(f"    Path: {c['path']}")
        print(f"    Line: {c['line']} (Snapped: {c.get('snapped')})")
        print(f"    Diff Position: {c.get('diff_position')}")
        print(f"    Preview: {c.get('preview')}")

    # Verify first comment mapped exactly to line 12
    assert comments[0]["line"] == 12, f"Expected line 12, got {comments[0]['line']}"
    assert comments[0]["snapped"] is False
    # Verify second comment was snapped from 999 to valid diff line (e.g. 64)
    assert comments[1]["snapped"] is True
    print("\nPASS: Diff mapping and snapping successfully mapped both comments.")

    # Test 2: Safety Gate on external PR with dry_run = False
    print("\n[TEST 2] Safety Gate: Attempt live posting on external repo (pallets/flask)...")
    res2 = run_post_review({
        "pr_url": pr_url,
        "findings": mock_findings,
        "summary": "Test safety gate",
        "dry_run": False,
    })

    print(f"Status: {res2.get('status')} | OK: {res2.get('ok')}")
    print(f"Error: {res2.get('error')}")

    assert res2.get("ok") is False, "Safety gate failed: allowed posting to non-demo repo!"
    assert "Safety gate blocked" in res2.get("error", ""), "Safety gate error message missing!"
    print("PASS: Safety gate successfully blocked live posting to external repo.")

    # Test 3: Formatting verification
    print("\n[TEST 3] Comment Markdown formatting verification...")
    formatted_c = format_review_comment(mock_findings[0])
    print("Sample Formatted Comment:\n" + "-" * 40)
    print(formatted_c)
    print("-" * 40)

    assert "**[Blocker]" in formatted_c
    assert "```yaml" in formatted_c  # Detected .yaml language!
    assert "OWASP A06:2021" in formatted_c

    print("\n[ALL PHASE 8 TESTS PASSED SUCCESSFULLY!]")

if __name__ == "__main__":
    main()
