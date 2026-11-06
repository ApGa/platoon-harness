"""The `openhands` driver on the real OpenHands SDK against FakeModel. Free: a dummy key, an isolated home, and loopback
only. The dev environment holds the SDK's `openhands` extra, so these never skip.

No live model has run through this driver: all of this is what the SDK did on FakeModel, but for one rule of the
worker's turns, held on a stand-in of the SDK in a process of its own, where it takes the place of the worker's module
that loads the SDK.
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Role, Session, Team, __version__
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
from platoon_harness.drivers.levels import Conformance, Profile, implementation, levels
from platoon_harness.drivers.openhands import OpenHandsDriver
from platoon_harness.drivers.process import Record
from platoon_harness.runtime.paths import write_conformance
from platoon_harness.team import AuthProfile, Command
from platoon_harness.testing import (
    ENVIRONMENT_TOOL,
    ENVIRONMENT_TOOLS,
    TOOL,
    Call,
    FakeModel,
    FakeTools,
    ScriptedDriver,
    Stall,
    Text,
    ToolCall,
    chat_access,
    check_harness,
    goal,
)
from platoon_harness.testing.loopback import Loopback, Message, answer
from platoon_harness.testing.model import COMPACTION_HEADERS, INPUT_TOKENS, OUTPUT_TOKENS
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
    """The worker, given longer than a binary to come up, as it loads the SDK first."""
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


TASK = ToolCall("task", {"description": "make it", "prompt": "Make the file.", "subagent_type": "general-purpose"})


async def conformance(folder: Path) -> Conformance:
    return await check_harness("openhands", folder)


@pytest.mark.timeout(1200)
async def test_the_openhands_driver_conforms(tmp_path, monkeypatch):
    result = await conformance(tmp_path / "check")

    print(result)
    assert result.failed == (), str(result)
    assert (result.driver, result.version) == ("openhands", PINNED)
    skipped = {check.name for check in result.checks if check.state == "skipped"}
    assert skipped == {"tool_item_carries_its_anchor", "native_child_seen", "one_shot_exits", "declared_but_unproven"}
    profile = Profile(driver="openhands", implementation=implementation(OpenHandsDriver()), version=PINNED)
    earned = levels(OpenHandsDriver().describe().capabilities, profile, result)
    assert earned.operational.state == "met", earned.operational.reasons
    assert earned.observable.state == "met", earned.observable.reasons
    assert earned.trainable.state == "unmet"

    write_conformance(tmp_path, result)
    async with FakeModel() as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            started = (await of_type(session, "agent.started"))[0]

    assert started.data["levels"]["operational"]["state"] == "met", started.data["levels"]["operational"]


def on_fake_model(tmp_path: Path, fake: FakeModel, **fields: Any) -> AgentSpec:
    """An agent in a home of its own, reaching FakeModel by key."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    given = access(tmp_path / "home")(fake)
    spec = {"agent": "ada", "role": "worker", "goal": "", "cwd": work, "folder": tmp_path / "ada", "model": MODEL}
    fields = {**spec, "access": given, **fields}
    return AgentSpec.model_validate({**fields, "goal": goal(fields["goal"])})


def keyed(home: Path, model: FakeModel, monkeypatch: pytest.MonkeyPatch, **role: Any) -> Team:
    """One agent on the worker, reaching FakeModel the way an auth profile would, in a home of its own."""
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENAI_BASE_URL", f"{model.url}/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    bob = Role(**{"harness": "openhands", "model": MODEL, "auth": "fake", **role})
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
    spec = AgentSpec(agent="ada", role="worker", goal=goal("go"), cwd=tmp_path / "work", folder=tmp_path / "ada")
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
    would. It writes no log of its calls where it works."""
    replies = (TASK, ToolCall("terminal", {"command": "touch made-by-the-child"}, id="call_child"), "made", "done")

    async with FakeModel(*replies) as model:
        spec = on_fake_model(tmp_path, model, goal="hand it on", allow_native_children=True)
        driver = OpenHandsDriver()
        heard = Allowing(driver)
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    asked = [report.gist for report in heard.of(ApprovalRequested)]
    assert "task" in model.calls[0].tools
    assert sorted(path.name for path in spec.cwd.iterdir()) == ["made-by-the-child"]
    assert len(asked) == 2 and asked[0].startswith("task ") and "touch made-by-the-child" in asked[1]
    assert any(gap.what == "native_child_unattributed" for gap in heard.of(GapReport))
    assert not heard.of(ChildSeen)
    trees = [usage.tokens for usage in heard.of(Usage) if usage.scope == "tree"]
    calls = [usage.tokens for usage in heard.of(Usage) if usage.scope == "call"]
    assert (sum(trees), sum(calls)) == (2 * SPENT, 2 * SPENT)
    assert len(heard.of(ModelCall)) == 2


async def test_an_interrupt_stops_its_own_agent_at_its_next_ask_and_nothing_asks_outside_a_turn(tmp_path):
    """The task tool lets a child run on past its parent's interrupt, so its next ask stops it, and the next turn's call
    is the parent's, carrying what it was handed."""
    replies = (TASK, ToolCall("terminal", {"command": "touch made-by-the-child"}, id="call_child"), "heard you")

    async with FakeModel(*replies) as model:
        spec = on_fake_model(tmp_path, model, goal="hand it on", allow_native_children=True)
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(spec, heard)
        task = await heard.until(ApprovalRequested)
        await driver.answer(task.id, "allow")
        await heard.until(ApprovalRequested, lambda asked: asked is not task)
        await driver.interrupt()
        cut = await heard.until(TurnEnded)
        await driver.deliver(Delivery(input="42", boundary="turn", text="the word is cinnabar", items=()))
        await heard.until(TurnEnded, lambda ended: ended is not cut)
        await driver.stop(2.0)

    assert cut.reason == "interrupted" and len(heard.of(ApprovalRequested)) == 2
    assert not (spec.cwd / "made-by-the-child").exists()
    assert len(model.calls) == 3 and model.calls[2].says("cinnabar")


async def test_a_message_waits_while_an_approval_is_open_and_lands_after_what_was_decided(tmp_path):
    """A message the SDK took while it waited would supersede the action, or come between a call and its result."""
    async with FakeModel(ToolCall("terminal", {"command": "touch ran"}, id="call_term"), "done") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(spec, heard)
        asked = await heard.until(ApprovalRequested)
        await driver.deliver(Delivery(input="41", boundary="model_call", text="the word is cinnabar", items=()))
        await driver.answer(asked.id, "allow")
        delivered = await heard.until(InputDelivered, lambda landed: landed.input == "41")
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    carried = next(call for call in model.calls if call.says("cinnabar"))
    said = [json.dumps(message) for message in carried.json["messages"]]
    result = next(n for n, message in enumerate(said) if "call_term" in message and '"tool"' in message)
    assert (spec.cwd / "ran").exists()
    assert (delivered.input, delivered.boundary, delivered.evidence) == ("41", "model_call", "request")
    assert result < next(n for n, message in enumerate(said) if "cinnabar" in message)


async def test_a_message_during_a_model_call_that_asks_waits_for_the_runtime_s_answer(tmp_path):
    """The SDK rejects what a step asks to run once a message came during its model call, unasked, so nothing goes to
    the conversation while a run goes on: the run pauses after its step, and the message lands after the result."""
    gated = ToolCall("terminal", {"command": "touch ran"}, id="call_term")

    async with FakeModel([Stall(), gated], "done") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        driver = OpenHandsDriver()
        heard = Allowing(driver)
        await driver.start(spec, heard)
        await asyncio.wait_for(model.call(0), TIMEOUT)
        await driver.deliver(Delivery(input="41", boundary="model_call", text="the word is cinnabar", items=()))
        model.release()
        delivered = await heard.until(InputDelivered, lambda landed: landed.input == "41")
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    carried = next(call for call in model.calls if call.says("cinnabar"))
    said = [json.dumps(message) for message in carried.json["messages"]]
    result = next(n for n, message in enumerate(said) if "call_term" in message and '"tool"' in message)
    assert (spec.cwd / "ran").exists() and len(heard.of(ApprovalRequested)) == 1
    assert (delivered.input, delivered.boundary, delivered.evidence) == ("41", "model_call", "request")
    assert result < next(n for n, message in enumerate(said) if "cinnabar" in message)


async def test_an_allow_an_interrupt_cuts_off_leaves_no_action_for_the_next_turn(tmp_path):
    """An action a turn left pending would run at the next run, after its message, between a call and its result, which
    no provider takes. Sent together, the allow or the interrupt may come first, and either way the action is answered
    in its own turn."""
    async with FakeModel(ToolCall("terminal", {"command": "touch ran"}, id="call_term"), "next") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(spec, heard)
        asked = await heard.until(ApprovalRequested)
        await asyncio.gather(driver.answer(asked.id, "allow"), driver.interrupt())
        cut = await heard.until(TurnEnded)
        await driver.deliver(Delivery(input="42", boundary="turn", text="something else now", items=()))
        await heard.until(TurnEnded, lambda ended: ended is not cut)
        await driver.stop(2.0)

    messages = model.calls[-1].json["messages"]
    roles = [message["role"] for message in messages]
    result = json.dumps(messages[roles.index("tool")])
    assert cut.reason == "interrupted" and roles.index("tool") == roles.index("assistant") + 1
    assert "The turn ended before this ran." not in result or not (spec.cwd / "ran").exists()


async def test_an_interrupt_while_an_approval_is_open_cuts_off_no_call_and_the_action_never_runs(tmp_path):
    """No run was under way, so the turn's usage is whole, and the model hears in its next turn why the action did not
    run."""
    async with FakeModel(ToolCall("terminal", {"command": "touch ran"}, id="call_term"), "next") as model:
        spec = on_fake_model(tmp_path, model, goal="go")
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(spec, heard)
        await heard.until(ApprovalRequested)
        await driver.interrupt()
        cut = await heard.until(TurnEnded)
        await driver.deliver(Delivery(input="42", boundary="turn", text="something else now", items=()))
        await heard.until(TurnEnded, lambda ended: ended is not cut)
        await driver.stop(2.0)

    assert cut.reason == "interrupted" and not heard.of(GapReport)
    assert not (spec.cwd / "ran").exists() and model.calls[-1].says("The turn ended before this ran.")


LAST_TICKS = """
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from platoon_harness.config import Secret
from platoon_harness.drivers import AgentSpec, Delivery

agent = SimpleNamespace(ready=lambda *_: ((), (), None), pending=lambda _: [])
sys.modules["platoon_harness.drivers.openhands.agent"] = agent
from platoon_harness.drivers.openhands.worker import Worker


class Conversation:
    '''Of a conversation, what the worker touches: a run that finishes at once, a message that makes a finished one idle
    again, and, after the first run, a delivery `ticks` turns of the loop later.'''

    def __init__(self, worker, ticks):
        self.state = SimpleNamespace(execution_status=SimpleNamespace(value="idle"), events=[], active_branch=list)
        self.conversation_stats = SimpleNamespace(usage_to_metrics={})
        self.id, self.sent, self.ran_late = "c", [], asyncio.Event()
        self._worker, self._ticks = worker, ticks

    def send_message(self, text):
        self.sent.append(text)
        if self.state.execution_status.value == "finished":
            self.state.execution_status.value = "idle"

    async def arun(self):
        if "late" in self.sent:
            self.ran_late.set()
        self.state.execution_status.value = "finished"
        if self.sent == ["first"]:
            self._later(self._ticks)

    def _later(self, ticks):
        if ticks:
            asyncio.get_running_loop().call_soon(self._later, ticks - 1)
        else:
            late = Delivery(input="42", boundary="model_call", text="late", items=())
            asyncio.ensure_future(self._worker.deliver(late))

    def pause(self):
        pass

    def interrupt(self):
        pass

    def close(self):
        pass


async def ran(ticks, folder):
    worker = Worker()
    conversation = Conversation(worker, ticks)
    agent.start = lambda *_, **__: conversation
    spec = {"agent": "ada", "role": "worker", "cwd": folder, "folder": folder / str(ticks), "model": "m"}
    heard = []

    async def report(said):
        heard.append(said)

    await worker.start(AgentSpec.model_validate({**spec, "access": {"OPENAI_API_KEY": Secret("k")}}), report)
    await worker.deliver(Delivery(input="41", boundary="turn", text="first", items=()))
    try:
        await asyncio.wait_for(conversation.ran_late.wait(), 5)
    except TimeoutError:
        return False
    finally:
        await worker.stop(1.0)
    return True


async def main(folder):
    print(json.dumps({ticks: await ran(ticks, folder) for ticks in range(8)}))


asyncio.run(main(Path(sys.argv[1])))
"""
"""A program for a process of its own: whether a delivery that came that many turns of the loop after a turn's last run
returned was run by a run after it."""


async def test_a_delivery_that_comes_as_a_turn_ends_is_run(tmp_path):
    """One that came in the last ticks of a turn reached the conversation after the turn read its status, and no run
    came after it."""
    command = [sys.executable, "-I", "-c", LAST_TICKS, str(tmp_path)]
    done = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True, timeout=TIMEOUT)

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.splitlines()[-1]) == {str(ticks): True for ticks in range(8)}


async def test_a_failed_model_call_is_not_retried_and_ends_the_turn_with_the_sdk_s_error(tmp_path):
    """A retry is a second call a gateway records, so the SDK makes none, and nobody measured the call that failed."""
    asked = []

    async def fail(message: Message, _: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        asked.append(message.target)
        writer.write(answer(500, b'{"error": {"message": "the model fell over"}}'))
        return True

    async with Loopback(fail) as server:
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, server, goal="go"), heard)
        ended = await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert (len(asked), ended.reason) == (1, "LLMServiceUnavailableError")
    assert any(gap.what == "usage_lower_bound" for gap in heard.of(GapReport))


async def test_a_run_the_sdk_finds_repeating_itself_ends_the_turn_stuck_and_whole(tmp_path):
    thinking = [ToolCall("think", {"thought": "again"}, id=f"call_{n}") for n in range(4)]

    async with FakeModel(*thinking, "never asked for") as model:
        driver, heard = OpenHandsDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go"), heard)
        ended = await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert (ended.reason, len(model.calls)) == ("stuck", 4)
    assert not heard.of(GapReport)


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

    condensing = [call for call in heard.of(ModelCall) if call.purpose == "compaction"]
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
        delivered = await heard.until(InputDelivered, lambda landed: landed.input == "41")
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
    assert [(event.data["how"], event.data["boundary"], event.data["evidence"]) for event in delivered] == [
        ("wake", "turn", "request"),
        ("launch", "turn", "request"),
    ]
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


async def test_the_worker_named_as_a_wire_command_runs_as_from_an_environment_of_its_own(tmp_path, monkeypatch):
    """The dev environment's interpreter stands in for one of its own, named as drivers.md names it. The worker is then
    a wire program like any other, and shows our tools by their own names all the same. It goes by `openhands` and
    runs as the wire driver, so what was kept of the openhands driver's checks would say nothing of it."""
    worker = Command(command=(sys.executable, "-P", "-m", "platoon_harness.drivers.openhands"), mode="wire")

    async with FakeModel(ToolCall("session_status", {}, id="call_status"), "fine") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, harness=worker)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "how is the session?")
            await until(lambda: of_type(session, "turn.ended"), session)
            ended = await of_type(session, "turn.ended")
            started = (await of_type(session, "agent.started"))[0]
            items = [(event.gist, event.data["outcome"]) for event in await of_type(session, "item.recorded")]

    assert [event.data["reason"] for event in ended] == ["stopped"]
    verified = {"driver": "openhands", "version": PINNED, "login": "key", "tools": "visible"}
    wire = "platoon_harness.drivers.wire:WireDriver"
    pinned = {"implementation": wire, "sdk": __version__, "host": socket.gethostname()}
    assert started.data["verified"] == {**verified, **pinned, "allow_native_children": False}
    assert ("session_status completed", "completed") in items
    assert model.calls[0].offers("session_status") and "mcp__ph__" not in model.calls[0].message.body.decode()


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
            told = (await session.get_body(instructed[0].data["body"])).decode()

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
            told = [(await session.get_body(event.data["body"])).decode() for event in instructed]

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
    """A steer waits in the worker for the run to pause, and an interrupt hands it back to the runtime, which offers it
    again, so the model hears it once."""
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


def taken_twice(finished: list[Any]) -> bool:
    """Whether a wake and a steer have both been handed over."""
    return len([event for event in finished if event.data["kind"] == "deliver"]) == 2


async def test_a_tail_of_live_text_joined_to_what_was_committed_is_the_text(tmp_path, monkeypatch):
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.a_tail_joined_to_what_was_committed_is_the_text(team, tmp_path)


async def test_an_idle_harness_rests_and_its_next_message_resumes_it_natively(tmp_path, monkeypatch):
    async with FakeModel("noted", "heliotrope") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.an_idle_harness_rests_and_its_next_message_resumes_it_natively(team, tmp_path, model)


HELD = ToolCall("wait", {"from": ["@you"], "hold": 30}, id="call_held")
"""A call of our `wait` that holds, so a test can kill the worker while it is in a turn."""


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
    """OpenHands' calls reach us through the shim, whose id is its own and no item's, so no tool item holds the
    anchor."""
    async with FakeModel(ToolCall("agent_spawn", clients.SPAWN, id="call_spawn"), "spawned it") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        spawned, under = await clients.a_spawn_and_the_call_that_made_it(team, tmp_path)

    assert (list(spawned.native), under) == (["platoon-harness/callId"], [])


async def test_a_cited_write_is_traced_to_no_model_call_and_its_read_stays_unconfirmed(tmp_path, monkeypatch):
    """OpenHands' calls reach us through the shim under its own id, which no item holds, so each answer about the write
    stops at its commit, and only the handover that woke it is confirmed, by the request that carried it."""
    replies = (ToolCall("message_read", {"after": 0}, id="call_read"), ToolCall("message_send", clients.CITING), "done")
    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        traced = await clients.a_read_then_a_cited_write(team, tmp_path)

    clients.hold_their_bounds(traced, "commit")
    made = traced.lineage.made
    assert made.anchor is not None and made.anchor.key == "platoon-harness/callId"
    assert (made.item, made.call) == (None, None)
    assert [(edge.how, edge.confirmed and edge.confirmed.evidence) for edge in traced.exposure.edges] == [
        ("wake", "request")
    ]


async def test_the_tui_sends_from_its_composer_and_draws_the_reply_once(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.the_tui_sends_from_its_composer_and_draws_the_reply_once(team, tmp_path)


async def test_openhands_condenser_sends_the_headers_and_is_reported_as_compaction(tmp_path):
    """Sealed, OpenHands shows its model our tools, by their own names, the environment's, named by its server as
    OpenHands' SDK names a server's tools, so its `finish` and `think` collide with nothing, and its own `finish` and
    `think` alone: forty calls of the environment's tool take its view past what its condenser keeps, and the
    condenser's call carries the gateway's compaction headers and is reported, for that purpose, by the id the model
    gave it."""
    calls = [ToolCall(f"environment_{ENVIRONMENT_TOOL}", {"note": f"step {n}"}, id=f"call_{n}") for n in range(40)]
    async with FakeModel(*calls, "SUMMARY of the steps so far", "done") as model, FakeTools() as tools:
        gateway = model.gateway("bearer-of-ada")
        spec = on_fake_model(tmp_path, model, goal="look forty times", access=gateway, tools=tools.binding(tmp_path))
        driver = OpenHandsDriver()
        heard = Allowing(driver)
        await driver.start(spec, heard)
        ready = await heard.until(Ready)
        await heard.until(Compacted)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    compacting = [call for call in model.calls if call.carries(COMPACTION_HEADERS)]
    reported = [call for call in heard.of(ModelCall) if call.purpose == "compaction"]
    assert len(compacting) == 1 and [call.call_id for call in reported] == [compacting[0].response_id]
    assert {call.bearer for call in model.calls} == {"bearer-of-ada"}
    environment = {f"environment_{tool}" for tool in ENVIRONMENT_TOOLS}
    assert set(model.calls[0].tools) == set(ready.tools_visible or ()) == {TOOL, "finish", "think", *environment}
    assert [call.json["params"]["name"] for call in model.tool_calls] == [ENVIRONMENT_TOOL] * 40
