"""Conversation memory manager for multi-agent runs (per project)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.workspace.paths import project_dir, read_json, write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryTurn:
    role: str
    content: str
    agent: str = ""
    timestamp: str = ""


@dataclass
class ConversationMemory:
    turns: list[MemoryTurn] = field(default_factory=list)
    last_thread_id: str = ""


class ConversationManager:
    """Persist multi-agent conversation memory under the project folder."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.path = project_dir(self.project_path) / "multi_agent_memory.json"

    def load(self) -> ConversationMemory:
        raw = read_json(self.path, {})
        turns = [
            MemoryTurn(
                role=str(t.get("role") or "user"),
                content=str(t.get("content") or ""),
                agent=str(t.get("agent") or ""),
                timestamp=str(t.get("timestamp") or ""),
            )
            for t in (raw.get("turns") or [])
        ]
        return ConversationMemory(
            turns=turns[-80:],
            last_thread_id=str(raw.get("last_thread_id") or ""),
        )

    def save(self, memory: ConversationMemory) -> None:
        write_json(
            self.path,
            {
                "last_thread_id": memory.last_thread_id,
                "turns": [asdict(t) for t in memory.turns[-80:]],
            },
        )

    def add(
        self,
        role: str,
        content: str,
        *,
        agent: str = "",
        thread_id: str = "",
    ) -> ConversationMemory:
        memory = self.load()
        memory.turns.append(
            MemoryTurn(
                role=role,
                content=content[:8000],
                agent=agent,
                timestamp=_now(),
            )
        )
        if thread_id:
            memory.last_thread_id = thread_id
        self.save(memory)
        return memory

    def as_message_dicts(self, limit: int = 12) -> list[dict[str, str]]:
        memory = self.load()
        out: list[dict[str, str]] = []
        for turn in memory.turns[-limit:]:
            out.append({"role": turn.role, "content": turn.content})
        return out

    def context_block(self, limit: int = 8) -> str:
        memory = self.load()
        if not memory.turns:
            return ""
        lines = ["CONVERSATION MEMORY:"]
        for turn in memory.turns[-limit:]:
            who = turn.agent or turn.role
            lines.append(f"- [{who}] {turn.content[:400]}")
        return "\n".join(lines)
