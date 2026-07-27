"""LangGraph agent node implementations."""

from __future__ import annotations

from typing import Any, Callable

from src.editing.apply import build_proposed_edit
from src.multi_agent.llm import chat_json, chat_text
from src.multi_agent.memory import ConversationManager
from src.multi_agent.prompts import (
    ANALYZER_PROMPT,
    CODER_PROMPT,
    DOCS_PROMPT,
    FINAL_PROMPT,
    PLANNER_PROMPT,
    RESEARCH_PROMPT,
    REVIEWER_PROMPT,
    TESTER_PROMPT,
)
from src.multi_agent.state import AgentState, log_event
from src.multi_agent.tools_registry import ToolRegistry
from src.project_overview import build_project_overview
from src.llm.ollama_client import OllamaClient


def _edit_dicts_from_paths(
    project_path: str,
    edits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in edits:
        path = str(item.get("path") or "").replace("\\", "/")
        content = str(item.get("content") or "")
        if not path or not content.strip():
            continue
        try:
            proposed = build_proposed_edit(
                project_path,
                path,
                content if content.endswith("\n") else content + "\n",
                note=str(item.get("action") or "multi-agent edit"),
            )
            out.append(proposed.to_dict())
        except Exception:
            continue
    return out


class AgentNodes:
    """Factory for LangGraph node callables bound to client + tools."""

    def __init__(self, client: OllamaClient, tools: ToolRegistry) -> None:
        self.client = client
        self.tools = tools

    def planner(self, state: AgentState) -> dict[str, Any]:
        events = [log_event("Planning", "Breaking request into tasks…", status="running")]
        overview = ""
        try:
            overview = build_project_overview(state["project_path"]).context[:10000]
        except Exception as exc:  # noqa: BLE001
            overview = f"(overview failed: {exc})"
        listing = self.tools.list_directory(".")
        memory = ConversationManager(state["project_path"]).context_block()
        user = (
            f"USER REQUEST:\n{state['user_request']}\n\n"
            f"{memory}\n\n"
            f"PROJECT OVERVIEW:\n{overview}\n\n"
            f"TOP-LEVEL:\n{listing[:3000]}"
        )
        data = chat_json(self.client, PLANNER_PROMPT, user)
        if not data:
            data = {
                "summary": state["user_request"],
                "tasks": [
                    "Research local docs and indexed code",
                    "Analyze relevant files",
                    "Propose code edits",
                    "Review and generate tests",
                ],
                "files_to_modify": [],
                "files_to_create": ["CHANGES.md"],
                "notes": "Fallback plan — model JSON parse failed.",
            }
        ConversationManager(state["project_path"]).add(
            "assistant",
            data.get("summary") or state["user_request"],
            agent="planner",
            thread_id=state.get("thread_id", ""),
        )
        events.append(
            log_event(
                "Planning",
                "Plan ready — waiting for approval" if not state.get("plan_approved") else "Plan approved",
                status="waiting" if not state.get("plan_approved") else "completed",
                detail=str(data.get("summary") or ""),
            )
        )
        return {
            "tasks": list(data.get("tasks") or []),
            "plan_summary": str(data.get("summary") or ""),
            "plan_notes": str(data.get("notes") or ""),
            "files_to_modify": [str(p) for p in (data.get("files_to_modify") or [])],
            "files_to_create": [str(p) for p in (data.get("files_to_create") or [])],
            "execution_log": events,
        }

    def research(self, state: AgentState) -> dict[str, Any]:
        events = [log_event("Searching", "Research agent scanning docs + index…")]
        req = state["user_request"]
        smart = self.tools.smart_search(req)
        rag = self.tools.rag_retrieve(req)
        readme = ""
        for candidate in ("README.md", "readme.md", "docs/README.md"):
            text = self.tools.read_file(candidate)
            if text and not text.startswith("File not found") and "Not found" not in text[:40]:
                readme = text[:6000]
                break
        git_status = self.tools.git_status()
        user = (
            f"REQUEST:\n{req}\n\n"
            f"SMART SEARCH:\n{smart[:5000]}\n\n"
            f"RAG:\n{(rag or '(no index)')[:5000]}\n\n"
            f"README:\n{readme or '(none)'}\n\n"
            f"GIT STATUS:\n{git_status[:2000]}"
        )
        data = chat_json(self.client, RESEARCH_PROMPT, user)
        notes = str(data.get("notes") or smart[:2000])
        events.append(log_event("Searching", "Research complete", status="completed", detail=notes[:300]))
        pending = list(self.tools.pending_approvals)
        self.tools.pending_approvals.clear()
        return {
            "research_notes": notes,
            "rag_context": rag or "",
            "execution_log": events,
            "pending_tool_actions": pending,
        }

    def analyzer(self, state: AgentState) -> dict[str, Any]:
        events = [log_event("Reading files", "Analyzer loading relevant files…")]
        candidates = list(
            dict.fromkeys(
                list(state.get("files_to_modify") or [])
                + list(state.get("files_to_create") or [])
            )
        )
        # Also pull keywords from research via filesystem search
        search_hits = self.tools.search_files(state["user_request"][:80])
        loaded = self.tools.load_files(candidates, max_files=8)
        events.append(
            log_event(
                "Reading files",
                f"Loaded {len(loaded)} file(s)",
                status="completed",
                detail=", ".join(loaded.keys()) or "(none yet)",
            )
        )
        user = (
            f"REQUEST:\n{state['user_request']}\n\n"
            f"PLAN:\n{state.get('plan_summary')}\nTasks: {state.get('tasks')}\n\n"
            f"RESEARCH:\n{state.get('research_notes')}\n\n"
            f"RAG:\n{(state.get('rag_context') or '')[:4000]}\n\n"
            f"SEARCH HITS:\n{search_hits[:3000]}\n\n"
            f"FILE CONTENTS:\n{json_preview(loaded)}"
        )
        data = chat_json(self.client, ANALYZER_PROMPT, user)
        relevant = [str(p) for p in (data.get("relevant_files") or candidates)]
        # Load any newly identified files
        more = self.tools.load_files(
            [p for p in relevant if p not in loaded],
            max_files=6,
        )
        loaded.update(more)
        analysis = str(data.get("analysis") or "Analyze files listed in the plan.")
        return {
            "analysis": analysis,
            "relevant_files": relevant,
            "file_contents": loaded,
            "files_to_modify": list(
                dict.fromkeys(list(state.get("files_to_modify") or []) + [p for p in relevant if p in loaded])
            ),
            "execution_log": events,
        }

    def coder(self, state: AgentState) -> dict[str, Any]:
        events = [log_event("Generating", "Coder proposing edits (not writing disk)…")]
        targets = list(
            dict.fromkeys(
                list(state.get("files_to_modify") or [])
                + list(state.get("files_to_create") or [])
            )
        )
        if not targets:
            targets = ["CHANGES.md"]
        contents = state.get("file_contents") or {}
        user = (
            f"REQUEST:\n{state['user_request']}\n\n"
            f"PLAN:\n{state.get('plan_summary')}\n{state.get('tasks')}\n\n"
            f"ANALYSIS:\n{state.get('analysis')}\n\n"
            f"RESEARCH:\n{state.get('research_notes')}\n\n"
            f"TARGETS: {targets}\n\n"
            f"CURRENT FILES:\n{json_preview(contents)}\n\n"
            "Propose full file contents for each target."
        )
        data = chat_json(self.client, CODER_PROMPT, user)
        raw_edits = list(data.get("edits") or [])
        if not raw_edits:
            # Minimal fallback proposal
            raw_edits = [
                {
                    "path": targets[0],
                    "action": "create" if targets[0] not in contents else "modify",
                    "content": (
                        f"# Planned change\n\nGoal: {state['user_request']}\n\n"
                        f"Analysis:\n{state.get('analysis')}\n"
                    ),
                }
            ]
        proposed = _edit_dicts_from_paths(state["project_path"], raw_edits)
        events.append(
            log_event(
                "Generating",
                f"Proposed {len(proposed)} edit(s)",
                status="completed",
                detail=", ".join(e.get("path", "") for e in proposed),
            )
        )
        return {
            "proposed_edits": proposed,
            "coder_notes": str(data.get("notes") or ""),
            "execution_log": events,
        }

    def reviewer(self, state: AgentState) -> dict[str, Any]:
        events = [log_event("Reviewing", "Reviewer checking bugs/security/performance/style…")]
        edits = state.get("proposed_edits") or []
        preview = []
        for e in edits[:6]:
            preview.append(
                f"### {e.get('path')}\n```\n{str(e.get('new_content') or '')[:2500]}\n```"
            )
        user = (
            f"REQUEST:\n{state['user_request']}\n\n"
            f"CODER NOTES:\n{state.get('coder_notes')}\n\n"
            f"PROPOSED EDITS:\n" + "\n\n".join(preview)
        )
        data = chat_json(self.client, REVIEWER_PROMPT, user)
        report = str(data.get("report") or "No automated review details.")
        issues = [str(i) for i in (data.get("issues") or [])]
        events.append(log_event("Reviewing", "Review complete", status="completed"))
        return {
            "review_report": report,
            "review_issues": issues,
            "execution_log": events,
        }

    def tester(self, state: AgentState) -> dict[str, Any]:
        events = [log_event("Testing", "Tester generating pytest proposals…")]
        edits = state.get("proposed_edits") or []
        preview = []
        for e in edits[:4]:
            preview.append(f"FILE {e.get('path')}:\n{str(e.get('new_content') or '')[:3000]}")
        user = (
            f"REQUEST:\n{state['user_request']}\n\n"
            f"REVIEW ISSUES:\n{state.get('review_issues')}\n\n"
            f"CODE:\n" + "\n\n".join(preview)
        )
        data = chat_json(self.client, TESTER_PROMPT, user)
        tests = _edit_dicts_from_paths(state["project_path"], list(data.get("tests") or []))
        # Optionally run safe pytest if tests already exist — never destructive
        pytest_out = self.tools.terminal_run("pytest -q --tb=no", approved=False)
        events.append(
            log_event(
                "Testing",
                f"Proposed {len(tests)} test file(s)",
                status="completed",
                detail=pytest_out[:400],
            )
        )
        pending = list(self.tools.pending_approvals)
        self.tools.pending_approvals.clear()
        return {
            "test_proposals": tests,
            "tester_notes": str(data.get("notes") or ""),
            "execution_log": events,
            "pending_tool_actions": pending,
        }

    def docs(self, state: AgentState) -> dict[str, Any]:
        events = [log_event("Documentation", "Docs agent deciding README updates…")]
        readme = self.tools.read_file("README.md")
        user = (
            f"REQUEST:\n{state['user_request']}\n\n"
            f"PLAN:\n{state.get('plan_summary')}\n\n"
            f"CODER NOTES:\n{state.get('coder_notes')}\n\n"
            f"CURRENT README:\n{readme[:6000]}"
        )
        data = chat_json(self.client, DOCS_PROMPT, user)
        docs: list[dict[str, Any]] = []
        if data.get("needed"):
            docs = _edit_dicts_from_paths(state["project_path"], list(data.get("docs") or []))
        events.append(
            log_event(
                "Documentation",
                "Docs update proposed" if docs else "No docs change needed",
                status="completed",
            )
        )
        return {
            "docs_proposals": docs,
            "docs_notes": str(data.get("notes") or ""),
            "execution_log": events,
        }

    def final(self, state: AgentState) -> dict[str, Any]:
        events = [log_event("Completed", "Composing final response…", status="running")]
        edit_paths = [e.get("path") for e in (state.get("proposed_edits") or [])]
        test_paths = [e.get("path") for e in (state.get("test_proposals") or [])]
        doc_paths = [e.get("path") for e in (state.get("docs_proposals") or [])]
        user = (
            f"REQUEST: {state['user_request']}\n"
            f"PLAN: {state.get('plan_summary')}\n"
            f"TASKS: {state.get('tasks')}\n"
            f"EDITS: {edit_paths}\n"
            f"TESTS: {test_paths}\n"
            f"DOCS: {doc_paths}\n"
            f"REVIEW:\n{state.get('review_report')}\n"
            f"ISSUES: {state.get('review_issues')}\n"
        )
        text = chat_text(self.client, FINAL_PROMPT, user)
        ConversationManager(state["project_path"]).add(
            "assistant",
            text,
            agent="final",
            thread_id=state.get("thread_id", ""),
        )
        events.append(log_event("Completed", "Multi-agent run finished", status="completed"))
        return {
            "final_response": text,
            "execution_log": events,
        }


def json_preview(files: dict[str, str], limit: int = 8000) -> str:
    parts: list[str] = []
    used = 0
    for path, content in files.items():
        chunk = f"### {path}\n{content}\n"
        if used + len(chunk) > limit:
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts) or "(no files loaded)"


def bind_nodes(client: OllamaClient, tools: ToolRegistry) -> dict[str, Callable[[AgentState], dict]]:
    nodes = AgentNodes(client, tools)
    return {
        "planner": nodes.planner,
        "research": nodes.research,
        "analyzer": nodes.analyzer,
        "coder": nodes.coder,
        "reviewer": nodes.reviewer,
        "tester": nodes.tester,
        "docs": nodes.docs,
        "final": nodes.final,
    }
