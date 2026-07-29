"""Deterministic handlers for common UI commands (list / read / create).

These run against the pasted/active project path without needing the Tools toggle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.tools.filesystem import FileSystemTools, PendingWrite


@dataclass
class QuickActionResult:
    kind: str  # list | read | create | none
    context: str = ""
    sources: list[str] | None = None
    pending_write: PendingWrite | None = None
    effective_prompt: str | None = None
    info: str = ""


def wants_list_files(prompt: str) -> bool:
    text = (prompt or "").lower()
    return any(
        t in text
        for t in (
            "list the project files",
            "list project files",
            "list the files",
            "list files",
            "list directory",
            "show project structure",
            "show folder structure",
            "what files are in",
        )
    )


def wants_read_file(prompt: str) -> bool:
    text = (prompt or "").lower()
    return bool(
        re.search(r"(?i)\b(read|open|show|explain)\b.+\.(py|md|txt|yaml|yml|json|toml)\b", text)
        or re.search(r"(?i)\bread\s+[\w./\\-]+", text)
    )


def wants_code_edit(prompt: str) -> bool:
    """True when the user wants to change existing code (not create a brand-new file)."""
    text = (prompt or "").lower().strip()
    phrases = (
        "add a function",
        "add function",
        "add a method",
        "add a class",
        "add an endpoint",
        "add endpoint",
        "add a helper",
        "implement ",
        "refactor ",
        "fix ",
        "modify ",
        "update the",
        "update this",
        "change the",
        "change ",
        "edit this",
        "edit the",
        "insert ",
        "remove the",
        "delete the",
        "add jwt",
        "add auth",
        "add authentication",
        "rename ",
        "replace ",
        "title of",
        "tittle",
        "website title",
        "site title",
    )
    if any(p in text for p in phrases):
        return True
    # "from Suraj Kumar to Akash"
    if re.search(r"(?i)\bfrom\b.+\bto\b", text):
        return True
    # e.g. "add validation to src/main.py"
    if re.search(
        r"(?i)\b(add|implement|update|modify|refactor|fix|change)\b.+\b(to|in|into)\b.+\.\w+",
        text,
    ):
        return True
    return False


def wants_create_file(prompt: str) -> bool:
    text = (prompt or "").lower()
    # "Add a function to main.py" is an edit, not a new-file create.
    if wants_code_edit(prompt):
        explicit_new = any(
            t in text
            for t in (
                "create file",
                "create a file",
                "add a file",
                "new file",
                "make a file",
                "create examples/",
            )
        )
        if not explicit_new:
            return False
    return any(
        t in text
        for t in (
            "create file",
            "create a file",
            "create examples/",
            "write file",
            "add a file",
            "make a file",
            "generate file",
        )
    ) or bool(
        re.search(
            r"(?i)\b(create|write|generate)\b.+\.(py|md|txt|yaml|yml|json)\b",
            text,
        )
    )


def extract_file_path(prompt: str) -> str | None:
    """Best-effort extract of a relative file path from a command."""
    patterns = [
        r"(?i)\b(?:read|open|show|explain|create|write|add|generate)\s+(?:the\s+file\s+)?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)",
        r"(?i)\b([A-Za-z0-9_./\\-]+\.(?:py|md|txt|yaml|yml|json|toml))\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt or "")
        if match:
            return match.group(1).replace("\\", "/")
    return None


def handle_list(project_path: str) -> QuickActionResult:
    tools = FileSystemTools(project_path)
    listed = tools.list_directory(".")
    # Also list a couple of important subfolders for a richer overview
    extras = []
    for sub in ("src", "ui", "config", "tests", "agents", "tools"):
        sub_list = tools.list_directory(sub)
        if sub_list.ok and "Not found" not in sub_list.output:
            extras.append(f"\n[{sub}/]\n{sub_list.output}")
    body = listed.output + "".join(extras)
    context = (
        f"PROJECT PATH: {project_path}\n\n"
        f"FILE LISTING:\n{body}\n"
    )
    return QuickActionResult(
        kind="list",
        context=context,
        sources=["."],
        effective_prompt=(
            "Using ONLY the FILE LISTING, describe the project structure.\n"
            "Group by folders and mention important files. Do not invent files."
        ),
        info=f"Listed files in `{project_path}`",
    )


def handle_read(project_path: str, prompt: str) -> QuickActionResult:
    rel = extract_file_path(prompt) or "src/config.py"
    tools = FileSystemTools(project_path)
    read = tools.read_file(rel)
    context = (
        f"PROJECT PATH: {project_path}\n"
        f"REQUESTED FILE: {rel}\n\n"
        f"{read.output}\n"
    )
    return QuickActionResult(
        kind="read",
        context=context,
        sources=[rel],
        effective_prompt=(
            f"Using ONLY the file contents for `{rel}`, explain what this file does.\n"
            "Cover purpose, important functions/classes, and how other parts may use it.\n"
            "If the file was not found, say so clearly."
        ),
        info=f"Read `{rel}` from `{project_path}`",
    )


def handle_create_prepare(project_path: str, prompt: str) -> QuickActionResult:
    """Prepare a create-file request. Content is generated by the LLM next."""
    rel = extract_file_path(prompt) or "examples/hello.py"
    return QuickActionResult(
        kind="create",
        context=f"PROJECT PATH: {project_path}\nTARGET FILE: {rel}\n",
        sources=[rel],
        effective_prompt=(
            f"Create the full contents for the file `{rel}` based on this request:\n"
            f"{prompt}\n\n"
            "Reply with:\n"
            "1) A short explanation (2-4 sentences)\n"
            "2) Then ONE markdown code block containing the FULL file content only.\n"
            "Do not ask questions. Make the code complete and runnable."
        ),
        info=f"Will propose creating `{rel}` (needs your Approve write)",
    )


def propose_write_from_answer(
    project_path: str,
    relative_path: str,
    answer: str,
) -> PendingWrite | None:
    """Extract the last fenced code block from the model answer and propose a write."""
    blocks = re.findall(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", answer or "", flags=re.DOTALL)
    if not blocks:
        return None
    content = blocks[-1].strip() + "\n"
    tools = FileSystemTools(project_path)
    result = tools.write_file(relative_path, content)
    return result.pending_write
