"""Create vector embeddings using a local Ollama embedding model."""

from __future__ import annotations

from typing import Sequence

import requests

from src.llm.ollama_client import OllamaError


class OllamaEmbedder:
    """Turn text into numbers (vectors) via Ollama's /api/embeddings endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def embed(self, text: str) -> list[float]:
        """Embed a single string."""
        vectors = self.embed_batch([text])
        return vectors[0]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed many strings. Ollama's classic API is one-at-a-time; we loop."""
        results: list[list[float]] = []
        for text in texts:
            payload = {"model": self.model, "prompt": text}
            try:
                response = requests.post(
                    f"{self.base_url}/api/embeddings",
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                vector = data.get("embedding")
                if not vector:
                    raise OllamaError(
                        f"No embedding returned. Pull the model with:\n"
                        f"  ollama pull {self.model}"
                    )
                results.append(vector)
            except requests.RequestException as exc:
                raise OllamaError(
                    "Failed to create embeddings. Is Ollama running?\n"
                    f"Also run: ollama pull {self.model}\n"
                    f"Details: {exc}"
                ) from exc
        return results
