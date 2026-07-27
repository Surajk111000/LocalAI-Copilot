"""AI context manager: pinned files + token estimation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from src.workspace.paths import context_path, read_json, write_json


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token). Good enough for UI."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class ContextFile:
    path: str
    pinned: bool = False
    tokens: int = 0


class ContextManager:
    def __init__(self, project_path: str | Path) -> None:
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.root = Path(self.project_path)
        self.path = context_path(self.project_path)

    def _load(self) -> list[ContextFile]:
        raw = read_json(self.path, {"files": []})
        files: list[ContextFile] = []
        for item in raw.get("files") or []:
            files.append(
                ContextFile(
                    path=str(item.get("path") or ""),
                    pinned=bool(item.get("pinned", False)),
                    tokens=int(item.get("tokens") or 0),
                )
            )
        return files

    def _save(self, files: list[ContextFile]) -> None:
        write_json(self.path, {"files": [asdict(f) for f in files]})

    def list_files(self) -> list[ContextFile]:
        return self._load()

    def add(self, rel_or_abs: str, pinned: bool = False) -> ContextFile | None:
        target = Path(rel_or_abs)
        if not target.is_absolute():
            target = self.root / target
        if not target.is_file():
            return None
        try:
            rel = str(target.resolve().relative_to(self.root.resolve())).replace("\\", "/")
        except ValueError:
            rel = str(target.resolve())
        text = ""
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
        tokens = estimate_tokens(text)
        files = self._load()
        for existing in files:
            if existing.path == rel:
                existing.pinned = existing.pinned or pinned
                existing.tokens = tokens
                self._save(files)
                return existing
        entry = ContextFile(path=rel, pinned=pinned, tokens=tokens)
        files.append(entry)
        self._save(files)
        return entry

    def remove(self, path: str) -> None:
        files = [f for f in self._load() if f.path != path]
        self._save(files)

    def clear(self, keep_pinned: bool = False) -> None:
        if keep_pinned:
            files = [f for f in self._load() if f.pinned]
        else:
            files = []
        self._save(files)

    def pin(self, path: str, pinned: bool = True) -> None:
        files = self._load()
        for f in files:
            if f.path == path:
                f.pinned = pinned
        self._save(files)

    def total_tokens(self) -> int:
        return sum(f.tokens for f in self._load())

    def build_context_block(self, max_chars: int = 24_000) -> str:
        """Build text block for the LLM from context files."""
        parts: list[str] = []
        used = 0
        # Pinned first.
        files = sorted(self._load(), key=lambda f: (not f.pinned, f.path))
        for item in files:
            path = Path(item.path)
            if not path.is_absolute():
                path = self.root / path
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            chunk = f"### Context file: {item.path}\n```\n{content}\n```\n"
            if used + len(chunk) > max_chars:
                remaining = max_chars - used
                if remaining < 200:
                    break
                chunk = chunk[:remaining] + "\n...[truncated]\n"
                parts.append(chunk)
                break
            parts.append(chunk)
            used += len(chunk)
        return "\n".join(parts)
