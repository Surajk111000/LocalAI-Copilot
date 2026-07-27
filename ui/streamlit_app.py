"""Streamlit UI for the local coding copilot.

Phases:
1) Chat with local LLM
2) RAG over a project folder
3) Filesystem tools with write approval
4) Multi-workspace
5) Cursor-style Agent mode (plan → approve → diff → apply)
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.mode import CopilotMode, is_agent_mode
from src.agents.tool_agent import ToolAgent
from src.code_search import extract_search_query, search_project, wants_code_search
from src.config import get_ollama_settings, get_rag_settings, load_config
from src.context.manager import ContextManager
from src.editing.apply import ProposedEdit, build_proposed_edit
from src.llm.ollama_client import (
    OllamaClient,
    OllamaError,
    build_messages,
    is_chat_model,
)
from src.project_overview import (
    build_path_context,
    build_project_overview,
    wants_project_explanation,
)
from src.quick_actions import (
    extract_file_path,
    handle_create_prepare,
    handle_list,
    handle_read,
    propose_write_from_answer,
    wants_create_file,
    wants_list_files,
    wants_read_file,
)
from src.rag.embeddings import OllamaEmbedder
from src.rag.ingest import ProjectIndexer
from src.rag.retriever import ProjectRetriever
from src.search.smart_search import smart_search, wants_smart_where
from src.sessions.store import SessionStore
from src.system_info import clamp_threads, get_system_resources
from ui.components.cpu_safety import enforce_cpu_safety, render_cpu_safety_panel
from src.tools.filesystem import FileSystemTools, PendingWrite
from src.workspace.activity import ActivityStore
from src.workspace.manager import WorkspaceManager
from src.workspace.settings import ProjectSettings
from ui.components.activity import render_activity
from ui.components.agent_toolbox import render_agent_toolbox
from ui.components.chat_sessions import (
    persist_messages_to_session,
    render_chat_sessions,
    sync_messages_from_session,
)
from ui.components.context_panel import render_context_panel
from ui.components.diff_viewer import render_diff_viewer, render_version_history
from ui.components.execution_panel import (
    render_execution_panel,
    render_pending_tool_approvals,
)
from ui.components.explorer import render_explorer
from ui.components.multi_agent_panel import (
    render_multi_agent_controls,
    start_multi_agent,
)
from ui.components.plan_viewer import render_plan_viewer
from ui.components.sidebar_projects import render_project_manager
from ui.components.productivity_hub import render_dashboard, render_productivity_hub
from ui.components.theme import brand_header, inject_theme
from ui.components.workspace_settings import render_workspace_settings
from src.productivity.devlog import console
from src.productivity.metrics import MetricsStore
from src.productivity.personas import persona_system_prompt
from src.productivity.rules import load_project_rules


def wants_agent_feature(prompt: str) -> bool:
    """Heuristic: user is asking the agent to implement/change code."""
    text = (prompt or "").lower().strip()
    starters = (
        "add ",
        "implement ",
        "create ",
        "build ",
        "refactor ",
        "update ",
        "modify ",
        "fix ",
        "migrate ",
        "introduce ",
        "wire ",
        "integrate ",
    )
    return any(text.startswith(s) for s in starters) or "authentication" in text


def overview_is_file_prompt(prompt: str) -> bool:
    """True only for single-file explain requests (not whole-project)."""
    text = (prompt or "").lower()
    if "project" in text or "folder" in text or "structure" in text:
        return False
    return "explain this file" in text or text.strip() == "explain this code"


def prompt_needs_tools(prompt: str) -> bool:
    """Return True only when the user clearly wants filesystem actions.

    Simple 'write a function' prompts should use fast streaming chat instead of
    the slower multi-step tool agent (important on a 3B local model).
    """
    text = (prompt or "").lower()
    keywords = (
        "list the",
        "list files",
        "list directory",
        "list project",
        "read ",
        "open ",
        "search for",
        "search files",
        "find where",
        "find file",
        "create file",
        "create a file",
        "write file",
        "write to",
        "save to",
        "edit ",
        "modify ",
        "update file",
        "overwrite",
        "in the project",
        "in this project",
        "into the project",
        "examples/",
        "src/",
        ".py file",
    )
    return any(k in text for k in keywords)


def init_page() -> None:
    config = load_config()
    ui = config.get("ui", {})
    st.set_page_config(
        page_title=ui.get("title", "Local AI Coding Copilot"),
        page_icon=ui.get("page_icon", "💻"),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme(st.session_state.get("ui_theme", "dark"))


def get_client(
    model: str,
    num_thread: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    num_ctx: int | None = None,
) -> OllamaClient:
    settings = get_ollama_settings()
    thread = num_thread
    if thread is None and settings.get("num_thread") is not None:
        thread = int(settings["num_thread"])
    temp = settings["temperature"] if temperature is None else temperature
    return OllamaClient(
        base_url=settings["base_url"],
        model=model,
        temperature=temp,
        top_p=0.9 if top_p is None else top_p,
        num_predict=settings["num_predict"],
        num_ctx=num_ctx,
        num_thread=thread,
    )


def get_embedder() -> OllamaEmbedder:
    settings = get_ollama_settings()
    return OllamaEmbedder(
        base_url=settings["base_url"],
        model=settings["embed_model"],
    )


def render_resource_controls(*, show_slider: bool = True) -> int:
    """Show CPU/RAM usage and optional CPU-thread slider for Ollama."""
    info = get_system_resources()
    st.markdown("---")
    st.subheader("Hardware (safe limits)")

    st.markdown(
        f"**CPU:** {info.physical_cores} cores / {info.logical_cores} threads  \n"
        f"**RAM:** {info.ram_used_gb} / {info.ram_total_gb} GB used "
        f"({info.ram_percent}%)  \n"
        f"**Free RAM:** {info.ram_available_gb} GB"
    )

    if info.ollama_rss_gb is not None:
        st.markdown(f"**Ollama RAM now:** ~{info.ollama_rss_gb} GB")
    else:
        st.caption("Ollama process memory: not detected yet")

    st.progress(min(info.ram_percent / 100.0, 1.0))

    if not show_slider:
        current = clamp_threads(
            int(st.session_state.get("num_thread", info.recommended_threads)),
            info,
        )
        st.caption(
            f"Threads controlled in Workspace settings "
            f"(now {current}; safe {info.safe_min_threads}–{info.safe_max_threads})."
        )
        if info.ram_available_gb < 2.5:
            st.warning("Low free RAM (< 2.5 GB). Close other apps before generating.")
        return current

    default_threads = st.session_state.get(
        "num_thread", info.recommended_threads
    )
    default_threads = clamp_threads(int(default_threads), info)

    num_thread = st.slider(
        "CPU threads for LLM",
        min_value=info.safe_min_threads,
        max_value=info.safe_max_threads,
        value=default_threads,
        help=(
            "Safe range only: leaves CPU free for Windows + this UI. "
            "Higher = often faster generation, but the laptop may stutter."
        ),
    )
    st.session_state.num_thread = int(num_thread)

    st.caption(
        f"Safe range: {info.safe_min_threads}–{info.safe_max_threads} "
        f"(recommended {info.recommended_threads}). "
        "Max is capped so one core stays free."
    )
    if info.ram_available_gb < 2.5:
        st.warning(
            "Low free RAM (< 2.5 GB). Close other apps before generating."
        )
    return int(num_thread)


def sidebar(
    client: OllamaClient, default_model: str
) -> tuple[str, str | None, bool, bool, int, float, SessionStore | None, ProjectSettings]:
    """Returns model, project, rag, tools, threads, temperature, session store, settings."""
    wm = WorkspaceManager()
    session_store: SessionStore | None = None
    project_settings = ProjectSettings(preferred_model=default_model)

    available = False
    chat_models: list[str] = []
    embed_models: list[str] = []
    try:
        available = client.is_available()
        if available:
            chat_models = client.list_chat_models()
            embed_models = client.list_embed_models()
    except OllamaError:
        available = False

    with st.sidebar:
        st.markdown("### Workspace")
        st.caption("Local-only · Ollama on localhost:11434")
        if available:
            st.success("Ollama is running")
        else:
            st.error("Ollama is not running")
            st.markdown(
                "Install from [ollama.com](https://ollama.com), then:\n\n"
                "`ollama pull qwen2.5-coder:3b`\n\n"
                "`ollama pull nomic-embed-text`"
            )

        project_path = render_project_manager(wm)

        # Bootstrap: if nothing open but session has a path, open it
        if not project_path:
            fallback = st.session_state.get("project_path") or str(ROOT)
            if Path(fallback).is_dir():
                try:
                    project_path = wm.open_project(fallback)
                except Exception:
                    project_path = fallback if Path(fallback).is_dir() else None

        st.markdown("---")
        st.markdown("#### Copilot mode")
        mode = st.radio(
            "Mode",
            [CopilotMode.CHAT.value, CopilotMode.AGENT.value],
            format_func=lambda m: "Chat" if m == "chat" else "Agent (plan → approve → edit)",
            horizontal=True,
            key="copilot_mode",
            help=(
                "Chat: normal Q&A. "
                "Agent: analyze project, show an execution plan, then propose diffs. "
                "Nothing is written without your approval."
            ),
        )
        st.session_state.copilot_mode = mode
        if is_agent_mode(mode):
            st.caption("Agent mode: LangGraph multi-agent (plan → research → code → review → test → docs).")
        else:
            st.caption("Chat mode: fast conversation / explain / search.")

        st.markdown("---")
        with st.expander("Explorer", expanded=True):
            render_explorer(project_path)

        st.markdown("---")
        with st.expander("Chat sessions", expanded=True):
            session_store = render_chat_sessions(project_path)

        st.markdown("---")
        with st.expander("Workspace settings", expanded=False):
            if not chat_models:
                options = (
                    [default_model]
                    if is_chat_model(default_model)
                    else ["qwen2.5-coder:3b"]
                )
            else:
                options = chat_models
            project_settings = render_workspace_settings(
                project_path, options, default_model
            )
            inject_theme(project_settings.theme)

        st.markdown("---")
        with st.expander("AI Dashboard", expanded=False):
            render_dashboard(project_path)

        st.markdown("---")
        with st.expander("Productivity", expanded=False):
            # Client for toolbox will be recreated in main; use probe for generation helpers
            render_productivity_hub(project_path, client)

        # Sync toggles from per-project settings (source of truth)
        selected = project_settings.preferred_model
        use_rag = bool(project_settings.rag_enabled)
        use_tools = bool(project_settings.filesystem_enabled)
        num_thread = int(project_settings.cpu_threads)
        temperature = float(project_settings.temperature)
        st.session_state.use_rag = use_rag
        st.session_state.use_tools = use_tools
        st.session_state.num_thread = num_thread
        st.session_state.persona_id = project_settings.persona_id
        st.session_state.ui_theme = project_settings.theme
        st.session_state.project_path = project_path or st.session_state.get(
            "project_path", ""
        )

        st.markdown("---")
        st.subheader("Project memory (RAG)")
        if embed_models:
            st.success(f"Embed model ready: `{embed_models[0]}`")
        else:
            st.warning("No embed model. Run: `ollama pull nomic-embed-text`")

        if st.button("Index project", use_container_width=True, type="primary"):
            _run_indexing(project_path or "")

        if project_path:
            try:
                retriever = ProjectRetriever(get_embedder())
                if retriever.has_index(project_path):
                    st.info("Index found for this folder")
                else:
                    st.warning("Not indexed yet — click Index project")
            except Exception:
                st.caption("Index status unavailable until Ollama is running.")

        render_resource_controls(show_slider=False)
        render_cpu_safety_panel()

        st.markdown("---")
        if st.button("Clear current chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_writes = []
            if session_store:
                persist_messages_to_session(session_store)
            st.rerun()

        if st.button("⏹ Stop generation", use_container_width=True, type="secondary"):
            st.session_state.stop_generation = True
            st.session_state.pending_prompt = None
            st.session_state.pop("_quick_effective_prompt", None)
            st.warning("Stop requested — generation will cancel.")
            st.rerun()

        st.caption(
            "Tip for GTX 1050 (4GB): `qwen2.5-coder:3b` + `nomic-embed-text`."
        )

    # Load chat history when switching projects / first load
    if project_path and session_store:
        switched = st.session_state.pop("_workspace_switch", False)
        if switched or "messages" not in st.session_state or not st.session_state.get(
            "_sessions_bootstrapped"
        ):
            sync_messages_from_session(session_store)
            st.session_state._sessions_bootstrapped = True
            st.session_state._active_project_for_sessions = project_path
        elif st.session_state.get("_active_project_for_sessions") != project_path:
            sync_messages_from_session(session_store)
            st.session_state._active_project_for_sessions = project_path

    return (
        selected,
        project_path or None,
        use_rag,
        use_tools,
        num_thread,
        temperature,
        session_store,
        project_settings,
    )


def _run_indexing(project_path: str) -> None:
    if not project_path:
        st.sidebar.error("Enter a project folder path first.")
        return
    path = Path(project_path).expanduser()
    if not path.exists() or not path.is_dir():
        st.sidebar.error(f"Folder not found: {project_path}")
        return

    rag = get_rag_settings()
    indexer = ProjectIndexer(
        get_embedder(),
        chunk_size=rag["chunk_size"],
        overlap=rag["overlap"],
        batch_size=rag["batch_size"],
    )

    with st.sidebar.status("Indexing project…", expanded=True) as status:
        try:
            st.write("Reading files and creating embeddings (local)…")
            stats = indexer.index_project(path)
            status.update(
                label=(
                    f"Indexed {stats.chunks_indexed} chunks "
                    f"from {stats.files_indexed} files"
                ),
                state="complete",
            )
            st.session_state.last_index_stats = stats
        except OllamaError as exc:
            status.update(label="Indexing failed", state="error")
            st.error(str(exc))
        except Exception as exc:
            status.update(label="Indexing failed", state="error")
            st.error(f"Indexing error: {exc}")


def _pending_writes_to_proposed(project_path: str | None) -> None:
    """Migrate legacy PendingWrite list into ProposedEdit diff flow."""
    pending: list[PendingWrite] = list(st.session_state.get("pending_writes") or [])
    if not pending:
        return
    existing = st.session_state.get("proposed_edits") or []
    for write in pending:
        try:
            if project_path:
                edit = build_proposed_edit(
                    project_path,
                    write.path,
                    write.content,
                    note="tool/agent proposal",
                )
            else:
                edit = ProposedEdit(
                    path=write.path,
                    new_content=write.content,
                    old_content=getattr(write, "old_content", "") or "",
                    is_new=write.is_new,
                    absolute_path=write.absolute_path,
                )
            existing.append(edit.to_dict())
        except Exception:
            existing.append(
                ProposedEdit(
                    path=write.path,
                    new_content=write.content,
                    old_content=getattr(write, "old_content", "") or "",
                    is_new=write.is_new,
                    absolute_path=write.absolute_path,
                ).to_dict()
            )
    st.session_state.proposed_edits = existing
    st.session_state.pending_writes = []


def render_pending_writes(project_path: str | None) -> None:
    """Compatibility shim: fold old pending writes into the diff viewer."""
    _pending_writes_to_proposed(project_path)
    render_diff_viewer(project_path)


def _guess_lang(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".sql": "sql",
        ".toml": "toml",
        ".html": "html",
        ".css": "css",
    }.get(suffix, "text")


def render_chat(
    client: OllamaClient,
    project_path: str | None,
    use_rag: bool,
    use_tools: bool,
    session_store: SessionStore | None = None,
    project_settings: ProjectSettings | None = None,
) -> None:
    mode = st.session_state.get("copilot_mode", CopilotMode.CHAT.value)
    mode_label = "Agent" if is_agent_mode(mode) else "Chat"
    brand_header(
        f"{mode_label} mode · local Ollama · writes require approval · "
        f"threads: {getattr(client, 'num_thread', None) or 'auto'}"
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_writes" not in st.session_state:
        st.session_state.pending_writes = []
    if "proposed_edits" not in st.session_state:
        st.session_state.proposed_edits = []

    main_col, right_col = st.columns([3.2, 1.15], gap="medium")

    with right_col:
        with st.container(border=True):
            render_execution_panel()
        with st.container(border=True):
            render_context_panel(project_path)
        with st.container(border=True):
            render_version_history(project_path)
        with st.container(border=True):
            render_activity(project_path)
        preview = st.session_state.get("explorer_preview")
        if preview and st.session_state.get("explorer_preview_path"):
            with st.container(border=True):
                st.markdown("#### Preview")
                st.caption(st.session_state.explorer_preview_path)
                st.code(
                    preview[:6000],
                    language=_guess_lang(st.session_state.explorer_preview_path),
                )

    with main_col:
        if is_agent_mode(mode):
            with st.expander("Agent toolbox (search · symbols · inline · review · docs)", expanded=False):
                render_agent_toolbox(project_path, client)
        _render_chat_main(
            client,
            project_path,
            use_rag,
            use_tools,
            session_store,
            project_settings,
        )


def _render_chat_main(
    client: OllamaClient,
    project_path: str | None,
    use_rag: bool,
    use_tools: bool,
    session_store: SessionStore | None,
    project_settings: ProjectSettings | None,
) -> None:
    render_pending_writes(project_path)
    render_pending_tool_approvals(project_path)
    render_multi_agent_controls(client, project_path)
    # Legacy single-planner viewer only when not in LangGraph flow
    if not st.session_state.get("multi_agent_snapshot"):
        render_plan_viewer(project_path, client)

    mode = st.session_state.get("copilot_mode", CopilotMode.CHAT.value)
    if is_agent_mode(mode):
        st.markdown("### LangGraph multi-agent workflow")
        st.caption(
            "Ask for a feature (e.g. **Add JWT authentication**). "
            "Pipeline: Planner → Research → Analyzer → Coder → Reviewer → Tester → Docs → Final. "
            "Paused after Planning for your approval. **Nothing is written without Accept on diffs.**"
        )
    else:
        st.markdown("### Explain any local folder or file")
        st.caption(
            "Copy-paste any local path below (folder **or** single file). "
            "Example folder: `G:\\Projects\\my-app` — "
            "Example file: `G:\\Projects\\my-app\\src\\main.py`"
        )

    # Remember recent paths so switching projects is easy
    if "recent_explain_paths" not in st.session_state:
        st.session_state.recent_explain_paths = []
    if "explain_path_input" not in st.session_state:
        st.session_state.explain_path_input = (
            st.session_state.get("explain_target_path")
            or project_path
            or ""
        )

    explain_path = st.text_input(
        "Local path to explain (paste folder or file)",
        placeholder=r"G:\Projects\some-other-app   or   G:\Projects\app\src\main.py",
        key="explain_path_input",
    ).strip().strip('"').strip("'")
    st.session_state.explain_target_path = explain_path

    # Keep sidebar project path in sync when user pastes a folder
    if explain_path:
        p = Path(explain_path)
        if p.exists() and p.is_dir():
            st.session_state.project_path = explain_path
            try:
                WorkspaceManager().open_project(explain_path)
            except Exception:
                pass

    recent = [p for p in st.session_state.recent_explain_paths if p != explain_path]
    if recent:
        picked = st.selectbox(
            "Or pick a recent path",
            options=["(choose a recent path)"] + recent,
            index=0,
            key="recent_path_picker",
        )
        if picked != "(choose a recent path)" and st.button(
            "Load selected recent path", use_container_width=True
        ):
            st.session_state.explain_path_input = picked
            st.session_state.explain_target_path = picked
            if Path(picked).is_dir():
                st.session_state.project_path = picked
            elif Path(picked).is_file():
                st.session_state.project_path = str(Path(picked).parent)
            st.rerun()

    btn_cols = st.columns(3)
    with btn_cols[0]:
        if st.button(
            "Explain this folder/project",
            use_container_width=True,
            type="primary",
            disabled=not bool(explain_path),
        ):
            # Always explain the folder (if user pasted a file, use its parent)
            p = Path(explain_path)
            folder = str(p.parent if p.is_file() else p)
            st.session_state.explain_path_input = folder
            st.session_state.explain_target_path = folder
            st.session_state.project_path = folder
            st.session_state.force_explain_folder = True
            _remember_path(folder)
            st.session_state.pending_prompt = (
                "Explain this entire project folder: structure, pages, components, and how to run it"
            )
    with btn_cols[1]:
        if st.button(
            "Explain this file/code",
            use_container_width=True,
            disabled=not bool(explain_path),
        ):
            st.session_state.force_explain_folder = False
            _remember_path(explain_path)
            st.session_state.pending_prompt = "Explain this file"
    with btn_cols[2]:
        if st.button(
            "Use as active project",
            use_container_width=True,
            disabled=not bool(explain_path),
            help="Sets sidebar project path (for tools/RAG) to this folder.",
        ):
            p = Path(explain_path)
            folder = str(p.parent) if p.exists() and p.is_file() else explain_path
            st.session_state.project_path = folder
            try:
                WorkspaceManager().open_project(folder)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
            _remember_path(explain_path)
            st.success("Active project path updated.")
            st.rerun()

    st.markdown("**Try a command** (uses your active/pasted project path):")

    prompt_groups = {
        "Project": [
            "List the project files and explain the folder structure",
            "Read src/config.py and explain what each setting does",
            "Search for OllamaClient and tell me which files define or use it",
            "Where is login?",
        ],
        "Agent edits": [
            "Add JWT authentication",
            "Add a /health endpoint",
            "Generate pytest tests for the main module",
        ],
        "Create / write": [
            "Create examples/hello.py with a hello_world() function and a main block",
            "Create examples/fastapi_hello.py with a FastAPI /health endpoint",
        ],
        "Code generation": [
            "Write a FastAPI hello world app with / and /health endpoints",
            "Write a Python function to reverse a linked list with docstring and example",
            "Generate a Dockerfile for a Python FastAPI app using uvicorn",
        ],
    }

    for group_name, prompts in prompt_groups.items():
        st.caption(group_name)
        cols = st.columns(len(prompts))
        for col, example in zip(cols, prompts):
            if col.button(example, use_container_width=True, key=f"ex_{hash(example)}"):
                st.session_state.pending_prompt = example

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("sources"):
                with st.expander("Files used"):
                    for src in message["sources"]:
                        if "start_line" in src:
                            st.markdown(
                                f"- `{src['path']}` "
                                f"(lines {src['start_line']}-{src['end_line']})"
                            )
                        else:
                            st.markdown(f"- `{src['path']}`")
            if message.get("tool_trace"):
                with st.expander("Tool calls"):
                    for line in message["tool_trace"]:
                        st.code(line, language="text")

    prompt = st.chat_input("Type a coding command or project question…")
    if "pending_prompt" in st.session_state:
        prompt = st.session_state.pop("pending_prompt")

    # Handle stop even when no new prompt (interrupted mid-generation)
    if st.session_state.pop("stop_generation", False):
        reason = (
            "🛑 **CPU safety stop** — laptop load was too high. "
            "Unlock from the sidebar when it cools down."
            if st.session_state.get("cpu_safety_lock")
            else "⏹ Generation stopped."
        )
        with st.chat_message("assistant"):
            st.warning(reason)
        stop_text = (
            "_🛑 Generation stopped by CPU safety guard._"
            if st.session_state.get("cpu_safety_lock")
            else "_⏹ Generation stopped by user._"
        )
        if not st.session_state.messages or st.session_state.messages[-1].get("content") != stop_text:
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": stop_text,
                    "sources": [],
                    "tool_trace": [],
                }
            )
        if session_store:
            persist_messages_to_session(session_store)
        return

    if not prompt:
        return

    # Block new AI work when CPU/RAM safety lock is active
    if not enforce_cpu_safety(during_generation=False):
        with st.chat_message("assistant"):
            st.error(
                st.session_state.get("cpu_safety_status", {}).get("message")
                or "CPU safety lock is active. Unlock in the sidebar when load drops."
            )
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "_🛑 Blocked by CPU safety — unlock in the sidebar when the laptop cools down._",
                "sources": [],
                "tool_trace": ["cpu_safety"],
            }
        )
        if session_store:
            persist_messages_to_session(session_store)
        return

    if project_path:
        ActivityStore(project_path).add("prompt", prompt)

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
    ]

    context = ""
    sources: list[dict] = []
    explain_target = (
        st.session_state.get("explain_target_path")
        or project_path
        or ""
    ).strip()
    search_root = project_path or (
        explain_target if explain_target and Path(explain_target).is_dir() else ""
    )

    # Inject pinned / context-manager files first
    if project_path:
        pinned_block = ContextManager(project_path).build_context_block()
        if pinned_block:
            context = pinned_block

    # Agent mode: LangGraph multi-agent (pause after planner)
    if is_agent_mode(mode) and wants_agent_feature(prompt) and not wants_project_explanation(prompt):
        if not project_path:
            with st.chat_message("assistant"):
                st.error("Open a project first, then ask the agent to implement a change.")
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": "**Error:** No project open for Agent mode.",
                    "sources": [],
                    "tool_trace": [],
                }
            )
            if session_store:
                persist_messages_to_session(session_store)
            return
        with st.chat_message("assistant"):
            with st.spinner("LangGraph Planner agent running…"):
                snap = start_multi_agent(client, project_path, prompt)
            answer = (
                f"**Multi-agent plan ready** (LangGraph interrupted after Planner)\n\n"
                f"**Summary:** {snap.get('plan_summary')}\n\n"
                f"**Tasks:**\n"
                + ("\n".join(f"- {t}" for t in (snap.get("tasks") or [])) or "- (none)")
                + "\n\n**Files to modify:**\n"
                + ("\n".join(f"- `{p}`" for p in (snap.get("files_to_modify") or [])) or "- (none)")
                + "\n\n**New files:**\n"
                + ("\n".join(f"- `{p}`" for p in (snap.get("files_to_create") or [])) or "- (none)")
                + "\n\nApprove in the panel above to continue "
                "Research → Analyzer → Coder → Reviewer → Tester → Docs → Final.\n\n"
                "**No files were modified.**"
            )
            st.markdown(answer)
            ActivityStore(project_path).add("prompt", f"LangGraph plan: {prompt}")
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer,
                "sources": [
                    {"path": p}
                    for p in list(snap.get("files_to_modify") or [])
                    + list(snap.get("files_to_create") or [])
                ],
                "tool_trace": ["langgraph:planner"],
            }
        )
        if session_store:
            persist_messages_to_session(session_store)
        st.rerun()
        return

    # Smart "Where is X?" search
    if wants_smart_where(prompt) and project_path:
        with st.chat_message("assistant"):
            with st.spinner("Smart search…"):
                result = smart_search(project_path, prompt)
            answer = (
                f"{result.summary}\n\n"
                + ("**Symbols**\n" + "\n".join(f"- `{s}`" for s in result.symbols) + "\n\n" if result.symbols else "")
                + ("**Hits**\n```\n" + "\n".join(result.hits[:30]) + "\n```" if result.hits else "_No content hits._")
            )
            st.markdown(answer)
            ActivityStore(project_path).add("search", prompt)
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer,
                "sources": [],
                "tool_trace": ["smart_search"],
            }
        )
        if session_store:
            persist_messages_to_session(session_store)
        return

    # Auto-search the project for "Search for X" (no Tools toggle required)
    if wants_code_search(prompt) and not wants_project_explanation(prompt):
        if not search_root:
            with st.chat_message("assistant"):
                st.error(
                    "Set a project folder path first (sidebar or Explain path box), "
                    "then search again."
                )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": "**Error:** No project folder set for search.",
                    "sources": [],
                    "tool_trace": [],
                }
            )
            if session_store:
                persist_messages_to_session(session_store)
            return
        try:
            query = extract_search_query(prompt)
            bundle = search_project(search_root, query)
            context = ((context + "\n\n") if context else "") + bundle.context
            sources = [{"path": p} for p in bundle.files_used]
            ActivityStore(search_root).add("search", query)
            st.info(
                f"Searched `{search_root}` for `{bundle.query}` — "
                f"{bundle.hit_count} hit line(s)"
            )
        except Exception as exc:
            with st.chat_message("assistant"):
                st.error(str(exc))
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"**Error:** {exc}",
                    "sources": [],
                    "tool_trace": [],
                }
            )
            if session_store:
                persist_messages_to_session(session_store)
            return

    # List / Read / Create against the project path (no Tools toggle required)
    elif wants_list_files(prompt) or wants_read_file(prompt) or wants_create_file(prompt):
        if not search_root:
            with st.chat_message("assistant"):
                st.error("Set/paste a project folder path first, then try again.")
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": "**Error:** No project folder set.",
                    "sources": [],
                    "tool_trace": [],
                }
            )
            if session_store:
                persist_messages_to_session(session_store)
            return
        try:
            if wants_list_files(prompt):
                action = handle_list(search_root)
            elif wants_create_file(prompt):
                action = handle_create_prepare(search_root, prompt)
                st.session_state.pending_create_path = (
                    extract_file_path(prompt) or "examples/hello.py"
                )
            else:
                action = handle_read(search_root, prompt)
            extra = action.context
            context = ((context + "\n\n") if context else "") + extra
            sources = [{"path": p} for p in (action.sources or [])]
            if action.effective_prompt:
                st.session_state._quick_effective_prompt = action.effective_prompt
            if action.info:
                st.info(action.info)
        except Exception as exc:
            with st.chat_message("assistant"):
                st.error(str(exc))
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"**Error:** {exc}",
                    "sources": [],
                    "tool_trace": [],
                }
            )
            if session_store:
                persist_messages_to_session(session_store)
            return

    # Auto-read the pasted path for explain prompts
    elif wants_project_explanation(prompt):
        if not explain_target:
            with st.chat_message("assistant"):
                st.error(
                    "Paste a local folder or file path in **Explain any local folder or file**, "
                    r"for example `G:\Projects\my-app` or `G:\Projects\my-app\main.py`."
                )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "**Error:** No path set. Paste any local folder/file path, then click Explain."
                    ),
                    "sources": [],
                    "tool_trace": [],
                }
            )
            if session_store:
                persist_messages_to_session(session_store)
            return
        try:
            target = explain_target
            force_folder = bool(st.session_state.pop("force_explain_folder", False))
            # "Explain this project/folder" must always use a directory
            prompt_l = prompt.lower()
            if force_folder or "project" in prompt_l or "folder" in prompt_l or "structure" in prompt_l:
                p = Path(target)
                if p.is_file():
                    target = str(p.parent)
                overview = build_project_overview(target)
            else:
                overview = build_path_context(target)
            extra = overview.context
            context = ((context + "\n\n") if context else "") + extra
            sources = [{"path": p} for p in overview.files_used]
            kind_label = "file" if overview.kind == "file" else "folder"
            st.info(
                f"Reading local {kind_label}: `{overview.project_path}` "
                f"({len(overview.files_used)} items in context)"
            )
            with st.expander("Context files loaded", expanded=True):
                for src in overview.files_used:
                    st.markdown(f"- `{src}`")
            _remember_path(overview.project_path)
            if project_path:
                ActivityStore(project_path).add("file", f"Explain {overview.project_path}")
        except FileNotFoundError as exc:
            with st.chat_message("assistant"):
                st.error(str(exc))
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"**Error:** {exc}",
                    "sources": [],
                    "tool_trace": [],
                }
            )
            if session_store:
                persist_messages_to_session(session_store)
            return

    elif use_rag and project_path:
        try:
            rag = get_rag_settings()
            retriever = ProjectRetriever(get_embedder(), top_k=rag["top_k"])
            if retriever.has_index(project_path):
                chunks = retriever.retrieve(project_path, prompt)
                rag_ctx = retriever.format_context(chunks)
                context = ((context + "\n\n") if context else "") + rag_ctx
                sources = [
                    {
                        "path": c.path,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                    }
                    for c in chunks
                ]
        except OllamaError as exc:
            with st.chat_message("assistant"):
                st.error(str(exc))
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"**Error:** {exc}",
                    "sources": [],
                    "tool_trace": [],
                }
            )
            if session_store:
                persist_messages_to_session(session_store)
            return

    effective_prompt = prompt
    quick_prompt = st.session_state.pop("_quick_effective_prompt", None)
    if quick_prompt:
        effective_prompt = quick_prompt
    elif wants_code_search(prompt) and context:
        effective_prompt = (
            "Using ONLY the SEARCH HITS provided, answer where the symbol/text appears.\n"
            "List matching file paths and briefly what each hit is.\n"
            "If there are no hits, say it was not found in the project.\n"
            "Do NOT say you lack project context — search results are already provided."
        )
    elif wants_project_explanation(prompt) and context:
        if overview_is_file_prompt(prompt):
            effective_prompt = (
                "Using ONLY the FILE CONTENTS provided, explain this code.\n"
                "Cover: purpose, important functions/classes, inputs/outputs, and how it fits a project.\n"
                "Cite the file path. Do NOT ask for more information."
            )
        else:
            effective_prompt = (
                "Using ONLY the PROJECT CONTEXT provided, explain the WHOLE project.\n"
                "Do NOT write an answer that only explains package.json.\n"
                "Required sections:\n"
                "1) Overview — what the app is (e.g. React portfolio)\n"
                "2) Folder structure — describe src/, pages/, components/, data/, configs\n"
                "3) Important source files — App.jsx, main.jsx, each page/component briefly\n"
                "4) Data & routing — how pages are connected\n"
                "5) How to run — npm scripts from package.json (short)\n"
                "Cite real paths. Keep package.json to a few bullets only."
            )

    # Optional custom system prompt from project settings is applied in build_messages

    auto_fs = (
        wants_list_files(prompt)
        or wants_read_file(prompt)
        or wants_create_file(prompt)
        or wants_code_search(prompt)
        or wants_project_explanation(prompt)
    )

    with st.chat_message("assistant"):
        if sources:
            with st.expander(
                "Files used",
                expanded=bool(wants_code_search(prompt) or wants_list_files(prompt) or wants_read_file(prompt)),
            ):
                for src in sources:
                    if "start_line" in src:
                        st.markdown(
                            f"- `{src['path']}` "
                            f"(lines {src['start_line']}-{src['end_line']})"
                        )
                    else:
                        st.markdown(f"- `{src['path']}`")

        placeholder = st.empty()
        tool_trace: list[str] = []
        new_pending_writes = False
        answer = ""

        try:
            run_tools = bool(
                use_tools
                and project_path
                and prompt_needs_tools(prompt)
                and not auto_fs
            )
            if use_tools and project_path and not run_tools and not auto_fs:
                st.caption(
                    "Fast chat mode (tools skipped for this prompt). "
                    "Ask to list/read/create a file to use tools."
                )

            if run_tools:
                st.caption(
                    "Running tools… Click **⏹ Stop generation** in the sidebar "
                    "or **Stop** (top-right) to cancel."
                )
                placeholder.markdown(
                    '<span class="loading-pulse">Running tools…</span>',
                    unsafe_allow_html=True,
                )
                agent = ToolAgent(client, FileSystemTools(project_path), max_steps=3)
                result = agent.run(
                    effective_prompt,
                    history=history,
                    context=context or None,
                )
                if result.error:
                    answer = f"**Error:** {result.error}"
                else:
                    answer = result.answer or "(No answer produced.)"
                tool_trace = result.tool_trace
                if result.pending_writes:
                    existing = st.session_state.get("proposed_edits") or []
                    for pw in result.pending_writes:
                        try:
                            edit = build_proposed_edit(
                                project_path,
                                pw.path,
                                pw.content,
                                note="tool agent proposal",
                            )
                            existing.append(edit.to_dict())
                        except Exception:
                            existing.append(
                                ProposedEdit(
                                    path=pw.path,
                                    new_content=pw.content,
                                    old_content=getattr(pw, "old_content", "") or "",
                                    is_new=pw.is_new,
                                    absolute_path=pw.absolute_path,
                                ).to_dict()
                            )
                    st.session_state.proposed_edits = existing
                    st.session_state.pending_writes = []
                    new_pending_writes = True
                    if project_path:
                        ActivityStore(project_path).add(
                            "edit",
                            f"Proposed {len(result.pending_writes)} write(s)",
                        )
                placeholder.markdown(answer)
                if tool_trace:
                    with st.expander("Tool calls", expanded=True):
                        for line in tool_trace:
                            st.code(line, language="text")
                if result.pending_writes:
                    st.info(
                        f"{len(result.pending_writes)} write(s) pending — "
                        "approve or reject in the panel above."
                    )
            else:
                if use_tools and not project_path:
                    st.warning("Set a project folder to use filesystem tools.")
                st.caption(
                    "Generating… Click **⏹ Stop generation** in the sidebar "
                    "or **Stop** (top-right) to cancel."
                )
                messages = build_messages(
                    effective_prompt,
                    history=history,
                    context=context or None,
                    system_prompt=_effective_system_prompt(
                        project_path, project_settings
                    ),
                )
                use_stream = True
                if project_settings is not None:
                    use_stream = bool(project_settings.streaming)
                import time as _time

                t0 = _time.perf_counter()
                if use_stream:
                    collected: list[str] = []
                    stream = client.chat(messages, stream=True)
                    assert not isinstance(stream, str)
                    stopped = False
                    chunk_i = 0
                    for chunk in stream:
                        chunk_i += 1
                        # Periodically re-check CPU so a runaway load can abort mid-stream
                        if chunk_i == 1 or chunk_i % 24 == 0:
                            if not enforce_cpu_safety(during_generation=True):
                                stopped = True
                                break
                        if st.session_state.get("stop_generation"):
                            stopped = True
                            break
                        collected.append(chunk)
                        placeholder.markdown("".join(collected) + "▌")
                    answer = "".join(collected)
                    if stopped:
                        if st.session_state.get("cpu_safety_lock"):
                            answer = (
                                (answer + "\n\n") if answer else ""
                            ) + "_🛑 Generation stopped by CPU safety guard._"
                        else:
                            answer = (
                                (answer + "\n\n") if answer else ""
                            ) + "_⏹ Generation stopped by user._"
                        st.session_state.stop_generation = False
                    placeholder.markdown(answer)
                else:
                    raw = client.chat(messages, stream=False)
                    assert isinstance(raw, str)
                    answer = raw
                    placeholder.markdown(answer)
                elapsed_ms = (_time.perf_counter() - t0) * 1000
                if project_path:
                    MetricsStore(project_path).record_response(
                        effective_prompt, answer, elapsed_ms
                    )
                    console.add(
                        f"Chat response {elapsed_ms:.0f}ms",
                        source="chat",
                        detail=f"~tokens in/out est.",
                    )

            # For create-file prompts, turn the generated code into an Approve write
            if wants_create_file(prompt) and search_root and answer and not answer.startswith("**Error:**"):
                rel = st.session_state.pop(
                    "pending_create_path",
                    extract_file_path(prompt) or "examples/hello.py",
                )
                pending = propose_write_from_answer(search_root, rel, answer)
                if pending is not None:
                    try:
                        edit = build_proposed_edit(
                            search_root,
                            pending.path,
                            pending.content,
                            note="create file proposal",
                        )
                        existing = st.session_state.get("proposed_edits") or []
                        existing.append(edit.to_dict())
                        st.session_state.proposed_edits = existing
                    except Exception:
                        existing = st.session_state.get("pending_writes") or []
                        existing.append(pending)
                        st.session_state.pending_writes = existing
                    new_pending_writes = True
                    if project_path:
                        ActivityStore(project_path).add("edit", f"Proposed create {pending.path}")
                    st.info(
                        f"Proposed file `{pending.path}` — review Diff (Accept/Reject) above."
                    )
        except OllamaError as exc:
            answer = f"**Error:** {exc}"
            placeholder.markdown(answer)
        except Exception as exc:
            answer = f"**Error:** {exc}"
            placeholder.markdown(answer)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "tool_trace": tool_trace,
        }
    )
    if session_store:
        persist_messages_to_session(session_store)
    if new_pending_writes:
        st.rerun()


def _remember_path(path: str) -> None:
    """Keep a short recent-path list for quick switching."""
    path = (path or "").strip()
    if not path:
        return
    recent: list[str] = st.session_state.get("recent_explain_paths", [])
    recent = [p for p in recent if p != path]
    recent.insert(0, path)
    st.session_state.recent_explain_paths = recent[:8]


def _effective_system_prompt(
    project_path: str | None,
    project_settings: ProjectSettings | None,
) -> str:
    """Merge persona + project `.rules` + optional system prompt override."""
    persona_id = (
        (project_settings.persona_id if project_settings else None)
        or st.session_state.get("persona_id")
        or "default"
    )
    rules_text = ""
    if project_path:
        try:
            rules_text = load_project_rules(project_path).text
        except Exception:
            rules_text = ""
    prompt = persona_system_prompt(persona_id, rules_text)
    if project_settings and project_settings.system_prompt.strip():
        # Keep persona/rules, append user override as extra guidance
        override = project_settings.system_prompt.strip()
        if override not in prompt:
            prompt = f"{prompt}\n\nUSER SYSTEM OVERRIDE:\n{override}"
    return prompt


def main() -> None:
    init_page()
    settings = get_ollama_settings()
    probe = OllamaClient(base_url=settings["base_url"], model=settings["model"])
    (
        selected_model,
        project_path,
        use_rag,
        use_tools,
        num_thread,
        temperature,
        session_store,
        project_settings,
    ) = sidebar(probe, default_model=settings["model"])
    client = get_client(
        selected_model,
        num_thread=num_thread,
        temperature=temperature,
        top_p=getattr(project_settings, "top_p", 0.9),
        num_ctx=getattr(project_settings, "context_size", 4096),
    )
    render_chat(
        client,
        project_path,
        use_rag,
        use_tools,
        session_store=session_store,
        project_settings=project_settings,
    )


if __name__ == "__main__":
    main()
