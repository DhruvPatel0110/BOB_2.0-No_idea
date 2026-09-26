"""
findings.py — Finding schema, validation, deduplication, and risk scoring.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITIES = ("Blocker", "Major", "Minor", "Nit")
CATEGORIES = ("security", "logic", "maintainability", "style", "tests")

SEVERITY_WEIGHTS = {"Blocker": 10, "Major": 3, "Minor": 1, "Nit": 0.2}

SKIP_EXTENSIONS = set(
    os.getenv("SKIP_FILE_EXTENSIONS", ".min.js,.min.css,.lock,.sum,.mod").split(",")
)

# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    severity:    str
    category:    str
    file_path:   str
    line_start:  int
    line_end:    int
    title:       str
    explanation: str
    suggestion:  str
    citation:    Optional[str] = None
    # GitHub-specific (filled in Phase 8)
    diff_position: Optional[int] = None

    # ── Severity helpers ───────────────────────────────────────────────────
    @property
    def severity_rank(self) -> int:
        return SEVERITIES.index(self.severity) if self.severity in SEVERITIES else 99

    def __lt__(self, other: "Finding") -> bool:
        # Sort: lower rank (more severe) first; then file; then line
        if self.severity_rank != other.severity_rank:
            return self.severity_rank < other.severity_rank
        if self.file_path != other.file_path:
            return self.file_path < other.file_path
        return self.line_start < other.line_start


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _coerce_severity(raw: str) -> str:
    raw = str(raw).strip().capitalize()
    return raw if raw in SEVERITIES else "Minor"


def _coerce_category(raw: str) -> str:
    raw = str(raw).strip().lower()
    return raw if raw in CATEGORIES else "maintainability"


def validate_finding(raw: dict, file_path: str) -> Optional[Finding]:
    """
    Convert a raw dict from the LLM into a Finding, coercing bad values.
    Returns None if the dict is missing required fields entirely.
    """
    title = str(raw.get("title") or "").strip()
    explanation = str(raw.get("explanation") or "").strip()
    if not title or not explanation:
        return None

    try:
        line_start = int(raw.get("line_start") or 0)
        line_end   = int(raw.get("line_end")   or line_start)
    except (TypeError, ValueError):
        line_start = line_end = 0

    return Finding(
        severity=_coerce_severity(raw.get("severity", "Minor")),
        category=_coerce_category(raw.get("category", "maintainability")),
        file_path=file_path,
        line_start=max(0, line_start),
        line_end=max(0, line_end),
        title=title[:120],
        explanation=explanation,
        suggestion=str(raw.get("suggestion") or "").strip(),
        citation=raw.get("citation") or None,
    )


def parse_findings(raw_list: list[dict], file_path: str) -> list[Finding]:
    """Validate and convert a list of raw dicts from the LLM."""
    results: list[Finding] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        f = validate_finding(item, file_path)
        if f is not None:
            results.append(f)
    return results


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

_LINE_PROXIMITY = 5  # findings within this many lines + same category = duplicate


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """
    Remove duplicate findings across all files/hunks.
    Two findings are duplicates when:
      - Same file_path
      - Same category
      - |line_start difference| ≤ LINE_PROXIMITY
    Keep the one with higher severity (lower rank).
    """
    kept: list[Finding] = []
    for candidate in findings:
        duplicate_of: Optional[int] = None
        for i, existing in enumerate(kept):
            if (
                existing.file_path == candidate.file_path
                and existing.category  == candidate.category
                and abs(existing.line_start - candidate.line_start) <= _LINE_PROXIMITY
            ):
                duplicate_of = i
                break
        if duplicate_of is None:
            kept.append(candidate)
        else:
            # Replace if candidate is more severe
            if candidate.severity_rank < kept[duplicate_of].severity_rank:
                kept[duplicate_of] = candidate
    return sorted(kept)


# ---------------------------------------------------------------------------
# Risk score
# ---------------------------------------------------------------------------

def compute_risk_score(findings: list[Finding]) -> int:
    """
    Weighted severity sum, capped at 100.
      Blocker×10 + Major×3 + Minor×1 + Nit×0.2
    Always returns at least 1 when there are any findings.
    """
    if not findings:
        return 0
    raw = sum(SEVERITY_WEIGHTS.get(f.severity, 0) for f in findings)
    return max(1, min(100, round(raw)))


# ---------------------------------------------------------------------------
# Aggregation helpers for the API response
# ---------------------------------------------------------------------------

def findings_by_severity(findings: list[Finding]) -> dict[str, int]:
    result = {s: 0 for s in SEVERITIES}
    for f in findings:
        result[f.severity] = result.get(f.severity, 0) + 1
    return result


def findings_by_category(findings: list[Finding]) -> dict[str, int]:
    result = {c: 0 for c in CATEGORIES}
    for f in findings:
        result[f.category] = result.get(f.category, 0) + 1
    return result


def findings_to_dicts(findings: list[Finding]) -> list[dict]:
    return [
        {
            "severity":    f.severity,
            "category":    f.category,
            "file":        f.file_path,
            "line_start":  f.line_start,
            "line_end":    f.line_end,
            "title":       f.title,
            "explanation": f.explanation,
            "suggestion":  f.suggestion,
            "citation":    f.citation,
        }
        for f in findings
    ]
