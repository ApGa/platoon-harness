"""The tool plane: an agent's operations as tools, over MCP and `ph`, from one derivation."""

from pathlib import Path

from .mcp import ToolServer
from .surface import Surface, harness_name, list_tools, preamble, shell_name, tool_name

PH = Path(__file__).with_name("ph.py")
SHIM = Path(__file__).with_name("shim.py")

__all__ = [
    "PH",
    "SHIM",
    "Surface",
    "ToolServer",
    "harness_name",
    "list_tools",
    "preamble",
    "shell_name",
    "tool_name",
]
