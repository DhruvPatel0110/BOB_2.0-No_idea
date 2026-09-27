# Datasets — PRISM Code Review Coach
## Dataset Sourcing, Licensing & Ingestion Reference

---

## 1. Overview

PRISM uses datasets at two layers:
1. **Cold-start corpus** — pre-built vector store that gives PRISM meaningful context on any repo, even one with zero review history.
2. **Offline evaluation** — used to measure whether PRISM's generated findings match real human reviewer comments (not used at runtime).

**All datasets listed here are free to use (CC, MIT, Apache 2.0, or research-use licenses).**

---

## 2. Primary Dataset: Microsoft CodeReviewer

| Property | Value |
|---|---|
| Name | CodeReviewer |
| Publisher | Microsoft Research |
| Paper | https://arxiv.org/abs/2203.09095 |
| GitHub | https://github.com/microsoft/CodeBERT/tree/master/CodeReviewer |
| HuggingFace | `microsoft/codereview` (if published) / raw download from GitHub |
| License | MIT |
| Size | ~150k (diff, review_comment) pairs across 9 languages |
| Languages | Python, Java, JavaScript, TypeScript, Go, Ruby, PHP, C, C++ |

### What it contains
- `diff`: the code change (unified diff format)
- `msg`: the reviewer's comment text
- `label`: quality label (some splits include accept/reject)
- Three tasks: change quality estimation, review comment generation, code refinement

### How PRISM uses it

**Cold-start corpus ingestion (scripts/setup_cold_start.py):**
1. Download the dataset split from HuggingFace Hub:
   ```python
   from datasets import load_dataset
   ds = load_dataset("microsoft/codereview", split="train")
   ```
   If the HuggingFace dataset isn't published, download the raw TSV files from GitHub and parse manually.
2. Sample 50,000 rows evenly across languages (≈5,555 per language) to keep index size manageable.
3. For each row: create a `(diff, msg)` pair chunk.
   - **Embedded text:** the `diff` field (what gets queried against).
   - **Payload metadata:** `msg` (the review comment — injected into the prompt as a "similar past comment" context item).
4. Upsert into ChromaDB collection `cold_start_reviews`.

**Offline evaluation:**
- Hold out 5,000 rows (stratified by language) as evaluation set.
- For each held-out `diff`, run PRISM's `prism_generate_review` and compare output to the real `msg` using BERTScore (free, local via `bert-score` pip package).
- Target: BERTScore F1 > 0.70 on the held-out set.

---

## 3. Supplementary Dataset: CodeSearchNet

| Property | Value |
|---|---|
| Name | CodeSearchNet |
| Publisher | GitHub / Hugging Face |
| HuggingFace | `code_search_net` |
| License | Various (MIT, Apache 2.0 per repo) |
| Size | 2M (code, docstring) pairs across 6 languages |
| Languages | Python, Java, JavaScript, PHP, Go, Ruby |

### How PRISM uses it
- **Not** used for review comment generation.
- Used for source file chunking benchmarks: the `func_code_string` field provides a large corpus of real functions to test tree-sitter chunking accuracy (does the chunker correctly identify function boundaries?).
- Optional: embed a 10k-row sample as additional source-code context for the `cold_start_reviews` collection, helping retrieval when the hunk references a pattern from a well-known library.

---

## 4. Supplementary Dataset: Methods2Test (Optional, Java-only)

| Property | Value |
|---|---|
| Name | Methods2Test |
| Publisher | Microsoft |
| Paper | https://arxiv.org/abs/2203.12776 |
| HuggingFace | `andstor/methods2test_small` |
| License | MIT |
| Size | 780k test ↔ focal method pairs (small version: ~80k) |
| Language | Java only |

### How PRISM uses it
- Powers the **"missing test coverage"** finding category for Java PRs.
- For a changed Java method, retrieve similar focal methods from this dataset and check whether a corresponding test pattern exists.
- Only loaded into ChromaDB (`cold_start_tests`) if the PR being reviewed contains Java files.
- Low priority — implement only after core review pipeline is working.

---

## 5. Hand-Curated Corpus: OWASP Rules

| Property | Value |
|---|---|
| Source | OWASP Top 10 (2021) — https://owasp.org/www-project-top-ten/ |
| License | CC BY-SA 4.0 (free to use with attribution) |
| Format | Hand-written JSONL (one rule per line) |
| File | `data/cold_start/owasp_rules.jsonl` |
| Size | 10 rules × 3–4 language-specific patterns each ≈ 40 chunks |

### Schema (each line):
```json
{
  "rule_id": "A03:2021",
  "rule_name": "Injection",
  "language": "python",
  "pattern_description": "String concatenation in SQL query construction",
  "example_bad": "query = 'SELECT * FROM users WHERE id=' + user_id",
  "why_bad": "Allows attacker to inject arbitrary SQL via user_id input.",
  "fix": "Use parameterised queries: cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))",
  "source_label": "OWASP A03:2021 — Injection"
}
```

### OWASP rules to cover (minimum viable set):
- A01: Broken Access Control → missing auth checks
- A02: Cryptographic Failures → hardcoded secrets, weak hashing (MD5/SHA1)
- A03: Injection → SQL injection, command injection, XSS
- A05: Security Misconfiguration → debug mode on, open CORS, default credentials
- A06: Vulnerable Components → known-bad version patterns in `requirements.txt` / `package.json`
- A07: Identification and Authentication Failures → session token not invalidated, weak password check
- A08: Software and Data Integrity → no signature verification on downloads/updates
- A10: Server-Side Request Forgery → unvalidated URL in fetch/requests call

---

## 6. Hand-Curated Corpus: Code Smell Catalog

| Property | Value |
|---|---|
| Source | Refactoring.Guru (https://refactoring.guru/refactoring/smells) |
| License | Content is freely accessible; snippets summarised in own words |
| Format | Hand-written JSONL |
| File | `data/cold_start/code_smells.jsonl` |
| Size | ~40 smell definitions |

### Schema (each line):
```json
{
  "smell_id": "long_method",
  "smell_name": "Long Method",
  "category": "maintainability",
  "description": "A method that is too long to understand at a glance. Usually exceeds 20–30 lines.",
  "detection_signal": "Function body > 40 lines, or cyclomatic complexity > 10",
  "why_bad": "Hard to test, understand, and change without side effects.",
  "fix": "Extract sub-functions. Each function should do one thing.",
  "source_label": "Code smell: Long Method"
}
```

### Smells to cover (minimum viable set):
**Bloaters:** Long Method, Large Class, Long Parameter List, Data Clumps
**Object-Orientation Abusers:** Switch Statements, Temporary Field, Refused Bequest
**Change Preventers:** Divergent Change, Shotgun Surgery, Parallel Inheritance Hierarchies
**Dispensables:** Dead Code, Duplicate Code, Speculative Generality, Lazy Class
**Couplers:** Feature Envy, Inappropriate Intimacy, Message Chains

---

## 7. Live Data (Best for Demo)

For the actual hackathon demo, live PR data pulled via GitHub API is far more impressive than static dataset examples. The datasets above are context and grounding material — the demo's input is always a real (or sandbox) PR.

**Recommended demo repo setup:**
1. Create a GitHub repo named `prism-demo-repo` (public or private, your account).
2. Pre-populate it with 5–10 merged PRs that have real review comments (can be fabricated/staged).
3. These staged PRs cover all finding categories: one with a SQL injection bug, one with a missing null check, one violating a `CONTRIBUTING.md` rule, one missing tests.
4. Open one live PR during the demo that touches multiple files — PRISM reviews it live.

This staged-repo approach was used successfully by TestForge Pro at the May 2026 hackathon and is the recommended demo safety pattern.

---

## 8. Dataset Download & Setup Script

`scripts/download_datasets.py` handles all dataset acquisition:

```
Usage: python scripts/download_datasets.py [--dataset all|codereviewer|methods2test|codesearchnet]
                                            [--sample-size 50000]
                                            [--output-dir ./data/datasets]
```

**What it does:**
1. Checks HuggingFace Hub for each dataset (uses `datasets` library — free, no token required for public datasets).
2. Downloads and caches to `./data/datasets/` (gitignored).
3. Samples to the configured size and writes `{dataset}_sample.jsonl` to `./data/cold_start/`.

`scripts/setup_cold_start.py` then reads those JSONL files, chunks + embeds them, and upserts into ChromaDB. Run order:

```bash
python scripts/download_datasets.py --dataset codereviewer
python scripts/setup_cold_start.py
```

Expected runtime: ~15 minutes for full cold-start setup on a modern laptop (most time is embedding 50k rows with `nomic-embed-text`).

---

## 9. Dataset Sizes & ChromaDB Footprint Estimates

| Collection | Source | Chunk Count | Approx Size (768-dim float32) |
|---|---|---|---|
| `cold_start_reviews` | CodeReviewer sample | 50,000 | ~150 MB |
| `cold_start_owasp` | Hand-curated | 40 | ~0.1 MB |
| `cold_start_smells` | Hand-curated | 40 | ~0.1 MB |
| `cold_start_tests` | Methods2Test (optional) | 10,000 | ~30 MB |
| `repo_*_style` | Per-repo style docs | ~30–100 | ~0.3 MB |
| `repo_*_history` | Per-repo PR comments | ~100–2000 | ~6 MB |
| **Total (minimum viable)** | | ~50,210 | **~180 MB** |

This fits comfortably on any development machine with >2 GB free disk space.

---

## 10. Licensing Summary

| Dataset | License | Commercial Use | Attribution Required |
|---|---|---|---|
| Microsoft CodeReviewer | MIT | ✅ | No (MIT) |
| CodeSearchNet | Apache 2.0 | ✅ | No |
| Methods2Test | MIT | ✅ | No |
| OWASP Top 10 (summaries) | CC BY-SA 4.0 | ✅ | Yes — "Source: OWASP" |
| Refactoring.Guru (paraphrased) | Own words | ✅ | Recommended |

All datasets are safe to use for the hackathon and for any derivative work.
