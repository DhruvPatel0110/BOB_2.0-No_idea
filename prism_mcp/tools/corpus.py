"""
corpus.py — prism_build_corpus tool.

Phase 3: stub — returns {status: "not_implemented"}.
Phase 4: will fetch CONTRIBUTING.md, style guides, and past PR review
         comment threads, chunk+embed them, and upsert into ChromaDB.
"""

from __future__ import annotations


def run_build_corpus(args: dict) -> dict:
    """
    Phase 3 stub.

    Expected args:
        owner         (str)  — GitHub repo owner
        repo          (str)  — GitHub repo name
        force_rebuild (bool) — re-index even if already indexed
    """
    owner = args.get("owner", "")
    repo  = args.get("repo", "")

    return {
        "status":  "not_implemented",
        "message": (
            f"prism_build_corpus for {owner}/{repo} is a Phase 4 feature. "
            "Run after the RAG layer is implemented."
        ),
        "owner": owner,
        "repo":  repo,
    }
