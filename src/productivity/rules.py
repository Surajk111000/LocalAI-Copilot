"""Load project conventions from a `.rules` folder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RULE_NAMES = (
    "README.md",
    "rules.md",
    "conventions.md",
    "coding.md",
    "style.md",
    "security.md",
)


@dataclass
class ProjectRules:
    files: list[str]
    text: str

    @property
    def empty(self) -> bool:
        return not self.text.strip()


def load_project_rules(project_path: str | Path, max_chars: int = 12_000) -> ProjectRules:
    """Read `.rules/` (and optional `.cursorrules` / `AGENTS.md`) into one block."""
    root = Path(project_path).expanduser().resolve()
    chunks: list[str] = []
    files: list[str] = []

    # Cursor-compatible single files
    for name in (".cursorrules", "AGENTS.md", ".rulerules"):
        path = root / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files.append(name)
            chunks.append(f"### {name}\n{text.strip()}")

    rules_dir = root / ".rules"
    if rules_dir.is_dir():
        candidates = sorted(rules_dir.glob("*.md")) + sorted(rules_dir.glob("*.txt"))
        # Prefer known names first
        ordered: list[Path] = []
        for preferred in RULE_NAMES:
            p = rules_dir / preferred
            if p.exists():
                ordered.append(p)
        for p in candidates:
            if p not in ordered:
                ordered.append(p)
        for path in ordered:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            files.append(rel)
            chunks.append(f"### {rel}\n{text.strip()}")

    combined = "\n\n".join(chunks)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n… truncated …"
    return ProjectRules(files=files, text=combined)


def ensure_sample_rules(project_path: str | Path) -> Path:
    """Create a starter `.rules/README.md` if missing."""
    root = Path(project_path).expanduser().resolve()
    rules_dir = root / ".rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    readme = rules_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Project rules\n\n"
            "- Prefer clear, typed Python.\n"
            "- Never commit secrets.\n"
            "- All file writes require user approval in the copilot UI.\n"
            "- Keep changes minimal and focused.\n",
            encoding="utf-8",
        )
    return readme
