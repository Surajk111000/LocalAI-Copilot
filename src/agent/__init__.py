"""Agent package — lazy exports to avoid heavy import chains at UI startup."""

from __future__ import annotations

__all__ = [
    "AgentCoder",
    "AgentPlanner",
    "CopilotMode",
    "EditPlan",
    "is_agent_mode",
]


def __getattr__(name: str):
    if name in {"CopilotMode", "is_agent_mode"}:
        from src.agent import mode as _mode

        return getattr(_mode, name)
    if name == "EditPlan":
        from src.agent.plan_types import EditPlan

        return EditPlan
    if name in {"AgentCoder", "AgentPlanner"}:
        from src.agent import planner as _planner

        return getattr(_planner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
