"""Proposed edits, safe apply, and approval helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.editing.diff import change_stats, unified_diff
from src.editing.versions import VersionStore
from src.tools.filesystem import FileSystemTools, PendingWrite, SKIP_DIRS


@dataclass
class ProposedEdit:
    """One file change awaiting explicit user approval."""

    path: str
    new_content: str
    old_content: str = ""
    is_new: bool = False
    absolute_path: str = ""
    note: str = ""
    status: str = "pending"  # pending | accepted | rejected

    def to_pending_write(self) -> PendingWrite:
        return PendingWrite(
            path=self.path,
            content=self.new_content,
            absolute_path=self.absolute_path,
            is_new=self.is_new,
        )

    def stats(self) -> dict[str, int]:
        return change_stats(self.old_content, self.new_content)

    def unified(self) -> str:
        return unified_diff(self.old_content, self.new_content, self.path)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProposedEdit":
        return cls(
            path=str(data.get("path") or ""),
            new_content=str(data.get("new_content") or ""),
            old_content=str(data.get("old_content") or ""),
            is_new=bool(data.get("is_new", False)),
            absolute_path=str(data.get("absolute_path") or ""),
            note=str(data.get("note") or ""),
            status=str(data.get("status") or "pending"),
        )


@dataclass
class EditBatch:
    """Multi-file edit set from an approved plan."""

    id: str
    goal: str
    edits: list[ProposedEdit] = field(default_factory=list)
    status: str = "pending"  # pending | partial | applied | rejected


def build_proposed_edit(project_path: str | Path, relative_path: str, new_content: str, note: str = "") -> ProposedEdit:
    tools = FileSystemTools(project_path)
    target = tools.resolve(relative_path)
    if any(part in SKIP_DIRS for part in target.relative_to(tools.root).parts[:-1]):
        raise PermissionError(f"Refusing protected path: {relative_path}")
    rel = str(target.relative_to(tools.root)).replace("\\", "/")
    is_new = not target.exists()
    old = ""
    if not is_new and target.is_file():
        old = target.read_text(encoding="utf-8", errors="replace")
    return ProposedEdit(
        path=rel,
        new_content=new_content,
        old_content=old,
        is_new=is_new,
        absolute_path=str(target),
        note=note,
    )


def apply_edit(
    project_path: str | Path,
    edit: ProposedEdit,
    *,
    note: str = "",
    batch_id: str | None = None,
    record_history: bool = True,
) -> tuple[bool, str]:
    """Write one approved edit and optionally snapshot for undo."""
    tools = FileSystemTools(project_path)
    pending = edit.to_pending_write()
    if record_history:
        store = VersionStore(project_path)
        store.snapshot_and_record(
            path=edit.path,
            new_content=edit.new_content,
            previous_content=edit.old_content,
            is_new=edit.is_new,
            note=note or edit.note or "accepted edit",
            batch_id=batch_id,
        )
    result = tools.apply_write(pending)
    return result.ok, result.output


def apply_edits(
    project_path: str | Path,
    edits: list[ProposedEdit],
    *,
    note: str = "",
    batch_id: str | None = None,
) -> list[tuple[str, bool, str]]:
    import uuid

    bid = batch_id or uuid.uuid4().hex[:12]
    results: list[tuple[str, bool, str]] = []
    for edit in edits:
        if edit.status == "rejected":
            results.append((edit.path, False, "skipped (rejected)"))
            continue
        ok, msg = apply_edit(
            project_path,
            edit,
            note=note,
            batch_id=bid,
        )
        results.append((edit.path, ok, msg))
    return results
