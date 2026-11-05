"""What proves a driver or an extension: a deterministic harness, a loopback model, and named checks."""

from .conformance import chat_access, check_driver, goal
from .extension import check_extension
from .harnesses import check_harness
from .model import FakeModel, Request, Stall, Text, Thought, ToolCall
from .scripted import (
    SHELL,
    Ask,
    AskModel,
    Call,
    EndTurn,
    Exit,
    Fail,
    Hang,
    Say,
    ScriptedDriver,
    Think,
    Wait,
    every_turn_asks_the_model,
)
from .tools import NAMESPACE, TOOL, FakeTools

__all__ = [
    "NAMESPACE",
    "SHELL",
    "TOOL",
    "Ask",
    "AskModel",
    "Call",
    "EndTurn",
    "Exit",
    "Fail",
    "FakeModel",
    "FakeTools",
    "Hang",
    "Request",
    "Say",
    "ScriptedDriver",
    "Stall",
    "Text",
    "Think",
    "Thought",
    "ToolCall",
    "Wait",
    "chat_access",
    "check_driver",
    "check_extension",
    "check_harness",
    "every_turn_asks_the_model",
    "goal",
]
