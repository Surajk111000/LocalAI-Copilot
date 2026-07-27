"""LangGraph multi-agent coding pipeline."""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.llm.ollama_client import OllamaClient
from src.multi_agent.memory import ConversationManager
from src.multi_agent.nodes import bind_nodes
from src.multi_agent.state import AgentState
from src.multi_agent.tools_registry import ToolRegistry
from src.rag.embeddings import OllamaEmbedder


def build_coding_graph(
    client: OllamaClient,
    tools: ToolRegistry,
    *,
    checkpointer: MemorySaver | None = None,
):
    """
    Planner → Research → Analyzer → Coder → Reviewer → Tester → Docs → Final

    Compiled with interrupt_after=['planner'] so the UI can require plan approval.
    """
    nodes = bind_nodes(client, tools)
    graph = StateGraph(AgentState)
    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "research")
    graph.add_edge("research", "analyzer")
    graph.add_edge("analyzer", "coder")
    graph.add_edge("coder", "reviewer")
    graph.add_edge("reviewer", "tester")
    graph.add_edge("tester", "docs")
    graph.add_edge("docs", "final")
    graph.add_edge("final", END)

    memory = checkpointer or MemorySaver()
    return graph.compile(
        checkpointer=memory,
        interrupt_after=["planner"],
    )


class MultiAgentRunner:
    """High-level API for Streamlit: start → approve plan → continue."""

    def __init__(
        self,
        client: OllamaClient,
        project_path: str,
        *,
        embedder: OllamaEmbedder | None = None,
    ) -> None:
        self.client = client
        self.project_path = project_path
        self.tools = ToolRegistry(project_path, embedder=embedder)
        self.checkpointer = MemorySaver()
        self.graph = build_coding_graph(client, self.tools, checkpointer=self.checkpointer)

    def _config(self, thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def start(self, user_request: str, *, thread_id: str | None = None) -> dict[str, Any]:
        """Run until planner finishes (interrupt)."""
        tid = thread_id or uuid.uuid4().hex[:12]
        ConversationManager(self.project_path).add(
            "user",
            user_request,
            agent="user",
            thread_id=tid,
        )
        initial: AgentState = {
            "user_request": user_request,
            "project_path": self.project_path,
            "thread_id": tid,
            "conversation": ConversationManager(self.project_path).as_message_dicts(),
            "plan_approved": False,
            "tasks": [],
            "plan_summary": "",
            "plan_notes": "",
            "files_to_modify": [],
            "files_to_create": [],
            "research_notes": "",
            "relevant_files": [],
            "file_contents": {},
            "rag_context": "",
            "analysis": "",
            "proposed_edits": [],
            "coder_notes": "",
            "review_report": "",
            "review_issues": [],
            "test_proposals": [],
            "tester_notes": "",
            "docs_proposals": [],
            "docs_notes": "",
            "final_response": "",
            "execution_log": [],
            "pending_tool_actions": [],
            "errors": [],
        }
        self.graph.invoke(initial, self._config(tid))
        return self.snapshot(tid)

    def approve_and_continue(self, thread_id: str) -> dict[str, Any]:
        """Resume graph after planner interrupt (research → final)."""
        # Mark approval in state then resume
        self.graph.update_state(
            self._config(thread_id),
            {"plan_approved": True},
        )
        self.graph.invoke(None, self._config(thread_id))
        return self.snapshot(thread_id)

    def snapshot(self, thread_id: str) -> dict[str, Any]:
        state = self.graph.get_state(self._config(thread_id))
        values = dict(state.values or {})
        values["thread_id"] = thread_id
        values["next"] = list(state.next or [])
        values["interrupted"] = bool(state.next)
        return values

    def reject(self, thread_id: str) -> dict[str, Any]:
        self.graph.update_state(
            self._config(thread_id),
            {
                "plan_approved": False,
                "final_response": "Plan rejected by user. No further agents ran.",
                "execution_log": [
                    {
                        "phase": "Completed",
                        "message": "Plan rejected",
                        "status": "completed",
                        "detail": "",
                    }
                ],
            },
        )
        snap = self.snapshot(thread_id)
        snap["interrupted"] = False
        snap["next"] = []
        return snap
