"""What each real harness sends a model across a tool call, a wake and a resume, on FakeModel. Free: dummy keys, an
isolated home, and loopback only. Tool block stability is a measurement to take, so this states one. Each skips where
its binary is not installed. OpenHands is no binary, and the dev environment holds the SDK's `openhands` extra."""

import hashlib
import json
import shutil
from collections.abc import Callable
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.testing import FakeModel, ToolCall
from platoon_harness.testing.model import Request

from ..unit.runtime import support
from ..unit.runtime.support import in_state, of_type, until
from . import test_claude, test_codex, test_openhands, test_pi

pytestmark = [pytest.mark.slow, pytest.mark.timeout(120)]

MARK = "the fourth word is celadon"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()[:8]


def system_of(request: Request) -> Any:
    """The system prompt in each dialect's shape, which on Claude Code holds a fresh header per request."""
    body = request.json
    if "system" in body:
        return [block for block in body["system"] if "x-anthropic-billing-header" not in block.get("text", "")]
    return [item for item in body.get("input", body.get("messages")) if item.get("role") in ("system", "developer")]


def wait_call(harness: str) -> ToolCall:
    arguments = {"from": ["@you"]}
    if harness == "codex":
        return ToolCall("wait", arguments, id="call_wait", namespace="mcp__ph")
    if harness == "openhands":
        return ToolCall("wait", arguments, id="call_wait")
    return ToolCall("mcp__ph__wait", arguments, id="toolu_wait")


TEAMS: dict[str, Callable[..., Team]] = {
    "claude": test_claude.keyed,
    "codex": test_codex.keyed,
    "pi": test_pi.keyed,
    "openhands": test_openhands.keyed,
}


@pytest.mark.parametrize("harness", TEAMS)
async def test_the_tool_block_and_our_words_hold_still_across_a_wake_and_a_resume(harness, tmp_path, monkeypatch):
    if harness != "openhands" and shutil.which(harness) is None:
        pytest.skip(f"{harness} is not installed, so this met no real harness here")
    monkeypatch.setattr(support, "SECONDS", test_openhands.TIMEOUT)  # The OpenHands worker loads its SDK first.
    replies = (wait_call(harness), "waiting for you", "woken", "resumed")

    async with FakeModel(*replies) as model:
        team = TEAMS[harness](tmp_path / "home", model, monkeypatch)
        role = team.roles["bob"].model_copy(update={"instructions": MARK})
        team = team.model_copy(update={"roles": {"bob": role}})

        async with Session.start(team, name="shape", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "wait for me")
            await in_state(session, "bob", "waiting")
            await session.send("@bob", "carry on")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 2)

        async with Session.resume("shape", root=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "one more")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 3)

    calls = [request for request in model.calls if request.json.get("tools")]
    tools = [digest(request.json["tools"]) for request in calls]
    system = [digest(system_of(request)) for request in calls]
    size = len(json.dumps(calls[0].json["tools"]))
    words = [request.message.body.decode().count(MARK) for request in calls]
    others = len(model.calls) - len(calls)
    print(f"{harness}: {len(calls)} requests with tools, {others} without, {size} bytes of tools")
    print(f"{harness}: tools {tools}, system {system}, our words per request {words}")
    assert len(set(tools)) == 1, tools
    assert set(words) == {1}, words
