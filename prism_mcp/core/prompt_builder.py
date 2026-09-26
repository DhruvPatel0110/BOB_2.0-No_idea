"""
prompt_builder.py — Assemble the PRISM review prompt for a single HunkChunk.

Phase 2: no RAG context injected yet — only the system instruction + diff.
Phase 4 will extend build_review_prompt() to accept context_chunks and
inject them between the system block and the diff.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prism_mcp.utils.diff_parser import HunkChunk

# ---------------------------------------------------------------------------
# Token budget (must stay inside Granite 3.x 4k effective window)
# ---------------------------------------------------------------------------

CONTEXT_TOKEN_BUDGET = int(os.getenv("RAG_CONTEXT_TOKEN_BUDGET", "1500"))

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are PRISM (Precise Review & Intelligent Scoring Module), an expert code \
reviewer. Analyse the diff below and produce a JSON array of findings.

Rules:
- Output ONLY a valid JSON array. No prose, no markdown fences, no explanation \
  outside the JSON.
- If there are no issues, output exactly: []
- Every element in the array must follow this schema exactly:
  {
    "severity":    "Blocker" | "Major" | "Minor" | "Nit",
    "category":    "security" | "logic" | "maintainability" | "style" | "tests",
    "line_start":  <integer — line number in the NEW file>,
    "line_end":    <integer — line number in the NEW file>,
    "title":       "<short title, ≤10 words>",
    "explanation": "<why this matters, 1-3 sentences>",
    "suggestion":  "<concrete fix, code snippet or description>",
    "citation":    "<exact source_label from RELEVANT CONTEXT if grounded in context, else null>"
  }
- If a finding relates to or violates any guideline, style doc, past review, or rule \
in the 'RELEVANT CONTEXT' block, set "citation" to that exact source_label \
(e.g. "CONTRIBUTING.md §...", "PR #...", "OWASP ...", "Code smell: ..."). \
Otherwise, set "citation": null.

Severity guide:
  Blocker      — must be fixed before merge (security hole, data loss, crash)
  Major        — serious logic/correctness issue; likely to cause bugs
  Minor        — code quality problem; should be fixed but won't break things
  Nit          — style/formatting/naming; optional to fix
""".strip()

# ---------------------------------------------------------------------------
# Summary prompt (one per PR, not per hunk — used in Phase 2 post-aggregation)
# ---------------------------------------------------------------------------

_SUMMARY_PROMPT_TEMPLATE = """\
You are PRISM, an AI code reviewer. Given the following PR metadata and a \
summary of findings, write:
1. A single paragraph (3-5 sentences) describing what this PR does and its \
   overall quality.
2. A bullet list of the top risks (max 5 bullets, most severe first).

Output plain text — no JSON.

PR title: {title}
PR description: {body}
Files changed: {files}
Findings: {findings_summary}
""".strip()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_review_prompt(
    chunk: "HunkChunk",
    context_chunks: list[dict] | None = None,   # Phase 4 will populate this
) -> str:
    """
    Return the full prompt string to send to Ollama for one diff hunk.

    Structure:
        [SYSTEM INSTRUCTION]
        --- CONTEXT (Phase 4 only) ---
        [retrieved context block]
        --- END CONTEXT ---
        [DIFF]
    """
    parts: list[str] = [_SYSTEM_PROMPT, ""]

    # ── Context block (Phase 4+) ───────────────────────────────────────────
    if context_chunks:
        from prism_mcp.utils.token_counter import count_tokens
        ctx_parts: list[str] = []
        budget = CONTEXT_TOKEN_BUDGET
        for c in context_chunks:
            snippet = f"[{c.get('source_label', 'context')}]\n{c.get('text', '')}"
            toks = count_tokens(snippet)
            if toks > budget:
                break
            ctx_parts.append(snippet)
            budget -= toks
        if ctx_parts:
            parts.append("--- RELEVANT CONTEXT ---")
            parts.extend(ctx_parts)
            parts.append("--- END CONTEXT ---")
            parts.append("")

    # ── Sub-chunk annotation ───────────────────────────────────────────────
    sub_note = ""
    if chunk.sub_chunk_total > 1:
        sub_note = f" [sub-chunk {chunk.sub_chunk_index}/{chunk.sub_chunk_total}]"

    # ── File context (surrounding lines) ──────────────────────────────────
    file_ctx_block = ""
    if chunk.context_lines:
        file_ctx_block = (
            f"\nFull-file context (surrounding lines):\n"
            f"```\n{chunk.context_lines}\n```\n"
        )

    # ── Diff block ─────────────────────────────────────────────────────────
    parts.append(
        f"Review this diff. File: {chunk.file_path}{sub_note}. "
        f"Language: {chunk.language}.\n"
        f"{file_ctx_block}"
        f"Diff:\n```diff\n{chunk.diff_text}\n```"
    )

    return "\n".join(parts)


def build_summary_prompt(
    title: str,
    body: str,
    file_list: list[str],
    findings: list[dict],
) -> str:
    """Return the prompt for generating the PR summary paragraph."""
    from collections import Counter
    sev_counts = Counter(f.get("severity", "?") for f in findings)
    cat_counts = Counter(f.get("category", "?") for f in findings)
    findings_summary = (
        f"Total: {len(findings)}. "
        f"Severity: {dict(sev_counts)}. "
        f"Categories: {dict(cat_counts)}."
    )
    return _SUMMARY_PROMPT_TEMPLATE.format(
        title=title or "(no title)",
        body=(body or "(no description)")[:500],
        files=", ".join(file_list[:20]) or "(none)",
        findings_summary=findings_summary,
    )
