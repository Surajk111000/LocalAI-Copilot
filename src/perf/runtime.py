"""Performance helpers: cache, lazy load, background indexing."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache:
    """Simple thread-safe TTL cache."""

    def __init__(self, default_ttl: float = 60.0) -> None:
        self.default_ttl = default_ttl
        self._data: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if entry.expires_at < time.time():
                self._data.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            self._data[key] = CacheEntry(
                value=value,
                expires_at=time.time() + float(ttl if ttl is not None else self.default_ttl),
            )

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# Shared caches
tree_cache = TTLCache(default_ttl=45.0)
rules_cache = TTLCache(default_ttl=120.0)


def lazy(factory: Callable[[], T]) -> Callable[[], T]:
    """Lazy singleton initializer (thread-safe)."""
    lock = threading.Lock()
    box: dict[str, T] = {}

    def getter() -> T:
        if "value" not in box:
            with lock:
                if "value" not in box:
                    box["value"] = factory()
        return box["value"]

    return getter


@dataclass
class BackgroundIndexJob:
    project_path: str
    status: str = "idle"  # idle | running | done | error
    message: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0


_jobs: dict[str, BackgroundIndexJob] = {}
_jobs_lock = threading.Lock()


def get_index_job(project_path: str) -> BackgroundIndexJob | None:
    key = str(Path(project_path).resolve())
    with _jobs_lock:
        return _jobs.get(key)


def start_background_indexing(
    project_path: str,
    indexer_factory: Callable[[], Any],
) -> BackgroundIndexJob:
    """Run ProjectIndexer.index_project in a daemon thread."""
    key = str(Path(project_path).resolve())
    with _jobs_lock:
        existing = _jobs.get(key)
        if existing and existing.status == "running":
            return existing
        job = BackgroundIndexJob(project_path=key, status="running", started_at=time.time())
        _jobs[key] = job

    def worker() -> None:
        try:
            indexer = indexer_factory()
            stats = indexer.index_project(key)
            with _jobs_lock:
                job.status = "done"
                job.message = (
                    f"Indexed {getattr(stats, 'chunks_indexed', 0)} chunks "
                    f"from {getattr(stats, 'files_indexed', 0)} files"
                )
                job.finished_at = time.time()
            tree_cache.clear()
        except Exception as exc:  # noqa: BLE001
            with _jobs_lock:
                job.status = "error"
                job.message = str(exc)
                job.finished_at = time.time()

    thread = threading.Thread(target=worker, name="bg-index", daemon=True)
    thread.start()
    return job
