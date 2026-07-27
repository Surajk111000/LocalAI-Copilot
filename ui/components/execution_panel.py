"""Execution panel for the LangGraph multi-agent pipeline."""

from __future__ import annotations

import streamlit as st

PHASE_ORDER = [
    "Planning",
    "Searching",
    "Reading files",
    "Generating",
    "Reviewing",
    "Testing",
    "Documentation",
    "Completed",
]

STATUS_ICON = {
    "running": "⏳",
    "completed": "✅",
    "waiting": "⏸️",
    "error": "❌",
}


def render_execution_panel(execution_log: list[dict] | None = None) -> None:
    """Display Planning → … → Completed progress."""
    st.markdown("#### Execution Panel")
    log = execution_log or st.session_state.get("multi_agent_log") or []

    # Latest status per phase
    latest: dict[str, dict] = {}
    for event in log:
        phase = str(event.get("phase") or "")
        if phase:
            latest[phase] = event

    cols = st.columns(len(PHASE_ORDER))
    for col, phase in zip(cols, PHASE_ORDER):
        event = latest.get(phase)
        if not event:
            col.markdown(f"⚪\n\n**{phase}**")
            continue
        icon = STATUS_ICON.get(str(event.get("status")), "•")
        col.markdown(f"{icon}\n\n**{phase}**")

    if not log:
        st.caption("Idle — start an Agent request to see live stages.")
        return

    with st.expander("Detailed agent log", expanded=True):
        for event in log:
            icon = STATUS_ICON.get(str(event.get("status")), "•")
            st.markdown(
                f"{icon} **{event.get('phase')}** — {event.get('message')}"
            )
            if event.get("detail"):
                st.caption(str(event["detail"])[:500])


def render_pending_tool_approvals(project_path: str | None) -> None:
    """Approve gated git/terminal commands."""
    pending = st.session_state.get("pending_tool_actions") or []
    if not pending or not project_path:
        return
    st.warning(f"{len(pending)} tool action(s) need approval")
    from src.tools.git_tools import GitTools
    from src.tools.terminal_tools import TerminalTools

    for i, action in enumerate(list(pending)):
        tool = action.get("tool")
        command = action.get("command") or ""
        with st.expander(f"{tool}: `{command}`", expanded=True):
            c1, c2 = st.columns(2)
            if c1.button("Approve & run", key=f"tool_ok_{i}", type="primary"):
                if tool == "git":
                    result = GitTools(project_path).run(
                        list(action.get("args") or []),
                        approved=True,
                    )
                    st.code(result.output)
                else:
                    result = TerminalTools(project_path).run(command, approved=True)
                    st.code(result.output)
                pending.pop(i)
                st.session_state.pending_tool_actions = pending
                st.rerun()
            if c2.button("Reject", key=f"tool_no_{i}"):
                pending.pop(i)
                st.session_state.pending_tool_actions = pending
                st.rerun()
