"""Error / traceback assistant: locate source and suggest fixes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.llm.ollama_client import OllamaClient, OllamaError
from src.tools.filesystem import FileSystemTools

FRAME_RE = re.compile(
    r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>\S+))?'
)
JS_FRAME_RE = re.compile(
    r"(?P<file>[\w./\\-]+\.(?:py|js|ts|tsx|jsx)):?(?P<line>\d+)?(?::(?P<col>\d+))?"
)


@dataclass
class TraceFrame:
    file: str
    line: int
    func: str = ""


@dataclass
class ErrorAssistResult:
    frames: list[TraceFrame]
    local_files: list[str]
    snippets: dict[str, str]
    suggestion: str


def parse_traceback(traceback_text: str) -> list[TraceFrame]:
    frames: list[TraceFrame] = []
    for match in FRAME_RE.finditer(traceback_text or ""):
        frames.append(
            TraceFrame(
                file=match.group("file"),
                line=int(match.group("line")),
                func=match.group("func") or "",
            )
        )
    if frames:
        return frames
    # Fallback loose parser
    for match in JS_FRAME_RE.finditer(traceback_text or ""):
        line = int(match.group("line") or 1)
        frames.append(TraceFrame(file=match.group("file"), line=line))
    return frames


def _resolve_in_project(project_path: Path, file_hint: str) -> str | None:
    hint = Path(file_hint)
    # Absolute path inside project
    try:
        resolved = hint if hint.is_absolute() else (project_path / hint)
        resolved = resolved.resolve()
        resolved.relative_to(project_path)
        if resolved.is_file():
            return str(resolved.relative_to(project_path)).replace("\\", "/")
    except Exception:
        pass
    # Search by basename
    name = hint.name
    for path in project_path.rglob(name):
        if path.is_file():
            return str(path.relative_to(project_path)).replace("\\", "/")
    return None


def assist_error(
    project_path: str | Path,
    traceback_text: str,
    client: OllamaClient | None = None,
) -> ErrorAssistResult:
    root = Path(project_path).expanduser().resolve()
    frames = parse_traceback(traceback_text)
    local_files: list[str] = []
    snippets: dict[str, str] = {}
    tools = FileSystemTools(root)

    for frame in frames[-5:]:
        rel = _resolve_in_project(root, frame.file)
        if not rel:
            continue
        if rel not in local_files:
            local_files.append(rel)
        result = tools.read_file(rel)
        if result.ok:
            lines = result.output.splitlines()
            # Extract window around line
            start = max(frame.line - 8, 1)
            # Find content after FILE header
            body_lines = lines
            for idx, line in enumerate(lines):
                if line.strip() == "" and idx > 0:
                    body_lines = lines[idx + 1 :]
                    break
            window = body_lines[start - 1 : frame.line + 8]
            numbered = "\n".join(
                f"{start + i:>4}: {text}" for i, text in enumerate(window)
            )
            snippets[f"{rel}:{frame.line}"] = numbered

    suggestion = ""
    if client is not None:
        prompt = (
            "You are a debugging assistant. Given a traceback and source snippets, "
            "explain the root cause and propose a minimal fix.\n\n"
            f"TRACEBACK:\n{traceback_text[:6000]}\n\n"
            "SNIPPETS:\n"
            + "\n\n".join(f"### {k}\n{v}" for k, v in snippets.items())
        )
        try:
            suggestion = client.chat(
                [
                    {
                        "role": "system",
                        "content": "Be concrete. Cite file paths. Propose minimal fixes.",
                    },
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )  # type: ignore[assignment]
            assert isinstance(suggestion, str)
        except OllamaError as exc:
            suggestion = f"**Error contacting model:** {exc}"
    elif not suggestion:
        suggestion = (
            "Paste this into Agent/Chat after reviewing located files, "
            "or enable the model for automatic suggestions."
        )

    return ErrorAssistResult(
        frames=frames,
        local_files=local_files,
        snippets=snippets,
        suggestion=suggestion,
    )
