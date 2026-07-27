"""Shared state for the LangGraph multi-agent coding pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    """State that flows through every agent node."""

    # Request + project
    user_request: str
    project_path: str
    thread_id: str

    # Conversation memory
    conversation: list[dict[str, str]]

    # Planner
    tasks: list[str]
    plan_summary: str
    plan_notes: str
    files_to_modify: list[str]
    files_to_create: list[str]
    plan_approved: bool

    # Research / Analyzer
    research_notes: str
    relevant_files: list[str]
    file_contents: dict[str, str]
    rag_context: str
    analysis: str

    # Coder
    proposed_edits: list[dict[str, Any]]
    coder_notes: str

    # Reviewer
    review_report: str
    review_issues: list[str]

    # Tester
    test_proposals: list[dict[str, Any]]
    tester_notes: str

    # Docs
    docs_proposals: list[dict[str, Any]]
    docs_notes: str

    # Final
    final_response: str

    # Execution panel (append-only log)
    execution_log: Annotated[list[dict[str, Any]], operator.add]

    # Pending tool approvals (git reset, rm, etc.)
    pending_tool_actions: Annotated[list[dict[str, Any]], operator.add]

    # Errors
    errors: Annotated[list[str], operator.add]


def log_event(
    phase: str,
    message: str,
    *,
    status: str = "running",
    detail: str = "",
) -> dict[str, Any]:
    """Build one execution-panel event."""
    return {
        "phase": phase,
        "message": message,
        "status": status,  # running | completed | error | waiting
        "detail": detail,
    }
