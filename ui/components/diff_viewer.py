"""Diff viewer + accept/reject for proposed multi-file edits."""

from __future__ import annotations

import streamlit as st

from src.editing.apply import ProposedEdit, apply_edit
from src.editing.versions import VersionStore
from src.workspace.activity import ActivityStore


def _edits_from_state() -> list[ProposedEdit]:
    raw = st.session_state.get("proposed_edits") or []
    out: list[ProposedEdit] = []
    for item in raw:
        if isinstance(item, ProposedEdit):
            out.append(item)
        elif isinstance(item, dict):
            out.append(ProposedEdit.from_dict(item))
    return out


def _save_edits(edits: list[ProposedEdit]) -> None:
    st.session_state.proposed_edits = [e.to_dict() for e in edits]


def render_diff_viewer(project_path: str | None) -> None:
    edits = _edits_from_state()
    if not edits:
        return

    pending = [e for e in edits if e.status == "pending"]
    st.warning(f"{len(pending)} proposed file change(s) awaiting approval")

    c1, c2, c3 = st.columns(3)
    if c1.button("Accept all pending", type="primary", use_container_width=True, key="diff_accept_all"):
        if not project_path:
            st.error("Open a project first.")
        else:
            batch_note = st.session_state.get("proposed_edits_note", "multi-file edit")
            for edit in edits:
                if edit.status != "pending":
                    continue
                ok, msg = apply_edit(project_path, edit, note=batch_note)
                edit.status = "accepted" if ok else "pending"
                if ok:
                    ActivityStore(project_path).add("edit", f"Accepted {edit.path}", edit.path)
                else:
                    st.error(msg)
            _save_edits(edits)
            st.success("Accepted pending edits (history saved for undo).")
            st.rerun()

    if c2.button("Reject all pending", use_container_width=True, key="diff_reject_all"):
        for edit in edits:
            if edit.status == "pending":
                edit.status = "rejected"
        _save_edits(edits)
        st.rerun()

    if c3.button("Clear finished", use_container_width=True, key="diff_clear_done"):
        remaining = [e for e in edits if e.status == "pending"]
        _save_edits(remaining)
        st.rerun()

    for i, edit in enumerate(edits):
        stats = edit.stats()
        badge = edit.status.upper()
        title = (
            f"[{badge}] {'Create' if edit.is_new else 'Modify'}: `{edit.path}` "
            f"(+{stats['added']}/-{stats['removed']})"
        )
        with st.expander(title, expanded=edit.status == "pending"):
            tabs = st.tabs(["Diff", "OLD", "NEW"])
            with tabs[0]:
                diff_text = edit.unified() or "(no textual diff)"
                st.code(diff_text, language="diff")
            with tabs[1]:
                st.code(edit.old_content or "(new file)", language="text")
            with tabs[2]:
                st.code(edit.new_content or "", language="text")

            if edit.status == "pending":
                a, b = st.columns(2)
                if a.button("Accept file", key=f"accept_edit_{i}", type="primary"):
                    if not project_path:
                        st.error("Open a project first.")
                    else:
                        ok, msg = apply_edit(
                            project_path,
                            edit,
                            note=st.session_state.get("proposed_edits_note", edit.note),
                        )
                        if ok:
                            edit.status = "accepted"
                            ActivityStore(project_path).add("edit", f"Accepted {edit.path}", edit.path)
                            _save_edits(edits)
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                if b.button("Reject file", key=f"reject_edit_{i}"):
                    edit.status = "rejected"
                    _save_edits(edits)
                    st.rerun()


def render_version_history(project_path: str | None) -> None:
    st.markdown("#### Version History / Undo")
    if not project_path:
        st.caption("Open a project to view accepted edits.")
        return
    store = VersionStore(project_path)
    if st.button("Undo latest accepted edit", use_container_width=True, key="undo_latest"):
        ok, msg = store.undo_latest()
        if ok:
            ActivityStore(project_path).add("edit", msg)
            st.success(msg)
            st.rerun()
        else:
            st.warning(msg)

    recent = store.list_recent(12)
    if not recent:
        st.caption("No accepted modifications yet.")
        return
    for item in recent:
        cols = st.columns([4, 1])
        cols[0].markdown(
            f"`{item.get('path')}` — {item.get('note') or ''}  \n"
            f"<small>{item.get('created_at')}</small>",
            unsafe_allow_html=True,
        )
        if cols[1].button("Undo", key=f"undo_{item['id']}"):
            ok, msg = store.undo_version(item["id"])
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
