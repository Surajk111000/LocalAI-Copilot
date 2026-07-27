"""Local ChromaDB wrapper for project code chunks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from src.config import ROOT_DIR


def collection_name_for_path(project_path: Path) -> str:
    """Stable short name so each project gets its own vector collection."""
    digest = hashlib.sha1(str(project_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"project_{digest}"


def chroma_persist_dir_for_project(project_path: str | Path | None = None) -> Path:
    """Per-project Chroma folder under memory/projects/<id>/chroma.

    Falls back to the legacy shared memory/chroma when no project is given.
    """
    if project_path:
        from src.workspace.paths import chroma_dir

        return chroma_dir(project_path)
    return ROOT_DIR / "memory" / "chroma"


def get_chroma_client(persist_dir: Path | None = None) -> chromadb.PersistentClient:
    """Open (or create) an on-disk Chroma database."""
    path = persist_dir or (ROOT_DIR / "memory" / "chroma")
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_project_chroma_client(project_path: str | Path) -> chromadb.PersistentClient:
    """Client rooted at this project's private vector DB directory."""
    return get_chroma_client(chroma_persist_dir_for_project(project_path))


def get_or_create_collection(
    client: chromadb.PersistentClient,
    name: str,
) -> Collection:
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(client: chromadb.PersistentClient, name: str) -> Collection:
    """Delete and recreate a collection (used when re-indexing a project)."""
    try:
        client.delete_collection(name)
    except Exception:
        pass
    return get_or_create_collection(client, name)


def query_collection(
    collection: Collection,
    query_embedding: list[float],
    n_results: int = 5,
) -> dict[str, Any]:
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
