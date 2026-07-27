"""Productivity hub: prompts, personas, TODOs, errors, git, terminal, export, logs."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.assistants.coding import commit_message
from src.llm.ollama_client import OllamaClient
from src.perf.runtime import get_index_job, start_background_indexing
from src.plugins.api import example_echo_plugin, registry
from src.productivity.devlog import console
from src.productivity.error_assistant import assist_error
from src.productivity.export import write_export
from src.productivity.personas import list_personas
from src.productivity.prompts import PromptLibrary
from src.productivity.rules import ensure_sample_rules, load_project_rules
from src.productivity.todo_scanner import scan_todos, summarize_todos
from src.tools.git_tools import GitTools
from src.tools.terminal_tools import TerminalTools


def render_productivity_hub(project_path: str | None, client: OllamaClient) -> None:
    st.markdown("#### Productivity")
    if not project_path:
        st.caption("Open a project to use productivity tools.")
        return

    tabs = st.tabs(
        [
            "Prompts",
            "Persona",
            "Rules",
            "Git",
            "Terminal",
            "TODOs",
            "Errors",
            "Export",
            "Plugins",
            "Logs",
            "Shortcuts",
        ]
    )

    with tabs[0]:
        _prompts_tab(project_path)
    with tabs[1]:
        _persona_tab()
    with tabs[2]:
        _rules_tab(project_path)
    with tabs[3]:
        _git_tab(project_path, client)
    with tabs[4]:
        _terminal_tab(project_path, client)
    with tabs[5]:
        _todos_tab(project_path)
    with tabs[6]:
        _errors_tab(project_path, client)
    with tabs[7]:
        _export_tab(project_path)
    with tabs[8]:
        _plugins_tab()
    with tabs[9]:
        _logs_tab()
    with tabs[10]:
        _shortcuts_tab()


def _prompts_tab(project_path: str) -> None:
    lib = PromptLibrary(project_path)
    q = st.text_input("Search prompts", key="prompt_lib_search")
    items = lib.search(q)
    for item in items:
        cols = st.columns([4, 1])
        cols[0].markdown(f"**{item.title}** `{item.category}`")
        cols[0].caption(item.prompt[:160])
        if cols[1].button("Use", key=f"use_prompt_{item.id}"):
            st.session_state.pending_prompt = item.prompt
            console.add(f"Prompt used: {item.title}", source="prompt_library")
            st.rerun()
    st.markdown("---")
    st.markdown("**Add custom prompt**")
    title = st.text_input("Title", key="custom_prompt_title")
    body = st.text_area("Prompt text", key="custom_prompt_body", height=80)
    if st.button("Save prompt", key="save_custom_prompt"):
        lib.add_custom(title, body)
        st.success("Saved.")
        st.rerun()


def _persona_tab() -> None:
    personas = list_personas()
    options = {p.id: f"{p.name} — {p.description}" for p in personas}
    current = st.session_state.get("persona_id", "default")
    choice = st.selectbox(
        "Active persona",
        options=list(options.keys()),
        format_func=lambda k: options[k],
        index=list(options.keys()).index(current) if current in options else 0,
        key="persona_select",
    )
    st.session_state.persona_id = choice
    persona = next(p for p in personas if p.id == choice)
    st.code(persona.system_prompt, language="text")


def _rules_tab(project_path: str) -> None:
    rules = load_project_rules(project_path)
    if rules.empty:
        st.caption("No `.rules/` found yet.")
        if st.button("Create sample .rules/README.md", key="create_rules"):
            path = ensure_sample_rules(project_path)
            st.success(f"Created {path}")
            st.rerun()
    else:
        st.success(f"Loaded {len(rules.files)} rule file(s)")
        for f in rules.files:
            st.markdown(f"- `{f}`")
        with st.expander("Rules text injected into AI context", expanded=False):
            st.markdown(rules.text)


def _git_tab(project_path: str, client: OllamaClient) -> None:
    git = GitTools(project_path)
    c1, c2, c3 = st.columns(3)
    if c1.button("Status", key="git_status"):
        r = git.status()
        st.session_state.git_output = r.output
        console.add("git status", source="git", detail=r.output[:500])
    if c2.button("Diff", key="git_diff"):
        r = git.diff_full()
        st.session_state.git_output = r.output
        console.add("git diff", source="git", detail=r.output[:500])
    if c3.button("Branch", key="git_branch"):
        r = git.branch()
        st.session_state.git_output = r.output

    if st.button("Generate commit message", key="git_gen_msg"):
        with st.spinner("Summarizing…"):
            result = commit_message(client, project_path)
        st.session_state.pending_commit_message = result.content
        st.markdown(result.content)

    msg = st.text_area(
        "Commit message",
        value=st.session_state.get("pending_commit_message", ""),
        key="git_commit_msg",
        height=100,
    )
    a1, a2, a3, a4 = st.columns(4)
    if a1.button("Stage all", key="git_add"):
        r = git.add(["."], approved=True)
        st.session_state.git_output = r.output
        console.add("git add .", source="git", detail=r.output[:300])
    if a2.button("Commit (approve)", key="git_commit"):
        r = git.commit(msg, approved=True)
        st.session_state.git_output = r.output
        console.add("git commit", source="git", detail=r.output[:300], level="warn")
    if a3.button("Pull (approve)", key="git_pull"):
        r = git.pull(approved=True)
        st.session_state.git_output = r.output
        console.add("git pull", source="git", detail=r.output[:300], level="warn")
    if a4.button("Push (approve)", key="git_push"):
        r = git.push(approved=True)
        st.session_state.git_output = r.output
        console.add("git push", source="git", detail=r.output[:300], level="warn")

    if st.session_state.get("git_output"):
        st.code(st.session_state.git_output, language="text")


def _terminal_tab(project_path: str, client: OllamaClient) -> None:
    st.caption("Terminal assistant — generate commands, run only after approval.")
    goal = st.text_input(
        "What do you want to run?",
        key="term_goal",
        placeholder="Run pytest for the auth module",
    )
    if st.button("Generate command", key="term_gen"):
        with st.spinner("Generating…"):
            raw = client.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You generate ONE safe shell command for a developer laptop. "
                            "Return ONLY the command, no markdown."
                        ),
                    },
                    {"role": "user", "content": goal},
                ],
                stream=False,
            )
        assert isinstance(raw, str)
        cmd = raw.strip().strip("`").splitlines()[0]
        st.session_state.pending_terminal_cmd = cmd
    cmd = st.text_input(
        "Command",
        value=st.session_state.get("pending_terminal_cmd", ""),
        key="term_cmd",
    )
    if st.button("Approve & run", type="primary", key="term_run"):
        tools = TerminalTools(project_path)
        result = tools.run(cmd, approved=True)
        st.session_state.terminal_output = result.output
        console.add(
            f"terminal: {cmd}",
            source="terminal",
            detail=result.output[:500],
            level="info" if result.ok else "error",
        )
    if st.session_state.get("terminal_output"):
        st.code(st.session_state.terminal_output, language="text")


def _todos_tab(project_path: str) -> None:
    if st.button("Scan TODO/FIXME/BUG/HACK", key="todo_scan"):
        hits = scan_todos(project_path)
        st.session_state.todo_hits = [
            {"kind": h.kind, "path": h.path, "line": h.line, "text": h.text} for h in hits
        ]
        st.session_state.todo_summary = summarize_todos(hits)
    summary = st.session_state.get("todo_summary") or {}
    if summary:
        st.write(summary)
    for hit in st.session_state.get("todo_hits") or []:
        st.markdown(f"`{hit['kind']}` `{hit['path']}:{hit['line']}` — {hit['text']}")


def _errors_tab(project_path: str, client: OllamaClient) -> None:
    tb = st.text_area("Paste traceback", key="error_tb", height=160)
    if st.button("Analyze error", type="primary", key="error_analyze"):
        with st.spinner("Locating source + suggesting fix…"):
            result = assist_error(project_path, tb, client)
        st.session_state.error_assist = {
            "files": result.local_files,
            "suggestion": result.suggestion,
            "snippets": result.snippets,
        }
        console.add("Error assistant ran", source="error_assistant")
    data = st.session_state.get("error_assist")
    if data:
        st.markdown("**Located files**")
        for f in data.get("files") or []:
            st.markdown(f"- `{f}`")
        for key, snippet in (data.get("snippets") or {}).items():
            with st.expander(key):
                st.code(snippet, language="text")
        st.markdown(data.get("suggestion") or "")


def _export_tab(project_path: str) -> None:
    fmt = st.selectbox("Format", ["markdown", "json", "html", "pdf"], key="export_fmt")
    st.caption("PDF exports as print-ready HTML (browser: Print → Save as PDF).")
    if st.button("Export current chat", key="export_chat"):
        messages = st.session_state.get("messages") or []
        path = write_export(project_path, messages, fmt, title="Local AI Coding Copilot")
        st.success(f"Wrote `{path}`")
        console.add(f"Exported chat → {path}", source="export")


def _plugins_tab() -> None:
    if st.button("Load demo echo plugin", key="load_echo_plugin"):
        example_echo_plugin()
        st.success("Registered `echo` tool.")
    tools = registry.list_tools()
    if not tools:
        st.caption("No plugins registered yet.")
    for tool in tools:
        st.markdown(f"- `{tool.name}` ({tool.plugin}) — {tool.description}")
    text = st.text_input("Echo text", key="plugin_echo_text")
    if st.button("Call echo", key="plugin_echo_call"):
        result = registry.call("echo", {"text": text})
        st.json(result)


def _logs_tab() -> None:
    if st.button("Clear logs", key="clear_devlog"):
        console.clear()
    for event in reversed(console.list(80)):
        st.markdown(
            f"`{event['level']}` **{event['source']}** — {event['message']}"
        )
        if event.get("detail"):
            st.caption(str(event["detail"])[:300])


def _shortcuts_tab() -> None:
    st.markdown(
        """
**Keyboard shortcuts (Streamlit mappings)**

| Shortcut | Action in this app |
|----------|--------------------|
| **Ctrl+K** | Open Productivity → focus Inline / command style flows (Agent toolbox Inline AI) |
| **Ctrl+L** | Focus chat input (browser / Streamlit chat) |
| **Ctrl+Shift+P** | Open Productivity hub (this panel) / command palette stand-in |
| **Ctrl+Enter** | Send chat (Streamlit chat input) |

> True OS-level shortcuts are limited inside Streamlit. Use the Productivity tabs
> and Agent toolbox as the Cursor/Windsurf/Cline equivalents.
"""
    )


def render_dashboard(project_path: str | None) -> None:
    st.markdown("#### AI Dashboard")
    if not project_path:
        st.caption("Open a project to see stats.")
        return
    from src.productivity.metrics import MetricsStore

    stats = MetricsStore(project_path).snapshot()
    c1, c2, c3 = st.columns(3)
    c1.metric("Chats", stats["chat_count"])
    c2.metric("Responses", stats["response_count"])
    c3.metric("Avg response (ms)", stats["avg_response_ms"])
    c4, c5, c6 = st.columns(3)
    c4.metric("Prompt tokens ~", stats["prompt_tokens_est"])
    c5.metric("Completion tokens ~", stats["completion_tokens_est"])
    c6.metric("Indexed chunks", stats["indexed_chunks"])

    job = get_index_job(project_path)
    if job:
        st.caption(f"Background index: {job.status} — {job.message}")

    if st.button("Start background indexing", key="bg_index"):
        from src.config import get_rag_settings
        from src.rag.embeddings import OllamaEmbedder
        from src.rag.ingest import ProjectIndexer
        from src.config import get_ollama_settings

        settings = get_ollama_settings()
        rag = get_rag_settings()

        def factory():
            embedder = OllamaEmbedder(settings["base_url"], settings["embed_model"])
            return ProjectIndexer(
                embedder,
                chunk_size=rag["chunk_size"],
                overlap=rag["overlap"],
                batch_size=rag["batch_size"],
            )

        job = start_background_indexing(project_path, factory)
        console.add("Background indexing started", source="perf")
        st.info(f"Indexing status: {job.status}")
