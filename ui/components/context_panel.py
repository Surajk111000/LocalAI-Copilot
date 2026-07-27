"""Context manager panel: pinned files + token estimate."""

from __future__ import annotations

import streamlit as st

from src.context.manager import ContextManager


def render_context_panel(project_path: str | None) -> None:
    st.markdown("#### AI Context")
    if not project_path:
        st.caption("Open a project to manage context files.")
        return

    ctx = ContextManager(project_path)
    files = ctx.list_files()
    total = ctx.total_tokens()
    st.markdown(
        f'<span class="token-pill">~{total:,} tokens</span>',
        unsafe_allow_html=True,
    )
    st.caption(f"{len(files)} file(s) in context")

    if not files:
        st.caption("No files in context. Use Explorer → Add to Context.")
        return

    for item in files:
        pin = "📌" if item.pinned else "📎"
        cols = st.columns([3, 1, 1, 1])
        cols[0].markdown(f"{pin} `{item.path}`  \n~{item.tokens} tok")
        if cols[1].button("Pin" if not item.pinned else "Unpin", key=f"pin_{item.path}"):
            ctx.pin(item.path, not item.pinned)
            st.rerun()
        if cols[2].button("✕", key=f"rm_{item.path}", help="Remove"):
            ctx.remove(item.path)
            st.rerun()

    c1, c2 = st.columns(2)
    if c1.button("Remove all", use_container_width=True, key="ctx_clear_all"):
        ctx.clear(keep_pinned=False)
        st.rerun()
    if c2.button("Keep pinned only", use_container_width=True, key="ctx_keep_pinned"):
        ctx.clear(keep_pinned=True)
        st.rerun()
