"""Multi-project manager sidebar UI."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.workspace.manager import WorkspaceManager


def render_project_manager(wm: WorkspaceManager) -> str | None:
    """Render open/recent projects. Returns active project path or None."""
    st.markdown("#### Projects")
    open_box = st.text_input(
        "Open project folder",
        placeholder=r"G:\Projects\my-app",
        key="open_project_input",
        label_visibility="collapsed",
    )
    cols = st.columns([2, 1])
    if cols[0].button("Open", use_container_width=True, type="primary", key="btn_open_project"):
        path = (open_box or "").strip().strip('"').strip("'")
        if path:
            try:
                wm.open_project(path)
                st.session_state.project_path = path
                st.session_state.explain_path_input = path
                st.session_state.explain_target_path = path
                st.session_state._workspace_switch = True
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    if cols[1].button("Close", use_container_width=True, key="btn_close_active"):
        active = wm.active()
        if active:
            wm.close_project(active)
            st.session_state._workspace_switch = True
            st.rerun()

    open_projects = wm.list_open()
    active = wm.active()
    if not open_projects:
        st.caption("No projects open yet.")
    for entry in open_projects:
        is_active = entry.path == active
        label = f"{'●' if is_active else '○'} {entry.name}"
        row = st.columns([4, 1])
        if row[0].button(
            label,
            key=f"proj_{entry.path}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
            help=entry.path,
        ):
            if not is_active:
                wm.set_active(entry.path)
                st.session_state.project_path = entry.path
                st.session_state.explain_path_input = entry.path
                st.session_state.explain_target_path = entry.path
                st.session_state._workspace_switch = True
                st.rerun()
        if row[1].button("✕", key=f"close_{entry.path}", help="Close project"):
            wm.close_project(entry.path)
            st.session_state._workspace_switch = True
            st.rerun()
        st.caption(entry.path)

    recent = wm.list_recent(8)
    if recent:
        with st.expander("Recent projects", expanded=False):
            for entry in recent:
                if st.button(
                    entry.name,
                    key=f"recent_{entry.path}",
                    use_container_width=True,
                    help=entry.path,
                ):
                    try:
                        wm.open_project(entry.path)
                        st.session_state.project_path = entry.path
                        st.session_state.explain_path_input = entry.path
                        st.session_state.explain_target_path = entry.path
                        st.session_state._workspace_switch = True
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(str(exc))

    if active and Path(active).is_dir():
        st.session_state.project_path = active
        return active
    return st.session_state.get("project_path")
