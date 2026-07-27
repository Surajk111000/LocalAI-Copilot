"""Workspace settings panel (per-project)."""

from __future__ import annotations

import streamlit as st

from src.productivity.personas import list_personas
from src.system_info import clamp_threads, get_system_resources
from src.workspace.paths import project_id_for_path
from src.workspace.settings import ProjectSettings, SettingsStore


def render_workspace_settings(
    project_path: str | None,
    chat_models: list[str],
    default_model: str,
) -> ProjectSettings:
    st.markdown("#### Workspace Settings")
    if not project_path:
        st.caption("Open a project to save settings.")
        return ProjectSettings(preferred_model=default_model)

    store = SettingsStore(project_path)
    settings = store.load()
    info = get_system_resources()
    pid = project_id_for_path(project_path)

    options = chat_models or [default_model]
    preferred = settings.preferred_model if settings.preferred_model in options else (
        default_model if default_model in options else options[0]
    )
    index = options.index(preferred)

    model = st.selectbox(
        "Preferred model",
        options=options,
        index=index,
        key=f"ws_model_{pid}",
    )
    personas = list_personas()
    persona_ids = [p.id for p in personas]
    persona_index = (
        persona_ids.index(settings.persona_id)
        if settings.persona_id in persona_ids
        else 0
    )
    persona_id = st.selectbox(
        "AI persona",
        options=persona_ids,
        index=persona_index,
        format_func=lambda i: next(p.name for p in personas if p.id == i),
        key=f"ws_persona_{pid}",
    )
    st.session_state.persona_id = persona_id

    theme = st.radio(
        "Theme",
        ["dark", "light"],
        index=0 if settings.theme != "light" else 1,
        horizontal=True,
        key=f"ws_theme_{pid}",
    )
    st.session_state.ui_theme = theme

    rag_enabled = st.toggle(
        "RAG enabled", value=settings.rag_enabled, key=f"ws_rag_{pid}"
    )
    filesystem_enabled = st.toggle(
        "Filesystem tools",
        value=settings.filesystem_enabled,
        key=f"ws_fs_{pid}",
    )
    streaming = st.toggle(
        "Streaming responses",
        value=settings.streaming,
        key=f"ws_stream_{pid}",
    )
    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=float(settings.temperature),
        step=0.05,
        key=f"ws_temp_{pid}",
    )
    top_p = st.slider(
        "Top P",
        min_value=0.1,
        max_value=1.0,
        value=float(settings.top_p),
        step=0.05,
        key=f"ws_top_p_{pid}",
    )
    context_size = st.select_slider(
        "Context size (num_ctx)",
        options=[2048, 4096, 6144, 8192],
        value=int(settings.context_size)
        if int(settings.context_size) in {2048, 4096, 6144, 8192}
        else 4096,
        key=f"ws_ctx_{pid}",
    )
    safe_default = clamp_threads(int(settings.cpu_threads), info)
    cpu_threads = st.slider(
        "CPU threads",
        min_value=info.safe_min_threads,
        max_value=info.safe_max_threads,
        value=safe_default,
        key=f"ws_threads_{pid}",
    )
    system_prompt = st.text_area(
        "System prompt override",
        value=settings.system_prompt,
        height=100,
        key=f"ws_prompt_{pid}",
    )

    updated = ProjectSettings(
        preferred_model=model,
        rag_enabled=rag_enabled,
        cpu_threads=int(cpu_threads),
        temperature=float(temperature),
        top_p=float(top_p),
        context_size=int(context_size),
        streaming=bool(streaming),
        filesystem_enabled=filesystem_enabled,
        persona_id=persona_id,
        theme=theme,
        system_prompt=system_prompt,
    )
    store.save(updated)
    return updated
