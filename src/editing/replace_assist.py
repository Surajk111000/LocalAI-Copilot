"""Deterministic text-replace assist — propose diffs like Cursor/Codex.

For prompts such as "change Suraj Kumar to Akash" or "title from X to Y",
search the project, apply replacements in memory, and return ProposedEdit
objects for Accept/Reject. No LLM advice steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.editing.apply import ProposedEdit, build_proposed_edit
from src.tools.filesystem import FileSystemTools

SKIP_DIR_PARTS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    "coverage",
    ".cache",
}

TEXT_SUFFIXES = {
    ".html",
    ".htm",
    ".jsx",
    ".tsx",
    ".js",
    ".ts",
    ".css",
    ".scss",
    ".json",
    ".md",
    ".txt",
    ".py",
    ".yaml",
    ".yml",
    ".toml",
    ".vue",
    ".svelte",
}


@dataclass
class ReplacePlan:
    old: str
    new: str
    edits: list[ProposedEdit]
    summary: str


def extract_abs_project_path(prompt: str) -> str | None:
    """Pull a Windows/Unix absolute path out of a chat message."""
    text = prompt or ""
    patterns = [
        # Stop at whitespace so "G:\proj change title" keeps the command text
        r'([A-Za-z]:\\(?:[^\s\\/:*?"<>|]+\\)*[^\s\\/:*?"<>|]*)',
        r'(/?(?:Users|home|mnt|Projects|var|opt)/[^\s"\']+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        raw = match.group(1).rstrip(".,;:)")
        path = Path(raw)
        if path.exists():
            return str(path.resolve())
    return None


def extract_replace_pair(prompt: str) -> tuple[str, str] | None:
    """Detect 'from X to Y' / 'change X to Y' / title renames."""
    text = (prompt or "").strip()
    # Strip a leading absolute path so it does not become part of X
    text = re.sub(
        r'^[A-Za-z]:\\(?:[^\s\\/:*?"<>|]+\\)*[^\s\\/:*?"<>|]*\s*',
        "",
        text,
    ).strip()
    # Drop soft filler prefixes (may appear more than once)
    for _ in range(3):
        updated = re.sub(
            r"(?i)^(in\s+the\s+project|please|pls|can you|could you|the)[,:]?\s+",
            "",
            text,
        ).strip()
        if updated == text:
            break
        text = updated

    patterns = [
        # title of website from X to Y / tittle … (common typo)
        r"(?i)\btitt?le(?:\s+of\s+(?:the\s+)?(?:website|site|page|app))?\s+(?:from\s+)?(.+?)\s+to\s+(.+?)\s*$",
        r"(?i)\b(?:change|rename|update|replace|set)\s+(?:the\s+)?(?:website\s+|site\s+|page\s+)?titt?le\s+(?:from\s+)?(.+?)\s+to\s+(.+?)\s*$",
        r"(?i)\bfrom\s+(.+?)\s+to\s+(.+?)\s*$",
        r"(?i)\b(?:change|rename|update|replace)\s+(.+?)\s+to\s+(.+?)\s*$",
        r"(?i)\b(?:change|rename|update)\s+(?:the\s+)?name\s+(?:from\s+)?(.+?)\s+to\s+(.+?)\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        old = _clean_phrase(match.group(1))
        new = _clean_phrase(match.group(2))
        if old and new and old.lower() != new.lower():
            return old, new
    return None


def _clean_phrase(value: str) -> str:
    text = (value or "").strip().strip("\"'`")
    text = re.sub(r"(?i)^(the\s+)?(website|site|page|app|project)\s+", "", text).strip()
    text = re.sub(r"(?i)\s+in\s+(the\s+)?project$", "", text).strip()
    # "please the title of website from suraj" — leftover junk
    text = re.sub(r"(?i)^(please|pls)\s+", "", text).strip()
    return text.strip(" .,;:")


def wants_text_replace(prompt: str) -> bool:
    return extract_replace_pair(prompt) is not None


def _should_skip(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & {s.lower() for s in SKIP_DIR_PARTS}:
        return True
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return True
    return False


def _variants(old: str) -> list[str]:
    """Common casing variants for a display name."""
    old = old.strip()
    variants = [old]
    if old.lower() not in {v.lower() for v in variants}:
        variants.append(old.lower())
    titled = old.title()
    if titled not in variants:
        variants.append(titled)
    upper = old.upper()
    if len(old) <= 4 and upper not in variants:
        variants.append(upper)
    # Prefer longer matches first
    variants.sort(key=len, reverse=True)
    # Dedupe case-sensitive
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def propose_text_replacements(
    project_path: str | Path,
    old: str,
    new: str,
    *,
    max_files: int = 20,
) -> ReplacePlan:
    """Search project for `old`, propose file edits replacing with `new`."""
    root = Path(project_path).expanduser().resolve()
    tools = FileSystemTools(str(root))
    variants = _variants(old)
    # Search with the longest / original phrase
    search_term = variants[0]
    result = tools.search_files(search_term, ".")
    hit_paths: list[str] = []
    if result.ok:
        for line in result.output.splitlines():
            # Typical format: path:line:content or path
            rel = line.split(":", 1)[0].strip()
            if rel and rel not in hit_paths:
                hit_paths.append(rel)

    # Always check common brand/title files even if search misses
    for candidate in (
        "index.html",
        "index.htm",
        "public/index.html",
        "src/components/Navbar.jsx",
        "src/components/Navbar.tsx",
        "src/data/portfolioData.js",
        "src/data/portfolioData.ts",
        "package.json",
        "README.md",
    ):
        if (root / candidate).is_file() and candidate not in hit_paths:
            hit_paths.append(candidate)

    edits: list[ProposedEdit] = []
    touched: list[str] = []
    for rel in hit_paths:
        if len(edits) >= max_files:
            break
        path = root / rel
        if not path.is_file() or _should_skip(path):
            continue
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        updated = original
        for variant in variants:
            if variant in updated:
                # Preserve simple Title Case for the replacement when variant was titled
                replacement = new
                if variant == variant.title() and new == new.lower():
                    replacement = new.title()
                elif variant == variant.upper() and len(variant) <= 4:
                    replacement = new.upper()
                updated = updated.replace(variant, replacement)
        if updated == original:
            # Case-insensitive fallback for the primary phrase
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            if not pattern.search(original):
                continue
            updated = pattern.sub(new, original)
        if updated == original:
            continue
        try:
            rel_norm = str(path.resolve().relative_to(root)).replace("\\", "/")
        except ValueError:
            rel_norm = rel.replace("\\", "/")
        edits.append(
            build_proposed_edit(
                root,
                rel_norm,
                updated,
                note=f"replace `{old}` → `{new}`",
            )
        )
        touched.append(rel_norm)

    summary = (
        f"Proposed replacing **`{old}` → `{new}`** in {len(edits)} file(s):\n"
        + ("\n".join(f"- `{p}`" for p in touched) or "- (no matches found)")
        + "\n\nReview the **diff panel** and click **Accept** to write changes to disk."
    )
    return ReplacePlan(old=old, new=new, edits=edits, summary=summary)
