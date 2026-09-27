"""
review.py — Endpoints for initiating, polling, and posting PR reviews.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks

from backend.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ReviewStatusResponse,
    PostReviewRequest,
    PostReviewResponse,
)
from backend.session_store import (
    create_session,
    get_session,
    update_session,
    list_sessions,
)
from prism_mcp.tools.analyze import run_analyze_pr
from prism_mcp.tools.post import run_post_review

log = logging.getLogger(__name__)
router = APIRouter()


async def _run_review_job(
    review_id: str,
    pr_url: str,
    post_comments: bool,
    language_hint: Optional[str],
) -> None:
    """Background task that executes the full PRISM review pipeline."""
    try:
        update_session(
            review_id,
            progress={
                "stage": "fetching_pr",
                "message": "Fetching PR diff and changed files from GitHub...",
                "percent": 20,
            },
        )

        loop = asyncio.get_running_loop()
        args = {
            "pr_url": pr_url,
            "post_comments": post_comments,
            "language_hint": language_hint,
        }

        # run_analyze_pr runs chunking, RAG context retrieval, Ollama generation, and findings parsing
        result = await loop.run_in_executor(None, run_analyze_pr, args)

        if "error" in result:
            update_session(
                review_id,
                status="failed",
                completed_at=time.time(),
                error=result["error"],
                progress={
                    "stage": "failed",
                    "message": f"Analysis failed: {result['error']}",
                    "percent": 100,
                },
            )
        else:
            update_session(
                review_id,
                status="complete",
                completed_at=time.time(),
                result=result,
                progress={
                    "stage": "complete",
                    "message": f"Review complete — {len(result.get('findings', []))} findings identified",
                    "percent": 100,
                },
            )
    except Exception as e:
        log.exception("Background review job %s raised unexpected error", review_id)
        update_session(
            review_id,
            status="failed",
            completed_at=time.time(),
            error=str(e),
            progress={
                "stage": "failed",
                "message": f"Review encountered an unexpected exception: {e}",
                "percent": 100,
            },
        )


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze_pr(req: AnalyzeRequest) -> AnalyzeResponse:
    """
    Submits a GitHub PR for asynchronous review analysis.
    Returns review_id immediately; frontend polls GET /review/{review_id}.
    """
    url = req.pr_url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PR URL. Must begin with https://github.com/",
        )
    if "pull" not in url:
        raise HTTPException(
            status_code=400,
            detail="Invalid PR URL. Expected format: https://github.com/owner/repo/pull/N",
        )

    review_id = str(uuid.uuid4())
    create_session(review_id, url)

    # Launch non-blocking background task
    asyncio.create_task(
        _run_review_job(
            review_id=review_id,
            pr_url=url,
            post_comments=req.post_comments,
            language_hint=req.language_hint,
        )
    )

    return AnalyzeResponse(
        review_id=review_id,
        status="processing",
        message="Review job queued and running in background",
    )


@router.get("", response_model=List[ReviewStatusResponse])
@router.get("/", response_model=List[ReviewStatusResponse], include_in_schema=False)
async def get_all_reviews() -> List[ReviewStatusResponse]:
    """Returns list of recent review sessions."""
    return [ReviewStatusResponse(**s) for s in list_sessions()]


@router.get("/{review_id}", response_model=ReviewStatusResponse)
async def get_review_status(review_id: str) -> ReviewStatusResponse:
    """
    Poll the status of an ongoing or completed review.
    Returns findings payload when status == 'complete'.
    """
    sess = get_session(review_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Review session not found")
    return ReviewStatusResponse(**sess)


@router.post("/{review_id}/post", response_model=PostReviewResponse)
async def post_review_comments(
    review_id: str,
    req: PostReviewRequest = PostReviewRequest(),
) -> PostReviewResponse:
    """
    Posts the findings of a completed review back to GitHub as line-anchored comments.
    Defaults to dry_run: true. Set dry_run: false for live publishing.
    """
    sess = get_session(review_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Review session not found")

    if sess.get("status") != "complete":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot post review: analysis is in status '{sess.get('status')}'. Must be 'complete'.",
        )

    result_data = sess.get("result") or {}
    findings = result_data.get("findings", [])
    summary = result_data.get("summary", "")

    loop = asyncio.get_running_loop()
    post_args = {
        "pr_url": sess["pr_url"],
        "findings": findings,
        "summary": summary,
        "dry_run": req.dry_run,
    }

    res = await loop.run_in_executor(None, run_post_review, post_args)
    if not res.get("ok", True) and "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])

    return PostReviewResponse(
        status=res.get("status", "simulated" if req.dry_run else "posted"),
        dry_run=res.get("dry_run", req.dry_run),
        pr_url=res.get("pr_url", sess["pr_url"]),
        findings_count=res.get("findings_count", len(findings)),
        message=res.get("message", "Review comments processed"),
    )
