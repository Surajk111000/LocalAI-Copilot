"""Execution panel for the LangGraph multi-agent pipeline."""

from __future__ import annotations

import html
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
    "running": "●",
    "completed": "✓",
    "waiting": "❚❚",
    "error": "✕",
    "idle": "○",
}

STATUS_CLASS = {
    "running": "ep-run",
    "completed": "ep-done",
    "waiting": "ep-wait",
    "error": "ep-err",
    "idle": "ep-idle",
}

PANEL_CSS = """
<style>
.ep-wrap { margin: 0 0 0.4rem 0; }
.ep-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 0.5rem; margin-bottom: 0.55rem;
}
.ep-title { font-weight: 600; font-size: 0.95rem; margin: 0; }
.ep-badge {
  font-size: 0.72rem; font-weight: 500; letter-spacing: 0.02em;
  padding: 0.15rem 0.45rem; border-radius: 999px;
  border: 1px solid var(--border, #30363d);
  color: var(--muted, #8b949e); background: transparent;
  white-space: nowrap;
}
.ep-badge.ep-wait { color: #d29922; border-color: #9e6a03; background: rgba(210,153,34,0.12); }
.ep-badge.ep-run { color: #58a6ff; border-color: #1f6feb; background: rgba(88,166,255,0.12); }
.ep-badge.ep-done { color: #3fb950; border-color: #238636; background: rgba(63,185,80,0.12); }
.ep-badge.ep-err { color: #f85149; border-color: #da3633; background: rgba(248,81,73,0.12); }
.ep-badge.ep-idle { color: var(--muted, #8b949e); }
.ep-hint {
  font-size: 0.8rem; color: var(--muted, #8b949e);
  margin: 0 0 0.65rem 0; line-height: 1.35;
}
.ep-list { list-style: none; margin: 0; padding: 0; }
.ep-item {
  display: grid; grid-template-columns: 1.1rem 1fr; gap: 0.45rem;
  align-items: start; padding: 0.28rem 0; position: relative;
}
.ep-item:not(:last-child)::after {
  content: ""; position: absolute; left: 0.42rem; top: 1.15rem;
  bottom: -0.05rem; width: 1px; background: var(--border, #30363d);
}
.ep-dot {
  width: 0.85rem; height: 0.85rem; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 0.55rem; font-weight: 700; margin-top: 0.12rem;
  border: 1.5px solid var(--border, #30363d);
  color: var(--muted, #8b949e); background: transparent; z-index: 1;
}
.ep-dot.ep-done { background: #238636; border-color: #3fb950; color: #fff; }
.ep-dot.ep-run {
  background: #1f6feb; border-color: #58a6ff; color: #fff;
  animation: ep-pulse 1.2s ease-in-out infinite;
}
.ep-dot.ep-wait { background: #9e6a03; border-color: #d29922; color: #fff; border-radius: 3px; }
.ep-dot.ep-err { background: #da3633; border-color: #f85149; color: #fff; }
.ep-label { font-size: 0.82rem; color: var(--text, #e6edf3); line-height: 1.25; }
.ep-label small {
  display: block; color: var(--muted, #8b949e); font-size: 0.72rem;
  font-weight: 400; margin-top: 0.1rem;
}
.ep-item.ep-idle .ep-label { color: var(--muted, #8b949e); }
@keyframes ep-pulse { 0%,100%{opacity:.55} 50%{opacity:1} }
</style>
"""


def _overall_status(latest: dict[str, dict], log: list[dict]) -> tuple[str, str, str]:
    """Return (badge_class, badge_label, hint)."""
    if not log:
        return "ep-idle", "Idle", "Start an Agent request to see live stages."

    for phase in reversed(PHASE_ORDER):
        event = latest.get(phase)
        if not event:
            continue
        status = str(event.get("status") or "")
        msg = str(event.get("message") or "")
        if status == "error":
            return "ep-err", "Error", msg or "A stage failed."
        if status == "waiting":
            return (
                "ep-wait",
                "Waiting",
                msg or "Approve the plan in the main panel to continue.",
            )
        if status == "running":
            return "ep-run", "Running", msg or f"{phase} in progress…"
        if phase == "Completed" and status == "completed":
            return "ep-done", "Done", msg or "Pipeline finished — review diffs before Accept."

    # Fallback: last event
    last = log[-1]
    status = str(last.get("status") or "idle")
    cls = STATUS_CLASS.get(status, "ep-idle")
    label = status.replace("_", " ").title()
    return cls, label, str(last.get("message") or "")


def _phase_state(phase: str, latest: dict[str, dict]) -> tuple[str, str]:
    """Return (status_class, detail) for a phase."""
    event = latest.get(phase)
    if not event:
        # Mark earlier completed phases when a later one has started
        return "ep-idle", ""
    status = str(event.get("status") or "idle")
    cls = STATUS_CLASS.get(status, "ep-idle")
    detail = str(event.get("message") or "")
    return cls, detail


def render_execution_panel(execution_log: list[dict] | None = None) -> None:
    """Compact vertical stepper — fits the narrow right rail."""
    st.markdown(PANEL_CSS, unsafe_allow_html=True)

    log = list(execution_log or st.session_state.get("multi_agent_log") or [])
    latest: dict[str, dict] = {}
    for event in log:
        phase = str(event.get("phase") or "")
        if phase:
            latest[phase] = event

    # If a later phase is active, treat earlier unfinished phases as completed for display
    active_idx = -1
    for i, phase in enumerate(PHASE_ORDER):
        if phase in latest:
            active_idx = i
    display_latest = dict(latest)
    for i, phase in enumerate(PHASE_ORDER):
        if i < active_idx and phase not in display_latest:
            display_latest[phase] = {
                "phase": phase,
                "status": "completed",
                "message": "",
            }
        elif i < active_idx and str(display_latest[phase].get("status")) == "waiting":
            # Planning was waiting, then pipeline continued — show completed
            if any(
                p in latest and str(latest[p].get("status")) in {"running", "completed", "waiting"}
                for p in PHASE_ORDER[i + 1 :]
            ):
                display_latest[phase] = {
                    **display_latest[phase],
                    "status": "completed",
                    "message": display_latest[phase].get("message") or "Approved",
                }

    badge_cls, badge_label, hint = _overall_status(display_latest, log)

    items_html: list[str] = []
    for phase in PHASE_ORDER:
        cls, detail = _phase_state(phase, display_latest)
        icon_map = {
            "ep-idle": "○",
            "ep-run": "●",
            "ep-done": "✓",
            "ep-wait": "❚❚",
            "ep-err": "✕",
        }
        icon = icon_map.get(cls, "○")
        detail_html = (
            f"<small>{html.escape(detail[:90])}</small>" if detail else ""
        )
        items_html.append(
            f'<li class="ep-item {cls}">'
            f'<span class="ep-dot {cls}" aria-hidden="true">{icon}</span>'
            f'<span class="ep-label">{html.escape(phase)}{detail_html}</span>'
            f"</li>"
        )

    st.markdown(
        f"""
<div class="ep-wrap">
  <div class="ep-head">
    <p class="ep-title">Execution</p>
    <span class="ep-badge {badge_cls}">{html.escape(badge_label)}</span>
  </div>
  <p class="ep-hint">{html.escape(hint)}</p>
  <ul class="ep-list">
    {''.join(items_html)}
  </ul>
</div>
""",
        unsafe_allow_html=True,
    )

    snap = st.session_state.get("multi_agent_snapshot") or {}
    if snap.get("interrupted"):
        st.caption("Action needed → Approve / Reject the plan in the chat column.")

    if log:
        with st.expander("Detailed agent log", expanded=False):
            for event in log:
                status = str(event.get("status") or "")
                icon = STATUS_ICON.get(status, "•")
                st.markdown(
                    f"{icon} **{event.get('phase')}** — {event.get('message')}"
                )
                if event.get("detail"):
                    st.caption(str(event["detail"])[:400])
        if st.button("Clear execution", use_container_width=True, key="ep_clear_log"):
            st.session_state.multi_agent_log = []
            st.session_state.multi_agent_snapshot = {}
            st.session_state.pending_tool_actions = []
            st.session_state.pop("active_edit_plan", None)
            st.rerun()


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
