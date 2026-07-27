"""Tests for chat vs embedding model separation."""

from src.llm.ollama_client import is_chat_model, is_embedding_model


def test_nomic_is_embedding_only() -> None:
    assert is_embedding_model("nomic-embed-text:latest")
    assert not is_chat_model("nomic-embed-text:latest")


def test_qwen_is_chat_model() -> None:
    assert is_chat_model("qwen2.5-coder:3b")
    assert not is_embedding_model("qwen2.5-coder:3b")
