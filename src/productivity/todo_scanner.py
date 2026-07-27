"""Scan for TODO / FIXME / BUG / HACK markers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.explorer.tree import SKIP_DIRS

MARKER_RE = re.compile(r"\b(TODO|FIXME|BUG|HACK|XXX)\b[:\s-]?(.*)$", re.I)
CODE_EXTS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".md",
    ".sql",
    ".yml",
    ".yaml",
}


@dataclass
class TodoHit:
    kind: str
    path: str
    line: int
    text: str


def scan_todos(project_path: str | Path, limit: int = 200) -> list[TodoHit]:
    root = Path(project_path).expanduser().resolve()
    hits: list[TodoHit] = []
    for path in root.rglob("*"):
        if len(hits) >= limit:
            break
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in CODE_EXTS:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        for i, line in enumerate(lines, start=1):
            match = MARKER_RE.search(line)
            if not match:
                continue
            hits.append(
                TodoHit(
                    kind=match.group(1).upper(),
                    path=rel,
                    line=i,
                    text=line.strip()[:240],
                )
            )
            if len(hits) >= limit:
                break
    return hits


def summarize_todos(hits: list[TodoHit]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.kind] = counts.get(hit.kind, 0) + 1
    return counts
