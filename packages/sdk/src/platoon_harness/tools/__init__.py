"""The tool plane: an agent's operations as tools, over MCP and `ph`, from one derivation."""

from pathlib import Path

from platoon_harness.kernel import tool_name

from .mcp import ToolServer
from .surface import Surface, delivery_text, harness_name, held_tools, list_tools, preamble, shell_name

PH = Path(__file__).with_name("ph.py")
SHIM = Path(__file__).with_name("shim.py")

__all__ = [
    "PH",
    "SHIM",
    "Surface",
    "ToolServer",
    "delivery_text",
    "harness_name",
    "held_tools",
    "list_tools",
    "preamble",
    "shell_name",
    "tool_name",
]
