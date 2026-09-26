"""
generate.py — prism_generate_review tool.

Thin wrapper around the Phase 2 Ollama caller.
Takes a raw diff hunk + optional RAG context chunks (ignored in Phase 3)
and returns a findings JSON array.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def run_generate_review(args: dict) -> dict:
    """
    Called by the MCP server for the prism_generate_review tool.

    Args:
        diff_hunk      (str)   — raw unified diff hunk text
        file_path      (str)   — file path the hunk belongs to
        language       (str)   — programming language (optional)
        context_chunks (list)  — RAG chunks from prism_retrieve_context
                                 (passed through to prompt builder; empty in Phase 3)

    Returns:
        {
            "findings":    [...],   # list of finding dicts
            "raw_output":  "...",   # raw model text (for debugging)
            "hunk_tokens": int,
        }
    """
    diff_hunk      = args.get("diff_hunk", "")
    file_path      = args.get("file_path", "unknown")
    language       = args.get("language") or None
    context_chunks = args.get("context_chunks") or []

    if not diff_hunk.strip():
        return {"error": "diff_hunk is required and must not be empty"}

    try:
        from prism_mcp.utils.diff_parser   import HunkChunk, _detect_language
        from prism_mcp.utils.token_counter  import count_tokens
        from prism_mcp.core.prompt_builder  import build_review_prompt
        from prism_mcp.core.ollama_client   import generate_review
        from prism_mcp.core.findings        import parse_findings, findings_to_dicts

        lang = language or _detect_language(file_path)

        # Build a minimal HunkChunk from the raw hunk text
        chunk = HunkChunk(
            file_path=file_path,
            language=lang,
            hunk_header="",
            old_start=0,
            new_start=0,
            diff_lines=diff_hunk.splitlines(keepends=True),
            context_lines="",
            change_type="modified",
        )

        prompt = build_review_prompt(
            chunk,
            context_chunks=context_chunks if context_chunks else None,
        )
        raw_findings, raw_text = generate_review(prompt)
        findings = parse_findings(raw_findings, file_path)

        return {
            "findings":    findings_to_dicts(findings),
            "raw_output":  raw_text,
            "hunk_tokens": count_tokens(diff_hunk),
        }

    except Exception as e:
        log.exception("prism_generate_review failed")
        return {"error": f"Review generation failed: {e}"}
