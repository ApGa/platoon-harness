"""ScriptedDriver: each step, its capabilities as data, and real MCP and model calls."""

import pytest

from platoon_harness import Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers import (
    ApprovalRequested,
    Capabilities,
    Delivery,
    Delta,
    Driver,
    DriverError,
    Exited,
    InputDelivered,
    Item,
    ModelCall,
    Offered,
    Ready,
    TurnEnded,
    TurnStarted,
    Usage,
)
from platoon_harness.testing import (
    TOOL,
    Ask,
    AskModel,
    Call,
    EndTurn,
    Exit,
    Fail,
    FakeModel,
    FakeTools,
    Hang,
    Say,
    ScriptedDriver,
    Think,
    ToolCall,
    Wait,
    chat_access,
)

from ..runtime.support import Gateways, in_state, of_type, scripted, until
from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)


def delivery(input: str = "d1", boundary: str = "turn", gist: str = "hello") -> Delivery:
    return Delivery(input=input, boundary=boundary, text=gist, items=(Offered(ref="inbox/ada@1", gist=gist),))


async def started(tmp_path, *turns, capabilities=None, **fields) -> tuple[ScriptedDriver, Heard]:
    options = {} if capabilities is None else {"capabilities": capabilities}
    driver, heard = ScriptedDriver(turns, **options), Heard()
    await driver.start(make_spec(tmp_path, **fields), heard)
    return driver, heard


def test_it_is_a_driver():
    assert isinstance(ScriptedDriver(), Driver)


async def test_say_streams_then_records(tmp_path):
    driver, heard = await started(tmp_path, [Say("hello there")])

    await heard.until(TurnEnded)
    await driver.stop(1)

    assert [type(report) for report in heard.reports] == [
        Ready,
        InputDelivered,
        TurnStarted,
        Delta,
        Item,
        TurnEnded,
        Exited,
    ]
    assert heard.of(InputDelivered)[0].input == "launch"
    assert (heard.of(Item)[0].kind, heard.of(Item)[0].body) == ("message", "hello there")


async def test_with_no_goal_it_waits_and_its_first_turn_is_on_a_delivery(tmp_path):
    driver, heard = await started(tmp_path, [Say("the first turn")], goal="")
    await heard.until(Ready)

    assert heard.of(TurnStarted) == []

    await driver.deliver(delivery())

    assert (await heard.until(Item)).gist == "the first turn"
    await driver.stop(1)


async def test_a_session_that_never_ended_a_turn_resumes_with_nothing_to_remember(tmp_path):
    driver, heard = ScriptedDriver(), Heard()

    await driver.start(make_spec(tmp_path, goal="", resume="scripted-ada"), heard)

    assert (await heard.until(Ready)).native == "scripted-ada"
    await driver.stop(1)


async def test_no_two_approvals_share_an_id_across_a_resume(tmp_path):
    first, heard = await started(tmp_path, [Ask("may I?")])
    asked = await heard.until(ApprovalRequested)
    await first.stop(1)

    second, again = ScriptedDriver([[Ask("may I?")]]), Heard()
    await second.start(make_spec(tmp_path, resume="scripted-ada"), again)
    await second.deliver(delivery())

    assert (await again.until(ApprovalRequested)).id != asked.id
    await second.stop(1)


async def test_think_is_a_thought(tmp_path):
    driver, heard = await started(tmp_path, [Think("hmm")])

    assert (await heard.until(Item)).kind == "thought"
    await driver.stop(1)


async def test_a_long_text_keeps_its_body_and_cuts_its_gist(tmp_path):
    driver, heard = await started(tmp_path, [Say("x" * 1000)])

    item = await heard.until(Item)
    await driver.stop(1)

    assert (len(item.gist), len(item.body)) == (280, 1000)


async def test_turns_run_one_per_delivery_and_then_run_out(tmp_path):
    driver, heard = await started(tmp_path, [Say("one")], [Say("two")])
    await heard.until(TurnEnded)

    await driver.deliver(delivery("d1"))
    await heard.until(Item, lambda item: item.gist == "two")
    await driver.deliver(delivery("d2"))
    await heard.until(InputDelivered, lambda delivered: delivered.input == "d2")
    await heard.until(TurnStarted, lambda turn: turn.turn.startswith("t3-"))
    await driver.stop(1)

    assert [turn.turn.partition("-")[0] for turn in heard.of(TurnStarted)] == ["t1", "t2", "t3"]
    assert len({turn.turn.partition("-")[2] for turn in heard.of(TurnStarted)}) == 1


async def test_a_delivery_at_a_turn_boundary_waits_for_the_turn_to_end(tmp_path):
    driver, heard = await started(tmp_path, [Wait(), Say("first")], [Say("second")])
    await heard.until(TurnStarted)

    await driver.deliver(delivery())
    await heard.until(Item, lambda item: item.gist == "second")
    await driver.stop(1)

    order = [type(report) for report in heard.reports]
    assert order.index(TurnEnded) < len(order) - order[::-1].index(InputDelivered) - 1


async def test_a_steer_lands_between_steps(tmp_path):
    driver, heard = await started(tmp_path, [Wait(), Say("after")])
    await heard.until(TurnStarted)

    await driver.deliver(delivery(boundary="tool"))

    landed = await heard.until(InputDelivered, lambda landed: landed.input != "launch")
    assert (landed.boundary, landed.evidence) == ("tool", "between_steps")
    await heard.until(Item)
    await driver.stop(1)


async def test_an_undeclared_boundary_is_refused(tmp_path):
    driver, _ = await started(tmp_path, capabilities=Capabilities(persistent=True, boundaries={"turn"}))

    with pytest.raises(DriverError, match="no tool boundary"):
        await driver.deliver(delivery(boundary="tool"))
    await driver.stop(1)


async def test_end_turn_drops_the_rest(tmp_path):
    driver, heard = await started(tmp_path, [EndTurn("done early"), Say("never")])

    assert (await heard.until(TurnEnded)).reason == "done early"
    await driver.stop(1)
    assert heard.of(Item) == []


async def test_fail_ends_the_turn_and_not_the_harness(tmp_path):
    driver, heard = await started(tmp_path, [Fail("boom")], [Say("still here")])

    assert (await heard.until(TurnEnded)).reason == "failed: boom"
    await driver.deliver(delivery())
    assert (await heard.until(Item)).gist == "still here"
    await driver.stop(1)


async def test_exit_ends_the_harness_in_the_middle_of_its_turn(tmp_path):
    driver, heard = await started(tmp_path, [Say("bye"), Exit("crashed"), Say("never")])

    assert (await heard.until(Exited)).reason == "crashed"
    assert heard.of(TurnEnded) == []
    with pytest.raises(DriverError, match="has exited"):
        await driver.deliver(delivery())
    await driver.stop(1)
    assert len(heard.of(Exited)) == 1


async def test_ask_holds_the_turn_until_answered(tmp_path):
    driver, heard = await started(tmp_path, [Ask("run rm?"), Say("after")])
    asked = await heard.until(ApprovalRequested)

    assert heard.of(Item) == []
    await driver.answer(asked.id, "deny")

    decided = await heard.until(Item, lambda item: item.approval is not None)
    assert (decided.approval, decided.outcome) == (asked.id, "deny")
    await heard.until(Item, lambda item: item.gist == "after")
    await driver.stop(1)


async def test_answering_what_nobody_asked_is_refused(tmp_path):
    driver, _ = await started(tmp_path)

    with pytest.raises(DriverError, match="no approval"):
        await driver.answer("nothing", "allow")
    await driver.stop(1)


async def test_hang_holds_until_interrupted_and_what_never_landed_goes_with_the_turn(tmp_path):
    driver, heard = await started(tmp_path, [Hang()], [Say("next")])
    await heard.until(TurnStarted)
    await driver.deliver(delivery())

    await driver.interrupt()

    assert (await heard.until(TurnEnded)).reason == "interrupted"
    assert await driver.reconcile("d1") == "unknown"
    await driver.deliver(delivery())
    assert (await heard.until(Item)).gist == "next"
    await driver.stop(1)


async def test_an_unsteerable_harness_cannot_be_interrupted(tmp_path):
    capabilities = Capabilities(persistent=True, boundaries={"turn"})
    driver, _ = await started(tmp_path, capabilities=capabilities)

    with pytest.raises(DriverError, match="cannot be interrupted"):
        await driver.interrupt()
    await driver.stop(1)


async def test_a_one_shot_exits_after_its_turn(tmp_path):
    driver, heard = await started(tmp_path, [Say("once")], capabilities=Capabilities())

    assert await heard.until(Exited)
    with pytest.raises(DriverError, match="has exited"):
        await driver.deliver(delivery())
    await driver.stop(1)


async def test_a_one_shot_refuses_input_while_it_runs(tmp_path):
    driver, heard = await started(tmp_path, [Hang()], capabilities=Capabilities())
    await heard.until(TurnStarted)

    with pytest.raises(DriverError, match="takes nothing after its goal"):
        await driver.deliver(delivery())
    await driver.stop(1)


async def test_it_refuses_to_resume_when_it_cannot(tmp_path):
    with pytest.raises(DriverError, match="cannot resume"):
        await ScriptedDriver(capabilities=Capabilities()).start(make_spec(tmp_path, resume="s-1"), Heard())


async def test_reconcile_tells_landed_from_waiting_from_unknown(tmp_path):
    driver, heard = await started(tmp_path, [EndTurn()], [Hang()])
    await heard.until(TurnEnded)
    await driver.deliver(delivery("landed"))
    await heard.until(InputDelivered, lambda landed: landed.input == "landed")
    await driver.deliver(delivery("waiting"))

    assert await driver.reconcile("waiting") == "not_landed"
    assert await driver.reconcile("never") == "unknown"
    assert await driver.reconcile("landed") == "landed"
    await driver.stop(1)


async def test_stop_before_start_does_nothing():
    await ScriptedDriver().stop(1)


async def test_a_tool_call_is_real_mcp_with_the_bearer(tmp_path):
    async with FakeTools() as tools:
        driver, heard = await started(tmp_path, [Call(TOOL, {"note": "hi"})], tools=tools.binding(tmp_path))
        await heard.until(TurnEnded)
        await driver.stop(1)

    assert tools.calls == [{"name": TOOL, "arguments": {"note": "hi"}}]
    assert driver.results[0]["content"][0]["text"] == "pong"
    assert [item.phase for item in heard.of(Item)] == ["started", "completed"]
    assert heard.of(Ready)[0].tools_visible == (TOOL,)


async def test_a_tool_refused_at_the_door_fails_the_call_loudly(tmp_path):
    async with FakeTools() as tools:
        wrong = tools.binding(tmp_path).model_copy(update={"token": Secret("wrong")})

        with pytest.raises(DriverError, match="tools/list answered 401"):
            await ScriptedDriver().start(make_spec(tmp_path, tools=wrong), Heard())


async def test_no_tools_means_visibility_is_unknown(tmp_path):
    driver, heard = await started(tmp_path)

    assert (await heard.until(Ready)).tools_visible is None
    await driver.stop(1)


async def test_ask_model_is_a_real_model_call_and_runs_what_it_calls(tmp_path):
    async with FakeModel(ToolCall(TOOL, {"note": "x"}, id="call_a"), "all done") as model, FakeTools() as tools:
        driver, heard = await started(
            tmp_path, [AskModel()], tools=tools.binding(tmp_path), model="m", access=chat_access(model)
        )
        await heard.until(TurnEnded)
        await driver.stop(1)

    assert len(model.calls) == 2
    assert model.calls[0].offers(TOOL) and model.calls[0].says("do the thing")
    assert model.calls[1].says("call_a") and model.calls[1].says("pong")
    assert [call.call_id for call in heard.of(ModelCall)] == [call.response_id for call in model.calls]
    assert [usage.scope for usage in heard.of(Usage)] == ["call", "call"]
    assert tools.calls[0]["name"] == TOOL
    assert heard.of(Item)[-1].gist == "all done"


async def test_a_tool_that_is_not_ours_is_gated(tmp_path):
    async with FakeModel(ToolCall("shell", id="call_s"), "done") as model:
        driver, heard = await started(tmp_path, [AskModel()], model="m", access=chat_access(model))
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "allow")
        await heard.until(TurnEnded)
        await driver.stop(1)

    assert model.calls[1].says("shell allow")


async def test_a_harness_with_no_approvals_says_so_to_the_model(tmp_path):
    capabilities = Capabilities(persistent=True, boundaries={"turn"})
    async with FakeModel(ToolCall("shell"), "done") as model:
        driver, heard = await started(
            tmp_path, [AskModel()], capabilities=capabilities, model="m", access=chat_access(model)
        )
        await heard.until(TurnEnded)
        await driver.stop(1)

    assert model.calls[1].says("needs an approval")
    assert heard.of(ApprovalRequested) == []


async def test_an_effort_it_cannot_set_is_refused(tmp_path):
    with pytest.raises(DriverError, match="no effort"):
        await ScriptedDriver().start(make_spec(tmp_path, effort="low"), Heard())


async def test_no_model_where_access_was_given_is_refused_at_the_start(tmp_path):
    spec = make_spec(tmp_path, access={"OPENAI_API_KEY": Secret("a-key")})

    with pytest.raises(DriverError, match="set a model"):
        await ScriptedDriver().start(spec, Heard())


async def test_no_model_set_is_refused_rather_than_defaulted(tmp_path):
    driver, heard = await started(tmp_path, [AskModel()], [Say("still here")])

    ended = await heard.until(TurnEnded)
    assert ended.reason == "failed: no model was set, and this harness will not pick one"
    await driver.deliver(delivery())
    assert (await heard.until(Item)).gist == "still here"
    await driver.stop(1)


async def test_two_approvals_in_one_turn_have_two_ids(tmp_path):
    driver, heard = await started(tmp_path, [Ask("first?"), Ask("second?")])

    first = await heard.until(ApprovalRequested, lambda asked: asked.gist == "first?")
    await driver.answer(first.id, "allow")
    second = await heard.until(ApprovalRequested, lambda asked: asked.gist == "second?")
    await driver.stop(1)

    assert first.id != second.id


async def test_a_resumed_harness_has_its_transcript_and_no_new_turn(tmp_path):
    async with FakeModel("first") as model:
        access = chat_access(model)
        driver, heard = await started(tmp_path, [AskModel()], model="m", access=access)
        await heard.until(TurnEnded)
        await driver.stop(1)

        again, heard = ScriptedDriver([[AskModel()]]), Heard()
        await again.start(make_spec(tmp_path, model="m", access=access, resume="scripted-ada"), heard)
        await heard.until(Ready)
        assert heard.of(TurnStarted) == []

        await again.deliver(delivery(gist="more"))
        await heard.until(TurnEnded)
        await again.stop(1)

    assert model.calls[1].says("do the thing") and model.calls[1].says("more")


async def test_scripted_driver_sends_each_tool_calls_id_so_each_op_joins_its_call(tmp_path):
    """Two identical claims one model call chose go under ids of their own, which their tool items hold, so each is a
    claim of its own and joins that call, as a harness's does. With no id the tool plane takes the second for a repeat
    of the first in its turn, which a `Call` step still is."""
    queue = {"kind": "queue", "writers": "all", "readers": "all", "delivery": "pull", "max_inflight": 2}
    team = Team.model_validate(
        {"roles": {"bob": {"harness": scripted([AskModel()])}}, "topology": {"channels": {"tasks": queue}}}
    )
    claims = [ToolCall("task_claim", {"queue": "tasks"}, id=f"call_{n}") for n in (1, 2)]
    model = FakeModel(claims, "both claimed")
    async with model, Session.start(team, root=tmp_path, authority=Gateways(model)) as session:
        await in_state(session, "bob", "idle")
        for name in ("one", "two"):
            await session.task_add("tasks", name)
        await session.send("@bob", "claim two")
        claimed = await until(lambda: of_type(session, "task.claimed"), session, lambda found: len(found) == 2)
        await in_state(session, "bob", "idle")
        [called, _] = await of_type(session, "model.called")
        made = [(await session.lineage(f"{event.stream}@{event.version}")).made for event in claimed]

    assert sorted(event.stream for event in claimed) == ["task/tasks/1", "task/tasks/2"]
    assert [(found.anchor and (found.anchor.key, found.anchor.id, found.anchor.ops)) for found in made] == [
        ("scripted/toolCallId", "call_1", 1),
        ("scripted/toolCallId", "call_2", 1),
    ]
    assert {found.call for found in made} == {f"{called.stream}@{called.version}"}


async def test_scripted_driver_joins_each_op_to_its_own_call_on_the_ids_fake_model_gives(tmp_path):
    """A script that names no ids gets ids of each reply's own, so the same claim chosen in two turns is two claims,
    each joined to the call that chose it, and not the second a repeat of the first, joined to the first's call."""
    queue = {"kind": "queue", "writers": "all", "readers": "all", "delivery": "pull", "max_inflight": 2}
    roles = {"bob": {"harness": scripted([AskModel()], [AskModel()])}}
    team = Team.model_validate({"roles": roles, "topology": {"channels": {"tasks": queue}}})
    claim = ToolCall("task_claim", {"queue": "tasks"})
    model = FakeModel(claim, "claimed one", claim, "claimed another")
    async with model, Session.start(team, root=tmp_path, authority=Gateways(model)) as session:
        await in_state(session, "bob", "idle")
        for name in ("one", "two"):
            await session.task_add("tasks", name)
        for number in (1, 2):
            await session.send("@bob", "claim one")
            await until(lambda: of_type(session, "turn.ended"), session, lambda found, n=number: len(found) == n)
            await in_state(session, "bob", "idle")
        claimed = await of_type(session, "task.claimed")
        calls = [f"{event.stream}@{event.version}" for event in await of_type(session, "model.called")]
        made = [(await session.lineage(f"{event.stream}@{event.version}")).made for event in claimed]

    assert sorted(event.stream for event in claimed) == ["task/tasks/1", "task/tasks/2"]
    assert [(found.anchor and found.anchor.id, found.call) for found in made] == [
        ("call_1_0", calls[0]),
        ("call_3_0", calls[2]),
    ]


async def test_scripted_driver_fails_the_turn_of_a_tool_call_under_an_id_it_has_sent(tmp_path):
    """An op is joined to its call by the id, so a second call under one would be joined to the first's: it is refused,
    loudly, and never sent."""
    same = ToolCall(TOOL, {"note": "x"}, id="call_a")
    async with FakeModel(same, "once", same, "twice") as model, FakeTools() as tools:
        driver, heard = await started(
            tmp_path, [AskModel()], [AskModel()], tools=tools.binding(tmp_path), model="m", access=chat_access(model)
        )
        await heard.until(TurnEnded)
        await driver.deliver(delivery())
        await heard.until(TurnEnded, lambda ended: ended.reason != "stopped")
        await driver.stop(1)

    assert [ended.reason for ended in heard.of(TurnEnded)] == [
        "stopped",
        "failed: the model gave tool call id call_a twice, and an op joins its call by its id",
    ]
    assert len(tools.calls) == 1
