"""Execution plan viewer — approve before any edits are generated."""

from __future__ import annotations

import streamlit as st

from src.agent.planner import AgentCoder, AgentPlanner, EditPlan
from src.llm.ollama_client import OllamaClient


def render_plan_viewer(
    project_path: str | None,
    client: OllamaClient | None = None,
) -> None:
    plan_data = st.session_state.get("active_edit_plan")
    if not plan_data:
        return
    plan = EditPlan.from_dict(plan_data) if isinstance(plan_data, dict) else plan_data

    st.info("**Agent execution plan** — nothing is written until you approve.")
    st.markdown(f"**Goal:** {plan.goal}")
    st.markdown(f"**Summary:** {plan.summary}")
    if plan.analysis:
        with st.expander("Analysis", expanded=False):
            st.markdown(plan.analysis)
    if plan.steps:
        st.markdown("**Steps**")
        for i, step in enumerate(plan.steps, 1):
            st.markdown(f"{i}. {step}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Files to modify**")
        if plan.files_to_modify:
            for p in plan.files_to_modify:
                st.markdown(f"- `{p}`")
        else:
            st.caption("(none)")
    with col_b:
        st.markdown("**New files**")
        if plan.files_to_create:
            for p in plan.files_to_create:
                st.markdown(f"- `{p}`")
        else:
            st.caption("(none)")

    if plan.notes:
        st.caption(f"Notes: {plan.notes}")

    if plan.status == "awaiting_approval":
        c1, c2 = st.columns(2)
        if c1.button("Approve plan & generate edits", type="primary", use_container_width=True):
            if not project_path or client is None:
                st.error("Need an open project and running model.")
            else:
                with st.spinner("Generating proposed edits (still not writing to disk)…"):
                    plan.status = "generating"
                    st.session_state.active_edit_plan = plan.to_dict()
                    coder = AgentCoder(client)
                    edits = coder.generate_edits(project_path, plan)
                    st.session_state.proposed_edits = [e.to_dict() for e in edits]
                    st.session_state.proposed_edits_note = plan.goal
                    plan.status = "ready"
                    st.session_state.active_edit_plan = plan.to_dict()
                    if project_path:
                        AgentPlanner(client).save_plan(project_path, plan)
                st.success(
                    f"Prepared {len(edits)} proposed edit(s). Review diffs below, then Accept/Reject."
                )
                st.rerun()
        if c2.button("Reject plan", use_container_width=True):
            plan.status = "rejected"
            st.session_state.active_edit_plan = plan.to_dict()
            st.rerun()
    elif plan.status == "ready":
        st.success("Plan approved — review diffs and accept individual files.")
    elif plan.status == "rejected":
        st.warning("Plan rejected. Ask again in Agent mode to create a new plan.")
