"""
retrieve.py — prism_retrieve_context tool (Phase 4 — fully implemented).

Queries ChromaDB across all relevant collections for a given diff hunk,
runs the cross-encoder reranker, and returns the top-6 context chunks to
inject into the review prompt.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

RAG_CANDIDATES_PER_COLLECTION = int(os.getenv("RAG_CANDIDATES_PER_COLLECTION", "10"))
RAG_TOP_K                     = int(os.getenv("RAG_TOP_K", "6"))


def run_retrieve_context(args: dict) -> dict:
    """
    Query ChromaDB + rerank for a single diff hunk.

    Args:
        diff_hunk  (str)  — raw unified diff hunk text
        file_path  (str)  — file the hunk belongs to
        language   (str)  — programming language (optional)
        repo_owner (str)  — GitHub repo owner (for repo-scoped collections)
        repo_name  (str)  — GitHub repo name

    Returns:
        {
            "context_chunks": [...],   # top-k chunk dicts, each with source_label
            "collection_hits": {...},  # how many candidates per collection
        }
    """
    diff_hunk  = args.get("diff_hunk", "").strip()
    file_path  = args.get("file_path", "")
    language   = args.get("language", "")
    repo_owner = args.get("repo_owner", "")
    repo_name  = args.get("repo_name",  "")

    if not diff_hunk:
        return {"error": "diff_hunk is required", "context_chunks": []}

    try:
        from prism_mcp.rag.embedder     import embed_one
        from prism_mcp.rag.vector_store import query_collection, collection_names
        from prism_mcp.rag.reranker     import rerank

        # Build query: combine file path hint + language hint + hunk text
        query_text = _build_query(diff_hunk, file_path, language)
        query_vec  = embed_one(query_text)

        cols        = collection_names(repo_owner or "none", repo_name or "none")
        candidates  = []
        hits        = {}
        n           = RAG_CANDIDATES_PER_COLLECTION

        # Query all 6 collections, collect candidates
        for key, col_name in cols.items():
            results = query_collection(col_name, query_vec, n_results=n)
            hits[key] = len(results)
            candidates.extend(results)

        log.debug(
            "retrieve_context: %d total candidates from %d collections",
            len(candidates), len(cols)
        )

        # Rerank and return top-k
        top_chunks = rerank(query_text, candidates, top_k=RAG_TOP_K)

        return {
            "context_chunks":  top_chunks,
            "collection_hits": hits,
            "total_candidates": len(candidates),
        }

    except Exception as e:
        log.exception("retrieve_context failed")
        return {
            "error":           f"Retrieval failed: {e}",
            "context_chunks":  [],
            "collection_hits": {},
        }


def _build_query(diff_hunk: str, file_path: str, language: str) -> str:
    """
    Build a retrieval query from the diff hunk.
    Prepend file/language context so the embedding captures the domain.
    Trim the hunk to ~300 tokens to keep the query focused.
    """
    try:
        import tiktoken
        enc  = tiktoken.get_encoding("cl100k_base")
        toks = enc.encode(diff_hunk)
        if len(toks) > 300:
            diff_hunk = enc.decode(toks[:300])
    except Exception:
        if len(diff_hunk) > 1200:
            diff_hunk = diff_hunk[:1200]

    parts = []
    if language:
        parts.append(f"Language: {language}")
    if file_path:
        parts.append(f"File: {file_path}")
    parts.append(diff_hunk)
    return "\n".join(parts)
