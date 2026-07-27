"""Rename a symbol across the project — proposes edits only."""

from __future__ import annotations

import re
from pathlib import Path

from src.editing.apply import ProposedEdit, build_proposed_edit
from src.explorer.tree import SKIP_DIRS

TEXT_EXTS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
}


def rename_symbol(
    project_path: str | Path,
    old_name: str,
    new_name: str,
    *,
    limit_files: int = 40,
) -> list[ProposedEdit]:
    """Word-boundary rename across text files. Returns ProposedEdit list (unapplied)."""
    old_name = (old_name or "").strip()
    new_name = (new_name or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return []
    if not re.match(r"^[A-Za-z_][\w]*$", old_name) or not re.match(r"^[A-Za-z_][\w]*$", new_name):
        raise ValueError("Symbol names must be simple identifiers (letters/digits/_).")

    root = Path(project_path).expanduser().resolve()
    pattern = re.compile(rf"\b{re.escape(old_name)}\b")
    edits: list[ProposedEdit] = []

    for path in root.rglob("*"):
        if len(edits) >= limit_files:
            break
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not pattern.search(text):
            continue
        new_text = pattern.sub(new_name, text)
        if new_text == text:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        edits.append(
            build_proposed_edit(
                root,
                rel,
                new_text,
                note=f"rename {old_name} → {new_name}",
            )
        )
    return edits
