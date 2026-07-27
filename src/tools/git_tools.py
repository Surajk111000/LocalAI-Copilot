"""Approval-gated git tools for the multi-agent system."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

# Read-only / safe by default
SAFE_GIT = {
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "remote",
    "rev-parse",
    "stash list",
}

# Require explicit user approval before running
DESTRUCTIVE_GIT = {
    "reset",
    "clean",
    "checkout",
    "restore",
    "push --force",
    "push -f",
    "branch -D",
    "rebase",
}


@dataclass
class GitResult:
    ok: bool
    output: str
    needs_approval: bool = False
    command: str = ""


def _run(project_path: str | Path, args: list[str], timeout: int = 30) -> GitResult:
    root = Path(project_path).expanduser().resolve()
    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return GitResult(ok=proc.returncode == 0, output=out.strip() or "(empty)", command=" ".join(cmd))
    except FileNotFoundError:
        return GitResult(False, "git executable not found on PATH.", command=" ".join(cmd))
    except subprocess.TimeoutExpired:
        return GitResult(False, "git command timed out.", command=" ".join(cmd))


def _is_destructive(args: list[str]) -> bool:
    joined = " ".join(args).lower()
    if any(flag in joined for flag in ("--force", " -f", " -d", " -D", "--hard", "--clean")):
        return True
    if args and args[0].lower() in {"reset", "clean", "rebase", "restore"}:
        return True
    if len(args) >= 2 and args[0] == "branch" and args[1] in {"-D", "-d"}:
        return True
    if args and args[0] == "push" and any(a in {"--force", "-f"} for a in args):
        return True
    return False


class GitTools:
    """Safe git wrapper — destructive commands return needs_approval instead of running."""

    def __init__(self, project_path: str | Path) -> None:
        self.root = Path(project_path).expanduser().resolve()

    def status(self) -> GitResult:
        return _run(self.root, ["status", "--short", "--branch"])

    def diff(self, staged: bool = False) -> GitResult:
        args = ["diff", "--stat"]
        if staged:
            args.insert(1, "--cached")
        return _run(self.root, args)

    def log(self, n: int = 5) -> GitResult:
        return _run(self.root, ["log", f"-{n}", "--oneline"])

    def branch(self) -> GitResult:
        return _run(self.root, ["branch", "-vv"])

    def current_branch(self) -> GitResult:
        return _run(self.root, ["rev-parse", "--abbrev-ref", "HEAD"])

    def diff_full(self, staged: bool = False) -> GitResult:
        args = ["diff"]
        if staged:
            args.append("--cached")
        return _run(self.root, args)

    def add(self, paths: list[str] | None = None, *, approved: bool = True) -> GitResult:
        targets = paths or ["."]
        return self.run(["add", *targets], approved=approved)

    def commit(self, message: str, *, approved: bool = False) -> GitResult:
        message = (message or "").strip()
        if not message:
            return GitResult(False, "Commit message required.", command="git commit")
        # Commit is gated — mutates repo history tip
        if not approved:
            return GitResult(
                False,
                "Commit requires approval.",
                needs_approval=True,
                command=f'git commit -m {message!r}',
            )
        return _run(self.root, ["commit", "-m", message])

    def pull(self, *, approved: bool = False) -> GitResult:
        if not approved:
            return GitResult(
                False,
                "git pull requires approval (may merge remote changes).",
                needs_approval=True,
                command="git pull",
            )
        return _run(self.root, ["pull"], timeout=60)

    def push(self, *, approved: bool = False, force: bool = False) -> GitResult:
        args = ["push"]
        if force:
            args.append("--force")
        return self.run(args, approved=approved)

    def run(self, args: list[str], *, approved: bool = False) -> GitResult:
        args = [str(a) for a in args]
        # Treat bare push/pull/commit as needing approval
        if args and args[0] in {"push", "pull", "commit"} and not approved:
            return GitResult(
                ok=False,
                output=f"git {args[0]} requires explicit approval.",
                needs_approval=True,
                command="git " + " ".join(args),
            )
        if _is_destructive(args) and not approved:
            return GitResult(
                ok=False,
                output=(
                    "Destructive git command blocked. "
                    "Add to pending approvals and confirm in the UI."
                ),
                needs_approval=True,
                command="git " + " ".join(args),
            )
        return _run(self.root, args)
