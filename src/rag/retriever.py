"""Retrieve the most relevant code chunks for a user question."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.rag.embeddings import OllamaEmbedder
from src.rag.store import (
    collection_name_for_path,
    get_chroma_client,
    get_or_create_collection,
    get_project_chroma_client,
    query_collection,
)


@dataclass
class RetrievedChunk:
    path: str
    content: str
    start_line: int
    end_line: int
    score: float


class ProjectRetriever:
    """Search the indexed project for code related to a question."""

    def __init__(self, embedder: OllamaEmbedder, top_k: int = 5) -> None:
        self.embedder = embedder
        self.top_k = top_k

    def _client_for(self, root: Path):
        """Prefer per-project DB; fall back to legacy shared memory/chroma."""
        try:
            client = get_project_chroma_client(root)
            name = collection_name_for_path(root)
            collection = get_or_create_collection(client, name)
            if collection.count() > 0:
                return client
        except Exception:
            pass
        return get_chroma_client()

    def has_index(self, project_path: str | Path) -> bool:
        root = Path(project_path).expanduser().resolve()
        name = collection_name_for_path(root)
        clients = [get_project_chroma_client(root), get_chroma_client()]
        for client in clients:
            try:
                collection = get_or_create_collection(client, name)
                if collection.count() > 0:
                    return True
            except Exception:
                continue
        return False

    def retrieve(
        self,
        project_path: str | Path,
        question: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        root = Path(project_path).expanduser().resolve()
        client = self._client_for(root)
        name = collection_name_for_path(root)
        collection = get_or_create_collection(client, name)

        if collection.count() == 0:
            return []

        k = top_k or self.top_k
        query_vec = self.embedder.embed(question)
        raw = query_collection(collection, query_vec, n_results=k)

        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        results: list[RetrievedChunk] = []
        for doc, meta, distance in zip(documents, metadatas, distances):
            # Cosine distance from Chroma: lower is better. Convert to a 0–1-ish score.
            score = 1.0 - float(distance) if distance is not None else 0.0
            results.append(
                RetrievedChunk(
                    path=str(meta.get("path", "unknown")),
                    content=doc or "",
                    start_line=int(meta.get("start_line", 1)),
                    end_line=int(meta.get("end_line", 1)),
                    score=score,
                )
            )
        return results

    @staticmethod
    def format_context(chunks: list[RetrievedChunk]) -> str:
        """Turn retrieved chunks into prompt text for the LLM."""
        if not chunks:
            return ""
        parts: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            parts.append(
                f"[{i}] {chunk.path} (lines {chunk.start_line}-{chunk.end_line})\n"
                f"{chunk.content}"
            )
        return "\n\n---\n\n".join(parts)
