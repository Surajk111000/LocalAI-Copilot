"""Basic safety tests for filesystem tools (no Ollama required)."""

from pathlib import Path

import pytest

from src.agents.tool_agent import ToolAgent
from src.tools.filesystem import FileSystemTools


def test_path_escape_blocked(tmp_path: Path) -> None:
    tools = FileSystemTools(tmp_path)
    with pytest.raises(PermissionError):
        tools.resolve("../outside.txt")


def test_list_and_read(tmp_path: Path) -> None:
    (tmp_path / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    tools = FileSystemTools(tmp_path)

    listed = tools.list_directory(".")
    assert listed.ok
    assert "hello.py" in listed.output

    read = tools.read_file("hello.py")
    assert read.ok
    assert "print('hi')" in read.output


def test_write_requires_approval(tmp_path: Path) -> None:
    tools = FileSystemTools(tmp_path)
    proposed = tools.write_file("new.py", "x = 1\n")
    assert proposed.ok
    assert proposed.pending_write is not None
    assert not (tmp_path / "new.py").exists()

    applied = tools.apply_write(proposed.pending_write)
    assert applied.ok
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "x = 1\n"


def test_parse_tool_call() -> None:
    text = """
I need to inspect the file.
<tool_call>
{"name": "read_file", "arguments": {"path": "src/config.py"}}
</tool_call>
"""
    parsed = ToolAgent._parse_tool_call(text)
    assert parsed is not None
    assert parsed["name"] == "read_file"
    assert parsed["arguments"]["path"] == "src/config.py"
