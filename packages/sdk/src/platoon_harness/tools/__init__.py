"""The tool plane: an agent's operations as tools, over MCP and `ph`, from one derivation."""

from pathlib import Path

from platoon_harness.kernel import tool_name

from .mcp import ToolServer
from .surface import (
    NAMESPACE,
    OP_NAMED,
    PREAMBLE,
    Surface,
    delivery_heading,
    delivery_text,
    harness_name,
    held_tools,
    instructions,
    list_tools,
    preamble,
    shell_name,
    slots,
    surface_of,
    taught,
)

PH = Path(__file__).with_name("ph.py")
SHIM = Path(__file__).with_name("shim.py")

__all__ = [
    "NAMESPACE",
    "OP_NAMED",
    "PH",
    "PREAMBLE",
    "SHIM",
    "Surface",
    "ToolServer",
    "delivery_heading",
    "delivery_text",
    "harness_name",
    "held_tools",
    "instructions",
    "list_tools",
    "preamble",
    "shell_name",
    "slots",
    "surface_of",
    "taught",
    "tool_name",
]
