"""
health.py — Health check endpoint for PRISM dashboard and monitors.
"""

from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter
from backend.models.schemas import HealthResponse
from prism_mcp.tools.health import run_health_check

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse, include_in_schema=False)
async def get_health() -> HealthResponse:
    """
    Check availability of core dependencies: Ollama, ChromaDB, and GitHub API.
    Returns status used by the dashboard health panel.
    """
    loop = asyncio.get_running_loop()
    # Run in executor to prevent blocking the event loop on network calls
    result = await loop.run_in_executor(None, run_health_check)
    return HealthResponse(**result)
