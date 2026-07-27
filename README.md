# Local AI Coding Copilot

A **local-first** AI coding assistant. You type a command in a Streamlit UI; a model running on your laptop (via [Ollama](https://ollama.com)) writes the code.

No cloud API keys. No deployment. Push this repo to GitHub to show the engineering — run it on your machine.

## Features

### Phase 1 — Local coding chat
- Chat UI built with Streamlit
- Local LLM via Ollama (`qwen2.5-coder:3b` by default — friendly to 4GB VRAM)
- Coding-focused system prompt (command → code)
- Streaming responses
- Model picker + connection status in the sidebar

### Phase 2 — Project memory (RAG)
- Index a local project folder
- Embeddings via `nomic-embed-text` (Ollama)
- Vector store: ChromaDB (stored under `memory/`, gitignored)
- Answers cite which files were used

### Phase 3 — Filesystem tools
- Agent can `list_directory`, `read_file`, `search_files`
- `write_file` proposes changes — **you approve before anything is saved**
- Paths are sandboxed to the selected project folder

### Phase 4 — Multi-workspace
- Open/switch multiple projects, explorer, context manager, chat sessions, per-project memory

### Phase 5 — Cursor-style editing
- Chat vs Agent modes, plan → diff → accept, version history + undo
- Smart search, symbols, rename, inline AI, review/tests/docs/commit assistants

### Phase 7 — Productivity suite (Cursor / Windsurf / Cline inspired)
- Prompt library + custom AI personas
- Project `.rules/` conventions
- Terminal assistant (generate → approve → run)
- Git integration (status/diff/branch/commit/push/pull + commit messages)
- TODO/FIXME/BUG/HACK scanner + traceback Error Assistant
- Session memory, AI dashboard, developer logs
- Settings: temperature, top_p, context size, threads, streaming, theme
- Plugin API, chat export (Markdown/JSON/HTML-PDF), keyboard shortcut map
- Performance: TTL cache, background indexing
- Docs: Architecture, Installation, Developer, Contributing, MIT License

## Architecture

```text
You → Streamlit UI
        ├── Chat mode (fast Q&A)
        └── Agent mode → LangGraph multi-agent
              Planner → Research → Analyzer → Coder
                → Reviewer → Tester → Docs → Final
              (interrupt after Planner for approval)
              Tools: filesystem | git | terminal | RAG
              Diff Accept/Reject → Version history / Undo
              memory/projects/<id>/…
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Installation](docs/INSTALLATION.md)
- [Developer guide](docs/DEVELOPER.md)
- [Contributing](CONTRIBUTING.md)
- [License (MIT)](LICENSE)

- Python 3.10+
- [Ollama](https://ollama.com) installed and running
- ~8–16 GB RAM (16 GB recommended)
- Optional: NVIDIA GPU (GTX 1050 4GB works with small/quantized models)

## Quick start

### 1. Install Ollama

Download from https://ollama.com and open the app.

### 2. Pull a coding model

```bash
ollama pull qwen2.5-coder:3b
ollama pull nomic-embed-text
```

If coding feels fast enough later, try:

```bash
ollama pull qwen2.5-coder:7b
```

Then change `config/config.yaml` → `ollama.model` to `qwen2.5-coder:7b`.

### 3. Install Python deps

```bash
cd Local-AI-Coding-Copilot
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Run the UI

```bash
streamlit run ui/streamlit_app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

### 5. Index a project (RAG)

In the sidebar:
1. Paste a local folder path (for example this repo itself)
2. Click **Index project**
3. Keep **Use project context** on
4. Ask: `Explain this project` or `Where is the Ollama client?`

### 6. Use filesystem tools

1. Keep **Enable filesystem tools** on
2. Ask: `List the project files` or `Read src/config.py and explain it`
3. To create a file: `Create examples/hello.py with a hello function`
4. Review the proposed file → **Approve write** or **Reject**

## Example commands

- `List the project files`
- `Read src/config.py and explain it`
- `Search for OllamaClient`
- `Create examples/hello.py with a hello function`
- `Explain this project`

## Project layout

```text
Local-AI-Coding-Copilot/
├── config/
│   ├── config.yaml           # local settings (safe to edit)
│   └── config.example.yaml   # template for GitHub
├── src/
│   ├── config.py
│   ├── agents/
│   │   └── tool_agent.py     # tool-calling loop
│   ├── tools/
│   │   └── filesystem.py     # list/read/search/write
│   ├── llm/
│   │   └── ollama_client.py  # talks to local Ollama
│   └── rag/
│       ├── chunker.py
│       ├── embeddings.py
│       ├── ingest.py
│       ├── retriever.py
│       └── store.py
├── ui/
│   └── streamlit_app.py
├── memory/                   # local ChromaDB (gitignored)
├── requirements.txt
└── README.md
```

## Local-only by design

- Models live inside Ollama on your PC (not in this git repo)
- The app calls `http://localhost:11434` only
- Indexed project data stays in `memory/` on your disk
- GitHub hosts **source code + docs**, not your model weights or personal indexes

## Roadmap

- [x] Local coding chat (Ollama + Streamlit)
- [x] RAG over a project folder (ChromaDB + embeddings)
- [x] File read/write tools (with approval)
- [ ] Git + terminal tools
- [ ] Multi-agent flow (planner → coder → reviewer) with LangGraph
- [ ] Continue.dev / VS Code setup guide

## License

MIT (add a LICENSE file when you publish).
