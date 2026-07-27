"""Chat sessions panel: multi-chat CRUD + search."""

from __future__ import annotations

import streamlit as st

from src.sessions.store import SessionStore


def sync_messages_from_session(store: SessionStore) -> None:
    """Load active session messages into Streamlit session_state."""
    session = store.ensure_active()
    st.session_state.active_chat_id = session.id
    st.session_state.messages = list(session.messages)
    st.session_state.pending_writes = st.session_state.get("pending_writes", [])


def persist_messages_to_session(store: SessionStore) -> None:
    """Write current chat messages back to the active session file."""
    session = store.ensure_active()
    session.messages = list(st.session_state.get("messages") or [])
    # Auto-title from first user message if still default
    if session.title in {"New chat", "Chat"} and session.messages:
        for msg in session.messages:
            if msg.get("role") == "user":
                text = str(msg.get("content") or "").strip().replace("\n", " ")
                session.title = (text[:48] + "…") if len(text) > 48 else (text or "Chat")
                break
    store.save(session)
    store.set_active(session.id)


def render_chat_sessions(project_path: str | None) -> SessionStore | None:
    st.markdown("#### Chats")
    if not project_path:
        st.caption("Open a project for per-project chat history.")
        return None

    store = SessionStore(project_path)
    # Ensure at least one session exists
    store.ensure_active()

    search = st.text_input(
        "Search chats",
        key="chat_search",
        placeholder="Search titles or messages…",
        label_visibility="collapsed",
    )
    sessions = store.search(search) if search.strip() else store.list_sessions()
    active_id = store.active_id()

    if st.button("＋ New chat", use_container_width=True, key="new_chat_btn"):
        persist_messages_to_session(store)
        store.create("New chat")
        sync_messages_from_session(store)
        st.rerun()

    for session in sessions[:30]:
        is_active = session.id == active_id
        label = f"{'▸ ' if is_active else ''}{session.title}"
        cols = st.columns([4, 1, 1, 1])
        if cols[0].button(
            label,
            key=f"chat_{session.id}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            if not is_active:
                persist_messages_to_session(store)
                store.set_active(session.id)
                sync_messages_from_session(store)
                st.rerun()
        if cols[1].button("✎", key=f"rename_btn_{session.id}", help="Rename"):
            st.session_state[f"renaming_{session.id}"] = True
        if cols[2].button("⧉", key=f"dup_{session.id}", help="Duplicate"):
            persist_messages_to_session(store)
            store.duplicate(session.id)
            sync_messages_from_session(store)
            st.rerun()
        if cols[3].button("🗑", key=f"del_{session.id}", help="Delete"):
            store.delete(session.id)
            sync_messages_from_session(store)
            st.rerun()

        if st.session_state.get(f"renaming_{session.id}"):
            new_title = st.text_input(
                "Rename chat",
                value=session.title,
                key=f"rename_input_{session.id}",
            )
            if st.button("Save name", key=f"save_rename_{session.id}"):
                store.rename(session.id, new_title)
                st.session_state[f"renaming_{session.id}"] = False
                st.rerun()

    return store
