"""
test_review.py — Phase 2 smoke test.

Fetches a real GitHub PR diff via the API, runs the full Phase 2 pipeline,
and prints the results. This is the Phase 2 exit-criteria check.

Usage:
    python scripts/test_review.py --pr https://github.com/owner/repo/pull/NUMBER
    python scripts/test_review.py --pr https://github.com/owner/repo/pull/NUMBER --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.request
import urllib.error

# Make sure prism_mcp is importable from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env before importing pipeline modules
def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

_load_env()

from prism_mcp.core.pipeline import review_pr  # noqa: E402  (after path + env setup)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# ---------------------------------------------------------------------------
# GitHub helpers (lightweight — no external deps)
# ---------------------------------------------------------------------------

def _gh_get(url: str) -> dict | str:
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github+json",
        "User-Agent":    "PRISM-smoke-test",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        ct = r.headers.get("Content-Type", "")
        body = r.read()
        if "json" in ct:
            return json.loads(body)
        return body.decode("utf-8", errors="replace")


def _gh_diff(url: str) -> str:
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3.diff",
        "User-Agent":    "PRISM-smoke-test",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_pr_url(url: str) -> tuple[str, str, int]:
    """Return (owner, repo, pr_number) from a GitHub PR URL."""
    # https://github.com/OWNER/REPO/pull/NUMBER
    parts = url.rstrip("/").split("/")
    try:
        pull_idx = parts.index("pull")
        owner    = parts[pull_idx - 2]
        repo     = parts[pull_idx - 1]
        number   = int(parts[pull_idx + 1])
        return owner, repo, number
    except (ValueError, IndexError):
        print(f"ERROR: Cannot parse PR URL: {url}", file=sys.stderr)
        print("Expected format: https://github.com/OWNER/REPO/pull/NUMBER", file=sys.stderr)
        sys.exit(1)


def fetch_pr(owner: str, repo: str, number: int) -> tuple[dict, str, dict[str, str]]:
    """
    Returns (pr_meta, diff_text, file_contents).
    file_contents maps file_path → full file text for context.
    """
    base = f"https://api.github.com/repos/{owner}/{repo}"
    pr_url = f"{base}/pulls/{number}"

    print(f"Fetching PR metadata: {pr_url}")
    pr_meta_raw = _gh_get(pr_url)
    assert isinstance(pr_meta_raw, dict)

    pr_meta = {
        "title": pr_meta_raw.get("title", ""),
        "body":  pr_meta_raw.get("body", "") or "",
        "url":   pr_meta_raw.get("html_url", ""),
        "files": [],
    }

    # Fetch diff
    print("Fetching diff...")
    diff_text = _gh_diff(f"{base}/pulls/{number}")

    # Fetch changed file list for context
    print("Fetching changed file list...")
    files_raw = _gh_get(f"{base}/pulls/{number}/files")
    assert isinstance(files_raw, list)

    file_contents: dict[str, str] = {}
    head_sha = pr_meta_raw.get("head", {}).get("sha", "")

    changed_files = [f["filename"] for f in files_raw]
    pr_meta["files"] = changed_files

    # Fetch full file content for changed files (for context lines)
    for filename in changed_files[:20]:  # cap at 20
        try:
            file_data = _gh_get(f"{base}/contents/{filename}?ref={head_sha}")
            if isinstance(file_data, dict) and file_data.get("encoding") == "base64":
                import base64
                content = base64.b64decode(file_data["content"]).decode("utf-8", errors="replace")
                file_contents[filename] = content
        except Exception as e:
            print(f"  Could not fetch {filename}: {e}")

    return pr_meta, diff_text, file_contents


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    "Blocker": "\033[91m",  # red
    "Major":   "\033[93m",  # yellow
    "Minor":   "\033[94m",  # blue
    "Nit":     "\033[90m",  # grey
}
RESET = "\033[0m"
BOLD  = "\033[1m"
GREEN = "\033[92m"


def _print_result(result, verbose: bool = False) -> None:
    d = result.to_dict()

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}PRISM Review — Phase 2 Smoke Test{RESET}")
    print(f"{'=' * 60}")
    print(f"PR:           {d['pr_url'] or '(local)'}")
    print(f"Files:        {len(d['files_reviewed'])} reviewed, {len(d['files_skipped'])} skipped")
    print(f"Hunks:        {d['hunk_count']}")
    print(f"Duration:     {d['duration_s']}s")
    print(f"Model:        {d['model_used']}")
    print()

    # Risk score
    score = d["risk_score"]
    color = "\033[92m" if score < 20 else "\033[93m" if score < 50 else "\033[91m"
    print(f"Risk score:   {color}{BOLD}{score}/100{RESET}")
    print()

    # Severity breakdown
    print("Findings breakdown:")
    for sev, count in d["findings_by_severity"].items():
        if count:
            c = SEVERITY_COLORS.get(sev, "")
            print(f"  {c}{sev:10}{RESET}  {count}")
    print()

    # Findings
    findings = d["findings"]
    if not findings:
        print(f"{GREEN}No findings.{RESET}")
    else:
        print(f"{BOLD}{len(findings)} finding(s):{RESET}")
        for i, f in enumerate(findings, 1):
            sev_color = SEVERITY_COLORS.get(f["severity"], "")
            citation  = f"  [{f['citation']}]" if f.get("citation") else ""
            print(f"\n  {i}. {sev_color}[{f['severity']}]{RESET} {BOLD}{f['title']}{RESET}{citation}")
            print(f"     File: {f['file']}  L{f['line_start']}-{f['line_end']}  ({f['category']})")
            if verbose:
                print(f"     {f['explanation']}")
                if f.get("suggestion"):
                    print(f"     Suggestion: {f['suggestion'][:200]}")

    print()
    print(f"{BOLD}Summary:{RESET}")
    print(d["summary"])
    print()

    # JSON output for CI / piping
    if verbose:
        print(f"\n{BOLD}Full JSON result:{RESET}")
        print(json.dumps(d, indent=2))


# ---------------------------------------------------------------------------
# Exit criteria check
# ---------------------------------------------------------------------------

def _check_exit_criteria(result) -> bool:
    """
    Phase 2 exit criteria:
      - At least 1 finding returned (pipeline produced output)
      - At least 1 Blocker or Major if the PR has changed files
      - Risk score is > 0 when findings exist
    """
    d = result.to_dict()
    findings = d["findings"]
    passed = True

    print(f"\n{BOLD}Phase 2 Exit Criteria:{RESET}")

    # 1. Pipeline produced a result
    if d["hunk_count"] > 0:
        print(f"  {GREEN}[PASS]{RESET} Pipeline ran on {d['hunk_count']} hunk(s)")
    else:
        print(f"  \033[91m[FAIL]{RESET} No hunks processed — is the diff empty?")
        passed = False

    # 2. At least some findings (or empty diff is legitimate)
    if findings:
        print(f"  {GREEN}[PASS]{RESET} {len(findings)} finding(s) returned")
    elif d["hunk_count"] == 0:
        print(f"  \033[93m[WARN]{RESET} 0 findings — diff may be empty or trivial")
    else:
        print(f"  \033[93m[WARN]{RESET} 0 findings — model may need a PR with known issues")

    # 3. Risk score consistent with findings
    if findings and d["risk_score"] > 0:
        print(f"  {GREEN}[PASS]{RESET} Risk score is {d['risk_score']} (non-zero)")
    elif not findings:
        print(f"  \033[93m[WARN]{RESET} Risk score is 0 (no findings)")
    else:
        print(f"  \033[91m[FAIL]{RESET} Findings exist but risk score is 0")
        passed = False

    # 4. Severity tags are valid
    valid_sevs = {"Blocker", "Major", "Minor", "Nit"}
    bad = [f for f in findings if f["severity"] not in valid_sevs]
    if not bad:
        print(f"  {GREEN}[PASS]{RESET} All findings have valid severity tags")
    else:
        print(f"  \033[91m[FAIL]{RESET} {len(bad)} finding(s) have invalid severity: {bad[:2]}")
        passed = False

    print()
    if passed:
        print(f"{GREEN}{BOLD}Phase 2 PASSED — pipeline is working.{RESET}\n")
    else:
        print(f"\033[91m{BOLD}Phase 2 FAILED — see issues above.{RESET}\n")

    return passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="PRISM Phase 2 smoke test")
    parser.add_argument("--pr",      required=True, help="GitHub PR URL")
    parser.add_argument("--verbose", action="store_true", help="Print explanations + full JSON")
    parser.add_argument("--log",     default="WARNING", help="Log level (default: WARNING)")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.WARNING),
                        format="%(levelname)s %(name)s: %(message)s")

    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set in .env", file=sys.stderr)
        return 1

    owner, repo, number = _parse_pr_url(args.pr)
    print(f"\nReviewing PR #{number} in {owner}/{repo}...")

    try:
        pr_meta, diff_text, file_contents = fetch_pr(owner, repo, number)
    except urllib.error.HTTPError as e:
        print(f"ERROR: GitHub API returned {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("  → GitHub token is invalid or expired", file=sys.stderr)
        elif e.code == 404:
            print("  → PR not found or repo is private (check token has 'repo' scope)", file=sys.stderr)
        return 1

    def _progress(msg: str) -> None:
        print(f"  {msg}")

    result = review_pr(
        diff=diff_text,
        file_contents=file_contents,
        pr_meta=pr_meta,
        progress_cb=_progress,
    )

    _print_result(result, verbose=args.verbose)
    passed = _check_exit_criteria(result)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
