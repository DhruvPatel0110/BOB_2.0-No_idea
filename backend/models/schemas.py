"""
schemas.py — Pydantic models for PRISM REST API.
Shared across FastAPI endpoints and aligned with MCP tool definitions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Review Schemas
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    pr_url: str = Field(
        ...,
        description="Full GitHub Pull Request URL (e.g. https://github.com/owner/repo/pull/123)",
        examples=["https://github.com/pallets/flask/pull/5000"],
    )
    post_comments: bool = Field(
        default=False,
        description="Whether to automatically post comments to GitHub (requires Phase 8 and demo repo safety check)",
    )
    language_hint: Optional[str] = Field(
        default=None,
        description="Optional language override (e.g. python, typescript, java)",
    )


class AnalyzeResponse(BaseModel):
    review_id: str = Field(..., description="Unique UUID for this review session")
    status: str = Field(default="processing", description="Initial status: 'processing'")
    message: str = Field(default="Review initiated in background", description="Status message")


class ReviewProgress(BaseModel):
    stage: str = Field(..., description="Current processing stage (e.g. fetching_pr, chunking, rag_retrieval, generating_review)")
    message: str = Field(..., description="Human-readable progress description")
    percent: Optional[int] = Field(default=None, description="Estimated completion percentage (0-100)")


class ReviewStatusResponse(BaseModel):
    review_id: str = Field(..., description="Unique UUID for the review session")
    status: str = Field(..., description="Status: 'processing' | 'complete' | 'failed'")
    pr_url: str = Field(..., description="Target GitHub PR URL")
    created_at: float = Field(..., description="Epoch timestamp when the review was submitted")
    completed_at: Optional[float] = Field(default=None, description="Epoch timestamp when the review finished")
    progress: Optional[Dict[str, Any]] = Field(default=None, description="Latest progress snapshot")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Full ReviewResult payload once complete")
    error: Optional[str] = Field(default=None, description="Error message if review failed")


class PostReviewRequest(BaseModel):
    dry_run: bool = Field(
        default=True,
        description="If True (default), simulates the post without sending comments to GitHub. If False, performs live review posting.",
    )


class PostReviewResponse(BaseModel):
    status: str = Field(..., description="Posting status (e.g. 'simulated' | 'posted' | 'not_implemented')")
    dry_run: bool = Field(..., description="Whether this was a dry run")
    pr_url: str = Field(..., description="Target GitHub PR URL")
    findings_count: int = Field(..., description="Number of inline findings included in review")
    message: str = Field(..., description="Status explanation")


# ---------------------------------------------------------------------------
# Corpus Schemas
# ---------------------------------------------------------------------------

class CorpusBuildRequest(BaseModel):
    owner: str = Field(..., description="GitHub repository owner", examples=["pallets"])
    repo: str = Field(..., description="GitHub repository name", examples=["flask"])
    force_rebuild: bool = Field(default=False, description="Rebuild corpus from scratch if true")


class CorpusBuildResponse(BaseModel):
    ok: bool = Field(..., description="Whether corpus indexing completed successfully")
    owner: str = Field(..., description="GitHub repository owner")
    repo: str = Field(..., description="GitHub repository name")
    style_chunks: int = Field(default=0, description="Number of style/convention chunks indexed")
    history_chunks: int = Field(default=0, description="Number of merged PR review comments indexed")
    duration_s: float = Field(default=0.0, description="Time taken to build corpus in seconds")
    corpus_status: Dict[str, Any] = Field(default_factory=dict, description="Updated corpus statistics")
    error: Optional[str] = Field(default=None, description="Error details if build failed")


class CorpusStatusResponse(BaseModel):
    collections: Dict[str, Any] = Field(..., description="Collection statistics keyed by collection name")
    cold_start_loaded: bool = Field(..., description="Whether all cold-start collections (OWASP, smells, reviews) are ready")
    persist_dir: str = Field(..., description="Path to ChromaDB persist directory")


# ---------------------------------------------------------------------------
# Health Schemas
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    all_ok: bool = Field(..., description="True if all critical services (Ollama, ChromaDB, GitHub) are operational")
    ollama: Dict[str, Any] = Field(..., description="Ollama connectivity and model presence")
    chromadb: Dict[str, Any] = Field(..., description="ChromaDB client read/write health")
    github: Dict[str, Any] = Field(..., description="GitHub API authentication and rate limit status")
