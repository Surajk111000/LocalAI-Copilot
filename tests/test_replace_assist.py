"""Tests for Cursor-style text replace assist."""

from pathlib import Path

from src.editing.replace_assist import (
    extract_replace_pair,
    propose_text_replacements,
    wants_text_replace,
)
from src.quick_actions import wants_code_edit


def test_extract_replace_messy_title_prompt() -> None:
    prompt = (
        r"G:\Projects\suraj-portfolio in the project please the tittle "
        r"of website from suraj kumar to akash"
    )
    assert wants_text_replace(prompt)
    assert wants_code_edit(prompt)
    pair = extract_replace_pair(prompt)
    assert pair is not None
    assert pair[0].lower() == "suraj kumar"
    assert pair[1].lower() == "akash"


def test_propose_replace(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<title>Suraj Kumar | Portfolio</title>\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text(
        "export const name = 'Suraj Kumar';\n", encoding="utf-8"
    )
    plan = propose_text_replacements(tmp_path, "Suraj Kumar", "Akash")
    assert len(plan.edits) >= 2
    joined = "\n".join(e.new_content for e in plan.edits)
    assert "Akash" in joined
    assert "Suraj Kumar" not in joined
