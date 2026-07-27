"""Text diff helpers for the approval UI."""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass
class DiffHunk:
    """One contiguous change region for display."""

    kind: str  # equal | add | remove | replace
    old_text: str
    new_text: str


def unified_diff(old: str, new: str, path: str = "file") -> str:
    """Classic unified diff string (git-style)."""
    old_lines = (old or "").splitlines(keepends=True)
    new_lines = (new or "").splitlines(keepends=True)
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )


def side_by_side_hunks(old: str, new: str, context: int = 3) -> list[DiffHunk]:
    """Produce compact hunks for OLD / NEW panels."""
    matcher = difflib.SequenceMatcher(None, (old or "").splitlines(), (new or "").splitlines())
    hunks: list[DiffHunk] = []
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Keep a little context around changes only when adjacent to edits
            continue
        hunks.append(
            DiffHunk(
                kind=tag,
                old_text="\n".join(old_lines[i1:i2]),
                new_text="\n".join(new_lines[j1:j2]),
            )
        )
    if not hunks and old == new:
        return [DiffHunk(kind="equal", old_text=old or "", new_text=new or "")]
    if not hunks:
        # Entire file replace with no opcode quirks
        return [DiffHunk(kind="replace", old_text=old or "", new_text=new or "")]
    return hunks


def change_stats(old: str, new: str) -> dict[str, int]:
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1
    return {"added": added, "removed": removed, "old_lines": len(old_lines), "new_lines": len(new_lines)}
