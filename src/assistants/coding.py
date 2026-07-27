"""Prompt builders for review / refactor / tests / docs / commit / inline AI.

These assistants NEVER write files themselves — they return text or ProposedEdit
lists that still require user approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.editing.apply import ProposedEdit, build_proposed_edit
from src.editing.versions import VersionStore
from src.llm.ollama_client import OllamaClient, OllamaError
from src.project_overview import build_path_context, build_project_overview
from src.tools.filesystem import FileSystemTools


@dataclass
class AssistantResult:
    title: str
    content: str
    proposed_edits: list[ProposedEdit] | None = None


def _chat(client: OllamaClient, system: str, user: str) -> str:
    try:
        raw = client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=False,
        )
        assert isinstance(raw, str)
        return raw.strip()
    except OllamaError as exc:
        return f"**Error:** {exc}"


def _extract_code(text: str) -> str:
    fence = re.search(r"```(?:\w+)?\s*([\s\S]*?)```", text or "")
    if fence:
        return fence.group(1).strip() + "\n"
    return (text or "").strip() + "\n"


# ---- Code review ----

REVIEW_SYSTEM = """You are a strict local code reviewer.
Report findings under these headings only:
## Bugs
## Performance
## Security
## Clean code
Be concrete. Cite file paths and line-ish locations when possible.
Never modify files. Never invent APIs that are not in the provided code.
"""


def review_text(client: OllamaClient, code: str, *, scope: str = "selection") -> AssistantResult:
    content = _chat(
        client,
        REVIEW_SYSTEM,
        f"Review scope: {scope}\n\nCODE:\n{code[:20000]}",
    )
    return AssistantResult(title=f"Code review ({scope})", content=content)


def review_file(client: OllamaClient, project_path: str | Path, rel_path: str) -> AssistantResult:
    tools = FileSystemTools(project_path)
    result = tools.read_file(rel_path)
    if not result.ok:
        return AssistantResult(title="Code review", content=result.output)
    return review_text(client, result.output, scope=f"file:{rel_path}")


def review_project(client: OllamaClient, project_path: str | Path) -> AssistantResult:
    overview = build_project_overview(project_path)
    return review_text(client, overview.context, scope="project")


# ---- Refactor suggestions (never auto-apply) ----

REFACTOR_SYSTEM = """You suggest refactoring improvements.
Output:
## Suggested improvements
(bullets)
## Example refactored snippet
(one optional code fence — suggestion only)
Do NOT claim you changed any files. Never instruct silent writes.
"""


def suggest_refactor(client: OllamaClient, code: str) -> AssistantResult:
    content = _chat(client, REFACTOR_SYSTEM, f"CODE:\n{code[:16000]}")
    return AssistantResult(title="Refactor suggestions", content=content)


# ---- Selection actions ----

ACTION_PROMPTS = {
    "explain": "Explain this code clearly for a junior engineer.",
    "optimize": "Suggest optimized version. Explain trade-offs briefly, then show improved code in one fence.",
    "refactor": "Suggest a cleaner refactor. Show improved code in one fence. Do not claim files were changed.",
    "generate_tests": "Generate pytest unit tests for this code in one python fence.",
}


def run_selection_action(
    client: OllamaClient,
    action: str,
    code: str,
    *,
    project_path: str | Path | None = None,
    target_path: str | None = None,
) -> AssistantResult:
    instruction = ACTION_PROMPTS.get(action, ACTION_PROMPTS["explain"])
    content = _chat(
        client,
        "You are a local coding assistant. Be concise and practical.",
        f"{instruction}\n\nCODE:\n{code[:16000]}",
    )
    edits: list[ProposedEdit] | None = None
    if action == "generate_tests" and project_path and target_path:
        test_path = _default_test_path(target_path)
        edits = [
            build_proposed_edit(
                project_path,
                test_path,
                _extract_code(content),
                note="generated tests",
            )
        ]
    return AssistantResult(title=action.replace("_", " ").title(), content=content, proposed_edits=edits)


def _default_test_path(source_path: str) -> str:
    p = Path(source_path)
    name = p.stem if p.stem != "__init__" else "module"
    return str(Path("tests") / f"test_{name}.py").replace("\\", "/")


# ---- Test generator ----

def generate_tests(
    client: OllamaClient,
    project_path: str | Path,
    source_path: str,
) -> AssistantResult:
    tools = FileSystemTools(project_path)
    result = tools.read_file(source_path)
    if not result.ok:
        return AssistantResult(title="Test generator", content=result.output)
    content = _chat(
        client,
        "Generate complete pytest tests. Return one python code fence only with full test file.",
        f"SOURCE FILE {source_path}:\n{result.output[:16000]}",
    )
    test_path = _default_test_path(source_path)
    edit = build_proposed_edit(project_path, test_path, _extract_code(content), note="pytest generator")
    return AssistantResult(
        title=f"Generate tests → {test_path}",
        content=content,
        proposed_edits=[edit],
    )


# ---- Docs generator ----

DOC_KINDS = {
    "readme": "Generate a practical README.md for this project. One markdown fence with full README.",
    "api": "Generate API documentation markdown from the project context. One markdown fence.",
    "docstrings": "Add/improve docstrings for the given file. Return the FULL updated file in one code fence.",
}


def generate_docs(
    client: OllamaClient,
    project_path: str | Path,
    kind: str,
    *,
    file_path: str | None = None,
) -> AssistantResult:
    kind = kind if kind in DOC_KINDS else "readme"
    if kind == "docstrings":
        if not file_path:
            return AssistantResult(title="Docs", content="Select a file for docstring generation.")
        tools = FileSystemTools(project_path)
        result = tools.read_file(file_path)
        if not result.ok:
            return AssistantResult(title="Docs", content=result.output)
        content = _chat(client, DOC_KINDS[kind], result.output[:16000])
        edit = build_proposed_edit(
            project_path,
            file_path,
            _extract_code(content),
            note="docstrings",
        )
        return AssistantResult(title="Docstrings", content=content, proposed_edits=[edit])

    overview = build_project_overview(project_path)
    content = _chat(client, DOC_KINDS[kind], overview.context[:18000])
    out_path = "README.md" if kind == "readme" else "docs/API.md"
    edit = build_proposed_edit(project_path, out_path, _extract_code(content), note=f"docs:{kind}")
    return AssistantResult(title=f"Docs → {out_path}", content=content, proposed_edits=[edit])


# ---- Commit assistant ----

def commit_message(
    client: OllamaClient,
    project_path: str | Path,
    *,
    extra_summary: str = "",
) -> AssistantResult:
    store = VersionStore(project_path)
    recent = store.list_recent(15)
    lines = []
    for item in recent:
        lines.append(
            f"- {item.get('path')} ({'new' if item.get('is_new') else 'modified'}) "
            f"— {item.get('note') or ''}"
        )
    if not lines and not extra_summary:
        return AssistantResult(
            title="Commit assistant",
            content="No accepted edits in version history yet. Accept some changes first.",
        )
    body = "Recent accepted changes:\n" + ("\n".join(lines) or "(none)")
    if extra_summary:
        body += f"\n\nUser notes:\n{extra_summary}"
    content = _chat(
        client,
        "Write a concise conventional commit message (subject <= 72 chars) "
        "plus a short bullet body. Do not wrap in code fences.",
        body,
    )
    return AssistantResult(title="Commit message", content=content)


# ---- Inline AI (Ctrl+K style) ----

INLINE_SYSTEM = """You generate or transform code for an inline editor.
Return ONLY one code fence with the result. No prose.
If instruction is to insert new code, produce just that snippet.
If instruction is to transform selected code, produce the full replacement for the selection.
"""


def inline_generate(client: OllamaClient, instruction: str, selected: str = "") -> AssistantResult:
    user = f"INSTRUCTION:\n{instruction}\n\n"
    if selected.strip():
        user += f"SELECTED CODE:\n{selected}\n"
    content = _chat(client, INLINE_SYSTEM, user)
    return AssistantResult(title="Inline AI", content=content)
