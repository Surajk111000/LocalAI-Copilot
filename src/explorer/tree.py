"""Project explorer: folder tree + instant file search."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".turbo",
    "coverage",
    ".idea",
    ".vscode",
    "chroma",
}


@dataclass
class TreeNode:
    name: str
    path: str  # relative path with /
    is_dir: bool
    children: list["TreeNode"] | None = None


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def build_tree(root: str | Path, max_depth: int = 6, max_entries: int = 2000) -> TreeNode:
    root_path = Path(root).expanduser().resolve()
    count = 0

    def walk(current: Path, depth: int) -> TreeNode:
        nonlocal count
        node = TreeNode(
            name=current.name if current != root_path else root_path.name,
            path="." if current == root_path else _rel(current, root_path),
            is_dir=True,
            children=[],
        )
        if depth > max_depth or count >= max_entries:
            return node
        try:
            entries = sorted(
                current.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            return node
        for entry in entries:
            if count >= max_entries:
                break
            if entry.name.startswith(".") and entry.name not in {".env.example"}:
                # Still show common config files; skip hidden dirs/files mostly.
                if entry.is_dir() or entry.name not in {".gitignore", ".env.example"}:
                    if entry.is_dir():
                        continue
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                count += 1
                node.children.append(walk(entry, depth + 1))
            else:
                count += 1
                node.children.append(
                    TreeNode(
                        name=entry.name,
                        path=_rel(entry, root_path),
                        is_dir=False,
                    )
                )
        return node

    return walk(root_path, 0)


def search_files(
    root: str | Path,
    query: str,
    limit: int = 50,
) -> list[str]:
    """Instant filename search (case-insensitive substring)."""
    q = query.strip().lower()
    if not q:
        return []
    root_path = Path(root).expanduser().resolve()
    hits: list[str] = []
    for path in root_path.rglob("*"):
        if len(hits) >= limit:
            break
        if not path.is_file():
            continue
        # Skip heavy dirs
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = _rel(path, root_path)
        if q in path.name.lower() or q in rel.lower():
            hits.append(rel)
    return hits


def file_icon(name: str, is_dir: bool) -> str:
    if is_dir:
        return "📁"
    ext = Path(name).suffix.lower()
    mapping = {
        ".py": "🐍",
        ".js": "🟨",
        ".jsx": "⚛️",
        ".ts": "🔷",
        ".tsx": "⚛️",
        ".json": "🧾",
        ".md": "📝",
        ".yml": "⚙️",
        ".yaml": "⚙️",
        ".toml": "⚙️",
        ".css": "🎨",
        ".html": "🌐",
        ".txt": "📄",
        ".sh": "💻",
        ".bat": "💻",
        ".ps1": "💻",
    }
    return mapping.get(ext, "📄")
