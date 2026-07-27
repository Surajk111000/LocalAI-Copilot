"""Automatic code search for prompts like 'Search for OllamaClient'.

Does not require the Tools toggle. Reads the active project folder and
returns search hits as LLM context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.tools.filesystem import FileSystemTools


@dataclass
class SearchBundle:
    query: str
    context: str
    files_used: list[str]
    hit_count: int


def wants_code_search(prompt: str) -> bool:
    text = (prompt or "").lower().strip()
    triggers = (
        "search for ",
        "search ",
        "find where ",
        "find file ",
        "find ",
        "where is ",
        "locate ",
        "look for ",
    )
    # Avoid treating "explain this project" etc. as search
    if "explain" in text and "project" in text:
        return False
    return any(text.startswith(t) or f" {t}" in f" {text}" for t in triggers)


def extract_search_query(prompt: str) -> str:
    """Pull the search term from a natural-language command."""
    text = (prompt or "").strip()
    patterns = [
        r"(?i)^search\s+for\s+(.+)$",
        r"(?i)^search\s+(.+)$",
        r"(?i)^find\s+where\s+(.+)$",
        r"(?i)^find\s+file\s+(.+)$",
        r"(?i)^find\s+(.+)$",
        r"(?i)^where\s+is\s+(.+)$",
        r"(?i)^locate\s+(.+)$",
        r"(?i)^look\s+for\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            query = match.group(1).strip().strip("?.!\"'`")
            # Remove trailing filler like "in the project"
            query = re.sub(
                r"(?i)\s+in\s+(the\s+)?(project|codebase|repo|folder)\s*$",
                "",
                query,
            ).strip()
            return query
    return text


def search_project(project_path: str | Path, query: str) -> SearchBundle:
    """Run substring search across the project and format hits for the LLM."""
    query = (query or "").strip()
    if not query:
        raise ValueError("Empty search query")

    tools = FileSystemTools(project_path)
    result = tools.search_files(query, ".")
    output = result.output if result.ok else f"Search failed: {result.output}"

    files: list[str] = []
    for line in output.splitlines():
        if ":" in line and not line.startswith("No matches"):
            files.append(line.split(":", 1)[0].strip())
    # unique preserve order
    seen: set[str] = set()
    unique_files: list[str] = []
    for path in files:
        if path not in seen:
            seen.add(path)
            unique_files.append(path)

    context = (
        f"SEARCH QUERY: {query}\n"
        f"PROJECT PATH: {Path(project_path).resolve()}\n\n"
        f"SEARCH HITS:\n{output}\n"
    )
    return SearchBundle(
        query=query,
        context=context,
        files_used=unique_files,
        hit_count=0 if output.startswith("No matches") else len(output.splitlines()),
    )
