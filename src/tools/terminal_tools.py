"""Approval-gated terminal tools (local project only)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Allowlist prefixes for auto-run (still sandboxed to project cwd)
SAFE_PREFIXES = (
    "pytest",
    "python -m pytest",
    "python -m compileall",
    "ruff check",
    "ruff format --check",
    "mypy",
    "npm test",
    "npm run test",
    "npm run build",
    "npm run lint",
    "dir",
    "ls",
    "git status",
    "git diff",
    "git log",
)

BLOCKED_PATTERNS = [
    re.compile(r"\brm\s+-rf\b", re.I),
    re.compile(r"\bdel\s+/[sf]\b", re.I),
    re.compile(r"\bformat\s+", re.I),
    re.compile(r"\bshutdown\b", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r">\s*/dev/", re.I),
    re.compile(r"\bcurl\b.*\|\s*(sh|bash)", re.I),
    re.compile(r"\bgit\s+push\s+.*(-f|--force)\b", re.I),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.I),
]


@dataclass
class TerminalResult:
    ok: bool
    output: str
    needs_approval: bool = False
    command: str = ""


def _blocked(command: str) -> bool:
    return any(p.search(command) for p in BLOCKED_PATTERNS)


def _is_safe(command: str) -> bool:
    c = " ".join(command.strip().split())
    return any(c.lower().startswith(prefix) for prefix in SAFE_PREFIXES)


class TerminalTools:
    """Run commands in the project directory with a safety gate."""

    def __init__(self, project_path: str | Path) -> None:
        self.root = Path(project_path).expanduser().resolve()

    def run(self, command: str, *, approved: bool = False, timeout: int = 60) -> TerminalResult:
        command = (command or "").strip()
        if not command:
            return TerminalResult(False, "Empty command.", command=command)
        if _blocked(command):
            return TerminalResult(
                False,
                "Blocked dangerous command pattern.",
                needs_approval=True,
                command=command,
            )
        if not _is_safe(command) and not approved:
            return TerminalResult(
                False,
                "Command is not on the safe allowlist. Approve explicitly in the UI to run.",
                needs_approval=True,
                command=command,
            )
        try:
            proc = subprocess.run(
                command,
                cwd=str(self.root),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            out = ((proc.stdout or "") + (proc.stderr or "")).strip() or "(empty)"
            # Cap output size for LLM/UI
            if len(out) > 12_000:
                out = out[:12_000] + "\n… truncated …"
            return TerminalResult(proc.returncode == 0, out, command=command)
        except subprocess.TimeoutExpired:
            return TerminalResult(False, "Command timed out.", command=command)
        except Exception as exc:  # noqa: BLE001
            return TerminalResult(False, str(exc), command=command)
