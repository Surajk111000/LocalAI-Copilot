"""Edit-plan data types (no filesystem path imports — safe for UI imports)."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class EditPlan:
    id: str
    goal: str
    summary: str
    analysis: str
    files_to_modify: list[str] = field(default_factory=list)
    files_to_create: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    status: str = "awaiting_approval"  # awaiting_approval | approved | rejected | generating | ready
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditPlan":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            goal=str(data.get("goal") or ""),
            summary=str(data.get("summary") or ""),
            analysis=str(data.get("analysis") or ""),
            files_to_modify=list(data.get("files_to_modify") or []),
            files_to_create=list(data.get("files_to_create") or []),
            steps=list(data.get("steps") or []),
            status=str(data.get("status") or "awaiting_approval"),
            notes=str(data.get("notes") or ""),
        )
