"""The `claude` driver on the real binary against FakeModel. Free: a dummy key, an isolated home, and loopback only."""

import asyncio
import fcntl
import json
import os
import shutil
import signal
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    Compacted,
    Delivery,
    DriverError,
    Exited,
    Item,
    ModelCall,
    Ready,
    TurnEnded,
    Usage,
)
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.levels import Conformance, Profile, levels
from platoon_harness.drivers.process import Record
from platoon_harness.runtime.paths import read_running
from platoon_harness.team import AuthProfile
from platoon_harness.testing import NAMESPACE, TOOL, FakeModel, Stall, Text, ToolCall, check_driver
from platoon_harness.testing.model import INPUT_TOKENS, OUTPUT_TOKENS

from ..unit.drivers.support import Heard
from ..unit.runtime.support import in_state, of_type, until

pytestmark = [pytest.mark.slow, pytest.mark.timeout(120)]

BASH = "Bash"
MODEL = "fake-model"
TIMEOUT = 60.0
GATED = ToolCall(BASH, {"command": "touch gated", "description": "needs an approval"}, id="call_gated")
CHILD = ToolCall("Agent", {"description": "a child", "prompt": "say so", "subagent_type": "general-purpose"})


@pytest.fixture(autouse=True)
def binary():
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed, so this driver met no real harness here")


def access(home: Path):
    """How a harness reaches FakeModel, on a dummy key, with a home of its own so that no login takes part."""

    def given(model: FakeModel) -> dict[str, Secret]:
        home.mkdir(exist_ok=True)
        variables = {
            "ANTHROPIC_BASE_URL": model.url,
            "ANTHROPIC_API_KEY": "dummy-key",
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        }
        return {name: Secret(value) for name, value in variables.items()}

    return given


def shell(command: str) -> ToolCall:
    return ToolCall(BASH, {"command": command, "description": "conformance"})


def ours(note: str) -> ToolCall:
    return ToolCall(f"mcp__{NAMESPACE}__{TOOL}", {"note": note})


def garbling(folder: Path):
    """Write into the harness's own stdout, since nothing makes the real binary write a frame no parser knows."""

    async def garble(_: ClaudeDriver) -> None:
        record = Record.read(folder / "malformed_frame_is_a_gap" / "agent")
        assert record is not None
        pipe = os.open(f"/proc/{record.pid}/fd/1", os.O_WRONLY)
        os.write(pipe, b"this is no frame\n" + json.dumps({"type": "nobody knows"}).encode() + b"\n")
        os.close(pipe)

    return garble


async def conformance(folder: Path) -> Conformance:
    return await check_driver(
        ClaudeDriver,
        folder=folder,
        access=access(folder / "home"),
        garble=garbling(folder),
        gated=GATED,
        shell=shell,
        tool=ours,
        child=CHILD,
        timeout=TIMEOUT,
    )


async def test_the_claude_driver_conforms(tmp_path):
    result = await conformance(tmp_path)

    print(result)
    assert result.failed == (), str(result)
    assert result.driver == "claude"
    skipped = {check.name for check in result.checks if check.state == "skipped"}
    assert skipped == {"one_shot_exits", "declared_but_unproven"}
    earned = levels(ClaudeDriver().describe().capabilities, Profile(driver="claude", version=result.version), result)
    assert earned.operational.state == "met", earned.operational.reasons
    assert earned.observable.state == "met", earned.observable.reasons


def keyed(home: Path, model: FakeModel, monkeypatch: pytest.MonkeyPatch, **role: Any) -> Team:
    """One agent on the real binary, reaching FakeModel the way an auth profile would."""
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setenv("ANTHROPIC_BASE_URL", model.url)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    bob = Role(harness="claude", model=MODEL, auth="fake", **role)
    return Team(roles={"bob": bob}, auth={"fake": AuthProfile(env=("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY"))})


async def test_a_real_harness_calls_our_tools_parks_wakes_and_resumes_in_a_session(tmp_path, monkeypatch):
    replies = (
        ToolCall("mcp__ph__peers", id="toolu_peers"),
        ToolCall("mcp__ph__wait", {"from": ["@you"]}, id="toolu_wait"),
        "waiting for you",
        "woken",
        "resumed",
    )

    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, name="real", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "find your peers, then wait for me")
            await in_state(session, "bob", "waiting")

            await session.send("@bob", "carry on, the word is cinnabar")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 2)

            items = await of_type(session, "item.recorded")
            placed = await of_type(session, "wait.registered")
            started = (await of_type(session, "agent.started"))[0]
            assert [event.data["reason"] for event in await of_type(session, "turn.ended")] == ["stopped", "stopped"]
            assert {"toolu_peers", "toolu_wait"} <= {event.data["native_id"] for event in items}
            assert placed[0].native["claudecode/toolUseId"] == "toolu_wait"
            assert started.data["effective_model"] == MODEL
            assert started.data["verified"]["login"] == "key"

        async with Session.resume("real", root=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "what was the word?")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 3)

    assert model.calls[-1].says("cinnabar")
    assert model.calls[0].offers("mcp__ph__wait")


async def test_a_real_harness_finishes_with_its_turn(tmp_path, monkeypatch):
    replies = (ToolCall("mcp__ph__agent_finish", {"gist": "all done"}, id="toolu_finish"), "that is all")

    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "finish")
            await in_state(session, "bob", "ended")
            ending = await session.ending()

    assert ending.agents[0]["status"] == "finished"
    assert ending.agents[0]["report"]["gist"] == "all done"


async def test_a_turn_the_owner_stopped_is_told_on_resume_and_the_harness_goes_on(tmp_path, monkeypatch):
    async with FakeModel([Stall(), Text("never heard")], "understood") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, name="stopped", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "think for a long time")
            await asyncio.wait_for(model.call(0), TIMEOUT)

        async with Session.resume("stopped", root=tmp_path) as session:
            ended = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)

    assert [event.data["reason"] for event in ended] == ["stopped by its owner", "stopped"]
    assert model.calls[-1].says("the owner stopping the session")


def taken_twice(finished: list[Any]) -> bool:
    """Whether a wake and a steer have both been handed over."""
    return len([event for event in finished if event.data["kind"] == "deliver"]) == 2


async def test_a_steer_an_interrupt_cut_off_is_offered_again_and_reaches_the_model(tmp_path, monkeypatch):
    async with FakeModel([Stall()], "the next turn") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, delivery="steer")

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await asyncio.wait_for(model.call(0), TIMEOUT)
            await session.send("@bob", "the word is cinnabar")
            await until(lambda: of_type(session, "effect.finished"), session, taken_twice)
            await session.interrupt("@bob")
            ended = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)

    assert [event.data["reason"] for event in ended] == ["interrupted", "stopped"]
    assert model.calls[1].message.body.decode().count("cinnabar") == 1


def let_go(folder: Path) -> None:
    """Wait for a dead runtime's lock, which outlives its signal by a moment."""
    with (folder / "lock").open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)


async def test_a_steer_the_harness_took_and_never_landed_survives_a_killed_runtime(tmp_path, monkeypatch):
    async with FakeModel([Stall()], "noted") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, delivery="steer")
        guest = await Session.start(team, name="crash", root=tmp_path, cwd=tmp_path, detach=True)
        await in_state(guest, "bob", "idle")
        await guest.send("@bob", "go")
        await asyncio.wait_for(model.call(0), TIMEOUT)
        await guest.send("@bob", "the word is cinnabar")
        await until(lambda: of_type(guest, "effect.finished"), guest, taken_twice)
        running = read_running(guest.folder)
        assert running is not None
        os.kill(running.pid, signal.SIGKILL)
        await guest.leave()
        await asyncio.to_thread(let_go, guest.folder)

        async with Session.resume("crash", root=tmp_path) as session:
            await until(lambda: of_type(session, "turn.ended"), session)
            offers = await of_type(session, "context.offered")

    assert model.calls[-1].says("cinnabar")
    assert "inbox/bob@2" in [item["ref"] for item in offers[-1].data["items"]]


def on_fake_model(tmp_path: Path, fake: FakeModel, **fields: Any) -> AgentSpec:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    spec = {"agent": "ada", "role": "worker", "goal": "", "cwd": work, "folder": tmp_path / "ada", "model": MODEL}
    return AgentSpec.model_validate({**spec, "access": access(tmp_path / "home")(fake), **fields})


async def test_a_resumed_harness_knows_what_landed_after_a_kill(tmp_path):
    delivery = Delivery(input="41", boundary="turn", text="remember heliotrope", items=())

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model)
        first, heard = ClaudeDriver(), Heard()
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await first.deliver(delivery)
        await heard.until(TurnEnded)
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, signal.SIGKILL)
        await heard.until(Exited)
        await first.stop(2.0)

        second, heard = ClaudeDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        try:
            assert await second.reconcile("41") == "landed"
            assert await second.reconcile("42") == "unknown"
        finally:
            await second.stop(2.0)


async def test_a_compaction_reports_its_summary_and_its_model_call(tmp_path):
    delivery = Delivery(input="41", boundary="turn", text="/compact", items=())

    async with FakeModel("one", "<summary>the summary</summary>") as model:
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="say one"), heard)
        await heard.until(TurnEnded)
        try:
            await driver.deliver(delivery)
            compacted = await heard.until(Compacted)
            called = await heard.until(ModelCall, lambda call: call.purpose == "compaction")
            await heard.until(TurnEnded, lambda _: len(heard.of(TurnEnded)) == 2)
        finally:
            await driver.stop(2.0)

    assert compacted.forgotten is None
    assert compacted.summary is not None and "the summary" in compacted.summary
    assert called.call_id is None
    assert sum(usage.tokens or 0 for usage in heard.of(Usage)) == len(model.calls) * (INPUT_TOKENS + OUTPUT_TOKENS)


async def test_effort_reaches_the_model_and_one_the_harness_would_drop_is_refused(tmp_path):
    async with FakeModel("ok") as model:
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go", effort="low"), heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

        refused = ClaudeDriver()
        with pytest.raises(DriverError, match="bogus was asked for"):
            await refused.start(on_fake_model(tmp_path, model, effort="bogus"), Heard())
        await refused.stop(2.0)

    assert model.calls[0].json["output_config"]["effort"] == "low"


async def test_with_no_model_on_a_login_of_its_own_ready_says_the_harness_s_default(tmp_path):
    async with FakeModel() as model:
        given = {name: secret.reveal() for name, secret in access(tmp_path / "home")(model).items()}
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, model=None, access={}, env=given), heard)
        ready = await heard.until(Ready)
        await driver.stop(2.0)

    assert ready.effective_model is not None
    assert not model.calls


async def test_a_harness_signed_in_nowhere_says_so_when_its_turn_ends(tmp_path):
    variables = {"HOME": str(tmp_path / "home"), "CLAUDE_CONFIG_DIR": str(tmp_path / "home" / ".claude")}
    (tmp_path / "home").mkdir()

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model, access={}, env=variables, goal="go")
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(spec, heard)
        ended = await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert "Not logged in" in ended.reason
    assert not [item for item in heard.of(Item) if item.call_id is not None]
