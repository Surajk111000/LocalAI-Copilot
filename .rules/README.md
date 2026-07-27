# Project rules

These conventions are loaded by Local AI Coding Copilot.

## General

- Prefer minimal, focused changes.
- Do not invent cloud services the user did not ask for.
- Never commit secrets (API keys, `.env` with credentials).

## Python

- Use type hints (Python 3.10+).
- Keep modules small and testable.
- Avoid silent file overwrites — propose diffs for approval.

## Git / terminal

- No `reset --hard`, force-push, or `rm -rf` without explicit user approval.
- Prefer conventional commit messages.

## UI

- Keep Streamlit components modular under `ui/components/`.
- Dark theme is default; light theme must remain readable.
