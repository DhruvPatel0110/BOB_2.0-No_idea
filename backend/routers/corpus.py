"""
corpus.py — Endpoints for managing and querying PRISM's RAG knowledge corpus.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from backend.models.schemas import (
    CorpusBuildRequest,
    CorpusBuildResponse,
    CorpusStatusResponse,
)
from prism_mcp.tools.corpus import run_build_corpus
from prism_mcp.rag.vector_store import corpus_status

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status", response_model=CorpusStatusResponse)
async def get_corpus_status(
    owner: Optional[str] = Query(default="", description="Optional GitHub repo owner"),
    repo: Optional[str] = Query(default="", description="Optional GitHub repo name"),
) -> CorpusStatusResponse:
    """
    Returns indexed collections, chunk counts, and cold-start dataset status.
    Serves as the data provider for the dashboard's CorpusStatus panel.
    """
    loop = asyncio.get_running_loop()
    status = await loop.run_in_executor(None, corpus_status, owner or "", repo or "")
    return CorpusStatusResponse(**status)


@router.post("/build", response_model=CorpusBuildResponse)
async def build_corpus(req: CorpusBuildRequest) -> CorpusBuildResponse:
    """
    Fetches style guide / CONTRIBUTING.md docs and merged PR history for a repo,
    chunks and embeds them, and upserts into ChromaDB.
    """
    loop = asyncio.get_running_loop()
    args = {
        "owner": req.owner.strip(),
        "repo": req.repo.strip(),
        "force_rebuild": req.force_rebuild,
    }

    result = await loop.run_in_executor(None, run_build_corpus, args)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Failed to build corpus"),
        )

    return CorpusBuildResponse(**result)
