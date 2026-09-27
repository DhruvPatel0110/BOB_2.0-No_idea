"""
post.py — prism_post_review tool (Phase 8 — GitHub PR Review Comment Posting).

Implements:
1. Diff position & line mapper: Maps each finding to the correct diff line and position.
2. Comment formatter: Renders bold severity, title, explanation, suggestion codeblock, and citation label.
3. Review body formatter: Executive summary and severity badge tally.
4. Demo repo safety gate: Blocks live posting (dry_run: false) to non-demo repos.
5. Batch PR review creation: Atomically posts all inline comments via GitHub REST API.
6. Incremental learning hook: Appends posted review comments into ChromaDB repo history collection.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from prism_mcp.utils.diff_mapper import build_diff_index, map_finding_to_diff

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Language lookup for code blocks
# ---------------------------------------------------------------------------

_EXT_TO_LANG: Dict[str, str] = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java",
    ".go": "go", ".rb": "ruby", ".php": "php", ".c": "c",
    ".cpp": "cpp", ".cs": "csharp", ".rs": "rust", ".kt": "kotlin",
    ".sql": "sql", ".sh": "bash", ".bash": "bash", ".yaml": "yaml",
    ".yml": "yaml", ".json": "json", ".toml": "toml", ".html": "html",
    ".css": "css", ".md": "markdown",
}


# ---------------------------------------------------------------------------
# GitHub REST API Helpers
# ---------------------------------------------------------------------------

def _get_gh_token() -> str:
    return os.getenv("GITHUB_TOKEN", "").strip()


def _gh_headers(token: str, accept: str = "application/vnd.github+json") -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "User-Agent": "PRISM-mcp-server",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _parse_pr_target(pr_url: str, args: dict) -> Tuple[str, str, int]:
    """Extract owner, repo, and pull_number from pr_url or explicit args."""
    if not pr_url:
        owner = str(args.get("owner", "")).strip()
        repo = str(args.get("repo", "")).strip()
        num = args.get("pr_number") or args.get("pull_number")
        if owner and repo and num:
            return owner, repo, int(num)
        raise ValueError("Target PR not specified. Provide 'pr_url' or ('owner', 'repo', 'pr_number').")

    parts = pr_url.rstrip("/").split("/")
    try:
        idx = parts.index("pull")
        owner = parts[idx - 2]
        repo = parts[idx - 1]
        number = int(parts[idx + 1])
        return owner, repo, number
    except (ValueError, IndexError):
        raise ValueError(f"Cannot parse PR URL: '{pr_url}'. Expected format: https://github.com/owner/repo/pull/N")


def _fetch_pr_info(owner: str, repo: str, pull_number: int, token: str) -> Tuple[dict, str]:
    """
    Fetches PR metadata (including latest head.sha) and raw unified diff.
    """
    base_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"

    # 1. Fetch PR JSON metadata
    req_meta = urllib.request.Request(base_url, headers=_gh_headers(token))
    with urllib.request.urlopen(req_meta, timeout=30) as resp:
        pr_meta = json.loads(resp.read().decode("utf-8"))

    # 2. Fetch PR Diff
    req_diff = urllib.request.Request(
        base_url,
        headers=_gh_headers(token, accept="application/vnd.github.v3.diff"),
    )
    with urllib.request.urlopen(req_diff, timeout=30) as resp:
        diff_text = resp.read().decode("utf-8", errors="replace")

    return pr_meta, diff_text


# ---------------------------------------------------------------------------
# Comment & Body Formatters
# ---------------------------------------------------------------------------

def format_review_comment(finding: dict) -> str:
    """
    Renders finding into GitHub Markdown review comment:
    **[Severity] Title**

    Explanation

    **Suggested fix:**
    ```lang
    suggestion
    ```

    📎 *citation | PRISM v0.1*
    """
    severity = str(finding.get("severity") or "Minor").strip().capitalize()
    title = str(finding.get("title") or "Code Quality Observation").strip()
    explanation = str(finding.get("explanation") or "").strip()
    suggestion = str(finding.get("suggestion") or "").strip()
    citation = str(finding.get("citation") or "").strip()
    file_path = finding.get("file") or finding.get("file_path") or ""

    ext = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    lang = _EXT_TO_LANG.get(ext, "")

    parts = [f"**[{severity}] {title}**\n"]
    if explanation:
        parts.append(f"{explanation}\n")

    if suggestion:
        sug_clean = suggestion.strip()
        if not sug_clean.startswith("```"):
            parts.append(f"**Suggested fix:**\n```{lang}\n{sug_clean}\n```\n")
        else:
            parts.append(f"**Suggested fix:**\n{sug_clean}\n")

    if citation:
        parts.append(f"📎 *{citation} | PRISM v0.1*")
    else:
        parts.append("📎 *PRISM v0.1*")

    return "\n".join(parts)


def format_review_body(
    summary: str,
    findings: List[dict],
    general_findings: Optional[List[dict]] = None,
) -> str:
    """Renders the executive summary markdown for the review."""
    parts = [
        "## 🔬 PRISM Automated Code Review",
        "",
    ]
    if summary and summary.strip():
        parts.append(summary.strip())
        parts.append("")

    # Severity tally
    counts: Dict[str, int] = {}
    for f in findings:
        sev = str(f.get("severity") or "Minor").capitalize()
        counts[sev] = counts.get(sev, 0) + 1

    badges = []
    if "Blocker" in counts:
        badges.append(f"🔴 **Blocker**: {counts['Blocker']}")
    if "Major" in counts:
        badges.append(f"🟠 **Major**: {counts['Major']}")
    if "Minor" in counts:
        badges.append(f"🟡 **Minor**: {counts['Minor']}")
    if "Nit" in counts:
        badges.append(f"⚪ **Nit**: {counts['Nit']}")

    if badges:
        parts.append(" | ".join(badges))
        parts.append("")

    if general_findings:
        parts.append("### 📋 General Findings")
        for gf in general_findings:
            f_sev = gf.get("severity", "Minor")
            f_title = gf.get("title", "")
            f_file = gf.get("file", "")
            f_expl = gf.get("explanation", "")
            parts.append(f"- **[{f_sev}] {f_title}** (`{f_file}`): {f_expl}")
        parts.append("")

    parts.append("---")
    parts.append("*Automated review posted by **PRISM** — Intelligent Code Review Coach (IBM Bob 2.0 Hackathon)*")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Incremental Learning Hook
# ---------------------------------------------------------------------------

def _run_incremental_learning(
    owner: str,
    repo: str,
    pull_number: int,
    findings: List[dict],
) -> None:
    """
    Background hook: embeds posted comments into ChromaDB repo history collection.
    """
    try:
        from prism_mcp.rag.chunker import ChunkDoc
        from prism_mcp.rag.embedder import embed_texts
        from prism_mcp.rag.vector_store import collection_names, upsert_chunks

        chunks = []
        for i, f in enumerate(findings):
            f_file = f.get("file") or f.get("file_path") or "general"
            f_title = f.get("title") or "Finding"
            f_sev = f.get("severity") or "Minor"
            f_expl = f.get("explanation") or ""
            f_sug = f.get("suggestion") or ""

            text = f"PR #{pull_number} review finding [{f_sev}] on {f_file}: {f_title}\n{f_expl}"
            if f_sug:
                text += f"\nSuggested fix:\n{f_sug}"

            chunk_id = ChunkDoc.make_id(f"pr_{pull_number}_{f_file}_{i}", text)
            chunk = ChunkDoc(
                chunk_id=chunk_id,
                file_path=f_file,
                text=text,
                language="markdown",
                start_line=int(f.get("line_start") or 0),
                end_line=int(f.get("line_end") or 0),
                symbol_name="",
                chunk_type="review_comment",
                source_label=f"PR #{pull_number} review comment on {f_file}",
            )
            chunks.append(chunk)

        if chunks:
            texts = [c.text for c in chunks]
            embeddings = embed_texts(texts)
            col_name = collection_names(owner, repo)["history"]
            upserted = upsert_chunks(col_name, chunks, embeddings)
            log.info("Incremental learning: indexed %d review comments into %s", upserted, col_name)
    except Exception as e:
        log.warning("Incremental learning hook failed (non-critical): %s", e)


def _schedule_incremental_learning(
    owner: str,
    repo: str,
    pull_number: int,
    findings: List[dict],
) -> None:
    t = threading.Thread(
        target=_run_incremental_learning,
        args=(owner, repo, pull_number, findings),
        daemon=True,
    )
    t.start()


# ---------------------------------------------------------------------------
# Public Entry Point: run_post_review
# ---------------------------------------------------------------------------

def run_post_review(args: dict) -> dict:
    """
    Submits PRISM findings as a formal GitHub PR review.

    Expected args:
        pr_url   (str)          — GitHub PR URL (or owner, repo, pr_number)
        findings (list[dict])   — Findings array from prism_analyze_pr
        summary  (str)          — Review body / PR summary text
        dry_run  (bool)         — If True (default), validate & format without posting

    Returns a dict with review status, dry_run flag, and comment statistics.
    """
    pr_url = str(args.get("pr_url", "")).strip()
    findings = args.get("findings", [])
    summary = str(args.get("summary", "")).strip()
    dry_run = bool(args.get("dry_run", True))

    token = _get_gh_token()
    if not token:
        return {
            "ok": False,
            "error": "GITHUB_TOKEN is not configured in .env",
            "dry_run": dry_run,
            "pr_url": pr_url,
        }

    # 1. Parse target PR
    try:
        owner, repo, pull_number = _parse_pr_target(pr_url, args)
    except ValueError as e:
        return {"ok": False, "error": str(e), "dry_run": dry_run, "pr_url": pr_url}

    full_pr_url = pr_url or f"https://github.com/{owner}/{repo}/pull/{pull_number}"

    # 2. Demo Repo Safety Gate
    demo_owner = os.getenv("DEMO_REPO_OWNER", "").strip()
    demo_repo = os.getenv("DEMO_REPO_NAME", "").strip()

    if not dry_run and demo_owner and demo_repo:
        if owner.lower() != demo_owner.lower() or repo.lower() != demo_repo.lower():
            err_msg = (
                f"Safety gate blocked live review: target repository '{owner}/{repo}' does not match "
                f"designated demo repository '{demo_owner}/{demo_repo}'. "
                "Set dry_run: true to simulate review comments without modifying live GitHub repositories."
            )
            log.warning(err_msg)
            return {
                "ok": False,
                "error": err_msg,
                "dry_run": False,
                "pr_url": full_pr_url,
                "status": "safety_gate_blocked",
            }

    # 3. Fetch PR info and unified diff
    try:
        pr_meta, diff_text = _fetch_pr_info(owner, repo, pull_number, token)
    except urllib.error.HTTPError as e:
        status_msg = f"GitHub API returned HTTP {e.code}"
        if e.code == 404:
            status_msg += f" — PR #{pull_number} or repo {owner}/{repo} not found (verify token permissions)."
        elif e.code == 401:
            status_msg += " — GITHUB_TOKEN is invalid or expired."
        return {"ok": False, "error": status_msg, "dry_run": dry_run, "pr_url": full_pr_url}
    except Exception as e:
        return {"ok": False, "error": f"Failed to fetch PR #{pull_number}: {e}", "dry_run": dry_run, "pr_url": full_pr_url}

    head_sha = pr_meta.get("head", {}).get("sha", "")
    if not head_sha:
        return {
            "ok": False,
            "error": "Could not determine head commit SHA for PR",
            "dry_run": dry_run,
            "pr_url": full_pr_url,
        }

    # 4. Build diff index and map findings
    diff_index = build_diff_index(diff_text)
    inline_comments: List[dict] = []
    general_findings: List[dict] = []

    for f in findings:
        formatted_body = format_review_comment(f)
        mapped = map_finding_to_diff(f, diff_index)

        if mapped["in_diff"]:
            inline_comments.append({
                "path": mapped["path"],
                "line": mapped["line"],
                "side": "RIGHT",
                "body": formatted_body,
                "_position": mapped["position"],
                "_snapped": mapped["snapped"],
            })
        else:
            general_findings.append(f)

    review_body = format_review_body(summary, findings, general_findings)

    # 5. Handle Dry Run
    if dry_run:
        return {
            "ok": True,
            "status": "simulated",
            "dry_run": True,
            "pr_url": full_pr_url,
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "commit_id": head_sha,
            "findings_count": len(findings),
            "inline_comments_count": len(inline_comments),
            "general_findings_count": len(general_findings),
            "review_body": review_body,
            "formatted_comments": [
                {
                    "path": c["path"],
                    "line": c["line"],
                    "side": c["side"],
                    "diff_position": c.get("_position"),
                    "snapped": c.get("_snapped"),
                    "preview": c["body"][:160] + ("..." if len(c["body"]) > 160 else ""),
                }
                for c in inline_comments
            ],
            "message": (
                f"Dry run simulation successful: {len(inline_comments)} inline comment(s) "
                f"mapped to diff positions. Ready for posting on commit {head_sha[:7]}."
            ),
        }

    # 6. Live Post to GitHub Reviews API
    post_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
    review_payload: Dict[str, Any] = {
        "commit_id": head_sha,
        "body": review_body,
        "event": "COMMENT",
    }
    if inline_comments:
        review_payload["comments"] = [
            {
                "path": c["path"],
                "line": c["line"],
                "side": "RIGHT",
                "body": c["body"],
            }
            for c in inline_comments
        ]

    payload_bytes = json.dumps(review_payload).encode("utf-8")
    req_post = urllib.request.Request(
        post_url,
        data=payload_bytes,
        headers={
            **_gh_headers(token),
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req_post, timeout=30) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            review_id = resp_data.get("id")
            html_url = resp_data.get("html_url")

            # 7. Incremental Learning hook
            _schedule_incremental_learning(owner, repo, pull_number, findings)

            return {
                "ok": True,
                "status": "posted",
                "dry_run": False,
                "pr_url": full_pr_url,
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "review_id": review_id,
                "html_url": html_url,
                "findings_count": len(findings),
                "inline_comments_count": len(inline_comments),
                "message": f"Successfully posted formal PR review to GitHub: {html_url or f'PR #{pull_number}'}",
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        log.error("GitHub POST review failed with HTTP %d: %s", e.code, err_body)
        try:
            err_json = json.loads(err_body)
            detail = err_json.get("message", err_body)
            if "errors" in err_json:
                detail += f" ({err_json['errors']})"
        except Exception:
            detail = err_body
        return {
            "ok": False,
            "status": "error",
            "dry_run": False,
            "pr_url": full_pr_url,
            "error": f"GitHub review post failed (HTTP {e.code}): {detail}",
        }
    except Exception as e:
        log.exception("Unexpected error while posting PR review")
        return {
            "ok": False,
            "status": "error",
            "dry_run": False,
            "pr_url": full_pr_url,
            "error": f"Failed to post PR review: {e}",
        }
