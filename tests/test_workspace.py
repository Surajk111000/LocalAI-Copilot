"""Tests for multi-workspace core modules."""

from __future__ import annotations

from pathlib import Path

from src.context.manager import ContextManager, estimate_tokens
from src.explorer.actions import copy_path_text, delete_path, read_file, rename_path
from src.explorer.tree import build_tree, search_files
from src.sessions.store import SessionStore
from src.workspace.activity import ActivityStore
from src.workspace.manager import WorkspaceManager
from src.workspace.paths import project_id_for_path
from src.workspace.settings import ProjectSettings, SettingsStore


def test_project_id_stable(tmp_path: Path) -> None:
    a = project_id_for_path(tmp_path)
    b = project_id_for_path(tmp_path)
    assert a == b
    assert len(a) == 12


def test_workspace_open_switch_recent(tmp_path: Path) -> None:
    proj_a = tmp_path / "alpha"
    proj_b = tmp_path / "beta"
    proj_a.mkdir()
    proj_b.mkdir()
    state = tmp_path / "workspace_state.json"
    wm = WorkspaceManager(state_file=state)

    wm.open_project(proj_a)
    assert wm.active() == str(proj_a.resolve())
    wm.open_project(proj_b)
    assert wm.active() == str(proj_b.resolve())
    assert len(wm.list_open()) == 2

    wm.set_active(str(proj_a.resolve()))
    assert wm.active() == str(proj_a.resolve())

    recent = wm.list_recent()
    assert str(proj_a.resolve()) in [r.path for r in recent]
    assert str(proj_b.resolve()) in [r.path for r in recent]

    wm.close_project(str(proj_a.resolve()))
    assert len(wm.list_open()) == 1
    assert wm.active() == str(proj_b.resolve())


def test_settings_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.workspace.settings.settings_path",
        lambda _p: tmp_path / "settings.json",
    )
    monkeypatch.setattr(
        "src.workspace.paths.settings_path",
        lambda _p: tmp_path / "settings.json",
    )
    # SettingsStore imports settings_path from paths at call time via module
    from src.workspace import settings as settings_mod

    monkeypatch.setattr(
        settings_mod,
        "settings_path",
        lambda _p: tmp_path / "settings.json",
    )
    store = SettingsStore(tmp_path)
    store.save(
        ProjectSettings(
            preferred_model="qwen2.5-coder:3b",
            rag_enabled=True,
            cpu_threads=3,
            temperature=0.4,
            filesystem_enabled=True,
        )
    )
    loaded = store.load()
    assert loaded.rag_enabled is True
    assert loaded.cpu_threads == 3
    assert loaded.temperature == 0.4
    assert loaded.filesystem_enabled is True


def test_activity_store(tmp_path: Path, monkeypatch) -> None:
    from src.workspace import activity as activity_mod

    monkeypatch.setattr(
        activity_mod,
        "activity_path",
        lambda _p: tmp_path / "activity.json",
    )
    store = ActivityStore(tmp_path)
    store.add("prompt", "hello world")
    store.add("search", "OllamaClient")
    store.add("file", "Opened main.py", "main.py")
    items = store.list(limit=10)
    assert len(items) >= 3
    assert store.list(kind="search")[0].text == "OllamaClient"


def test_context_manager(tmp_path: Path, monkeypatch) -> None:
    from src.context import manager as ctx_mod

    monkeypatch.setattr(ctx_mod, "context_path", lambda _p: tmp_path / "context.json")
    (tmp_path / "hello.py").write_text("print('hi')\n" * 10, encoding="utf-8")
    ctx = ContextManager(tmp_path)
    entry = ctx.add("hello.py", pinned=True)
    assert entry is not None
    assert entry.pinned is True
    assert ctx.total_tokens() > 0
    block = ctx.build_context_block()
    assert "hello.py" in block
    ctx.remove("hello.py")
    assert ctx.list_files() == []


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_session_store(tmp_path: Path, monkeypatch) -> None:
    from src.sessions import store as store_mod

    monkeypatch.setattr(store_mod, "chats_dir", lambda _p: tmp_path / "chats")
    sessions = SessionStore(tmp_path)
    first = sessions.create("First")
    first.messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    sessions.save(first)

    second = sessions.create("Second")
    assert sessions.active_id() == second.id

    sessions.set_active(first.id)
    loaded = sessions.get(first.id)
    assert loaded is not None
    assert len(loaded.messages) == 2

    dup = sessions.duplicate(first.id)
    assert dup is not None
    assert dup.id != first.id
    assert len(dup.messages) == 2

    sessions.rename(first.id, "Renamed")
    assert sessions.get(first.id).title == "Renamed"

    hits = sessions.search("hello")
    assert any(s.id == first.id or s.id == dup.id for s in hits)

    sessions.delete(second.id)
    assert sessions.get(second.id) is None


def test_explorer_tree_and_actions(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "readme.md").write_text("# hi\n", encoding="utf-8")

    tree = build_tree(tmp_path)
    assert tree.is_dir
    hits = search_files(tmp_path, "app")
    assert "src/app.py" in hits or any(h.endswith("app.py") for h in hits)

    read = read_file(tmp_path, "src/app.py")
    assert read.ok
    assert "x = 1" in read.content

    renamed = rename_path(tmp_path, "src/app.py", "main.py")
    assert renamed.ok
    assert (tmp_path / "src" / "main.py").exists()

    copied = copy_path_text(tmp_path, "src/main.py", absolute=True)
    assert copied.ok
    assert "main.py" in copied.content

    deleted = delete_path(tmp_path, "src/main.py")
    assert deleted.ok
    assert not (tmp_path / "src" / "main.py").exists()
