"""Build a text overview of a local project folder for 'Explain this project'.

Works for Python, React/Vite, Node, etc. Reads folder structure plus important
source/config files. Does NOT dump the entire repo (context/speed limits).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "memory",
    ".ollama",
    "dist",
    "build",
    ".cursor",
    ".next",
    "coverage",
    "public",  # often binary assets; still show in tree
}

# Skip binary / huge asset types when reading file contents
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".exe",
    ".dll",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".jfif",
    ".lock",
}

PRIORITY_FILES = (
    # Docs first
    "README.md",
    "readme.md",
    "QUICKSTART.md",
    "DEPLOYMENT.md",
    # App entrypoints / source before package.json so the model sees real code early
    "index.html",
    "src/main.jsx",
    "src/main.tsx",
    "src/main.js",
    "src/main.ts",
    "src/App.jsx",
    "src/App.tsx",
    "src/App.js",
    "src/index.js",
    "src/index.tsx",
    "src/index.css",
    "src/data/portfolioData.js",
    "app.py",
    "main.py",
    "src/config.py",
    "ui/streamlit_app.py",
    # Config last (models often over-focus on package.json if it comes first)
    "package.json",
    "vite.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.mjs",
    "tailwind.config.js",
    "tailwind.config.ts",
    "postcss.config.js",
    "netlify.toml",
    "vercel.json",
    "pyproject.toml",
    "requirements.txt",
    "tsconfig.json",
    "jsconfig.json",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
)

# Prefer source under these folders (in order)
SOURCE_DIRS = (
    "src",
    "src/pages",
    "src/components",
    "src/data",
    "src/hooks",
    "src/lib",
    "src/utils",
    "pages",
    "components",
    "app",
    "ui",
    "agents",
    "tools",
    "rag",
)

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".scss",
    ".html",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
}

MAX_FILE_CHARS = 2800
MAX_TOTAL_CHARS = 22_000
MAX_TREE_ENTRIES = 180
MAX_SOURCE_FILES = 18


@dataclass
class ProjectOverview:
    project_path: str
    context: str
    files_used: list[str]
    kind: str = "folder"  # "folder" | "file"


def wants_project_explanation(prompt: str) -> bool:
    """Detect prompts that need automatic project-folder reading."""
    text = (prompt or "").lower().strip()
    triggers = (
        "explain this project",
        "explain the project",
        "what is this project",
        "what's this project",
        "describe this project",
        "summarize this project",
        "overview of this project",
        "project architecture",
        "how does this project work",
        "explain my project",
        "explain this folder",
        "explain this file",
        "explain this code",
        "explain the code",
        "explain selected path",
    )
    return any(t in text for t in triggers)


def build_path_context(target: str | Path) -> ProjectOverview:
    """Explain either a local folder or a single local file."""
    path = Path(str(target).strip().strip('"').strip("'")).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    if path.is_file():
        return build_file_overview(path)
    if path.is_dir():
        return build_project_overview(path)
    raise FileNotFoundError(f"Not a file or folder: {path}")


def build_file_overview(file_path: Path) -> ProjectOverview:
    """Read one file and prepare context for code explanation."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read file: {file_path}") from exc

    snippet = text[: MAX_FILE_CHARS * 3]
    if len(text) > len(snippet):
        snippet += "\n… truncated …"

    context = (
        f"FILE PATH: {file_path}\n"
        f"FILE NAME: {file_path.name}\n\n"
        f"FILE CONTENTS:\n```\n{snippet}\n```\n"
    )
    return ProjectOverview(
        project_path=str(file_path),
        context=context,
        files_used=[file_path.name],
        kind="file",
    )


def build_project_overview(project_path: str | Path) -> ProjectOverview:
    """Read a folder and return prompt-ready context + file list."""
    root = Path(project_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Project folder not found: {root}")

    tree = _build_tree(root)
    candidates = _candidate_files(root)

    parts: list[str] = [
        f"PROJECT PATH: {root}",
        "",
        "TASK: Explain the WHOLE project, not only package.json.",
        "You must cover folder structure + main source files (App, pages, components).",
        "",
        "FILES INCLUDED IN THIS CONTEXT:",
        ", ".join(candidates) if candidates else "(structure only)",
        "",
        "FOLDER STRUCTURE:",
        tree,
        "",
        "KEY FILE CONTENTS:",
    ]
    files_used: list[str] = ["(folder structure)"] + [
        c.replace("\\", "/") for c in candidates
    ]
    total = sum(len(p) for p in parts)

    for rel in candidates:
        path = root / rel
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.strip():
            continue
        # Keep package.json short so the model does not spend the whole answer on it
        limit = 1200 if path.name.lower() == "package.json" else MAX_FILE_CHARS
        snippet = text[:limit]
        if len(text) > limit:
            snippet += "\n… truncated …"
        block = f"\nFILE: {rel}\n```\n{snippet}\n```\n"
        if total + len(block) > MAX_TOTAL_CHARS:
            parts.append(
                "\n(Additional source files omitted to fit model context limits.)\n"
            )
            break
        parts.append(block)
        total += len(block)

    if len(candidates) == 0:
        parts.append(
            "\n(No readable source/config files found beyond the folder tree.)\n"
        )

    # Deduplicate files_used preserving order, only those we actually care about
    unique_files: list[str] = []
    seen_files: set[str] = set()
    for item in files_used:
        if item not in seen_files:
            seen_files.add(item)
            unique_files.append(item)

    return ProjectOverview(
        project_path=str(root),
        context="\n".join(parts),
        files_used=unique_files,
        kind="folder",
    )


def _candidate_files(root: Path) -> list[str]:
    """Pick the most useful files for explaining any local project."""
    found: list[str] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        key = rel.replace("\\", "/").lower()
        if key in seen:
            return
        path = root / rel
        if not path.is_file():
            return
        if path.suffix.lower() in SKIP_SUFFIXES:
            return
        seen.add(key)
        found.append(rel.replace("\\", "/"))

    for name in PRIORITY_FILES:
        add(name)

    # Collect source files from common project folders
    scored: list[tuple[int, str]] = []
    for folder_name in SOURCE_DIRS:
        folder = root / folder_name
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            # Deprioritize giant CSS / lockfiles style noise
            if path.name.lower() in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            rank = 0
            lower = rel.lower()
            if lower.endswith(("app.jsx", "app.tsx", "main.jsx", "main.tsx", "main.py")):
                rank -= 20
            if "/pages/" in lower or "/components/" in lower:
                rank -= 10
            if "/data/" in lower:
                rank -= 5
            if lower.endswith(".css"):
                rank += 5
            scored.append((rank, rel))

    for _, rel in sorted(scored):
        add(rel)
        if len(found) >= MAX_SOURCE_FILES:
            break

    # Top-level useful configs not already covered
    for path in sorted(root.glob("*")):
        if path.is_file() and path.suffix.lower() in {".js", ".ts", ".json", ".toml", ".md"}:
            add(path.name)
        if len(found) >= MAX_SOURCE_FILES + 6:
            break

    return found


def _build_tree(root: Path) -> str:
    lines: list[str] = ["."]
    count = 1

    def walk(current: Path, prefix: str = "", depth: int = 0) -> None:
        nonlocal count
        if depth > 5:
            return
        try:
            children = sorted(
                current.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            return
        visible = [
            c
            for c in children
            if c.name not in SKIP_DIRS and not c.name.startswith(".")
        ]
        # Keep trees readable: skip dumping huge image folders' every file
        if current.name.lower() in {"image", "images", "assets", "static"}:
            visible = [c for c in visible if c.is_dir()][:3] + [
                c for c in visible if c.is_file()
            ][:5]

        for i, child in enumerate(visible):
            if count >= MAX_TREE_ENTRIES:
                lines.append(prefix + "└── …")
                return
            connector = "└── " if i == len(visible) - 1 else "├── "
            name = child.name + ("/" if child.is_dir() else "")
            lines.append(prefix + connector + name)
            count += 1
            if child.is_dir():
                extension = "    " if i == len(visible) - 1 else "│   "
                walk(child, prefix + extension, depth + 1)

    walk(root)
    return "\n".join(lines)
