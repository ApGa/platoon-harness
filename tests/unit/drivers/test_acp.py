"""The ACP driver, on a stand-in agent that speaks the real frames: what it negotiates, and what each frame becomes."""

import json
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import __version__
from platoon_harness.config import Secret
from platoon_harness.drivers import (
    ApprovalRequested,
    Compacted,
    Delivery,
    DriverError,
    Exited,
    GapReport,
    InputDelivered,
    Item,
    Native,
    Ready,
    TurnEnded,
)
from platoon_harness.drivers.levels import Check, Conformance, Profile, implementation, levels
from platoon_harness.testing import FakeModel
from platoon_harness.testing.conformance import _CHECKS
from platoon_harness_acp import CAPABILITIES, AcpDriver, OpenCodeDriver

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

GRACE = 5.0
FAKE = Path(__file__).with_name("fake_acp.py")
OPTIONS = [
    {"optionId": "once", "kind": "allow_once", "name": "Allow once"},
    {"optionId": "always", "kind": "allow_always", "name": "Always allow"},
    {"optionId": "reject", "kind": "reject_once", "name": "Reject"},
]


def update(said: str, **fields: Any) -> dict[str, Any]:
    return {
        "say": {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": "$session", "update": {"sessionUpdate": said, **fields}},
        }
    }


def ask(call: dict[str, Any], options: list[dict[str, Any]] = OPTIONS) -> dict[str, Any]:
    return {"ask": {"sessionId": "$session", "toolCall": call, "options": options}}


class Agent:
    """A stand-in agent on a script, and what it heard, frame by frame."""

    def __init__(self, folder: Path, **script: Any) -> None:
        self.script, self.log = folder / "script.json", folder / "heard.jsonl"
        self.script.write_text(json.dumps(script))

    def driver(self) -> AcpDriver:
        return AcpDriver([sys.executable, "-I", str(FAKE), str(self.script), str(self.log)])

    def heard(self, method: str | None = None) -> list[dict[str, Any]]:
        frames = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return [frame for frame in frames if method is None or frame.get("method") == method]

    def answers(self) -> list[dict[str, Any]]:
        """What the driver answered each permission request with."""
        return [frame["result"]["outcome"] for frame in self.heard() if str(frame.get("id")).startswith("ask-")]


async def test_protocol_1_is_negotiated_and_anything_else_disconnects(tmp_path):
    """It asks for protocol 1 with no file system and no terminal, takes an agent that answers 1, and stops one that
    answers anything else before opening a session, as ACP has a client disconnect from a version it does not speak."""
    agent, heard = Agent(tmp_path, protocol=2), Heard()

    with pytest.raises(DriverError, match="it speaks ACP protocol 2, and this driver 1 alone"):
        await agent.driver().start(make_spec(tmp_path, goal=""), heard)

    await heard.until(Exited)
    [hello] = agent.heard("initialize")
    assert hello["params"]["protocolVersion"] == 1
    assert hello["params"]["clientCapabilities"]["fs"] == {"readTextFile": False, "writeTextFile": False}
    assert hello["params"]["clientCapabilities"]["terminal"] is False
    assert agent.heard("session/new") == []

    (tmp_path / "speaks").mkdir()
    agent, heard = Agent(tmp_path / "speaks", protocol=1), Heard()
    driver = agent.driver()
    await driver.start(make_spec(tmp_path, goal=""), heard)
    ready = await heard.until(Ready)
    await driver.stop(GRACE)

    assert (ready.native, ready.version) == ("s-1", "9.9.9")
    assert [frame["params"]["cwd"] for frame in agent.heard("session/new")] == [str(tmp_path)]


async def test_an_unknown_update_keeps_its_raw_frame_and_a_gap(tmp_path):
    """An update of a kind nothing here maps, and a line that is no frame at all, are kept raw, each with a gap, and the
    turn goes on to its end, as what the agent said around them is reported as usual."""
    turn = [
        update("subagent_update", childSessionId="s-2", note="kept"),
        {"say": "this is no frame"},
        update("agent_message_chunk", content={"type": "text", "text": "still here"}, messageId="m-1"),
    ]
    agent, heard = Agent(tmp_path, turns=[turn]), Heard()
    driver = agent.driver()
    await driver.start(make_spec(tmp_path), heard)

    await heard.until(TurnEnded)
    await driver.stop(GRACE)

    [unknown] = heard.of(Native)[:1]
    assert unknown.kind == "session/update subagent_update"
    assert '"childSessionId": "s-2"' in unknown.raw and '"note": "kept"' in unknown.raw
    assert any(native.raw == "this is no frame" for native in heard.of(Native))
    assert [gap.what for gap in heard.of(GapReport)] == ["unknown_update", "unknown_update"]
    assert [(item.kind, item.body) for item in heard.of(Item)] == [("message", "still here")]
    assert heard.of(TurnEnded)[0].reason == "stopped"


async def test_permission_requests_go_through_the_runtime_s_approvals_with_their_tool_call_as_the_ask(tmp_path):
    """A request that names its tool call by id alone asks what the agent last said of that call, which is its whole
    ask; the verdict goes back as the option of its kind for this once, never `always`; one that says nothing of what it
    would do carries no ask and says so; where no option is of the verdict's kind, and for one an interrupt cuts short,
    the answer is `cancelled`; and the tool's end names the approval that let it through."""
    command = "touch é 日本 " + " ".join(f"part{n:04d}" for n in range(600))
    first = [
        update("tool_call", toolCallId="call_1", title="shell", kind="execute", status="pending", rawInput={}),
        update("tool_call_update", toolCallId="call_1", title=command[:20], rawInput={"command": command}),
        ask({"toolCallId": "call_1"}),
        update(
            "tool_call_update",
            toolCallId="call_1",
            status="completed",
            content=[{"type": "content", "content": {"type": "text", "text": "done"}}],
        ),
    ]
    second = [
        ask({"toolCallId": "call_2", "title": "mystery"}),
        ask(
            {"toolCallId": "call_3", "rawInput": {}}, [option for option in OPTIONS if option["kind"] == "allow_always"]
        ),
    ]
    third = [ask({"toolCallId": "call_4", "rawInput": {"command": "sleep 1"}}), {"wait": True}]
    agent, heard = Agent(tmp_path, turns=[first, second, third]), Heard()
    driver = agent.driver()
    await driver.start(make_spec(tmp_path), heard)

    asked = await heard.until(ApprovalRequested)
    await driver.answer(asked.id, "allow")
    done = await heard.until(Item, lambda item: item.phase == "completed")

    assert asked.body is not None and json.loads(asked.body) == {
        "title": command[:20],
        "kind": "execute",
        "rawInput": {"command": command},
    }
    assert (done.native_id, done.approval, done.outcome, done.body) == ("call_1", asked.id, "completed", "done")

    await driver.deliver(Delivery(input="2", boundary="turn", text="again", items=()))
    silent = await heard.until(ApprovalRequested, lambda report: report.id != asked.id)
    await driver.answer(silent.id, "deny")
    always = await heard.until(ApprovalRequested, lambda report: report.id not in (asked.id, silent.id))
    await driver.answer(always.id, "allow")
    await heard.until(TurnEnded, lambda ended: len(heard.of(TurnEnded)) == 2)

    assert silent.body is None and silent.gist == "mystery, which says nothing more of what it would do"
    assert always.body is not None

    await driver.deliver(Delivery(input="3", boundary="turn", text="once more", items=()))
    cut = await heard.until(ApprovalRequested, lambda report: report.id not in (asked.id, silent.id, always.id))
    await driver.interrupt()
    await heard.until(TurnEnded, lambda ended: len(heard.of(TurnEnded)) == 3)
    await driver.stop(GRACE)

    assert cut.body is not None and heard.of(TurnEnded)[2].reason == "interrupted"
    assert agent.answers() == [
        {"outcome": "selected", "optionId": "once"},
        {"outcome": "selected", "optionId": "reject"},
        {"outcome": "cancelled"},
        {"outcome": "cancelled"},
    ]


async def test_steering_is_refused_until_a_fixture_passes(tmp_path):
    """Only the turn is declared, a delivery for any other boundary is refused, saying why, and one that comes during a
    turn goes as the next prompt only once the turn's own has been answered."""
    held = [ask({"toolCallId": "call_1", "rawInput": {}})]
    agent, heard = Agent(tmp_path, turns=[held, []]), Heard()
    driver = agent.driver()
    await driver.start(make_spec(tmp_path), heard)
    asked = await heard.until(ApprovalRequested)

    for boundary in ("tool", "model_call"):
        with pytest.raises(DriverError, match="no fixture has shown an agent taking a prompt during a turn"):
            await driver.deliver(Delivery(input="steer", boundary=boundary, text="now", items=()))
    await driver.deliver(Delivery(input="next", boundary="turn", text="after", items=()))
    prompts_before = len(agent.heard("session/prompt"))
    await driver.answer(asked.id, "allow")
    landed = await heard.until(InputDelivered, lambda delivered: delivered.input == "next")
    await heard.until(TurnEnded, lambda ended: len(heard.of(TurnEnded)) == 2)
    await driver.stop(GRACE)

    frames = agent.heard()
    answered = next(index for index, frame in enumerate(frames) if frame.get("id") == "ask-1")
    prompts = [index for index, frame in enumerate(frames) if frame.get("method") == "session/prompt"]
    assert CAPABILITIES.boundaries == {"turn"} and landed.boundary == "turn"
    assert prompts_before == 1 and prompts[0] < answered < prompts[1]
    assert [frames[index]["params"]["prompt"][0]["text"] for index in prompts] == ["do the thing", "after"]


async def test_an_interrupt_before_a_prompt_goes_sends_none(tmp_path):
    """A delivery whose prompt has not gone reached nothing, so an interrupt drops it and no turn begins, and the
    runtime offers it again."""
    agent, heard = Agent(tmp_path, turns=[[]]), Heard()
    driver = agent.driver()
    await driver.start(make_spec(tmp_path, goal=""), heard)
    await heard.until(Ready)

    await driver.deliver(Delivery(input="dropped", boundary="turn", text="never", items=()))
    await driver.interrupt()
    await driver.deliver(Delivery(input="kept", boundary="turn", text="this", items=()))
    await heard.until(TurnEnded)
    await driver.stop(GRACE)

    assert [delivered.input for delivered in heard.of(InputDelivered)] == ["kept"]
    assert [frame["params"]["prompt"][0]["text"] for frame in agent.heard("session/prompt")] == ["this"]
    assert await driver.reconcile("dropped") == "unknown"


async def test_acp_levels_never_reach_trainable(tmp_path):
    """Even on a gateway login with our tools seen and every check passed, as it declares no sealed launch and no id of
    a model call, and it refuses a gateway outright."""
    every = tuple(Check(name=definition.name, state="passed") for definition in _CHECKS)
    for driver in (OpenCodeDriver(), Agent(tmp_path, turns=[]).driver()):
        made = implementation(driver)
        result = Conformance(
            driver=driver.name,
            implementation=made,
            version="1",
            sdk=__version__,
            host=socket.gethostname(),
            checks=every,
        )
        profile = Profile(driver=driver.name, implementation=made, version="1", login="gateway", tools="visible")

        earned = levels(driver.describe().capabilities, profile, result)

        assert (earned.operational.state, earned.observable.state, earned.trainable.state) == ("met", "met", "unmet")
        assert "it has no sealed launch, so the user's own setup reaches the policy" in earned.trainable.reasons
        assert "it cannot tie a model call to an agent" in earned.trainable.reasons
    async with FakeModel() as model:
        with pytest.raises(DriverError, match="sealed launch"):
            await AcpDriver(["true"]).start(make_spec(tmp_path, access=model.gateway("bearer"), model="m"), Heard())


async def test_a_compaction_is_reported_with_what_it_forgot_unknown(tmp_path):
    """Its summary, said in chunks or whole, takes the place of what it forgot, which ACP does not name."""
    turn = [
        update("compaction_summary_chunk", compactionId="c-1", content={"type": "text", "text": "so far, "}),
        update("compaction_summary_chunk", compactionId="c-1", content={"type": "text", "text": "this"}),
        update("compaction_update", compactionId="c-1", status="completed"),
        update("compaction_update", compactionId="c-2", status="failed"),
    ]
    agent, heard = Agent(tmp_path, turns=[turn]), Heard()
    driver = agent.driver()
    await driver.start(make_spec(tmp_path), heard)

    await heard.until(TurnEnded)
    await driver.stop(GRACE)

    assert [(report.forgotten, report.summary) for report in heard.of(Compacted)] == [(None, "so far, this")]
    assert agent.heard("initialize")[0]["params"]["clientCapabilities"]["session"] == {"compaction": {}}


async def test_opencode_refuses_a_start_with_no_model(tmp_path):
    """OpenCode with no model set sends prompts to a hosted model nobody chose."""
    with pytest.raises(DriverError, match="set a model"):
        await OpenCodeDriver().start(make_spec(tmp_path, access={"KEY": Secret("k")}, model=None), Heard())
    with pytest.raises(DriverError, match="set a model"):
        await OpenCodeDriver().start(make_spec(tmp_path), Heard())
