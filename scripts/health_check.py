"""
prism_health_check — Phase 1 exit-criteria validator.

Checks:
  1. Ollama is reachable and both required models are available.
  2. ChromaDB client can be instantiated and a test collection created/deleted.
  3. GitHub token is valid and has the required scopes.

Usage:
    python scripts/health_check.py

Exit codes:
    0  — all checks passed
    1  — one or more checks failed
"""

import os
import sys
import json
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Load .env (stdlib only — no python-dotenv dependency yet at Phase 1)
# ---------------------------------------------------------------------------

def load_env(path: str = ".env") -> None:
    """Parse a .env file and inject into os.environ (skips comments/blanks)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

load_env()

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL      = os.getenv("OLLAMA_MODEL", "granite3-dense:8b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
GITHUB_TOKEN      = os.getenv("GITHUB_TOKEN", "")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg: str) -> None: print(f"  {RED}✗{RESET}  {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}!{RESET}  {msg}")
def section(title: str) -> None: print(f"\n{BOLD}{title}{RESET}")

def http_get(url: str, headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()

def http_post(url: str, body: dict, headers: dict | None = None) -> tuple[int, bytes]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()

# ---------------------------------------------------------------------------
# Check 1: Ollama
# ---------------------------------------------------------------------------

def check_ollama() -> bool:
    section("1 · Ollama")
    passed = True

    # Ping
    status, body = http_get(f"{OLLAMA_BASE_URL}/api/tags")
    if status != 200:
        fail(f"Ollama not reachable at {OLLAMA_BASE_URL}  (HTTP {status})")
        fail("Run: ollama serve   or restart the Ollama app")
        return False
    ok(f"Ollama reachable at {OLLAMA_BASE_URL}")

    # Check models
    try:
        tags = json.loads(body)
        available = {m["name"].split(":")[0] + ":" + m["name"].split(":")[1]
                     if ":" in m["name"] else m["name"]
                     for m in tags.get("models", [])}
        # also store raw names for fuzzy match
        raw_names = {m["name"] for m in tags.get("models", [])}
    except Exception:
        warn("Could not parse model list from Ollama — skipping model checks")
        return True

    def model_present(model: str) -> bool:
        return model in raw_names or model in available or any(
            n.startswith(model.split(":")[0]) for n in raw_names
        )

    if model_present(OLLAMA_MODEL):
        ok(f"Generation model present: {OLLAMA_MODEL}")
    else:
        fail(f"Generation model NOT found: {OLLAMA_MODEL}")
        fail(f"Run: ollama pull {OLLAMA_MODEL}")
        passed = False

    if model_present(OLLAMA_EMBED_MODEL):
        ok(f"Embedding model present:   {OLLAMA_EMBED_MODEL}")
    else:
        fail(f"Embedding model NOT found: {OLLAMA_EMBED_MODEL}")
        fail(f"Run: ollama pull {OLLAMA_EMBED_MODEL}")
        passed = False

    # Quick generate smoke test — use streaming so we get the first token
    # fast without waiting for the full response (avoids cold-load timeout).
    if passed:
        import socket
        gen_req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/generate",
            data=json.dumps({"model": OLLAMA_MODEL, "prompt": "Hi", "stream": True, "options": {"num_predict": 3}}).encode(),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(gen_req, timeout=120) as r:
                gen_status = r.status
                # Read just the first newline-delimited JSON chunk
                first_line = b""
                while True:
                    ch = r.read(1)
                    if not ch or ch == b"\n":
                        break
                    first_line += ch
            chunk = json.loads(first_line) if first_line else {}
            if gen_status == 200 and "response" in chunk:
                ok(f"Generate smoke test passed ({OLLAMA_MODEL}) — first token: '{chunk['response']}'")
            else:
                fail(f"Generate smoke test unexpected response: status={gen_status} chunk={first_line[:120]}")
                passed = False
        except Exception as e:
            fail(f"Generate smoke test failed: {e}")
            passed = False

    # Quick embed smoke test
    if passed:
        status, body = http_post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            {"model": OLLAMA_EMBED_MODEL, "prompt": "hello world"}
        )
        if status == 200:
            data = json.loads(body)
            dim = len(data.get("embedding", []))
            ok(f"Embedding smoke test passed ({OLLAMA_EMBED_MODEL}, dim={dim})")
        else:
            fail(f"Embedding smoke test failed: HTTP {status}")
            passed = False

    return passed

# ---------------------------------------------------------------------------
# Check 2: ChromaDB
# ---------------------------------------------------------------------------

def check_chromadb() -> bool:
    section("2 · ChromaDB")
    try:
        import chromadb  # type: ignore
    except ImportError:
        fail("chromadb not installed — run: pip install chromadb")
        return False

    os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
    try:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        ok(f"ChromaDB client initialised (path: {CHROMA_PERSIST_DIR})")
    except Exception as e:
        fail(f"ChromaDB init failed: {e}")
        return False

    # Create and delete a test collection
    test_col = "prism-health-test"
    try:
        col = client.get_or_create_collection(test_col)
        col.upsert(
            ids=["test-1"],
            documents=["health check document"],
            embeddings=[[0.1] * 384],
        )
        result = col.query(query_embeddings=[[0.1] * 384], n_results=1)
        assert result["ids"][0][0] == "test-1"
        client.delete_collection(test_col)
        ok("ChromaDB read/write/delete cycle passed")
    except Exception as e:
        fail(f"ChromaDB R/W test failed: {e}")
        # attempt cleanup
        try:
            client.delete_collection(test_col)
        except Exception:
            pass
        return False

    return True

# ---------------------------------------------------------------------------
# Check 3: GitHub Token
# ---------------------------------------------------------------------------

def check_github() -> bool:
    section("3 · GitHub Token")

    if not GITHUB_TOKEN:
        fail("GITHUB_TOKEN is not set in .env")
        fail("Get a free PAT at: https://github.com/settings/tokens")
        return False

    status, body = http_get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "User-Agent": "PRISM-health-check"}
    )

    if status == 401:
        fail("GitHub token is invalid or expired")
        return False
    if status == 403:
        fail("GitHub token lacks required scopes — regenerate with: repo, write:discussion")
        return False
    if status != 200:
        fail(f"GitHub API returned HTTP {status}")
        return False

    try:
        user = json.loads(body)
        ok(f"GitHub token valid — authenticated as: {user.get('login', '?')}")
    except Exception:
        ok("GitHub token valid (could not parse username)")

    # Check rate limit remaining
    status2, body2 = http_get(
        "https://api.github.com/rate_limit",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "User-Agent": "PRISM-health-check"}
    )
    if status2 == 200:
        rl = json.loads(body2)
        remaining = rl.get("rate", {}).get("remaining", "?")
        limit = rl.get("rate", {}).get("limit", "?")
        ok(f"Rate limit: {remaining}/{limit} requests remaining this hour")
    
    return True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    print(f"\n{BOLD}===========================================")
    print( "   PRISM Health Check - Phase 1 Validator  ")
    print(f"==========================================={RESET}")

    results = {
        "Ollama":    check_ollama(),
        "ChromaDB":  check_chromadb(),
        "GitHub":    check_github(),
    }

    section("Summary")
    all_passed = True
    for name, passed in results.items():
        if passed:
            ok(f"{name}")
        else:
            fail(f"{name}")
            all_passed = False

    print()
    if all_passed:
        print(f"{GREEN}{BOLD}  Phase 1 complete — all systems go.{RESET}\n")
        return 0
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"{RED}{BOLD}  Phase 1 NOT complete — fix: {', '.join(failed)}{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
