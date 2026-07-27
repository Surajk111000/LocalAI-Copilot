"""Recent activity tracking per project."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from src.workspace.paths import activity_path, read_json, write_json

ActivityKind = Literal["file", "search", "prompt", "edit"]


@dataclass
class ActivityItem:
    kind: ActivityKind
    text: str
    path: str = ""
    timestamp: str = ""


class ActivityStore:
    def __init__(self, project_path: str | Path, limit: int = 50) -> None:
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.path = activity_path(self.project_path)
        self.limit = limit

    def _load_raw(self) -> list[dict]:
        raw = read_json(self.path, {"items": []})
        return list(raw.get("items") or [])

    def list(self, kind: ActivityKind | None = None, limit: int = 20) -> list[ActivityItem]:
        items = self._load_raw()
        out: list[ActivityItem] = []
        for item in items:
            if kind and item.get("kind") != kind:
                continue
            out.append(
                ActivityItem(
                    kind=item.get("kind", "prompt"),
                    text=str(item.get("text") or ""),
                    path=str(item.get("path") or ""),
                    timestamp=str(item.get("timestamp") or ""),
                )
            )
            if len(out) >= limit:
                break
        return out

    def add(self, kind: ActivityKind, text: str, path: str = "") -> None:
        items = self._load_raw()
        entry = {
            "kind": kind,
            "text": text[:500],
            "path": path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Deduplicate consecutive identical entries.
        if items and items[0].get("kind") == kind and items[0].get("text") == entry["text"]:
            items[0] = entry
        else:
            items.insert(0, entry)
        write_json(self.path, {"items": items[: self.limit]})
