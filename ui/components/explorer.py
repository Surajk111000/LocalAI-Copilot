"""Project explorer panel with file actions menu."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.context.manager import ContextManager
from src.explorer.actions import copy_path_text, delete_path, read_file, rename_path
from src.explorer.tree import build_tree, file_icon, search_files
from src.workspace.activity import ActivityStore


def _flatten_files(node, out: list[str] | None = None) -> list[str]:
    out = out if out is not None else []
    if not node.is_dir:
        out.append(node.path)
    for child in node.children or []:
        _flatten_files(child, out)
    return out


def _render_tree_node(node, depth: int = 0, key_prefix: str = "tree") -> None:
    indent = " " * depth
    icon = file_icon(node.name, node.is_dir)
    label = f"{indent}{icon} {node.name}"
    if node.is_dir:
        with st.expander(label if depth else f"{icon} {node.name}", expanded=depth < 1):
            for child in node.children or []:
                _render_tree_node(child, depth + 1, key_prefix=f"{key_prefix}_{node.name}")
    else:
        if st.button(label, key=f"{key_prefix}_{node.path}", use_container_width=True):
            st.session_state.selected_explorer_path = node.path


def render_explorer(project_path: str | None) -> None:
    st.markdown("#### Explorer")
    if not project_path or not Path(project_path).is_dir():
        st.caption("Open a project to browse files.")
        return

    query = st.text_input(
        "Search files",
        key="explorer_search",
        placeholder="filename…",
        label_visibility="collapsed",
    )
    if query.strip():
        hits = search_files(project_path, query, limit=40)
        st.caption(f"{len(hits)} match(es)")
        for hit in hits:
            icon = file_icon(Path(hit).name, False)
            if st.button(f"{icon} {hit}", key=f"search_hit_{hit}", use_container_width=True):
                st.session_state.selected_explorer_path = hit
    else:
        with st.spinner("Loading tree…"):
            tree = build_tree(project_path, max_depth=5, max_entries=1200)
        # Flat file picker is more reliable in Streamlit than deep nested expanders.
        files = _flatten_files(tree)
        with st.expander("Folder tree", expanded=True):
            st.caption(f"{len(files)} files indexed in tree view")
            # Show top-level folders as expanders with files
            by_dir: dict[str, list[str]] = {}
            for f in files:
                parent = str(Path(f).parent).replace("\\", "/")
                if parent == ".":
                    parent = "(root)"
                by_dir.setdefault(parent, []).append(f)
            for folder in sorted(by_dir.keys())[:80]:
                with st.expander(f"📁 {folder}", expanded=False):
                    for f in by_dir[folder][:80]:
                        icon = file_icon(Path(f).name, False)
                        if st.button(
                            f"{icon} {Path(f).name}",
                            key=f"file_{f}",
                            use_container_width=True,
                            help=f,
                        ):
                            st.session_state.selected_explorer_path = f

    selected = st.session_state.get("selected_explorer_path")
    if selected:
        st.markdown(f"**Selected:** `{selected}`")
        action = st.selectbox(
            "File action (right-click substitute)",
            [
                "— choose action —",
                "Explain",
                "Read",
                "Open",
                "Rename",
                "Delete",
                "Copy Path",
                "Add to Context",
            ],
            key="explorer_action",
        )
        new_name = ""
        if action == "Rename":
            new_name = st.text_input("New name", value=Path(selected).name, key="explorer_rename")
        confirm_delete = False
        if action == "Delete":
            confirm_delete = st.checkbox("Confirm delete", key="explorer_delete_confirm")

        if st.button("Run action", use_container_width=True, key="explorer_run_action"):
            _run_action(project_path, selected, action, new_name, confirm_delete)


def _run_action(
    project_path: str,
    selected: str,
    action: str,
    new_name: str,
    confirm_delete: bool,
) -> None:
    activity = ActivityStore(project_path)
    ctx = ContextManager(project_path)

    if action == "Explain":
        abs_path = str((Path(project_path) / selected).resolve())
        st.session_state.explain_path_input = abs_path
        st.session_state.explain_target_path = abs_path
        st.session_state.pending_prompt = "Explain this file"
        activity.add("file", f"Explain {selected}", selected)
        st.rerun()
    elif action == "Read":
        result = read_file(project_path, selected)
        if result.ok:
            st.session_state.explorer_preview = result.content
            st.session_state.explorer_preview_path = selected
            activity.add("file", f"Read {selected}", selected)
            st.success(result.message)
        else:
            st.error(result.message)
    elif action == "Open":
        abs_path = str((Path(project_path) / selected).resolve())
        st.session_state.explain_path_input = abs_path
        st.session_state.explain_target_path = abs_path
        result = read_file(project_path, selected)
        if result.ok:
            st.session_state.explorer_preview = result.content
            st.session_state.explorer_preview_path = selected
        activity.add("file", f"Open {selected}", selected)
        st.success(f"Opened {selected}")
    elif action == "Rename":
        result = rename_path(project_path, selected, new_name)
        if result.ok:
            st.session_state.selected_explorer_path = result.path
            activity.add("edit", f"Renamed to {result.path}", result.path)
            st.success(result.message)
            st.rerun()
        else:
            st.error(result.message)
    elif action == "Delete":
        if not confirm_delete:
            st.warning("Check Confirm delete first.")
            return
        result = delete_path(project_path, selected)
        if result.ok:
            st.session_state.selected_explorer_path = None
            activity.add("edit", f"Deleted {selected}", selected)
            st.success(result.message)
            st.rerun()
        else:
            st.error(result.message)
    elif action == "Copy Path":
        result = copy_path_text(project_path, selected, absolute=True)
        if result.ok:
            st.code(result.content, language="text")
            st.session_state.copied_path = result.content
            st.success("Path shown above — select and copy.")
        else:
            st.error(result.message)
    elif action == "Add to Context":
        entry = ctx.add(selected)
        if entry:
            activity.add("file", f"Added to context: {selected}", selected)
            st.success(f"Added `{selected}` (~{entry.tokens} tokens)")
        else:
            st.error("Could not add file to context.")
    else:
        st.info("Choose an action first.")
