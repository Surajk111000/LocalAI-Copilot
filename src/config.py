"""Load YAML config for the local coding copilot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "config.yaml"
EXAMPLE_CONFIG_PATH = ROOT_DIR / "config" / "config.example.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Read config.yaml (falls back to the example file if missing)."""
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        config_path = EXAMPLE_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            "No config found. Create config/config.yaml from config.example.yaml."
        )
    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data


def get_ollama_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return Ollama connection settings with safe defaults for a 4GB GPU laptop."""
    cfg = config or load_config()
    ollama = cfg.get("ollama", {})
    return {
        "base_url": ollama.get("base_url", "http://localhost:11434").rstrip("/"),
        "model": ollama.get("model", "qwen2.5-coder:3b"),
        "temperature": float(ollama.get("temperature", 0.2)),
        "num_predict": int(ollama.get("num_predict", 2048)),
        "embed_model": ollama.get("embed_model", "nomic-embed-text"),
        "num_thread": ollama.get("num_thread"),
    }


def get_rag_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return RAG indexing/retrieval settings."""
    cfg = config or load_config()
    rag = cfg.get("rag", {})
    return {
        "chunk_size": int(rag.get("chunk_size", 1200)),
        "overlap": int(rag.get("overlap", 200)),
        "top_k": int(rag.get("top_k", 5)),
        "batch_size": int(rag.get("batch_size", 16)),
    }
