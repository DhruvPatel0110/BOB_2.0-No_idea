"""
vector_store.py — ChromaDB wrapper for Phase 4 RAG.

Manages 6 named collections:
  Per-repo (keyed by owner/repo slug):
    style_{slug}    — CONTRIBUTING.md, style guides, linter configs
    history_{slug}  — past PR review comment threads
    source_{slug}   — source-code chunks from the repo

  Global (cold-start, shared across all repos):
    cold_start_reviews — Microsoft CodeReviewer sample (Phase 5)
    cold_start_owasp   — OWASP Top-10 rules (Phase 5)
    cold_start_smells  — Code smell catalog (Phase 5)

All upserts are idempotent via SHA-256 chunk_id.

Public API:
    upsert_chunks(collection_name, chunks, embeddings)
    query(collection_name, query_embedding, n_results) -> list[dict]
    collection_stats(collection_name)                 -> dict
    corpus_status()                                   -> dict
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")

# ---------------------------------------------------------------------------
# Repo slug helper
# ---------------------------------------------------------------------------

def repo_slug(owner: str, repo: str) -> str:
    """Convert owner/repo to a safe collection-name fragment."""
    raw = f"{owner}_{repo}".lower()
    return re.sub(r"[^a-z0-9_-]", "_", raw)[:40]


def collection_names(owner: str, repo: str) -> dict[str, str]:
    """Return all 6 collection names for a given repo."""
    slug = repo_slug(owner, repo)
    return {
        "style":                f"style_{slug}",
        "history":              f"history_{slug}",
        "source":               f"source_{slug}",
        "cold_start_reviews":   "cold_start_reviews",
        "cold_start_owasp":     "cold_start_owasp",
        "cold_start_smells":    "cold_start_smells",
    }


# ---------------------------------------------------------------------------
# Client (lazy init, singleton per process)
# ---------------------------------------------------------------------------

_client = None

def _get_client():
    global _client
    if _client is None:
        import chromadb
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        log.debug("ChromaDB client initialised at %s", CHROMA_PERSIST_DIR)
    return _client


def _get_collection(name: str):
    return _get_client().get_or_create_collection(
        name,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Public: upsert
# ---------------------------------------------------------------------------

def upsert_chunks(
    collection_name: str,
    chunks: list,          # list[ChunkDoc]
    embeddings: list[list[float]],
) -> int:
    """
    Upsert chunks into the named collection. Idempotent via chunk_id.

    Returns the number of chunks upserted.
    """
    if not chunks:
        return 0

    col = _get_collection(collection_name)

    ids        = [c.chunk_id for c in chunks]
    documents  = [c.text for c in chunks]
    metadatas  = [
        {
            "file_path":    c.file_path,
            "language":     c.language,
            "start_line":   c.start_line,
            "end_line":     c.end_line,
            "symbol_name":  c.symbol_name,
            "chunk_type":   c.chunk_type,
            "source_label": c.source_label,
        }
        for c in chunks
    ]

    # Chroma upsert in batches of 500 to avoid payload size limits
    BATCH = 500
    total = 0
    for i in range(0, len(chunks), BATCH):
        col.upsert(
            ids=ids[i:i+BATCH],
            embeddings=embeddings[i:i+BATCH],
            documents=documents[i:i+BATCH],
            metadatas=metadatas[i:i+BATCH],
        )
        total += len(ids[i:i+BATCH])

    log.debug("upsert_chunks: %s ← %d chunks", collection_name, total)
    return total


# ---------------------------------------------------------------------------
# Public: query
# ---------------------------------------------------------------------------

def query_collection(
    collection_name: str,
    query_embedding: list[float],
    n_results: int = 10,
) -> list[dict]:
    """
    Query a collection and return the top-n results as dicts.

    Returns [] (not an error) if the collection is empty or query fails.
    """
    try:
        col = _get_collection(collection_name)
        count = col.count()
        if count == 0:
            return []

        n = min(n_results, count)
        result = col.query(
            query_embeddings=[query_embedding],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

        rows = []
        for doc, meta, dist in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            rows.append({
                "text":         doc,
                "source_label": meta.get("source_label", ""),
                "file_path":    meta.get("file_path", ""),
                "start_line":   meta.get("start_line", 0),
                "end_line":     meta.get("end_line", 0),
                "language":     meta.get("language", ""),
                "chunk_type":   meta.get("chunk_type", ""),
                "score":        round(1 - dist, 4),   # cosine sim from distance
            })
        return rows
    except Exception as e:
        log.debug("query_collection failed for %s: %s", collection_name, e)
        return []


# ---------------------------------------------------------------------------
# Public: stats / status
# ---------------------------------------------------------------------------

def collection_stats(collection_name: str) -> dict:
    try:
        col   = _get_collection(collection_name)
        count = col.count()
        return {"name": collection_name, "count": count, "ok": True}
    except Exception as e:
        return {"name": collection_name, "count": 0, "ok": False, "error": str(e)}


def corpus_status(owner: str = "", repo: str = "") -> dict:
    """Return chunk counts for all collections relevant to a repo."""
    names = collection_names(owner or "none", repo or "none")
    stats = {key: collection_stats(col) for key, col in names.items()}
    cold_start_loaded = all(
        stats[k]["count"] > 0
        for k in ("cold_start_reviews", "cold_start_owasp", "cold_start_smells")
    )
    return {
        "collections":        stats,
        "cold_start_loaded":  cold_start_loaded,
        "persist_dir":        CHROMA_PERSIST_DIR,
    }
