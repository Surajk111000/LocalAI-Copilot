"""Export chat sessions to Markdown / JSON / HTML (PDF-ready)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def export_markdown(messages: list[dict[str, Any]], title: str = "Chat export") -> str:
    lines = [f"# {title}", "", f"_Exported {_stamp()} UTC_", ""]
    for msg in messages:
        role = str(msg.get("role") or "unknown").upper()
        content = str(msg.get("content") or "")
        lines.append(f"## {role}")
        lines.append("")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def export_json(messages: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> str:
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta or {},
        "messages": messages,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def export_html(messages: list[dict[str, Any]], title: str = "Chat export") -> str:
    """HTML suitable for browser Print → Save as PDF."""
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{title}</title>",
        "<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:860px;"
        "margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "h1{border-bottom:1px solid #ccc} .role{color:#555;font-size:.85rem}"
        "pre{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:8px}"
        "@media print{body{margin:0}}</style></head><body>",
        f"<h1>{title}</h1>",
        f"<p>Exported {_stamp()} UTC — use Print → Save as PDF for a PDF copy.</p>",
    ]
    for msg in messages:
        role = str(msg.get("role") or "")
        content = (
            str(msg.get("content") or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        parts.append(f"<div class='role'><strong>{role}</strong></div>")
        parts.append(f"<pre>{content}</pre>")
    parts.append("</body></html>")
    return "\n".join(parts)


def write_export(
    project_path: str | Path,
    messages: list[dict[str, Any]],
    fmt: str,
    *,
    title: str = "Chat export",
) -> Path:
    root = Path(project_path).expanduser().resolve()
    out_dir = root / ".copilot_exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower().strip()
    stamp = _stamp()
    if fmt == "markdown" or fmt == "md":
        path = out_dir / f"chat_{stamp}.md"
        path.write_text(export_markdown(messages, title), encoding="utf-8")
    elif fmt == "json":
        path = out_dir / f"chat_{stamp}.json"
        path.write_text(export_json(messages, {"title": title}), encoding="utf-8")
    elif fmt in {"html", "pdf"}:
        # PDF = HTML print-ready export (no heavy PDF dependency)
        path = out_dir / f"chat_{stamp}.html"
        path.write_text(export_html(messages, title), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported export format: {fmt}")
    return path
