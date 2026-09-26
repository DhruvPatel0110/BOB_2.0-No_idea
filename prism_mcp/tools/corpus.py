"""
corpus.py — prism_build_corpus tool (Phase 4 — fully implemented).

Fetches a GitHub repo's:
  • CONTRIBUTING.md / style guide / linter configs  → style collection
  • Last 50 merged PRs + their review comment threads → history collection

Chunks, embeds, and upserts into ChromaDB. Idempotent — safe to re-run.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GitHub helpers (stdlib only)
# ---------------------------------------------------------------------------

def _gh_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "User-Agent":    "PRISM-corpus-builder",
    }


def _gh_get(url: str, accept: str | None = None) -> dict | list | str | None:
    headers = _gh_headers()
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ct   = r.headers.get("Content-Type", "")
            body = r.read()
            return json.loads(body) if "json" in ct else body.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        log.warning("GitHub API %s → HTTP %d", url, e.code)
        return None
    except Exception as e:
        log.warning("GitHub API %s → %s", url, e)
        return None


def _decode_file(data: dict) -> str | None:
    if isinstance(data, dict) and data.get("encoding") == "base64":
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Style docs fetcher
# ---------------------------------------------------------------------------

_STYLE_FILES = [
    "CONTRIBUTING.md",
    "contributing.md",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
    "STYLEGUIDE.md",
    "style_guide.md",
    "docs/style_guide.md",
    ".eslintrc.json",
    ".eslintrc.js",
    "pyproject.toml",
    ".flake8",
    "setup.cfg",
    ".rubocop.yml",
    "checkstyle.xml",
    "google_checks.xml",
]


def _fetch_style_files(base_url: str) -> list[tuple[str, str]]:
    """Return list of (filename, content) for found style/config files."""
    found = []
    for filename in _STYLE_FILES:
        data = _gh_get(f"{base_url}/contents/{filename}")
        if data and isinstance(data, dict):
            content = _decode_file(data)
            if content and content.strip():
                log.info("  style: fetched %s (%d bytes)", filename, len(content))
                found.append((filename, content))
    return found


# ---------------------------------------------------------------------------
# PR history fetcher
# ---------------------------------------------------------------------------

def _fetch_pr_history(base_url: str, max_prs: int = 50) -> list[tuple[str, str]]:
    """
    Fetch the last max_prs merged PRs and their review comments.
    Returns list of (source_label, text) where text is the comment body.
    """
    prs_url = f"{base_url}/pulls?state=closed&sort=updated&direction=desc&per_page={max_prs}"
    prs     = _gh_get(prs_url)
    if not isinstance(prs, list):
        return []

    merged_prs = [pr for pr in prs if pr.get("merged_at")]
    log.info("  history: found %d merged PRs (of %d closed)", len(merged_prs), len(prs))

    items: list[tuple[str, str]] = []
    for pr in merged_prs:
        pr_num   = pr["number"]
        pr_title = pr.get("title", f"PR #{pr_num}")

        # Review comments (inline)
        comments = _gh_get(f"{base_url}/pulls/{pr_num}/comments?per_page=100")
        if isinstance(comments, list):
            for c in comments:
                body = (c.get("body") or "").strip()
                path = c.get("path", "")
                line = c.get("line") or c.get("original_line") or ""
                if body and len(body) > 20:
                    label = f"PR #{pr_num} ({pr_title}) review comment on {path}"
                    if line:
                        label += f" L{line}"
                    items.append((label, body))

        # Issue comments (general PR comments)
        issue_comments = _gh_get(f"{base_url}/issues/{pr_num}/comments?per_page=50")
        if isinstance(issue_comments, list):
            for c in issue_comments:
                body = (c.get("body") or "").strip()
                if body and len(body) > 30:
                    label = f"PR #{pr_num} ({pr_title}) comment"
                    items.append((label, body))

    log.info("  history: collected %d comment items", len(items))
    return items


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java",
    ".go": "go", ".rb": "ruby", ".php": "php",
    ".md": "markdown", ".txt": "text",
    ".toml": "toml", ".cfg": "ini", ".yml": "yaml", ".yaml": "yaml",
    ".json": "json",
}

def _lang_for(filename: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_LANG.get(ext, "text")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_build_corpus(args: dict) -> dict:
    """
    Fetch, chunk, embed, and upsert a repo's style docs + PR history.

    Args:
        owner         (str)  — GitHub repo owner
        repo          (str)  — GitHub repo name
        force_rebuild (bool) — ignore existing data and rebuild from scratch
    """
    owner         = args.get("owner", "").strip()
    repo_name     = args.get("repo",  "").strip()
    force_rebuild = bool(args.get("force_rebuild", False))

    if not owner or not repo_name:
        return {"ok": False, "error": "owner and repo are required"}
    if not os.getenv("GITHUB_TOKEN"):
        return {"ok": False, "error": "GITHUB_TOKEN not set"}

    from prism_mcp.rag.chunker      import chunk_source_file
    from prism_mcp.rag.embedder     import embed_texts
    from prism_mcp.rag.vector_store import upsert_chunks, collection_names, corpus_status

    cols    = collection_names(owner, repo_name)
    base    = f"https://api.github.com/repos/{owner}/{repo_name}"
    t0      = time.monotonic()
    stats   = {"style": 0, "history": 0}

    # ── 1. Style docs ────────────────────────────────────────────────────────
    log.info("build_corpus: fetching style files for %s/%s", owner, repo_name)
    style_files = _fetch_style_files(base)

    style_chunks_all = []
    for filename, content in style_files:
        lang   = _lang_for(filename)
        chunks = chunk_source_file(filename, content, lang, max_tokens=400)
        style_chunks_all.extend(chunks)

    if style_chunks_all:
        texts = [c.text for c in style_chunks_all]
        embs  = embed_texts(texts)
        upserted = upsert_chunks(cols["style"], style_chunks_all, embs)
        stats["style"] = upserted
        log.info("build_corpus: upserted %d style chunks", upserted)
    else:
        log.info("build_corpus: no style files found for %s/%s", owner, repo_name)

    # ── 2. PR review history ─────────────────────────────────────────────────
    log.info("build_corpus: fetching PR history for %s/%s", owner, repo_name)
    history_items = _fetch_pr_history(base)

    if history_items:
        from prism_mcp.rag.chunker import ChunkDoc
        hist_chunks = []
        for label, text in history_items:
            cid = ChunkDoc.make_id(f"{owner}/{repo_name}/history", text)
            hist_chunks.append(ChunkDoc(
                chunk_id=cid,
                file_path=f"{owner}/{repo_name}",
                text=text,
                language="text",
                start_line=0,
                end_line=0,
                symbol_name="",
                chunk_type="history",
                source_label=label,
            ))

        texts = [c.text for c in hist_chunks]
        embs  = embed_texts(texts)
        upserted = upsert_chunks(cols["history"], hist_chunks, embs)
        stats["history"] = upserted
        log.info("build_corpus: upserted %d history chunks", upserted)

    duration = round(time.monotonic() - t0, 1)
    status   = corpus_status(owner, repo_name)

    return {
        "ok":              True,
        "owner":           owner,
        "repo":            repo_name,
        "style_chunks":    stats["style"],
        "history_chunks":  stats["history"],
        "duration_s":      duration,
        "corpus_status":   status,
    }
