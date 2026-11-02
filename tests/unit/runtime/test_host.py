"""The host: effects performed level-triggered, each harness heard in order, and links that outlive the daemon."""

import asyncio
import json
import stat
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
    Capabilities,
    Delivery,
    Delta,
    DriverError,
    GapReport,
    Item,
    Receipt,
    Report,
    Reporter,
    Started,
    TurnEnded,
    TurnStarted,
    Usage,
)
from platoon_harness.kernel import ManualClock, hash_token
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, LocalAuthority, Runtime, SpawnRequest
from platoon_harness.testing import Ask, Call, Exit, Hang, Say, ScriptedDriver, Think

from .support import SECONDS, harness, in_state, journal, of_type, scripted, solo, until

pytestmark = pytest.mark.timeout(30)


async def ended(session: Session, agent: str) -> dict[str, Any]:
    await in_state(session, agent, "ended")
    return next(row for row in (await session.ending()).agents if row["agent"] == agent)


class Recording(ScriptedDriver):
    """A scripted harness that keeps what it was started and handed."""

    specs: list[AgentSpec] = []
    deliveries: list[Delivery] = []

    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        Recording.specs.append(spec)
        return await super().start(spec, report)

    async def deliver(self, delivery: Delivery) -> Receipt:
        Recording.deliveries.append(delivery)
        return await super().deliver(delivery)


@pytest.fixture
def recording() -> type[Recording]:
    Recording.specs, Recording.deliveries = [], []
    return Recording


def recorded(driver: type[Recording]) -> Callable[[], Awaitable[list[Delivery]]]:
    """What the harness was handed, to ask of it each time the journal moves."""

    async def handed() -> list[Delivery]:
        return driver.deliveries

    return handed


class Stuck(ScriptedDriver):
    """A harness whose handover never comes back."""

    async def deliver(self, delivery: Delivery) -> Receipt:
        await asyncio.Event().wait()
        raise AssertionError


# Admit, workspace and launch.


async def test_a_raw_token_stays_in_memory_and_only_its_hash_is_journaled(tmp_path):
    tokens: list[str] = []

    class Keeping(LocalAuthority):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            admission = await super().admit(spawn)
            tokens.append(admission.token.reveal())
            return admission

    team = solo()
    async with Session.start(team, authority=Keeping(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        text = json.dumps([event.model_dump(mode="json") for event in await journal(session)])

    assert tokens[0] not in text
    assert hash_token(tokens[0]) in text


async def test_an_authority_that_refuses_ends_the_spawn(tmp_path):
    class Refusing(LocalAuthority):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            raise DriverError("not on this budget")

    team = solo()
    async with Session.start(team, authority=Refusing(team), root=tmp_path) as session:
        row = await ended(session, "bob")

        assert (row["status"], row["reason"]) == ("failed", "its spawn failed: not on this budget")
        assert await of_type(session, "agent.started") == []


async def test_an_authority_hears_how_an_agent_ended(tmp_path):
    heard: asyncio.Future[tuple[AgentRef, AgentOutcome]] = asyncio.get_running_loop().create_future()

    class Listening(LocalAuthority):
        async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
            heard.set_result((agent, outcome))

    team = solo()
    async with Session.start(team, authority=Listening(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.cancel("@bob")

        assert await asyncio.wait_for(heard, SECONDS) == (
            AgentRef(agent="bob", role="bob"),
            AgentOutcome(status="cancelled"),
        )


async def test_each_agent_gets_its_own_binding_instructions_preamble_and_ph(tmp_path, recording):
    team = solo(instructions="Be brief.", model="m")
    team = team.model_copy(
        update={"roles": {"bob": team.roles["bob"].model_copy(update={"harness": harness(recording)})}}
    )

    async with Session.start(team, cwd=tmp_path, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        spec = recording.specs[0]
        ready = (await of_type(session, "agent.started"))[0]

    ph = spec.folder / "bin" / "ph"
    assert (spec.agent, spec.role, spec.model, spec.cwd) == ("bob", "bob", "m", tmp_path)
    assert spec.folder == session.folder / "agents" / "bob"
    assert spec.tools is not None and spec.tools.bin == ph.parent
    assert stat.S_IMODE(ph.stat().st_mode) & stat.S_IXUSR
    assert ph.read_text().startswith("#!/usr/bin/env python3")
    assert "?surface=mcp__ph" in spec.tools.url
    assert spec.instructions is not None and spec.instructions.startswith("Be brief.\n\n")
    assert "`mcp__ph__wait`" in spec.instructions
    assert "wait" in ready.data["tools_visible"]


async def test_a_harness_with_no_tool_path_gets_no_binding(tmp_path, recording):
    def none() -> ScriptedDriver:
        return recording(capabilities=Capabilities(persistent=True, boundaries={"turn"}))

    team = Team.model_validate({"roles": {"bob": {"harness": harness(none)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")

    assert recording.specs[0].tools is None
    assert recording.specs[0].instructions is None


async def test_capabilities_and_levels_reach_agent_started(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = (await of_type(session, "agent.started"))[0]

    assert started.data["declared"]["persistent"] is True
    assert started.data["verified"]["tools"] == "visible"
    assert started.data["levels"]["operational"]["state"] == "unverified"
    assert "no conformance result for scripted" in started.data["levels"]["operational"]["reasons"]


async def test_a_workspace_nobody_built_yet_fails_loudly(tmp_path):
    team = solo(workspace="worktree")

    async with Session.start(team, root=tmp_path) as session:
        row = await ended(session, "bob")

        assert row["status"] == "failed"
        failed = (await of_type(session, "effect.failed"))[0]
        assert failed.data["error"] == "workspace `worktree` is not available yet: use `shared`"
        assert await of_type(session, "agent.started") == []


async def test_a_harness_that_will_not_start_fails_its_spawn_and_its_parent_hears(tmp_path):
    class Broken(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            raise DriverError("no such binary")

    team = Team.model_validate(
        {
            "roles": {
                "lead": {
                    "harness": scripted([Call("agent_spawn", {"name": "w", "child_role": "worker"})]),
                    "may_spawn": ["worker"],
                },
                "worker": {"harness": harness(Broken)},
            },
            "topology": {"manager-worker": {"manager": "lead", "workers": "worker"}},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@lead", "go")
        await until(lambda: of_type(session, "agent.ended"), session)
        told = await until(lambda: of_type(session, "message.sent"), session, lambda sent: len(sent) > 1)

        assert told[-1].gist.startswith("w failed")
        assert (await session.ending()).reason == "agent_failed"


async def test_a_harness_that_never_says_ready_is_a_failure_and_not_a_hang(tmp_path):
    class Silent(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            return Started(native="silent")

    clock = ManualClock(1000.0)
    team = Team.model_validate({"roles": {"bob": {"harness": harness(Silent)}}})

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1060.0)
        clock.advance(60.0)
        row = await ended(session, "bob")

        assert row["status"] == "failed"
        assert "never said it was ready" in (await of_type(session, "effect.failed"))[0].data["error"]


async def test_a_harness_that_never_returns_from_start_is_a_failure_and_not_a_hang(tmp_path):
    class Wedged(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            await asyncio.Event().wait()
            raise AssertionError

    clock = ManualClock(1000.0)
    team = Team.model_validate({"roles": {"bob": {"harness": harness(Wedged)}}})

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1060.0)
        clock.advance(60.0)

        assert (await ended(session, "bob"))["status"] == "failed"


async def test_a_missing_credential_fails_the_spawn_and_says_which(tmp_path):
    team = Team.model_validate(
        {"roles": {"bob": {"harness": scripted(), "auth": "work"}}, "auth": {"work": {"env": ["NOT_SET_ANYWHERE"]}}}
    )

    async with Session.start(team, root=tmp_path) as session:
        row = await ended(session, "bob")

        assert row["status"] == "failed"
        assert "`NOT_SET_ANYWHERE` is not set" in (await of_type(session, "effect.failed"))[0].data["error"]


async def test_a_credential_in_what_a_driver_said_is_masked_in_the_journal(tmp_path):
    class Leaky(ScriptedDriver):
        async def deliver(self, delivery: Delivery) -> Receipt:
            assert self._spec.tools is not None
            raise DriverError(f"it refused the token {self._spec.tools.token.reveal()}")

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Leaky)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        failed = await until(lambda: of_type(session, "effect.failed"), session)

    assert failed[0].data["error"] == "it refused the token ***"


async def test_a_goal_comes_with_its_body(tmp_path, recording):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(recording), "count": 0}}})

    async with Session.start(team, root=tmp_path) as session:
        await session.spawn("ada", "bob", "the short of it", body="the long of it")
        await in_state(session, "ada", "idle", "running")

    assert recording.specs[0].goal == "the short of it\n\nthe long of it"


# Delivery.


async def test_a_message_reaches_a_harness_as_text_with_the_ref_and_the_input(tmp_path, recording):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(recording)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        sent = await session.send("@bob", "read this", body="the whole of it")
        await until(recorded(recording), session)
        body = next(event.data["body"] for event in await of_type(session, "message.sent"))

    delivery = recording.deliveries[0]
    assert delivery.text.splitlines() == [
        f"New messages (delivery {delivery.input}):",
        f"- {sent['ref']} from @you: read this",
        f"  Its body is {body}: pass that as `ref` to `mcp__ph__blob_get`.",
    ]
    assert delivery.items[0].sender == "@you"
    assert delivery.items[0].body == body


async def test_what_a_delivery_landed_on_is_confirmed_as_exposure(tmp_path):
    async with Session.start(solo([Say("heard")]), root=tmp_path) as session:
        await session.send("@bob", "go")
        delivered = await until(lambda: of_type(session, "context.delivered"), session)

        assert delivered[0].data["evidence"] == "turn_start"


async def test_a_delivery_with_no_harness_fails_and_is_offered_again(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        host = session._runtime.host
        link = host.link("bob")
        del host._links["bob"]

        await session.send("@bob", "anyone there?")
        await until(lambda: of_type(session, "effect.failed"), session)

        host._links["bob"] = link
        await until(lambda: of_type(session, "context.delivered"), session)
        assert len(await of_type(session, "context.offered")) == 2


# Around a delivery that hangs.


async def test_interrupt_works_while_a_delivery_hangs(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(lambda: Stuck([[Hang()]])), "delivery": "steer"}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.spawn("ada", "bob", "hold on")
        await in_state(session, "ada", "running")
        await session.send("@ada", "this will hang")
        await until(
            lambda: of_type(session, "effect.started"),
            session,
            lambda found: found and found[-1].data["kind"] == "deliver",
        )

        await session.interrupt("@ada")
        ended_turn = await until(lambda: of_type(session, "turn.ended"), session)

        assert ended_turn[0].data["reason"] == "interrupted"


async def test_stop_works_while_a_delivery_hangs(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(lambda: Stuck())}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "this will hang")
        await until(
            lambda: of_type(session, "effect.started"),
            session,
            lambda found: found and found[-1].data["kind"] == "deliver",
        )

        await session.cancel("@bob")

        await until(
            lambda: of_type(session, "effect.finished"),
            session,
            lambda found: found and found[-1].data["kind"] == "stop",
        )


async def test_an_answer_goes_around_a_delivery_that_hangs(tmp_path):
    def stuck() -> ScriptedDriver:
        return Stuck([[Ask("may I?"), Say("thanks")]])

    team = Team.model_validate({"roles": {"bob": {"harness": harness(stuck), "count": 0, "delivery": "steer"}}})

    async with Session.start(team, root=tmp_path) as session:
        await session.spawn("ada", "bob", "ask first")
        asked = (await until(session.approvals, session))[0]
        await session.send("@ada", "this will hang")
        await until(
            lambda: of_type(session, "effect.started"),
            session,
            lambda found: found and found[-1].data["kind"] == "deliver",
        )

        await session.resolve(asked["id"], "allow", expected_version=asked["version"])

        items = await until(
            lambda: of_type(session, "item.recorded"), session, lambda found: found and found[-1].gist == "thanks"
        )
        assert items[-2].data["outcome"] == "allow"


# Takeover.


async def test_deliveries_wait_while_a_takeover_holds_an_agent(tmp_path):
    async with Session.start(solo([Say("heard")]), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "first")
        await in_state(session, "bob", "waking", "running", "idle")
        await until(lambda: of_type(session, "turn.ended"), session)
        await session.takeover("@bob")

        await session.send("@bob", "while held")

        assert (await session.status("@bob"))["state"] == "held"
        assert len(await of_type(session, "context.offered")) == 1

        await session.release_agent("@bob")
        offered = await until(lambda: of_type(session, "context.offered"), session, lambda found: len(found) == 2)

        assert offered[-1].data["items"][0]["ref"] == "inbox/bob@2"


async def test_a_delivery_already_asked_for_waits_out_a_takeover(tmp_path):
    held = asyncio.Event()
    delivered = asyncio.Event()

    class Slow(ScriptedDriver):
        async def deliver(self, delivery: Delivery) -> Receipt:
            delivered.set()
            return await super().deliver(delivery)

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Slow)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        runtime = session._runtime
        host = runtime.host
        real = host._dispatch

        def paused() -> None:
            if held.is_set():
                real()

        host._dispatch = paused
        await session.send("@bob", "held back")
        await until(lambda: runtime_ready(runtime), session)
        await session.takeover("@bob")
        host._dispatch = real
        held.set()
        await session.submit("agent.status", agent="@bob")
        await session.put_body(b"nudge")
        await until(lambda: of_type(session, "agent.held"), session)

        assert not delivered.is_set()

        await session.release_agent("@bob")
        async with asyncio.timeout(SECONDS):
            await delivered.wait()


async def runtime_ready(runtime: Runtime) -> list[dict[str, Any]]:
    kernel = runtime.kernel
    return kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"}).result


# Reports.


async def test_reports_are_journaled_in_the_order_they_were_said(tmp_path):
    turn = [Say("one"), Think("two"), Say("three")]

    async with Session.start(solo(turn), root=tmp_path) as session:
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)

        assert [event.gist for event in await of_type(session, "item.recorded")] == ["one", "two", "three"]


async def test_a_report_s_body_is_stored_and_journaled_by_its_hash(tmp_path):
    async with Session.start(solo([Say("the whole of what it said")]), root=tmp_path) as session:
        await session.send("@bob", "go")
        item = (await until(lambda: of_type(session, "item.recorded"), session))[0]

        assert item.data["body"].startswith("sha256:")
        stored = await session.get_body(item.data["body"].removeprefix("sha256:"))
        assert stored == b"the whole of what it said"


async def test_a_delta_reaches_a_follower_and_never_the_journal(tmp_path):
    release = asyncio.Event()

    class Talking(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            started = await super().start(spec, report)
            await release.wait()
            await report(Delta(text="live words"))
            return started

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Talking)}}})

    async with Session.start(team, root=tmp_path) as session:
        frames = session.deltas("bob")
        next_frame = asyncio.ensure_future(anext(frames))
        release.set()

        frame = await asyncio.wait_for(next_frame, SECONDS)

        assert frame.text == "live words"
        assert "live words" not in json.dumps([event.gist for event in await journal(session)])
        await frames.aclose()


async def test_every_word_of_the_vocabulary_has_somewhere_to_go(tmp_path):
    said: list[Report] = [
        TurnStarted(turn="t1"),
        Usage(tokens=7, label="provider"),
        GapReport(plane="model", what="hidden_call"),
        Item(kind="tool", gist="ran it"),
        TurnEnded(reason="stopped"),
    ]

    class Reporting(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            started = await super().start(spec, report)
            for item in said:
                await report(item)
            return started

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Reporting)}}})

    async with Session.start(team, root=tmp_path) as session:
        await until(lambda: of_type(session, "turn.ended"), session)
        ending = await session.ending()

    assert ending.usage["tokens"] == {"amount": 7.0, "label": "provider"}
    assert ending.gaps == ({"agent": "bob", "what": "hidden_call", "plane": "model", "count": 1},)


async def test_activity_renews_a_lease_up_to_its_limit(tmp_path):
    class Busy(ScriptedDriver):
        async def stamp(self):
            await self._report(Item(kind="thought", gist="still at it"))

    drivers: list[Busy] = []

    def busy() -> Busy:
        drivers.append(Busy([[Call("task_claim", {"queue": "work"}), Hang()]]))
        return drivers[-1]

    clock = ManualClock(1000.0)
    team = Team.model_validate(
        {
            "roles": {"lead": {"harness": scripted()}, "worker": {"harness": harness(busy)}},
            "topology": {
                "channels": {
                    "work": {
                        "kind": "queue",
                        "writers": "human",
                        "readers": "role:worker",
                        "lease": "60s",
                        "lease_max": "100s",
                    }
                }
            },
        }
    )

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        await in_state(session, "worker", "idle")
        await session.enqueue("work", "do it")
        await session.send("@worker", "go")
        task = await until(lambda: of_type(session, "task.claimed"), session)
        working = drivers[-1]

        clock.advance(31.0)
        await working.stamp()
        renewed = await until(lambda: of_type(session, "task.renewed"), session)
        assert renewed[0].data["lease_until"] == 1091.0

        clock.advance(40.0)
        await working.stamp()
        renewed = await until(lambda: of_type(session, "task.renewed"), session, lambda found: len(found) == 2)
        assert renewed[1].data["lease_until"] == 1100.0

        clock.advance(20.0)
        await working.stamp()

        assert len(await of_type(session, "task.renewed")) == 2
        assert task[0].data["task"] == "1"


# What dies.


async def test_a_harness_that_exits_is_lost_and_its_parent_hears(tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "lead": {
                    "harness": scripted([Call("agent_spawn", {"name": "w", "child_role": "worker", "goal": "fall"})]),
                    "may_spawn": ["worker"],
                },
                "worker": {"harness": scripted([Exit("it fell over")])},
            },
            "topology": {"manager-worker": {"manager": "lead", "workers": "worker"}},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@lead", "go")
        await until(lambda: of_type(session, "agent.ended"), session)
        told = await until(lambda: of_type(session, "message.sent"), session, lambda sent: len(sent) > 1)

        assert told[-1].gist == "w lost: it fell over"
        assert (await session.ending()).reason == "agent_failed"


async def test_a_driver_that_raises_something_unexpected_loses_its_harness_with_no_silent_hang(tmp_path):
    class Crashing(ScriptedDriver):
        async def deliver(self, delivery: Delivery) -> Receipt:
            raise RuntimeError("a bug in the driver")

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Crashing)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        row = await ended(session, "bob")

        assert (row["status"], row["reason"]) == ("lost", "its deliver failed: RuntimeError")


async def test_a_report_that_cannot_be_taken_ends_the_harness_and_not_the_host(tmp_path, monkeypatch):
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        kernel = session._runtime.kernel

        async def no_room(body: bytes) -> str:
            raise OSError("no space left on device")

        monkeypatch.setattr(kernel, "put_body", no_room)
        link = session._runtime.host.link("bob")
        await session._runtime.host._heard(link, Item(kind="message", gist="said", body="lost"))
        row = await ended(session, "bob")

        assert (row["status"], row["reason"]) == ("lost", "its reports could not be taken")


async def test_an_approval_the_journal_will_not_hold_is_denied_so_no_harness_blocks(tmp_path):
    answers: list[tuple[str, str]] = []

    class Repeating(ScriptedDriver):
        async def answer(self, approval: str, verdict: Any) -> None:
            answers.append((approval, verdict))

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Repeating)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        host = session._runtime.host
        link = host.link("bob")

        await host._heard(link, ApprovalRequested(id="a1", gist="may I?"))
        await host._heard(link, ApprovalRequested(id="a1", gist="may I, again?"))

    assert answers == [("a1", "deny")]


async def test_a_restarted_daemon_loses_no_harness(tmp_path, monkeypatch):
    async with Session.start(solo([Say("still here")]), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        runtime = session._runtime
        host = runtime.host
        link = host.link("bob")
        real = host._dispatch
        calls = []

        def fails_once() -> None:
            calls.append(None)
            if len(calls) == 1:
                raise RuntimeError("a daemon's bad moment")
            real()

        monkeypatch.setattr(host, "_dispatch", fails_once)
        await session.send("@bob", "go")
        await session.put_body(b"nudge")
        items = await until(lambda: of_type(session, "item.recorded"), session)

        assert items[0].gist == "still here"
        assert host.link("bob") is link
        assert len(calls) >= 2


async def test_several_runtimes_share_a_process(tmp_path):
    first = await Session.start(solo([Say("one")]), name="first", root=tmp_path)
    second = await Session.start(solo([Say("two")]), name="second", root=tmp_path)

    await first.send("@bob", "go")
    await second.send("@bob", "go")

    one = await until(lambda: of_type(first, "item.recorded"), first)
    two = await until(lambda: of_type(second, "item.recorded"), second)
    assert (one[0].gist, two[0].gist) == ("one", "two")
    await first.leave()
    await second.leave()


async def test_an_agent_that_ended_leaves_no_harness_behind(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.cancel("@bob")
        await until(
            lambda: of_type(session, "effect.finished"),
            session,
            lambda found: found and found[-1].data["kind"] == "stop",
        )

        assert session._runtime.host.link("bob") is None


async def test_a_token_works_only_while_its_agent_lives(tmp_path, recording):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(recording)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        binding = recording.specs[0].tools
        assert isinstance(binding.token, Secret)
        kernel = session._runtime.kernel

        assert kernel.authenticate(binding.token.reveal()).id == "agent:bob"

        await session.cancel("@bob")
        await in_state(session, "bob", "ended")

        with pytest.raises(Exception, match="unknown credential"):
            kernel.authenticate(binding.token.reveal())
