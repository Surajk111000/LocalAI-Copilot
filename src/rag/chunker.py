"""Split project files into overlapping text chunks for embedding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# File types worth indexing for a coding assistant
CODE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".sql",
    ".sh",
    ".bat",
    ".ps1",
    ".html",
    ".css",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".r",
    ".ipynb",
}

SPECIAL_FILENAMES = {
    "dockerfile",
    "makefile",
    "readme",
    "license",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "docker-compose.yml",
    "docker-compose.yaml",
}

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "memory",
    ".ollama",
}


@dataclass
class CodeChunk:
    """One piece of a file ready for the vector database."""

    chunk_id: str
    path: str
    content: str
    start_line: int
    end_line: int


def should_index_file(path: Path) -> bool:
    """Return True if this file looks useful for code search."""
    name = path.name.lower()
    if name in SPECIAL_FILENAMES or name.startswith("dockerfile"):
        return True
    return path.suffix.lower() in CODE_EXTENSIONS


def iter_project_files(root: Path) -> list[Path]:
    """Walk a project folder and return indexable files."""
    root = root.resolve()
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if should_index_file(path):
            files.append(path)
    return sorted(files)


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[tuple[int, int, str]]:
    """Split text into overlapping chunks.

    Returns list of (start_line, end_line, chunk_text).
    Lines are 1-based for human-friendly citations.
    """
    if not text.strip():
        return []

    lines = text.splitlines()
    # Build char offsets per line so we can map chunk spans back to line numbers
    line_starts: list[int] = []
    cursor = 0
    for line in lines:
        line_starts.append(cursor)
        cursor += len(line) + 1  # +1 for the newline we split on

    full = text if text.endswith("\n") else text + "\n"
    chunks: list[tuple[int, int, str]] = []
    start = 0
    length = len(full)

    while start < length:
        end = min(start + chunk_size, length)
        piece = full[start:end].strip()
        if piece:
            start_line = _offset_to_line(start, line_starts)
            end_line = _offset_to_line(max(end - 1, start), line_starts)
            chunks.append((start_line, end_line, piece))
        if end >= length:
            break
        start = max(0, end - overlap)

    return chunks


def _offset_to_line(offset: int, line_starts: list[int]) -> int:
    """Map a character offset to a 1-based line number."""
    if not line_starts:
        return 1
    line = 1
    for i, start in enumerate(line_starts, start=1):
        if start <= offset:
            line = i
        else:
            break
    return line


def chunk_file(
    path: Path,
    root: Path,
    *,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[CodeChunk]:
    """Read one file and turn it into CodeChunk objects."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    results: list[CodeChunk] = []
    for index, (start_line, end_line, content) in enumerate(
        chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    ):
        results.append(
            CodeChunk(
                chunk_id=f"{rel}::{index}",
                path=rel,
                content=content,
                start_line=start_line,
                end_line=end_line,
            )
        )
    return results
