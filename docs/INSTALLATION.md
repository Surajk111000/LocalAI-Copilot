# Installation Guide

## Prerequisites

- Windows / macOS / Linux
- Python **3.10+**
- [Ollama](https://ollama.com) installed and running
- 8–16 GB RAM recommended (GTX 1050 4GB works with small models)

## 1. Install Ollama models

```bash
ollama pull qwen2.5-coder:3b
ollama pull nomic-embed-text
```

## 2. Clone / open the project

```bash
cd Local-AI-Coding-Copilot
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

### macOS / Linux

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure (optional)

Copy `config/config.example.yaml` → `config/config.yaml` and adjust:

- `ollama.model`
- `ollama.temperature`
- `ollama.num_thread`

## 4. Run

```bash
streamlit run ui/streamlit_app.py
```

Open http://localhost:8501

## 5. First project

1. Sidebar → **Open** a folder
2. Optional: **Index project** (RAG)
3. Use **Chat** for Q&A or **Agent** for multi-file plans
4. Accept diffs before any disk write

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Ollama not running | Start the Ollama app |
| Embed model in chat dropdown | Use coding model; keep `nomic-embed-text` for index only |
| Slow laptop | Lower CPU threads in Workspace settings |
| Stale UI | Restart Streamlit; delete `__pycache__` if needed |
