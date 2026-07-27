"""Persistent chat sessions per project."""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.workspace.paths import chats_dir, read_json, write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChatSession:
    id: str
    title: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class SessionStore:
    def __init__(self, project_path: str | Path) -> None:
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.dir = chats_dir(self.project_path)
        self.index_path = self.dir / "index.json"

    def _load_index(self) -> dict:
        return read_json(self.index_path, {"active_id": None, "sessions": []})

    def _save_index(self, index: dict) -> None:
        write_json(self.index_path, index)

    def _session_path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.json"

    def list_sessions(self) -> list[ChatSession]:
        index = self._load_index()
        out: list[ChatSession] = []
        for meta in index.get("sessions") or []:
            sid = meta.get("id")
            if not sid:
                continue
            data = read_json(self._session_path(sid), None)
            if not data:
                out.append(
                    ChatSession(
                        id=sid,
                        title=str(meta.get("title") or "Chat"),
                        created_at=str(meta.get("created_at") or ""),
                        updated_at=str(meta.get("updated_at") or ""),
                    )
                )
                continue
            out.append(
                ChatSession(
                    id=data["id"],
                    title=data.get("title") or "Chat",
                    messages=list(data.get("messages") or []),
                    created_at=data.get("created_at") or "",
                    updated_at=data.get("updated_at") or "",
                )
            )
        out.sort(key=lambda s: s.updated_at or s.created_at, reverse=True)
        return out

    def get(self, session_id: str) -> ChatSession | None:
        data = read_json(self._session_path(session_id), None)
        if not data:
            return None
        return ChatSession(
            id=data["id"],
            title=data.get("title") or "Chat",
            messages=list(data.get("messages") or []),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )

    def create(self, title: str = "New chat") -> ChatSession:
        now = _now()
        session = ChatSession(
            id=uuid.uuid4().hex[:12],
            title=title,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        self._write_session(session)
        index = self._load_index()
        index.setdefault("sessions", []).insert(
            0,
            {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            },
        )
        index["active_id"] = session.id
        self._save_index(index)
        return session

    def save(self, session: ChatSession) -> None:
        session.updated_at = _now()
        self._write_session(session)
        index = self._load_index()
        found = False
        for meta in index.get("sessions") or []:
            if meta.get("id") == session.id:
                meta["title"] = session.title
                meta["updated_at"] = session.updated_at
                found = True
                break
        if not found:
            index.setdefault("sessions", []).insert(
                0,
                {
                    "id": session.id,
                    "title": session.title,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                },
            )
        self._save_index(index)

    def rename(self, session_id: str, title: str) -> None:
        session = self.get(session_id)
        if not session:
            return
        session.title = title.strip() or "Chat"
        self.save(session)

    def delete(self, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
        index = self._load_index()
        index["sessions"] = [
            s for s in (index.get("sessions") or []) if s.get("id") != session_id
        ]
        if index.get("active_id") == session_id:
            index["active_id"] = (
                index["sessions"][0]["id"] if index["sessions"] else None
            )
        self._save_index(index)

    def duplicate(self, session_id: str) -> ChatSession | None:
        original = self.get(session_id)
        if not original:
            return None
        now = _now()
        copy_session = ChatSession(
            id=uuid.uuid4().hex[:12],
            title=f"{original.title} (copy)",
            messages=copy.deepcopy(original.messages),
            created_at=now,
            updated_at=now,
        )
        self._write_session(copy_session)
        index = self._load_index()
        index.setdefault("sessions", []).insert(
            0,
            {
                "id": copy_session.id,
                "title": copy_session.title,
                "created_at": copy_session.created_at,
                "updated_at": copy_session.updated_at,
            },
        )
        index["active_id"] = copy_session.id
        self._save_index(index)
        return copy_session

    def search(self, query: str) -> list[ChatSession]:
        q = query.strip().lower()
        if not q:
            return self.list_sessions()
        matches: list[ChatSession] = []
        for session in self.list_sessions():
            if q in session.title.lower():
                matches.append(session)
                continue
            for msg in session.messages:
                content = str(msg.get("content") or "").lower()
                if q in content:
                    matches.append(session)
                    break
        return matches

    def active_id(self) -> str | None:
        return self._load_index().get("active_id")

    def set_active(self, session_id: str) -> None:
        index = self._load_index()
        index["active_id"] = session_id
        self._save_index(index)

    def ensure_active(self) -> ChatSession:
        aid = self.active_id()
        if aid:
            session = self.get(aid)
            if session:
                return session
        return self.create("New chat")

    def _write_session(self, session: ChatSession) -> None:
        write_json(self._session_path(session.id), asdict(session))
