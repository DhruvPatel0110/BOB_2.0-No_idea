"""
setup_cold_start.py — Phase 5 cold-start corpus builder.

Reads the three JSONL files from data/cold_start/ and upserts them into
ChromaDB's three global cold-start collections:
    cold_start_reviews  ← codereviewer_sample.jsonl (diff → review comment)
    cold_start_owasp    ← owasp_rules.jsonl
    cold_start_smells   ← code_smells.jsonl

Run AFTER download_datasets.py:
    python scripts/download_datasets.py   # ~5 min to stream + sample
    python scripts/setup_cold_start.py    # ~15 min to embed 50k rows

Usage:
    python scripts/setup_cold_start.py
    python scripts/setup_cold_start.py --skip-reviews   # only owasp + smells (fast)
    python scripts/setup_cold_start.py --dry-run        # count rows, don't embed

Exit codes:
    0 — success / cold_start_loaded: true
    1 — failure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

_load_env()

COLD_START_DIR = os.getenv("COLD_START_DIR", "./data/cold_start")

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg: str) -> None: print(f"  {RED}✗{RESET}  {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}!{RESET}  {msg}")
def info(msg: str) -> None: print(f"  …  {msg}")


# ---------------------------------------------------------------------------
# JSONL loader
# ---------------------------------------------------------------------------

def _load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


# ---------------------------------------------------------------------------
# Converters: raw row → embeddable text + ChunkDoc
# ---------------------------------------------------------------------------

def _review_row_to_chunk(row: dict):
    from prism_mcp.rag.chunker import ChunkDoc
    diff  = (row.get("diff") or "").strip()
    msg   = (row.get("msg") or "").strip()
    lang  = row.get("language", "text")
    sid   = row.get("source_id", "")
    label = row.get("source_label", f"CodeReviewer ({lang})")

    # Embed the diff (what gets queried against at review time)
    # Store the review comment in the text field so it's injected as context
    embed_text = diff[:1500]   # trim to keep embeddings fast
    store_text = f"[Review comment for diff below]\n{msg}\n\n[Diff]\n{diff[:800]}"

    return ChunkDoc(
        chunk_id    = ChunkDoc.make_id("cold_start_reviews", diff + msg),
        file_path   = "cold_start_reviews",
        text        = store_text,
        language    = lang,
        start_line  = 0,
        end_line    = 0,
        symbol_name = "",
        chunk_type  = "history",
        source_label= label,
    ), embed_text


def _owasp_row_to_chunk(row: dict):
    from prism_mcp.rag.chunker import ChunkDoc
    label = row.get("source_label", f"OWASP {row.get('rule_id','')}")
    text  = (
        f"{label}\n"
        f"Pattern: {row.get('pattern_description','')}\n"
        f"Bad example: {row.get('example_bad','')}\n"
        f"Why bad: {row.get('why_bad','')}\n"
        f"Fix: {row.get('fix','')}"
    )
    return ChunkDoc(
        chunk_id    = ChunkDoc.make_id("cold_start_owasp", text),
        file_path   = "cold_start_owasp",
        text        = text,
        language    = row.get("language", "any"),
        start_line  = 0,
        end_line    = 0,
        symbol_name = row.get("rule_id", ""),
        chunk_type  = "owasp",
        source_label= label,
    ), text


def _smell_row_to_chunk(row: dict):
    from prism_mcp.rag.chunker import ChunkDoc
    label = row.get("source_label", f"Code smell: {row.get('smell_name','')}")
    text  = (
        f"{label}\n"
        f"Category: {row.get('category','')}\n"
        f"Description: {row.get('description','')}\n"
        f"Detection: {row.get('detection_signal','')}\n"
        f"Why bad: {row.get('why_bad','')}\n"
        f"Fix: {row.get('fix','')}"
    )
    return ChunkDoc(
        chunk_id    = ChunkDoc.make_id("cold_start_smells", text),
        file_path   = "cold_start_smells",
        text        = text,
        language    = "any",
        start_line  = 0,
        end_line    = 0,
        symbol_name = row.get("smell_id", ""),
        chunk_type  = "smell",
        source_label= label,
    ), text


# ---------------------------------------------------------------------------
# Batch embed + upsert with progress
# ---------------------------------------------------------------------------

def _embed_and_upsert(
    collection: str,
    chunks_and_texts: list[tuple],
    batch_size: int = 32,
    dry_run: bool = False,
) -> int:
    from prism_mcp.rag.embedder     import embed_texts
    from prism_mcp.rag.vector_store import upsert_chunks

    total   = len(chunks_and_texts)
    upserted = 0
    t0 = time.monotonic()

    for i in range(0, total, batch_size):
        batch = chunks_and_texts[i : i + batch_size]
        chunk_objs  = [c for c, _ in batch]
        embed_inputs = [t for _, t in batch]

        if not dry_run:
            embs = embed_texts(embed_inputs)
            upsert_chunks(collection, chunk_objs, embs)

        upserted += len(batch)
        elapsed   = time.monotonic() - t0
        rate      = upserted / max(elapsed, 0.1)
        eta       = (total - upserted) / max(rate, 0.1)
        pct       = 100 * upserted // total
        print(
            f"\r    {pct:3d}%  {upserted:,}/{total:,}  "
            f"{rate:.0f} rows/s  ETA {eta:.0f}s       ",
            end="", flush=True,
        )

    print()  # newline after progress
    return upserted


# ---------------------------------------------------------------------------
# Individual corpus builders
# ---------------------------------------------------------------------------

def build_owasp(dry_run: bool) -> int:
    path = os.path.join(COLD_START_DIR, "owasp_rules.jsonl")
    rows = _load_jsonl(path)
    if not rows:
        warn(f"owasp_rules.jsonl not found at {path}")
        return 0
    pairs = [_owasp_row_to_chunk(r) for r in rows]
    info(f"OWASP: {len(pairs)} rules → cold_start_owasp")
    n = _embed_and_upsert("cold_start_owasp", pairs, dry_run=dry_run)
    ok(f"cold_start_owasp: {n} chunks upserted")
    return n


def build_smells(dry_run: bool) -> int:
    path = os.path.join(COLD_START_DIR, "code_smells.jsonl")
    rows = _load_jsonl(path)
    if not rows:
        warn(f"code_smells.jsonl not found at {path}")
        return 0
    pairs = [_smell_row_to_chunk(r) for r in rows]
    info(f"Code smells: {len(pairs)} smells → cold_start_smells")
    n = _embed_and_upsert("cold_start_smells", pairs, dry_run=dry_run)
    ok(f"cold_start_smells: {n} chunks upserted")
    return n


def build_reviews(dry_run: bool) -> int:
    path = os.path.join(COLD_START_DIR, "codereviewer_sample.jsonl")
    rows = _load_jsonl(path)
    if not rows:
        warn(f"codereviewer_sample.jsonl not found — run download_datasets.py first")
        return 0
    pairs = [_review_row_to_chunk(r) for r in rows]
    info(f"CodeReviewer: {len(pairs):,} rows → cold_start_reviews")
    if not dry_run:
        warn("Embedding 50k rows via Ollama nomic-embed-text (~15 min on a modern laptop).")
        warn("Set EMBED_BATCH_SIZE=64 in .env to speed this up if you have a fast GPU.")
    n = _embed_and_upsert("cold_start_reviews", pairs, batch_size=32, dry_run=dry_run)
    ok(f"cold_start_reviews: {n:,} chunks upserted")
    return n


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description="PRISM Phase 5 cold-start corpus setup")
    parser.add_argument("--skip-reviews", action="store_true",
                        help="Skip the large CodeReviewer corpus (only load OWASP + smells)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count rows and validate files, but do not embed or upsert")
    args = parser.parse_args()

    print(f"\n{BOLD}PRISM Phase 5 — Cold-Start Corpus Setup{RESET}")
    print("=" * 42)

    if args.dry_run:
        warn("DRY RUN — no embedding or upsert will occur")

    t0 = time.monotonic()

    owasp_n  = build_owasp(args.dry_run)
    smells_n = build_smells(args.dry_run)
    reviews_n = 0 if args.skip_reviews else build_reviews(args.dry_run)

    total_s = time.monotonic() - t0

    print(f"\n{BOLD}Summary{RESET}")
    print(f"  cold_start_owasp:    {owasp_n} chunks")
    print(f"  cold_start_smells:   {smells_n} chunks")
    print(f"  cold_start_reviews:  {reviews_n:,} chunks")
    print(f"  Total time:          {total_s:.1f}s")

    if args.dry_run:
        print(f"\n{YELLOW}{BOLD}  Dry run complete — re-run without --dry-run to actually embed.{RESET}\n")
        return 0

    # Verify cold_start_loaded
    if not args.skip_reviews:
        from prism_mcp.rag.vector_store import corpus_status
        status = corpus_status()
        loaded = status.get("cold_start_loaded", False)
        if loaded:
            print(f"\n{GREEN}{BOLD}  Phase 5 complete — cold_start_loaded: true{RESET}\n")
            return 0
        else:
            col_stats = status.get("collections", {})
            for k in ("cold_start_reviews", "cold_start_owasp", "cold_start_smells"):
                cnt = col_stats.get(k, {}).get("count", 0)
                print(f"  {k}: {cnt} chunks")
            fail("cold_start_loaded is still false — check errors above")
            return 1
    else:
        ok("OWASP + smells loaded. Run without --skip-reviews to load CodeReviewer.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
