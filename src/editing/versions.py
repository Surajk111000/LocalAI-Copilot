"""Version history + undo for accepted file edits."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.workspace.paths import project_dir, read_json, write_json

# Prefer helpers from paths; keep local fallbacks so a stale paths.py never crashes the UI.
try:
    from src.workspace.paths import versions_dir, versions_index_path
except ImportError:  # pragma: no cover

    def versions_dir(project_path: str | Path) -> Path:
        path = project_dir(project_path) / "versions"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def versions_index_path(project_path: str | Path) -> Path:
        return versions_dir(project_path) / "index.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FileVersion:
    id: str
    path: str
    content: str
    previous_content: str
    is_new: bool
    note: str = ""
    created_at: str = ""
    batch_id: str = ""


@dataclass
class VersionBatch:
    id: str
    note: str
    created_at: str
    versions: list[str] = field(default_factory=list)  # version ids


class VersionStore:
    """Store every accepted modification so the user can undo."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.root = Path(self.project_path)
        self.dir = versions_dir(self.project_path)
        self.index_path = versions_index_path(self.project_path)

    def _load_index(self) -> dict:
        return read_json(self.index_path, {"batches": [], "versions": []})

    def _save_index(self, index: dict) -> None:
        write_json(self.index_path, index)

    def snapshot_and_record(
        self,
        *,
        path: str,
        new_content: str,
        previous_content: str,
        is_new: bool,
        note: str = "",
        batch_id: str | None = None,
    ) -> FileVersion:
        vid = uuid.uuid4().hex[:12]
        bid = batch_id or uuid.uuid4().hex[:12]
        version = FileVersion(
            id=vid,
            path=path.replace("\\", "/"),
            content=new_content,
            previous_content=previous_content,
            is_new=is_new,
            note=note,
            created_at=_now(),
            batch_id=bid,
        )
        write_json(self.dir / f"{vid}.json", asdict(version))
        index = self._load_index()
        index.setdefault("versions", []).insert(0, {
            "id": version.id,
            "path": version.path,
            "batch_id": version.batch_id,
            "note": version.note,
            "created_at": version.created_at,
            "is_new": version.is_new,
        })
        batches = index.setdefault("batches", [])
        found = False
        for batch in batches:
            if batch.get("id") == bid:
                batch.setdefault("versions", []).append(vid)
                found = True
                break
        if not found:
            batches.insert(
                0,
                {
                    "id": bid,
                    "note": note,
                    "created_at": version.created_at,
                    "versions": [vid],
                },
            )
        # Keep history bounded
        index["versions"] = index["versions"][:200]
        index["batches"] = batches[:100]
        self._save_index(index)
        return version

    def list_recent(self, limit: int = 30) -> list[dict]:
        return list(self._load_index().get("versions") or [])[:limit]

    def list_batches(self, limit: int = 20) -> list[dict]:
        return list(self._load_index().get("batches") or [])[:limit]

    def get(self, version_id: str) -> FileVersion | None:
        data = read_json(self.dir / f"{version_id}.json", None)
        if not data:
            return None
        return FileVersion(**data)

    def undo_version(self, version_id: str) -> tuple[bool, str]:
        """Restore the file to previous_content (or delete if it was new)."""
        version = self.get(version_id)
        if not version:
            return False, f"Version not found: {version_id}"
        target = (self.root / version.path).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            return False, "Path escapes project root"
        try:
            if version.is_new:
                if target.exists():
                    target.unlink()
                msg = f"Undid create — deleted `{version.path}`"
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(version.previous_content, encoding="utf-8")
                msg = f"Restored previous version of `{version.path}`"
            # Record the undo itself as a new version entry
            current = version.content if not version.is_new or target.exists() else ""
            if version.is_new:
                current = version.content
            self.snapshot_and_record(
                path=version.path,
                new_content=version.previous_content if not version.is_new else "",
                previous_content=current,
                is_new=False,
                note=f"undo:{version.id}",
            )
            return True, msg
        except OSError as exc:
            return False, str(exc)

    def undo_latest(self) -> tuple[bool, str]:
        recent = self.list_recent(1)
        if not recent:
            return False, "No version history to undo."
        return self.undo_version(recent[0]["id"])

    def undo_batch(self, batch_id: str) -> tuple[bool, str]:
        index = self._load_index()
        batch = next((b for b in index.get("batches") or [] if b.get("id") == batch_id), None)
        if not batch:
            return False, f"Batch not found: {batch_id}"
        # Undo in reverse order
        messages: list[str] = []
        for vid in reversed(list(batch.get("versions") or [])):
            ok, msg = self.undo_version(vid)
            messages.append(msg)
            if not ok:
                return False, "; ".join(messages)
        return True, f"Undid batch {batch_id}: " + "; ".join(messages)
