"""Tests for LangGraph multi-agent pipeline and gated tools."""

from __future__ import annotations

from pathlib import Path

from src.multi_agent.graph import MultiAgentRunner, build_coding_graph
from src.multi_agent.memory import ConversationManager
from src.multi_agent.tools_registry import ToolRegistry
from src.tools.git_tools import GitTools
from src.tools.terminal_tools import TerminalTools


class FakeOllama:
    """Deterministic stand-in for OllamaClient.chat."""

    def chat(self, messages, stream=False):  # noqa: ANN001
        system = messages[0]["content"]
        if "PLANNER" in system:
            return (
                '{"summary":"Add hello module","tasks":["research","code","test"],'
                '"files_to_modify":[],"files_to_create":["hello_ma.py"],"notes":"ok"}'
            )
        if "RESEARCH" in system:
            return '{"notes":"no existing hello","keywords":["hello"],"doc_paths":["README.md"]}'
        if "ANALYZER" in system or "CODEBASE ANALYZER" in system:
            return (
                '{"analysis":"create hello_ma.py","relevant_files":["hello_ma.py"],'
                '"touch_points":[],"risks":[]}'
            )
        if "CODER" in system:
            return (
                '{"notes":"new file","edits":[{"path":"hello_ma.py","action":"create",'
                '"content":"def hello():\\n    return \\"hi\\"\\n"}]}'
            )
        if "REVIEWER" in system:
            return (
                '{"report":"Looks fine","issues":[],"severity":"low","approve_for_tests":true}'
            )
        if "TESTER" in system:
            return (
                '{"notes":"basic test","tests":[{"path":"tests/test_hello_ma.py",'
                '"content":"from hello_ma import hello\\n\\ndef test_hello():\\n    assert hello() == \\"hi\\"\\n"}]}'
            )
        if "DOCUMENTATION" in system:
            return '{"needed":false,"notes":"skip","docs":[]}'
        if "FINAL RESPONSE" in system:
            return "Proposed hello_ma.py and tests. Accept diffs to apply."
        return "{}"


def test_git_destructive_requires_approval(tmp_path: Path) -> None:
    tools = GitTools(tmp_path)
    result = tools.run(["reset", "--hard"], approved=False)
    assert result.needs_approval
    assert not result.ok


def test_terminal_blocks_rm_rf(tmp_path: Path) -> None:
    tools = TerminalTools(tmp_path)
    result = tools.run("rm -rf /", approved=True)
    assert result.needs_approval or not result.ok


def test_terminal_allowlist_pytest(tmp_path: Path) -> None:
    tools = TerminalTools(tmp_path)
    # May fail if pytest finds nothing, but should attempt without approval gate
    result = tools.run("pytest -q --tb=no", approved=False)
    assert result.needs_approval is False


def test_conversation_memory(tmp_path: Path, monkeypatch) -> None:
    from src.multi_agent import memory as mem_mod
    from src.workspace import paths as paths_mod

    monkeypatch.setattr(paths_mod, "project_dir", lambda _p: tmp_path / "proj")
    monkeypatch.setattr(mem_mod, "project_dir", lambda _p: tmp_path / "proj")
    mgr = ConversationManager(tmp_path)
    mgr.add("user", "Add feature", agent="user", thread_id="abc")
    mgr.add("assistant", "Planned", agent="planner", thread_id="abc")
    loaded = mgr.load()
    assert len(loaded.turns) == 2
    assert "CONVERSATION MEMORY" in mgr.context_block()


def test_langgraph_interrupt_then_continue(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    client = FakeOllama()
    runner = MultiAgentRunner(client, str(tmp_path), embedder=None)  # type: ignore[arg-type]

    snap = runner.start("Add a hello helper")
    assert snap.get("interrupted") is True
    assert snap.get("plan_summary")
    assert "Planning" in {e.get("phase") for e in (snap.get("execution_log") or [])}

    # Disk untouched after planner
    assert not (tmp_path / "hello_ma.py").exists()

    snap2 = runner.approve_and_continue(snap["thread_id"])
    assert snap2.get("interrupted") in (False, None) or snap2.get("next") == []
    assert snap2.get("final_response")
    assert snap2.get("proposed_edits")
    # Still not written — proposals only
    assert not (tmp_path / "hello_ma.py").exists()


def test_build_graph_nodes() -> None:
    client = FakeOllama()
    tools = ToolRegistry(str(Path.cwd()), embedder=None)
    graph = build_coding_graph(client, tools)  # type: ignore[arg-type]
    assert graph is not None
