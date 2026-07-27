"""Explorer file actions: rename, delete, read, copy path, etc."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ActionResult:
    ok: bool
    message: str
    path: str = ""
    content: str = ""


def resolve_under_root(root: str | Path, rel_path: str) -> Path:
    root_path = Path(root).expanduser().resolve()
    target = (root_path / rel_path).resolve()
    if not str(target).startswith(str(root_path)):
        raise PermissionError("Path escapes project root")
    return target


def read_file(root: str | Path, rel_path: str, max_chars: int = 80_000) -> ActionResult:
    try:
        target = resolve_under_root(root, rel_path)
        if not target.is_file():
            return ActionResult(False, f"Not a file: {rel_path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        msg = f"Read {rel_path}" + (" (truncated)" if truncated else "")
        return ActionResult(True, msg, path=rel_path, content=text)
    except Exception as exc:  # noqa: BLE001
        return ActionResult(False, str(exc), path=rel_path)


def rename_path(root: str | Path, rel_path: str, new_name: str) -> ActionResult:
    try:
        target = resolve_under_root(root, rel_path)
        if not target.exists():
            return ActionResult(False, f"Not found: {rel_path}")
        new_name = new_name.strip()
        if not new_name or "/" in new_name or "\\" in new_name:
            return ActionResult(False, "Invalid new name")
        dest = target.with_name(new_name)
        if dest.exists():
            return ActionResult(False, f"Already exists: {new_name}")
        target.rename(dest)
        new_rel = str(dest.relative_to(Path(root).resolve())).replace("\\", "/")
        return ActionResult(True, f"Renamed to {new_rel}", path=new_rel)
    except Exception as exc:  # noqa: BLE001
        return ActionResult(False, str(exc), path=rel_path)


def delete_path(root: str | Path, rel_path: str) -> ActionResult:
    try:
        target = resolve_under_root(root, rel_path)
        if not target.exists():
            return ActionResult(False, f"Not found: {rel_path}")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return ActionResult(True, f"Deleted {rel_path}", path=rel_path)
    except Exception as exc:  # noqa: BLE001
        return ActionResult(False, str(exc), path=rel_path)


def copy_path_text(root: str | Path, rel_path: str, absolute: bool = True) -> ActionResult:
    try:
        target = resolve_under_root(root, rel_path)
        text = str(target) if absolute else rel_path.replace("\\", "/")
        return ActionResult(True, "Path ready to copy", path=text, content=text)
    except Exception as exc:  # noqa: BLE001
        return ActionResult(False, str(exc), path=rel_path)
