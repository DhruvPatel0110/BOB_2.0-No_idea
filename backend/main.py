"""
main.py — FastAPI Application Entry Point for PRISM.
Phase 6: Exposes PRISM tools as a REST API for the Next.js frontend.
"""

from __future__ import annotations

import logging
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import review, corpus, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("prism_backend")

app = FastAPI(
    title="PRISM — AI Code Review Coach API",
    version="0.6.0",
    description=(
        "REST API wrapping PRISM's MCP tools for GitHub PR analysis, "
        "convention-aware RAG context retrieval, and review generation."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS Configuration (allows Next.js frontend at localhost:3000)
# ---------------------------------------------------------------------------

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mount Routers
# ---------------------------------------------------------------------------

app.include_router(review.router, prefix="/review", tags=["review"])
app.include_router(corpus.router, prefix="/corpus", tags=["corpus"])
app.include_router(health.router, prefix="/health", tags=["health"])


# ---------------------------------------------------------------------------
# Root & Info Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["info"])
async def root():
    return {
        "service": "PRISM AI Code Review Coach Backend",
        "version": "0.6.0",
        "phase": "Phase 6 — FastAPI Backend",
        "status": "online",
        "docs": "/docs",
        "endpoints": {
            "health": "GET /health",
            "corpus_status": "GET /corpus/status",
            "corpus_build": "POST /corpus/build",
            "review_analyze": "POST /review/analyze",
            "review_status": "GET /review/{review_id}",
            "review_post": "POST /review/{review_id}/post",
        },
    }
