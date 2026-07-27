"""Smart natural-language code search: 'Where is login?' etc."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.code_search import search_project
from src.symbols.index import find_symbols

INTENT_KEYWORDS: dict[str, list[str]] = {
    "login": ["login", "signin", "sign_in", "auth", "authenticate", "session"],
    "auth": ["auth", "jwt", "token", "oauth", "permission", "authorize"],
    "database": ["database", "db", "sqlalchemy", "postgres", "mongodb", "connection", "connect"],
    "config": ["config", "settings", "env", "configuration"],
    "api": ["api", "router", "endpoint", "fastapi", "flask", "express", "route"],
    "test": ["test_", "pytest", "unittest", "describe(", "it("],
}


@dataclass
class SmartSearchResult:
    query: str
    intent: str
    keywords: list[str]
    hits: list[str]
    symbols: list[str]
    summary: str


def detect_intent(question: str) -> tuple[str, list[str]]:
    text = (question or "").lower()
    # Strip common NL wrappers
    text = re.sub(r"^(where\s+(is|are)|find|show|locate)\s+", "", text).strip(" ?")
    for intent, keywords in INTENT_KEYWORDS.items():
        if intent in text or any(k in text for k in keywords):
            return intent, keywords
    # Fall back: use meaningful tokens
    tokens = [t for t in re.findall(r"[A-Za-z_][\w]*", text) if len(t) > 2]
    return "general", tokens[:5] or [text]


def smart_search(project_path: str | Path, question: str, limit: int = 25) -> SmartSearchResult:
    intent, keywords = detect_intent(question)
    hits: list[str] = []
    symbol_lines: list[str] = []

    for kw in keywords:
        bundle = search_project(project_path, kw)
        for line in (bundle.context or "").splitlines():
            if line.strip() and line not in hits:
                hits.append(line)
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break

    for sym in find_symbols(project_path, query=keywords[0] if keywords else "", limit=20):
        symbol_lines.append(f"{sym.kind}: {sym.name} @ {sym.path}:{sym.line}")

    summary = (
        f"Intent `{intent}` using keywords {keywords}. "
        f"Found {len(hits)} content hit(s) and {len(symbol_lines)} symbol(s)."
    )
    return SmartSearchResult(
        query=question,
        intent=intent,
        keywords=keywords,
        hits=hits[:limit],
        symbols=symbol_lines[:20],
        summary=summary,
    )


def wants_smart_where(prompt: str) -> bool:
    text = (prompt or "").lower().strip()
    return text.startswith("where is") or text.startswith("where are") or text.startswith(
        "find where"
    )
