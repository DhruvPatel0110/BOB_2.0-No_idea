"""
token_counter.py — tiktoken-based token budget utilities.

Used to:
  - Count tokens in any string (for prompt budget management).
  - Split oversized HunkChunks into overlapping sub-chunks so each
    fits within the LLM's context window.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prism_mcp.utils.diff_parser import HunkChunk

# ---------------------------------------------------------------------------
# tiktoken setup — fall back to a character estimate if not installed
# ---------------------------------------------------------------------------

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")  # same family as Granite/LLaMA tokenisers

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text))

except ImportError:  # pragma: no cover
    def count_tokens(text: str) -> int:  # type: ignore[misc]
        """Rough estimate: 1 token ≈ 4 chars."""
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Config (overridable via env)
# ---------------------------------------------------------------------------

HUNK_MAX_TOKENS     = int(os.getenv("HUNK_MAX_TOKENS", "1500"))
HUNK_OVERLAP_TOKENS = int(os.getenv("HUNK_OVERLAP_TOKENS", "100"))


# ---------------------------------------------------------------------------
# Sub-chunking
# ---------------------------------------------------------------------------

def split_hunk_if_needed(chunk: "HunkChunk") -> list["HunkChunk"]:
    """
    If the hunk's diff text fits within HUNK_MAX_TOKENS, return [chunk].
    Otherwise split into overlapping sub-chunks of ~HUNK_MAX_TOKENS tokens
    with HUNK_OVERLAP_TOKENS overlap, and tag each with sub_chunk_index /
    sub_chunk_total so the review loop can track them.
    """
    from prism_mcp.utils.diff_parser import HunkChunk  # local import avoids circular

    diff_lines = chunk.diff_lines
    if count_tokens(chunk.diff_text) <= HUNK_MAX_TOKENS:
        return [chunk]

    # Build sub-chunks by sliding a token window over the diff lines
    sub_chunks: list[HunkChunk] = []
    window_lines: list[str] = []
    window_tokens = 0
    overlap_lines: list[str] = []

    def _flush(start_offset: int) -> None:
        if not window_lines:
            return
        sub = HunkChunk(
            file_path=chunk.file_path,
            language=chunk.language,
            hunk_header=chunk.hunk_header,
            old_start=chunk.old_start + start_offset,
            new_start=chunk.new_start + start_offset,
            diff_lines=list(window_lines),
            context_lines=chunk.context_lines,
            change_type=chunk.change_type,
        )
        sub_chunks.append(sub)

    line_offset = 0
    for line in diff_lines:
        toks = count_tokens(line + "\n")
        if window_tokens + toks > HUNK_MAX_TOKENS and window_lines:
            _flush(line_offset - len(window_lines))
            # Keep overlap: take the last N lines whose token sum ≤ HUNK_OVERLAP_TOKENS
            overlap: list[str] = []
            overlap_tok = 0
            for prev in reversed(window_lines):
                pt = count_tokens(prev + "\n")
                if overlap_tok + pt > HUNK_OVERLAP_TOKENS:
                    break
                overlap.insert(0, prev)
                overlap_tok += pt
            window_lines = list(overlap)
            window_tokens = overlap_tok
        window_lines.append(line)
        window_tokens += toks
        line_offset += 1

    if window_lines:
        _flush(line_offset - len(window_lines))

    # Tag sub-chunk index / total
    total = len(sub_chunks)
    for i, sc in enumerate(sub_chunks):
        sc.sub_chunk_index = i + 1
        sc.sub_chunk_total = total

    return sub_chunks
