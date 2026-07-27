"""Agent toolbox: symbols, rename, review, tests, docs, commit, inline AI, selection."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.assistants.coding import (
    commit_message,
    generate_docs,
    generate_tests,
    inline_generate,
    review_file,
    review_project,
    review_text,
    run_selection_action,
    suggest_refactor,
)
from src.llm.ollama_client import OllamaClient
from src.symbols.index import find_symbols
from src.symbols.rename import rename_symbol


def render_agent_toolbox(project_path: str | None, client: OllamaClient) -> None:
    st.markdown("#### Agent toolbox")
    if not project_path:
        st.caption("Open a project to use agent tools.")
        return

    tab_search, tab_symbols, tab_inline, tab_review, tab_gen, tab_commit = st.tabs(
        ["Smart search", "Symbols", "Inline AI", "Review", "Generate", "Commit"]
    )

    with tab_search:
        st.caption('Ask: "Where is login?" or "Where database connection?"')
        q = st.text_input("Smart search", key="smart_search_q", placeholder="Where is login?")
        if st.button("Search", key="smart_search_btn") and q.strip():
            from src.search.smart_search import smart_search

            with st.spinner("Searching…"):
                result = smart_search(project_path, q)
            st.info(result.summary)
            if result.symbols:
                st.markdown("**Symbols**")
                for line in result.symbols:
                    st.code(line, language="text")
            if result.hits:
                st.markdown("**Content hits**")
                st.code("\n".join(result.hits[:40]), language="text")
            else:
                st.caption("No content hits.")

    with tab_symbols:
        kind = st.selectbox(
            "Kind",
            ["all", "function", "class", "variable", "import"],
            key="sym_kind",
        )
        query = st.text_input("Filter symbol name", key="sym_query")
        if st.button("Find symbols", key="sym_find"):
            hits = find_symbols(
                project_path,
                kind=None if kind == "all" else kind,
                query=query,
                limit=80,
            )
            if not hits:
                st.caption("No symbols found.")
            for hit in hits:
                st.markdown(f"`{hit.kind}` **{hit.name}** — `{hit.path}:{hit.line}`")
                st.caption(hit.text)

        st.markdown("---")
        st.markdown("**Rename symbol (proposes edits only)**")
        old = st.text_input("Old name", key="rename_old")
        new = st.text_input("New name", key="rename_new")
        if st.button("Propose rename", key="rename_btn"):
            try:
                with st.spinner("Scanning project…"):
                    edits = rename_symbol(project_path, old, new)
                if not edits:
                    st.warning("No matches found.")
                else:
                    st.session_state.proposed_edits = [e.to_dict() for e in edits]
                    st.session_state.proposed_edits_note = f"rename {old} → {new}"
                    st.success(f"Proposed changes in {len(edits)} file(s). Review diffs.")
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    with tab_inline:
        st.caption("Cursor-style inline AI (Streamlit stand-in for Ctrl+K)")
        instruction = st.text_input(
            "Instruction",
            key="inline_instruction",
            placeholder="Generate a FastAPI /health endpoint",
        )
        selected = st.text_area(
            "Selected code (optional)",
            key="inline_selected",
            height=120,
            placeholder="Paste highlighted code here",
        )
        if st.button("Generate (Inline AI)", key="inline_run", type="primary"):
            with st.spinner("Generating…"):
                result = inline_generate(client, instruction, selected)
            st.session_state.last_assistant_result = {
                "title": result.title,
                "content": result.content,
            }
            st.markdown(result.content)

        st.markdown("---")
        st.markdown("**Selection actions** (Explain / Optimize / Refactor / Tests)")
        action = st.selectbox(
            "Action",
            ["explain", "optimize", "refactor", "generate_tests"],
            key="sel_action",
        )
        sel_code = st.text_area("Code selection", key="sel_code", height=140)
        sel_path = st.text_input(
            "Source path (for test generation)",
            key="sel_path",
            placeholder="src/auth.py",
        )
        if st.button("Run selection action", key="sel_run"):
            with st.spinner("Working…"):
                result = run_selection_action(
                    client,
                    action,
                    sel_code,
                    project_path=project_path,
                    target_path=sel_path or None,
                )
            st.markdown(result.content)
            if result.proposed_edits:
                st.session_state.proposed_edits = [e.to_dict() for e in result.proposed_edits]
                st.session_state.proposed_edits_note = result.title
                st.info("Proposed file edit ready — review in Diff viewer.")
                st.rerun()

    with tab_review:
        scope = st.radio(
            "Review scope",
            ["Current file", "Selected code", "Whole project"],
            key="review_scope",
            horizontal=True,
        )
        file_path = st.text_input("File path", key="review_file", placeholder="src/main.py")
        selected = st.text_area("Selected code", key="review_selected", height=100)
        if st.button("Run review", key="review_run", type="primary"):
            with st.spinner("Reviewing…"):
                if scope == "Whole project":
                    result = review_project(client, project_path)
                elif scope == "Current file":
                    result = review_file(client, project_path, file_path)
                else:
                    result = review_text(client, selected, scope="selection")
            st.markdown(result.content)
            if st.button("Also suggest refactor (no writes)", key="review_refactor"):
                ref = suggest_refactor(client, selected or result.content[:8000])
                st.markdown(ref.content)

    with tab_gen:
        st.markdown("**Test generator**")
        src = st.text_input("Source file", key="gen_test_src", placeholder="src/auth.py")
        if st.button("Generate pytest file", key="gen_tests"):
            with st.spinner("Generating tests…"):
                result = generate_tests(client, project_path, src)
            st.markdown(result.content)
            if result.proposed_edits:
                st.session_state.proposed_edits = [e.to_dict() for e in result.proposed_edits]
                st.session_state.proposed_edits_note = result.title
                st.info("Proposed test file — accept via Diff viewer.")
                st.rerun()

        st.markdown("---")
        st.markdown("**Documentation generator**")
        doc_kind = st.selectbox("Doc type", ["readme", "api", "docstrings"], key="doc_kind")
        doc_file = st.text_input("File (for docstrings)", key="doc_file", placeholder="src/api.py")
        if st.button("Generate docs", key="gen_docs"):
            with st.spinner("Generating docs…"):
                result = generate_docs(
                    client,
                    project_path,
                    doc_kind,
                    file_path=doc_file or None,
                )
            st.markdown(result.content)
            if result.proposed_edits:
                st.session_state.proposed_edits = [e.to_dict() for e in result.proposed_edits]
                st.session_state.proposed_edits_note = result.title
                st.info("Proposed documentation edit — accept via Diff viewer.")
                st.rerun()

    with tab_commit:
        notes = st.text_area("Optional notes for commit message", key="commit_notes", height=80)
        if st.button("Generate commit message", key="commit_btn", type="primary"):
            with st.spinner("Summarizing accepted changes…"):
                result = commit_message(client, project_path, extra_summary=notes)
            st.markdown(result.content)
            st.session_state.last_commit_message = result.content
