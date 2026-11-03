"""The `pi` driver on the real binary against FakeModel. Free: a dummy key, an isolated home, and loopback only.

Pi has no login here and has met no real model through this driver: all of this is what the binary did on FakeModel.
"""

import asyncio
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
    ApprovalRequested,
    Compacted,
    Delivery,
    DriverError,
    Exited,
    GapReport,
    InputDelivered,
    Item,
    ModelCall,
    Native,
    Ready,
    TurnEnded,
    TurnStarted,
    Usage,
)
from platoon_harness.drivers.levels import Conformance, Profile, levels
from platoon_harness.drivers.pi import PiDriver
from platoon_harness.drivers.process import Record
from platoon_harness.team import AuthProfile
from platoon_harness.testing import (
    NAMESPACE,
    TOOL,
    FakeModel,
    FakeTools,
    Stall,
    Text,
    ToolCall,
    chat_access,
    check_driver,
)
from platoon_harness.testing.loopback import answer
from platoon_harness.testing.model import INPUT_TOKENS, OUTPUT_TOKENS
from platoon_harness.tools import PREAMBLE, delivery_heading

from ..unit.drivers.support import Heard, running
from ..unit.runtime.support import in_state, of_type, until
from . import clients
from .scripts import TOLD, following_up, strings

pytestmark = [pytest.mark.slow, pytest.mark.timeout(120)]

MODEL = "fake-model"
PINNED = "1.5.0"
OFFLINE = "PI_OFFLINE"  # What a test asks of pi, as tests reach no network. A user's pi is left to reach its own.
TIMEOUT = 60.0
BASH = "bash"
PRICE = {"input": 1.0, "output": 2.0, "cacheRead": 0.0, "cacheWrite": 0.0}


@pytest.fixture(autouse=True)
def binary():
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed, so this driver met no real harness here")


def own_setup(home: Path, model: FakeModel, **settings: Any) -> None:
    """A user's agent directory: a provider of theirs, with a price, a login held in `auth.json` and their settings."""
    agent = home / ".pi" / "agent"
    agent.mkdir(parents=True, exist_ok=True)
    listed = {"id": MODEL, "contextWindow": 100_000, "maxTokens": 1_000, "cost": PRICE}
    provider = {"baseUrl": f"{model.url}/v1", "api": "openai-completions", "models": [listed]}
    (agent / "models.json").write_text(json.dumps({"providers": {"fake": provider}}))
    (agent / "auth.json").write_text(json.dumps({"fake": {"type": "api_key", "key": "dummy-login"}}))
    (agent / "settings.json").write_text(json.dumps({"defaultProvider": "fake", "defaultModel": MODEL, **settings}))


def access(home: Path):
    """How a harness reaches FakeModel: through a home of its own, so that no login of the person running this takes
    part. Naming `HOME` is access, as an auth profile's is."""

    def given(model: FakeModel) -> dict[str, Secret]:
        own_setup(home, model)
        return {"HOME": Secret(str(home)), OFFLINE: Secret("yes")}

    return given


def shell(command: str) -> ToolCall:
    return ToolCall(BASH, {"command": command})


def gated(command: str) -> ToolCall:
    return ToolCall(BASH, {"command": command}, id="call_gated")


def ours(note: str) -> ToolCall:
    return ToolCall(f"mcp__{NAMESPACE}__{TOOL}", {"note": note})


def garbling(folder: Path):
    """Write into the harness's own stdout, since nothing makes the real binary write a frame no parser knows."""

    async def garble(_: PiDriver) -> None:
        record = Record.read(folder / "malformed_frame_is_a_gap" / "agent")
        assert record is not None
        pipe = os.open(f"/proc/{record.pid}/fd/1", os.O_WRONLY)
        os.write(pipe, b"this is no frame\n" + json.dumps({"type": "nobody_knows"}).encode() + b"\n")
        os.close(pipe)

    return garble


async def conformance(folder: Path) -> Conformance:
    return await check_driver(
        PiDriver,
        folder=folder,
        access=access(folder / "home"),
        garble=garbling(folder),
        gated=gated,
        shell=shell,
        tool=ours,
        timeout=TIMEOUT,
    )


async def test_the_pi_driver_conforms(tmp_path):
    result = await conformance(tmp_path)

    print(result)
    assert result.failed == (), str(result)
    assert (result.driver, result.version) == ("pi", PINNED)
    skipped = {check.name for check in result.checks if check.state == "skipped"}
    assert skipped == {
        "tool_item_carries_its_anchor",
        "native_children_off_by_default",
        "native_child_seen",
        "one_shot_exits",
        "declared_but_unproven",
    }
    earned = levels(PiDriver().describe().capabilities, Profile(driver="pi", version=result.version), result)
    assert earned.operational.state == "met", earned.operational.reasons
    assert earned.observable.state == "met", earned.observable.reasons


def on_fake_model(tmp_path: Path, fake: FakeModel, *, settings: Any = None, **fields: Any) -> AgentSpec:
    """An agent in a user's own setup, in a home of its own, with `HOME` as its access."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    home = tmp_path / "home"
    own_setup(home, fake, **(settings or {}))
    spec = {"agent": "ada", "role": "worker", "goal": "", "cwd": work, "folder": tmp_path / "ada", "model": MODEL}
    return AgentSpec.model_validate({**spec, "access": {"HOME": Secret(str(home))}, "env": {OFFLINE: "1"}, **fields})


def tool(name: str, id: str, **arguments: Any) -> ToolCall:
    return ToolCall(f"mcp__ph__{name}", arguments, id=id)


def keyed(home: Path, model: FakeModel, monkeypatch: pytest.MonkeyPatch, **role: Any) -> Team:
    """One agent on the real binary, reaching FakeModel the way an auth profile would."""
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENAI_BASE_URL", f"{model.url}/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    monkeypatch.setenv(OFFLINE, "yes")
    bob = Role(harness="pi", model=MODEL, auth="fake", **role)
    return Team(roles={"bob": bob}, auth={"fake": AuthProfile(env=("OPENAI_BASE_URL", "OPENAI_API_KEY", OFFLINE))})


def their_extension(home: Path, source: str) -> None:
    folder = home / ".pi" / "agent" / "extensions"
    folder.mkdir(exist_ok=True)
    (folder / "theirs.js").write_text(source)


async def test_a_login_settings_and_extensions_of_the_user_s_stay_theirs(tmp_path):
    """The supported way: our server comes in through `-e`, so pi keeps its own agent directory, and nothing there is
    written by us."""
    async with FakeModel() as model, FakeTools() as tools:
        spec = on_fake_model(tmp_path, model, goal="go", model=None, access={}, tools=tools.binding(tmp_path))
        spec = spec.model_copy(update={"env": {"HOME": str(tmp_path / "home")}})
        agent = tmp_path / "home" / ".pi" / "agent"
        their_extension(
            tmp_path / "home",
            "export default (pi) => pi.registerTool({ name: 'their_tool', label: 'theirs', description: 'theirs',"
            " parameters: { type: 'object', properties: {} }, execute: async () => ({ content: [], details: {} }) });",
        )
        (agent / "mcp.json").write_text(json.dumps({"mcpServers": {"their_server": {"command": "true"}}}))
        (spec.cwd / "AGENTS.md").write_text("the project's words")
        before = {path: path.read_bytes() for path in agent.rglob("*.json")}
        driver, heard = PiDriver(), Heard()
        await driver.start(spec, heard)
        ready = await heard.until(Ready)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert ready.effective_model == MODEL
    assert model.calls[0].message.header("authorization") == "Bearer dummy-login"
    assert model.calls[0].offers("their_tool")
    assert model.calls[0].offers(f"mcp__{NAMESPACE}__{TOOL}")
    assert model.calls[0].says("the project's words")
    assert {path: path.read_bytes() for path in before} == before


async def test_a_role_with_no_login_is_refused_and_says_how_to_sign_in(tmp_path):
    (tmp_path / "home").mkdir()
    (tmp_path / "work").mkdir()
    fields = {"agent": "ada", "role": "worker", "goal": "go", "cwd": tmp_path / "work", "folder": tmp_path / "ada"}

    for model in (None, "openai/gpt-5.4"):
        spec = AgentSpec(**fields, model=model, env={"HOME": str(tmp_path / "home"), OFFLINE: "1"})
        driver = PiDriver()
        with pytest.raises(DriverError, match="no login for"):
            await driver.start(spec, Heard())
        await driver.stop(2.0)


async def test_access_is_a_provider_of_the_agent_s_own_and_no_saved_login_pays(tmp_path):
    async with FakeModel() as model, FakeTools() as tools:
        spec = on_fake_model(tmp_path, model, goal="go", tools=tools.binding(tmp_path))
        given = {**chat_access(model), "HOME": Secret(str(tmp_path / "home"))}
        driver, heard = PiDriver(), Heard()
        await driver.start(spec.model_copy(update={"access": given}), heard)
        ready = await heard.until(Ready)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert ready.effective_model == MODEL
    assert model.calls[0].message.header("authorization") == "Bearer dummy-key"
    assert model.calls[0].offers(TOOL)
    assert not heard.of(Native)
    assert [usage.tokens for usage in heard.of(Usage)] == [INPUT_TOKENS + OUTPUT_TOKENS]


async def test_a_model_named_with_its_provider_reads_as_it_was_asked_for(tmp_path):
    async with FakeModel() as model:
        driver, heard = PiDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, model=f"fake/{MODEL}"), heard)
        ready = await heard.until(Ready)
        await driver.stop(2.0)

    assert ready.effective_model == f"fake/{MODEL}"


async def test_effort_reaches_the_model_on_a_model_that_has_it(tmp_path):
    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model, goal="go", effort="low")
        given = {**chat_access(model), "HOME": Secret(str(tmp_path / "home"))}
        driver, heard = PiDriver(), Heard()
        await driver.start(spec.model_copy(update={"access": given}), heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert model.calls[0].json["reasoning_effort"] == "low"


@pytest.mark.parametrize("effort", ["low", "bogus"])
async def test_an_effort_it_cannot_honor_is_refused(tmp_path, effort):
    async with FakeModel() as model:
        driver = PiDriver()
        with pytest.raises(DriverError, match=f"{effort} was asked for"):
            await driver.start(on_fake_model(tmp_path, model, effort=effort), Heard())
        await driver.stop(2.0)

    assert not model.calls


async def test_two_identical_calls_in_a_turn_are_two_calls_through_the_shim(tmp_path, monkeypatch):
    """Why our tools go through the shim: over HTTP pi sends no id, and the second claim was taken for a retry."""
    claim = tool("task_claim", "call_one", queue="tasks")
    again = tool("task_claim", "call_two", queue="tasks")

    async with FakeModel(claim, again, "claimed") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        queue = {"kind": "queue", "writers": "human", "readers": "role:bob", "max_inflight": 2}
        team = Team(roles=team.roles, auth=team.auth, topology={"channels": {"tasks": queue}})

        async with Session.start(team, name="real", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.task_add("tasks", "the first")
            await session.task_add("tasks", "the second")
            await session.send("@bob", "claim two")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 1)
            claimed = await of_type(session, "task.claimed")
            started = (await of_type(session, "agent.started"))[0]

    assert len({event.stream for event in claimed}) == 2
    assert all("platoon-harness/callId" in event.native for event in claimed)
    assert started.data["effective_model"] == MODEL
    assert started.data["declared"]["approvals"] == "gated"


async def test_what_the_journal_says_a_harness_was_told_is_what_it_sent_its_model(tmp_path, monkeypatch):
    """The text journaled at launch is in the first request whole, once, beside whatever the harness says itself."""
    async with FakeModel("kestrel, done") as model:
        role = {"preamble": f"{PREAMBLE}\nA team of one.", "instructions": TOLD}
        team = keyed(tmp_path / "home", model, monkeypatch, **role)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await until(lambda: of_type(session, "turn.ended"), session)
            instructed = await of_type(session, "agent.instructed")
            told = (await session.get_body(instructed[0].data["instructions"])).decode()

    assert told.endswith("A team of one.\n\nBegin every reply with the word kestrel, then use `mcp__ph__peers`.")
    assert sum(text.count(told) for text in strings(model.calls[0].json)) == 1


async def test_what_the_journal_says_a_resumed_harness_was_told_is_what_it_sent_its_model(tmp_path, monkeypatch):
    """A harness that reopens its own session is handed and journaled what it was told when that began, though a
    channel has come since, and that text is in the request after the resume whole, once."""
    async with FakeModel("first", "second") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, instructions=TOLD)

        async with Session.start(team, name="told", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await until(lambda: of_type(session, "turn.ended"), session)
            await session.create_channel("news", "topic", readers=["all"], writers=["all"])

        async with Session.resume("told", root=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "again")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 2)
            instructed = await of_type(session, "agent.instructed")
            told = [(await session.get_body(event.data["instructions"])).decode() for event in instructed]

    assert len(told) == 2 and told[0] == told[1] and "news" not in told[1]
    assert sum(text.count(told[1]) for text in strings(model.calls[-1].json)) == 1


async def test_a_real_harness_that_stays_answers_a_task_a_follow_up_and_a_question_on_one_process(
    tmp_path, monkeypatch
):
    """The owner's flow, with a scripted lead: each answer wakes the lead and nothing else does, and the helper keeps
    one process until the lead retires it."""
    async with FakeModel("first answer", "second answer", "it meant this") as model:
        team = following_up(keyed(tmp_path / "home", model, monkeypatch))

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await session.send("@lead", "go")
            ending = await session.settled(timeout=TIMEOUT)
            events = [event async for event in session.events()]

    turns = [event.agent for event in events if event.type == "turn.started"]
    reports = [event.data["delivery"] for event in events if event.type == "message.sent" and event.data["subject"]]
    assert ending.reason == "settled", ending
    assert (turns.count("lead"), turns.count("bob")) == (4, 3)
    assert [event.agent for event in events if event.type in ("agent.started", "agent.resumed")] == ["lead", "bob"]
    assert reports == ["wake", "wake", "wake", "next-turn"]
    assert {row["agent"]: row["status"] for row in ending.agents} == {"lead": "finished", "bob": "retired"}
    assert len(model.calls) == 3
    assert all(call.says("what you say last in it goes to @lead") for call in model.calls)
    assert model.calls[1].says("A follow-up task") and model.calls[2].says("A question about it")


async def test_a_real_harness_calls_our_tools_parks_wakes_and_resumes_in_a_session(tmp_path, monkeypatch):
    replies = (tool("wait", "call_wait", **{"from": ["@you"]}), "waiting for you", "woken", "resumed")

    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, name="real", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "wait for me")
            await in_state(session, "bob", "waiting")

            await session.send("@bob", "carry on, the word is cinnabar")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 2)
            assert [event.data["reason"] for event in await of_type(session, "turn.ended")] == ["stopped", "stopped"]

        async with Session.resume("real", root=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "what was the word?")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 3)
            usages = await of_type(session, "usage.reported")

    assert model.calls[-1].says("cinnabar")
    assert model.calls[0].offers("wait")
    assert sum(event.data["tokens"] for event in usages) == len(model.calls) * (INPUT_TOKENS + OUTPUT_TOKENS)


async def test_a_real_harness_finishes_with_its_turn(tmp_path, monkeypatch):
    replies = (tool("agent_finish", "call_finish", gist="all done"), "that is all")

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


async def test_a_role_s_approval_policy_answers_the_gate(tmp_path, monkeypatch):
    run = shell("touch ran")

    async with FakeModel(run, "done") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, approvals="deny")

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "touch it")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 1)
            decided = [event for event in await of_type(session, "item.recorded") if event.data["approval"] is not None]

    assert not (tmp_path / "ran").exists()
    assert decided[0].data["outcome"] == "failed"
    assert model.calls[1].says("The runtime denied this.")


async def test_only_what_can_change_something_asks(tmp_path):
    reads = ToolCall("read", {"path": "note.txt"}, id="call_read")

    async with FakeModel(reads, ours("no gate"), "done") as model, FakeTools() as tools:
        spec = on_fake_model(tmp_path, model, goal="go", tools=tools.binding(tmp_path))
        (spec.cwd / "note.txt").write_text("a note")
        driver, heard = PiDriver(), Heard()
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert not heard.of(ApprovalRequested)
    assert len(tools.calls) == 1
    assert model.calls[1].says("a note")


async def test_a_denied_command_never_runs_and_the_item_says_so(tmp_path):
    async with FakeModel(ToolCall(BASH, {"command": "touch gated"}, id="call_gated"), "done") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        driver, heard = PiDriver(), Heard()
        await driver.start(spec, heard)
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "deny")
        decided = await heard.until(Item, lambda item: item.approval is not None)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert not (spec.cwd / "gated").exists()
    assert (decided.approval, decided.outcome, decided.native_id) == (asked.id, "failed", "call_gated")
    assert asked.gist.startswith("bash {")


class Allowing(Heard):
    """A reporter that says yes to whatever is asked, as a role that allows would."""

    def __init__(self, driver: PiDriver) -> None:
        super().__init__()
        self._driver = driver

    async def __call__(self, report: Any) -> None:
        await super().__call__(report)
        if isinstance(report, ApprovalRequested):
            await self._driver.answer(report.id, "allow")


async def test_a_gate_of_the_user_s_own_asks_too(tmp_path):
    """Their `confirm` is an approval. A `select`, as pi's own example gate uses, no verdict can answer, so it is
    cancelled and their gate blocks, which is said."""
    gate = """export default (pi) => pi.on("tool_call", async (event, ctx) => {
        const asked = event.input.command === "true"
          ? await ctx.ui.confirm("Theirs", "may it?")
          : (await ctx.ui.select("Which?", ["Yes", "No"])) === "Yes";
        return asked ? undefined : { block: true, reason: "their gate" };
    });"""
    calls = (ToolCall(BASH, {"command": "true"}, id="call_one"), ToolCall(BASH, {"command": "false"}, id="call_two"))

    async with FakeModel(*calls, "done") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        their_extension(tmp_path / "home", gate)
        driver = PiDriver()
        heard = Allowing(driver)
        await driver.start(spec, heard)
        native = await heard.until(Native)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert "Theirs may it?" in [asked.gist for asked in heard.of(ApprovalRequested)]
    assert native.kind == "extension_ui_request/select"
    assert model.calls[-1].says("their gate")


async def test_a_command_of_an_extension_is_taken_at_once_and_reaches_no_model(tmp_path):
    async with FakeModel() as model:
        driver = PiDriver()
        with pytest.raises(DriverError, match="reached no model"):
            await driver.start(on_fake_model(tmp_path, model, goal="/mcp"), Heard())
        await driver.stop(2.0)

    assert not model.calls


async def test_an_interrupt_ends_a_running_tool_and_an_open_gate(tmp_path):
    running_tool = ToolCall(BASH, {"command": "exec sleep 600"}, id="call_tool")

    async with FakeModel(running_tool, "next") as model:
        driver, heard = PiDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go"), heard)
        await heard.until(ApprovalRequested)
        await driver.interrupt()
        ended = await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert ended.reason == "interrupted"


async def test_a_steer_during_a_model_call_is_in_the_next_one_within_the_turn(tmp_path):
    steer = Delivery(input="41", boundary="model_call", text="the steer says cinnabar", items=())

    async with FakeModel([Stall(), ours("steer")], "done") as model, FakeTools() as tools:
        driver, heard = PiDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go", tools=tools.binding(tmp_path)), heard)
        await asyncio.wait_for(model.call(0), TIMEOUT)
        await driver.deliver(steer)
        model.release()
        delivered = await heard.until(InputDelivered)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert delivered.boundary == "model_call"
    assert len(heard.of(TurnStarted)) == 1
    assert model.calls[1].says("cinnabar")


def taken_twice(finished: list[Any]) -> bool:
    """Whether a wake and a steer have both been handed over."""
    return len([event for event in finished if event.data["kind"] == "deliver"]) == 2


async def test_an_interrupt_as_a_handover_begins_a_turn_never_reads_as_a_failure(tmp_path, monkeypatch):
    """The interrupt lands before the turn has begun, as it begins, or once it runs, and each must read as itself. What
    was waiting for the agent then wakes nothing, and a message sent after it wakes the agent as usual."""
    async with FakeModel([Stall(), Text("first")], "after") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await until(lambda: of_type(session, "effect.started"), session, handing_over)
            await session.interrupt("@bob")
            model.release()
            await in_state(session, "bob", "idle")
            await session.send("@bob", "again")
            ended = await until(lambda: of_type(session, "turn.ended"), session, stopped_at_last)

    assert {event.data["reason"] for event in ended} <= {"interrupted", "stopped"}


def handing_over(started: list[Any]) -> bool:
    return any(event.data["kind"] == "deliver" for event in started)


def stopped_at_last(ended: list[Any]) -> bool:
    return bool(ended) and ended[-1].data["reason"] == "stopped"


async def test_an_agent_that_took_no_turn_comes_back_anew_on_a_resume(tmp_path, monkeypatch):
    """Its harness wrote no session to reopen, so a resume that asked for one would lose it."""
    async with FakeModel("here") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, name="idle", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")

        async with Session.resume("idle", root=tmp_path) as session:
            await until(lambda: of_type(session, "agent.resumed"), session)
            await session.send("@bob", "are you there?")
            ended = await until(lambda: of_type(session, "turn.ended"), session)

    assert ended[-1].data["reason"] == "stopped"
    assert model.calls[-1].says("are you there?")


async def test_a_steer_an_interrupt_cut_off_comes_with_the_next_message_and_reaches_the_model(tmp_path, monkeypatch):
    """What the harness took and never landed wakes nothing once its turn is interrupted, and is offered again, once,
    with the next message."""
    async with FakeModel([Stall()], "the next turn") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, delivery="steer")

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await asyncio.wait_for(model.call(0), TIMEOUT)
            await session.send("@bob", "the word is cinnabar")
            await until(lambda: of_type(session, "effect.finished"), session, taken_twice)
            await session.interrupt("@bob")
            await until(lambda: of_type(session, "turn.ended"), session)
            await session.send("@bob", "carry on")
            ended = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)

    assert [event.data["reason"] for event in ended] == ["interrupted", "stopped"]
    assert model.calls[1].message.body.decode().count("cinnabar") == 1


async def test_a_resumed_harness_knows_what_landed_after_a_kill(tmp_path):
    landed = Delivery(input="41", boundary="turn", text=f"{delivery_heading(41)}\n- remember heliotrope", items=())

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model)
        first, heard = PiDriver(), Heard()
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await first.deliver(landed)
        delivered = await heard.until(InputDelivered)
        await heard.until(TurnEnded)
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, signal.SIGKILL)
        await heard.until(Exited)
        await first.stop(2.0)

        second, heard = PiDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        try:
            assert await second.reconcile("41") == "landed"
            assert await second.reconcile("4") == "unknown"
        finally:
            await second.stop(2.0)

    assert (delivered.boundary, delivered.evidence) == ("turn", "message_start")


async def test_a_session_that_took_no_turn_cannot_resume_and_says_so(tmp_path):
    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model)
        first, heard = PiDriver(), Heard()
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await first.stop(2.0)

        second, heard = PiDriver(), Heard()
        with pytest.raises(DriverError, match="is gone"):
            await second.start(spec.model_copy(update={"resume": native}), heard)
        await second.stop(2.0)

    assert "No session found" in (spec.folder / "stderr.log").read_text()


async def test_a_tool_a_kill_cut_off_reads_as_no_result_on_resume_and_never_ran_again(tmp_path):
    """What a resumed harness shows of a dangling tool call, which the cut-off notice must not contradict. The tool
    leads a group of its own, so it outlives the kill, as `crash_window` says, until a stop ends it by its `TMPDIR`."""
    delivery = Delivery(input="41", boundary="turn", text="carry on", items=())
    command = ToolCall(BASH, {"command": "echo ran >> ran; echo $$ > pipe; exec sleep 600"}, id="call_dangling")

    async with FakeModel(command, "ok") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        os.mkfifo(spec.cwd / "pipe")
        first, heard = PiDriver(), Heard()
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await driver_allows(first, heard)
        tool_pid = int(await asyncio.to_thread((spec.cwd / "pipe").read_text))
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, signal.SIGKILL)
        await heard.until(Exited)
        outlived = running(tool_pid)
        await first.stop(2.0)
        assert (outlived, running(tool_pid)) == (True, False)

        second, heard = PiDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        await second.deliver(delivery)
        await heard.until(TurnEnded)
        await second.stop(2.0)

    assert (spec.cwd / "ran").read_text() == "ran\n"
    results = [message for message in model.calls[-1].json["messages"] if message["role"] == "tool"]
    assert [(result["tool_call_id"], result["content"]) for result in results] == [
        ("call_dangling", "No result provided")
    ]


async def driver_allows(driver: PiDriver, heard: Heard) -> None:
    asked = await heard.until(ApprovalRequested)
    await driver.answer(asked.id, "allow")


async def test_our_words_go_beside_the_user_s_own_and_come_once_on_a_resume_too(tmp_path):
    delivery = Delivery(input="41", boundary="turn", text="again", items=())

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model, goal="go", instructions="our words, viridian")
        (tmp_path / "home" / ".pi" / "agent" / "APPEND_SYSTEM.md").write_text("their words, ochre")
        first, heard = PiDriver(), Heard()
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await heard.until(TurnEnded)
        await first.stop(2.0)

        second, heard = PiDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        await second.deliver(delivery)
        await heard.until(TurnEnded)
        await second.stop(2.0)

    assert [call.message.body.decode().count("viridian") for call in model.calls] == [1, 1]
    assert [call.message.body.decode().count("ochre") for call in model.calls] == [1, 1]


async def test_a_compaction_reports_its_call_what_it_forgot_and_its_summary(tmp_path):
    settings = {"compaction": {"keepRecentTokens": 1, "reserveTokens": 99_990}}
    second = Delivery(input="41", boundary="turn", text="say two" * 20, items=())

    async with FakeModel("one", "summary one", "summary two", "two", "summary three", "summary four") as model:
        driver, heard = PiDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="say one" * 20, settings=settings), heard)
        await heard.until(Compacted)
        await heard.until(TurnEnded)
        await driver.deliver(second)
        await heard.until(Compacted, lambda _: len(heard.of(Compacted)) == 2)
        entries = await driver._ask("get_entries")
        await driver.stop(2.0)

    first_compaction, second_compaction = heard.of(Compacted)
    users = [
        entry["id"] for entry in entries["entries"] if entry["type"] == "message" and entry["message"]["role"] == "user"
    ]
    assert first_compaction.summary
    assert first_compaction.forgotten == (users[0],)
    assert users[1] in second_compaction.forgotten
    assert users[0] not in second_compaction.forgotten
    calls = [call for call in heard.of(ModelCall) if call.purpose == "compaction"]
    assert [call.call_id for call in calls] == [None, None]
    tokens = sum(usage.tokens or 0 for usage in heard.of(Usage))
    assert tokens == len(model.calls) * (INPUT_TOKENS + OUTPUT_TOKENS)
    assert not [gap for gap in heard.of(GapReport) if gap.what == "compaction_opaque"]


async def test_a_tool_call_is_cut_at_the_timeout_it_declares(tmp_path, monkeypatch):
    """The cap on one tool call is the one we set, so a tool that never answers is told so and the turn goes on."""
    monkeypatch.setattr("platoon_harness.drivers.pi._TOOL_TIMEOUT_S", 1)

    class Silent(FakeTools):
        def _reply(self, frame: dict[str, Any]) -> bytes:
            if frame.get("method") != "tools/call":
                return super()._reply(frame)
            return answer(202)

    async with FakeModel(ours("never answered"), "done") as model, Silent() as tools:
        driver, heard = PiDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go", tools=tools.binding(tmp_path)), heard)
        cut = await heard.until(Item, lambda item: item.phase == "completed")
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert cut.outcome == "failed"
    assert "timed out" in (cut.body or "")


async def test_a_server_of_ours_that_fails_is_said_aloud(tmp_path):
    async with FakeModel() as model, FakeTools() as tools:
        binding = tools.binding(tmp_path).model_copy(update={"token": Secret("not-the-token")})
        driver, heard = PiDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, tools=binding), heard)
        said = await heard.until(Native, lambda native: native.kind == "notify")
        await driver.stop(2.0)

    assert NAMESPACE in said.raw
    assert "not-the-token" not in said.raw


async def test_a_login_s_kind_comes_from_pi_s_own_check(tmp_path, monkeypatch):
    async with FakeModel() as model:
        own_setup(tmp_path / "home", model)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert PiDriver().describe().login == "key"


async def test_a_resumed_session_takes_the_instructions_it_is_handed(tmp_path):
    """Pi sets our section afresh at each launch, so a resume that handed it other text than its session began with
    would tell it that."""
    async with FakeModel("one", "two") as model:
        spec = on_fake_model(tmp_path, model, goal="go", instructions="ALPHA-ONE")
        driver, heard = PiDriver(), Heard()
        await driver.start(spec, heard)
        native = (await heard.until(Ready)).native
        await heard.until(TurnEnded)
        await driver.stop(2.0)

        resumed, heard = PiDriver(), Heard()
        again = {"resume": native, "goal": "", "instructions": "BRAVO-TWO"}
        await resumed.start(spec.model_copy(update=again), heard)
        await heard.until(Ready)
        await resumed.deliver(Delivery(input="41", boundary="turn", text="again", items=()))
        await heard.until(TurnEnded)
        await resumed.stop(2.0)

    assert model.calls[-1].says("BRAVO-TWO") and not model.calls[-1].says("ALPHA-ONE")


async def test_a_tail_of_live_text_joined_to_what_was_committed_is_the_text(tmp_path, monkeypatch):
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.a_tail_joined_to_what_was_committed_is_the_text(team, tmp_path)


async def test_stop_below_stops_the_turns_of_a_lead_and_its_child_and_keeps_both(tmp_path, monkeypatch):
    async with FakeModel([Stall()]) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.stop_below_stops_the_turns_of_a_lead_and_its_child_and_keeps_both(team, tmp_path, model)


async def test_an_interrupt_under_a_tokens_limit_leaves_the_session_to_go_on(tmp_path, monkeypatch):
    async with FakeModel([Stall()], "carried on") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.an_interrupt_under_a_tokens_limit_leaves_the_session_to_go_on(team, tmp_path, model)


async def test_a_spawn_carries_the_anchor_of_the_call_that_made_it(tmp_path, monkeypatch):
    """Pi's calls reach us through the shim, whose id is its own and no item's, so no tool item holds the anchor."""
    async with FakeModel(ToolCall("mcp__ph__agent_spawn", clients.SPAWN, id="call_spawn"), "spawned it") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        spawned, under = await clients.a_spawn_and_the_call_that_made_it(team, tmp_path)

    assert (list(spawned.native), under) == (["platoon-harness/callId"], [])


async def test_the_tui_sends_from_its_composer_and_draws_the_reply_once(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.the_tui_sends_from_its_composer_and_draws_the_reply_once(team, tmp_path)
