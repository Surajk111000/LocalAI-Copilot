"""Tests for quick list/read/create helpers."""

from pathlib import Path

from src.quick_actions import (
    extract_file_path,
    handle_list,
    handle_read,
    propose_write_from_answer,
    wants_code_edit,
    wants_create_file,
    wants_list_files,
    wants_read_file,
)


def test_detectors_and_extract() -> None:
    assert wants_list_files("List the project files and explain the folder structure")
    assert wants_read_file("Read src/config.py and explain what each setting does")
    assert wants_create_file(
        "Create examples/hello.py with a hello_world() function and a main block"
    )
    assert not wants_create_file("Add a validate_email function to src/main.py")
    assert wants_code_edit("Add a validate_email function to src/main.py")
    assert extract_file_path("Read src/config.py and explain") == "src/config.py"


def test_list_and_read(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    listed = handle_list(str(tmp_path))
    assert listed.kind == "list"
    assert "a.py" in listed.context

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "config.py").write_text("MODEL = 'x'\n", encoding="utf-8")
    read = handle_read(str(tmp_path), "Read src/config.py and explain it")
    assert "MODEL" in read.context


def test_propose_write(tmp_path: Path) -> None:
    answer = "Here is the file:\n```python\ndef hello():\n    return 'hi'\n```\n"
    pending = propose_write_from_answer(str(tmp_path), "examples/hello.py", answer)
    assert pending is not None
    assert pending.path == "examples/hello.py"
    assert "def hello" in pending.content
