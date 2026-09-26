"""
retrieve.py — prism_retrieve_context tool.

Phase 3: stub — returns an empty context_chunks array.
Phase 4: will query ChromaDB, run the cross-encoder reranker, and return
         the top-k context chunks to inject into the review prompt.
"""

from __future__ import annotations


def run_retrieve_context(args: dict) -> dict:
    """
    Phase 3 stub.

    Expected args:
        diff_hunk  (str)  — raw unified diff hunk
        file_path  (str)  — file the hunk belongs to
        language   (str)  — programming language
        repo_owner (str)  — GitHub repo owner (for repo-scoped retrieval)
        repo_name  (str)  — GitHub repo name
    """
    return {
        "status":         "not_implemented",
        "context_chunks": [],
        "message":        (
            "prism_retrieve_context is a Phase 4 feature. "
            "Retrieval will be available after the RAG layer is implemented."
        ),
    }
