"""Unified tool registry used by multi-agent nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.rag.embeddings import OllamaEmbedder
from src.rag.retriever import ProjectRetriever
from src.search.smart_search import smart_search
from src.tools.filesystem import FileSystemTools
from src.tools.git_tools import GitTools
from src.tools.terminal_tools import TerminalTools


@dataclass
class ToolRegistry:
    """Filesystem + git + terminal + RAG — destructive ops need approval."""

    project_path: str
    embedder: OllamaEmbedder | None = None
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.fs = FileSystemTools(self.project_path)
        self.git = GitTools(self.project_path)
        self.terminal = TerminalTools(self.project_path)

    def list_directory(self, path: str = ".") -> str:
        return self.fs.list_directory(path).output

    def read_file(self, path: str) -> str:
        return self.fs.read_file(path).output

    def search_files(self, query: str, path: str = ".") -> str:
        return self.fs.search_files(query, path).output

    def smart_search(self, question: str) -> str:
        result = smart_search(self.project_path, question)
        parts = [result.summary]
        if result.symbols:
            parts.append("Symbols:\n" + "\n".join(result.symbols[:20]))
        if result.hits:
            parts.append("Hits:\n" + "\n".join(result.hits[:30]))
        return "\n\n".join(parts)

    def rag_retrieve(self, question: str, top_k: int = 5) -> str:
        if self.embedder is None:
            return ""
        try:
            retriever = ProjectRetriever(self.embedder, top_k=top_k)
            if not retriever.has_index(self.project_path):
                return ""
            chunks = retriever.retrieve(self.project_path, question, top_k=top_k)
            return ProjectRetriever.format_context(chunks)
        except Exception as exc:  # noqa: BLE001
            return f"(RAG unavailable: {exc})"

    def git_status(self) -> str:
        return self.git.status().output

    def git_diff(self) -> str:
        return self.git.diff().output

    def git_log(self, n: int = 5) -> str:
        return self.git.log(n=n).output

    def git_run(self, args: list[str], *, approved: bool = False) -> str:
        result = self.git.run(args, approved=approved)
        if result.needs_approval:
            self.pending_approvals.append(
                {"tool": "git", "command": result.command, "args": args}
            )
        return result.output

    def terminal_run(self, command: str, *, approved: bool = False) -> str:
        result = self.terminal.run(command, approved=approved)
        if result.needs_approval:
            self.pending_approvals.append(
                {"tool": "terminal", "command": result.command}
            )
        return result.output

    def load_files(self, paths: list[str], max_files: int = 8) -> dict[str, str]:
        out: dict[str, str] = {}
        for rel in paths[:max_files]:
            result = self.fs.read_file(rel)
            if result.ok:
                # Strip the FILE: header for cleaner LLM context
                text = result.output
                if text.startswith("FILE:"):
                    parts = text.split("\n\n", 1)
                    text = parts[1] if len(parts) > 1 else text
                out[rel] = text[:10000]
        return out
