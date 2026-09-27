# PRISM — System Architecture
## Precise Review & Intelligent Scoring Module
### Architecture Reference Document

---

## 1. What PRISM Is

PRISM is the AI code review coach built on IBM Bob for the IBM Bob 2.0 Hackathon. It is not a linter wrapper or a "send diff to ChatGPT" script. It is a structured review pipeline that:

- Retrieves repo-specific context before every review (RAG-grounded, not generic)
- Produces findings that are severity-tagged, category-classified, and cited to real sources
- Posts findings into GitHub's native review interface (line-anchored comments)
- Learns incrementally — merged PR review history feeds back into the corpus

**Name breakdown:** Precise Review & Intelligent Scoring Module.

---

## 2. System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                           │
│  Dashboard (Next.js/React) — diff viewer, findings panel,      │
│  risk score, corpus health, post-to-GitHub button              │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────▼────────────────────────────────────────┐
│                      PRISM BACKEND (FastAPI)                    │
│  /review  /corpus  /health  /findings  /post                   │
└──────┬──────────────────────────────────────────────────────────┘
       │ MCP stdio
┌──────▼──────────────────────────────────────────────────────────┐
│                   PRISM MCP SERVER (Python)                     │
│  prism_analyze_pr | prism_build_corpus | prism_retrieve_context │
│  prism_generate_review | prism_post_review | prism_health_check │
└──────┬──────────────────────┬──────────────────────────────────┘
       │                      │
┌──────▼──────────┐    ┌──────▼──────────────────────────────────┐
│  GitHub MCP     │    │          LOCAL SERVICES                 │
│  Server (npx)   │    │  ChromaDB (./data/chroma_db)            │
│  PAT auth       │    │  Ollama (localhost:11434)               │
│                 │    │    granite3-dense:8b (generation)       │
│  GitHub REST    │    │    nomic-embed-text (embeddings)        │
│  API v3         │    │  HuggingFace Inference API (fallback)   │
└─────────────────┘    └─────────────────────────────────────────┘
```

---

## 3. Technology Stack (All Free)

| Layer | Technology | Free? |
|---|---|---|
| UI framework | Next.js 14 (App Router) + Tailwind CSS | ✅ Open-source |
| UI diff viewer | `react-diff-viewer-continued` | ✅ MIT |
| Backend API | FastAPI (Python 3.11) | ✅ Open-source |
| MCP server | Python `mcp` SDK (stdio) | ✅ Open-source |
| LLM (primary) | IBM Granite via Bob (hackathon access) | ✅ Provided |
| LLM (fallback) | `ollama run granite3-dense:8b` | ✅ Free / local |
| Embeddings (primary) | Ollama `nomic-embed-text` | ✅ Free / local |
| Embeddings (fallback) | HuggingFace Inference API (free tier) | ✅ Free tier |
| Vector store | ChromaDB (local persistent) | ✅ Open-source |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` | ✅ Local / free |
| Code chunker | `tree-sitter` | ✅ Open-source |
| GitHub integration | `@modelcontextprotocol/server-github` | ✅ MIT / free PAT |
| Token counting | `tiktoken` | ✅ Open-source |

**No paid APIs are used. GitHub Token = free with any GitHub account. HF Token = free with any HuggingFace account.**

---

## 4. Directory Structure

```
prism/                          # project root
├── approach_plan.md
├── RAG_PIPELINE.md
├── MCP_SERVER.md
├── PRISM_ARCHITECTURE.md       # this file
├── DATASETS.md
├── .env.example
├── .env                        # local secrets (gitignored)
│
├── prism_mcp/                  # MCP server (Python)
│   ├── server.py
│   ├── tools/
│   │   ├── analyze_pr.py
│   │   ├── build_corpus.py
│   │   ├── retrieve.py
│   │   ├── generate.py
│   │   ├── post_review.py
│   │   └── health.py
│   ├── rag/
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── vector_store.py
│   │   └── reranker.py
│   ├── github/
│   │   └── client.py
│   └── utils/
│       ├── diff_parser.py
│       ├── token_counter.py
│       └── dedup.py
│
├── backend/                    # FastAPI backend
│   ├── main.py
│   ├── routers/
│   │   ├── review.py
│   │   ├── corpus.py
│   │   └── health.py
│   └── models/
│       └── schemas.py
│
├── frontend/                   # Next.js dashboard
│   ├── app/
│   │   ├── page.tsx            # PR URL input + submit
│   │   ├── review/[id]/page.tsx # findings view
│   │   └── layout.tsx
│   └── components/
│       ├── DiffViewer.tsx
│       ├── FindingsPanel.tsx
│       ├── RiskScore.tsx
│       └── CorpusStatus.tsx
│
├── data/
│   ├── chroma_db/              # ChromaDB persistence (gitignored)
│   ├── cold_start/             # pre-built cold-start corpus files
│   │   ├── owasp_rules.jsonl
│   │   └── code_smells.jsonl
│   └── datasets/               # downloaded dataset files (gitignored)
│
├── scripts/
│   ├── setup_cold_start.py     # build cold-start corpus once
│   ├── download_datasets.py    # pull CodeReviewer sample from HuggingFace
│   └── test_review.py          # smoke test: review a single PR
│
├── .bob/
│   └── mcp.json                # Bob MCP server registration
│
├── requirements.txt            # Python dependencies
├── package.json                # Node dependencies (frontend + MCP npm packages)
└── docker-compose.yml          # optional: run Ollama in container
```

---

## 5. Core Review Pipeline — Step-by-Step

### Step 1: PR Ingestion

**Trigger:** User submits a GitHub PR URL in the dashboard or Bob chat.

**Operations:**
1. Parse URL → `{owner, repo, pr_number}`.
2. GitHub MCP `get_pull_request` → fetch title, body, base SHA, head SHA, author, labels.
3. GitHub MCP `get_pull_request_diff` → raw unified diff string.
4. GitHub MCP `get_pull_request_files` → list of `{filename, status, additions, deletions, patch}`.
5. For each changed file: GitHub MCP `get_file_contents` at head SHA → full file text (needed for function-level context beyond the hunk).
6. Store all fetched data in a session object keyed by `{owner}/{repo}#{pr_number}`.

**Output:** Structured PR session object.

---

### Step 2: Corpus Warm-Up (Idempotent)

**Trigger:** Called before Step 3 if corpus for `{owner/repo}` is stale or absent.

**Operations:**
1. Check ChromaDB: does `repo_{owner}_{repo}_style` exist and was it indexed within the last 24 hours?
2. If stale/absent: call `prism_build_corpus` (see MCP_SERVER.md §4 for full details).
3. Cold-start corpus (`cold_start_reviews`, `cold_start_owasp`, `cold_start_smells`) is loaded once at server start and persists across sessions.

---

### Step 3: Diff Chunking

**Operations:**
1. Parse the unified diff into individual hunks using `diff_parser.py`.
2. Each hunk is a `{file_path, hunk_header, lines, language}` object.
3. Language detected from file extension; overridden by `language_hint` if provided.
4. Hunks longer than 1500 tokens are split into overlapping 800-token sub-hunks (100-token overlap).
5. Attach the 30 lines of full-file context surrounding each hunk's start line (pre-fetched in Step 1).

**Output:** Ordered list of `HunkChunk` objects ready for review.

---

### Step 4: Per-Hunk Review Loop

For each `HunkChunk`:

**4a. Context Retrieval**
- Call `prism_retrieve_context` with the hunk text + file path + language + repo.
- Returns top-6 reranked context chunks (see RAG_PIPELINE.md §6 for full retrieval logic).

**4b. Prompt Assembly**
- Insert system prompt (PRISM reviewer persona).
- Insert retrieved context block (capped at 1500 tokens).
- Insert diff hunk + surrounding file context.
- Total prompt budget: ≤3800 tokens.

**4c. Generation**
- Call Ollama `granite3-dense:8b` via `http://localhost:11434/api/generate`.
- Parse JSON array from response.
- If JSON parse fails: retry once with an explicit "output valid JSON only" instruction appended.

**4d. Finding Normalisation**
- Validate each finding has required fields.
- Map `line_start`/`line_end` to GitHub diff position offsets.
- Attach `hunk_id`, `file_path`, `language` to each finding.

---

### Step 5: PR Summary Generation

After all hunks are reviewed, a separate summary prompt is sent:

```
Given these findings from a PR review, write:
1. A one-paragraph plain-English summary of what this PR does.
2. A bullet list of the top 3–5 risks or concerns.

PR title: {title}
PR description: {body}
Files changed: {file_list}
Finding summary: {findings_by_category_and_severity}
```

This runs once per PR, not per hunk. Output is the `summary` field in the review result.

---

### Step 6: Aggregation & Deduplication

- Merge findings from all hunks.
- Deduplicate: same `(file, category)` + line within 5 = keep higher severity.
- Sort: Blockers first, then by file path, then by line number.
- Compute risk score: `min(100, Blockers×10 + Majors×3 + Minors×1 + Nits×0.2)`.
- Group into `findings_by_category` and `findings_by_severity` for dashboard widgets.

---

### Step 7: Dashboard Display

The FastAPI backend serves the structured review result to the Next.js frontend:

**Dashboard panels:**
1. **PR Header** — title, author, link, base → head branch.
2. **Risk Score** — circular gauge, colour-coded (green < 20, yellow 20–50, red > 50).
3. **Findings Breakdown** — bar chart of severity counts; pie chart of category counts.
4. **Diff Viewer** — full unified diff with inline finding annotations on affected lines. Clicking a finding annotation expands the explanation + suggestion + citation.
5. **Finding List** — sortable/filterable table of all findings.
6. **Corpus Status** — mini panel showing which collections are loaded and when last indexed.
7. **Post to GitHub** — button that calls `prism_post_review` with `dry_run=false`.

---

### Step 8: GitHub Comment Posting

**Trigger:** User clicks "Post to GitHub" in the dashboard (or passes `post_comments=true` to `prism_analyze_pr`).

**Format of a posted review comment:**
```
**[Major] Potential null dereference — `user.profile` can be undefined**

`user.profile.name` is accessed on line 47 without a null check. If `user` exists but has
no `profile` (e.g., newly created accounts), this throws a TypeError at runtime.

**Suggested fix:**
```js
const name = user?.profile?.name ?? 'Unknown';
```

📎 *Similar issue flagged in PR #38 | PRISM PRISM v0.1*
```

**Mechanism:**
- All findings posted as a single `create_pull_request_review` call (batch), not individual `add_pull_request_review_comment` calls, to avoid rate limit noise and appear as one reviewer.
- Review event type: `COMMENT` (not `APPROVE` or `REQUEST_CHANGES` — keeps it non-blocking for demos).
- Review body = the PR summary paragraph.

---

## 6. PRISM's Differentiator: Convention-Aware Feedback

This is the feature that separates PRISM from "linter + LLM":

**Generic AI output:**
> "Consider adding null checks here."

**PRISM output:**
> "This project's `CONTRIBUTING.md §4.2` requires null checks on all API response fields before access. Similar feedback was left in PR #38 by @senior-dev. Use optional chaining: `user?.profile?.name`."

The citation mechanism works as follows:
1. When a retrieved chunk comes from `repo_*_style` (style guide), the `source_label` is `CONTRIBUTING.md §{heading}`.
2. When it comes from `repo_*_history` (past PR), the `source_label` is `PR #{pr_number} comment (by @{author})`.
3. When it comes from cold-start OWASP, the `source_label` is `OWASP {rule_id}:{year}`.
4. When it comes from cold-start smells, the `source_label` is `Code smell: {smell_name}`.

The citation is appended to the finding's `explanation` field and rendered in the GitHub comment.

---

## 7. Incremental Learning

After a PR is merged, PRISM can ingest its review comments back into the corpus:

**Trigger:** Bob hook on `prism_post_review` success, or manual call to `prism_build_corpus` with `force_rebuild=false`.

**What gets indexed:**
- The review comments PRISM posted (so they become precedent for future reviews of the same patterns).
- Any human reviewer comments on the same PR (fetched via GitHub MCP after the PR is merged).

**Effect:** Over time, the `repo_*_history` collection grows richer, and PRISM's citations become more specific to the team's actual review culture.

---

## 8. Failure Modes & Fallbacks

| Failure | Fallback |
|---|---|
| Ollama unreachable | Fall back to HuggingFace Inference API for embeddings; generation blocked with clear error |
| GitHub rate limit hit | Cache PR data for session; retry with exponential backoff |
| ChromaDB collection empty | Use cold-start corpus only; note absence of repo-specific context in review output |
| JSON parse failure from LLM | Retry once with stricter JSON-only instruction; if still fails, return raw text as a single Nit-severity finding |
| PR diff too large (>10k lines) | Review only the top 20 most-changed files; surface a warning in the dashboard |
| HuggingFace free tier exhausted | Log warning; skip reranking; use raw cosine similarity ranking |

---

## 9. Security & Data Handling

- **No PR diffs are stored permanently.** Session data lives in memory and is cleared after the review result is delivered.
- **ChromaDB stores only:** embedded chunks of style docs, config files, and review comment text (no raw secrets/code).
- **GitHub token** is read from env var; never logged; never sent outside the MCP call to GitHub's own servers.
- **Demo safety:** `prism_post_review` defaults to `dry_run=true`. Live posting is only enabled for the designated demo repo (`DEMO_REPO_OWNER/DEMO_REPO_NAME` in `.env`).

---

## 10. Setup Checklist (First-Time)

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull granite3-dense:8b
ollama pull nomic-embed-text

# 2. Python environment
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# 3. Node / MCP packages
npm install
npx -y @modelcontextprotocol/server-github --version  # verify install

# 4. Environment
cp .env.example .env
# edit .env — add GITHUB_TOKEN and optionally HF_TOKEN

# 5. Cold-start corpus
python scripts/setup_cold_start.py

# 6. Smoke test
python scripts/test_review.py --pr https://github.com/your/repo/pull/1

# 7. Start services
uvicorn backend.main:app --reload &   # FastAPI backend
cd frontend && npm run dev             # Next.js dashboard
```

---

## 11. Demo Script (for Judges)

1. Open dashboard at `http://localhost:3000`.
2. Paste a PR URL from the designated demo repo.
3. Click "Analyze PR" → watch the live progress (per-hunk status shown as it runs).
4. Review the dashboard: risk score, findings by category, inline diff annotations.
5. Click a finding annotation to expand its explanation + citation.
6. Click "Post to GitHub" → show the PR on GitHub with PRISM's review comments appearing as a formal review.
7. Highlight one comment that cites a past PR: "This project's CONTRIBUTING.md requires X. Similar issue flagged in PR #7."

**Key judge moments:**
- The citation ("per CONTRIBUTING.md §3") demonstrates RAG grounding, not generic LLM output.
- The GitHub review integration demonstrates real workflow integration, not a side dashboard.
- The risk score + severity breakdown is scannable in 3 seconds — no wall of text.
