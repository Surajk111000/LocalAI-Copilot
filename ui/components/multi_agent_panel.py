"""UI controls for LangGraph multi-agent plan approval + resume."""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.agent.plan_types import EditPlan
from src.llm.ollama_client import OllamaClient
from src.multi_agent.graph import MultiAgentRunner
from src.rag.embeddings import OllamaEmbedder


def _runner(client: OllamaClient, project_path: str) -> MultiAgentRunner:
    key = f"marunner_{project_path}"
    cache = st.session_state.get("_multi_agent_runners") or {}
    runner = cache.get(key)
    if runner is None:
        embedder = None
        try:
            from src.config import get_ollama_settings

            settings = get_ollama_settings()
            embedder = OllamaEmbedder(
                base_url=settings["base_url"],
                model=settings["embed_model"],
            )
        except Exception:
            embedder = None
        runner = MultiAgentRunner(client, project_path, embedder=embedder)
        cache[key] = runner
        st.session_state._multi_agent_runners = cache
    return runner


def start_multi_agent(
    client: OllamaClient,
    project_path: str,
    user_request: str,
) -> dict[str, Any]:
    runner = _runner(client, project_path)
    snap = runner.start(user_request)
    _store_snapshot(snap)
    return snap


def _store_snapshot(snap: dict[str, Any]) -> None:
    st.session_state.multi_agent_snapshot = snap
    st.session_state.multi_agent_thread_id = snap.get("thread_id")
    st.session_state.multi_agent_log = list(snap.get("execution_log") or [])
    st.session_state.pending_tool_actions = list(snap.get("pending_tool_actions") or [])

    # Bridge to existing plan viewer
    plan = EditPlan(
        id=str(snap.get("thread_id") or "plan"),
        goal=str(snap.get("user_request") or ""),
        summary=str(snap.get("plan_summary") or ""),
        analysis=str(snap.get("analysis") or snap.get("research_notes") or ""),
        files_to_modify=list(snap.get("files_to_modify") or []),
        files_to_create=list(snap.get("files_to_create") or []),
        steps=list(snap.get("tasks") or []),
        notes=str(snap.get("plan_notes") or ""),
        status="awaiting_approval" if snap.get("interrupted") else "ready",
    )
    st.session_state.active_edit_plan = plan.to_dict()


def render_multi_agent_controls(
    client: OllamaClient,
    project_path: str | None,
) -> None:
    snap = st.session_state.get("multi_agent_snapshot") or {}
    if not snap or not project_path:
        return

    interrupted = bool(snap.get("interrupted"))
    if interrupted:
        st.info(
            "LangGraph paused after **Planner**. "
            "Approve to continue: Research → Analyzer → Coder → Reviewer → Tester → Docs → Final."
        )
        c1, c2 = st.columns(2)
        if c1.button(
            "Approve plan — continue multi-agent pipeline",
            type="primary",
            use_container_width=True,
            key="ma_approve",
        ):
            runner = _runner(client, project_path)
            with st.spinner(
                "Running Research → Analyzer → Coder → Reviewer → Tester → Docs → Final…"
            ):
                snap = runner.approve_and_continue(str(snap.get("thread_id")))
            _store_snapshot(snap)
            # Collect all proposals into diff viewer
            edits = []
            edits.extend(snap.get("proposed_edits") or [])
            edits.extend(snap.get("test_proposals") or [])
            edits.extend(snap.get("docs_proposals") or [])
            st.session_state.proposed_edits = edits
            st.session_state.proposed_edits_note = str(snap.get("user_request") or "multi-agent")
            if snap.get("final_response"):
                st.session_state.messages = st.session_state.get("messages") or []
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": snap["final_response"],
                        "sources": [
                            {"path": e.get("path")}
                            for e in edits
                            if e.get("path")
                        ],
                        "tool_trace": ["langgraph:multi-agent"],
                    }
                )
            st.success("Pipeline complete — review diffs before Accept.")
            st.rerun()
        if c2.button("Reject plan", use_container_width=True, key="ma_reject"):
            runner = _runner(client, project_path)
            snap = runner.reject(str(snap.get("thread_id")))
            _store_snapshot(snap)
            st.warning("Plan rejected.")
            st.rerun()
    elif snap.get("final_response"):
        with st.expander("Final multi-agent response", expanded=True):
            st.markdown(snap["final_response"])
        if snap.get("review_report"):
            with st.expander("Reviewer report"):
                st.markdown(snap["review_report"])
