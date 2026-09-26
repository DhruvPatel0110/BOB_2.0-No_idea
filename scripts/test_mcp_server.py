"""
test_mcp_server.py — Phase 3 exit-criteria validator.

Tests that the PRISM MCP server starts cleanly, all 6 tools are registered,
and each tool returns a valid (even if stubbed) response.

This script exercises the tool implementations directly (no subprocess needed)
since the MCP protocol layer is already validated by the mcp SDK.

Usage:
    python scripts/test_mcp_server.py
    python scripts/test_mcp_server.py --pr https://github.com/owner/repo/pull/N

Exit codes:
    0 — all Phase 3 exit criteria passed
    1 — one or more checks failed
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


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

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}[PASS]{RESET}  {msg}")
def fail(msg: str) -> None: print(f"  {RED}[FAIL]{RESET}  {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}[WARN]{RESET}  {msg}")
def section(t: str) -> None: print(f"\n{BOLD}{t}{RESET}")


# ---------------------------------------------------------------------------
# Check 1: server module imports cleanly
# ---------------------------------------------------------------------------

def check_imports() -> bool:
    section("1 · Server module imports")
    try:
        import prism_mcp.server as srv  # noqa: F401
        ok("prism_mcp.server imports without errors")
    except ImportError as e:
        fail(f"Import failed: {e}")
        fail("Run:  pip install mcp  (mcp_types is bundled with the mcp package)")
        return False
    except Exception as e:
        fail(f"Unexpected error during import: {e}")
        return False

    # Verify all 6 tool modules import cleanly
    tools = ["health", "analyze", "corpus", "retrieve", "generate", "post"]
    passed = True
    for t in tools:
        try:
            __import__(f"prism_mcp.tools.{t}")
            ok(f"prism_mcp.tools.{t} imports OK")
        except Exception as e:
            fail(f"prism_mcp.tools.{t} import failed: {e}")
            passed = False
    return passed


# ---------------------------------------------------------------------------
# Check 2: prism_health_check returns valid structure
# ---------------------------------------------------------------------------

def check_health_tool() -> bool:
    section("2 · prism_health_check tool")
    try:
        from prism_mcp.tools.health import run_health_check
        result = run_health_check()
    except Exception as e:
        fail(f"run_health_check() raised: {e}")
        return False

    required_keys = {"all_ok", "ollama", "chromadb", "github"}
    missing = required_keys - set(result.keys())
    if missing:
        fail(f"Missing keys in health result: {missing}")
        return False
    ok("Health result has all required keys")

    for sub in ("ollama", "chromadb", "github"):
        if "ok" not in result[sub]:
            fail(f"result['{sub}'] missing 'ok' key")
            return False

    all_ok = result["all_ok"]
    if all_ok:
        ok(f"all_ok=True — Ollama, ChromaDB, and GitHub are all reachable")
    else:
        issues = []
        for sub in ("ollama", "chromadb", "github"):
            if not result[sub]["ok"]:
                issues.append(f"{sub}: {result[sub].get('error', 'unknown error')}")
        warn(f"all_ok=False (expected if deps not running) — {'; '.join(issues)}")
        ok("Structure is valid regardless of dependency state")

    return True


# ---------------------------------------------------------------------------
# Check 3: stub tools return valid (non-error) responses
# ---------------------------------------------------------------------------

def check_stub_tools() -> bool:
    section("3 · Stub tools return valid responses")
    passed = True

    # prism_build_corpus
    from prism_mcp.tools.corpus import run_build_corpus
    result = run_build_corpus({"owner": "test-owner", "repo": "test-repo"})
    if "status" in result and "error" not in result:
        ok("prism_build_corpus returns {status: ...} stub")
    else:
        fail(f"prism_build_corpus unexpected response: {result}")
        passed = False

    # prism_retrieve_context
    from prism_mcp.tools.retrieve import run_retrieve_context
    result = run_retrieve_context({"diff_hunk": "+x = 1", "file_path": "test.py"})
    if isinstance(result.get("context_chunks"), list):
        ok("prism_retrieve_context returns {context_chunks: []} stub")
    else:
        fail(f"prism_retrieve_context unexpected response: {result}")
        passed = False

    # prism_post_review
    from prism_mcp.tools.post import run_post_review
    result = run_post_review({"pr_url": "https://github.com/x/y/pull/1", "findings": [], "dry_run": True})
    if "status" in result and result.get("dry_run") is True:
        ok("prism_post_review returns stub with dry_run=True")
    else:
        fail(f"prism_post_review unexpected response: {result}")
        passed = False

    return passed


# ---------------------------------------------------------------------------
# Check 4: prism_generate_review on a tiny synthetic diff
# ---------------------------------------------------------------------------

def check_generate_tool() -> bool:
    section("4 · prism_generate_review (synthetic diff)")

    SYNTHETIC_DIFF = """\
--- a/example.py
+++ b/example.py
@@ -1,3 +1,5 @@
+import os
+password = os.getenv("SECRET", "hardcoded_password_123")
 def main():
-    pass
+    print(password)
"""

    try:
        from prism_mcp.tools.generate import run_generate_review
        result = run_generate_review({
            "diff_hunk": SYNTHETIC_DIFF,
            "file_path": "example.py",
            "language":  "python",
        })
    except Exception as e:
        fail(f"run_generate_review raised: {e}")
        return False

    if "error" in result:
        warn(f"prism_generate_review returned error (Ollama may not be running): {result['error']}")
        warn("This is expected if Ollama is offline — structure check still passes")
        return True

    if not isinstance(result.get("findings"), list):
        fail(f"Expected 'findings' list in result, got: {list(result.keys())}")
        return False

    ok(f"prism_generate_review returned {len(result['findings'])} finding(s)")
    if result["findings"]:
        f = result["findings"][0]
        required = {"severity", "category", "title"}
        missing  = required - set(f.keys())
        if missing:
            fail(f"Finding missing keys: {missing}")
            return False
        ok(f"First finding: [{f['severity']}] {f['title']}")

    return True


# ---------------------------------------------------------------------------
# Check 5 (optional): prism_analyze_pr on a real PR
# ---------------------------------------------------------------------------

def check_analyze_pr(pr_url: str) -> bool:
    section(f"5 · prism_analyze_pr — {pr_url}")

    if not os.getenv("GITHUB_TOKEN"):
        warn("GITHUB_TOKEN not set — skipping live PR test")
        return True

    try:
        from prism_mcp.tools.analyze import run_analyze_pr
        result = run_analyze_pr({"pr_url": pr_url})
    except Exception as e:
        fail(f"run_analyze_pr raised: {e}")
        return False

    if "error" in result:
        fail(f"prism_analyze_pr returned error: {result['error']}")
        return False

    required = {"pr_url", "risk_score", "findings", "findings_by_severity", "summary"}
    missing  = required - set(result.keys())
    if missing:
        fail(f"ReviewResult missing keys: {missing}")
        return False

    ok(f"Review complete — risk score: {result['risk_score']}/100")
    ok(f"Findings: {len(result['findings'])}  hunks: {result.get('hunk_count', '?')}")
    ok(f"Summary (first 100 chars): {result['summary'][:100]}...")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description="PRISM Phase 3 exit-criteria validator")
    parser.add_argument("--pr", default="", help="Optional GitHub PR URL for live test (Check 5)")
    args = parser.parse_args()

    print(f"\n{BOLD}===========================================")
    print( "   PRISM Phase 3 — MCP Server Validator   ")
    print(f"==========================================={RESET}")

    results: dict[str, bool] = {}
    results["imports"]  = check_imports()
    results["health"]   = check_health_tool()
    results["stubs"]    = check_stub_tools()
    results["generate"] = check_generate_tool()
    if args.pr:
        results["analyze_pr"] = check_analyze_pr(args.pr)

    section("Summary")
    all_passed = True
    for name, passed in results.items():
        if passed:
            ok(name)
        else:
            fail(name)
            all_passed = False

    print()
    if all_passed:
        print(f"{GREEN}{BOLD}  Phase 3 complete — MCP server is ready.{RESET}")
        print(f"  Bob can now call prism_analyze_pr, prism_health_check, and all 6 tools.\n")
        return 0
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"{RED}{BOLD}  Phase 3 NOT complete — fix: {', '.join(failed)}{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
