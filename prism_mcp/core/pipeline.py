"""
pipeline.py — Phase 2 end-to-end review orchestrator.

Wires together:
  diff_parser → token_counter → prompt_builder → ollama_client → findings

Entry point: review_pr(diff, file_contents, pr_meta) → ReviewResult
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

from prism_mcp.utils.diff_parser   import parse_diff, HunkChunk
from prism_mcp.utils.token_counter import split_hunk_if_needed
from prism_mcp.core.prompt_builder  import build_review_prompt, build_summary_prompt
from prism_mcp.core.ollama_client   import generate_review, generate_summary
from prism_mcp.core.findings        import (
    parse_findings, deduplicate, compute_risk_score,
    findings_by_severity, findings_by_category, findings_to_dicts,
    attribute_citations, SKIP_EXTENSIONS, Finding,
)

log = logging.getLogger(__name__)

MAX_FILES_PER_PR = int(os.getenv("MAX_FILES_PER_PR", "20"))
MAX_HUNKS_PER_PR = int(os.getenv("MAX_HUNKS_PER_PR", "5"))

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class HunkResult:
    file_path:   str
    hunk_header: str
    findings:    list[Finding]
    raw_output:  str
    duration_s:  float

@dataclass
class ReviewResult:
    pr_url:                str
    summary:               str
    risk_score:            int
    findings:              list[Finding]
    findings_by_severity:  dict[str, int]
    findings_by_category:  dict[str, int]
    files_reviewed:        list[str]
    files_skipped:         list[str]
    hunk_count:            int
    duration_s:            float
    model_used:            str

    def to_dict(self) -> dict:
        return {
            "pr_url":               self.pr_url,
            "summary":              self.summary,
            "risk_score":           self.risk_score,
            "findings":             findings_to_dicts(self.findings),
            "findings_by_severity": self.findings_by_severity,
            "findings_by_category": self.findings_by_category,
            "files_reviewed":       self.files_reviewed,
            "files_skipped":        self.files_skipped,
            "hunk_count":           self.hunk_count,
            "duration_s":           round(self.duration_s, 2),
            "model_used":           self.model_used,
        }

# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------

def review_pr(
    diff:          str,
    file_contents: Optional[dict[str, str]] = None,
    pr_meta:       Optional[dict]           = None,
    language_hint: Optional[str]            = None,
    context_chunks_fn: Optional[Callable[[HunkChunk], list[dict]]] = None,
    progress_cb:   Optional[Callable] = None,
) -> ReviewResult:
    """
    Full review pipeline for one PR.

    Args:
        diff:             Raw unified diff string.
        file_contents:    {file_path: full_file_text} for context extraction.
        pr_meta:          {title, body, url, files} from GitHub for summary.
        language_hint:    Override language detection.
        context_chunks_fn: Phase 4 hook — called per chunk, returns RAG context.
                           Pass None in Phase 2.
        progress_cb:      Optional callback(msg) for streaming progress to UI.

    Returns:
        ReviewResult with all aggregated findings.
    """
    t0 = time.monotonic()
    pr_meta       = pr_meta or {}
    file_contents = file_contents or {}

    def _progress(stage: str, msg: str, percent: int = 0) -> None:
        if progress_cb:
            try:
                progress_cb(stage, msg, percent)
            except TypeError:
                try:
                    progress_cb(f"[{stage}] {msg}")
                except Exception:
                    pass
            except Exception as ex:
                log.warning("progress_cb error: %s", ex)
        log.info("[%s] %s (%d%%)", stage, msg, percent)
        print(f"\n[PRISM-PIPELINE] [{stage.upper()}] {msg} ({percent}%)", flush=True)

    # ── 1. Parse diff ──────────────────────────────────────────────────────
    _progress("parsing_diff", "Parsing PR diff into syntax hunks and AST nodes...", 25)
    all_chunks = parse_diff(diff, language_hint=language_hint, file_contents=file_contents)

    # ── 2. Filter skipped file types ──────────────────────────────────────
    files_skipped: list[str] = []
    chunks_to_review: list[HunkChunk] = []
    seen_files: list[str] = []

    for chunk in all_chunks:
        ext = "." + chunk.file_path.rsplit(".", 1)[-1].lower() if "." in chunk.file_path else ""
        if ext in SKIP_EXTENSIONS:
            if chunk.file_path not in files_skipped:
                files_skipped.append(chunk.file_path)
            continue
        chunks_to_review.append(chunk)
        if chunk.file_path not in seen_files:
            seen_files.append(chunk.file_path)

    # Cap at MAX_FILES_PER_PR unique files
    if len(seen_files) > MAX_FILES_PER_PR:
        allowed = set(seen_files[:MAX_FILES_PER_PR])
        extra   = [f for f in seen_files[MAX_FILES_PER_PR:]]
        files_skipped.extend(extra)
        chunks_to_review = [c for c in chunks_to_review if c.file_path in allowed]
        _progress("file_capped", f"Large PR: capped at {MAX_FILES_PER_PR} files; skipping {len(extra)} others", 28)

    files_reviewed = list(dict.fromkeys(c.file_path for c in chunks_to_review))

    # ── 3. Sub-chunk oversized hunks ──────────────────────────────────────
    expanded: list[HunkChunk] = []
    for chunk in chunks_to_review:
        expanded.extend(split_hunk_if_needed(chunk))

    if len(expanded) > MAX_HUNKS_PER_PR:
        _progress(
            "hunk_capped",
            f"PR has {len(expanded)} hunks; analyzing top {MAX_HUNKS_PER_PR} hunks for responsive analysis (set MAX_HUNKS_PER_PR in .env to change)",
            30,
        )
        expanded = expanded[:MAX_HUNKS_PER_PR]

    _progress("analyzing_hunks", f"Reviewing {len(files_reviewed)} file(s), {len(expanded)} hunk(s)...", 30)

    # ── 4. Per-hunk review loop ────────────────────────────────────────────
    all_findings: list[Finding] = []
    hunk_results: list[HunkResult] = []

    for i, chunk in enumerate(expanded, 1):
        label = chunk.file_path
        if chunk.sub_chunk_total > 1:
            label += f" [{chunk.sub_chunk_index}/{chunk.sub_chunk_total}]"

        pct = 30 + int(((i - 1) / len(expanded)) * 55)
        _progress(
            "analyzing_hunk",
            f"[{i}/{len(expanded)}] Reviewing {label} (lines {chunk.line_start}-{chunk.line_end})",
            pct,
        )

        # Phase 4 hook: retrieve RAG context (no-op in Phase 2)
        t_rag = time.monotonic()
        ctx_chunks = context_chunks_fn(chunk) if context_chunks_fn else None
        rag_s = time.monotonic() - t_rag
        print(f"  [RAG] Retrieved {len(ctx_chunks or [])} context chunks in {rag_s:.2f}s", flush=True)

        prompt = build_review_prompt(chunk, context_chunks=ctx_chunks)

        print(f"  [OLLAMA] Prompting model ({len(prompt)} chars)...", flush=True)
        t_hunk = time.monotonic()
        raw_findings, raw_text = generate_review(prompt)
        duration = time.monotonic() - t_hunk
        print(f"  [OLLAMA] Generated response in {duration:.1f}s", flush=True)

        findings = parse_findings(raw_findings, chunk.file_path)
        print(f"  [FINDINGS] Extracted {len(findings)} finding(s) from hunk {i}/{len(expanded)}", flush=True)

        if ctx_chunks:
            attribute_citations(findings, ctx_chunks)
        all_findings.extend(findings)
        hunk_results.append(HunkResult(
            file_path=chunk.file_path,
            hunk_header=chunk.hunk_header,
            findings=findings,
            raw_output=raw_text,
            duration_s=duration,
        ))
        log.debug("  hunk %d/%d → %d findings in %.1fs", i, len(expanded), len(findings), duration)

    # ── 5. Deduplicate + score ─────────────────────────────────────────────
    _progress("scoring", "Deduplicating findings and computing risk score...", 88)
    deduped   = deduplicate(all_findings)
    score     = compute_risk_score(deduped)
    by_sev    = findings_by_severity(deduped)
    by_cat    = findings_by_category(deduped)

    # ── 6. PR summary ─────────────────────────────────────────────────────
    _progress("generating_summary", "Generating PR executive summary via LLM...", 92)
    summary_prompt = build_summary_prompt(
        title=pr_meta.get("title", ""),
        body=pr_meta.get("body", ""),
        file_list=files_reviewed,
        findings=findings_to_dicts(deduped),
    )
    summary = generate_summary(summary_prompt).strip()

    total_time = time.monotonic() - t0
    _progress("complete", f"Review complete — {len(deduped)} findings, risk score {score}, {total_time:.1f}s total", 100)

    return ReviewResult(
        pr_url=pr_meta.get("url", ""),
        summary=summary,
        risk_score=score,
        findings=deduped,
        findings_by_severity=by_sev,
        findings_by_category=by_cat,
        files_reviewed=files_reviewed,
        files_skipped=files_skipped,
        hunk_count=len(expanded),
        duration_s=total_time,
        model_used=os.getenv("OLLAMA_MODEL", "granite3-dense:2b"),
    )
