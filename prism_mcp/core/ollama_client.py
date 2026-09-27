"""
ollama_client.py — Streaming Ollama API client for PRISM.

Handles:
  - Streaming generate (reads first-token-fast, collects full response)
  - Embeddings (used in Phase 4)
  - JSON extraction from model output (with one retry)
  - HuggingFace Inference API fallback for embeddings
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.error
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "granite3-dense:2b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))
OLLAMA_TIMEOUT     = int(os.getenv("OLLAMA_TIMEOUT", "600"))
HF_TOKEN           = os.getenv("HF_TOKEN", "")
HF_EMBED_URL       = (
    "https://api-inference.huggingface.co/pipeline/feature-extraction/"
    "sentence-transformers/all-MiniLM-L6-v2"
)

# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: dict, timeout: int = 120, headers: dict | None = None) -> bytes:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _stream_generate(url: str, payload: dict, timeout: int | None = None) -> str:
    """
    Send a streaming generate request to Ollama and collect the full
    response text by concatenating all 'response' fields from the
    newline-delimited JSON stream.
    """
    timeout = timeout or OLLAMA_TIMEOUT
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}
    )
    collected: list[str] = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        while True:
            line = r.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            collected.append(chunk.get("response", ""))
            if chunk.get("done", False):
                break
    return "".join(collected)


# ---------------------------------------------------------------------------
# JSON extraction from raw LLM output
# ---------------------------------------------------------------------------

_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _extract_json_array(text: str) -> list[dict]:
    """
    Extract a JSON array from the model's raw text output.
    Handles: bare array, array inside markdown fences, leading prose.
    """
    # 1. Try direct parse (model output IS the array)
    stripped = text.strip()
    if stripped.startswith("["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # 2. Strip markdown fences
    fenced = re.sub(r"```(?:json)?\s*", "", stripped)
    fenced = re.sub(r"```", "", fenced).strip()
    if fenced.startswith("["):
        try:
            return json.loads(fenced)
        except json.JSONDecodeError:
            pass

    # 3. Regex search for first [...] block
    m = _JSON_ARRAY_RE.search(fenced)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return []


# ---------------------------------------------------------------------------
# Public: generate review findings
# ---------------------------------------------------------------------------

def generate_review(prompt: str, model: str | None = None) -> tuple[list[dict], str]:
    """
    Send prompt to Ollama and return (findings_list, raw_text).

    If JSON parsing fails on the first attempt, retries once with an
    explicit "output valid JSON only" suffix appended to the prompt.

    Returns ([], raw_text) if both attempts fail.
    """
    model = model or OLLAMA_MODEL
    url   = f"{OLLAMA_BASE_URL}/api/generate"

    def _attempt(p: str) -> tuple[list[dict], str]:
        total_cores = os.cpu_count() or 4
        safe_threads = max(1, min(total_cores - 2, 6))
        env_threads = os.getenv("OLLAMA_NUM_THREADS")
        threads = int(env_threads) if env_threads else safe_threads

        raw = _stream_generate(url, {
            "model":   model,
            "prompt":  p,
            "stream":  True,
            "options": {
                "temperature": 0.1,
                "num_predict": OLLAMA_NUM_PREDICT,
                "num_thread": threads,
            },
        })
        findings = _extract_json_array(raw)
        return findings, raw

    findings, raw = _attempt(prompt)
    if not isinstance(findings, list):
        findings = []

    if not findings and raw.strip() not in ("", "[]"):
        # Retry with explicit JSON instruction
        retry_prompt = (
            prompt
            + "\n\nIMPORTANT: You MUST output ONLY a valid JSON array "
            "and nothing else. No prose, no fences. Start your response with [ "
            "and end with ]."
        )
        log.debug("JSON parse failed on first attempt — retrying with strict JSON instruction")
        findings, raw = _attempt(retry_prompt)
        if not isinstance(findings, list):
            findings = []

    log.debug("generate_review: model=%s findings=%d raw_len=%d", model, len(findings), len(raw))
    return findings, raw


# ---------------------------------------------------------------------------
# Public: generate PR summary
# ---------------------------------------------------------------------------

def generate_summary(prompt: str, model: str | None = None) -> str:
    """
    Send the summary prompt to Ollama and return the plain-text response.
    """
    model = model or OLLAMA_MODEL
    url   = f"{OLLAMA_BASE_URL}/api/generate"
    total_cores = os.cpu_count() or 4
    safe_threads = max(1, min(total_cores - 2, 6))
    env_threads = os.getenv("OLLAMA_NUM_THREADS")
    threads = int(env_threads) if env_threads else safe_threads

    return _stream_generate(url, {
        "model":   model,
        "prompt":  prompt,
        "stream":  True,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
            "num_thread": threads,
        },
    })


# ---------------------------------------------------------------------------
# Public: embeddings  (used in Phase 4 — included here so Phase 4 just calls it)
# ---------------------------------------------------------------------------

def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    """
    Embed a list of texts. Returns a list of float vectors.

    Primary: Ollama /api/embeddings (nomic-embed-text, dim=768).
    Fallback: HuggingFace Inference API (all-MiniLM-L6-v2, dim=384).
    """
    model = model or OLLAMA_EMBED_MODEL
    results: list[list[float]] = []

    try:
        for text in texts:
            body = _post_json(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                {"model": model, "prompt": text},
                timeout=30,
            )
            data = json.loads(body)
            results.append(data["embedding"])
        return results

    except Exception as e:
        log.warning("Ollama embedding failed (%s) — falling back to HuggingFace", e)

    # HuggingFace fallback
    if not HF_TOKEN:
        raise RuntimeError(
            "Ollama embeddings failed and HF_TOKEN is not set. "
            "Set HF_TOKEN in .env or fix Ollama."
        )
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    body = _post_json(HF_EMBED_URL, {"inputs": texts, "options": {"wait_for_model": True}},
                      timeout=60, headers=headers)
    return json.loads(body)
