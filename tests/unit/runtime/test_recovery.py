"""Recovery: each effect kind follows its row in architecture section 5.4. A runtime is abandoned in-process, leaving
the journal as a crash leaves it, so each row can be reached at will. `test_crash.py` does it on real processes."""

import asyncio
import json
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Refused, Session, Team, __version__
from platoon_harness.drivers import (
    AgentSpec,
    Capabilities,
    Delivery,
    DriverError,
    Exited,
    Ready,
    Receipt,
    Reconciled,
    Report,
    Reporter,
    Started,
    TurnEnded,
    TurnStarted,
)
from platoon_harness.kernel import ManualClock, is_held
from platoon_harness.primitives import CUT_OFF, Agents
from platoon_harness.runtime import Admission, LocalAuthority, Runtime, SpawnRequest, host, recovery
from platoon_harness.runtime.paths import MANIFEST
from platoon_harness.schema import ConfigError, Problem
from platoon_harness.testing import Ask, Call, Hang, Say, ScriptedDriver

from .support import SECONDS, harness, in_state, of_type, rebuilt_equals_live, scripted, solo, until

pytestmark = pytest.mark.timeout(30)

NO_RESUME = Capabilities(persistent=True, boundaries={"turn"}, tool_paths={"mcp-http"})


async def abandon(session: Session) -> None:
    """Drop a runtime as a crash would: no shutdown is journaled, and what was in flight stays `started`."""
    runtime = session._runtime
    assert runtime is not None
    session._runtime = session._link = None
    acting = tuple(runtime.host._acting.values())
    for task in acting:
        task.cancel()
    await asyncio.gather(*acting, return_exceptions=True)
    runtime.host.closing()
    await runtime.host.close(0.0)
    await runtime._close()


def started(kind: str, agent: str = "bob") -> Callable[[Session], Awaitable[Any]]:
    """Wait until an effect of this kind is in flight."""

    async def holds(session: Session) -> Any:
        async def found() -> list[Any]:
            events = await of_type(session, "effect.started")
            return [event for event in events if event.data["kind"] == kind and event.agent == agent]

        return await until(found, session)

    return holds


class Hanging(ScriptedDriver):
    """A harness that takes a handover and never answers."""

    async def deliver(self, delivery: Delivery) -> Receipt:
        await asyncio.Event().wait()
        raise AssertionError


class Knowing(ScriptedDriver):
    """A harness that can say whether something landed. It resumes into a session that remembers."""

    answer_found = "unknown"

    async def reconcile(self, input_id: str):
        return type(self).answer_found


def knowing(found: str) -> type[Knowing]:
    return type("Answered", (Knowing,), {"answer_found": found})


class ComesBack(ScriptedDriver):
    """A harness that hangs in its first turn, or does `first`, and once resumed does the rest of its script."""

    def __init__(self, *resumed: Any, first: Any = None, **options: Any) -> None:
        super().__init__([first or [Hang()]], **options)
        self._resumed = resumed

    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        if spec.resume is not None:
            self._turns = iter(self._resumed)
        return await super().start(spec, report)


def solo_with(make: Any, **role: Any) -> Team:
    return Team.model_validate({"roles": {"bob": {"harness": harness(make), **role}}})


# Admit.


async def test_an_admit_in_flight_is_never_retried_and_the_spawn_fails_with_a_gap(tmp_path):
    calls = []
    asked = asyncio.Event()

    class Slow(LocalAuthority):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            calls.append(spawn)
            asked.set()
            await asyncio.Event().wait()
            raise AssertionError

    team = solo_with(ScriptedDriver)
    session = await Session.start(team, name="s", authority=Slow(team), root=tmp_path)
    await asyncio.wait_for(asked.wait(), SECONDS)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        ending = await session.ending()
        failed = await of_type(session, "effect.failed")

    assert len(calls) == 1
    assert (ending.agents[0]["status"], ending.reason) == ("failed", "agent_failed")
    assert "never retried" in failed[0].data["error"]
    assert ending.gaps == ({"agent": "bob", "what": "crash_window", "plane": "model", "count": 1},)


async def test_an_admission_that_finished_is_asked_for_again_as_a_resume_and_the_spawn_goes_on(tmp_path):
    asked: list[SpawnRequest] = []

    class Keeping(LocalAuthority):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            asked.append(spawn)
            return await super().admit(spawn)

    team = solo_with(ScriptedDriver)
    session = await Session.start(team, name="s", authority=Keeping(team), root=tmp_path)
    await in_state(session, "bob", "idle")
    runtime = session._runtime
    assert runtime is not None
    real = runtime.host._acts["workspace"]

    async def dies(effect: Any) -> None:
        await real(effect)
        await asyncio.Event().wait()

    runtime.host._acts["workspace"] = dies
    await session.spawn("ada", "bob")
    await started("workspace", "ada")(session)
    await abandon(session)
    asked.clear()

    async with Session.resume("s", authority=Keeping(team), root=tmp_path) as session:
        await in_state(session, "ada", "idle")

    assert {(spawn.agent, spawn.resumed) for spawn in asked} == {("bob", True), ("ada", True)}


# Workspace.


async def test_a_workspace_in_flight_is_adopted(tmp_path):
    session = await Session.start(solo_with(ScriptedDriver), name="s", root=tmp_path)
    runtime = session._runtime
    assert runtime is not None

    async def hanging(effect: Any) -> None:
        await asyncio.Event().wait()

    runtime.host._acts["workspace"] = hanging
    await session.spawn("ada", "bob")
    await started("workspace", "ada")(session)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "ada", "idle")
        finished = [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "workspace"]

    assert finished[-1].data["result"] == {"path": str(Path.cwd())}


# Launch.


async def test_a_launch_in_flight_ends_the_agent_with_a_gap(tmp_path):
    class NeverUp(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            await asyncio.Event().wait()
            raise AssertionError

    session = await Session.start(solo_with(NeverUp), name="s", root=tmp_path)
    await started("launch")(session)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        ending = await session.ending()

    assert ending.agents[0]["status"] == "failed"
    assert any(row["what"] == "crash_window" for row in ending.gaps)


async def test_a_harness_that_said_ready_before_the_crash_has_its_launch_finished(tmp_path):
    class UpButSlow(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            found = await super().start(spec, report)
            if spec.resume is None:
                await asyncio.Event().wait()
            return found

    session = await Session.start(solo_with(UpButSlow), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        kinds = [event.data["kind"] for event in await of_type(session, "effect.finished")]
        resumed = await of_type(session, "agent.resumed")

    assert "launch" in kinds
    assert len(resumed) == 1


async def test_a_harness_that_cannot_resume_is_lost_with_a_gap_and_its_tasks_reopen(tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "bob": {"harness": scripted(capabilities=NO_RESUME)},
            },
            "topology": {"channels": {"work": {"kind": "queue", "writers": "human", "readers": "all"}}},
        }
    )
    session = await Session.start(team, name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        ending = await session.ending()

    assert (ending.agents[0]["status"], ending.agents[0]["reason"]) == ("lost", "its harness cannot resume")
    assert ending.gaps == ({"agent": "bob", "what": "crash_window", "plane": "control", "count": 1},)


async def test_a_harness_that_fails_to_resume_is_lost_and_says_why(tmp_path):
    class Fussy(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            if spec.resume is not None:
                raise DriverError("its session file is gone")
            return await super().start(spec, report)

    session = await Session.start(solo_with(Fussy), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        assert (await session.ending()).agents[0]["reason"] == "its session file is gone"


async def test_model_access_that_went_away_loses_the_agent_and_says_so(tmp_path):
    class Forgetful(LocalAuthority):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            if spawn.resumed:
                raise ConfigError([Problem("auth.work.env", "`KEY` is not set")])
            return await super().admit(spawn)

    team = solo_with(ScriptedDriver)
    session = await Session.start(team, name="s", authority=Forgetful(team), root=tmp_path)
    await in_state(session, "bob", "idle")
    await abandon(session)

    async with Session.resume("s", authority=Forgetful(team), root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        assert "`KEY` is not set" in (await session.ending()).agents[0]["reason"]


async def test_an_agent_with_no_native_id_cannot_resume(tmp_path):
    class Nameless(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            await report(Ready(version="1"))
            return Started()

    session = await Session.start(solo_with(Nameless), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        assert (await session.ending()).agents[0]["status"] == "lost"


async def test_a_group_that_cannot_be_proved_ours_is_left_and_named(tmp_path, monkeypatch):
    async def unproven(folder: Path, grace: float) -> tuple[str, ...]:
        return ("process group 4242 outlived its leader and cannot be proved ours",)

    session = await Session.start(solo_with(ScriptedDriver), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await abandon(session)
    monkeypatch.setattr(recovery, "reap", unproven)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        recorded = await of_type(session, "native.recorded")

    assert "process group 4242" in recorded[0].data["raw"]


# Deliver.


async def hanging_delivery(tmp_path: Path, make: Any, **role: Any) -> None:
    session = await Session.start(solo_with(make, **role), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await session.send("@bob", "deliver me")
    await started("deliver")(session)
    await abandon(session)


class Hangs(Knowing, Hanging):
    """It hangs on a handover until it is resumed."""

    async def deliver(self, delivery: Delivery) -> Receipt:
        if self._spec.resume is None:
            return await Hanging.deliver(self, delivery)
        return await ScriptedDriver.deliver(self, delivery)


async def test_a_driver_that_cannot_say_counts_as_not_knowing(tmp_path):
    class Refusing(Hangs):
        async def reconcile(self, input_id: str):
            raise DriverError("it keeps no record")

    await hanging_delivery(tmp_path, Refusing)

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "context.delivered"), session)

        assert len(await of_type(session, "context.offered")) == 2


@pytest.mark.parametrize("found", ["not_landed", "unknown"])
async def test_a_delivery_that_did_not_land_goes_again_under_a_new_input(tmp_path, found):
    await hanging_delivery(tmp_path, lambda: type("Found", (Hangs,), {"answer_found": found})())

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "context.delivered"), session)
        offers = await of_type(session, "context.offered")

    assert len(offers) == 2
    assert [item["ref"] for item in offers[0].data["items"]] == [item["ref"] for item in offers[1].data["items"]]
    assert offers[0].seq != offers[1].seq


async def test_a_delivery_that_landed_but_began_no_turn_goes_again(tmp_path):
    await hanging_delivery(tmp_path, lambda: type("Found", (Hangs,), {"answer_found": "landed"})())

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "turn.started"), session)

        assert len(await of_type(session, "context.offered")) == 2


async def test_a_delivery_that_landed_and_began_its_turn_counts_as_delivered(tmp_path):
    class LandsThenHangs(ScriptedDriver):
        async def deliver(self, delivery: Delivery) -> Receipt:
            if self._spec.resume is None:
                await self._report(TurnStarted(turn="t1"))
                await asyncio.Event().wait()
            return await super().deliver(delivery)

        async def reconcile(self, input_id: str):
            return "landed"

    session = await Session.start(solo_with(LandsThenHangs), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await session.send("@bob", "deliver me")
    await until(lambda: of_type(session, "turn.started"), session)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        finished = await until(lambda: of_type(session, "context.delivered"), session)

        assert finished[0].data["evidence"] == "reconcile"
        assert len(await of_type(session, "context.offered")) == 1
        assert (await of_type(session, "turn.lost"))[0].data == {"gap": "crash_window"}


# Answer.


async def asked_then_crashed(tmp_path: Path, make: Any) -> None:
    session = await Session.start(solo_with(make), name="s", root=tmp_path)
    await session.send("@bob", "go")
    asked = (await until(session.approvals, session))[0]
    await session.resolve(asked["id"], "allow", expected_version=asked["version"])
    await started("answer")(session)
    await abandon(session)


class HangsOnAnswers(Knowing):
    async def answer(self, approval: str, verdict: Any) -> None:
        if self._spec.resume is None:
            await asyncio.Event().wait()


@pytest.mark.parametrize(
    ("found", "ending"), [("landed", "effect.finished"), ("not_landed", "effect.failed"), ("unknown", None)]
)
async def test_an_answer_is_read_from_the_harness_or_stays_uncertain_in_attention(tmp_path, found, ending):
    def make() -> ScriptedDriver:
        return type("Found", (HangsOnAnswers,), {"answer_found": found})([[Ask("may I?")]])

    await asked_then_crashed(tmp_path, make)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        answers = [
            event
            for event in await of_type(session, "effect.finished", "effect.failed", "effect.uncertain")
            if event.data["kind"] == "answer"
        ]
        attention = {row["id"]: row["kind"] for row in await session.attention()}

    assert answers[-1].type == (ending or "effect.uncertain")
    shown = attention.get(f"effect/{answers[-1].data['id']}")
    assert shown == {"effect.finished": None, "effect.failed": "failed", None: "uncertain"}[ending]


@pytest.mark.parametrize(("happened", "event"), [(True, "effect.finished"), (False, "effect.failed")])
async def test_a_person_can_settle_an_answer_nobody_can_read_back(tmp_path, happened, event):
    def make() -> ScriptedDriver:
        return type("Found", (HangsOnAnswers,), {"answer_found": "unknown"})([[Ask("may I?")]])

    await asked_then_crashed(tmp_path, make)

    async with Session.resume("s", root=tmp_path) as session:
        await until(session.attention, session, lambda rows: any(row["kind"] == "uncertain" for row in rows))
        row = next(row for row in await session.attention() if row["id"].startswith("effect/"))

        await session.settle_effect(row["actions"][0]["args"]["id"], happened)

        assert "answer" in [found.data["kind"] for found in await of_type(session, event)]
        assert row["id"] not in [found["id"] for found in await session.attention()]


# Interrupt and stop.


async def test_an_interrupt_in_flight_is_repeated(tmp_path):
    class HangsOnInterrupt(ScriptedDriver):
        async def interrupt(self) -> Receipt:
            if self._spec.resume is None:
                await asyncio.Event().wait()
            return await super().interrupt()

    session = await Session.start(solo_with(lambda: HangsOnInterrupt([[Hang()]])), name="s", root=tmp_path)
    await session.send("@bob", "go")
    await in_state(session, "bob", "running")
    await session.interrupt("@bob")
    await started("interrupt")(session)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        finished = await until(
            lambda: of_type(session, "effect.finished"),
            session,
            lambda found: any(event.data["kind"] == "interrupt" for event in found),
        )

    assert finished


async def test_a_stop_in_flight_is_repeated_with_nothing_left_to_stop(tmp_path):
    class HangsOnStop(ScriptedDriver):
        async def stop(self, grace: float) -> None:
            if self._spec.resume is None and not getattr(self, "stopped_once", False):
                self.stopped_once = True
                await asyncio.sleep(3600)

    session = await Session.start(solo_with(HangsOnStop), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await session.cancel_agent("@bob")
    await started("stop")(session)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        finished = await until(
            lambda: of_type(session, "effect.finished"),
            session,
            lambda found: any(event.data["kind"] == "stop" for event in found),
        )

    assert finished


# A closing session.


async def test_a_session_that_stopped_accepting_work_spends_nothing_on_a_resume(tmp_path):
    starts: list[AgentSpec] = []

    class Counting(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            starts.append(spec)
            return await super().start(spec, report)

    session = await Session.start(solo_with(Counting), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await session.close()
    await abandon(session)
    starts.clear()

    async with Session.resume("s", root=tmp_path) as session:
        status = await session.status()
        assert status["state"] == "closing"

    assert starts == []


async def test_a_crashed_session_rebuilds_to_what_it_held(tmp_path):
    session = await Session.start(solo_with(lambda: ScriptedDriver([[Say("said"), Hang()]])), name="s", root=tmp_path)
    await session.send("@bob", "go")
    await until(lambda: of_type(session, "item.recorded"), session)
    folder = session.folder
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")

    await rebuilt_equals_live(folder)


# What only a harness's next report could have moved.


class TakesItAndBeginsNothing(ScriptedDriver):
    """A harness that accepts a handover and goes quiet, until it comes back from a resume."""

    async def deliver(self, delivery: Delivery) -> Receipt:
        if self._spec.resume is None:
            return Receipt(boundary=delivery.boundary)
        return await super().deliver(delivery)


def begins_nothing() -> ScriptedDriver:
    return TakesItAndBeginsNothing([[Say("heard")]])


async def a_wake_with_no_turn(session: Session) -> None:
    await in_state(session, "bob", "idle")
    await session.send("@bob", "hello")
    await in_state(session, "bob", "waking")
    await started("deliver")(session)


@pytest.mark.parametrize("ending", ["a crash", "an owner's stop"])
async def test_a_wake_that_began_no_turn_goes_again(tmp_path, ending):
    session = await Session.start(solo_with(begins_nothing), name="s", root=tmp_path)
    await a_wake_with_no_turn(session)

    if ending == "a crash":
        await abandon(session)
    else:
        await session.leave()

    async with Session.resume("s", root=tmp_path) as session:
        items = await until(lambda: of_type(session, "item.recorded"), session)
        await in_state(session, "bob", "idle")

    assert items[0].gist == "heard"


async def test_a_launch_cut_short_by_a_stop_is_not_recorded_as_finished(tmp_path):
    class NeverReady(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            return Started(native="n")

    async with Session.start(solo_with(NeverReady), name="s", root=tmp_path) as session:
        await started("launch")(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        ending = await asyncio.wait_for(session.settled(), SECONDS)
        launches = [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "launch"]

    assert launches == []
    assert ending.agents[0]["status"] == "failed"
    assert any(row["what"] == "crash_window" for row in ending.gaps)


class QuietAtFirst(ScriptedDriver):
    """A harness that says ready and takes its time over its goal, as a real one does, until a crash has come."""

    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        if spec.resume is not None:
            return await super().start(spec, report)
        native = f"n-{spec.agent}"
        await report(Ready(native=native))
        return Started(native=native)


def quiet() -> ScriptedDriver:
    return QuietAtFirst([[Say("on it")]])


async def test_a_goal_that_never_began_is_told_again_and_runs(tmp_path):
    team = Team.model_validate(
        {"roles": {"bob": {"harness": scripted()}, "ada": {"harness": harness(quiet), "count": 0}}}
    )
    session = await Session.start(team, name="s", root=tmp_path)
    await session.spawn("ada", "ada", "the important thing")
    await until(lambda: of_type(session, "agent.started"), session, lambda found: len(found) == 2)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        items = await until(lambda: of_type(session, "item.recorded"), session)
        delivered = await of_type(session, "message.sent")

    assert items[0].gist == "on it"
    assert [event.gist for event in delivered] == ["the important thing"]


async def test_a_goal_that_never_began_with_no_way_back_is_named(tmp_path):
    class NoResume(QuietAtFirst):
        pass

    capabilities = NO_RESUME
    roles = {
        "bob": {"harness": scripted()},
        "ada": {"harness": harness(lambda: NoResume([], capabilities=capabilities)), "count": 0},
    }
    session = await Session.start(Team.model_validate({"roles": roles}), name="s", root=tmp_path)
    await session.spawn("ada", "ada", "the important thing")
    await until(lambda: of_type(session, "agent.started"), session, lambda found: len(found) == 2)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "ada", "ended")
        ending = await session.ending()

    row = next(row for row in ending.agents if row["agent"] == "ada")
    assert row["status"] == "lost"
    assert {"agent": "ada", "what": "crash_window", "plane": "control", "count": 1} in ending.gaps


async def test_a_goal_that_never_began_in_a_closing_session_is_named_and_settles(tmp_path):
    team = Team.model_validate(
        {"roles": {"bob": {"harness": scripted()}, "ada": {"harness": harness(quiet), "count": 0}}}
    )
    session = await Session.start(team, name="s", root=tmp_path)
    await session.spawn("ada", "ada", "the important thing")
    await until(lambda: of_type(session, "agent.started"), session, lambda found: len(found) == 2)
    await session.close()
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        ending = await asyncio.wait_for(session.settled(), SECONDS)

    row = next(row for row in ending.agents if row["agent"] == "ada")
    assert (row["status"], row["reason"]) == ("lost", "its session closed before it began its goal")


async def test_a_turn_lost_after_a_finish_still_finishes_the_agent(tmp_path):
    session = await Session.start(
        solo_with(lambda: ScriptedDriver([[Call("agent_finish", {"gist": "done"}), Hang()]])), name="s", root=tmp_path
    )
    await session.send("@bob", "go")
    await until(lambda: of_type(session, "agent.finished"), session)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        ending = await session.ending()

    assert ending.agents[0]["status"] == "finished"
    assert ending.agents[0]["report"] == {"gist": "done", "body": None}


async def test_an_approval_pending_at_a_crash_asks_nobody_afterwards(tmp_path):
    session = await Session.start(solo_with(lambda: ComesBack(first=[Ask("may I?")])), name="s", root=tmp_path)
    await session.send("@bob", "go")
    asked = (await until(session.approvals, session))[0]
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        ending = await asyncio.wait_for(session.settled(), SECONDS)

        assert await session.approvals() == []
        with pytest.raises(Refused) as refused:
            await session.resolve(asked["id"], "allow", expected_version=asked["version"])

    assert ending.reason != "needs_human"
    assert refused.value.refusal.code == "conflict"


# A turn that was cut off.


def comes_back(**role: Any) -> Team:
    return solo_with(lambda: ComesBack([Say("I looked first")]), **role)


async def cut_off_by_a_crash(tmp_path: Path, team: Team) -> None:
    session = await Session.start(team, name="s", root=tmp_path)
    await session.send("@bob", "go")
    await in_state(session, "bob", "running")
    await abandon(session)


async def notices(session: Session) -> list[Any]:
    return [event for event in await of_type(session, "message.sent") if "cut off" in event.gist]


async def test_an_agent_whose_turn_was_lost_is_told_and_woken_on_resume(tmp_path):
    await cut_off_by_a_crash(tmp_path, comes_back())

    async with Session.resume("s", root=tmp_path) as session:
        items = await until(lambda: of_type(session, "item.recorded"), session)
        told = await notices(session)

    assert items[-1].gist == "I looked first"
    assert [(event.stream, event.data["sender"]) for event in told] == [("inbox/bob", "runtime")]


async def test_a_crash_says_what_a_resumed_harness_may_also_show_and_does_not_contradict_it(tmp_path):
    await cut_off_by_a_crash(tmp_path, comes_back())

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "item.recorded"), session)
        told = (await notices(session))[0].gist

    for words in ("cut off by a crash", "in part or in full", "whatever your history shows", "before you repeat"):
        assert words in told


async def test_a_turn_stopped_by_the_owner_is_told_and_woken_on_resume(tmp_path):
    async with Session.start(comes_back(), name="s", root=tmp_path) as session:
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")

    async with Session.resume("s", root=tmp_path) as session:
        items = await until(lambda: of_type(session, "item.recorded"), session)
        told = await notices(session)

    assert items[-1].gist == "I looked first"
    assert [event.gist.partition(".")[0] for event in told] == [
        "Your last turn was cut off by the owner stopping the session"
    ]


async def test_a_turn_a_stop_ran_out_of_time_on_is_told_as_a_stop(tmp_path):
    class Deaf(ComesBack):
        async def interrupt(self) -> Receipt:
            return Receipt(boundary="turn")

    async with Session.start(solo_with(lambda: Deaf([Say("back")])), name="s", root=tmp_path) as session:
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
        await session.leave(grace=0.01)

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "item.recorded"), session)
        told = await notices(session)

    assert ["owner stopping" in event.gist for event in told] == [True]


async def test_a_crash_during_a_stop_still_tells_an_agent_its_stop_cut_it_off(tmp_path):
    session = await Session.start(comes_back(), name="s", root=tmp_path)
    await session.send("@bob", "go")
    await in_state(session, "bob", "running")
    runtime = session._runtime
    runtime.host.closing()
    await session.interrupt("@bob")
    await in_state(session, "bob", "idle")
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "item.recorded"), session)
        told = await notices(session)

    assert ["owner stopping" in event.gist for event in told] == [True]


async def test_a_human_s_interrupt_stays_one_and_nobody_is_told_or_woken_on_resume(tmp_path):
    session = await Session.start(comes_back(), name="s", root=tmp_path)
    await session.send("@bob", "go")
    await in_state(session, "bob", "running")
    await session.interrupt("@bob")
    await in_state(session, "bob", "idle")
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await asyncio.wait_for(session.settled(), SECONDS)
        told = await notices(session)
        turns = await of_type(session, "turn.started")

    assert told == [] and len(turns) == 1


async def test_a_turn_that_ended_before_the_crash_is_nothing_to_tell(tmp_path):
    session = await Session.start(solo_with(lambda: ScriptedDriver([[Say("done")]])), name="s", root=tmp_path)
    await session.send("@bob", "go")
    await until(lambda: of_type(session, "turn.ended"), session)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        assert await notices(session) == []


async def test_a_session_that_stopped_accepting_work_tells_nobody(tmp_path):
    session = await Session.start(comes_back(), name="s", root=tmp_path)
    await session.send("@bob", "go")
    await in_state(session, "bob", "running")
    await session.close()
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        assert await notices(session) == []
        assert len(await of_type(session, "turn.started")) == 1


async def test_a_harness_that_cannot_resume_is_lost_and_told_nothing(tmp_path):
    team = solo_with(lambda: ComesBack(capabilities=NO_RESUME))
    await cut_off_by_a_crash(tmp_path, team)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        assert await notices(session) == []


async def test_a_second_crash_before_the_next_turn_tells_it_again(tmp_path):
    took = asyncio.Event()

    class QuietOnceResumed(ComesBack):
        async def deliver(self, delivery: Delivery) -> Receipt:
            if self._spec.resume is not None and not took.is_set():
                took.set()
                return Receipt(boundary=delivery.boundary)
            return await super().deliver(delivery)

    await cut_off_by_a_crash(tmp_path, solo_with(lambda: QuietOnceResumed([Say("I looked first")])))
    session = await Session.resume("s", root=tmp_path)
    await asyncio.wait_for(took.wait(), SECONDS)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        items = await until(lambda: of_type(session, "item.recorded"), session)
        told = await notices(session)
        offers = await of_type(session, "context.offered")

    assert items[-1].gist == "I looked first"
    assert len({event.gist for event in told}) == 1 and len(told) == 2
    ref = f"{told[0].stream}@{told[0].version}"
    assert len([offer for offer in offers if ref in [item["ref"] for item in offer.data["items"]]]) == 2


@pytest.mark.parametrize("reason", sorted(CUT_OFF))
async def test_a_driver_cannot_say_what_only_the_runtime_can(tmp_path, reason):
    class Forges(ComesBack):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            async def forged(said: Report) -> None:
                await report(TurnEnded(reason=reason) if isinstance(said, TurnEnded) else said)

            return await super().start(spec, forged)

    session = await Session.start(solo_with(lambda: Forges(first=[Say("done")])), name="s", root=tmp_path)
    await session.send("@bob", "go")
    await until(lambda: of_type(session, "turn.ended"), session)
    await in_state(session, "bob", "idle")
    gaps = (await session.ending()).gaps
    ended = await of_type(session, "turn.ended")
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        assert await notices(session) == []

    assert [event.data["reason"] for event in ended] == ["unknown"]
    assert [gap["what"] for gap in gaps] == ["unknown_update"]


async def test_a_wake_the_budget_refuses_ends_the_session_needs_human(tmp_path):
    await cut_off_by_a_crash(tmp_path, comes_back(budget={"tokens": 1000}))

    async with Session.resume("s", root=tmp_path) as session:
        ending = await asyncio.wait_for(session.settled(), SECONDS)
        told = await notices(session)
        kinds = {row["kind"] for row in await session.attention()}

    assert ending.reason == "needs_human"
    assert len(told) == 1
    assert "budget" in kinds


async def test_a_budget_that_falls_back_to_turns_still_wakes_an_agent_after_a_crash(tmp_path):
    await cut_off_by_a_crash(tmp_path, comes_back(budget={"tokens": 1000, "turns": 5, "fallback": "turns"}))

    async with Session.resume("s", root=tmp_path) as session:
        items = await until(lambda: of_type(session, "item.recorded"), session)

    assert items[-1].gist == "I looked first"


async def test_raising_the_budget_lets_the_wake_it_refused_go_on(tmp_path):
    await cut_off_by_a_crash(tmp_path, comes_back(budget={"tokens": 1000}))

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "wake.refused"), session)

        await session.set_budget("role:bob", limits={"tokens": 1000, "turns": 5}, fallback="turns")

        items = await until(lambda: of_type(session, "item.recorded"), session)

    assert items[-1].gist == "I looked first"


async def test_a_lost_turn_stays_in_attention_until_its_agent_is_back_in_a_turn(tmp_path):
    await cut_off_by_a_crash(tmp_path, comes_back(budget={"tokens": 1000}))

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "wake.refused"), session)
        assert "turn/bob" in {row["id"] for row in await session.attention()}

        await session.set_budget("role:bob", limits={"tokens": 1000, "turns": 5}, fallback="turns")

        await until(lambda: of_type(session, "turn.started"), session, lambda found: len(found) == 2)
        assert "turn/bob" not in {row["id"] for row in await session.attention()}


# A goal that never began.


def goal_to_come(**team: Any) -> Team:
    roles = {
        "bob": {"harness": harness(lambda: ComesBack([Say("back")]))},
        "ada": {"harness": harness(quiet), "count": 0},
    }
    return Team.model_validate({"roles": roles, **team})


async def goal_unbegun(tmp_path: Path, team: Team, **options: Any) -> None:
    """A crash with `ada` up on a goal it never began, and `bob` in a turn if the team has one."""
    session = await Session.start(team, name="s", root=tmp_path, **options)
    if "bob" in team.roles:
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
    await session.spawn("ada", "ada", "the important thing")
    await until(lambda: of_type(session, "agent.started"), session, lambda found: len(found) == len(team.roles))
    await abandon(session)


async def test_a_goal_the_budget_will_not_retell_ends_the_session_needs_human(tmp_path):
    await goal_unbegun(tmp_path, goal_to_come(budget={"tokens": 1000}))

    async with Session.resume("s", root=tmp_path) as session:
        ending = await asyncio.wait_for(session.settled(), SECONDS)

    assert ending.reason == "needs_human"


async def test_a_goal_the_budget_held_a_turn_for_runs_after_a_crash(tmp_path):
    roles = {"ada": {"harness": harness(quiet), "count": 0, "budget": {"turns": 1}}}
    await goal_unbegun(tmp_path, Team.model_validate({"roles": roles}))

    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "turn.started"), session)
        refused = await of_type(session, "wake.refused")

    assert refused == []


async def test_a_goal_past_the_wall_ends_its_agent_and_the_session_drains(tmp_path):
    clock = ManualClock(1000.0)
    await goal_unbegun(tmp_path, goal_to_come(budget={"wall": "1m"}), clock=clock)
    clock.advance(120.0)

    async with Session.resume("s", root=tmp_path, clock=clock) as session:
        ending = await asyncio.wait_for(session.settled(), SECONDS)

    ada = next(agent for agent in ending.agents if agent["agent"] == "ada")
    assert ending.reason == "budget_exhausted"
    assert (ada["status"], ada["reason"]) == ("lost", "its session closed before it began its goal")


# A session from before a change.


def older(folder: Path, *, version: int) -> None:
    """Leave a journal's `v_agents` as an SDK with one column fewer left it, under that SDK's view version."""
    db = sqlite3.connect(folder / "journal.sqlite")
    db.execute("ALTER TABLE v_agents DROP COLUMN stopped")
    db.execute("UPDATE v_folds SET version = ? WHERE view = 'agents'", (version,))
    db.commit()
    db.close()


async def test_a_session_from_before_a_view_changed_resumes_and_tells_its_agent(tmp_path):
    await cut_off_by_a_crash(tmp_path, comes_back())
    older(tmp_path / "sessions" / "s", version=Agents.version - 1)

    async with Session.resume("s", root=tmp_path) as session:
        items = await until(lambda: of_type(session, "item.recorded"), session)

    assert items[-1].gist == "I looked first"


async def test_agents_nobody_can_read_stop_a_resume_loudly(tmp_path):
    await cut_off_by_a_crash(tmp_path, comes_back())
    older(tmp_path / "sessions" / "s", version=Agents.version)

    with pytest.raises(Refused, match="ValidationError"):
        await Session.resume("s", root=tmp_path)

    assert not is_held(tmp_path / "sessions" / "s")


# What nobody may wait on for ever.


class NeverSays(ScriptedDriver):
    """A harness whose handover hangs, and which hangs again when asked what became of it."""

    async def deliver(self, delivery: Delivery) -> Receipt:
        await asyncio.Event().wait()
        raise AssertionError

    async def reconcile(self, input_id: str) -> Reconciled:
        await asyncio.Event().wait()
        raise AssertionError


async def a_handover_nobody_will_explain(tmp_path: Path, make: type[NeverSays] = NeverSays) -> None:
    session = await Session.start(solo_with(make), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await session.send("@bob", "hello")
    await started("deliver")(session)
    await abandon(session)


async def test_a_harness_that_hangs_in_reconcile_answers_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "_RECONCILE_SECONDS", 0.01)
    await a_handover_nobody_will_explain(tmp_path)

    async with Session.resume("s", root=tmp_path) as session:
        failed = await until(lambda: of_type(session, "effect.failed"), session)

    assert "in flight" in failed[0].data["error"]


async def test_a_harness_that_breaks_in_reconcile_answers_unknown(tmp_path):
    class Broken(NeverSays):
        async def reconcile(self, input_id: str) -> Reconciled:
            raise RuntimeError("a bug in the driver")

    session = await Session.start(solo_with(Broken), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await session.send("@bob", "hello")
    await started("deliver")(session)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        assert await until(lambda: of_type(session, "effect.failed"), session)


async def test_a_stop_asked_during_recovery_ends_it(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "_RECONCILE_SECONDS", 3600.0)
    asked = asyncio.Event()

    class Telling(NeverSays):
        async def reconcile(self, input_id: str) -> Reconciled:
            asked.set()
            return await super().reconcile(input_id)

    await a_handover_nobody_will_explain(tmp_path, Telling)
    runtime = Runtime(tmp_path / "sessions" / "s")

    starting = asyncio.ensure_future(runtime.start())
    await asyncio.wait_for(asked.wait(), SECONDS)
    runtime.ask_to_stop()
    await asyncio.wait_for(starting, SECONDS)
    await asyncio.wait_for(runtime.run(), SECONDS)
    await runtime.stop()

    assert not is_held(runtime.folder)


class BrokenOnResume(ScriptedDriver):
    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        if spec.resume is not None:
            raise RuntimeError("a bug in the driver")
        return await super().start(spec, report)


async def test_one_broken_driver_on_resume_loses_one_agent(tmp_path):
    team = Team.model_validate(
        {"roles": {"bad": {"harness": harness(BrokenOnResume)}, "good": {"harness": scripted()}}}
    )
    session = await Session.start(team, name="s", root=tmp_path)
    await in_state(session, "bad", "idle")
    await in_state(session, "good", "idle")
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bad", "ended")
        await in_state(session, "good", "idle")
        ending = await session.ending()

    assert next(row for row in ending.agents if row["agent"] == "bad")["reason"] == (
        "its harness could not resume: RuntimeError"
    )
    assert any(row["what"] == "crash_window" for row in ending.gaps)


async def test_a_group_that_will_not_die_loses_its_own_agent_and_no_other(tmp_path, monkeypatch):
    team = Team.model_validate({"roles": {"bad": {"harness": scripted()}, "good": {"harness": scripted()}}})
    session = await Session.start(team, name="s", root=tmp_path)
    await in_state(session, "bad", "idle")
    await in_state(session, "good", "idle")
    await abandon(session)

    async def stubborn(folder: Path, grace: float) -> tuple[str, ...]:
        if folder.name == "bad":
            raise DriverError("process group 7 outlived SIGKILL")
        return ()

    monkeypatch.setattr(recovery, "reap", stubborn)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bad", "ended")
        await in_state(session, "good", "idle")
        ending = await session.ending()

    assert next(row for row in ending.agents if row["agent"] == "bad")["reason"] == "process group 7 outlived SIGKILL"


async def test_a_harness_that_exits_at_once_on_resume_costs_no_wait_and_says_why(tmp_path):
    class ExitsOnResume(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            if spec.resume is None:
                return await super().start(spec, report)
            await report(Exited(reason="no such session"))
            return Started(native=spec.resume)

    session = await Session.start(solo_with(ExitsOnResume), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await abandon(session)

    resumed = await asyncio.wait_for(Session.resume("s", root=tmp_path)._entered(), SECONDS)
    await in_state(resumed, "bob", "ended")
    ending = await resumed.ending()
    await resumed.leave()

    assert ending.agents[0]["reason"] == "no such session"
    assert any(row["what"] == "crash_window" for row in ending.gaps)


async def test_a_group_an_ended_agent_left_is_named(tmp_path, monkeypatch):
    async def unproven(folder: Path, grace: float) -> tuple[str, ...]:
        return ("process group 4242 outlived its leader and cannot be proved ours",)

    session = await Session.start(solo_with(ScriptedDriver), name="s", root=tmp_path)
    await in_state(session, "bob", "idle")
    await session.cancel_agent("@bob")
    await in_state(session, "bob", "ended")
    await abandon(session)
    monkeypatch.setattr(recovery, "reap", unproven)

    async with Session.resume("s", root=tmp_path) as session:
        recorded = await of_type(session, "native.recorded")
        gaps = await of_type(session, "gap.recorded")

    assert "process group 4242" in recorded[0].data["raw"]
    assert gaps[0].data["what"] == "crash_window"


async def test_a_resume_under_other_versions_is_labelled_and_goes_on(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        folder = session.folder
    manifest = json.loads((folder / MANIFEST).read_text())
    (folder / MANIFEST).write_text(json.dumps({**manifest, "sdk_version": "0.0.1"}))

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = await of_type(session, "runtime.started")

    assert started[0].data["drift"] == []
    assert started[-1].data["drift"] == [f"the SDK 0.0.1 is now {__version__}"]
    assert f"the SDK 0.0.1 is now {__version__}" in started[-1].gist


async def test_a_resume_under_the_same_versions_says_nothing(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = await of_type(session, "runtime.started")

    assert [event.gist for event in started] == ["runtime started", "runtime started"]
