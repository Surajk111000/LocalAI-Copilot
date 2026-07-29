"""Per-project workspace settings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from src.workspace.paths import read_json, settings_path, write_json


@dataclass
class ProjectSettings:
    preferred_model: str = "qwen2.5-coder:3b"
    rag_enabled: bool = False
    cpu_threads: int = 2  # low by default — keeps UI smoother on laptops
    temperature: float = 0.2
    top_p: float = 0.9
    context_size: int = 4096
    streaming: bool = True
    filesystem_enabled: bool = False
    persona_id: str = "default"
    theme: str = "dark"  # dark | light
    system_prompt: str = (
        "You are a local coding assistant. Be concise and practical. "
        "Prefer clear steps and short code examples."
    )


class SettingsStore:
    def __init__(self, project_path: str | Path) -> None:
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.path = settings_path(self.project_path)

    def load(self) -> ProjectSettings:
        raw = read_json(self.path, {})
        return ProjectSettings(
            preferred_model=str(raw.get("preferred_model") or "qwen2.5-coder:3b"),
            rag_enabled=bool(raw.get("rag_enabled", False)),
            cpu_threads=int(raw.get("cpu_threads") or 2),
            temperature=float(raw.get("temperature") if raw.get("temperature") is not None else 0.2),
            top_p=float(raw.get("top_p") if raw.get("top_p") is not None else 0.9),
            context_size=int(raw.get("context_size") or 4096),
            streaming=bool(raw.get("streaming", True)),
            filesystem_enabled=bool(raw.get("filesystem_enabled", False)),
            persona_id=str(raw.get("persona_id") or "default"),
            theme=str(raw.get("theme") or "dark"),
            system_prompt=str(
                raw.get("system_prompt")
                or ProjectSettings().system_prompt
            ),
        )

    def save(self, settings: ProjectSettings) -> None:
        write_json(self.path, asdict(settings))

    def update(self, **kwargs) -> ProjectSettings:
        current = self.load()
        for key, value in kwargs.items():
            if hasattr(current, key):
                setattr(current, key, value)
        self.save(current)
        return current
