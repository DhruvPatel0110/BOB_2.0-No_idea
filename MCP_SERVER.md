# MCP Server Design — PRISM Code Review Coach
## Architecture Reference Document

---

## 1. Overview

PRISM is wired into IBM Bob via an MCP (Model Context Protocol) server. This MCP server is the **single integration layer** between Bob's model calls and all external systems: GitHub, the local vector store, the local Ollama LLM/embedder, and the PRISM review pipeline itself. Bob calls tools; the MCP server executes them.

**Hard constraint: all services are free-tier or self-hosted.**

---

## 2. MCP Server Technology Choice

| Decision | Choice | Rationale |
|---|---|---|
| Transport | **stdio** (local) | Zero infrastructure; Bob launches the server as a subprocess. No auth, no networking. |
| Runtime | **Python 3.11+** with `mcp` SDK (`pip install mcp`) | Official SDK, stdio support, clean `@server.tool()` decorator API |
| Server entrypoint | `prism_mcp/server.py` | Single file registers all tools |
| Config registration | `.bob/mcp.json` (local scope) | Scoped to this workspace only |

The MCP server is started by Bob on-demand using the `stdio` transport:

```json
// .bob/mcp.json
{
  "mcpServers": {
    "prism": {
      "command": "python",
      "args": ["-m", "prism_mcp.server"],
      "env": {
        "PYTHONPATH": "${workspaceFolder}"
      }
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${env:GITHUB_TOKEN}"
      }
    }
  }
}
```

---

## 3. External MCP Servers (Consumed, Not Built)

### 3.1 GitHub MCP Server (`@modelcontextprotocol/server-github`)
- **Source:** Official MCP GitHub server — `npm i -g @modelcontextprotocol/server-github`
- **Auth:** `GITHUB_TOKEN` env var — classic PAT with `repo` + `pull_requests:write` scopes (free GitHub account).
- **Tools used by PRISM:**

| Tool | PRISM Usage |
|---|---|
| `get_pull_request` | Fetch PR metadata (title, body, base/head SHA, author) |
| `get_pull_request_diff` | Fetch the raw unified diff |
| `get_pull_request_files` | List all changed files with addition/deletion counts |
| `get_file_contents` | Fetch full file content at head SHA (for context beyond the diff hunk) |
| `list_pull_requests` | Enumerate past merged PRs for history corpus |
| `get_pull_request_comments` | Fetch all review thread comments from a past PR |
| `create_pull_request_review` | Post the final review (all comments in one batch) |
| `add_pull_request_review_comment` | Add individual inline comment (used for incremental posting) |
| `search_repositories` | Used during corpus setup to discover style/config files |

### 3.2 Filesystem MCP Server (`@modelcontextprotocol/server-filesystem`)
- **Source:** `npm i -g @modelcontextprotocol/server-filesystem`
- **Usage:** Optional — only activated when demoing against a locally cloned repo. Allows Bob to read local files for corpus building without needing GitHub API calls. Restricted to `./data/` and `./repos/` directories.
- **Auth:** None (local only).

---

## 4. PRISM Custom MCP Server — Tool Registry

The custom PRISM MCP server (`prism_mcp/server.py`) exposes these tools to Bob:

---

### Tool: `prism_analyze_pr`

**Purpose:** Full end-to-end review of a GitHub PR. This is the primary entrypoint Bob calls when a user pastes a PR URL.

**Input schema:**
```json
{
  "pr_url": "string — full GitHub PR URL, e.g. https://github.com/owner/repo/pull/42",
  "post_comments": "boolean — if true, post findings as GitHub review comments (default: false)",
  "language_hint": "string | null — override language detection (e.g. 'python', 'typescript')"
}
```

**What it does (internally):**
1. Parses `pr_url` → `{owner, repo, pr_number}`.
2. Calls GitHub MCP `get_pull_request` + `get_pull_request_diff` + `get_pull_request_files`.
3. Calls `prism_build_corpus` internally for the repo (idempotent).
4. Splits diff into per-hunk chunks.
5. For each hunk: calls `prism_retrieve_context` → builds prompt → calls `prism_generate_review`.
6. Aggregates, deduplicates, severity-ranks findings.
7. If `post_comments=true`: calls GitHub MCP `create_pull_request_review` with all findings.
8. Returns structured review result.

**Output schema:**
```json
{
  "pr": { "title": "...", "author": "...", "url": "..." },
  "summary": "One-paragraph plain-English summary of what the PR does",
  "risk_score": 42,
  "findings": [
    {
      "severity": "Blocker|Major|Minor|Nit",
      "category": "security|logic|maintainability|style|tests",
      "file": "src/auth.py",
      "line_start": 42,
      "line_end": 45,
      "title": "SQL injection risk",
      "explanation": "...",
      "suggestion": "...",
      "citation": "OWASP A03:2021"
    }
  ],
  "findings_by_category": { "security": 2, "logic": 1, "style": 4 },
  "findings_by_severity": { "Blocker": 1, "Major": 2, "Minor": 3, "Nit": 2 },
  "comments_posted": false
}
```

---

### Tool: `prism_build_corpus`

**Purpose:** Build or refresh the ChromaDB vector store for a specific repo. Should be called before reviewing a PR from an unfamiliar repo. Idempotent.

**Input schema:**
```json
{
  "owner": "string",
  "repo": "string",
  "force_rebuild": "boolean — drop and rebuild all collections (default: false)",
  "include_history_prs": "integer — how many past merged PRs to index (default: 50, max: 100)"
}
```

**What it does:**
1. Fetches `CONTRIBUTING.md`, `STYLE_GUIDE.md`, `.eslintrc`, `pyproject.toml`, `Makefile` from repo root via GitHub MCP.
2. Fetches last `include_history_prs` merged PRs and their review comments.
3. Chunks, embeds, upserts all into `repo_{owner}_{repo}_style` and `repo_{owner}_{repo}_history` ChromaDB collections.
4. Returns corpus statistics.

**Output schema:**
```json
{
  "status": "built|refreshed|up_to_date",
  "collections": {
    "style_chunks": 34,
    "history_chunks": 892,
    "source_chunks": 0
  },
  "indexed_prs": 50,
  "duration_seconds": 12.4
}
```

---

### Tool: `prism_retrieve_context`

**Purpose:** Given a diff hunk, retrieve the top-k most relevant context chunks from the vector store. Primarily used internally by `prism_analyze_pr`, but exposed for debugging/testing.

**Input schema:**
```json
{
  "diff_hunk": "string — the raw unified diff hunk text",
  "file_path": "string",
  "language": "string",
  "owner": "string",
  "repo": "string",
  "top_k": "integer — number of final context chunks to return (default: 6)"
}
```

**Output schema:**
```json
{
  "context_chunks": [
    {
      "rank": 1,
      "chunk_type": "review_history",
      "text": "...",
      "source_label": "PR #42 comment",
      "score": 0.87
    }
  ],
  "total_tokens": 843
}
```

---

### Tool: `prism_generate_review`

**Purpose:** Generate review findings for a single diff hunk given pre-retrieved context. Calls Ollama/Granite locally. Exposed separately for testing prompt quality without full pipeline overhead.

**Input schema:**
```json
{
  "diff_hunk": "string",
  "file_path": "string",
  "language": "string",
  "context_chunks": "array — output of prism_retrieve_context",
  "symbol_name": "string | null — function/class name if known"
}
```

**Output schema:**
```json
{
  "findings": [ /* array of finding objects, same schema as in prism_analyze_pr */ ],
  "prompt_tokens": 1240,
  "model_used": "granite3-dense:8b"
}
```

---

### Tool: `prism_corpus_status`

**Purpose:** Inspect the current state of the vector store — what repos are indexed, collection sizes, last-updated timestamps. Useful for the dashboard's "corpus health" panel.

**Input schema:**
```json
{
  "owner": "string | null — if null, returns status for all repos",
  "repo": "string | null"
}
```

**Output schema:**
```json
{
  "repos": [
    {
      "owner": "acme",
      "repo": "backend",
      "style_chunks": 34,
      "history_chunks": 892,
      "last_indexed": "2025-09-25T10:32:00Z",
      "pr_count": 50
    }
  ],
  "cold_start_loaded": true,
  "chroma_path": "./data/chroma_db"
}
```

---

### Tool: `prism_post_review`

**Purpose:** Post a previously generated review result to GitHub as a formal PR review. Wraps GitHub MCP `create_pull_request_review` with PRISM's comment formatting.

**Input schema:**
```json
{
  "owner": "string",
  "repo": "string",
  "pr_number": "integer",
  "findings": "array — findings from prism_analyze_pr output",
  "summary": "string — the PR summary paragraph",
  "dry_run": "boolean — if true, format comments but don't post (default: true)"
}
```

**Output schema:**
```json
{
  "posted": false,
  "review_id": null,
  "comment_count": 8,
  "formatted_comments": [ /* preview of what would be posted */ ]
}
```

---

### Tool: `prism_health_check`

**Purpose:** Verify all dependencies are reachable (Ollama, ChromaDB, GitHub token). Bob calls this on workspace startup.

**Input schema:** `{}` (no inputs)

**Output schema:**
```json
{
  "ollama": { "status": "ok|error", "model": "granite3-dense:8b", "embed_model": "nomic-embed-text" },
  "chromadb": { "status": "ok|error", "path": "./data/chroma_db", "collections": 6 },
  "github_token": { "status": "ok|error", "scopes": ["repo", "pull_requests:write"] },
  "hf_token": { "status": "ok|missing", "note": "optional, used as embedding fallback" }
}
```

---

## 5. Server Module Layout

```
prism_mcp/
├── server.py             # MCP server entrypoint — registers all tools
├── tools/
│   ├── analyze_pr.py     # prism_analyze_pr implementation
│   ├── build_corpus.py   # prism_build_corpus implementation
│   ├── retrieve.py       # prism_retrieve_context implementation
│   ├── generate.py       # prism_generate_review implementation
│   ├── post_review.py    # prism_post_review implementation
│   └── health.py         # prism_health_check implementation
├── rag/
│   ├── chunker.py        # tree-sitter based chunker
│   ├── embedder.py       # Ollama / HF fallback embedder
│   ├── vector_store.py   # ChromaDB wrapper
│   └── reranker.py       # cross-encoder reranker
├── github/
│   └── client.py         # thin wrapper around GitHub MCP tool calls
└── utils/
    ├── diff_parser.py    # unified diff → hunk list
    ├── token_counter.py  # tiktoken-based token budget manager
    └── dedup.py          # finding deduplication logic
```

---

## 6. Bob MCP Registration Config

```yaml
# .bob/mcp.yaml (alternative YAML registration)
mcpServers:
  prism:
    command: python
    args: ["-m", "prism_mcp.server"]
    env:
      PYTHONPATH: "."
      CHROMA_PERSIST_DIR: "./data/chroma_db"
      OLLAMA_BASE_URL: "http://localhost:11434"
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
      HF_TOKEN: "${HF_TOKEN}"

  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"

  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "./repos", "./data"]
```

---

## 7. Tool Call Sequence for a PR Review

```
Bob receives: "Review PR https://github.com/acme/backend/pull/99"
    │
    ▼
prism_health_check {}
    │
    ▼
prism_build_corpus { owner:"acme", repo:"backend" }
    │
    ▼
prism_analyze_pr { pr_url:"...", post_comments:false }
    │  (internally calls prism_retrieve_context + prism_generate_review per hunk)
    │
    ▼
[Bob presents findings in dashboard]
    │
    ▼
User confirms: "Post the review"
    │
    ▼
prism_post_review { owner:"acme", repo:"backend", pr_number:99, findings:[...], dry_run:false }
```

---

## 8. Rate Limit Handling

| API | Free Tier Limit | PRISM Handling |
|---|---|---|
| GitHub REST (PAT) | 5000 req/hr | Cached per session; diff + files for a typical PR = ~15 calls |
| GitHub REST (unauthenticated) | 60 req/hr | Always use authenticated PAT |
| HF Inference API | ~1000 req/day | Only used as embedding fallback; batching reduces call count |
| Ollama (local) | Unlimited | Default path for all embedding + generation |

All GitHub API calls are wrapped with a 1-second rate-limit backoff retry (max 3 retries) to handle transient 429s.
