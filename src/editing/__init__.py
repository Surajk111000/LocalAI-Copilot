"""Editing package: diffs, version history, safe apply.

Import from submodules directly when possible, e.g.:
    from src.editing.apply import ProposedEdit, build_proposed_edit
"""

from __future__ import annotations

__all__ = [
    "EditBatch",
    "ProposedEdit",
    "VersionStore",
    "apply_edit",
    "apply_edits",
    "build_proposed_edit",
    "change_stats",
    "side_by_side_hunks",
    "unified_diff",
]


def __getattr__(name: str):
    if name in {"EditBatch", "ProposedEdit", "apply_edit", "apply_edits", "build_proposed_edit"}:
        from src.editing import apply as _apply

        return getattr(_apply, name)
    if name == "VersionStore":
        from src.editing.versions import VersionStore

        return VersionStore
    if name in {"change_stats", "side_by_side_hunks", "unified_diff"}:
        from src.editing import diff as _diff

        return getattr(_diff, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
