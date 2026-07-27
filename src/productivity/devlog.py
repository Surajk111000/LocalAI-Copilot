"""Developer console / tool execution logs."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class LogEvent:
    level: str
    source: str
    message: str
    detail: str = ""
    timestamp: float = 0.0


class DevLog:
    """Ring-buffer log for tool executions and diagnostics."""

    def __init__(self, maxlen: int = 300) -> None:
        self._events: deque[LogEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(
        self,
        message: str,
        *,
        level: str = "info",
        source: str = "app",
        detail: str = "",
    ) -> None:
        event = LogEvent(
            level=level,
            source=source,
            message=message,
            detail=detail,
            timestamp=time.time(),
        )
        with self._lock:
            self._events.append(event)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._events)[-limit:]
        return [asdict(e) for e in items]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


# Process-wide console
console = DevLog()
