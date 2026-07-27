"""Unified session memory across chats + multi-agent turns."""

from __future__ import annotations

from pathlib import Path

from src.multi_agent.memory import ConversationManager
from src.sessions.store import SessionStore


class SessionMemory:
    """Remember previous discussions for the active project."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.chats = SessionStore(self.project_path)
        self.agent = ConversationManager(self.project_path)

    def remember_user(self, text: str) -> None:
        self.agent.add("user", text, agent="user")

    def remember_assistant(self, text: str, *, agent: str = "assistant") -> None:
        self.agent.add("assistant", text, agent=agent)

    def recent_context(self, limit: int = 10) -> str:
        parts = [self.agent.context_block(limit=limit)]
        try:
            session = self.chats.ensure_active()
            for msg in (session.messages or [])[-limit:]:
                role = msg.get("role")
                content = str(msg.get("content") or "")[:300]
                if role and content:
                    parts.append(f"- [chat:{role}] {content}")
        except Exception:
            pass
        return "\n".join(p for p in parts if p)
