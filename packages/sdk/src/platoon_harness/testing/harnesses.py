"""`check_harness`: `check_driver` on a harness the SDK drives, as installed here, against FakeModel and on no account.

Each harness reaches the model through a home of the check's own, so no login of the person running it takes part,
and is given what makes it run its shell, ask an approval, call our tool by the name its model knows, start a native
child where it has them, and write a frame no parser knows. `doctor --check` runs this, and so do the slow suites.
"""

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from platoon_harness.config import Secret
from platoon_harness.drivers import DriverError
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.codex import CodexDriver
from platoon_harness.drivers.levels import Conformance
from platoon_harness.drivers.openhands import OpenHandsDriver
from platoon_harness.drivers.pi import PiDriver
from platoon_harness.drivers.process import Record

from .conformance import Access, Factory, Garble, chat_access, check_driver
from .model import FakeModel, ToolCall
from .tools import NAMESPACE, TOOL

MODEL = "fake-model"
"""The model every check asks for, which FakeModel answers as."""

_PI_OFFLINE = "PI_OFFLINE"
_PI_PRICE = {"input": 1.0, "output": 2.0, "cacheRead": 0.0, "cacheWrite": 0.0}
_ESCALATED = {"sandbox_permissions": "require_escalated", "justification": "needs an approval"}

__all__ = ["check_harness"]


def _home(folder: Path) -> Path:
    home = folder / "home"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _garbling(folder: Path, frame: dict[str, Any]) -> Garble | None:
    """Write into the harness's own stdout, since nothing makes a real one write a frame no parser knows. Only Linux
    lets one process write to another's descriptor by its path, so elsewhere that check is skipped."""
    if sys.platform != "linux":
        return None

    async def garble(_: Any) -> None:
        record = Record.read(folder / "malformed_frame_is_a_gap" / "agent")
        assert record is not None
        pipe = os.open(f"/proc/{record.pid}/fd/1", os.O_WRONLY)
        os.write(pipe, b"this is no frame\n" + json.dumps(frame).encode() + b"\n")
        os.close(pipe)

    return garble


def _claude(folder: Path) -> dict[str, Any]:
    def access(model: FakeModel) -> dict[str, Secret]:
        home = _home(folder)
        variables = {
            "ANTHROPIC_BASE_URL": model.url,
            "ANTHROPIC_API_KEY": "dummy-key",
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        }
        return {name: Secret(value) for name, value in variables.items()}

    def bash(id: str = "call_1") -> Callable[[str], ToolCall]:
        return lambda command: ToolCall("Bash", {"command": command, "description": "conformance"}, id=id)

    return {
        "access": access,
        "garble": _garbling(folder, {"type": "nobody knows"}),
        "gated": bash("call_gated"),
        "shell": bash(),
        "tool": lambda note: ToolCall(f"mcp__{NAMESPACE}__{TOOL}", {"note": note}),
        "child": ToolCall("Agent", {"description": "a child", "prompt": "say so", "subagent_type": "general-purpose"}),
        "timeout": 60.0,
    }


def _codex(folder: Path) -> dict[str, Any]:
    def access(model: FakeModel) -> dict[str, Secret]:
        home = _home(folder)
        (home / ".codex").mkdir(exist_ok=True)
        (home / ".codex" / "config.toml").write_text("")
        return {**chat_access(model), "HOME": Secret(str(home)), "CODEX_HOME": Secret(str(home / ".codex"))}

    return {
        "access": access,
        "garble": _garbling(folder, {"method": "nobody/knows"}),
        "gated": lambda command: ToolCall("exec_command", {"cmd": command, **_ESCALATED}, id="call_gated"),
        "shell": lambda command: ToolCall("exec_command", {"cmd": command}),
        "tool": lambda note: ToolCall(TOOL, {"note": note}, namespace=f"mcp__{NAMESPACE}"),
        "child": ToolCall("spawn_agent", {"message": "say so"}, id="call_child", namespace="multi_agent_v1"),
        "timeout": 60.0,
    }


def _pi_setup(home: Path, model: FakeModel) -> None:
    """A pi agent directory of its own: a provider reaching `model`, with a price and a login held in `auth.json`."""
    agent = home / ".pi" / "agent"
    agent.mkdir(parents=True, exist_ok=True)
    listed = {"id": MODEL, "contextWindow": 100_000, "maxTokens": 1_000, "cost": _PI_PRICE}
    provider = {"baseUrl": f"{model.url}/v1", "api": "openai-completions", "models": [listed]}
    (agent / "models.json").write_text(json.dumps({"providers": {"fake": provider}}))
    (agent / "auth.json").write_text(json.dumps({"fake": {"type": "api_key", "key": "dummy-login"}}))
    (agent / "settings.json").write_text(json.dumps({"defaultProvider": "fake", "defaultModel": MODEL}))


def _pi(folder: Path) -> dict[str, Any]:
    def access(model: FakeModel) -> dict[str, Secret]:
        home = _home(folder)
        _pi_setup(home, model)
        return {"HOME": Secret(str(home)), _PI_OFFLINE: Secret("yes")}

    return {
        "access": access,
        "garble": _garbling(folder, {"type": "nobody_knows"}),
        "gated": lambda command: ToolCall("bash", {"command": command}, id="call_gated"),
        "shell": lambda command: ToolCall("bash", {"command": command}),
        "tool": lambda note: ToolCall(f"mcp__{NAMESPACE}__{TOOL}", {"note": note}),
        "timeout": 60.0,
    }


def _openhands(folder: Path) -> dict[str, Any]:
    def access(model: FakeModel) -> dict[str, Secret]:
        return {**chat_access(model), "HOME": Secret(str(_home(folder)))}

    def terminal(command: str) -> ToolCall:
        return ToolCall("terminal", {"command": command}, id="call_gated")

    task = {"description": "make it", "prompt": "Make the file.", "subagent_type": "general-purpose"}
    return {
        "access": access,
        "garble": _garbling(folder, {"jsonrpc": "2.0", "method": "nobody_knows"}),
        "gated": terminal,
        "shell": terminal,
        "child": ToolCall("task", task),
        "timeout": 90.0,
    }


_HARNESSES: dict[str, tuple[Factory, Callable[[Path], dict[str, Any]]]] = {
    "claude": (ClaudeDriver, _claude),
    "codex": (CodexDriver, _codex),
    "pi": (PiDriver, _pi),
    "openhands": (OpenHandsDriver, _openhands),
}
"""Each harness `check_harness` knows how to check: its driver, and what the checks give it."""


async def check_harness(name: str, folder: Path) -> Conformance:
    """Run every check on the harness `name` as it is installed here, against FakeModel, in `folder`, and say what it
    found, pinned to the driver and the harness version that answered. A harness no check ships for is refused."""
    if name not in _HARNESSES:
        raise DriverError(f"no check of {name} ships with the SDK: run `check_driver` on its driver")
    factory, given = _HARNESSES[name]
    options: dict[str, Any] = given(folder)
    access: Access = options.pop("access")
    return await check_driver(factory, folder=folder, access=access, **options)
