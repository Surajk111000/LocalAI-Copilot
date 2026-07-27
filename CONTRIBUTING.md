# Contributing Guide

Thanks for helping improve **Local AI Coding Copilot**.

## Principles

1. **Local-first** — no cloud LLM/API keys required for core flows.
2. **Approval-gated writes** — never write/delete/push without explicit user approval.
3. **Modular packages** — prefer `src/<area>/` modules over growing `streamlit_app.py`.
4. **Tests** — add/adjust pytest coverage for new libraries.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
pytest -q
streamlit run ui/streamlit_app.py
```

## Project layout (where to put code)

| Area | Path |
|------|------|
| UI | `ui/`, `ui/components/` |
| LLM | `src/llm/` |
| RAG | `src/rag/` |
| Editing / diffs | `src/editing/` |
| Multi-agent | `src/multi_agent/` |
| Productivity | `src/productivity/` |
| Plugins | `src/plugins/` |
| Perf | `src/perf/` |
| Tools | `src/tools/` |

## Pull requests

1. Keep PRs focused (one feature / fix).
2. Do not commit `memory/`, `.venv/`, or secrets.
3. Update README/docs when user-facing behavior changes.
4. Run `pytest -q` before opening a PR.

## Code style

- Python 3.10+ type hints.
- Small, readable functions.
- Prefer dataclasses for structured data.
- Log tool side-effects via `src.productivity.devlog.console`.

## Plugin contributions

Register tools with:

```python
from src.plugins import register_tool

def my_tool(args: dict) -> dict:
    return {"ok": True, "data": args}

register_tool("my_tool", my_tool, description="…", plugin="community")
```

## License

By contributing, you agree your work is released under the MIT License.
