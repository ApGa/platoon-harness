"""The check `platoon-harness doctor --check` runs on OpenCode: `check_driver` on it as installed here, against
FakeModel, in a home of the check's own and on no account.

What it gives OpenCode no run has shown (RFC 0072): the provider's shape, the rule that has its shell ask first and the
name its model knows its shell by, from a probe of 2.2.5 against another fake server and the 2.2.6 release's files. It
calls our tool by the name the driver declares and our words use, `mcp__<namespace>__<tool>`, so that it fails where
OpenCode's model knows our tool by another.
"""

import json
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from platoon_harness.config import Secret
from platoon_harness.drivers.levels import Conformance
from platoon_harness.drivers.process import Record
from platoon_harness.testing import NAMESPACE, TOOL, FakeModel, ToolCall, check_driver

from .opencode import OpenCodeDriver

_PROVIDER = "fake"
_NAME = "fake-model"
MODEL = f"{_PROVIDER}/{_NAME}"
"""What a role names FakeModel by on OpenCode, which names a model by its provider: OpenCode asks FakeModel for
`fake-model`."""
_SHELL = "shell"
_QUIET = {"OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_MODELS_FETCH": "1"}
"""What keeps OpenCode off the network but for FakeModel: no update and no catalogue of models fetched."""

__all__ = ["MODEL", "opencode"]


def _config(model: FakeModel) -> str:
    """OpenCode's configuration, given whole in `OPENCODE_CONFIG_CONTENT`: a provider of its own that reaches `model` on
    a dummy key, and a rule that has every shell command ask first, as with no rule OpenCode asks nothing."""
    listed = {
        _NAME: {
            "capabilities": {"tools": True},
            "limit": {"context": 100_000, "output": 1_000},
        }
    }
    settings = {"baseURL": f"{model.url}/v1", "apiKey": "dummy-key"}
    provider = {"package": "@ai-sdk/openai-compatible", "settings": settings, "models": listed}
    ask = [{"action": _SHELL, "resource": "*", "effect": "ask"}]
    return json.dumps({"model": MODEL, "providers": {_PROVIDER: provider}, "permissions": ask})


def _garbling(folder: Path) -> Callable[[Any], Awaitable[None]] | None:
    """Write into OpenCode's own stdout, as nothing makes it write a frame no parser knows. Only Linux lets one process
    write to another's descriptor by its path, so elsewhere that check is skipped."""
    if sys.platform != "linux":
        return None

    async def garble(_: Any) -> None:
        record = Record.read(folder / "malformed_frame_is_a_gap" / "agent")
        assert record is not None
        pipe = os.open(f"/proc/{record.pid}/fd/1", os.O_WRONLY)
        try:
            os.write(pipe, b"this is no frame\n")
        finally:
            os.close(pipe)

    return garble


def _shell(command: str, id: str | None = None) -> ToolCall:
    return ToolCall(_SHELL, {"command": command, "description": "conformance"}, id=id)


async def opencode(folder: Path) -> Conformance:
    """Run every check on OpenCode, as installed here, in `folder`, against FakeModel, on a home of the check's own."""
    home = folder / "home"

    def access(model: FakeModel) -> dict[str, Secret]:
        home.mkdir(parents=True, exist_ok=True)
        variables = {"HOME": str(home), "OPENCODE_CONFIG_CONTENT": _config(model), **_QUIET}
        return {name: Secret(value) for name, value in variables.items()}

    return await check_driver(
        OpenCodeDriver,
        folder=folder,
        access=access,
        garble=_garbling(folder),
        gated=lambda command: _shell(command, "call_gated"),
        shell=_shell,
        tool=lambda note: ToolCall(f"mcp__{NAMESPACE}__{TOOL}", {"note": note}),
        model=MODEL,
        timeout=60.0,
    )
