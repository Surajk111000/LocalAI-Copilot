"""Multi-project workspace manager (open / switch / recent history)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.workspace.paths import WORKSPACE_STATE_FILE, read_json, write_json


@dataclass
class ProjectEntry:
    path: str
    name: str
    opened_at: str = ""


@dataclass
class WorkspaceState:
    open_projects: list[str] = field(default_factory=list)
    active_project: str | None = None
    recent_projects: list[str] = field(default_factory=list)


class WorkspaceManager:
    """Track opened projects and persist workspace history."""

    def __init__(self, state_file: Path | None = None) -> None:
        self.state_file = state_file or WORKSPACE_STATE_FILE
        self.state = self._load()

    def _load(self) -> WorkspaceState:
        raw = read_json(self.state_file, {})
        return WorkspaceState(
            open_projects=list(raw.get("open_projects") or []),
            active_project=raw.get("active_project"),
            recent_projects=list(raw.get("recent_projects") or []),
        )

    def save(self) -> None:
        write_json(self.state_file, asdict(self.state))

    def open_project(self, path: str | Path) -> str:
        resolved = str(Path(path).expanduser().resolve())
        if not Path(resolved).is_dir():
            raise FileNotFoundError(f"Project folder not found: {resolved}")
        if resolved not in self.state.open_projects:
            self.state.open_projects.append(resolved)
        self.state.active_project = resolved
        self._touch_recent(resolved)
        self.save()
        return resolved

    def close_project(self, path: str) -> None:
        resolved = str(Path(path).expanduser().resolve())
        self.state.open_projects = [p for p in self.state.open_projects if p != resolved]
        if self.state.active_project == resolved:
            self.state.active_project = (
                self.state.open_projects[-1] if self.state.open_projects else None
            )
        self.save()

    def set_active(self, path: str) -> str:
        resolved = str(Path(path).expanduser().resolve())
        if resolved not in self.state.open_projects:
            return self.open_project(resolved)
        self.state.active_project = resolved
        self._touch_recent(resolved)
        self.save()
        return resolved

    def list_open(self) -> list[ProjectEntry]:
        entries: list[ProjectEntry] = []
        for path in list(self.state.open_projects):
            p = Path(path)
            if not p.exists():
                self.state.open_projects = [x for x in self.state.open_projects if x != path]
                continue
            entries.append(ProjectEntry(path=path, name=p.name))
        self.save()
        return entries

    def list_recent(self, limit: int = 10) -> list[ProjectEntry]:
        out: list[ProjectEntry] = []
        for path in self.state.recent_projects[:limit]:
            p = Path(path)
            out.append(ProjectEntry(path=path, name=p.name if p.name else path))
        return out

    def active(self) -> str | None:
        if self.state.active_project and Path(self.state.active_project).is_dir():
            return self.state.active_project
        if self.state.open_projects:
            return self.set_active(self.state.open_projects[0])
        return None

    def _touch_recent(self, path: str) -> None:
        recent = [p for p in self.state.recent_projects if p != path]
        recent.insert(0, path)
        self.state.recent_projects = recent[:20]
