"""The `codex` driver on the real binary against FakeModel. Free: a dummy key, an isolated home, and loopback only."""

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
    ChildSeen,
    Compacted,
    Delivery,
    DriverError,
    Exited,
    GapReport,
    InputDelivered,
    Item,
    ModelCall,
    Ready,
    TurnEnded,
    TurnStarted,
    Usage,
)
from platoon_harness.drivers.codex import CodexDriver
from platoon_harness.drivers.levels import Conformance, Profile, levels
from platoon_harness.drivers.process import Record
from platoon_harness.runtime.paths import write_conformance
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
    check_harness,
    goal,
)
from platoon_harness.testing.model import INPUT_TOKENS, OUTPUT_TOKENS
from platoon_harness.tools import PREAMBLE

from ..unit.drivers.support import Heard
from ..unit.runtime.gitting import repository
from ..unit.runtime.support import in_state, of_type, until
from . import clients, worktrees
from .scripts import TOLD, following_up, strings

pytestmark = [pytest.mark.slow, pytest.mark.timeout(120)]

MODEL = "fake-model"
TIMEOUT = 60.0
ESCALATED = {"sandbox_permissions": "require_escalated", "justification": "needs an approval"}
GATED = ToolCall("exec_command", {"cmd": "touch gated", **ESCALATED}, id="call_gated")
PINNED = "0.164.0"
CHILD = ToolCall("spawn_agent", {"message": "say so"}, id="call_child", namespace="multi_agent_v1")


@pytest.fixture(autouse=True)
def binary():
    if shutil.which("codex") is None:
        pytest.skip("codex is not installed, so this driver met no real harness here")


def access(home: Path, settings: str = ""):
    """How a harness reaches FakeModel, on a dummy key, with a home of its own so that no login takes part."""

    def given(model: FakeModel) -> dict[str, Secret]:
        (home / ".codex").mkdir(parents=True, exist_ok=True)
        (home / ".codex" / "config.toml").write_text(settings)
        codex = {"HOME": Secret(str(home)), "CODEX_HOME": Secret(str(home / ".codex"))}
        return {**chat_access(model), **codex}

    return given


def shell(command: str) -> ToolCall:
    return ToolCall("exec_command", {"cmd": command})


def gated(command: str) -> ToolCall:
    return ToolCall("exec_command", {"cmd": command, **ESCALATED}, id="call_gated")


def ours(note: str) -> ToolCall:
    return ToolCall(TOOL, {"note": note}, namespace=f"mcp__{NAMESPACE}")


def tool(name: str, id: str, **arguments: Any) -> ToolCall:
    return ToolCall(name, arguments, id=id, namespace="mcp__ph")


async def conformance(folder: Path) -> Conformance:
    return await check_harness("codex", folder)


@pytest.mark.timeout(600)
async def test_the_codex_driver_conforms(tmp_path, monkeypatch):
    result = await conformance(tmp_path / "check")

    print(result)
    assert result.failed == (), str(result)
    assert (result.driver, result.version) == ("codex", PINNED)
    skipped = {check.name for check in result.checks if check.state == "skipped"}
    assert skipped == {"call_ids_reported", "one_shot_exits", "declared_but_unproven"}
    earned = levels(CodexDriver().describe().capabilities, Profile(driver="codex", version=result.version), result)
    assert earned.operational.state == "met", earned.operational.reasons
    assert earned.observable.state == "met", earned.observable.reasons

    write_conformance(tmp_path, result)
    async with FakeModel() as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            started = (await of_type(session, "agent.started"))[0]

    assert started.data["levels"]["operational"]["state"] == "met", started.data["levels"]["operational"]


def on_fake_model(tmp_path: Path, fake: FakeModel, *, settings: str = "", **fields: Any) -> AgentSpec:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    spec = {"agent": "ada", "role": "worker", "goal": "", "cwd": work, "folder": tmp_path / "ada", "model": MODEL}
    given = {**spec, "access": access(tmp_path / "home", settings)(fake), **fields}
    return AgentSpec.model_validate({**given, "goal": goal(given["goal"])})


def keyed(home: Path, model: FakeModel, monkeypatch: pytest.MonkeyPatch, **role: Any) -> Team:
    """One agent on the real binary, reaching FakeModel the way an auth profile would."""
    (home / ".codex").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    monkeypatch.setenv("OPENAI_BASE_URL", f"{model.url}/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    bob = Role(harness="codex", model=MODEL, auth="fake", **role)
    return Team(roles={"bob": bob}, auth={"fake": AuthProfile(env=("OPENAI_BASE_URL", "OPENAI_API_KEY"))})


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
            told = (await session.get_body(instructed[0].data["body"])).decode()

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
            told = [(await session.get_body(event.data["body"])).decode() for event in instructed]

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
    replies = (
        tool("channel_list", "call_list"),
        tool("wait", "call_wait", **{"from": ["@you"]}),
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
            assert {"call_list", "call_wait"} <= {event.data["native_id"] for event in items}
            assert placed[0].native["callId"] == "call_wait"
            assert started.data["effective_model"] == MODEL
            assert started.data["verified"]["login"] == "key"

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


async def test_a_role_s_sandbox_reaches_the_harness(tmp_path, monkeypatch):
    async with FakeModel(shell("touch refused"), "done") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, sandbox="read-only")
        work = tmp_path / "work"
        work.mkdir()

        async with Session.start(team, root=tmp_path, cwd=work) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "touch it")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 1)

    assert not (work / "refused").exists()
    assert json.loads(model.calls[0].message.header("x-codex-turn-metadata"))["sandbox_mode"] == "read-only"


@pytest.mark.parametrize(
    ("sandbox", "inside", "outside"),
    [("read-only", False, False), ("workspace-write", True, False), ("danger-full-access", True, True)],
)
async def test_each_sandbox_it_declares_does_what_it_says(tmp_path, sandbox, inside, outside):
    settings = "[sandbox_workspace_write]\nexclude_slash_tmp = true\nexclude_tmpdir_env_var = true\n"
    target = tmp_path / "home" / "outside"
    async with FakeModel(shell(f"touch inside; touch {target}"), "done") as model:
        spec = on_fake_model(tmp_path, model, goal="go", sandbox=sandbox, settings=settings)
        driver, heard = CodexDriver(), Heard()
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert (spec.cwd / "inside").exists() == inside
    assert target.exists() == outside


async def test_a_resumed_harness_knows_what_landed_after_a_kill(tmp_path):
    delivery = Delivery(input="41", boundary="turn", text="remember heliotrope", items=())

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model)
        first, heard = CodexDriver(), Heard()
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await first.deliver(delivery)
        delivered = await heard.until(InputDelivered, lambda landed: landed.input == "41")
        await heard.until(TurnEnded)
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, signal.SIGKILL)
        await heard.until(Exited)
        await first.stop(2.0)

        second, heard = CodexDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        try:
            assert await second.reconcile("41") == "landed"
            assert await second.reconcile("42") == "unknown"
        finally:
            await second.stop(2.0)

    assert (delivered.boundary, delivered.evidence) == ("turn", "userMessage")


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


async def test_a_steer_during_a_model_call_is_in_the_next_one_within_the_turn(tmp_path):
    steer = Delivery(input="41", boundary="model_call", text="the steer says cinnabar", items=())

    async with FakeModel([Stall(), ours("steer")], "done") as model:
        driver, heard = CodexDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go"), heard)
        await asyncio.wait_for(model.call(0), TIMEOUT)
        await driver.deliver(steer)
        model.release()
        delivered = await heard.until(InputDelivered, lambda landed: landed.input == "41")
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert delivered.boundary == "model_call"
    assert len(heard.of(TurnStarted)) == 1
    assert model.calls[1].says("cinnabar")


async def test_a_tool_a_kill_cut_off_reads_as_aborted_on_resume_and_never_ran_again(tmp_path):
    """What a resumed harness shows of a dangling tool call, which the cut-off notice must not contradict."""
    delivery = Delivery(input="41", boundary="turn", text="carry on", items=())
    command = ToolCall(
        "exec_command", {"cmd": "echo ran >> ran; echo running > pipe; exec sleep 600"}, id="call_dangling"
    )

    async with FakeModel(command, "ok") as model:
        spec = on_fake_model(tmp_path, model, goal="go", sandbox="workspace-write")
        os.mkfifo(spec.cwd / "pipe")
        first, heard = CodexDriver(), Heard()
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await asyncio.to_thread((spec.cwd / "pipe").read_text)
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, signal.SIGKILL)
        await heard.until(Exited)
        await first.stop(2.0)

        second, heard = CodexDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        await second.deliver(delivery)
        await heard.until(TurnEnded)
        await second.stop(2.0)

    assert (spec.cwd / "ran").read_text() == "ran\n"
    outputs = [item for item in model.calls[-1].json["input"] if item["type"] == "function_call_output"]
    assert [(output["call_id"], output["output"]) for output in outputs] == [("call_dangling", "aborted")]


async def test_a_compaction_reports_its_call_and_a_gap_for_what_it_forgot(tmp_path):
    delivery = Delivery(input="41", boundary="turn", text="say two", items=())

    async with FakeModel("one", "the summary", "two") as model:
        driver, heard = CodexDriver(), Heard()
        settings = "model_auto_compact_token_limit = 10\n"
        await driver.start(on_fake_model(tmp_path, model, goal="say one", settings=settings), heard)
        await heard.until(TurnEnded)
        await driver.deliver(delivery)
        compacted = await heard.until(Compacted)
        called = await heard.until(ModelCall, lambda call: call.purpose == "compaction")
        await heard.until(TurnEnded, lambda _: len(heard.of(TurnEnded)) == 2)
        await driver.stop(2.0)

    assert (compacted.forgotten, compacted.summary) == (None, None)
    assert called.call_id is None
    assert sum(usage.tokens or 0 for usage in heard.of(Usage)) == len(model.calls) * (INPUT_TOKENS + OUTPUT_TOKENS)
    assert not [gap for gap in heard.of(GapReport) if gap.what == "hidden_call"]


async def test_a_child_holds_the_turn_open_and_its_spending_is_on_the_tree(tmp_path):
    async with FakeModel(CHILD, "the parent is done", "the child is done") as model:
        driver, heard = CodexDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="spawn one", allow_native_children=True), heard)
        child = await heard.until(ChildSeen)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert set(child.model_dump(exclude={"type"})) == {"native", "parent"}
    assert len(heard.of(TurnEnded)) == 1
    usages = heard.of(Usage)
    assert {usage.scope for usage in usages} == {"call", "tree"}
    assert sum(usage.tokens or 0 for usage in usages) == len(model.calls) * (INPUT_TOKENS + OUTPUT_TOKENS)
    assert len(heard.of(ModelCall)) == len(model.calls)


COLLABORATION = ("spawn_agent", "followup_task", "send_message", "interrupt_agent", "list_agents", "wait_agent")


@pytest.mark.parametrize("allowed", [False, True])
async def test_a_catalog_model_s_own_agents_are_off_unless_a_role_allows_them(tmp_path, allowed):
    """A current catalog model gets the second generation of Codex's own agents, its tools listed in the input, which
    `features.multi_agent` leaves on. FakeModel stands in for the model under that name."""
    async with FakeModel("ok") as model:
        driver, heard = CodexDriver(), Heard()
        spec = on_fake_model(tmp_path, model, goal="go", model="gpt-6-luna", allow_native_children=allowed)
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert bool(set(COLLABORATION) & set(model.calls[0].tools)) == allowed
    assert model.calls[0].says("You are `/root`") == allowed
    assert {request.message.target for request in model.requests} == {"/v1/responses"}


async def test_a_resumed_session_keeps_the_instructions_and_the_setting_of_its_own_agents_it_began_with(tmp_path):
    """`thread/resume` keeps the `developerInstructions` and the `agents.enabled` a thread began with, whatever it is
    sent, which is why a resume is handed that text again."""
    async with FakeModel("one", "two") as model:
        spec = on_fake_model(tmp_path, model, goal="go", instructions="ALPHA-ONE", model="gpt-6-luna")
        driver, heard = CodexDriver(), Heard()
        await driver.start(spec, heard)
        native = (await heard.until(Ready)).native
        await heard.until(TurnEnded)
        await driver.stop(2.0)

        resumed, heard = CodexDriver(), Heard()
        again = {"resume": native, "goal": None, "instructions": "BRAVO-TWO", "allow_native_children": True}
        await resumed.start(spec.model_copy(update=again), heard)
        await heard.until(Ready)
        await resumed.deliver(Delivery(input="41", boundary="turn", text="again", items=()))
        await heard.until(TurnEnded)
        await resumed.stop(2.0)

    assert model.calls[-1].says("ALPHA-ONE") and not model.calls[-1].says("BRAVO-TWO")
    assert not set(COLLABORATION) & set(model.calls[-1].tools)


async def test_an_interrupt_reaches_a_child_as_well(tmp_path):
    async with FakeModel(CHILD, [Stall()], [Stall()]) as model:
        driver, heard = CodexDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="spawn one", allow_native_children=True), heard)
        await heard.until(ChildSeen)
        await asyncio.wait_for(model.call(2), TIMEOUT)
        await driver.interrupt()
        turn = await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert turn.reason == "interrupted"


async def test_effort_reaches_the_model_and_comes_back_on_a_resume(tmp_path):
    async with FakeModel("ok") as model:
        spec = on_fake_model(tmp_path, model, goal="go", effort="low")
        driver, heard = CodexDriver(), Heard()
        await driver.start(spec, heard)
        native = (await heard.until(Ready)).native
        await heard.until(TurnEnded)
        await driver.stop(2.0)

        resumed = CodexDriver()
        await resumed.start(spec.model_copy(update={"resume": native}), Heard())
        await resumed.stop(2.0)

    assert model.calls[0].json["reasoning"]["effort"] == "low"


async def test_with_no_model_on_a_login_of_its_own_ready_says_the_harness_s_default(tmp_path):
    (tmp_path / "home" / ".codex").mkdir(parents=True)
    variables = {"HOME": str(tmp_path / "home"), "CODEX_HOME": str(tmp_path / "home" / ".codex")}

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model, model=None, access={}, env=variables)
        driver, heard = CodexDriver(), Heard()
        await driver.start(spec, heard)
        ready = await heard.until(Ready)
        await driver.stop(2.0)

    assert ready.effective_model
    assert not model.calls


async def test_what_the_user_set_stays_beside_ours(tmp_path):
    settings = 'developer_instructions = "their words"\n[shell_environment_policy]\nexclude = ["THEIR_SECRET"]\n'
    variables = {"THEIR_SECRET": "cinnabar"}
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "AGENTS.md").write_text("the project's words")
    said = shell("echo secret=$THEIR_SECRET token=$PLATOON_HARNESS_TOKEN")

    async with FakeModel(said, "done") as model, FakeTools() as tools:
        spec = on_fake_model(
            tmp_path,
            model,
            goal="go",
            settings=settings,
            instructions="our words",
            env=variables,
            tools=tools.binding(tmp_path),
        )
        driver, heard = CodexDriver(), Heard()
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert model.calls[0].says("their words")
    assert model.calls[0].says("our words")
    assert model.calls[0].says("the project's words")
    assert model.calls[1].says("secret= token=\\n")


async def test_the_user_s_own_mcp_server_asks_and_the_runtime_answers(tmp_path):
    called = ToolCall(TOOL, {"note": "theirs"}, id="call_theirs", namespace="mcp__theirs")

    async with FakeModel(called, "done") as model, FakeTools() as tools:
        url, token = tools.binding(tmp_path).url, tools.binding(tmp_path).token.reveal()
        settings = f'[mcp_servers.theirs]\nurl = "{url}"\nbearer_token_env_var = "THEIR_TOKEN"\n'
        spec = on_fake_model(tmp_path, model, goal="go", settings=settings, env={"THEIR_TOKEN": token})
        driver, heard = CodexDriver(), Heard()
        await driver.start(spec, heard)
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "allow")
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert "Allow the theirs MCP server" in asked.gist
    assert len(tools.calls) == 1


async def test_a_denied_command_never_runs_and_the_item_says_so(tmp_path):
    async with FakeModel(GATED, "done") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        driver, heard = CodexDriver(), Heard()
        await driver.start(spec, heard)
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "deny")
        decided = await heard.until(Item, lambda item: item.approval is not None)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert not (spec.cwd / "gated").exists()
    assert (decided.approval, decided.outcome, decided.native_id) == (asked.id, "declined", "call_gated")


async def test_a_required_server_that_refuses_us_fails_the_start_and_says_why(tmp_path):
    async with FakeModel() as model, FakeTools() as tools:
        binding = tools.binding(tmp_path).model_copy(update={"token": Secret("not-the-token")})
        driver = CodexDriver()
        with pytest.raises(DriverError, match="required MCP servers failed"):
            await driver.start(on_fake_model(tmp_path, model, tools=binding), Heard())
        await driver.stop(2.0)

    assert not model.calls


async def test_a_tail_of_live_text_joined_to_what_was_committed_is_the_text(tmp_path, monkeypatch):
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.a_tail_joined_to_what_was_committed_is_the_text(team, tmp_path)


async def test_an_idle_harness_rests_and_its_next_message_resumes_it_natively(tmp_path, monkeypatch):
    async with FakeModel("noted", "heliotrope") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.an_idle_harness_rests_and_its_next_message_resumes_it_natively(team, tmp_path, model)


HELD = ToolCall("wait", {"from": ["@you"], "hold": 30}, id="call_held", namespace="mcp__ph")
"""A call of our `wait` that holds, so a test can kill the harness while it is in a turn."""


async def test_a_harness_killed_alone_in_a_turn_is_resumed_once_and_told(tmp_path, monkeypatch):
    async with FakeModel("noted", HELD, "checked") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.a_harness_killed_alone_in_a_turn_is_resumed_once_and_told(team, tmp_path, model)


async def test_a_harness_killed_alone_twice_before_a_turn_ends_is_lost(tmp_path, monkeypatch):
    async with FakeModel("noted", HELD, HELD) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.a_harness_killed_alone_twice_before_a_turn_ends_is_lost(team, tmp_path, model)


async def test_stop_below_stops_the_turns_of_a_lead_and_its_child_and_keeps_both(tmp_path, monkeypatch):
    async with FakeModel([Stall()]) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.stop_below_stops_the_turns_of_a_lead_and_its_child_and_keeps_both(team, tmp_path, model)


async def test_an_interrupt_under_a_tokens_limit_leaves_the_session_to_go_on(tmp_path, monkeypatch):
    async with FakeModel([Stall()], "carried on") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.an_interrupt_under_a_tokens_limit_leaves_the_session_to_go_on(team, tmp_path, model)


async def test_a_spawn_carries_the_anchor_of_the_call_that_made_it(tmp_path, monkeypatch):
    """The spawn's anchor is the `native_id` of the tool item of the call that made it, so a client can join the two."""
    spawning = ToolCall("agent_spawn", clients.SPAWN, id="call_spawn", namespace="mcp__ph")
    async with FakeModel(spawning, "spawned it") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        spawned, under = await clients.a_spawn_and_the_call_that_made_it(team, tmp_path)

    assert under and {item.data["native_id"] for item in under} == set(spawned.native.values())


async def test_a_read_is_confirmed_by_the_item_that_holds_its_result_and_the_launch_by_the_first_input(
    tmp_path, monkeypatch
):
    async with FakeModel(tool("message_read", "call_read", after=0), "read it") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        read, confirmations = await clients.a_read_and_what_confirmed_it(team, tmp_path)

    hows = {event.data["how"]: event.data for event in confirmations}
    anchor = read.native["callId"]
    assert (hows["read"]["input"], hows["read"]["evidence"], hows["read"]["native_id"]) == (
        read.seq,
        "tool_item",
        anchor,
    )
    assert (hows["wake"]["evidence"], hows["launch"]["evidence"]) == ("userMessage", "userMessage")


async def test_a_cited_write_is_traced_to_its_item_and_no_model_call(tmp_path, monkeypatch):
    """Codex's `callId` joins its tool item, which names no model call, so each answer about the write stops at its
    commit, and the read before it was confirmed by its item, as returned to whatever made the call."""
    replies = (tool("message_read", "call_read", after=0), tool("message_send", "call_send", **clients.CITING), "done")
    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        traced = await clients.a_read_then_a_cited_write(team, tmp_path)

    clients.hold_their_bounds(traced, "commit")
    made = traced.lineage.made
    assert made.anchor is not None and made.anchor.key == "callId"
    assert (made.item is not None, made.call) == (True, None)
    assert [(edge.how, edge.confirmed and edge.confirmed.evidence) for edge in traced.exposure.edges] == [
        ("wake", "userMessage"),
        ("read", "tool_item"),
    ]


async def test_the_tui_sends_from_its_composer_and_draws_the_reply_once(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.the_tui_sends_from_its_composer_and_draws_the_reply_once(team, tmp_path)


async def test_codex_resumes_in_its_worktree(tmp_path, monkeypatch):
    """It commits in its worktree, its runtime is killed, and it resumes there: the same folder, the same branch."""
    repo = repository(tmp_path / "repo", monkeypatch)
    async with FakeModel(*worktrees.replies(gated)) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await worktrees.commits_is_killed_and_resumes_in_its_worktree(team, tmp_path, repo)
