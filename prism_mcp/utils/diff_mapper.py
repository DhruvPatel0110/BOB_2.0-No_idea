"""
diff_mapper.py — Map PRISM review findings to valid GitHub PR diff positions and line anchors.

GitHub PR Review Comment Requirements:
- Modern GitHub REST API (POST /repos/{owner}/{repo}/pulls/{number}/reviews)
  accepts comments with:
    - path: relative file path (must match a file in the PR)
    - line: line number in the target file (new file / RIGHT side)
    - side: "RIGHT" (default) or "LEFT"
  Alternatively, legacy GitHub review comments accept `position`:
    - position: 1-based index counting from the first `@@` hunk header of that file.

This module parses the unified diff to:
1. Index all modified files in the diff.
2. Build bidirectional lookups between (new_line) <-> (diff_position).
3. Validate and snap finding line numbers to the closest valid diff line within
   the affected file, preventing GitHub 422 "Validation Failed: line must be part of the diff".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


_HUNK_RE = re.compile(r"^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@")
_DIFF_GIT_RE = re.compile(r"^diff\s+--git\s+a/(.+)\s+b/(.+)$")


@dataclass
class FileDiffIndex:
    """Diff line & position mapping for a single file in a PR diff."""
    file_path: str
    valid_lines: Set[int] = field(default_factory=set)
    line_to_position: Dict[int, int] = field(default_factory=dict)
    position_to_line: Dict[int, int] = field(default_factory=dict)
    hunk_ranges: List[Tuple[int, int]] = field(default_factory=list)  # (start_line, end_line)

    def get_best_line(self, line_start: int, line_end: int = 0) -> Optional[int]:
        """
        Finds the exact line in valid diff lines, or snaps to the closest valid
        line in the file's diff hunks. Returns None if file has no valid diff lines.
        """
        if not self.valid_lines:
            return None

        # 1. Exact match on line_start
        if line_start in self.valid_lines:
            return line_start

        # 2. Match on line_end
        if line_end in self.valid_lines:
            return line_end

        # 3. Check if any line in [line_start, line_end] is in diff
        if line_start > 0 and line_end >= line_start:
            for candidate in range(line_start, line_end + 1):
                if candidate in self.valid_lines:
                    return candidate

        # 4. Snap to closest line in valid_lines
        target = line_start if line_start > 0 else (line_end if line_end > 0 else 1)
        closest_line = min(self.valid_lines, key=lambda l: abs(l - target))
        return closest_line


def build_diff_index(unified_diff: str) -> Dict[str, FileDiffIndex]:
    """
    Parses a unified diff string and returns a dictionary of
    normalized file_path -> FileDiffIndex.
    """
    files: Dict[str, FileDiffIndex] = {}
    lines = unified_diff.splitlines()

    current_file: Optional[str] = None
    current_index: Optional[FileDiffIndex] = None
    in_hunks = False
    diff_position = 0
    new_line = 0

    for line in lines:
        m_git = _DIFF_GIT_RE.match(line)
        if m_git:
            # New file started in diff
            current_file = m_git.group(2).strip()
            current_index = FileDiffIndex(file_path=current_file)
            files[current_file] = current_index
            in_hunks = False
            diff_position = 0
            continue

        if not current_file or current_index is None:
            continue

        m_hunk = _HUNK_RE.match(line)
        if m_hunk:
            in_hunks = True
            diff_position += 1  # GitHub position counts starting from first @@ line or line after
            new_line = int(m_hunk.group(2))
            continue

        if in_hunks:
            diff_position += 1
            if line.startswith("+"):
                # Addition: belongs to new file
                current_index.valid_lines.add(new_line)
                current_index.line_to_position[new_line] = diff_position
                current_index.position_to_line[diff_position] = new_line
                new_line += 1
            elif line.startswith("-"):
                # Deletion: belongs only to old file, does not advance new_line
                # GitHub allows commenting on diff position for deleted lines
                pass
            elif line.startswith(" "):
                # Context line: belongs to new file
                current_index.valid_lines.add(new_line)
                current_index.line_to_position[new_line] = diff_position
                current_index.position_to_line[diff_position] = new_line
                new_line += 1
            elif line.startswith("\\"):
                # e.g. "\ No newline at end of file"
                pass

    return files


def map_finding_to_diff(
    finding: dict,
    diff_index: Dict[str, FileDiffIndex],
) -> dict:
    """
    Maps a finding dict to a valid GitHub review comment target.

    Returns a dict with:
        path: str
        line: int
        side: "RIGHT"
        position: Optional[int]
        in_diff: bool
        snapped: bool
    """
    file_path = (finding.get("file") or finding.get("file_path") or "").strip()
    line_start = int(finding.get("line_start") or 0)
    line_end = int(finding.get("line_end") or line_start)

    # Normalize file path (strip leading slash or ./ or a/ or b/)
    clean_path = file_path.lstrip("./").lstrip("/")
    if clean_path.startswith("b/"):
        clean_path = clean_path[2:]

    # Match file in diff_index
    matched_file_key = None
    if clean_path in diff_index:
        matched_file_key = clean_path
    else:
        for k in diff_index.keys():
            if k == clean_path or k.endswith(clean_path) or clean_path.endswith(k):
                matched_file_key = k
                break

    if not matched_file_key:
        # File is not in the diff at all
        return {
            "path": clean_path,
            "line": max(1, line_start),
            "side": "RIGHT",
            "position": None,
            "in_diff": False,
            "snapped": False,
        }

    file_idx = diff_index[matched_file_key]
    best_line = file_idx.get_best_line(line_start, line_end)

    if best_line is None:
        return {
            "path": matched_file_key,
            "line": max(1, line_start),
            "side": "RIGHT",
            "position": None,
            "in_diff": False,
            "snapped": False,
        }

    snapped = (best_line != line_start and best_line != line_end)
    position = file_idx.line_to_position.get(best_line)

    return {
        "path": matched_file_key,
        "line": best_line,
        "side": "RIGHT",
        "position": position,
        "in_diff": True,
        "snapped": snapped,
    }
