"""Shared LLM helpers for multi-agent nodes."""

from __future__ import annotations

import json
import re
from typing import Any

from src.llm.ollama_client import OllamaClient, OllamaError

JSON_RE = re.compile(r"\{[\s\S]*\}")


def chat_json(client: OllamaClient, system: str, user: str) -> dict[str, Any]:
    """Ask the model for JSON; return {} on failure."""
    try:
        raw = client.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=False,
        )
        assert isinstance(raw, str)
        return extract_json(raw)
    except OllamaError:
        return {}


def chat_text(client: OllamaClient, system: str, user: str) -> str:
    try:
        raw = client.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=False,
        )
        assert isinstance(raw, str)
        return raw.strip()
    except OllamaError as exc:
        return f"**Error:** {exc}"


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = JSON_RE.search(text)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
