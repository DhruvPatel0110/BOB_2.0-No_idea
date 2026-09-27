# RAG Pipeline — PRISM Code Review Coach
## Architecture Reference Document

---

## 1. Overview

PRISM's RAG (Retrieval-Augmented Generation) pipeline grounds every review comment in real evidence — the specific repo's conventions, its past review threads, and authoritative code-review patterns from public datasets — rather than producing generic LLM opinions. This document defines every layer of that pipeline, the free tooling used at each layer, and the data flow from raw corpus to final injected prompt context.

**Hard constraint: 100% free-tier / open-source tooling only.**

---

## 2. Free Stack Selection

| Layer | Chosen Tool | Why Free / Why This One |
|---|---|---|
| Embedding model | `nomic-embed-text` via Ollama | Runs locally, no API cost, 768-dim, strong on code |
| Fallback embedding | `sentence-transformers/all-MiniLM-L6-v2` via HuggingFace Inference API | Free tier (no credit card), 384-dim, fast |
| Vector store | ChromaDB (local persistent) | Fully local, no server, Python-native, free |
| LLM for review generation | IBM Granite 3.x via IBM Bob (the hackathon's provided model) | Provided as part of hackathon access |
| Fallback LLM | `ollama run granite3-dense:8b` locally | Free, same model family |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` via `sentence-transformers` | Local, CPU-friendly, free |
| Chunking/parsing | `tree-sitter` (language-aware AST chunker) | Free, open-source |
| Dataset hosting | HuggingFace Hub (free datasets) + local disk | Free tier |

---

## 3. Corpus Sources

### 3.1 Per-Repo Corpus (dynamic, built at review time)

These are fetched live for the repo being reviewed:

1. **`CONTRIBUTING.md` / `STYLE_GUIDE.md`** — pulled from the repo root via GitHub MCP tool `get_file_contents`. If absent, skip.
2. **`.eslintrc` / `pyproject.toml` / `checkstyle.xml` / etc.** — linter configs that encode style rules. Fetched and serialised as text for embedding.
3. **Past merged PR review comments** — fetched via GitHub MCP `list_pull_requests` (state=closed, merged=true) + `get_pull_request_comments`. Last 100 merged PRs, comment body + file path + line context stored as `(comment_text, file_path, diff_hunk)` triples.
4. **Existing source files for changed paths** — the full file content of every file touched by the PR (not just the diff hunk). Provides function-level context for the review.

### 3.2 Cold-Start Corpus (static, pre-built once)

Used when a repo has no history (new projects, first PR). Loaded from:

1. **Microsoft CodeReviewer dataset** — sampled subset of review comment ↔ diff hunk pairs from HuggingFace: `microsoft/codereview` (or the raw files at `microsoft/CodeBERT/CodeReviewer`). We embed the `(diff_hunk, review_comment)` pairs. ~50k samples sampled evenly across languages for manageable size.
2. **Curated OWASP rule summaries** — hand-written or scraped short paragraphs for OWASP Top 10 (A01–A10), each tagged with language patterns that trigger the rule. Embedded as individual chunks.
3. **Common code smell catalog** — drawn from Refactoring.Guru "code smells" pages (freely accessible). ~80 smell definitions, each a 2–4 sentence chunk.

### 3.3 Corpus Priority at Retrieval

```
Repo style guide > Repo past review comments > Repo source files > Cold-start dataset > OWASP/smell catalog
```

Higher-priority sources are retrieved first and fill the context window budget before lower-priority sources are included.

---

## 4. Chunking Strategy

All chunking is language-aware via `tree-sitter`. The goal is semantically coherent chunks, not fixed-token windows.

### 4.1 Source Code Files
- Parse with `tree-sitter` for the file's language.
- Chunk at **function / method / class body** level.
- If a node exceeds 512 tokens, split on inner `block` or `statement` nodes recursively.
- Minimum chunk size: 30 tokens (skip trivial one-liners unless they're the full function).
- Attach metadata: `{file_path, start_line, end_line, language, symbol_name, chunk_type: "source"}`.

### 4.2 Markdown / Config / Docs
- Split on heading boundaries (`##`, `###`).
- Hard cap: 400 tokens per chunk with 50-token overlap.
- Metadata: `{source_file, section_heading, chunk_type: "doc"}`.

### 4.3 PR Review Comment Triples
- Each `(diff_hunk, review_comment)` pair is one chunk.
- Store the diff hunk as the chunk text (what gets embedded for retrieval), store the review_comment as payload metadata (what gets injected into the prompt).
- Metadata: `{pr_number, file_path, line, review_comment, chunk_type: "review_history"}`.

### 4.4 Cold-Start Dataset Entries
- Same triple structure as 4.3.
- Pre-chunked — the dataset already provides `(diff, comment)` pairs.
- Metadata: `{dataset: "codereviewer", language, chunk_type: "cold_start"}`.

---

## 5. Embedding & Indexing

### 5.1 Embedding Model

**Primary:** `nomic-embed-text` served via Ollama (`ollama pull nomic-embed-text`).
- Endpoint: `http://localhost:11434/api/embeddings`
- Dimension: 768
- Batch size: 32 chunks per request to stay within Ollama's default limits.

**Fallback:** HuggingFace Inference API — `sentence-transformers/all-MiniLM-L6-v2`.
- Endpoint: `https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2`
- Free tier: 1000 req/day for the free HF token.
- Dimension: 384.

Fallback is selected automatically if the Ollama server is unreachable.

### 5.2 Vector Store Layout (ChromaDB)

ChromaDB persists to `./data/chroma_db/` and uses the following collections:

| Collection Name | Contents | Embedding Dim |
|---|---|---|
| `repo_{owner}_{repo}_style` | Style guide + linter config chunks | 768 |
| `repo_{owner}_{repo}_history` | Past PR review comment triples | 768 |
| `repo_{owner}_{repo}_source` | Repo source file chunks (changed files) | 768 |
| `cold_start_reviews` | CodeReviewer dataset sample | 768 |
| `cold_start_owasp` | OWASP rule summaries | 768 |
| `cold_start_smells` | Code smell catalog | 768 |

Repo-specific collections are created/updated lazily when a PR from that repo is first reviewed. They are invalidated and rebuilt if the repo's default branch has advanced more than 50 commits since last index.

### 5.3 Indexing Pipeline

```
raw_corpus
    │
    ├─► chunk() ──► embed() ──► upsert into ChromaDB collection
    │                              (doc_id = sha256(chunk_text), so re-indexing is idempotent)
    │
    └─► metadata stored as ChromaDB document metadata (not embedded)
```

Upsert by content hash ensures incremental re-indexing is safe and cheap.

---

## 6. Query & Retrieval

### 6.1 Query Construction

For each diff hunk being reviewed, the retrieval query is constructed as:

```
query = f"""
{language} code change:
{diff_hunk}

Context: file {file_path}, function {symbol_name_if_known}
"""
```

The query is embedded with the same model used for indexing.

### 6.2 Retrieval Strategy — Hybrid

**Step 1 — Dense retrieval (vector similarity):**
- Query each relevant collection, `top_k=10` per collection.
- Use ChromaDB's cosine distance metric.

**Step 2 — Reranking:**
- Concatenate all retrieved chunks (up to 60 candidates).
- Feed each `(query, chunk_text)` pair through `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker.
- Sort by reranker score descending.
- Keep top 6 chunks for prompt injection (fits within a 4k-token context budget alongside the diff and system prompt).

**Step 3 — Priority filtering:**
- If any chunk is from `repo_*_style` or `repo_*_history` (repo-specific), those are guaranteed a slot in the top 6 even if reranker score is lower than a cold-start chunk. Up to 3 slots reserved for repo-specific context.

### 6.3 Retrieved Context Schema

Each retrieved context item passed to the prompt:

```json
{
  "rank": 1,
  "chunk_type": "review_history | style | source | cold_start_reviews | owasp | smell",
  "text": "...",
  "source_label": "CONTRIBUTING.md §3.2 | PR #42 comment | OWASP A03:2021",
  "score": 0.87
}
```

The `source_label` is injected into the review comment itself so Bob can cite it ("per CONTRIBUTING.md §3.2" / "similar issue flagged in PR #42").

---

## 7. Prompt Injection

### 7.1 Review Prompt Template

```
SYSTEM:
You are PRISM, a precise code review assistant. You review diffs and produce findings grounded in the provided context.

For each finding, output exactly this JSON structure:
{
  "severity": "Blocker|Major|Minor|Nit",
  "category": "security|logic|maintainability|style|tests",
  "line_start": <int>,
  "line_end": <int>,
  "title": "<short title>",
  "explanation": "<why this matters>",
  "suggestion": "<concrete fix>",
  "citation": "<source_label from context, or null>"
}

Output a JSON array. If no issues found, output [].

CONTEXT (grounding evidence):
---
{retrieved_context_block}
---

USER:
Review this diff. File: {file_path}. Language: {language}.

```diff
{diff_hunk}
```
```

### 7.2 Context Budget Management

The retrieved context block is capped at **1500 tokens**. If all 6 retrieved chunks together exceed this, chunks are truncated from the lowest-ranked one first, preserving full text for top-ranked chunks.

Total prompt budget (for Granite models):
- System prompt: ~300 tokens
- Context block: ≤1500 tokens  
- Diff hunk: ≤1500 tokens  
- Output space: ~500 tokens  
- **Total: ~3800 tokens** — stays within Granite 3.x 4k effective prompt window.

For large hunks (>1500 tokens), the hunk is sub-chunked into overlapping 800-token windows with 100-token overlap, each reviewed independently, then findings merged and deduplicated.

---

## 8. Post-Processing

### 8.1 Deduplication
- Two findings are duplicate if they share the same `(file_path, category)` and their `line_start` values are within 5 lines of each other.
- Keep the higher-severity one; discard the lower.

### 8.2 Severity Aggregation
- PR-level risk score = weighted sum: Blocker×10 + Major×3 + Minor×1 + Nit×0.
- Normalised to 0–100 for the dashboard display.

### 8.3 Comment Anchoring
- GitHub review comments require a `position` (line offset in the diff). PRISM maps `line_start` from the finding back to the diff position using a simple diff-hunk offset table built during ingestion.

---

## 9. Corpus Update Schedule

| Trigger | Action |
|---|---|
| New PR opened for a repo | Re-fetch style docs and linter configs (cheap, small files) |
| PR merged into default branch | Append its review comments to `repo_*_history` collection (incremental upsert) |
| Repo hasn't been reviewed in >30 days | Full re-index of source collection for changed files |
| Manual reset command | Drop and rebuild all repo-specific collections |

---

## 10. Data Flow Diagram

```
GitHub PR URL
      │
      ▼
[MCP: fetch diff + file contents + past review threads]
      │
      ├──► [Chunker] ──► [Embedder] ──► [ChromaDB upsert] (corpus update)
      │
      └──► For each diff hunk:
                │
                ▼
           [Query Builder]
                │
                ▼
           [ChromaDB dense retrieval] ──► [Cross-encoder reranker]
                │
                ▼
           [Top-6 context chunks]
                │
                ▼
           [Prompt Builder] ◄── [diff hunk + file metadata]
                │
                ▼
           [IBM Granite via Bob / Ollama fallback]
                │
                ▼
           [JSON findings parser]
                │
                ▼
           [Deduplicator + severity aggregator]
                │
                ▼
           [Dashboard render] + [MCP: post GitHub review comments]
```
