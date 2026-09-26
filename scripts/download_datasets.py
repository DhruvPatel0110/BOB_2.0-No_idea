"""
download_datasets.py — Phase 5 dataset acquisition script.

Downloads and samples the Microsoft CodeReviewer dataset from HuggingFace,
then writes a JSONL sample to data/cold_start/codereviewer_sample.jsonl.

Usage:
    python scripts/download_datasets.py
    python scripts/download_datasets.py --sample-size 50000
    python scripts/download_datasets.py --sample-size 5000   # fast test

Exit codes:
    0 — success
    1 — failure
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HF_DATASET_ID   = "fasterinnerlooper/codereviewer"
HF_CONFIG       = "train_generation"       # fields: oldf, patch, msg, id, y
OUTPUT_DIR      = os.getenv("COLD_START_DIR", "./data/cold_start")
OUTPUT_FILE     = os.path.join(OUTPUT_DIR, "codereviewer_sample.jsonl")
DEFAULT_SAMPLE  = 50_000

# Languages we want to cover evenly (detected from patch content heuristics)
TARGET_LANGS    = ["python", "java", "javascript", "typescript", "go",
                   "ruby", "php", "csharp", "cpp", "other"]
LANG_SLOTS      = DEFAULT_SAMPLE // len(TARGET_LANGS)  # ~5000 per language

# ---------------------------------------------------------------------------
# Language detection from patch text (fast heuristic — no tree-sitter needed)
# ---------------------------------------------------------------------------

_LANG_SIGNALS: list[tuple[str, list[str]]] = [
    ("python",     ["def ", "import ", "    pass", "elif ", "print("]),
    ("java",       ["public class", "void ", "System.out", "import java", "@Override"]),
    ("typescript", ["interface ", ": string", ": number", ": boolean", "export const"]),
    ("javascript", ["function ", "const ", "let ", "require(", "module.exports"]),
    ("go",         ["func ", "package ", ":= ", "fmt.Print", "import ("]),
    ("ruby",       ["def ", "end\n", "require '", "attr_", "puts "]),
    ("php",        ["<?php", "function ", "$", "echo ", "->"]),
    ("csharp",     ["using System", "namespace ", "public void", "Console.Write", "class "]),
    ("cpp",        ["#include", "std::", "cout <<", "int main", "::"]),
]

def _detect_lang(patch: str) -> str:
    scores = {}
    for lang, signals in _LANG_SIGNALS:
        scores[lang] = sum(1 for s in signals if s in patch)
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "other"


# ---------------------------------------------------------------------------
# Main download + sample
# ---------------------------------------------------------------------------

def download_codereviewer(sample_size: int, output_file: str) -> int:
    """
    Stream the CodeReviewer dataset, sample evenly across languages,
    and write to JSONL. Returns the number of rows written.
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' not installed. Run: pip install datasets", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    slots_per_lang  = max(1, sample_size // len(TARGET_LANGS))
    buckets: dict[str, list[dict]] = {lang: [] for lang in TARGET_LANGS}
    total_seen      = 0
    overflow: list[dict] = []   # rows beyond per-lang quota go here for top-up

    print(f"Streaming {HF_DATASET_ID} ({HF_CONFIG})…")
    print(f"Target: {sample_size} rows (~{slots_per_lang} per language)")

    ds = load_dataset(HF_DATASET_ID, HF_CONFIG, split="train", streaming=True)

    for row in ds:
        total_seen += 1
        patch = row.get("patch", "") or ""
        msg   = (row.get("msg", "") or "").strip()

        if not patch.strip() or not msg or len(msg) < 10:
            continue

        lang = _detect_lang(patch)
        item = {
            "diff":         patch,
            "msg":          msg,
            "language":     lang,
            "source_id":    str(row.get("id", "")),
            "source_label": f"CodeReviewer review comment ({lang})",
        }

        if len(buckets.get(lang, [])) < slots_per_lang:
            buckets.setdefault(lang, []).append(item)
        else:
            overflow.append(item)

        # Check if all buckets are full
        collected = sum(len(v) for v in buckets.values())
        if collected >= sample_size:
            break

        if total_seen % 10_000 == 0:
            print(f"  scanned {total_seen:,}  collected {collected:,}…")

    # Top up with overflow if some buckets are under-full
    collected = sum(len(v) for v in buckets.values())
    if collected < sample_size and overflow:
        random.shuffle(overflow)
        needed = sample_size - collected
        extra  = overflow[:needed]
        buckets.setdefault("other", []).extend(extra)

    # Write JSONL
    all_rows = [item for rows in buckets.values() for item in rows]
    random.shuffle(all_rows)

    with open(output_file, "w", encoding="utf-8") as f:
        for item in all_rows:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    lang_counts = {lang: len(rows) for lang, rows in buckets.items() if rows}
    print(f"\nWrote {len(all_rows):,} rows to {output_file}")
    print(f"Language distribution: {lang_counts}")
    return len(all_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description="Download CodeReviewer dataset sample")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE,
                        help=f"Number of rows to sample (default: {DEFAULT_SAMPLE})")
    parser.add_argument("--output-file", default=OUTPUT_FILE,
                        help=f"Output JSONL path (default: {OUTPUT_FILE})")
    args = parser.parse_args()

    print(f"\nPRISM Phase 5 — Dataset Download")
    print(f"{'=' * 40}")

    n = download_codereviewer(args.sample_size, args.output_file)
    if n == 0:
        print("ERROR: No rows written.", file=sys.stderr)
        return 1

    print(f"\nDone. Run next: python scripts/setup_cold_start.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
