"""
chunker.py — tree-sitter AST chunker for Phase 4 RAG corpus.

Splits source files at function/method/class boundaries. Falls back to
heading-boundary splits for Markdown/config and fixed-size line chunks
for any other file type. Each chunk gets metadata so retrieval can cite it.

Public API:
    chunk_source_file(file_path, text, language, *, max_tokens)
      → list[ChunkDoc]
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Chunk data model
# ---------------------------------------------------------------------------

@dataclass
class ChunkDoc:
    """One embeddable chunk from the corpus."""
    chunk_id:    str          # SHA256 of (file_path + text) — stable across re-runs
    file_path:   str
    text:        str
    language:    str
    start_line:  int
    end_line:    int
    symbol_name: str          # function/class name if AST split, else ""
    chunk_type:  str          # "function" | "class" | "heading" | "block"
    source_label: str         # human label for citation, e.g. "CONTRIBUTING.md §3"

    @staticmethod
    def make_id(file_path: str, text: str) -> str:
        return hashlib.sha256(f"{file_path}\x00{text}".encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Token counting (mirrors token_counter.py but local to avoid circular import)
# ---------------------------------------------------------------------------

def _count_tokens(text: str) -> int:
    try:
        import tiktoken
        _enc = tiktoken.get_encoding("cl100k_base")
        return len(_enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# tree-sitter language loader (lazy, cached)
# ---------------------------------------------------------------------------

_TS_CACHE: dict[str, object] = {}   # language_name → Language | None

def _get_ts_language(lang: str):
    """Return a tree-sitter Language for the given lang name, or None."""
    if lang in _TS_CACHE:
        return _TS_CACHE[lang]

    try:
        from tree_sitter import Language
        if lang == "python":
            import tree_sitter_python as m
            obj = Language(m.language())
        elif lang in ("javascript", "jsx"):
            import tree_sitter_javascript as m
            obj = Language(m.language())
        elif lang in ("typescript",):
            import tree_sitter_typescript as m
            obj = Language(m.language_typescript())
        elif lang in ("tsx",):
            import tree_sitter_typescript as m
            obj = Language(m.language_tsx())
        elif lang == "java":
            import tree_sitter_java as m
            obj = Language(m.language())
        elif lang == "go":
            import tree_sitter_go as m
            obj = Language(m.language())
        else:
            obj = None
    except Exception:
        obj = None

    _TS_CACHE[lang] = obj
    return obj


# ---------------------------------------------------------------------------
# AST-based chunking (Python / JS / TS / Java / Go)
# ---------------------------------------------------------------------------

# Node types that represent a top-level code unit worth chunking
_CHUNK_NODE_TYPES = {
    "python":     {"function_definition", "class_definition", "decorated_definition"},
    "javascript": {"function_declaration", "class_declaration", "method_definition",
                   "arrow_function", "lexical_declaration"},
    "jsx":        {"function_declaration", "class_declaration", "method_definition"},
    "typescript": {"function_declaration", "class_declaration", "method_definition",
                   "abstract_class_declaration", "interface_declaration"},
    "tsx":        {"function_declaration", "class_declaration", "method_definition"},
    "java":       {"class_declaration", "method_declaration", "constructor_declaration",
                   "interface_declaration", "enum_declaration"},
    "go":         {"function_declaration", "method_declaration", "type_declaration"},
}


def _get_symbol_name(node) -> str:
    """Extract the name identifier from an AST node."""
    for child in node.children:
        if child.type == "identifier" or child.type == "name":
            return child.text.decode("utf-8", errors="replace") if child.text else ""
    return ""


def _chunk_with_ast(
    file_path: str,
    text: str,
    language: str,
    max_tokens: int,
) -> list[ChunkDoc]:
    ts_lang = _get_ts_language(language)
    if ts_lang is None:
        return []

    from tree_sitter import Parser
    parser = Parser(ts_lang)
    source = text.encode("utf-8", errors="replace")
    tree   = parser.parse(source)
    lines  = text.splitlines()

    target_types = _CHUNK_NODE_TYPES.get(language, set())
    chunks: list[ChunkDoc] = []

    def visit(node, depth: int = 0) -> None:
        if node.type in target_types:
            start = node.start_point[0]   # 0-based row
            end   = node.end_point[0]
            chunk_text = "\n".join(lines[start : end + 1])

            if _count_tokens(chunk_text) > max_tokens:
                # Too large — descend to split children
                for child in node.children:
                    visit(child, depth + 1)
                return

            sym   = _get_symbol_name(node)
            label = f"{os.path.basename(file_path)}"
            if sym:
                label += f":{sym}"

            chunks.append(ChunkDoc(
                chunk_id=ChunkDoc.make_id(file_path, chunk_text),
                file_path=file_path,
                text=chunk_text,
                language=language,
                start_line=start + 1,
                end_line=end + 1,
                symbol_name=sym,
                chunk_type=node.type.replace("_declaration", "").replace("_definition", ""),
                source_label=label,
            ))
        else:
            for child in node.children:
                visit(child, depth + 1)

    visit(tree.root_node)

    # If AST produced no chunks (e.g. script with no top-level defs), fall back
    return chunks


# ---------------------------------------------------------------------------
# Markdown / heading-boundary chunking
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def _chunk_markdown(file_path: str, text: str, max_tokens: int) -> list[ChunkDoc]:
    """Split a Markdown file at H1/H2/H3 headings."""
    chunks: list[ChunkDoc] = []
    parts  = _HEADING_RE.split(text)
    # parts alternates: [pre-heading text, heading_name, section_text, ...]

    lines_seen = 0
    current_title = os.path.basename(file_path)

    i = 0
    while i < len(parts):
        if i == 0:
            body = parts[0].strip()
            title = current_title
        else:
            title = parts[i].strip()
            body  = (parts[i + 1].strip() if i + 1 < len(parts) else "")
            i    += 1

        i += 1
        if not body:
            continue

        chunk_text = f"# {title}\n\n{body}" if title else body
        start = lines_seen + 1
        lines_seen += chunk_text.count("\n") + 1
        end = lines_seen

        # Split oversized sections by paragraph
        if _count_tokens(chunk_text) > max_tokens:
            paras = re.split(r"\n{2,}", chunk_text)
            para_start = start
            for para in paras:
                if para.strip():
                    chunks.append(ChunkDoc(
                        chunk_id=ChunkDoc.make_id(file_path, para),
                        file_path=file_path,
                        text=para.strip(),
                        language="markdown",
                        start_line=para_start,
                        end_line=para_start + para.count("\n"),
                        symbol_name="",
                        chunk_type="heading",
                        source_label=f"{os.path.basename(file_path)} §{title}",
                    ))
                para_start += para.count("\n") + 2
        else:
            chunks.append(ChunkDoc(
                chunk_id=ChunkDoc.make_id(file_path, chunk_text),
                file_path=file_path,
                text=chunk_text,
                language="markdown",
                start_line=start,
                end_line=end,
                symbol_name="",
                chunk_type="heading",
                source_label=f"{os.path.basename(file_path)} §{title}",
            ))

    return chunks


# ---------------------------------------------------------------------------
# Generic fixed-size line chunking (fallback for any file type)
# ---------------------------------------------------------------------------

def _chunk_by_lines(
    file_path: str,
    text: str,
    language: str,
    max_tokens: int,
    overlap_lines: int = 10,
) -> list[ChunkDoc]:
    lines   = text.splitlines()
    chunks: list[ChunkDoc] = []
    start   = 0
    step_lines = max(1, max_tokens // 6)   # rough estimate: ~6 tokens/line

    while start < len(lines):
        end = min(start + step_lines, len(lines))
        chunk_text = "\n".join(lines[start:end])

        # Trim until within budget (in case estimate was off)
        while _count_tokens(chunk_text) > max_tokens and end > start + 1:
            end -= 1
            chunk_text = "\n".join(lines[start:end])

        chunks.append(ChunkDoc(
            chunk_id=ChunkDoc.make_id(file_path, chunk_text),
            file_path=file_path,
            text=chunk_text,
            language=language,
            start_line=start + 1,
            end_line=end,
            symbol_name="",
            chunk_type="block",
            source_label=f"{os.path.basename(file_path)} L{start+1}-{end}",
        ))
        # Overlap: step back by overlap_lines for next window
        start = max(start + 1, end - overlap_lines)

    return chunks


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def chunk_source_file(
    file_path: str,
    text: str,
    language: str,
    *,
    max_tokens: int = 400,
) -> list[ChunkDoc]:
    """
    Chunk a source file into embeddable ChunkDoc objects.

    Strategy (in order):
      1. AST-based for supported languages (Python, JS, TS, Java, Go).
      2. Heading-based for Markdown.
      3. Fixed-size line blocks for everything else.
    Falls back to fixed-size if AST produces 0 chunks.
    """
    if not text.strip():
        return []

    lang = language.lower()

    # --- Markdown / config ---
    if lang in ("markdown", "md"):
        result = _chunk_markdown(file_path, text, max_tokens)
        if result:
            return result

    # --- AST-supported languages ---
    if lang in _CHUNK_NODE_TYPES:
        result = _chunk_with_ast(file_path, text, lang, max_tokens)
        if result:
            return result

    # --- Fallback ---
    return _chunk_by_lines(file_path, text, lang, max_tokens)
