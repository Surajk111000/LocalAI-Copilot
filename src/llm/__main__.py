"""Quick CLI smoke test: python -m src.llm "Write a hello world in Python"."""

from __future__ import annotations

import sys

from src.config import get_ollama_settings
from src.llm.ollama_client import OllamaClient, OllamaError, build_messages


def main() -> None:
    prompt = " ".join(sys.argv[1:]) or "Write a Python hello world function."
    settings = get_ollama_settings()
    client = OllamaClient(
        base_url=settings["base_url"],
        model=settings["model"],
        temperature=settings["temperature"],
        num_predict=settings["num_predict"],
    )

    if not client.is_available():
        print("Ollama is not running. Install from https://ollama.com and start it.")
        sys.exit(1)

    print(f"Model: {client.model}")
    print(f"Prompt: {prompt}\n")
    try:
        for chunk in client.chat(build_messages(prompt), stream=True):
            print(chunk, end="", flush=True)
        print()
    except OllamaError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
