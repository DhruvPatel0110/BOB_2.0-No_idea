"""
analyze.py — prism_analyze_pr tool.

Fetches a GitHub PR diff + file contents and runs the full Phase 2 pipeline.
This is the primary tool Bob calls to review a PR.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
import urllib.error
import logging

log = logging.getLogger(__name__)

GITHUB_TOKEN  = ""   # re-read at call time from env


# ---------------------------------------------------------------------------
# GitHub helpers (stdlib only)
# ---------------------------------------------------------------------------

def _gh_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "User-Agent":    "PRISM-mcp-server",
    }


def _gh_get(url: str) -> dict | list | str:
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        ct   = r.headers.get("Content-Type", "")
        body = r.read()
        return json.loads(body) if "json" in ct else body.decode("utf-8", errors="replace")


def _gh_diff(url: str) -> str:
    headers = {**_gh_headers(), "Accept": "application/vnd.github.v3.diff"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_pr_url(url: str) -> tuple[str, str, int]:
    parts = url.rstrip("/").split("/")
    try:
        idx    = parts.index("pull")
        owner  = parts[idx - 2]
        repo   = parts[idx - 1]
        number = int(parts[idx + 1])
        return owner, repo, number
    except (ValueError, IndexError):
        raise ValueError(f"Cannot parse PR URL: {url!r}. Expected https://github.com/owner/repo/pull/N")


def _fetch_pr(owner: str, repo: str, number: int) -> tuple[dict, str, dict[str, str]]:
    base = f"https://api.github.com/repos/{owner}/{repo}"

    pr_raw = _gh_get(f"{base}/pulls/{number}")
    assert isinstance(pr_raw, dict)

    pr_meta = {
        "title": pr_raw.get("title", ""),
        "body":  pr_raw.get("body", "") or "",
        "url":   pr_raw.get("html_url", ""),
        "files": [],
    }

    diff_text  = _gh_diff(f"{base}/pulls/{number}")
    files_raw  = _gh_get(f"{base}/pulls/{number}/files")
    assert isinstance(files_raw, list)

    head_sha      = pr_raw.get("head", {}).get("sha", "")
    changed_files = [f["filename"] for f in files_raw]
    pr_meta["files"] = changed_files

    file_contents: dict[str, str] = {}
    for filename in changed_files[:20]:
        try:
            data = _gh_get(f"{base}/contents/{filename}?ref={head_sha}")
            if isinstance(data, dict) and data.get("encoding") == "base64":
                file_contents[filename] = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception as e:
            log.debug("Could not fetch %s: %s", filename, e)

    return pr_meta, diff_text, file_contents


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_analyze_pr(args: dict) -> dict:
    """
    Called by the MCP server for the prism_analyze_pr tool.

    Args (from MCP call):
        pr_url        (str)  — GitHub PR URL
        post_comments (bool) — reserved for Phase 8; ignored here
        language_hint (str)  — optional language override

    Returns the ReviewResult as a dict, or {"error": "..."} on failure.
    """
    pr_url        = args.get("pr_url", "").strip()
    language_hint = args.get("language_hint") or None

    if not pr_url:
        return {"error": "pr_url is required"}

    if not os.getenv("GITHUB_TOKEN"):
        return {"error": "GITHUB_TOKEN is not set — add it to .env"}

    # ── Fetch PR from GitHub ──────────────────────────────────────────────
    try:
        owner, repo, number = _parse_pr_url(pr_url)
    except ValueError as e:
        return {"error": str(e)}

    try:
        pr_meta, diff_text, file_contents = _fetch_pr(owner, repo, number)
    except urllib.error.HTTPError as e:
        msg = f"GitHub API HTTP {e.code}"
        if e.code == 401:
            msg += " — token invalid or expired"
        elif e.code == 404:
            msg += " — PR not found or repo is private (check token has 'repo' scope)"
        return {"error": msg}
    except Exception as e:
        return {"error": f"Failed to fetch PR: {e}"}

    if not diff_text.strip():
        return {"error": "PR diff is empty — nothing to review"}

    # ── Run pipeline ──────────────────────────────────────────────────────
    try:
        from prism_mcp.core.pipeline import review_pr
        from prism_mcp.tools.retrieve import run_retrieve_context

        def _context_chunks_fn(chunk):
            """RAG hook: retrieve context for a single HunkChunk."""
            result = run_retrieve_context({
                "diff_hunk":  chunk.diff_text,
                "file_path":  chunk.file_path,
                "language":   chunk.language,
                "repo_owner": owner,
                "repo_name":  repo,
            })
            return result.get("context_chunks") or []

        result = review_pr(
            diff=diff_text,
            file_contents=file_contents,
            pr_meta=pr_meta,
            language_hint=language_hint,
            context_chunks_fn=_context_chunks_fn,
        )
        return result.to_dict()
    except Exception as e:
        log.exception("Pipeline error for %s", pr_url)
        return {"error": f"Pipeline failed: {e}"}
