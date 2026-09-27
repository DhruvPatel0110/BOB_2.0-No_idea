"""
session_store.py — Thread-safe in-memory session store for PRISM reviews.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_MAX_SESSIONS = 200


def create_session(review_id: str, pr_url: str) -> Dict[str, Any]:
    """Create a new review session in processing state."""
    with _LOCK:
        session: Dict[str, Any] = {
            "review_id": review_id,
            "status": "processing",
            "pr_url": pr_url,
            "created_at": time.time(),
            "completed_at": None,
            "progress": {
                "stage": "queued",
                "message": "Review job queued",
                "percent": 5,
            },
            "result": None,
            "error": None,
        }
        _SESSIONS[review_id] = session

        # Prune oldest if exceeds capacity
        if len(_SESSIONS) > _MAX_SESSIONS:
            oldest_key = min(_SESSIONS.keys(), key=lambda k: _SESSIONS[k]["created_at"])
            _SESSIONS.pop(oldest_key, None)

        return dict(session)


def get_session(review_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a copy of a review session."""
    with _LOCK:
        sess = _SESSIONS.get(review_id)
        return dict(sess) if sess else None


def update_session(review_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Update fields of an existing review session."""
    with _LOCK:
        sess = _SESSIONS.get(review_id)
        if not sess:
            return None
        for k, v in kwargs.items():
            sess[k] = v
        return dict(sess)


def list_sessions() -> List[Dict[str, Any]]:
    """Return all review sessions sorted by creation time descending."""
    with _LOCK:
        return sorted(
            [dict(s) for s in _SESSIONS.values()],
            key=lambda s: s.get("created_at", 0),
            reverse=True,
        )
