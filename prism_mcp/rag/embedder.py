"""
embedder.py — Embedding wrapper for Phase 4 RAG.

Primary:  Ollama /api/embeddings with nomic-embed-text (dim=768, local, free).
Fallback: HuggingFace Inference API (all-MiniLM-L6-v2, dim=384) if Ollama fails.

Public API:
    embed_texts(texts: list[str]) -> list[list[float]]
    embed_one(text: str)          -> list[float]
    embedding_dim()               -> int
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL",   "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
HF_TOKEN           = os.getenv("HF_TOKEN", "")
HF_EMBED_URL       = (
    "https://api-inference.huggingface.co/pipeline/feature-extraction/"
    "sentence-transformers/all-MiniLM-L6-v2"
)

EMBED_BATCH_SIZE   = int(os.getenv("EMBED_BATCH_SIZE", "32"))

# ---------------------------------------------------------------------------
# Low-level HTTP helpers (stdlib only — matches ollama_client.py style)
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: dict, timeout: int = 60,
               headers: dict | None = None) -> bytes:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------
# Ollama embedder
# ---------------------------------------------------------------------------

def _embed_ollama(texts: list[str]) -> list[list[float]]:
    """Embed texts one-by-one via Ollama. Batching is serial; Ollama has no batch endpoint."""
    url     = f"{OLLAMA_BASE_URL}/api/embeddings"
    results = []
    for text in texts:
        body = _post_json(url, {"model": OLLAMA_EMBED_MODEL, "prompt": text}, timeout=30)
        data = json.loads(body)
        results.append(data["embedding"])
    return results


# ---------------------------------------------------------------------------
# HuggingFace fallback embedder
# ---------------------------------------------------------------------------

def _embed_hf(texts: list[str]) -> list[list[float]]:
    """Embed texts via HuggingFace Inference API in batches."""
    if not HF_TOKEN:
        raise RuntimeError(
            "Ollama embedding failed and HF_TOKEN is not set. "
            "Set HF_TOKEN in .env or ensure Ollama is running."
        )
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    results: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        body  = _post_json(
            HF_EMBED_URL,
            {"inputs": batch, "options": {"wait_for_model": True}},
            timeout=60,
            headers=headers,
        )
        batch_result = json.loads(body)
        # HF returns list[list[float]] or list[float] for single input
        if batch_result and isinstance(batch_result[0], float):
            results.append(batch_result)
        else:
            results.extend(batch_result)
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts. Returns a list of float vectors.

    Tries Ollama first; falls back to HuggingFace if Ollama is unreachable.
    Processes in EMBED_BATCH_SIZE batches.
    """
    if not texts:
        return []

    results: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        try:
            results.extend(_embed_ollama(batch))
        except Exception as e:
            log.warning("Ollama embedding failed for batch %d (%s) — trying HuggingFace", i, e)
            results.extend(_embed_hf(batch))

    return results


def embed_one(text: str) -> list[float]:
    """Embed a single text and return its vector."""
    return embed_texts([text])[0]


def embedding_dim() -> int:
    """
    Return the embedding dimension by embedding a probe string.
    nomic-embed-text → 768; all-MiniLM-L6-v2 → 384.
    Cached after first call.
    """
    if not hasattr(embedding_dim, "_dim"):
        vec = embed_one("probe")
        embedding_dim._dim = len(vec)   # type: ignore[attr-defined]
    return embedding_dim._dim   # type: ignore[attr-defined]
