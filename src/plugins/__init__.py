"""Plugin system package."""

from src.plugins.api import PluginRegistry, example_echo_plugin, register_tool, registry

__all__ = ["PluginRegistry", "example_echo_plugin", "register_tool", "registry"]
