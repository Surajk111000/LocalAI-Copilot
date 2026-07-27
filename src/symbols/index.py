"""Lightweight symbol index (regex) for Python / JS / TS — no LSP required."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.explorer.tree import SKIP_DIRS

CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx"}

PATTERNS = {
    "function": [
        re.compile(r"^\s*def\s+([A-Za-z_][\w]*)\s*\(", re.M),
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w]*)\s*\(", re.M),
        re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_][\w]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", re.M),
    ],
    "class": [
        re.compile(r"^\s*class\s+([A-Za-z_][\w]*)\b", re.M),
        re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][\w]*)\b", re.M),
    ],
    "variable": [
        re.compile(r"^\s*([A-Za-z_][\w]*)\s*=\s*[^=].*$", re.M),
        re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_][\w]*)\b", re.M),
    ],
    "import": [
        re.compile(r"^\s*(?:from\s+\S+\s+)?import\s+(.+)$", re.M),
        re.compile(r"^\s*import\s+.+from\s+['\"].+['\"]", re.M),
        re.compile(r"^\s*import\s+['\"].+['\"]", re.M),
    ],
}


@dataclass
class SymbolHit:
    kind: str
    name: str
    path: str
    line: int
    text: str


def _iter_code_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in CODE_EXTS:
            continue
        yield path


def find_symbols(
    project_path: str | Path,
    *,
    kind: str | None = None,
    query: str = "",
    limit: int = 100,
) -> list[SymbolHit]:
    root = Path(project_path).expanduser().resolve()
    q = (query or "").strip().lower()
    kinds = [kind] if kind else list(PATTERNS.keys())
    hits: list[SymbolHit] = []

    for file_path in _iter_code_files(root):
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(file_path.relative_to(root)).replace("\\", "/")
        lines = text.splitlines()
        for k in kinds:
            for pattern in PATTERNS.get(k, []):
                for match in pattern.finditer(text):
                    name = match.group(1) if match.lastindex else match.group(0)
                    name = str(name).strip()
                    if q and q not in name.lower() and q not in rel.lower():
                        continue
                    line_no = text[: match.start()].count("\n") + 1
                    snippet = lines[line_no - 1].strip() if 0 < line_no <= len(lines) else name
                    hits.append(
                        SymbolHit(
                            kind=k,
                            name=name[:120],
                            path=rel,
                            line=line_no,
                            text=snippet[:200],
                        )
                    )
                    if len(hits) >= limit:
                        return hits
    return hits


def find_definition(project_path: str | Path, symbol: str, limit: int = 20) -> list[SymbolHit]:
    return find_symbols(project_path, query=symbol, limit=limit)
