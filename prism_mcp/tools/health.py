"""
health.py — prism_health_check tool implementation.

Pings Ollama, ChromaDB, and the GitHub token.
Returns a structured dict that the MCP server serialises to JSON.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error


# ---------------------------------------------------------------------------
# Config (mirrors health_check.py but read at call-time so .env reloads work)
# ---------------------------------------------------------------------------

def _cfg() -> dict:
    return {
        "ollama_url":   os.getenv("OLLAMA_BASE_URL",    "http://localhost:11434"),
        "gen_model":    os.getenv("OLLAMA_MODEL",        "granite3-dense:8b"),
        "embed_model":  os.getenv("OLLAMA_EMBED_MODEL",  "nomic-embed-text"),
        "github_token": os.getenv("GITHUB_TOKEN",        ""),
        "chroma_dir":   os.getenv("CHROMA_PERSIST_DIR",  "./data/chroma_db"),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str, headers: dict | None = None, timeout: int = 10) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return 0, str(e).encode()


def _post(url: str, body: dict, timeout: int = 30) -> tuple[int, bytes]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return 0, str(e).encode()


# ---------------------------------------------------------------------------
# Sub-checks
# ---------------------------------------------------------------------------

def _check_ollama(cfg: dict) -> dict:
    base = cfg["ollama_url"]
    status, body = _get(f"{base}/api/tags")
    if status != 200:
        return {"ok": False, "error": f"Ollama not reachable at {base} (HTTP {status})"}

    try:
        raw_names = {m["name"] for m in json.loads(body).get("models", [])}
    except Exception:
        raw_names = set()

    def present(model: str) -> bool:
        return model in raw_names or any(n.startswith(model.split(":")[0]) for n in raw_names)

    gen_ok   = present(cfg["gen_model"])
    embed_ok = present(cfg["embed_model"])

    return {
        "ok":             gen_ok and embed_ok,
        "reachable":      True,
        "gen_model":      cfg["gen_model"],
        "gen_model_ok":   gen_ok,
        "embed_model":    cfg["embed_model"],
        "embed_model_ok": embed_ok,
        "error":          None if (gen_ok and embed_ok) else (
            f"Missing models: "
            + (cfg["gen_model"] if not gen_ok else "")
            + (" " if not gen_ok and not embed_ok else "")
            + (cfg["embed_model"] if not embed_ok else "")
        ),
    }


def _check_chromadb(cfg: dict) -> dict:
    try:
        import chromadb  # type: ignore
    except ImportError:
        return {"ok": False, "error": "chromadb not installed — run: pip install chromadb"}

    os.makedirs(cfg["chroma_dir"], exist_ok=True)
    try:
        client = chromadb.PersistentClient(path=cfg["chroma_dir"])
        # Quick R/W smoke test
        col = client.get_or_create_collection("prism-health-probe")
        col.upsert(ids=["probe"], documents=["ok"], embeddings=[[0.0] * 384])
        col.query(query_embeddings=[[0.0] * 384], n_results=1)
        client.delete_collection("prism-health-probe")
        return {"ok": True, "path": cfg["chroma_dir"], "error": None}
    except Exception as e:
        return {"ok": False, "path": cfg["chroma_dir"], "error": str(e)}


def _check_github(cfg: dict) -> dict:
    token = cfg["github_token"]
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN not set in .env"}

    status, body = _get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "PRISM-health-check"},
    )
    if status == 401:
        return {"ok": False, "error": "Token invalid or expired"}
    if status == 403:
        return {"ok": False, "error": "Token lacks required scopes (need: repo, write:discussion)"}
    if status != 200:
        return {"ok": False, "error": f"GitHub API HTTP {status}"}

    try:
        login = json.loads(body).get("login", "unknown")
    except Exception:
        login = "unknown"

    return {"ok": True, "authenticated_as": login, "error": None}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_health_check() -> dict:
    """
    Called by the MCP server for the prism_health_check tool.
    Returns a structured dict:
        {
            "all_ok": bool,
            "ollama":   {...},
            "chromadb": {...},
            "github":   {...},
        }
    """
    cfg = _cfg()

    ollama   = _check_ollama(cfg)
    chromadb = _check_chromadb(cfg)
    github   = _check_github(cfg)

    return {
        "all_ok":   ollama["ok"] and chromadb["ok"] and github["ok"],
        "ollama":   ollama,
        "chromadb": chromadb,
        "github":   github,
    }
