"""Built-in + user prompt library."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.workspace.paths import project_dir, read_json, write_json

BUILTIN_PROMPTS: list[dict[str, str]] = [
    {
        "id": "explain_module",
        "title": "Explain module",
        "category": "Explain",
        "prompt": "Explain this module: purpose, public API, and how it fits the project.",
    },
    {
        "id": "add_tests",
        "title": "Add pytest coverage",
        "category": "Tests",
        "prompt": "Generate pytest unit tests for the selected module with edge cases.",
    },
    {
        "id": "security_review",
        "title": "Security review",
        "category": "Review",
        "prompt": "Review for security issues: auth, injection, secrets, unsafe deserialization.",
    },
    {
        "id": "refactor_clean",
        "title": "Clean refactor",
        "category": "Refactor",
        "prompt": "Suggest a clean refactor for readability without changing behavior.",
    },
    {
        "id": "api_design",
        "title": "Design REST endpoint",
        "category": "Backend",
        "prompt": "Design a REST endpoint with request/response schemas and error cases.",
    },
    {
        "id": "commit_msg",
        "title": "Write commit message",
        "category": "Git",
        "prompt": "Write a conventional commit message for the current changes.",
    },
    {
        "id": "fix_bug",
        "title": "Fix from traceback",
        "category": "Debug",
        "prompt": "Here is a traceback. Locate the root cause and propose a minimal fix.",
    },
    {
        "id": "optimize_perf",
        "title": "Performance pass",
        "category": "Performance",
        "prompt": "Find performance bottlenecks and suggest concrete optimizations.",
    },
]


@dataclass
class PromptItem:
    id: str
    title: str
    category: str
    prompt: str
    builtin: bool = True


class PromptLibrary:
    """Reusable prompts: builtins + per-project custom prompts."""

    def __init__(self, project_path: str | Path | None = None) -> None:
        self.project_path = str(Path(project_path).resolve()) if project_path else None
        self._custom_path = (
            project_dir(self.project_path) / "prompt_library.json"
            if self.project_path
            else None
        )

    def list_all(self) -> list[PromptItem]:
        items = [
            PromptItem(
                id=p["id"],
                title=p["title"],
                category=p["category"],
                prompt=p["prompt"],
                builtin=True,
            )
            for p in BUILTIN_PROMPTS
        ]
        items.extend(self.list_custom())
        return items

    def list_custom(self) -> list[PromptItem]:
        if not self._custom_path:
            return []
        raw = read_json(self._custom_path, {"prompts": []})
        out: list[PromptItem] = []
        for p in raw.get("prompts") or []:
            out.append(
                PromptItem(
                    id=str(p.get("id") or ""),
                    title=str(p.get("title") or "Custom"),
                    category=str(p.get("category") or "Custom"),
                    prompt=str(p.get("prompt") or ""),
                    builtin=False,
                )
            )
        return out

    def add_custom(self, title: str, prompt: str, category: str = "Custom") -> PromptItem:
        if not self._custom_path:
            raise ValueError("Open a project to save custom prompts.")
        import uuid

        item = PromptItem(
            id=uuid.uuid4().hex[:10],
            title=title.strip() or "Custom",
            category=category.strip() or "Custom",
            prompt=prompt.strip(),
            builtin=False,
        )
        data = read_json(self._custom_path, {"prompts": []})
        prompts = list(data.get("prompts") or [])
        prompts.append(asdict(item))
        write_json(self._custom_path, {"prompts": prompts})
        return item

    def delete_custom(self, prompt_id: str) -> None:
        if not self._custom_path:
            return
        data = read_json(self._custom_path, {"prompts": []})
        prompts = [p for p in (data.get("prompts") or []) if p.get("id") != prompt_id]
        write_json(self._custom_path, {"prompts": prompts})

    def search(self, query: str) -> list[PromptItem]:
        q = (query or "").lower().strip()
        if not q:
            return self.list_all()
        return [
            p
            for p in self.list_all()
            if q in p.title.lower() or q in p.prompt.lower() or q in p.category.lower()
        ]
