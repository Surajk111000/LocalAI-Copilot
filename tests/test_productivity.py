"""Tests for productivity features."""

from __future__ import annotations

from pathlib import Path

from src.plugins.api import PluginRegistry, example_echo_plugin, registry
from src.productivity.error_assistant import parse_traceback
from src.productivity.export import export_json, export_markdown, write_export
from src.productivity.personas import get_persona, persona_system_prompt
from src.productivity.prompts import PromptLibrary
from src.productivity.rules import ensure_sample_rules, load_project_rules
from src.productivity.todo_scanner import scan_todos, summarize_todos
from src.tools.git_tools import GitTools


def test_prompt_library_builtin_and_custom(tmp_path: Path, monkeypatch) -> None:
    from src.productivity import prompts as prompts_mod
    from src.workspace import paths as paths_mod

    monkeypatch.setattr(paths_mod, "project_dir", lambda _p: tmp_path / "proj")
    monkeypatch.setattr(prompts_mod, "project_dir", lambda _p: tmp_path / "proj")
    lib = PromptLibrary(tmp_path)
    assert len(lib.list_all()) >= 5
    item = lib.add_custom("My tip", "Do the thing", "Custom")
    assert any(p.id == item.id for p in lib.list_custom())
    hits = lib.search("security")
    assert hits


def test_personas_and_rules(tmp_path: Path) -> None:
    assert get_persona("security").name == "Security"
    ensure_sample_rules(tmp_path)
    rules = load_project_rules(tmp_path)
    assert not rules.empty
    prompt = persona_system_prompt("backend", rules.text)
    assert "PROJECT RULES" in prompt
    assert "backend" in prompt.lower() or "Backend" in get_persona("backend").name


def test_todo_scanner(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("# TODO: wire auth\n# FIXME: race\n", encoding="utf-8")
    hits = scan_todos(tmp_path)
    assert any(h.kind == "TODO" for h in hits)
    summary = summarize_todos(hits)
    assert summary.get("TODO", 0) >= 1


def test_parse_traceback_and_export(tmp_path: Path) -> None:
    tb = '''Traceback (most recent call last):\n  File "src/app.py", line 10, in main\n    boom()\nValueError: nope\n'''
    frames = parse_traceback(tb)
    assert frames and frames[0].line == 10
    md = export_markdown([{"role": "user", "content": "hi"}])
    assert "# " in md
    js = export_json([{"role": "assistant", "content": "yo"}])
    assert "messages" in js
    path = write_export(tmp_path, [{"role": "user", "content": "x"}], "markdown")
    assert path.exists()


def test_plugin_registry() -> None:
    reg = PluginRegistry()
    reg.register("ping", lambda a: {"ok": True, "pong": a.get("x")}, description="ping")
    assert reg.call("ping", {"x": 1})["pong"] == 1
    example_echo_plugin()
    assert registry.call("echo", {"text": "hi"})["echo"] == "hi"


def test_git_commit_requires_approval(tmp_path: Path) -> None:
    tools = GitTools(tmp_path)
    result = tools.commit("msg", approved=False)
    assert result.needs_approval
