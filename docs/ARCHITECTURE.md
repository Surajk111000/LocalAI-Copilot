# Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     Streamlit UI (ui/)                       │
│  Chat | Agent | Productivity | Dashboard | Diff | Explorer  │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
        ┌───────▼────────┐           ┌────────▼────────┐
        │  Chat path     │           │  Agent path     │
        │  Ollama stream │           │  LangGraph      │
        └───────┬────────┘           └────────┬────────┘
                │                             │
                │     Planner→Research→Analyzer→Coder
                │     →Reviewer→Tester→Docs→Final
                │                             │
        ┌───────▼─────────────────────────────▼────────┐
        │                 Shared services               │
        │  RAG (Chroma) │ Filesystem │ Git │ Terminal   │
        │  Personas │ Rules │ Prompts │ Plugins │ Metrics│
        └──────────────────────┬───────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Ollama (localhost)  │
                    │ chat + embeddings   │
                    └─────────────────────┘
```

## Approval gates

Destructive or mutating operations never run silently:

1. **File writes** → Diff viewer Accept/Reject (+ version history/undo)
2. **Git commit/push/pull/reset** → explicit UI approval
3. **Terminal** → allowlist or approve-to-run
4. **LangGraph** → interrupt after Planner

## Per-project memory (`memory/projects/<id>/`)

- `chats/` — chat sessions
- `chroma/` — vector index
- `settings.json` — model/persona/theme/RAG/threads
- `versions/` — accepted edit history
- `metrics.json` — dashboard stats
- `prompt_library.json` — custom prompts
- `multi_agent_memory.json` — agent conversation memory

## Key packages

| Package | Responsibility |
|---------|----------------|
| `src/llm` | Ollama HTTP client |
| `src/rag` | chunk → embed → retrieve |
| `src/multi_agent` | LangGraph pipeline |
| `src/editing` | diffs, apply, undo |
| `src/productivity` | prompts, personas, todos, export, errors |
| `src/plugins` | tool registration API |
| `src/perf` | TTL cache, background indexing |
