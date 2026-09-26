"""
server.py — PRISM MCP Server entrypoint.

Registers all 6 PRISM tools using the mcp 2.x SDK constructor-based API.
Started by Bob as a stdio subprocess via .bob/mcp.json.

Usage (direct):
    python -m prism_mcp.server

Registered tools:
    prism_health_check       — ping Ollama / ChromaDB / GitHub
    prism_analyze_pr         — full end-to-end review of a GitHub PR
    prism_build_corpus       — index repo docs + past reviews into ChromaDB (Phase 4)
    prism_retrieve_context   — retrieve RAG chunks for a diff hunk (Phase 4)
    prism_generate_review    — call Ollama on a single diff hunk
    prism_post_review        — post findings as a GitHub PR review (Phase 8)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# Ensure the repo root is on the path when run as  python -m prism_mcp.server
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from prism_mcp.tools.health   import run_health_check
from prism_mcp.tools.analyze  import run_analyze_pr
from prism_mcp.tools.corpus   import run_build_corpus
from prism_mcp.tools.retrieve import run_retrieve_context
from prism_mcp.tools.generate import run_generate_review
from prism_mcp.tools.post     import run_post_review

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[types.Tool] = [
    types.Tool(
        name="prism_corpus_status",
        description="Return chunk counts for all ChromaDB collections for a given repo.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "GitHub repo owner"},
                "repo":  {"type": "string", "description": "GitHub repo name"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="prism_health_check",
        description="Ping Ollama, ChromaDB, and GitHub token. Returns a structured JSON status object.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="prism_analyze_pr",
        description="Run a full PRISM code review on a GitHub PR. Returns findings, risk score, and summary.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_url":        {"type": "string",  "description": "GitHub PR URL (https://github.com/owner/repo/pull/N)"},
                "post_comments": {"type": "boolean", "description": "If true, post findings as GitHub review (default false)"},
                "language_hint": {"type": "string",  "description": "Override language detection (e.g. 'python')"},
            },
            "required": ["pr_url"],
        },
    ),
    types.Tool(
        name="prism_build_corpus",
        description="Index a repo's style docs and past PR review comments into ChromaDB (Phase 4). Currently a stub.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner":         {"type": "string",  "description": "GitHub repo owner"},
                "repo":          {"type": "string",  "description": "GitHub repo name"},
                "force_rebuild": {"type": "boolean", "description": "Re-index even if already indexed"},
            },
            "required": ["owner", "repo"],
        },
    ),
    types.Tool(
        name="prism_retrieve_context",
        description="Retrieve top-k RAG context chunks for a diff hunk (Phase 4). Currently returns empty array.",
        inputSchema={
            "type": "object",
            "properties": {
                "diff_hunk":  {"type": "string", "description": "Raw unified diff hunk text"},
                "file_path":  {"type": "string", "description": "File path the hunk belongs to"},
                "language":   {"type": "string", "description": "Programming language of the file"},
                "repo_owner": {"type": "string", "description": "GitHub repo owner (for repo-scoped retrieval)"},
                "repo_name":  {"type": "string", "description": "GitHub repo name"},
            },
            "required": ["diff_hunk", "file_path"],
        },
    ),
    types.Tool(
        name="prism_generate_review",
        description="Run Ollama review on a single diff hunk with optional RAG context. Returns a findings JSON array.",
        inputSchema={
            "type": "object",
            "properties": {
                "diff_hunk":      {"type": "string", "description": "Raw unified diff hunk text"},
                "file_path":      {"type": "string", "description": "File path the hunk belongs to"},
                "language":       {"type": "string", "description": "Programming language"},
                "context_chunks": {
                    "type":  "array",
                    "description": "RAG context chunks from prism_retrieve_context (ignored in Phase 2/3)",
                    "items": {"type": "object"},
                },
            },
            "required": ["diff_hunk", "file_path"],
        },
    ),
    types.Tool(
        name="prism_post_review",
        description="Post PRISM findings as a formal GitHub PR review with inline comments (Phase 8). Currently a stub.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_url":   {"type": "string",  "description": "GitHub PR URL"},
                "findings": {"type": "array",   "description": "Findings array from prism_analyze_pr", "items": {"type": "object"}},
                "summary":  {"type": "string",  "description": "PR summary text to use as review body"},
                "dry_run":  {"type": "boolean", "description": "If true (default), validate but do not post"},
            },
            "required": ["pr_url", "findings"],
        },
    ),
]

_TOOL_MAP = {t.name: t for t in TOOLS}

# ---------------------------------------------------------------------------
# Handler functions (sync dispatch wrapped in asyncio executor)
# ---------------------------------------------------------------------------

async def _list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def _call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    name = params.name
    args = dict(params.arguments) if params.arguments else {}
    log.debug("call_tool: %s  args=%s", name, list(args.keys()))

    loop = asyncio.get_running_loop()

    if name == "prism_corpus_status":
        from prism_mcp.rag.vector_store import corpus_status
        result = await loop.run_in_executor(
            None, lambda: corpus_status(args.get("owner", ""), args.get("repo", ""))
        )
    elif name == "prism_health_check":
        result = await loop.run_in_executor(None, run_health_check)
    elif name == "prism_analyze_pr":
        result = await loop.run_in_executor(None, run_analyze_pr, args)
    elif name == "prism_build_corpus":
        result = await loop.run_in_executor(None, run_build_corpus, args)
    elif name == "prism_retrieve_context":
        result = await loop.run_in_executor(None, run_retrieve_context, args)
    elif name == "prism_generate_review":
        result = await loop.run_in_executor(None, run_generate_review, args)
    elif name == "prism_post_review":
        result = await loop.run_in_executor(None, run_post_review, args)
    else:
        result = {"error": f"Unknown tool: {name}"}

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(result, indent=2))]
    )


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

server = Server(
    "prism",
    version="0.3.0",
    description="PRISM — AI Code Review Coach for IBM Bob Hackathon",
    on_list_tools=_list_tools,
    on_call_tool=_call_tool,
)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
