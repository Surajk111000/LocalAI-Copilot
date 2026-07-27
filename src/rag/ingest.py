"""Index a project folder into ChromaDB using local Ollama embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.rag.chunker import chunk_file, iter_project_files
from src.rag.embeddings import OllamaEmbedder
from src.rag.store import (
    collection_name_for_path,
    get_project_chroma_client,
    reset_collection,
)


@dataclass
class IndexStats:
    project_path: str
    files_indexed: int
    chunks_indexed: int
    collection_name: str


class ProjectIndexer:
    """Walk a folder → chunk files → embed → store in ChromaDB."""

    def __init__(
        self,
        embedder: OllamaEmbedder,
        *,
        chunk_size: int = 1200,
        overlap: int = 200,
        batch_size: int = 16,
    ) -> None:
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.batch_size = batch_size

    def index_project(self, project_path: str | Path) -> IndexStats:
        root = Path(project_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Project folder not found: {root}")

        files = iter_project_files(root)
        all_chunks = []
        for file_path in files:
            all_chunks.extend(
                chunk_file(
                    file_path,
                    root,
                    chunk_size=self.chunk_size,
                    overlap=self.overlap,
                )
            )

        client = get_project_chroma_client(root)
        name = collection_name_for_path(root)
        collection = reset_collection(client, name)

        if not all_chunks:
            return IndexStats(
                project_path=str(root),
                files_indexed=0,
                chunks_indexed=0,
                collection_name=name,
            )

        # Embed and upsert in small batches to avoid long single requests
        for start in range(0, len(all_chunks), self.batch_size):
            batch = all_chunks[start : start + self.batch_size]
            texts = [
                f"File: {chunk.path}\nLines: {chunk.start_line}-{chunk.end_line}\n\n"
                f"{chunk.content}"
                for chunk in batch
            ]
            embeddings = self.embedder.embed_batch(texts)
            collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                documents=[chunk.content for chunk in batch],
                embeddings=embeddings,
                metadatas=[
                    {
                        "path": chunk.path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "project_path": str(root),
                    }
                    for chunk in batch
                ],
            )

        return IndexStats(
            project_path=str(root),
            files_indexed=len(files),
            chunks_indexed=len(all_chunks),
            collection_name=name,
        )
