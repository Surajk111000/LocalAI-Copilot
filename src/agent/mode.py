"""Copilot interaction modes."""

from __future__ import annotations

from enum import Enum


class CopilotMode(str, Enum):
    CHAT = "chat"
    AGENT = "agent"


def is_agent_mode(value: str | CopilotMode | None) -> bool:
    if value is None:
        return False
    if isinstance(value, CopilotMode):
        return value is CopilotMode.AGENT or value == CopilotMode.AGENT
    text = str(value).lower().strip()
    return text in {CopilotMode.AGENT.value, "agent"} or text.endswith(".agent")
