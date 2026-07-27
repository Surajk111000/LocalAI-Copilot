"""Tests for agent editing workflow, symbols, smart search, versions."""

from __future__ import annotations

from pathlib import Path

from src.agent.mode import CopilotMode, is_agent_mode
from src.editing.apply import apply_edit, build_proposed_edit
from src.editing.diff import change_stats, unified_diff
from src.editing.versions import VersionStore
from src.search.smart_search import detect_intent, smart_search, wants_smart_where
from src.symbols.index import find_symbols
from src.symbols.rename import rename_symbol


def test_mode_helpers() -> None:
    assert is_agent_mode(CopilotMode.AGENT)
    assert is_agent_mode("agent")
    assert not is_agent_mode("chat")


def test_diff_and_stats() -> None:
    old = "a\nb\nc\n"
    new = "a\nB\nc\n"
    diff = unified_diff(old, new, "x.py")
    assert "b" in diff or "-b" in diff or "B" in diff
    stats = change_stats(old, new)
    assert stats["added"] >= 1
    assert stats["removed"] >= 1


def test_proposed_edit_apply_and_undo(tmp_path: Path, monkeypatch) -> None:
    from src.editing import versions as versions_mod
    from src.workspace import paths as paths_mod

    monkeypatch.setattr(paths_mod, "versions_dir", lambda _p: tmp_path / "versions")
    monkeypatch.setattr(paths_mod, "versions_index_path", lambda _p: tmp_path / "versions" / "index.json")
    monkeypatch.setattr(versions_mod, "versions_dir", lambda _p: tmp_path / "versions")
    monkeypatch.setattr(versions_mod, "versions_index_path", lambda _p: tmp_path / "versions" / "index.json")

    src = tmp_path / "app.py"
    src.write_text("x = 1\n", encoding="utf-8")
    edit = build_proposed_edit(tmp_path, "app.py", "x = 2\n", note="bump")
    assert edit.old_content == "x = 1\n"
    assert not edit.is_new

    ok, msg = apply_edit(tmp_path, edit, note="bump")
    assert ok, msg
    assert src.read_text(encoding="utf-8") == "x = 2\n"

    store = VersionStore(tmp_path)
    recent = store.list_recent(1)
    assert recent
    ok, msg = store.undo_version(recent[0]["id"])
    assert ok, msg
    assert src.read_text(encoding="utf-8") == "x = 1\n"


def test_new_file_edit_and_undo(tmp_path: Path, monkeypatch) -> None:
    from src.editing import versions as versions_mod
    from src.workspace import paths as paths_mod

    monkeypatch.setattr(paths_mod, "versions_dir", lambda _p: tmp_path / "versions")
    monkeypatch.setattr(paths_mod, "versions_index_path", lambda _p: tmp_path / "versions" / "index.json")
    monkeypatch.setattr(versions_mod, "versions_dir", lambda _p: tmp_path / "versions")
    monkeypatch.setattr(versions_mod, "versions_index_path", lambda _p: tmp_path / "versions" / "index.json")

    edit = build_proposed_edit(tmp_path, "hello.py", "print('hi')\n", note="create")
    assert edit.is_new
    ok, _ = apply_edit(tmp_path, edit)
    assert ok
    assert (tmp_path / "hello.py").exists()
    store = VersionStore(tmp_path)
    ok, _ = store.undo_latest()
    assert ok
    assert not (tmp_path / "hello.py").exists()


def test_find_symbols(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "class Auth:\n    pass\n\ndef login(user):\n    return True\n\nVALUE = 1\n",
        encoding="utf-8",
    )
    hits = find_symbols(tmp_path, kind="function", query="login")
    assert any(h.name == "login" for h in hits)
    classes = find_symbols(tmp_path, kind="class")
    assert any(h.name == "Auth" for h in classes)


def test_rename_symbol_proposes_only(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def login():\n    return login\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import login\n", encoding="utf-8")
    edits = rename_symbol(tmp_path, "login", "sign_in")
    assert len(edits) >= 1
    # Disk unchanged until apply
    assert "def login" in (tmp_path / "a.py").read_text(encoding="utf-8")
    assert all("sign_in" in e.new_content for e in edits)


def test_smart_search(tmp_path: Path) -> None:
    (tmp_path / "auth.py").write_text("def login():\n    pass\n", encoding="utf-8")
    intent, kws = detect_intent("Where is login?")
    assert intent in {"login", "auth", "general"}
    assert wants_smart_where("Where is login?")
    result = smart_search(tmp_path, "Where is login?")
    assert result.hits or result.symbols
