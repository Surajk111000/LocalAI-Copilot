"""Thin HTTP client for a local Ollama server.

Ollama runs on your machine and exposes a simple REST API.
This module is the only place that talks to that API.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Iterable
from typing import Any

import requests


class OllamaError(Exception):
    """Raised when Ollama is unreachable or returns an error."""


def is_embedding_model(name: str) -> bool:
    """Heuristic: embedding models must not be used for /api/chat."""
    n = (name or "").lower()
    markers = (
        "embed",
        "embedding",
        "nomic-embed",
        "bge-",
        "e5-",
        "gte-",
        "mxbai-embed",
        "snowflake-arctic-embed",
        "all-minilm",
    )
    return any(m in n for m in markers)


def is_chat_model(name: str) -> bool:
    """True when the model can be used for coding chat."""
    return bool(name) and not is_embedding_model(name)


class OllamaClient:
    """Talk to a local Ollama instance (default: http://localhost:11434)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:3b",
        temperature: float = 0.2,
        top_p: float = 0.9,
        num_predict: int = 2048,
        num_ctx: int | None = None,
        num_thread: int | None = None,
        timeout: int = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.num_predict = num_predict
        self.num_ctx = num_ctx
        self.num_thread = num_thread
        self.timeout = timeout

    def is_available(self) -> bool:
        """Return True if the Ollama server responds."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        """Return model names installed in Ollama."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(
                "Cannot reach Ollama. Install it from https://ollama.com and start the app."
            ) from exc

        models = response.json().get("models", [])
        return [item.get("name", "") for item in models if item.get("name")]

    def list_chat_models(self) -> list[str]:
        """Return installed models that can chat (excludes embedding-only models)."""
        return [name for name in self.list_models() if is_chat_model(name)]

    def list_embed_models(self) -> list[str]:
        """Return installed embedding models."""
        return [name for name in self.list_models() if is_embedding_model(name)]

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """Send a chat request. If stream=True, yield text chunks."""
        chosen = model or self.model
        if is_embedding_model(chosen):
            raise OllamaError(
                f"`{chosen}` is an embedding model — it cannot chat.\n\n"
                "In the sidebar, set **Coding model** to a chat model like "
                "`qwen2.5-coder:3b`. Keep `nomic-embed-text` for RAG indexing only."
            )

        options: dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "num_predict": self.num_predict,
        }
        if self.num_ctx is not None:
            options["num_ctx"] = int(self.num_ctx)
        if self.num_thread is not None:
            options["num_thread"] = int(self.num_thread)

        payload: dict[str, Any] = {
            "model": chosen,
            "messages": messages,
            "stream": stream,
            "options": options,
        }
        url = f"{self.base_url}/api/chat"

        try:
            if stream:
                return self._stream_chat(url, payload)
            response = requests.post(url, json=payload, timeout=self.timeout)
            if response.status_code >= 400:
                raise OllamaError(self._error_from_response(response, payload["model"]))
            data = response.json()
            return data.get("message", {}).get("content", "")
        except OllamaError:
            raise
        except requests.RequestException as exc:
            raise OllamaError(self._friendly_error(exc, chosen)) from exc

    def _stream_chat(
        self, url: str, payload: dict[str, Any]
    ) -> Generator[str, None, None]:
        """Yield content tokens as Ollama generates them."""
        try:
            with requests.post(
                url, json=payload, stream=True, timeout=self.timeout
            ) as response:
                if response.status_code >= 400:
                    raise OllamaError(
                        self._error_from_response(response, payload["model"])
                    )
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise OllamaError(str(chunk["error"]))
                    content = chunk.get("message", {}).get("content")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break
        except OllamaError:
            raise
        except requests.RequestException as exc:
            raise OllamaError(
                self._friendly_error(exc, str(payload.get("model", self.model)))
            ) from exc

    @staticmethod
    def _error_from_response(response: requests.Response, model: str) -> str:
        """Turn Ollama HTTP errors into beginner-friendly messages."""
        detail = ""
        try:
            detail = str(response.json().get("error", "")).strip()
        except Exception:
            detail = (response.text or "").strip()

        lowered = detail.lower()
        if "does not support chat" in lowered:
            return (
                f"`{model}` cannot be used for chat (likely an embedding model).\n\n"
                "Pick a coding chat model such as `qwen2.5-coder:3b` in the sidebar."
            )
        if response.status_code == 404 or "not found" in lowered:
            return (
                f"Model `{model}` is not installed yet (Ollama returned 404).\n\n"
                "In PowerShell run:\n"
                f"  ollama pull {model}\n"
                "  ollama pull nomic-embed-text\n\n"
                "Wait until `ollama list` shows the model, then refresh this page."
            )
        if detail:
            return f"Ollama error: {detail}"
        return f"Ollama request failed with HTTP {response.status_code}."

    @staticmethod
    def _friendly_error(exc: Exception, model: str = "qwen2.5-coder:3b") -> str:
        text = str(exc)
        if "Connection" in text or "Failed to establish" in text:
            return (
                "Ollama is not running. Start the Ollama app, then run:\n"
                f"  ollama pull {model}"
            )
        return f"Ollama request failed: {text}"


CODING_SYSTEM_PROMPT = """You are a senior local coding assistant running fully on the user's laptop.
Your job: turn short commands into clear, working code.

Rules:
1. Prefer complete, runnable code over vague advice.
2. Put code in fenced markdown blocks with the language tag (```python, ```javascript, etc.).
3. Briefly explain what the code does after the code block (2–5 sentences).
4. If the request is unclear, ask one short clarifying question.
5. Match the language the user asked for. If none is specified, use Python.
6. Do not invent cloud APIs or paid services unless the user asks.
7. Keep answers focused — no fluff.
8. When PROJECT CONTEXT is provided, use it. Cite file paths you relied on.
9. If context is missing or insufficient, say what is missing instead of guessing project details.
"""


def build_messages(
    user_command: str,
    history: Iterable[dict[str, str]] | None = None,
    context: str | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    """Build the message list sent to the model (system + history + optional RAG context)."""
    system = (system_prompt or "").strip() or CODING_SYSTEM_PROMPT
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system}
    ]
    if history:
        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

    if context and context.strip():
        user_content = (
            "PROJECT CONTEXT (retrieved from the user's local codebase):\n"
            f"{context.strip()}\n\n"
            f"USER REQUEST:\n{user_command}"
        )
    else:
        user_content = user_command

    messages.append({"role": "user", "content": user_content})
    return messages
