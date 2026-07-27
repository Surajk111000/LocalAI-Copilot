"""Tests for automatic code search."""

from pathlib import Path

from src.code_search import extract_search_query, search_project, wants_code_search


def test_wants_and_extract() -> None:
    assert wants_code_search("Search for OllamaClient")
    assert extract_search_query("Search for OllamaClient") == "OllamaClient"
    assert extract_search_query("Where is login implemented?") == "login implemented"
    assert not wants_code_search("Explain this project")


def test_search_finds_symbol(tmp_path: Path) -> None:
    (tmp_path / "client.py").write_text(
        "class OllamaClient:\n    pass\n", encoding="utf-8"
    )
    bundle = search_project(tmp_path, "OllamaClient")
    assert bundle.hit_count >= 1
    assert "client.py" in bundle.context
    assert "OllamaClient" in bundle.context
