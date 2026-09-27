"""
session_store.py — Thread-safe in-memory session store for PRISM reviews.
Includes pre-seeded demo session for instant hackathon judge demonstration.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_MAX_SESSIONS = 200

# ---------------------------------------------------------------------------
# Pre-seeded Demo Session for Hackathon Judges (Phase 9 Backup / Fast Demo)
# ---------------------------------------------------------------------------

_DEMO_SAMPLE_DIFF = """diff --git a/demo_sample.py b/demo_sample.py
new file mode 100644
index 0000000..f6b6107
--- /dev/null
+++ b/demo_sample.py
@@ -0,0 +1,5 @@
+def get_user_profile(user_data: dict, user_id: str):
+    # Missing null safety checks and raw SQL concatenation
+    username = user_data["profile"]["username"]
+    query = f"SELECT * FROM users WHERE id = '{user_id}' AND name = '{username}'"
+    return query
"""

_SESSIONS["demo-pr-1"] = {
    "review_id": "demo-pr-1",
    "status": "complete",
    "pr_url": "https://github.com/DhruvPatel0110/BOB_2.0-No_idea/pull/1",
    "created_at": time.time() - 3600,
    "completed_at": time.time() - 3570,
    "progress": {
        "stage": "complete",
        "message": "Review complete — 2 convention-grounded findings identified",
        "percent": 100,
    },
    "result": {
        "pr_meta": {
            "title": "feat: add user profile query helper",
            "body": "Demo pull request testing PRISM AI Code Review Coach.",
            "url": "https://github.com/DhruvPatel0110/BOB_2.0-No_idea/pull/1",
            "author": "DhruvPatel0110",
            "files": ["demo_sample.py"],
        },
        "diff_text": _DEMO_SAMPLE_DIFF,
        "risk_score": 35,
        "summary": "This PR introduces a user profile query helper in demo_sample.py. While concise, it contains critical security vulnerabilities (SQL Injection) and fragile dictionary access patterns that violate the repository's CONTRIBUTING.md standards.",
        "key_risks": [
            "SQL Injection risk via direct f-string parameter interpolation into raw SQL query",
            "Unhandled KeyError / TypeError risk from unvalidated nested dict traversal",
            "Violation of CONTRIBUTING.md §1.1 parameterized queries mandate",
        ],
        "findings": [
            {
                "severity": "Blocker",
                "category": "security",
                "file": "demo_sample.py",
                "line_start": 4,
                "line_end": 4,
                "title": "Raw SQL String Interpolation (SQL Injection Risk)",
                "explanation": "Direct interpolation of user input ('user_id' and 'username') into raw SQL strings allows SQL injection attacks. CONTRIBUTING.md §1.1 strictly mandates parameterized queries or ORM query builders.",
                "suggestion": "query = \"SELECT * FROM users WHERE id = %s AND name = %s\"\nreturn db.execute(query, (user_id, username))",
                "citation": "CONTRIBUTING.md §1.1 | OWASP A03:2021",
            },
            {
                "severity": "Major",
                "category": "logic",
                "file": "demo_sample.py",
                "line_start": 3,
                "line_end": 3,
                "title": "Unsafe Nested Dictionary Access (Missing Null Safety)",
                "explanation": "Chained dictionary lookup user_data['profile']['username'] raises an unhandled KeyError or TypeError if 'profile' is null or omitted. CONTRIBUTING.md §2.1 requires safe access with .get() or default fallbacks.",
                "suggestion": "profile = user_data.get('profile') or {}\nusername = profile.get('username', 'Unknown')",
                "citation": "CONTRIBUTING.md §2.1",
            },
        ],
        "findings_by_category": {"security": 1, "logic": 1, "style": 0, "maintainability": 0, "tests": 0},
        "findings_by_severity": {"Blocker": 1, "Major": 1, "Minor": 0, "Nit": 0},
        "hunk_count": 1,
        "duration_s": 24.5,
    },
    "error": None,
}


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

        # Prune oldest if exceeds capacity (keep demo session)
        if len(_SESSIONS) > _MAX_SESSIONS:
            keys = [k for k in _SESSIONS.keys() if k != "demo-pr-1"]
            if keys:
                oldest_key = min(keys, key=lambda k: _SESSIONS[k]["created_at"])
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
