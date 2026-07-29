"""Agent mode: plan → approve → generate edits → never auto-write."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from src.agent.plan_types import EditPlan
from src.editing.apply import ProposedEdit, build_proposed_edit
from src.llm.ollama_client import OllamaClient, OllamaError
from src.project_overview import build_project_overview
from src.tools.filesystem import FileSystemTools
from src.workspace.paths import project_dir, read_json, write_json

try:
    from src.workspace.paths import plans_dir
except ImportError:  # pragma: no cover — stale Streamlit module cache

    def plans_dir(project_path: str | Path) -> Path:
        path = project_dir(project_path) / "plans"
        path.mkdir(parents=True, exist_ok=True)
        return path

PLAN_RE = re.compile(r"\{[\s\S]*\}")

PLAN_SYSTEM = """You are a careful local coding agent planner.
You NEVER modify files. You only produce an execution plan as JSON.

Return ONLY valid JSON with this shape:
{
  "summary": "one sentence",
  "analysis": "what the project is and what must change",
  "files_to_modify": ["existing/path.py"],
  "files_to_create": ["new/path.py"],
  "steps": ["step 1", "step 2", "step 3"],
  "notes": "risks or assumptions"
}

Rules:
- Prefer minimal changes.
- Use real-looking relative paths based on PROJECT CONTEXT.
- Do not invent dozens of files — keep the plan small and practical.
- If the request is unclear, still propose a reasonable minimal plan.
"""


EDIT_SYSTEM = """You are a local coding agent that proposes FULL file contents.
You NEVER write to disk. Return ONLY the complete new file content inside one markdown fence.

Example:
```python
# full file here
```

Rules:
- Output the ENTIRE file, not a partial patch.
- Preserve existing style when modifying.
- Keep changes focused on the user goal.
- No explanations outside the code fence.
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = PLAN_RE.search(text)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _extract_code_block(text: str) -> str:
    fence = re.search(r"```(?:\w+)?\s*([\s\S]*?)```", text or "")
    if fence:
        return fence.group(1).strip() + "\n"
    return (text or "").strip() + "\n"


class AgentPlanner:
    """Step 1–3: analyze project and produce an approval-gated plan."""

    def __init__(self, client: OllamaClient) -> None:
        self.client = client

    def analyze_and_plan(self, project_path: str | Path, goal: str) -> EditPlan:
        overview = build_project_overview(project_path)
        tools = FileSystemTools(project_path)
        listing = tools.list_directory(".")
        context = (
            f"GOAL:\n{goal}\n\n"
            f"PROJECT OVERVIEW:\n{overview.context[:14000]}\n\n"
            f"TOP-LEVEL FILES:\n{listing.output[:4000]}"
        )
        messages = [
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": context},
        ]
        try:
            raw = self.client.chat(messages, stream=False)
            assert isinstance(raw, str)
            data = _extract_json(raw)
        except OllamaError:
            data = {}

        if not data:
            data = {
                "summary": f"Implement: {goal}",
                "analysis": overview.context[:1500],
                "files_to_modify": [],
                "files_to_create": ["CHANGES.md"],
                "steps": [
                    "Analyze the project structure",
                    "Identify touch points for the requested feature",
                    "Propose new/updated files for approval",
                ],
                "notes": "Fallback plan — review carefully before approving.",
            }

        plan = EditPlan(
            id=uuid.uuid4().hex[:12],
            goal=goal,
            summary=str(data.get("summary") or goal),
            analysis=str(data.get("analysis") or ""),
            files_to_modify=[str(p).replace("\\", "/") for p in (data.get("files_to_modify") or [])],
            files_to_create=[str(p).replace("\\", "/") for p in (data.get("files_to_create") or [])],
            steps=[str(s) for s in (data.get("steps") or [])],
            notes=str(data.get("notes") or ""),
            status="awaiting_approval",
        )
        self.save_plan(project_path, plan)
        return plan

    def save_plan(self, project_path: str | Path, plan: EditPlan) -> None:
        path = plans_dir(project_path) / f"{plan.id}.json"
        write_json(path, plan.to_dict())
        write_json(plans_dir(project_path) / "active.json", {"active_id": plan.id})

    def load_active(self, project_path: str | Path) -> EditPlan | None:
        meta = read_json(plans_dir(project_path) / "active.json", {})
        pid = meta.get("active_id")
        if not pid:
            return None
        data = read_json(plans_dir(project_path) / f"{pid}.json", None)
        return EditPlan.from_dict(data) if data else None


class AgentCoder:
    """After plan approval: generate ProposedEdit objects (still not applied)."""

    def __init__(self, client: OllamaClient) -> None:
        self.client = client

    def generate_edits(
        self,
        project_path: str | Path,
        plan: EditPlan,
    ) -> list[ProposedEdit]:
        tools = FileSystemTools(project_path)
        edits: list[ProposedEdit] = []
        targets: list[tuple[str, bool]] = [
            *[(p, False) for p in plan.files_to_modify],
            *[(p, True) for p in plan.files_to_create],
        ]
        if not targets:
            targets = [("CHANGES.md", True)]

        for rel, expect_new in targets:
            existing = ""
            try:
                target = tools.resolve(rel)
                if target.is_file():
                    existing = target.read_text(encoding="utf-8", errors="replace")[:12000]
                    expect_new = False
            except Exception:
                existing = ""

            prompt = (
                f"GOAL: {plan.goal}\n"
                f"PLAN SUMMARY: {plan.summary}\n"
                f"FILE: {rel}\n"
                f"ACTION: {'CREATE' if expect_new else 'MODIFY'}\n\n"
                f"CURRENT FILE CONTENT:\n{existing or '(new file)'}\n\n"
                "Produce the full new file content now."
            )
            messages = [
                {"role": "system", "content": EDIT_SYSTEM},
                {"role": "user", "content": prompt},
            ]
            try:
                raw = self.client.chat(messages, stream=False)
                assert isinstance(raw, str)
                content = _extract_code_block(raw)
            except OllamaError as exc:
                content = (
                    f"# Generation failed for {rel}\n"
                    f"# Error: {exc}\n"
                    f"# Goal: {plan.goal}\n"
                )
            try:
                edit = build_proposed_edit(project_path, rel, content, note=plan.goal)
                edits.append(edit)
            except Exception:
                continue
        return edits
