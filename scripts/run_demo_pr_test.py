import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from prism_mcp.tools.analyze import run_analyze_pr
from prism_mcp.tools.post import run_post_review

def progress_cb(stage: str, msg: str, pct: int):
    print(f"[{stage.upper()}] ({pct}%) {msg}", flush=True)

def main():
    pr_url = "https://github.com/DhruvPatel0110/BOB_2.0-No_idea/pull/1"
    print("=" * 60)
    print("TESTING PRISM ON SMALL DEMO PR:", pr_url)
    print("=" * 60)

    # 1. Analyze PR
    t0 = time.time()
    result = run_analyze_pr({"pr_url": pr_url, "progress_cb": progress_cb})
    t1 = time.time()

    duration = round(t1 - t0, 1)
    print(f"\n[ANALYSIS COMPLETE in {duration}s!]")
    print(f"Risk Score: {result.get('risk_score')}")
    print(f"Summary:\n{result.get('summary')}\n")

    findings = result.get("findings", [])
    print(f"Findings Count: {len(findings)}")
    for i, f in enumerate(findings):
        print(f"\nFinding #{i+1}:")
        print(f"  [{f.get('severity')}] {f.get('title')}")
        print(f"  Location: {f.get('file')}:{f.get('line_start')}")
        print(f"  Citation: {f.get('citation')}")
        print(f"  Explanation: {f.get('explanation')}")
        print(f"  Suggestion:\n{f.get('suggestion')}")

    # 2. Test Phase 8: Dry Run (Simulation)
    print("\n" + "=" * 60)
    print("PHASE 8 TEST 1: Dry-Run Simulation")
    print("=" * 60)
    dry_res = run_post_review({
        "pr_url": pr_url,
        "findings": findings,
        "summary": result.get("summary", ""),
        "dry_run": True,
    })
    print(f"Status: {dry_res.get('status')} | OK: {dry_res.get('ok')}")
    print(f"Message: {dry_res.get('message')}")
    print(f"Inline comments count: {dry_res.get('inline_comments_count')}")
    for c in dry_res.get("formatted_comments", []):
        print(f"  - Line {c['line']}: {c['path']} (diff pos {c.get('diff_position')})")

    # 3. Test Phase 8: Live Post (Real GitHub PR Review!)
    print("\n" + "=" * 60)
    print("PHASE 8 TEST 2: LIVE Post to GitHub (dry_run=False)")
    print("=" * 60)
    live_res = run_post_review({
        "pr_url": pr_url,
        "findings": findings,
        "summary": result.get("summary", ""),
        "dry_run": False,
    })
    print(f"Status: {live_res.get('status')} | OK: {live_res.get('ok')}")
    print(f"Message: {live_res.get('message')}")
    print(f"GitHub Review URL: {live_res.get('html_url')}")
    print(f"Review ID: {live_res.get('review_id')}")

if __name__ == "__main__":
    main()
