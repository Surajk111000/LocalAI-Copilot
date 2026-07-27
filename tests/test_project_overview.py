"""Tests for project overview builder."""

from pathlib import Path

from src.project_overview import build_project_overview, wants_project_explanation


def test_wants_project_explanation() -> None:
    assert wants_project_explanation("Explain this project")
    assert wants_project_explanation("what is this project about?")
    assert not wants_project_explanation("Write a hello world function")


def test_build_overview_reads_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo App\nA test project.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    overview = build_project_overview(tmp_path)
    assert "Demo App" in overview.context
    assert "README.md" in overview.files_used
    assert "FOLDER STRUCTURE:" in overview.context


def test_build_path_context_file(tmp_path: Path) -> None:
    from src.project_overview import build_path_context

    file_path = tmp_path / "util.py"
    file_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    overview = build_path_context(file_path)
    assert overview.kind == "file"
    assert "def add" in overview.context
