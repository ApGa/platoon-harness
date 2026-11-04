"""The `openhands` driver on the real OpenHands SDK against FakeModel. Free: a dummy key, an isolated home, and loopback
only.

The worker lives in an environment of its own, which these tests find on PATH as `platoon-harness-openhands`. Build it
from the lock and put its `bin` on PATH:

    UV_PROJECT_ENVIRONMENT=/somewhere/openhands uv sync --package platoon-harness-openhands --frozen
    PATH=/somewhere/openhands/bin:$PATH uv run pytest -m slow tests/integration/test_openhands.py

No live model has run through this driver: all of this is what the SDK did on FakeModel.
"""

import asyncio
import json
import os
import shutil
import signal
import subprocess
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
    ModelCall,
    Ready,
    TurnEnded,
    Usage,
)
from platoon_harness.drivers.levels import Conformance, Profile, levels
from platoon_harness.drivers.openhands import WORKER, OpenHandsDriver
from platoon_harness.drivers.process import Record
from platoon_harness.team import AuthProfile
from platoon_harness.testing import (
    TOOL,
    Call,
    FakeModel,
    FakeTools,
    ScriptedDriver,
    Stall,
    Text,
    ToolCall,
    chat_access,
    check_driver,
)
from platoon_harness.testing.model import INPUT_TOKENS, OUTPUT_TOKENS
from platoon_harness.tools import PREAMBLE, delivery_heading

from ..unit.drivers.support import Heard
from ..unit.runtime import support
from ..unit.runtime.support import in_state, of_type, until
from . import clients
from .scripts import TOLD, strings

pytestmark = [pytest.mark.slow, pytest.mark.timeout(300)]

MODEL = "fake-model"
PINNED = "1.59.0"
TIMEOUT = 90.0
SPENT = INPUT_TOKENS + OUTPUT_TOKENS


@pytest.fixture(autouse=True)
def worker(monkeypatch):
    """The worker on PATH, given longer than a binary to come up, as it loads the SDK first."""
    if shutil.which(WORKER) is None:
        pytest.skip(f"{WORKER} is not on PATH, so this driver met no real OpenHands here")
    monkeypatch.setattr(support, "SECONDS", TIMEOUT)


def access(home: Path):
    """How the worker reaches FakeModel, in a home of its own, so that nothing of the person running this takes part.
    Naming `HOME` is access, as an auth profile's is."""

    def given(model: FakeModel) -> dict[str, Secret]:
        home.mkdir(parents=True, exist_ok=True)
        return {**chat_access(model), "HOME": Secret(str(home))}

    return given


def shell(command: str) -> ToolCall:
    return ToolCall("terminal", {"command": command}, id="call_gated")


def garbling(folder: Path):
    """Write into the worker's own stdout, as nothing makes the real SDK write a frame no parser knows."""

    async def garble(_: OpenHandsDriver) -> None:
        record = Record.read(folder / "malformed_frame_is_a_gap" / "agent")
        assert record is not None
        pipe = os.open(f"/proc/{record.pid}/fd/1", os.O_WRONLY)
        unknown = json.dumps({"jsonrpc": "2.0", "method": "nobody_knows"}).encode()
        os.write(pipe, b"this is no frame\n" + unknown + b"\n")
        os.close(pipe)

    return garble


async def conformance(folder: Path) -> Conformance:
    return await check_driver(
        OpenHandsDriver,
        folder=folder,
        access=access(folder / "home"),
        garble=garbling(folder),
        gated=shell,
        shell=shell,
        timeout=TIMEOUT,
    )


@pytest.mark.timeout(1200)
async def test_the_openhands_driver_conforms(tmp_path):
    result = await conformance(tmp_path)

    print(result)
    assert result.failed == (), str(result)
    assert (result.driver, result.version) == ("openhands", PINNED)
    skipped = {check.name for check in result.checks if check.state == "skipped"}
    assert skipped == {
        "tool_item_carries_its_anchor",
        "native_children_off_by_default",
        "native_child_seen",
        "one_shot_exits",
        "declared_but_unproven",
    }
    earned = levels(OpenHandsDriver().describe().capabilities, Profile(driver="openhands", version=PINNED), result)
    assert earned.operational.state == "met", earned.operational.reasons
    assert earned.observable.state == "met", earned.observable.reasons
    assert earned.trainable.state == "unmet"


def on_fake_model(tmp_path: Path, fake: FakeModel, **fields: Any) -> AgentSpec:
    """An agent in a home of its own, reaching FakeModel by key."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    given = access(tmp_path / "home")(fake)
    spec = {"agent": "ada", "role": "worker", "goal": "", "cwd": work, "folder": tmp_path / "ada", "model": MODEL}
    return AgentSpec.model_validate({**spec, "access": given, **fields})


def keyed(home: Path, model: FakeModel, monkeypatch: pytest.MonkeyPatch, **role: Any) -> Team:
    """One agent on the worker, reaching FakeModel the way an auth profile would, in a home of its own."""
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENAI_BASE_URL", f"{model.url}/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    bob = Role(harness="openhands", model=MODEL, auth="fake", **role)
    return Team(roles={"bob": bob}, auth={"fake": AuthProfile(env=("OPENAI_BASE_URL", "OPENAI_API_KEY"))})


class Allowing(Heard):
    """A reporter that says yes to whatever is asked, as a role that allows would."""

    def __init__(self, driver: OpenHandsDriver) -> None:
        super().__init__()
        self._driver = driver

    async def __call__(self, report: Any) -> None:
        await super().__call__(report)
        if isinstance(report, ApprovalRequested):
            await self._driver.answer(report.id, "allow")


async def test_a_role_with_no_key_is_refused_and_says_how_to_sign_in(tmp_path):
    (tmp_path / "work").mkdir()
    spec = AgentSpec(agent="ada", role="worker", goal="go", cwd=tmp_path / "work", folder=tmp_path / "ada")
    driver = OpenHandsDriver()
    with pytest.raises(DriverError, match="OPENAI_API_KEY"):
        await driver.start(spec.model_copy(update={"env": {"HOME": str(tmp_path / "home")}}), Heard())
    await driver.stop(2.0)


async def test_an_effort_a_model_takes_none_of_is_refused_as_litellm_would_drop_it(tmp_path):
    async with FakeModel() as model:
        driver = OpenHandsDriver()
        with pytest.raises(DriverError, match="takes no effort"):
            await driver.start(on_fake_model(tmp_path, model, model="gpt-4o", effort="low"), Heard())
        await driver.stop(2.0)

    assert not model.calls


async def test_our_words_and_the_project_s_reach_the_first_request_once_and_its_own_agents_are_off(tmp_path):
    """The project is a repository, as the SDK looks for its instructions from the repository's root."""
    async with FakeModel() as model, FakeTools() as tools:
        spec = on_fake_model(tmp_path, model, goal="go", instructions="our words, viridian")
        spec = spec.model_copy(update={"tools": tools.binding(tmp_path)})
        await asyncio.to_thread(subprocess.run, ["git", "init", "-q", str(spec.cwd)], check=True)
        (spec.cwd / "AGENTS.md").write_text("the project's words, ochre")
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(spec, heard)
        ready = await heard.until(Ready)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    first = model.calls[0]
    assert first.message.body.decode().count("viridian") == 1
    assert first.says("ochre")
    assert TOOL in first.tools and "task" not in first.tools
    assert ready.tools_visible is not None and TOOL in ready.tools_visible
    assert (ready.version, ready.effective_model, first.model) == (PINNED, MODEL, MODEL)


async def test_its_own_agents_when_allowed_are_unseen_and_ask_the_runtime_before_a_step(tmp_path):
    """Starting a child asks, as any action of the SDK's own does. The child runs in the SDK with no callback, so it is
    said as a gap, its spending at the scope of its parent's tree, and its step asks the runtime as its parent's
    would."""
    task = ToolCall("task", {"description": "make it", "prompt": "Make the file.", "subagent_type": "general-purpose"})
    replies = (task, ToolCall("terminal", {"command": "touch made-by-the-child"}, id="call_child"), "made", "done")

    async with FakeModel(*replies) as model:
        spec = on_fake_model(tmp_path, model, goal="hand it on", allow_native_children=True)
        driver = OpenHandsDriver()
        heard = Allowing(driver)
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    asked = [report.gist for report in heard.of(ApprovalRequested)]
    assert "task" in model.calls[0].tools
    assert (spec.cwd / "made-by-the-child").exists()
    assert len(asked) == 2 and asked[0].startswith("task ") and "touch made-by-the-child" in asked[1]
    assert any(gap.what == "native_child_unattributed" for gap in heard.of(GapReport))
    assert not heard.of(ChildSeen)
    trees = [usage.tokens for usage in heard.of(Usage) if usage.scope == "tree"]
    calls = [usage.tokens for usage in heard.of(Usage) if usage.scope == "call"]
    assert (sum(trees), sum(calls)) == (2 * SPENT, 2 * SPENT)
    assert len(heard.of(ModelCall)) == 2


async def test_a_message_waits_while_an_approval_is_open_and_lands_after_what_was_decided(tmp_path):
    """A message the SDK took while it waited would supersede the action, or come between a call and its result."""
    async with FakeModel(ToolCall("terminal", {"command": "touch ran"}, id="call_term"), "done") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(spec, heard)
        asked = await heard.until(ApprovalRequested)
        await driver.deliver(Delivery(input="41", boundary="model_call", text="the word is cinnabar", items=()))
        await driver.answer(asked.id, "allow")
        delivered = await heard.until(InputDelivered)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    carried = next(call for call in model.calls if call.says("cinnabar"))
    said = [json.dumps(message) for message in carried.json["messages"]]
    result = next(n for n, message in enumerate(said) if "call_term" in message and '"tool"' in message)
    assert (spec.cwd / "ran").exists()
    assert (delivered.input, delivered.boundary, delivered.evidence) == ("41", "model_call", "request")
    assert result < next(n for n, message in enumerate(said) if "cinnabar" in message)


async def test_a_condensation_names_what_it_forgot_and_its_own_call(tmp_path):
    """OpenHands' own condenser, which forgets once its view holds more than 80 events."""
    thinking = [ToolCall("think", {"thought": f"step {n}"}, id=f"call_{n}") for n in range(40)]
    summary = "SUMMARY of the steps so far"

    async with FakeModel(*thinking, summary, "done") as model:
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="think a while"), heard)
        compacted = await heard.until(Compacted)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    condensing = [call for call in heard.of(ModelCall) if call.purpose == "condenser"]
    assert compacted.summary == summary and compacted.forgotten
    assert len(condensing) == 1 and condensing[0].call_id is not None
    assert model.calls[-1].says(summary) and not model.calls[-1].says('"step 1"')
    assert sum(usage.tokens or 0 for usage in heard.of(Usage)) == len(model.calls) * SPENT


async def test_a_resumed_harness_knows_what_landed_after_a_kill(tmp_path):
    landed = Delivery(input="41", boundary="turn", text=f"{delivery_heading(41)}\n- remember heliotrope", items=())

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model)
        first, heard = OpenHandsDriver(), Heard()
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

        second, heard = OpenHandsDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        try:
            assert await second.reconcile("41") == "landed"
            assert await second.reconcile("4") == "unknown"
        finally:
            await second.stop(2.0)

    assert (delivered.boundary, delivered.evidence) == ("turn", "request")


async def test_a_tool_a_kill_cut_off_is_not_run_again_on_resume_and_the_model_is_told(tmp_path):
    """The SDK runs an action that has no result when it next runs, so the worker answers it before then."""
    command = ToolCall("terminal", {"command": "echo ran >> ran; echo $$ > pipe; exec sleep 600"}, id="call_dangling")

    async with FakeModel(command, "ok") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        os.mkfifo(spec.cwd / "pipe")
        first = OpenHandsDriver()
        heard = Allowing(first)
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await asyncio.to_thread((spec.cwd / "pipe").read_text)
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, signal.SIGKILL)
        await heard.until(Exited)
        await first.stop(2.0)

        second, heard = OpenHandsDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        await second.deliver(Delivery(input="41", boundary="turn", text="carry on", items=()))
        await heard.until(TurnEnded)
        await second.stop(2.0)

    assert (spec.cwd / "ran").read_text() == "ran\n"
    results = [message for message in model.calls[-1].json["messages"] if message["role"] == "tool"]
    assert "not run again" in json.dumps(results[-1])


async def test_a_resume_of_a_conversation_that_is_not_there_is_refused(tmp_path):
    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model)
        second, heard = OpenHandsDriver(), Heard()
        with pytest.raises(DriverError, match="no conversation"):
            await second.start(spec.model_copy(update={"resume": "8d6f1b3c-0f5e-4a8f-9a55-3c1f1f0b9d2e"}), heard)
        await second.stop(2.0)


async def test_a_person_s_message_reaches_the_request_that_carried_it(tmp_path, monkeypatch):
    async with FakeModel("heard you") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "the word is cinnabar")
            await until(lambda: of_type(session, "turn.ended"), session)
            delivered = await of_type(session, "context.delivered")
            started = (await of_type(session, "agent.started"))[0]

    assert model.calls[0].says("cinnabar")
    assert [(event.data["boundary"], event.data["evidence"]) for event in delivered] == [("turn", "request")]
    assert started.data["effective_model"] == MODEL and started.data["declared"]["approvals"] == "native"
    assert started.data["verified"]["tools"] == "visible"


async def test_a_real_harness_calls_our_tools_parks_wakes_and_resumes_in_a_session(tmp_path, monkeypatch):
    replies = (ToolCall("wait", {"from": ["@you"]}, id="call_wait"), "waiting for you", "woken", "resumed")

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

    assert model.calls[0].offers("wait")
    assert model.calls[-1].says("cinnabar")
    assert sum(event.data["tokens"] or 0 for event in usages) == len(model.calls) * SPENT


async def test_a_role_s_approval_policy_answers_openhands(tmp_path, monkeypatch):
    async with FakeModel(ToolCall("terminal", {"command": "touch ran"}, id="call_term"), "done") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, approvals="deny")

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "touch it")
            await until(lambda: of_type(session, "turn.ended"), session)
            decided = [event for event in await of_type(session, "item.recorded") if event.data["approval"] is not None]

    assert not (tmp_path / "ran").exists()
    assert decided[0].data["outcome"] == "rejected"
    assert model.calls[1].says("The runtime denied this.")


async def test_an_openhands_agent_and_a_scripted_one_exchange_messages_through_our_tools(tmp_path, monkeypatch):
    replies = (ToolCall("message_send", {"to": "@lead", "gist": "pong from bob"}, id="call_send"), "sent it")

    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        lead = {"harness": f"{__name__}:pinging"}
        roles = {"lead": lead, "bob": team.roles["bob"].model_dump(exclude_defaults=True)}
        edges = {"lead": ["role:bob"], "bob": ["role:lead"]}
        topology = {"edges": edges, "limits": {"max_hops": 4}}
        team = Team.model_validate({"roles": roles, "auth": team.canonical()["auth"], "topology": topology})

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await session.send("@lead", "go")
            ending = await session.settled(timeout=TIMEOUT)
            sent = await of_type(session, "message.sent")

    said = [(event.actor, event.gist) for event in sent if event.actor in ("agent:lead", "agent:bob")]
    assert ending.reason == "settled", ending
    assert ("agent:lead", "ping") in said and ("agent:bob", "pong from bob") in said
    assert model.calls[0].says("ping") and model.calls[0].offers("message_send")


def pinging() -> ScriptedDriver:
    """A lead that pings @bob and waits for its answer."""
    return ScriptedDriver(
        [
            [Call("message_send", {"to": "@bob", "gist": "ping"}), Call("wait", {"from": ["@bob"]})],
            [Call("agent_finish", {})],
        ]
    )


async def test_no_credential_reaches_the_agent_s_terminal_or_folder_and_it_leaves_its_workspace_as_it_was(
    tmp_path, monkeypatch
):
    """The worker exits on its own at the owner's stop, so the stop says no gap."""
    async with FakeModel(ToolCall("terminal", {"command": "env"}, id="call_env"), "done") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, approvals="allow")
        work = tmp_path / "work"
        work.mkdir()

        async with Session.start(team, name="clean", root=tmp_path, cwd=work) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "say your environment")
            await until(lambda: of_type(session, "turn.ended"), session)

    async with Session.attach("clean", root=tmp_path) as session:
        gaps = [event.data["what"] for event in await of_type(session, "gap.recorded")]

    shown = json.dumps(model.calls[1].json["messages"][-1])
    assert "TMPDIR=" in shown
    assert "dummy-key" not in shown and "PLATOON_HARNESS_TOKEN" not in shown and "OPENAI_BASE_URL" not in shown
    held = [path for path in (tmp_path / "sessions").rglob("*") if path.is_file() and b"dummy-key" in path.read_bytes()]
    assert held == []
    assert sorted(path.name for path in work.iterdir()) == []
    assert gaps == []


async def test_what_the_journal_says_a_harness_was_told_is_what_it_sent_its_model(tmp_path, monkeypatch):
    """The text journaled at launch is in the first request whole, once, beside whatever the harness says itself, with
    our tools by their own names."""
    async with FakeModel("kestrel, done") as model:
        role = {"preamble": f"{PREAMBLE}\nA team of one.", "instructions": TOLD}
        team = keyed(tmp_path / "home", model, monkeypatch, **role)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await until(lambda: of_type(session, "turn.ended"), session)
            instructed = await of_type(session, "agent.instructed")
            told = (await session.get_body(instructed[0].data["instructions"])).decode()

    assert told.endswith("A team of one.\n\nBegin every reply with the word kestrel, then use `peers`.")
    assert sum(text.count(told) for text in strings(model.calls[0].json)) == 1


async def test_what_the_journal_says_a_resumed_harness_was_told_is_what_it_sent_its_model(tmp_path, monkeypatch):
    """A conversation keeps the system prompt it began with, which the runtime hands it again on a resume, and that
    text is in the request after the resume whole, once."""
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


async def test_a_steer_an_interrupt_cut_off_is_offered_again_and_reaches_the_model(tmp_path, monkeypatch):
    """What the conversation took and never sent a model is offered again once its turn is interrupted. OpenHands keeps
    a message it was handed, so the model hears it once more than it was sent."""
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
    assert model.calls[1].message.body.decode().count("cinnabar") == 2


def taken_twice(finished: list[Any]) -> bool:
    """Whether a wake and a steer have both been handed over."""
    return len([event for event in finished if event.data["kind"] == "deliver"]) == 2


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
    """OpenHands' calls reach us through the shim, whose id is its own and no item's, so no tool item holds the
    anchor."""
    async with FakeModel(ToolCall("agent_spawn", clients.SPAWN, id="call_spawn"), "spawned it") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        spawned, under = await clients.a_spawn_and_the_call_that_made_it(team, tmp_path)

    assert (list(spawned.native), under) == (["platoon-harness/callId"], [])


async def test_the_tui_sends_from_its_composer_and_draws_the_reply_once(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.the_tui_sends_from_its_composer_and_draws_the_reply_once(team, tmp_path)
