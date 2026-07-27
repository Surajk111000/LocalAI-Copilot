"""Paths and IDs for per-project memory (chats, settings, chroma, activity)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.config import ROOT_DIR

WORKSPACE_ROOT = ROOT_DIR / "memory" / "workspaces"
PROJECTS_ROOT = ROOT_DIR / "memory" / "projects"
WORKSPACE_STATE_FILE = WORKSPACE_ROOT / "workspace_state.json"


def project_id_for_path(project_path: str | Path) -> str:
    resolved = str(Path(project_path).expanduser().resolve())
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]


def project_dir(project_path: str | Path) -> Path:
    path = PROJECTS_ROOT / project_id_for_path(project_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def chats_dir(project_path: str | Path) -> Path:
    path = project_dir(project_path) / "chats"
    path.mkdir(parents=True, exist_ok=True)
    return path


def chroma_dir(project_path: str | Path) -> Path:
    path = project_dir(project_path) / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path(project_path: str | Path) -> Path:
    return project_dir(project_path) / "settings.json"


def activity_path(project_path: str | Path) -> Path:
    return project_dir(project_path) / "activity.json"


def context_path(project_path: str | Path) -> Path:
    return project_dir(project_path) / "context.json"


def versions_dir(project_path: str | Path) -> Path:
    path = project_dir(project_path) / "versions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def versions_index_path(project_path: str | Path) -> Path:
    return versions_dir(project_path) / "index.json"


def plans_dir(project_path: str | Path) -> Path:
    path = project_dir(project_path) / "plans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
