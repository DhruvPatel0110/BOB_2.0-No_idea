"""
diff_parser.py — Parse a unified diff string into HunkChunk objects.

Each HunkChunk represents one contiguous changed block inside one file,
enriched with the surrounding full-file context lines (±30 lines around
the hunk's start line, provided separately when the caller has the full
file text available).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Language detection from file extension
# ---------------------------------------------------------------------------

_EXT_TO_LANG: dict[str, str] = {
    ".py":    "python",
    ".js":    "javascript",
    ".jsx":   "javascript",
    ".ts":    "typescript",
    ".tsx":   "typescript",
    ".java":  "java",
    ".go":    "go",
    ".rb":    "ruby",
    ".php":   "php",
    ".c":     "c",
    ".h":     "c",
    ".cpp":   "cpp",
    ".cc":    "cpp",
    ".cxx":   "cpp",
    ".hpp":   "cpp",
    ".cs":    "csharp",
    ".rs":    "rust",
    ".kt":    "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sh":    "bash",
    ".bash":  "bash",
    ".zsh":   "bash",
    ".yaml":  "yaml",
    ".yml":   "yaml",
    ".json":  "json",
    ".toml":  "toml",
    ".tf":    "terraform",
    ".sql":   "sql",
    ".md":    "markdown",
    ".html":  "html",
    ".css":   "css",
    ".scss":  "css",
}


def _detect_language(file_path: str, hint: Optional[str] = None) -> str:
    if hint:
        return hint.lower()
    ext = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return _EXT_TO_LANG.get(ext, "text")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class HunkChunk:
    """One diff hunk from one file, ready for review."""
    file_path: str
    language: str
    hunk_header: str        # e.g.  @@ -10,7 +10,9 @@
    old_start: int          # line number in old file where hunk starts
    new_start: int          # line number in new file where hunk starts
    diff_lines: list[str]   # raw hunk lines (include +/-/space prefix)
    context_lines: str      # surrounding full-file lines (injected later)
    change_type: str        # "modified" | "added" | "deleted"
    sub_chunk_index: int = 0       # 0 = not sub-chunked; >0 = sub-chunk N
    sub_chunk_total: int   = 1

    @property
    def diff_text(self) -> str:
        return "\n".join(self.diff_lines)

    @property
    def line_start(self) -> int:
        return self.new_start if self.new_start > 0 else self.old_start

    @property
    def line_end(self) -> int:
        start = self.line_start
        return max(start, start + len(self.diff_lines) - 1)

    @property
    def additions(self) -> int:
        return sum(1 for l in self.diff_lines if l.startswith("+") and not l.startswith("+++"))

    @property
    def deletions(self) -> int:
        return sum(1 for l in self.diff_lines if l.startswith("-") and not l.startswith("---"))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_DIFF_FILE_RE  = re.compile(r"^diff --git a/(.+) b/(.+)$")
_NEW_FILE_RE   = re.compile(r"^new file mode")
_DEL_FILE_RE   = re.compile(r"^deleted file mode")
_HUNK_RE       = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)")


def parse_diff(
    unified_diff: str,
    language_hint: Optional[str] = None,
    file_contents: Optional[dict[str, str]] = None,
    context_window: int = 30,
) -> list[HunkChunk]:
    """
    Parse a unified diff string into a flat list of HunkChunks.

    Args:
        unified_diff:   Raw unified diff text (output of `git diff`).
        language_hint:  Override language detection for all files.
        file_contents:  Dict mapping file_path → full file text. When
                        provided, the surrounding context_window lines are
                        attached to each chunk.
        context_window: Number of lines above/below the hunk to attach
                        as context (default 30).

    Returns:
        Ordered list of HunkChunk objects ready for review.
    """
    chunks: list[HunkChunk] = []
    lines = unified_diff.splitlines()

    current_file: str = ""
    change_type: str = "modified"
    hunk_lines: list[str] = []
    hunk_header: str = ""
    old_start = new_start = 0

    def _flush_hunk() -> None:
        if not hunk_lines or not current_file:
            return
        ctx = _extract_context(current_file, new_start, context_window, file_contents)
        chunks.append(HunkChunk(
            file_path=current_file,
            language=_detect_language(current_file, language_hint),
            hunk_header=hunk_header,
            old_start=old_start,
            new_start=new_start,
            diff_lines=list(hunk_lines),
            context_lines=ctx,
            change_type=change_type,
        ))
        hunk_lines.clear()

    for line in lines:
        m_file = _DIFF_FILE_RE.match(line)
        if m_file:
            _flush_hunk()
            current_file = m_file.group(2)  # b/ path
            change_type = "modified"
            continue

        if _NEW_FILE_RE.match(line):
            change_type = "added"
            continue
        if _DEL_FILE_RE.match(line):
            change_type = "deleted"
            continue

        # Skip --- / +++ header lines
        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        m_hunk = _HUNK_RE.match(line)
        if m_hunk:
            _flush_hunk()
            old_start = int(m_hunk.group(1))
            new_start = int(m_hunk.group(2))
            hunk_header = line
            continue

        if hunk_lines is not None and current_file and hunk_header:
            hunk_lines.append(line)

    _flush_hunk()
    return chunks


def _extract_context(
    file_path: str,
    hunk_start: int,
    window: int,
    file_contents: Optional[dict[str, str]],
) -> str:
    """Return ±window lines around hunk_start from full file text, if available."""
    if not file_contents or file_path not in file_contents:
        return ""
    all_lines = file_contents[file_path].splitlines()
    lo = max(0, hunk_start - window - 1)
    hi = min(len(all_lines), hunk_start + window)
    numbered = [
        f"{lo + i + 1:>4} | {l}"
        for i, l in enumerate(all_lines[lo:hi])
    ]
    return "\n".join(numbered)
