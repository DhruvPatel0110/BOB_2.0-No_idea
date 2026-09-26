"""
reranker.py — Cross-encoder reranker for Phase 4 RAG retrieval.

Uses sentence-transformers CrossEncoder (cross-encoder/ms-marco-MiniLM-L-6-v2)
to score (query, chunk) pairs and return the top-k by reranker score.

Guarantees at least REPO_SLOTS results come from repo-specific collections
(style/history/source) when available, preventing cold-start chunks from
crowding out project-specific context.

Public API:
    rerank(query, candidates, top_k, *, repo_slots) -> list[dict]
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
TOP_K_DEFAULT  = int(os.getenv("RAG_TOP_K", "6"))
REPO_SLOTS     = int(os.getenv("RAG_REPO_SLOTS", "3"))   # guaranteed repo-specific slots

# Lazy-loaded model (first call downloads ~80 MB)
_model = None

def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder
        log.info("Loading reranker model %s (first call only)…", RERANKER_MODEL)
        _model = CrossEncoder(RERANKER_MODEL)
    return _model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = TOP_K_DEFAULT,
    *,
    repo_slots: int = REPO_SLOTS,
) -> list[dict]:
    """
    Score all (query, chunk) pairs with the cross-encoder and return top_k.

    Args:
        query:      The diff hunk text used as the query.
        candidates: List of chunk dicts (each must have "text" and "source_label").
        top_k:      Total results to return.
        repo_slots: Minimum number of results reserved for repo-specific chunks
                    (chunk_type style/history/source). Filled from global chunks
                    if repo-specific pool is smaller than repo_slots.

    Returns:
        Top-k chunk dicts, each augmented with a "reranker_score" key.
        Returns candidates[:top_k] (no re-scoring) if CrossEncoder unavailable.
    """
    if not candidates:
        return []

    # --- Split into repo-specific vs cold-start ---
    repo_chunks   = [c for c in candidates if _is_repo_specific(c)]
    global_chunks = [c for c in candidates if not _is_repo_specific(c)]

    try:
        model = _get_model()

        def score(chunks: list[dict]) -> list[dict]:
            if not chunks:
                return []
            pairs  = [(query, c["text"]) for c in chunks]
            scores = model.predict(pairs).tolist()
            for chunk, s in zip(chunks, scores):
                chunk = dict(chunk)
                chunk["reranker_score"] = round(float(s), 4)
            return [
                {**c, "reranker_score": round(float(s), 4)}
                for c, s in zip(chunks, scores)
            ]

        scored_repo   = sorted(score(repo_chunks),   key=lambda x: x["reranker_score"], reverse=True)
        scored_global = sorted(score(global_chunks), key=lambda x: x["reranker_score"], reverse=True)

        # Fill repo slots first, then fill remaining from global pool
        taken_repo   = scored_repo[:repo_slots]
        remaining    = top_k - len(taken_repo)
        taken_global = scored_global[:max(0, remaining)]

        # Merge and re-sort by score
        merged = sorted(taken_repo + taken_global, key=lambda x: x["reranker_score"], reverse=True)
        return merged[:top_k]

    except Exception as e:
        log.warning("Reranker unavailable (%s) — returning top-%d by vector score", e, top_k)
        # Fallback: honour repo_slots guarantee by vector score
        repo_top   = sorted(repo_chunks,   key=lambda x: x.get("score", 0), reverse=True)[:repo_slots]
        global_top = sorted(global_chunks, key=lambda x: x.get("score", 0), reverse=True)
        merged     = repo_top + global_top
        merged     = sorted(merged, key=lambda x: x.get("score", 0), reverse=True)
        return merged[:top_k]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_repo_specific(chunk: dict) -> bool:
    """True if the chunk came from a repo-specific collection (style/history/source)."""
    label = chunk.get("source_label", "").lower()
    ctype = chunk.get("chunk_type", "").lower()
    # Repo-specific chunks come from style/history/source collections
    # Their source_label typically contains the repo file path (not OWASP/smell keys)
    non_repo_signals = ("owasp", "cwe", "smell", "codereviewer", "cold_start")
    return not any(s in label for s in non_repo_signals)
