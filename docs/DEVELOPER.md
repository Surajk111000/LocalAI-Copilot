# Developer Guide

## Mental model

Think of the copilot as three layers:

1. **UI** (`ui/`) — Streamlit presentation + approval surfaces  
2. **Orchestration** (`src/multi_agent`, `src/agents`) — decide what to do  
3. **Tools** (`src/tools`, `src/rag`, `src/editing`) — do it safely  

## Add a productivity feature

1. Put pure logic in `src/productivity/` (or a new package)
2. Add a thin UI tab in `ui/components/productivity_hub.py`
3. Wire sidebar expander only if needed
4. Add tests under `tests/`
5. Log actions with `console.add(...)`

## Add an LLM option

`OllamaClient` options live in `src/llm/ollama_client.py`:

- `temperature`, `top_p`, `num_predict`, `num_ctx`, `num_thread`

Persist user prefs in `ProjectSettings` (`src/workspace/settings.py`).

## Background indexing

```python
from src.perf import start_background_indexing

start_background_indexing(project_path, indexer_factory)
```

Jobs are daemon threads; check status via `get_index_job`.

## Project rules

Create `.rules/*.md` (or `.cursorrules` / `AGENTS.md`).  
They are injected into the system prompt via `persona_system_prompt(...)`.

## Testing

```bash
pytest -q
```

Prefer fake Ollama clients in unit tests (see `tests/test_multi_agent.py`).

## Safety checklist for new tools

- [ ] Sandboxed to project root?
- [ ] Destructive path requires approval?
- [ ] Logged to developer console?
- [ ] Covered by a test?
