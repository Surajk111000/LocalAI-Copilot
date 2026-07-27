"""AI dashboard metrics: chats, tokens, timings, index stats."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.sessions.store import SessionStore
from src.workspace.paths import project_dir, read_json, write_json


@dataclass
class TimingSample:
    label: str
    ms: float
    timestamp: float


@dataclass
class MetricsState:
    prompt_tokens_est: int = 0
    completion_tokens_est: int = 0
    response_count: int = 0
    total_response_ms: float = 0.0
    timings: list[dict[str, Any]] = field(default_factory=list)


_lock = threading.Lock()


def estimate_tokens(text: str) -> int:
    return max(0, len(text or "") // 4)


class MetricsStore:
    """Thread-safe per-project metrics for the AI dashboard."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.path = project_dir(self.project_path) / "metrics.json"

    def _load(self) -> MetricsState:
        raw = read_json(self.path, {})
        return MetricsState(
            prompt_tokens_est=int(raw.get("prompt_tokens_est") or 0),
            completion_tokens_est=int(raw.get("completion_tokens_est") or 0),
            response_count=int(raw.get("response_count") or 0),
            total_response_ms=float(raw.get("total_response_ms") or 0.0),
            timings=list(raw.get("timings") or [])[-50:],
        )

    def _save(self, state: MetricsState) -> None:
        write_json(self.path, asdict(state))

    def record_response(self, prompt: str, answer: str, elapsed_ms: float) -> None:
        with _lock:
            state = self._load()
            state.prompt_tokens_est += estimate_tokens(prompt)
            state.completion_tokens_est += estimate_tokens(answer)
            state.response_count += 1
            state.total_response_ms += float(elapsed_ms)
            state.timings.append(
                {
                    "label": "chat_response",
                    "ms": round(float(elapsed_ms), 1),
                    "timestamp": time.time(),
                }
            )
            state.timings = state.timings[-50:]
            self._save(state)

    def snapshot(self) -> dict[str, Any]:
        with _lock:
            state = self._load()
        avg = (
            state.total_response_ms / state.response_count
            if state.response_count
            else 0.0
        )
        chat_count = 0
        try:
            chat_count = len(SessionStore(self.project_path).list_sessions())
        except Exception:
            chat_count = 0

        indexed_files = 0
        embedding_chunks = 0
        try:
            from src.rag.retriever import ProjectRetriever
            from src.rag.embeddings import OllamaEmbedder
            from src.config import get_ollama_settings

            settings = get_ollama_settings()
            embedder = OllamaEmbedder(settings["base_url"], settings["embed_model"])
            retriever = ProjectRetriever(embedder)
            # Approximate via collection count if indexed
            from src.rag.store import (
                collection_name_for_path,
                get_or_create_collection,
                get_project_chroma_client,
            )

            client = get_project_chroma_client(self.project_path)
            name = collection_name_for_path(Path(self.project_path))
            coll = get_or_create_collection(client, name)
            embedding_chunks = coll.count()
            # Distinct paths if available is expensive; use chunk count as proxy
            indexed_files = embedding_chunks
        except Exception:
            pass

        return {
            "chat_count": chat_count,
            "response_count": state.response_count,
            "prompt_tokens_est": state.prompt_tokens_est,
            "completion_tokens_est": state.completion_tokens_est,
            "avg_response_ms": round(avg, 1),
            "indexed_chunks": embedding_chunks,
            "indexed_files_proxy": indexed_files,
            "recent_timings": state.timings[-10:],
        }
