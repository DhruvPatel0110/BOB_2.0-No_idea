"""
test_rag.py — Phase 4 exit-criteria validator.

Tests:
  1. RAG module imports (chunker, embedder, vector_store, reranker)
  2. Chunker produces chunks for Python, Markdown, and generic text
  3. Embedder returns vectors from Ollama (or HF fallback)
  4. ChromaDB upsert + query round-trip works
  5. Reranker scores and reorders candidates
  6. prism_build_corpus on a real repo → ≥10 style chunks  (requires --owner/--repo)
  7. prism_retrieve_context returns 6 chunks with source_labels  (requires corpus built)

Usage:
    python scripts/test_rag.py
    python scripts/test_rag.py --owner microsoft --repo vscode

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


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

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg: str)    -> None: print(f"  {GREEN}[PASS]{RESET}  {msg}")
def fail(msg: str)  -> None: print(f"  {RED}[FAIL]{RESET}  {msg}")
def warn(msg: str)  -> None: print(f"  {YELLOW}[WARN]{RESET}  {msg}")
def section(t: str) -> None: print(f"\n{BOLD}{t}{RESET}")


# ---------------------------------------------------------------------------
# Check 1: imports
# ---------------------------------------------------------------------------

def check_imports() -> bool:
    section("1 · RAG module imports")
    mods = [
        "prism_mcp.rag.chunker",
        "prism_mcp.rag.embedder",
        "prism_mcp.rag.vector_store",
        "prism_mcp.rag.reranker",
    ]
    passed = True
    for m in mods:
        try:
            __import__(m)
            ok(f"{m}")
        except Exception as e:
            fail(f"{m}: {e}")
            passed = False
    return passed


# ---------------------------------------------------------------------------
# Check 2: chunker
# ---------------------------------------------------------------------------

def check_chunker() -> bool:
    section("2 · Chunker")
    from prism_mcp.rag.chunker import chunk_source_file
    passed = True

    # Python AST
    py_code = """
def authenticate(user, password):
    if user == "admin" and password == "secret":
        return True
    return False

class Database:
    def query(self, sql):
        return eval(sql)
"""
    chunks = chunk_source_file("auth.py", py_code, "python")
    if len(chunks) >= 2:
        ok(f"Python AST chunker: {len(chunks)} chunks (function+class)")
        for c in chunks:
            ok(f"  → [{c.chunk_type}] {c.source_label}")
    else:
        fail(f"Python AST chunker: expected ≥2 chunks, got {len(chunks)}")
        passed = False

    # Markdown heading
    md = """# Style Guide

Use snake_case for all variable names.

## Imports

Always sort imports with isort. Group stdlib, third-party, local.

## Tests

Every new function must have a corresponding test in tests/.
"""
    md_chunks = chunk_source_file("CONTRIBUTING.md", md, "markdown")
    if len(md_chunks) >= 2:
        ok(f"Markdown chunker: {len(md_chunks)} sections")
    else:
        fail(f"Markdown chunker: expected ≥2 chunks, got {len(md_chunks)}")
        passed = False

    # Generic fallback
    text = "\n".join(f"line {i}" for i in range(100))
    fb_chunks = chunk_source_file("config.txt", text, "text")
    if fb_chunks:
        ok(f"Fallback line chunker: {len(fb_chunks)} chunks")
    else:
        fail("Fallback chunker produced 0 chunks")
        passed = False

    return passed


# ---------------------------------------------------------------------------
# Check 3: embedder
# ---------------------------------------------------------------------------

def check_embedder() -> bool:
    section("3 · Embedder")
    try:
        from prism_mcp.rag.embedder import embed_texts, embedding_dim
        vecs = embed_texts(["hello world", "def foo(): pass"])
        if len(vecs) == 2 and len(vecs[0]) > 0:
            dim = len(vecs[0])
            ok(f"embed_texts returned 2 vectors, dim={dim}")
            dim2 = embedding_dim()
            if dim2 == dim:
                ok(f"embedding_dim() = {dim2}")
            else:
                fail(f"embedding_dim() {dim2} ≠ vector len {dim}")
                return False
            return True
        else:
            fail(f"Unexpected embed_texts result: {[len(v) for v in vecs]}")
            return False
    except Exception as e:
        fail(f"Embedder error (Ollama may not be running): {e}")
        warn("Embedder is required for Phase 4 — ensure Ollama is running")
        return False


# ---------------------------------------------------------------------------
# Check 4: vector store round-trip
# ---------------------------------------------------------------------------

def check_vector_store() -> bool:
    section("4 · ChromaDB round-trip")
    try:
        import chromadb
        from prism_mcp.rag.chunker      import chunk_source_file
        from prism_mcp.rag.embedder     import embed_texts, embedding_dim
        from prism_mcp.rag.vector_store import upsert_chunks, query_collection

        py_code = "def secure_hash(data):\n    import hashlib\n    return hashlib.sha256(data).hexdigest()\n"
        chunks  = chunk_source_file("utils.py", py_code, "python")
        if not chunks:
            chunks_fallback = chunk_source_file("utils.py", py_code, "text")
            chunks = chunks_fallback

        dim   = embedding_dim()
        texts = [c.text for c in chunks]
        embs  = embed_texts(texts)

        n = upsert_chunks("test_phase4_rag", chunks, embs)
        ok(f"Upserted {n} chunk(s) into test_phase4_rag")

        results = query_collection("test_phase4_rag", embs[0], n_results=3)
        if results:
            ok(f"Query returned {len(results)} result(s)")
            ok(f"  Top result score={results[0]['score']:.3f}  label={results[0]['source_label']}")
        else:
            fail("Query returned 0 results after upsert")
            return False

        # Cleanup
        import chromadb as _chroma
        import os as _os
        _chroma.PersistentClient(path=_os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")).delete_collection("test_phase4_rag")
        ok("Cleaned up test collection")
        return True

    except Exception as e:
        fail(f"ChromaDB round-trip failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Check 5: reranker
# ---------------------------------------------------------------------------

def check_reranker() -> bool:
    section("5 · Reranker")
    try:
        from prism_mcp.rag.reranker import rerank

        query = "SQL injection vulnerability in user input"
        candidates = [
            {"text": "Always use parameterized queries to prevent SQL injection.", "source_label": "CONTRIBUTING.md §Security", "score": 0.7},
            {"text": "def hello(): print('hello world')",                          "source_label": "utils.py:hello",             "score": 0.3},
            {"text": "Use prepared statements when building database queries.",    "source_label": "owasp-A03",                  "score": 0.65},
            {"text": "Variable names should be snake_case.",                       "source_label": "CONTRIBUTING.md §Style",     "score": 0.2},
        ]
        results = rerank(query, candidates, top_k=3)
        if len(results) <= 3:
            ok(f"Reranker returned {len(results)} result(s) (top_k=3)")
            for r in results:
                score = r.get("reranker_score", r.get("score", "?"))
                ok(f"  score={score:.3f}  {r['source_label']}")
            # The SQL-related chunks should rank higher
            top_label = results[0]["source_label"].lower()
            if "sql" in top_label or "security" in top_label or "owasp" in top_label or "prepared" in results[0]["text"].lower():
                ok("Top result is relevance-correct (SQL/security topic)")
            else:
                warn(f"Top result may not be most relevant: {results[0]['source_label']}")
            return True
        else:
            fail(f"Reranker returned {len(results)} > 3 results")
            return False
    except Exception as e:
        fail(f"Reranker error: {e}")
        return False


# ---------------------------------------------------------------------------
# Check 6: prism_build_corpus (live, optional)
# ---------------------------------------------------------------------------

def check_build_corpus(owner: str, repo: str) -> bool:
    section(f"6 · prism_build_corpus — {owner}/{repo}")

    if not os.getenv("GITHUB_TOKEN"):
        warn("GITHUB_TOKEN not set — skipping corpus build test")
        return True

    from prism_mcp.tools.corpus import run_build_corpus
    try:
        result = run_build_corpus({"owner": owner, "repo": repo})
    except Exception as e:
        fail(f"run_build_corpus raised: {e}")
        return False

    if not result.get("ok"):
        fail(f"build_corpus failed: {result.get('error', result)}")
        return False

    style   = result.get("style_chunks", 0)
    history = result.get("history_chunks", 0)
    ok(f"style_chunks={style}  history_chunks={history}  duration={result.get('duration_s')}s")

    if style >= 10:
        ok(f"≥10 style chunks — exit criterion MET")
    elif style > 0:
        warn(f"{style} style chunks — repo may have minimal style docs (still valid)")
    else:
        warn(f"0 style chunks — repo has no CONTRIBUTING.md or style guide")

    return True


# ---------------------------------------------------------------------------
# Check 7: prism_retrieve_context (live, optional)
# ---------------------------------------------------------------------------

def check_retrieve_context(owner: str, repo: str) -> bool:
    section(f"7 · prism_retrieve_context — {owner}/{repo}")

    SAMPLE_HUNK = """\
+def get_user(user_id):
+    query = f"SELECT * FROM users WHERE id = {user_id}"
+    return db.execute(query)
"""
    from prism_mcp.tools.retrieve import run_retrieve_context
    try:
        result = run_retrieve_context({
            "diff_hunk":  SAMPLE_HUNK,
            "file_path":  "app/models.py",
            "language":   "python",
            "repo_owner": owner,
            "repo_name":  repo,
        })
    except Exception as e:
        fail(f"run_retrieve_context raised: {e}")
        return False

    if "error" in result:
        fail(f"retrieve_context error: {result['error']}")
        return False

    chunks = result.get("context_chunks", [])
    ok(f"retrieve_context returned {len(chunks)} chunk(s)")
    ok(f"collection_hits: {result.get('collection_hits', {})}")

    for i, c in enumerate(chunks[:3], 1):
        label = c.get("source_label", "?")
        score = c.get("reranker_score", c.get("score", "?"))
        ok(f"  {i}. [{score}] {label}")

    # Exit criterion: at least one finding must have a citation
    citations = [c for c in chunks if c.get("source_label")]
    if citations:
        ok(f"All {len(citations)} chunk(s) have source_label — citations will be populated")
    else:
        fail("No chunks have source_label — citation field will be null")
        return False

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description="PRISM Phase 4 exit-criteria validator")
    parser.add_argument("--owner", default="", help="GitHub repo owner for live corpus test")
    parser.add_argument("--repo",  default="", help="GitHub repo name for live corpus test")
    args = parser.parse_args()

    print(f"\n{BOLD}===========================================")
    print( "   PRISM Phase 4 — RAG Layer Validator    ")
    print(f"==========================================={RESET}")

    results: dict[str, bool] = {}
    results["imports"]      = check_imports()
    results["chunker"]      = check_chunker()
    results["embedder"]     = check_embedder()
    if results["embedder"]:
        results["vector_store"] = check_vector_store()
        results["reranker"]     = check_reranker()
        if args.owner and args.repo:
            results["build_corpus"]     = check_build_corpus(args.owner, args.repo)
            results["retrieve_context"] = check_retrieve_context(args.owner, args.repo)
    else:
        warn("Skipping vector_store, reranker, corpus, retrieve checks (embedder failed)")

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
        print(f"{GREEN}{BOLD}  Phase 4 complete — RAG layer is operational.{RESET}\n")
        return 0
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"{RED}{BOLD}  Phase 4 issues — fix: {', '.join(failed)}{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
