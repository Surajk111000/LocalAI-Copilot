"""Simple plugin API — future tools register here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class PluginTool:
    name: str
    description: str
    handler: ToolHandler
    plugin: str


@dataclass
class PluginRegistry:
    """Process-wide registry for optional tools."""

    tools: dict[str, PluginTool] = field(default_factory=dict)

    def register(
        self,
        name: str,
        handler: ToolHandler,
        *,
        description: str = "",
        plugin: str = "custom",
    ) -> None:
        key = name.strip()
        if not key:
            raise ValueError("Tool name required")
        self.tools[key] = PluginTool(
            name=key,
            description=description or key,
            handler=handler,
            plugin=plugin,
        )

    def unregister(self, name: str) -> None:
        self.tools.pop(name, None)

    def list_tools(self) -> list[PluginTool]:
        return list(self.tools.values())

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self.tools.get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown plugin tool: {name}"}
        try:
            result = tool.handler(arguments or {})
            if not isinstance(result, dict):
                return {"ok": True, "result": result}
            return result
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}


# Global default registry
registry = PluginRegistry()


def register_tool(
    name: str,
    handler: ToolHandler,
    *,
    description: str = "",
    plugin: str = "custom",
) -> None:
    registry.register(name, handler, description=description, plugin=plugin)


def example_echo_plugin() -> None:
    """Built-in demo plugin used in tests / developer console."""

    def echo(args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "echo": args.get("text", "")}

    register_tool("echo", echo, description="Echo text (demo plugin)", plugin="demo")
