"""Recent activity panel."""

from __future__ import annotations

import streamlit as st

from src.workspace.activity import ActivityStore


def render_activity(project_path: str | None) -> None:
    st.markdown("#### Recent Activity")
    if not project_path:
        st.caption("Open a project to see activity.")
        return

    store = ActivityStore(project_path)
    kind = st.selectbox(
        "Filter",
        ["all", "file", "search", "prompt", "edit"],
        key="activity_filter",
        label_visibility="collapsed",
    )
    items = store.list(kind=None if kind == "all" else kind, limit=15)  # type: ignore[arg-type]
    if not items:
        st.caption("No activity yet.")
        return

    icons = {"file": "📄", "search": "🔎", "prompt": "💬", "edit": "✏️"}
    for item in items:
        icon = icons.get(item.kind, "•")
        st.markdown(f"{icon} `{item.kind}` — {item.text}")
        if item.path:
            st.caption(item.path)
