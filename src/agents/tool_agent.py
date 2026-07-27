"""Tool-using coding agent for local models.

Small models are uneven with native function-calling APIs, so we use a simple
text protocol: the model emits a <tool_call> JSON block when it needs a tool.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.llm.ollama_client import OllamaClient, OllamaError
from src.tools.filesystem import FileSystemTools, PendingWrite, ToolResult

TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)

TOOLS_SYSTEM_PROMPT = """You are a local coding agent with filesystem tools.
You work ONLY inside the user's selected project folder.

When you need information or want to change a file, emit EXACTLY one tool call:

<tool_call>
{"name": "TOOL_NAME", "arguments": {...}}
</tool_call>

Available tools:
1) list_directory — arguments: {"path": "."}
2) read_file — arguments: {"path": "relative/path.py"}
3) search_files — arguments: {"query": "text", "path": "."}
4) write_file — arguments: {"path": "relative/path.py", "content": "full file content"}
   NOTE: write_file needs user approval before disk changes.

Rules:
- Prefer tools over guessing project details.
- Use relative paths from the project root.
- After tool results arrive, continue until you can answer.
- When finished, reply in normal markdown with code blocks. Do NOT emit tool_call then.
- For write_file, include the FULL file content you want saved.
- Keep answers concise and cite paths you used.
"""


@dataclass
class AgentResult:
    answer: str
    tool_trace: list[str] = field(default_factory=list)
    pending_writes: list[PendingWrite] = field(default_factory=list)
    error: str | None = None


class ToolAgent:
    """Run a short ReAct-style loop: think → tool → observe → answer."""

    def __init__(
        self,
        client: OllamaClient,
        tools: FileSystemTools,
        *,
        max_steps: int = 4,
    ) -> None:
        self.client = client
        self.tools = tools
        self.max_steps = max_steps

    def run(
        self,
        user_command: str,
        *,
        history: list[dict[str, str]] | None = None,
        context: str | None = None,
    ) -> AgentResult:
        messages = self._build_messages(user_command, history=history, context=context)
        trace: list[str] = []
        pending_writes: list[PendingWrite] = []

        try:
            for step in range(self.max_steps):
                raw = self.client.chat(messages, stream=False)
                assert isinstance(raw, str)
                tool_call = self._parse_tool_call(raw)

                if not tool_call:
                    # Final natural-language answer
                    return AgentResult(
                        answer=raw.strip(),
                        tool_trace=trace,
                        pending_writes=pending_writes,
                    )

                name = str(tool_call.get("name", "")).strip()
                arguments = tool_call.get("arguments") or {}
                if not isinstance(arguments, dict):
                    arguments = {}

                result = self.tools.run(name, arguments)
                trace.append(self._format_trace(name, arguments, result))
                if result.pending_write is not None:
                    pending_writes.append(result.pending_write)

                # Keep the conversation going with the tool observation
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"TOOL RESULT ({name}):\n{result.output}\n\n"
                            "Continue. If you need another tool, emit another "
                            "<tool_call>. Otherwise give the final answer."
                        ),
                    }
                )

            # Max steps hit — ask once more for a final answer without tools
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Max tool steps reached. Give your best final answer now "
                        "in markdown. Do not emit tool_call."
                    ),
                }
            )
            final = self.client.chat(messages, stream=False)
            assert isinstance(final, str)
            return AgentResult(
                answer=final.strip(),
                tool_trace=trace,
                pending_writes=pending_writes,
            )
        except OllamaError as exc:
            return AgentResult(answer="", tool_trace=trace, error=str(exc))

    @staticmethod
    def _build_messages(
        user_command: str,
        history: list[dict[str, str]] | None = None,
        context: str | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": TOOLS_SYSTEM_PROMPT}
        ]
        if history:
            for item in history[-6:]:  # keep prompt small for 3B/7B models
                role = item.get("role")
                content = item.get("content")
                if role in {"user", "assistant"} and content:
                    messages.append({"role": role, "content": content})

        parts = [f"USER REQUEST:\n{user_command}"]
        if context and context.strip():
            parts.insert(
                0,
                "PROJECT CONTEXT (retrieved snippets):\n" + context.strip(),
            )
        messages.append({"role": "user", "content": "\n\n".join(parts)})
        return messages

    @staticmethod
    def _parse_tool_call(text: str) -> dict[str, Any] | None:
        match = TOOL_CALL_RE.search(text or "")
        if not match:
            return None
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or "name" not in data:
            return None
        return data

    @staticmethod
    def _format_trace(name: str, arguments: dict, result: ToolResult) -> str:
        # Avoid dumping huge write contents into the UI trace
        preview_args = dict(arguments)
        if "content" in preview_args:
            content = str(preview_args["content"])
            preview_args["content"] = f"<{len(content)} chars>"
        status = "ok" if result.ok else "error"
        return f"{name}({preview_args}) → {status}: {result.output[:300]}"
