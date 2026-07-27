"""Safe filesystem tools scoped to one project root.

The model never gets raw access to the whole disk — every path is resolved
under the project folder the user selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    "memory",
    ".ollama",
}

MAX_READ_CHARS = 12_000
MAX_SEARCH_HITS = 20
MAX_LIST_ENTRIES = 200


@dataclass
class PendingWrite:
    """A proposed file change that still needs the user's approval."""

    path: str
    content: str
    absolute_path: str
    is_new: bool
    old_content: str = ""


@dataclass
class ToolResult:
    name: str
    ok: bool
    output: str
    pending_write: PendingWrite | None = None


class FileSystemTools:
    """list / read / search / write — always rooted in project_root."""

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise FileNotFoundError(f"Project folder not found: {self.root}")

    def resolve(self, relative_path: str) -> Path:
        """Resolve a relative path and reject escapes outside the project."""
        raw = (relative_path or ".").strip() or "."
        candidate = (self.root / raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError(
                f"Path escapes project root: {relative_path}"
            ) from exc
        return candidate

    def list_directory(self, path: str = ".") -> ToolResult:
        try:
            target = self.resolve(path)
            if not target.exists():
                return ToolResult("list_directory", False, f"Not found: {path}")
            if not target.is_dir():
                return ToolResult("list_directory", False, f"Not a directory: {path}")

            entries: list[str] = []
            for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if item.name in SKIP_DIRS:
                    continue
                rel = str(item.relative_to(self.root)).replace("\\", "/")
                suffix = "/" if item.is_dir() else ""
                entries.append(f"{rel}{suffix}")
                if len(entries) >= MAX_LIST_ENTRIES:
                    entries.append("… truncated …")
                    break

            body = "\n".join(entries) if entries else "(empty)"
            return ToolResult("list_directory", True, body)
        except Exception as exc:
            return ToolResult("list_directory", False, str(exc))

    def read_file(self, path: str) -> ToolResult:
        try:
            target = self.resolve(path)
            if not target.exists() or not target.is_file():
                return ToolResult("read_file", False, f"File not found: {path}")

            text = target.read_text(encoding="utf-8", errors="ignore")
            if len(text) > MAX_READ_CHARS:
                text = text[:MAX_READ_CHARS] + "\n\n… truncated …"
            rel = str(target.relative_to(self.root)).replace("\\", "/")
            return ToolResult("read_file", True, f"FILE: {rel}\n\n{text}")
        except Exception as exc:
            return ToolResult("read_file", False, str(exc))

    def search_files(self, query: str, path: str = ".") -> ToolResult:
        """Simple case-insensitive substring search across text files."""
        query = (query or "").strip()
        if not query:
            return ToolResult("search_files", False, "query is required")

        try:
            start = self.resolve(path)
            if not start.exists():
                return ToolResult("search_files", False, f"Not found: {path}")

            hits: list[str] = []
            files = start.rglob("*") if start.is_dir() else [start]
            for file_path in files:
                if not file_path.is_file():
                    continue
                if any(part in SKIP_DIRS for part in file_path.parts):
                    continue
                if file_path.suffix.lower() not in {
                    ".py",
                    ".md",
                    ".txt",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".toml",
                    ".js",
                    ".ts",
                    ".tsx",
                    ".sql",
                    ".html",
                    ".css",
                } and file_path.name.lower() not in {"dockerfile", "makefile"}:
                    continue
                try:
                    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                except OSError:
                    continue
                rel = str(file_path.relative_to(self.root)).replace("\\", "/")
                for i, line in enumerate(lines, start=1):
                    if query.lower() in line.lower():
                        hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                        if len(hits) >= MAX_SEARCH_HITS:
                            body = "\n".join(hits) + "\n… more hits truncated …"
                            return ToolResult("search_files", True, body)

            body = "\n".join(hits) if hits else f"No matches for {query!r}"
            return ToolResult("search_files", True, body)
        except Exception as exc:
            return ToolResult("search_files", False, str(exc))

    def write_file(self, path: str, content: str) -> ToolResult:
        """Propose a write — does NOT touch disk until the user approves."""
        try:
            target = self.resolve(path)
            # Block writes into skipped system dirs
            if any(part in SKIP_DIRS for part in target.relative_to(self.root).parts[:-1]):
                return ToolResult(
                    "write_file",
                    False,
                    f"Refusing to write inside protected path: {path}",
                )
            if content is None:
                return ToolResult("write_file", False, "content is required")

            rel = str(target.relative_to(self.root)).replace("\\", "/")
            is_new = not target.exists()
            old_content = ""
            if not is_new and target.is_file():
                try:
                    old_content = target.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    old_content = ""
            pending = PendingWrite(
                path=rel,
                content=str(content),
                absolute_path=str(target),
                is_new=is_new,
                old_content=old_content,
            )
            action = "create" if pending.is_new else "overwrite"
            return ToolResult(
                "write_file",
                True,
                f"Proposed {action} of `{rel}` ({len(pending.content)} chars). "
                "Waiting for user approval.",
                pending_write=pending,
            )
        except Exception as exc:
            return ToolResult("write_file", False, str(exc))

    def apply_write(self, pending: PendingWrite) -> ToolResult:
        """Actually write a previously approved PendingWrite to disk."""
        try:
            target = Path(pending.absolute_path).resolve()
            target.relative_to(self.root)  # safety check
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(pending.content, encoding="utf-8")
            return ToolResult(
                "apply_write",
                True,
                f"Wrote `{pending.path}` ({len(pending.content)} chars).",
            )
        except Exception as exc:
            return ToolResult("apply_write", False, str(exc))

    def run(self, name: str, arguments: dict) -> ToolResult:
        args = arguments or {}
        if name == "list_directory":
            return self.list_directory(str(args.get("path", ".")))
        if name == "read_file":
            return self.read_file(str(args.get("path", "")))
        if name == "search_files":
            return self.search_files(
                str(args.get("query", "")),
                str(args.get("path", ".")),
            )
        if name == "write_file":
            return self.write_file(
                str(args.get("path", "")),
                str(args.get("content", "")),
            )
        return ToolResult(name, False, f"Unknown tool: {name}")
