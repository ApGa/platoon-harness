"""The host: effects performed level-triggered, each harness heard in order, and links that outlive the daemon."""

import asyncio
import base64
import json
import os
import shutil
import signal
import socket
import stat
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from platoon_harness import Session, Team, __version__, told
from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
    Capabilities,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
    Exited,
    GapReport,
    Item,
    Ready,
    Report,
    Reporter,
    TurnEnded,
    TurnStarted,
    Usage,
)
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.env import tmpdir
from platoon_harness.drivers.levels import Check, Conformance, implementation
from platoon_harness.drivers.process import RECORD, Record
from platoon_harness.kernel import Kernel, ManualClock, Outcome, Refusal, Refused, hash_token, is_held
from platoon_harness.primitives import Verdict
from platoon_harness.primitives.approvals import ASK_LIMIT
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, LocalAuthority, Runtime, SpawnRequest
from platoon_harness.runtime.paths import agent_folder, write_conformance
from platoon_harness.testing import Ask, Call, Exit, Hang, Say, ScriptedDriver, Think

from .support import SECONDS, harness, in_state, journal, of_type, offers, scripted, solo, until

MAKING = "`check_driver` checks it, and `write_conformance` keeps what it found here"

pytestmark = pytest.mark.timeout(30)


async def ended(session: Session, agent: str) -> dict[str, Any]:
    await in_state(session, agent, "ended")
    return next(row for row in (await session.ending()).agents if row["agent"] == agent)


async def stops(session: Session, *kinds: str) -> list[Any]:
    """The events of `kinds` of each agent's stop."""
    return [event for event in await of_type(session, *kinds) if event.data["kind"] == "stop"]


async def erased(session: Session) -> bool:
    """Whether the bytes of a body a person redacted are gone."""
    return any(event.data["kind"] == "erase" for event in await of_type(session, "effect.finished"))


async def test_a_commit_that_failed_and_landed_all_the_same_does_not_run_twice(tmp_path):
    """A failed commit's outcome is unknown. Told `unavailable` of something that landed, the host retries, and the key
    it keeps across its tries answers from the journal."""
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        runtime = session._runtime
        kernel, real = runtime.kernel, runtime.kernel.submit
        answers = iter([Refusal(code="unavailable", retry_after=0.001, detail="journal: disk I/O error")])

        async def lands_but_says_not(*args: Any, **options: Any) -> Outcome:
            outcome = await real(*args, **options)
            refusal = next(answers, None)
            return outcome if refusal is None else Outcome(op=args[1], args_hash="", refusal=refusal)

        kernel.submit = lands_but_says_not
        await runtime.host.insist("agent.report", {"agent": "bob", "report": Item(kind="message", gist="once")})
        del kernel.submit

        assert [event.gist for event in await of_type(session, "item.recorded")] == ["once"]


class Recording(ScriptedDriver):
    """A scripted harness that keeps what it was started and handed."""

    specs: list[AgentSpec] = []
    deliveries: list[Delivery] = []

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        Recording.specs.append(spec)
        return await super().start(spec, report)

    async def deliver(self, delivery: Delivery) -> None:
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


def launch_of(agent: str) -> Callable[[list[Any]], bool]:
    return lambda found: any(event.data["kind"] == "launch" and event.agent == agent for event in found)


def solo_with(make: Callable[[], Any], **role: Any) -> Team:
    return Team.model_validate({"roles": {"bob": {"harness": harness(make), **role}}})


class Stuck(ScriptedDriver):
    """A harness whose handover never comes back."""

    async def deliver(self, delivery: Delivery) -> None:
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
        await session.cancel_agent("@bob")

        assert await asyncio.wait_for(heard, SECONDS) == (
            AgentRef(agent="bob", role="bob"),
            AgentOutcome(status="cancelled", report="bob cancelled: cancelled by human:you"),
        )


async def test_a_parent_hears_of_a_child_s_end_only_once_its_authority_has(tmp_path):
    """A child's stop tells its authority how it ended, last, so its parent, between turns, is handed the report only
    once that has returned: here, once the test lets it."""
    told, go = asyncio.Event(), asyncio.Event()

    class Holding(LocalAuthority):
        async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
            told.set()
            await go.wait()

    spawning = Call("agent_spawn", {"name": "ada", "child_role": "worker", "goal": "report"})
    roles = {
        "lead": {"harness": scripted([spawning], [Say("heard")]), "may_spawn": ["worker"]},
        "worker": {"harness": scripted([Call("agent_finish", {"gist": "done"})])},
    }
    team = Team.model_validate({"roles": roles})
    async with Session.start(team, authority=Holding(team), root=tmp_path) as session:
        await in_state(session, "lead", "idle")
        await session.send("@lead", "start")
        await asyncio.wait_for(told.wait(), SECONDS)
        held = await offers(session)
        go.set()
        heard = await until(lambda: offers(session), session, lambda found: len(found) == 2)
        finished = await until(lambda: stops(session, "effect.finished"), session)

    assert [offer.agent for offer in held] == ["lead"]
    assert heard[1].agent == "lead" and heard[1].seq > finished[0].seq


async def test_an_authority_hears_of_an_end_whose_harness_would_not_stop(tmp_path):
    """A stop tells the authority how its agent ended even when ending the harness fails, and the parent is handed the
    report only after."""
    told: list[str] = []

    class Listening(LocalAuthority):
        async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
            told.append(agent.agent)

    class Stubborn(ScriptedDriver):
        async def stop(self, grace: float) -> None:
            await super().stop(grace)
            raise DriverError("it would not stop")

    spawning = Call("agent_spawn", {"name": "ada", "child_role": "worker", "goal": "report"})
    roles = {
        "lead": {"harness": scripted([spawning], [Say("heard")]), "may_spawn": ["worker"]},
        "worker": {"harness": harness(lambda: Stubborn([[Call("agent_finish", {"gist": "done"})]]))},
    }
    team = Team.model_validate({"roles": roles})
    async with Session.start(team, authority=Listening(team), root=tmp_path) as session:
        await in_state(session, "lead", "idle")
        await session.send("@lead", "start")
        failed = await until(lambda: stops(session, "effect.failed"), session)
        heard = await until(lambda: offers(session), session, lambda found: len(found) == 2)

    assert told == ["ada"]
    assert heard[1].agent == "lead" and heard[1].seq > failed[0].seq


async def test_a_long_forgotten_does_not_lose_the_agent(tmp_path):
    """Compaction can name more than one event holds, so the list is a body, whatever its length."""
    forgotten = tuple(f"{index:036d}" for index in range(500))

    class Compacting(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await super().start(spec, report)
            await report(Compacted(forgotten=forgotten, summary="what was kept"))

    async with Session.start(solo_with(Compacting), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        compacted = await until(lambda: of_type(session, "context.compacted"), session)
        kept = await session.get_body(compacted[0].data["forgotten"])
        summary = await session.get_body(compacted[0].data["summary"])
        ending = await session.ending()

    assert tuple(json.loads(kept)) == forgotten and summary == b"what was kept"
    assert ending.agents[0]["state"] == "idle" and ending.gaps == ()


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
    assert spec.instructions is not None and "`mcp__ph__wait`" in spec.instructions
    assert "wait" in ready.data["tools_visible"]


async def test_a_harness_that_shows_our_tools_by_their_own_names_is_told_them_by_those(tmp_path, recording):
    """OpenHands shows an MCP server's tools as the server lists them, so its words and its tool URL name none."""
    bare = ScriptedDriver().describe().capabilities.model_copy(update={"tool_names": "bare"})
    team = Team.model_validate({"roles": {"bob": {"harness": harness(lambda: recording([], capabilities=bare))}}})

    async with Session.start(team, cwd=tmp_path, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        spec = recording.specs[0]

    assert spec.tools is not None and spec.tools.url.endswith("?surface=mcp")
    assert spec.instructions is not None and "`wait`" in spec.instructions and "mcp__ph__" not in spec.instructions


async def test_a_role_has_the_last_word_in_its_agents_instructions(tmp_path, recording):
    """The preamble says how to end, and a role may say otherwise, so the role's words come after it."""
    team = solo_with(recording, instructions="Never call agent_finish.")

    async with Session.start(team, cwd=tmp_path, root=tmp_path) as session:
        await in_state(session, "bob", "idle")

    instructions = recording.specs[0].instructions
    assert instructions is not None and instructions.startswith("You are @bob.")
    assert instructions.endswith(
        "make `mcp__ph__agent_finish` your last call, or your session never closes. Told "
        "nothing of the kind, stay: it ends you for good, and a turn that only ends leaves you "
        "here for the next message.\n\nNever call agent_finish."
    )


async def test_what_a_harness_is_told_is_journaled_at_launch_and_at_every_resume(tmp_path, recording):
    """A harness that took no turn is started anew on a resume, which tells it again."""
    async with Session.start(solo_with(recording, instructions="Be brief."), name="told", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
    async with Session.resume("told", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        instructed = await of_type(session, "agent.instructed")
        told = [(await session.get_body(event.data["body"])).decode() for event in instructed]

    assert len(told) == 2 and told == [spec.instructions for spec in recording.specs]


async def test_a_harness_that_reopens_its_session_is_handed_what_it_was_told_when_that_began(tmp_path, recording):
    """Claude Code and Codex keep what a session began with, whatever a resume passes, so a resume hands that again and
    journals it, though who the agent can reach has changed since."""
    roles = {"bob": {"harness": harness(recording)}, "ann": {"harness": harness(recording), "count": 0}}
    team = Team.model_validate({"roles": roles, "topology": {"edges": {"bob": ["all"]}, "limits": {"max_hops": 4}}})
    async with Session.start(team, name="told", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        await session.spawn("ann", "ann")
        await in_state(session, "ann", "idle")
    async with Session.resume("told", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        instructed = [event for event in await of_type(session, "agent.instructed") if event.agent == "bob"]
        told = [(await session.get_body(event.data["body"])).decode() for event in instructed]

    launched, resumed = [spec for spec in recording.specs if spec.agent == "bob"]
    assert resumed.resume is not None and "You can message: @you." in told[0]
    assert told == [launched.instructions, resumed.instructions] == [told[0]] * 2


async def test_an_empty_template_tells_a_harness_only_its_role_s_words(tmp_path, recording):
    roles = {"bob": {"harness": harness(recording), "preamble": ""}, "ann": {"harness": harness(recording)}}
    team = Team.model_validate(
        {"preamble": "Team: @{name}.", "roles": {**roles, "eve": {**roles["bob"], "instructions": "Mine."}}}
    )

    async with Session.start(team, root=tmp_path) as session:
        for agent in ("ann", "bob", "eve"):
            await in_state(session, agent, "idle")

    assert {spec.agent: spec.instructions for spec in recording.specs} == {
        "ann": "Team: @ann.",
        "bob": None,
        "eve": "Mine.",
    }


async def test_nothing_told_is_journaled_as_nothing(tmp_path, recording):
    def none() -> ScriptedDriver:
        return recording(capabilities=Capabilities(persistent=True, boundaries={"turn"}))

    async with Session.start(solo_with(none), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        instructed = await of_type(session, "agent.instructed")

    assert [event.data["body"] for event in instructed] == [None]


async def test_a_role_s_preamble_is_told_in_place_of_its_team_s_and_its_words_come_last(tmp_path, recording):
    role = {"harness": harness(recording), "preamble": "Role: @{name}.", "instructions": "Use `peers`."}
    team = Team.model_validate(
        {"preamble": "Team: @{name}.", "roles": {"bob": role, "ann": {**role, "preamble": None}}}
    )

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "ann", "idle")
        await in_state(session, "bob", "idle")

    assert sorted(spec.instructions for spec in recording.specs) == [
        "Role: @bob.\n\nUse `mcp__ph__peers`.",
        "Team: @ann.\n\nUse `mcp__ph__peers`.",
    ]


async def test_what_each_role_would_be_told_is_what_a_session_tells_it(tmp_path, recording):
    def leading() -> ScriptedDriver:
        return recording([[Call("agent_spawn", {"name": "worker", "child_role": "worker"}), Say("started")]])

    roles = {
        "lead": {"harness": harness(leading), "may_spawn": ["worker"], "instructions": "Start `agent.spawn` once."},
        "worker": {"harness": harness(recording), "preamble": "You are @{name}.\n{ending}"},
    }
    topology = {"edges": {"lead": ["children", "human"], "worker": ["parent"]}, "limits": {"max_hops": 4}}
    team = Team.model_validate({"roles": roles, "topology": topology})
    expected = await told(team)

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@lead", "go")
        await until(lambda: of_type(session, "agent.started"), session, lambda started: len(started) == 2)

    assert {spec.role: spec.instructions for spec in recording.specs} == expected


@pytest.mark.parametrize("allowed", [False, True])
async def test_a_harness_starts_agents_of_its_own_only_where_its_role_allows(tmp_path, recording, allowed):
    async with Session.start(solo_with(recording, allow_native_children=allowed), root=tmp_path) as session:
        await in_state(session, "bob", "idle")

    assert recording.specs[0].allow_native_children is allowed


async def test_a_narrowed_role_keeps_ops_list_so_it_keeps_its_tools(tmp_path):
    async with Session.start(solo(tools=["wait"]), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        opened = (await of_type(session, "session.opened"))[0]
        started = (await of_type(session, "agent.started"))[0]

    assert "ops.list" in opened.data["roles"]["bob"]["tools"]
    assert started.data["tools_visible"] == ["wait"]


async def test_the_preamble_reaches_a_harness_once_and_never_a_delivery(tmp_path, recording):
    team = solo_with(recording, instructions="Be brief.")

    async with Session.start(team, cwd=tmp_path, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "one")
        await until(recorded(recording), session)
        await in_state(session, "bob", "idle")
        await session.send("@bob", "two")
        await until(recorded(recording), session, lambda handed: len(handed) > 1)

    assert len(recording.specs) == 1
    assert recording.specs[0].instructions.count("You are @bob.") == 1
    assert all("You are @bob." not in delivery.text for delivery in recording.deliveries)


async def test_a_harness_with_no_tool_path_gets_no_binding(tmp_path, recording):
    def none() -> ScriptedDriver:
        return recording(capabilities=Capabilities(persistent=True, boundaries={"turn"}))

    team = Team.model_validate({"roles": {"bob": {"harness": harness(none)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")

    assert recording.specs[0].tools is None
    assert recording.specs[0].instructions is None


async def test_a_role_s_effort_reaches_its_harness(tmp_path, recording):
    class Taking(Recording):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            Recording.specs.append(spec)
            return await super().start(spec.model_copy(update={"effort": None}), report)

    team = solo_with(Taking, effort="low")

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")

    assert recording.specs[0].effort == "low"


async def test_a_harness_that_cannot_honor_an_effort_fails_its_spawn(tmp_path):
    async with Session.start(solo(effort="low"), root=tmp_path) as session:
        row = await asyncio.wait_for(ended(session, "bob"), SECONDS)

    assert (row["status"], row["reason"]) == ("failed", "its spawn failed: a scripted harness has no effort to set")


async def test_a_role_with_an_auth_profile_is_on_a_key_whatever_login_the_harness_has(tmp_path, monkeypatch):
    class OnAPlan(ScriptedDriver):
        def describe(self) -> DriverInfo:
            return super().describe().model_copy(update={"login": "plan"})

    monkeypatch.setenv("KEY", "a-key")
    bob = {"harness": harness(OnAPlan), "auth": "keyed", "model": "m"}
    fields = {"auth": {"keyed": {"env": ["KEY"]}}, "roles": {"bob": bob}}

    async with Session.start(Team.model_validate(fields), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = (await of_type(session, "agent.started"))[0]

    assert started.data["verified"]["login"] == "key"


async def test_capabilities_and_levels_reach_agent_started(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = (await of_type(session, "agent.started"))[0]

    assert started.data["declared"]["persistent"] is True
    assert started.data["verified"]["tools"] == "visible"
    assert started.data["verified"]["allow_native_children"] is False
    assert started.data["levels"]["operational"]["state"] == "unverified"
    assert f"no conformance result for scripted is kept: {MAKING}" in started.data["levels"]["operational"]["reasons"]


def passing(version: str | None, driver: str = "scripted", made_by: object = ScriptedDriver()) -> Conformance:
    """A result of a harness at `version`, made here by `made_by`, whose every check that a level needs passed."""
    needed = (
        "describe_starts_nothing",
        "turn_end_reported",
        "exit_reported",
        "stop_leaves_no_process",
        "stop_ends_a_running_tool",
        "runs_in_its_workspace",
        "malformed_frame_is_a_gap",
    )
    checks = tuple(Check(name=name, state="passed") for name in needed)
    pinned = {"implementation": implementation(made_by), "sdk": __version__, "host": socket.gethostname()}
    return Conformance(driver=driver, version=version, checks=checks, **pinned)


async def test_levels_come_from_the_conformance_result_kept_for_the_harness_that_runs(tmp_path):
    """The host reads what `doctor --check` kept under the root at every launch and resume, and records it on the
    start, so a level rests on a result anyone can read back."""
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
    write_conformance(tmp_path, passing("1"))
    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started, resumed = await of_type(session, "agent.started"), await of_type(session, "agent.resumed")
        kept = await session.get_body(resumed[0].data["conformance"].removeprefix("sha256:"))

    assert started[0].data["conformance"] is None
    assert started[0].data["levels"]["operational"]["state"] == "unverified"
    assert resumed[0].data["levels"]["operational"] == {"state": "met", "reasons": []}
    assert resumed[0].data["levels"]["observable"]["state"] == "met"
    assert Conformance.model_validate_json(kept) == passing("1")


async def test_a_result_kept_for_another_version_says_nothing_of_the_one_that_runs(tmp_path):
    write_conformance(tmp_path, passing("0"))
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = (await of_type(session, "agent.started"))[0]

    reasons = started.data["levels"]["operational"]["reasons"]
    assert started.data["levels"]["operational"]["state"] == "unverified"
    assert reasons == [f"conformance ran on scripted 0, and this is scripted 1: {MAKING}"]
    assert started.data["conformance"] is None


async def test_a_result_of_an_unknown_version_vouches_for_nothing(tmp_path):
    """A harness that says no version is known to be no binary a result ran on, even one that said none either."""
    write_conformance(tmp_path, passing(None))
    team = Team.model_validate({"roles": {"bob": {"harness": scripted(version=None)}}})
    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = (await of_type(session, "agent.started"))[0]

    assert started.data["levels"]["operational"] == {
        "state": "unverified",
        "reasons": ["scripted said no version, so no result can speak for it"],
    }
    assert started.data["conformance"] is None


async def test_a_driver_that_calls_itself_claude_earns_nothing_from_what_was_kept_of_claude(tmp_path):
    """A name is a driver's own to give, so a result is pinned to the class that made it too: a driver calling itself
    `claude` at claude's version runs, and what was kept of the claude driver's checks says nothing of it."""
    write_conformance(tmp_path, passing("2.1.316", driver="claude", made_by=ClaudeDriver()))
    team = Team.model_validate({"roles": {"bob": {"harness": scripted(name="claude", version="2.1.316")}}})
    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = (await of_type(session, "agent.started"))[0]

    ran = "platoon_harness.drivers.claude:ClaudeDriver"
    assert started.data["levels"]["operational"] == {
        "state": "unverified",
        "reasons": [f"conformance ran on {ran}, and this is platoon_harness.testing.scripted:ScriptedDriver: {MAKING}"],
    }
    assert started.data["conformance"] is None


async def test_a_role_that_lets_its_harness_start_agents_of_its_own_is_profiled_so(tmp_path):
    async with Session.start(solo(allow_native_children=True), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        started = (await of_type(session, "agent.started"))[0]

    assert started.data["verified"]["allow_native_children"] is True


async def test_a_harness_that_will_not_start_fails_its_spawn_and_its_parent_hears(tmp_path):
    class Broken(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
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
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            pass

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
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
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
        async def deliver(self, delivery: Delivery) -> None:
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

    goal = recording.specs[0].goal
    assert goal is not None and goal.text == "the short of it\n\nthe long of it"
    assert [(item.ref, item.gist, item.body) for item in goal.items] == [("agent/ada@1", "the short of it", True)]


# Delivery.


async def test_a_message_reaches_a_harness_as_text_with_the_ref_and_the_input(tmp_path, recording):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(recording)}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        sent = await session.send("@bob", "read this", body="the whole of it")
        await until(recorded(recording), session)

    delivery = recording.deliveries[0]
    assert delivery.text.splitlines() == [
        f"New messages (delivery {delivery.input}):",
        f"- {sent['ref']} from @you: read this",
        "  It has a body: pass its ref as `ref` to `mcp__ph__blob_get`.",
    ]
    assert delivery.items[0].sender == "@you"
    assert delivery.items[0].body is True
    assert "sha256:" not in delivery.text


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
        assert len(await offers(session)) == 2


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

        await session.cancel_agent("@bob")

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
        assert len(await offers(session)) == 1

        await session.release("@bob")
        offered = await until(lambda: offers(session), session, lambda found: len(found) == 2)

        assert offered[-1].data["items"][0]["ref"] == "inbox/bob@2"


async def test_a_delivery_already_asked_for_waits_out_a_takeover(tmp_path):
    held = asyncio.Event()
    delivered = asyncio.Event()

    class Slow(ScriptedDriver):
        async def deliver(self, delivery: Delivery) -> None:
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

        await session.release("@bob")
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
        stored = await session.get_body(item.data["body"])
        assert stored == b"the whole of what it said"


async def test_a_delta_reaches_a_follower_and_never_the_journal(tmp_path):
    release = asyncio.Event()

    class Talking(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await super().start(spec, report)
            await release.wait()
            await report(Delta(text="live words"))
            await report(Item(kind="tool", phase="started", gist="looking"))

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Talking)}}})

    async with Session.start(team, root=tmp_path) as session:
        frames = session.deltas("bob")
        next_frame = asyncio.ensure_future(anext(frames))
        release.set()

        frame = await asyncio.wait_for(next_frame, SECONDS)

        assert frame.text == "live words"
        assert "live words" not in json.dumps([event.gist for event in await journal(session)])
        await frames.aclose()


def still_saying() -> Team:
    """An agent that says `first` and records it, then says `more` and goes on, as a tool starts. Live text is held back
    until the next report, as a secret could straddle two deltas."""
    said = (
        TurnStarted(turn="t1"),
        Delta(text="first"),
        Item(kind="message", gist="first"),
        Delta(text="more"),
        Item(kind="tool", phase="started", gist="looking"),
    )
    return Team.model_validate({"roles": {"bob": {"harness": harness(saying(*said))}}})


async def test_live_text_is_a_tail_bound_to_the_item_that_replaces_it(tmp_path):
    team = still_saying()

    async with Session.start(team, root=tmp_path) as session:
        await until(lambda: of_type(session, "item.recorded"), session, lambda found: len(found) == 2)
        frames = session.deltas("bob")
        frame = await asyncio.wait_for(anext(frames), SECONDS)
        await frames.aclose()
        item = (await of_type(session, "item.recorded"))[0]

    assert (frame.text, frame.lag, frame.ended) == ("more", 0, item.seq)


async def test_live_text_of_an_agent_that_ends_says_so_once_and_then_ends(tmp_path):
    team = still_saying()

    async with Session.start(team, root=tmp_path) as session:
        await until(lambda: of_type(session, "item.recorded"), session, lambda found: len(found) == 2)
        frames = session.deltas("bob")
        said = await asyncio.wait_for(anext(frames), SECONDS)

        await session.cancel_agent("@bob")

        rest = await asyncio.wait_for(alist(frames), SECONDS)
        ended = (await of_type(session, "agent.ended"))[0]

    assert said.text == "more"
    assert [(frame.text, frame.ended) for frame in rest] == [("", ended.seq)]


async def alist[T](items: AsyncIterator[T]) -> list[T]:
    return [item async for item in items]


async def test_every_word_of_the_vocabulary_has_somewhere_to_go(tmp_path):
    said: list[Report] = [
        TurnStarted(turn="t1"),
        Usage(tokens=7, label="provider"),
        GapReport(what="hidden_call"),
        Item(kind="tool", gist="ran it"),
        TurnEnded(reason="stopped"),
    ]

    class Reporting(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await super().start(spec, report)
            for item in said:
                await report(item)

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Reporting)}}})

    async with Session.start(team, root=tmp_path) as session:
        await until(lambda: of_type(session, "turn.ended"), session)
        ending = await session.ending()

    assert ending.usage["tokens"] == {"amount": 7.0, "label": "provider", "unmeasured": 0}
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
        await session.task_add("work", "do it")
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


async def test_a_harness_that_exits_twice_before_a_turn_ends_is_lost_and_its_parent_hears(tmp_path):
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

        assert told[-1].gist == "w lost: its harness exited again before a turn of its ended: it fell over"
        assert (await session.ending()).reason == "agent_failed"


async def test_a_driver_that_raises_something_unexpected_loses_its_harness_with_no_silent_hang(tmp_path):
    class Crashing(ScriptedDriver):
        async def deliver(self, delivery: Delivery) -> None:
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
        assert [gap["what"] for gap in (await session.ending()).gaps] == ["unknown_update"]


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


async def test_an_ask_a_person_redacted_and_asked_again_is_denied_and_its_harness_lives_on(tmp_path):
    """Redacted content does not come back, so the journal refuses the ask, and the approval is answered `deny`, as any
    the journal refuses is, with its harness at work still."""
    answers: list[tuple[str, str]] = []

    class Repeating(ScriptedDriver):
        async def answer(self, approval: str, verdict: Any) -> None:
            answers.append((approval, verdict))

    team = Team.model_validate({"roles": {"bob": {"harness": harness(Repeating)}}})
    leaked = "curl -H 'Authorization: leaked-key' https://example.invalid"

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        host = session._runtime.host
        link = host.link("bob")
        await host._heard(link, ApprovalRequested(id="a1", gist="may I?", body=leaked))
        [first] = await of_type(session, "approval.requested")
        await session.tombstone(first.data["body"])

        await host._heard(link, ApprovalRequested(id="a2", gist="may I, again?", body=leaked))
        asked = await of_type(session, "approval.requested")
        refused = await of_type(session, "op.refused")
        state = (await session.status("bob"))["state"]

    assert answers == [("a2", "deny")] and [event.data["id"] for event in asked] == ["a1"]
    assert (refused[-1].data["op"], refused[-1].data["code"], state) == ("agent.report", "invalid", "idle")


async def test_an_item_a_person_redacted_and_said_again_is_recorded_redacted_and_its_harness_lives_on(tmp_path):
    """Redacted content does not come back, so the item is recorded by the hash its body had, which reads as redacted
    once its bytes are gone too, and nothing stands in for it, with its harness at work still."""
    leaked = "the key is leaked-key"

    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        host = session._runtime.host
        link = host.link("bob")
        await host._heard(link, Item(kind="message", gist="said", body=leaked))
        [first] = await of_type(session, "item.recorded")
        redacted = first.data["body"]
        await session.tombstone(redacted)
        await until(lambda: erased(session), session)

        await host._heard(link, Item(kind="message", gist="said again", body=leaked))
        said = [event.data["body"] for event in await of_type(session, "item.recorded")]
        state = (await session.status("bob"))["state"]
        with pytest.raises(Refused) as read:
            await session.get_body(redacted)
        gaps = (await session.ending()).gaps

    assert (said, state, gaps, read.value.refusal.code) == ([redacted, redacted], "idle", (), "not_found")


async def test_an_agent_whose_last_words_a_person_redacted_ends_and_its_authority_hears_the_rest(tmp_path):
    """Its end cites them by their hash once their bytes are gone too, and its authority hears what the end keeps."""
    heard: asyncio.Future[AgentOutcome] = asyncio.get_running_loop().create_future()

    class Listening(LocalAuthority):
        async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
            heard.set_result(outcome)

    team = solo()
    async with Session.start(team, authority=Listening(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        host = session._runtime.host
        await host._heard(host.link("bob"), Item(kind="message", gist="said", body="the key is leaked-key"))
        [said] = await of_type(session, "item.recorded")
        await session.tombstone(said.data["body"])
        await until(lambda: erased(session), session)

        await session.retire("bob")
        [stop] = await until(lambda: stops(session, "effect.finished", "effect.failed"), session)
        [end] = await of_type(session, "agent.ended")

    assert (stop.type, end.data["body"]) == ("effect.finished", said.data["body"])
    assert heard.result() == AgentOutcome(status="retired", report="bob retired: retired by human:you")


async def test_an_agent_whose_instructions_a_person_redacted_is_lost_on_resume_saying_why(tmp_path, recording):
    """A harness that reopens its session is handed again what it was told when that began, and nothing stands in for
    words a person redacted, so its agent cannot come back, and ends saying so, where it once ended with a bare
    refusal's name."""
    team = solo_with(recording, instructions="The key is leaked-key.")
    async with Session.start(team, name="told", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        [instructed] = await of_type(session, "agent.instructed")
        await session.tombstone(instructed.data["body"])
        await until(lambda: erased(session), session)
    async with Session.resume("told", root=tmp_path) as session:
        end = await ended(session, "bob")

    assert (end["status"], end["reason"]) == (
        "lost",
        "what bob was told was redacted, and its harness cannot be handed it",
    )
    assert [spec.resume for spec in recording.specs] == [None]


async def test_instructions_equal_to_a_body_a_person_redacted_are_recorded_by_its_hash_and_their_agent_starts(
    tmp_path, recording
):
    """What a harness is told is stored as an item's body is: redacted content does not come back, so it is recorded by
    the hash it had, which reads as redacted, and its harness is told it all the same, as its role says it."""
    role = {"harness": harness(recording), "preamble": "", "instructions": "The key is leaked-key.", "count": 1}
    team = Team.model_validate({"roles": {"bob": role}})
    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        [first] = await of_type(session, "agent.instructed")
        await session.tombstone(first.data["body"])
        await until(lambda: erased(session), session)
        await session.spawn("ada", "bob")
        await in_state(session, "ada", "idle")
        told = [event.data["body"] for event in await of_type(session, "agent.instructed")]

    assert told == [first.data["body"]] * 2
    assert [spec.instructions for spec in recording.specs] == ["The key is leaked-key."] * 2


async def test_a_goal_a_person_redacted_before_its_harness_was_handed_it_is_not_handed_and_says_why(tmp_path):
    """Nothing stands in for a goal's body a person redacted, so the launch that would hand it over fails, saying so."""
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        ref = await session.put_body(b"the key is leaked-key")
        await session.tombstone(ref)
        with pytest.raises(DriverError) as handed:
            session._runtime.host._goal("ada", {"goal": "the short of it", "body": ref}, 1)

    assert str(handed.value) == "ada's goal was redacted, and its harness cannot be handed it"


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
        await session.cancel_agent("@bob")
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

        await session.cancel_agent("@bob")
        await in_state(session, "bob", "ended")

        with pytest.raises(Exception, match="unknown credential"):
            kernel.authenticate(binding.token.reveal())


# What a harness may leave hanging, and what comes of it.


async def test_an_interrupt_fails_a_delivery_that_hangs_and_queues_it_again(tmp_path):
    async with Session.start(solo_with(Stuck), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "hang")
        await in_state(session, "bob", "waking")
        await until(
            lambda: of_type(session, "effect.started"), session, lambda found: found[-1].data["kind"] == "deliver"
        )

        await session.interrupt("@bob")

        await in_state(session, "bob", "idle")
        failed = await until(lambda: of_type(session, "effect.failed"), session)
        assert failed[0].data["error"] == "it was interrupted"
        assert (await session.status("@bob"))["state"] == "idle"
        assert len(await session.attention()) >= 1


async def test_a_delivery_that_hangs_is_cut_off_and_queued_again(tmp_path):
    clock = ManualClock(1000.0)

    async with Session.start(solo_with(Stuck), root=tmp_path, clock=clock) as session:
        await until(lambda: of_type(session, "effect.finished"), session, launch_of("bob"))
        await session.send("@bob", "hang")
        await until(
            lambda: of_type(session, "effect.started"), session, lambda found: found[-1].data["kind"] == "deliver"
        )
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1060.0)

        clock.advance(60.0)

        await in_state(session, "bob", "idle")
        assert (await of_type(session, "effect.failed"))[0].data["error"] == "its harness did not take it in time"


async def test_an_interrupt_a_harness_never_takes_is_cut_off_and_leaves_the_turn_open(tmp_path):
    class Deaf(ScriptedDriver):
        async def interrupt(self) -> None:
            await asyncio.Event().wait()
            raise AssertionError

    clock = ManualClock(1000.0)

    async with Session.start(solo_with(lambda: Deaf([[Hang()]])), root=tmp_path, clock=clock) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
        clock.advance(1.0)  # So that its minute is its own, and no sleeper left from the handover can stand in for it.
        await session.interrupt("@bob")
        await until(
            lambda: of_type(session, "effect.started"), session, lambda found: found[-1].data["kind"] == "interrupt"
        )
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1061.0)

        clock.advance(60.0)

        failed = await until(lambda: of_type(session, "effect.failed"), session)
        assert failed[0].data["error"] == "its harness did not take it in time"
        assert (await session.status("@bob"))["state"] == "running"
        await session.cancel_agent("@bob")


async def test_an_answer_a_harness_never_takes_is_cut_off_and_stays_unanswered(tmp_path):
    class Deaf(ScriptedDriver):
        async def answer(self, approval: str, verdict: Verdict) -> None:
            await asyncio.Event().wait()

    clock = ManualClock(1000.0)

    async with Session.start(solo_with(lambda: Deaf([[Ask("run it?")]])), root=tmp_path, clock=clock) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
        asked = (await until(session.approvals, session))[0]
        clock.advance(1.0)  # So that its minute is its own, and no sleeper left from the handover can stand in for it.
        await session.resolve(asked["id"], "allow", expected_version=asked["version"])
        await until(
            lambda: of_type(session, "effect.started"), session, lambda found: found[-1].data["kind"] == "answer"
        )
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1061.0)

        clock.advance(60.0)

        failed = await until(lambda: of_type(session, "effect.failed"), session)
        assert failed[0].data["error"] == "its harness did not take it in time"


async def test_a_harness_that_takes_a_delivery_and_begins_no_turn_is_cut_off(tmp_path):
    class TakesIt(ScriptedDriver):
        async def deliver(self, delivery: Delivery) -> None:
            pass

    clock = ManualClock(1000.0)

    async with Session.start(solo_with(TakesIt), root=tmp_path, clock=clock) as session:
        await until(lambda: of_type(session, "effect.finished"), session, launch_of("bob"))
        await session.send("@bob", "hello")
        await until(
            lambda: of_type(session, "effect.started"), session, lambda found: found[-1].data["kind"] == "deliver"
        )
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1060.0)

        clock.advance(60.0)

        await in_state(session, "bob", "idle")


async def test_a_wake_finishes_when_its_turn_begins(tmp_path):
    async with Session.start(solo([Say("heard")]), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "hello")
        await until(lambda: of_type(session, "turn.ended"), session)

        events = await journal(session)

    types = [event.type if event.type != "effect.finished" else event.data["kind"] for event in events]
    assert types.index("turn.started") < types.index("deliver")


async def test_a_harness_that_says_ready_and_never_begins_its_goal_is_lost(tmp_path):
    class Dawdling(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await report(Ready(native="n"))

    clock = ManualClock(1000.0)
    team = Team.model_validate(
        {"roles": {"bob": {"harness": scripted()}, "ada": {"harness": harness(Dawdling), "count": 0}}}
    )

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        await in_state(session, "bob", "idle")
        await session.spawn("ada", "ada", "the important thing")
        launched = await until(lambda: of_type(session, "effect.finished"), session, launch_of("ada"))
        assert launched and "starting_agent" in (await session.status())["blockers"]
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1060.0)

        clock.advance(60.0)

        row = await ended(session, "ada")

    assert (row["status"], row["reason"]) == ("lost", "it said it was ready and never began its goal")


async def test_a_harness_that_exits_before_it_is_ready_fails_its_spawn_with_its_reason(tmp_path):
    class Gone(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await report(Exited(reason="no licence"))

    async with Session.start(solo_with(Gone), root=tmp_path) as session:
        row = await ended(session, "bob")

    assert (row["status"], row["reason"]) == ("failed", "its spawn failed: no licence")


# Reports the journal refuses.


class Saying(ScriptedDriver):
    """A harness that says its piece as soon as it is up."""

    said: tuple[Report, ...]

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        await super().start(spec, report)
        for said in self.said:
            await report(said)


def saying(*reports: Report) -> type[Saying]:
    return type("Said", (Saying,), {"said": reports})


async def test_a_ready_the_journal_refuses_fails_the_spawn_and_says_why(tmp_path):
    class TooMuch(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await report(Ready(native="n", tools_visible=("x" * 40_000,)))

    async with Session.start(solo_with(TooMuch), root=tmp_path) as session:
        row = await asyncio.wait_for(ended(session, "bob"), SECONDS)

    assert row["status"] == "failed"
    assert "ready report was refused: invalid" in row["reason"]


async def test_an_exit_with_a_reason_of_any_length_still_ends_the_agent(tmp_path):
    async with Session.start(solo_with(saying(Exited(reason="x" * 20_000))), root=tmp_path) as session:
        row = await ended(session, "bob")

    assert row["status"] == "lost"


async def test_a_report_the_journal_refuses_ends_the_harness_and_leaves_a_gap(tmp_path):
    item = Item(kind="tool", gist="ran it", outcome="x" * 20_000)

    async with Session.start(solo_with(saying(item)), root=tmp_path) as session:
        row = await ended(session, "bob")
        native = await of_type(session, "native.recorded")
        ending = await session.ending()

    assert row["status"] == "lost"
    assert "item report was refused: invalid" in row["reason"]
    assert native[0].data["kind"] == "item"
    assert {"agent": "bob", "what": "unknown_update", "plane": "control", "count": 1} in ending.gaps


async def test_a_late_word_from_an_ended_agent_is_no_loss(tmp_path):
    class Late(ScriptedDriver):
        async def stop(self, grace: float) -> None:
            await self._report(Item(kind="message", gist="too late"))
            await super().stop(grace)

    async with Session.start(solo_with(Late), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.cancel_agent("@bob")

        row = await ended(session, "bob")
        await until(
            lambda: of_type(session, "effect.finished"), session, lambda found: found[-1].data["kind"] == "stop"
        )

        assert await of_type(session, "native.recorded") == []

    assert row["status"] == "cancelled"


# Model pinning and assurance.


async def test_a_model_other_than_the_one_pinned_fails_the_spawn(tmp_path):
    class Hosted(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await report(Ready(native="n", effective_model="some-hosted-default"))

    async with Session.start(solo_with(Hosted, model="asked"), root=tmp_path) as session:
        row = await ended(session, "bob")

        assert await of_type(session, "agent.started") == []

    assert row["reason"] == "its spawn failed: it runs some-hosted-default, and asked is pinned"


async def test_a_model_nobody_can_name_stays_unknown_and_refuses_nothing(tmp_path):
    class Unsaid(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await report(Ready(native="n"))

    async with Session.start(solo_with(Unsaid, model="asked"), root=tmp_path) as session:
        await in_state(session, "bob", "idle")

        assert (await of_type(session, "agent.started"))[0].data["effective_model"] is None


async def test_assurance_is_recorded_once_on_a_harness_coming_up(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")

        assert (await of_type(session, "agent.started"))[0].data["assurance"] == "cooperative"


# Credentials.

SECRET = "s3cret-" + "k" * 40


class Keyed(LocalAuthority):
    async def admit(self, spawn: SpawnRequest) -> Admission:
        admission = await super().admit(spawn)
        return admission.model_copy(update={"access": {"KEY": Secret(SECRET)}})


async def test_every_driver_s_reports_are_masked_on_the_way_to_the_journal(tmp_path):
    team = solo_with(saying(Item(kind="message", gist=f"my key is {SECRET}", body=f"{SECRET}\n")), model="m")

    async with Session.start(team, authority=Keyed(team), root=tmp_path) as session:
        items = await until(lambda: of_type(session, "item.recorded"), session)
        body = await session.blob(f"{items[0].stream}@{items[0].version}")

    assert items[0].gist == "my key is ***"
    assert body["text"] == "***\n"


async def test_a_secret_in_an_approval_s_ask_is_masked_plain_and_encoded(tmp_path):
    """Before the ask is cut, too, so a secret the bound falls inside leaves no part of itself behind."""
    secret = 's3cret/value+with="specials"'
    encoded = base64.b64encode(secret.encode()).decode(), base64.urlsafe_b64encode(secret.encode()).decode().rstrip("=")
    forms = (secret, quote(secret, safe=""), json.dumps(secret)[1:-1], *encoded)
    straddling = "x" * (ASK_LIMIT - 10 - len(" | ".join(forms))) + secret
    said = ApprovalRequested(id="a1", gist=f"run with {secret}"[:280], body=f"{' | '.join(forms)}{straddling} tail")

    class Telling(LocalAuthority):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            admission = await super().admit(spawn)
            return admission.model_copy(update={"access": {"KEY": Secret(secret)}})

    team = solo_with(saying(said), model="m")
    async with Session.start(team, authority=Telling(team), root=tmp_path) as session:
        [asked] = await until(lambda: of_type(session, "approval.requested"), session)
        kept = (await session.get_body(asked.data["body"])).decode()

    assert asked.gist == "run with ***"
    assert kept.startswith("*** | *** | *** | *** | ***x") and kept.endswith("x*** tail")
    assert not any(form[:8] in kept for form in forms) and asked.data["cut"] == 0


async def test_a_lone_surrogate_in_an_item_s_body_is_kept_as_its_escape_as_in_an_ask(tmp_path):
    """A harness's JSON can carry one and UTF-8 cannot, so a body keeps it as its escape, `\\udcc3`, and not as `?`."""
    halved = "caf\udcc3\udca9 tail"
    said = Item(kind="message", gist="said", body=halved), ApprovalRequested(id="a1", gist="may I?", body=halved)

    async with Session.start(solo_with(saying(*said)), root=tmp_path) as session:
        [asked] = await until(lambda: of_type(session, "approval.requested"), session)
        [item] = await of_type(session, "item.recorded")
        kept = await session.get_body(item.data["body"])

    assert (kept, item.data["body"]) == (b"caf\\udcc3\\udca9 tail", asked.data["body"])


async def test_live_text_is_masked_too(tmp_path):
    team = solo_with(
        saying(Delta(text=f"the key is {SECRET}"), Item(kind="tool", phase="started", gist="ran")), model="m"
    )

    async with Session.start(team, authority=Keyed(team), root=tmp_path) as session:
        frame = await asyncio.wait_for(anext(session.deltas("@bob")), SECONDS)

    assert frame.text == "the key is ***"


async def test_a_secret_split_across_two_deltas_is_masked(tmp_path):
    split = len(SECRET) // 2
    tool = Item(kind="tool", gist="ran")
    said = (Delta(text=f"the key is {SECRET[:split]}"), Delta(text=f"{SECRET[split:]} and more"), tool)
    team = solo_with(saying(*said), model="m")

    async with Session.start(team, authority=Keyed(team), root=tmp_path) as session:
        frames = session.deltas("@bob")
        heard = ""
        while "more" not in heard:
            heard += (await asyncio.wait_for(anext(frames), SECONDS)).text

    assert heard == "the key is *** and more"


async def test_live_text_does_not_wait_past_the_next_report(tmp_path):
    """Text an item has replaced is no longer live, so the next report here is a tool's."""
    team = solo_with(saying(Delta(text="short"), Item(kind="tool", phase="started", gist="ran")), model="m")

    async with Session.start(team, authority=Keyed(team), root=tmp_path) as session:
        frame = await asyncio.wait_for(anext(session.deltas("@bob")), SECONDS)

    assert frame.text == "short"


async def test_live_text_cut_for_a_secret_keeps_its_characters_whole(tmp_path):
    text = "é" * 2000
    team = solo_with(
        saying(Delta(text=text), Delta(text=text), Item(kind="tool", phase="started", gist="ran")), model="m"
    )

    async with Session.start(team, authority=Keyed(team), root=tmp_path) as session:
        frames = session.deltas("@bob")
        heard = ""
        while len(heard) < 2 * len(text):
            heard += (await asyncio.wait_for(anext(frames), SECONDS)).text

    assert heard == text + text


async def test_a_stop_that_fails_is_masked_in_the_journal_and_the_log(tmp_path, caplog):
    class BadStop(ScriptedDriver):
        async def stop(self, grace: float) -> None:
            raise DriverError(f"stop failed with {SECRET}")

    team = solo_with(BadStop, model="m")

    async with Session.start(team, authority=Keyed(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.cancel_agent("@bob")
        failed = await until(lambda: of_type(session, "effect.failed"), session)

    assert failed[0].data["error"] == "stop failed with ***"
    assert SECRET not in caplog.text


async def test_a_driver_that_breaks_leaves_no_credential_in_the_log(tmp_path, caplog):
    class Breaks(ScriptedDriver):
        async def deliver(self, delivery: Delivery) -> None:
            raise RuntimeError(f"boom {SECRET}")

    team = solo_with(Breaks, model="m")

    async with Session.start(team, authority=Keyed(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "hello")
        failed = await until(lambda: of_type(session, "effect.failed"), session)

    assert failed[0].data["error"] == "RuntimeError: boom ***"
    assert SECRET not in caplog.text


# Shutdown.


async def test_a_wire_program_s_own_harness_goes_with_the_agent(tmp_path):
    program = tmp_path / "inner.py"
    program.write_text(
        "from platoon_harness.drivers.exec import ExecDriver\n"
        "from platoon_harness.drivers.wire import serve\n"
        "serve(ExecDriver(['sleep', '{goal}']))\n"
    )
    harnessed = {"command": [sys.executable, str(program)], "mode": "wire"}
    team = Team.model_validate({"roles": {"bob": {"harness": harnessed, "count": 0}, "z": {"harness": scripted()}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "z", "idle")
        await session.spawn("ada", "bob", "1000")
        await in_state(session, "ada", "running")
        folder = session.folder / "agents" / "ada"
        wire, inner = Record.read(folder), Record.read(folder / "wire")
        os.killpg(wire.pid, signal.SIGKILL)
        await in_state(session, "ada", "ended")
        await until(
            lambda: of_type(session, "effect.finished"), session, lambda found: found[-1].data["kind"] == "stop"
        )

        assert inner.state() == "gone"
        assert not (folder / "wire" / RECORD).exists()


async def test_leaving_while_a_stop_runs_still_stops_the_harness(tmp_path):
    stopping, stopped = asyncio.Event(), []

    class SlowStop(ScriptedDriver):
        async def stop(self, grace: float) -> None:
            stopped.append("asked")
            stopping.set()
            if len(stopped) == 1:
                await asyncio.Event().wait()
            stopped.append("done")

    session = await Session.start(solo_with(SlowStop), root=tmp_path)
    await in_state(session, "bob", "idle")
    await session.cancel_agent("@bob")
    await asyncio.wait_for(stopping.wait(), SECONDS)

    await asyncio.wait_for(session.leave(0.01), SECONDS)

    assert stopped == ["asked", "asked", "done"]


async def test_a_journal_that_will_not_commit_holds_up_no_shutdown(tmp_path, monkeypatch):
    session = await Session.start(solo([Hang()]), root=tmp_path)
    await session.send("@bob", "go")
    await in_state(session, "bob", "running")
    runtime = session._runtime
    assert runtime is not None

    async def failing(self: Kernel, principal: Any, op: str, args: Any, **options: Any) -> Outcome:
        return Outcome(op=op, args_hash="", refusal=Refusal(code="unavailable", detail="the disk is full"))

    monkeypatch.setattr(Kernel, "submit", failing)
    await asyncio.wait_for(session.leave(0.01), SECONDS)

    assert runtime.kernel.closed
    assert runtime.host._links == {}


async def test_a_driver_that_breaks_in_stop_leaves_nothing_half_closed(tmp_path):
    class BadStop(ScriptedDriver):
        async def stop(self, grace: float) -> None:
            raise RuntimeError("a bug in stop")

    team = Team.model_validate({"roles": {"bad": {"harness": harness(BadStop)}, "good": {"harness": scripted()}}})
    session = await Session.start(team, root=tmp_path)
    await in_state(session, "bad", "idle")
    await in_state(session, "good", "idle")
    runtime, folder = session._runtime, session.folder
    assert runtime is not None

    await session.leave()

    assert runtime.kernel.closed
    assert not is_held(folder)
    assert not (folder / "runtime.json").exists()


# Rest: an agent's process is not its identity.


class Starts:
    """Scripted harnesses that share one script, so a harness brought back goes on where the last left off, and the
    spec each instance was started with."""

    def __init__(self, *turns: Any) -> None:
        self.turns = iter(turns)
        self.specs: list[AgentSpec] = []

    def __call__(self) -> ScriptedDriver:
        starts = self

        class Recorded(ScriptedDriver):
            async def start(self, spec: AgentSpec, report: Reporter) -> None:
                starts.specs.append(spec)
                await super().start(spec, report)

        return Recorded(self.turns)


def rested(events: list[Any]) -> list[Any]:
    return [event for event in events if event.data["kind"] == "rest"]


async def test_an_idle_agent_s_process_ends_after_ten_minutes_and_its_next_message_resumes_it_natively(tmp_path):
    """No setting: ten minutes on the session's clock from its last turn's end. The agent stays as it stood, and its
    harness is brought back on its native session by the handover that needs it, which a resume offers nothing."""
    clock, starts = ManualClock(1000.0), Starts([Say("first")], [Say("second")])
    async with Session.start(solo_with(starts), root=tmp_path, clock=clock) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "one")
        await until(lambda: of_type(session, "turn.ended"), session)
        await asyncio.wait_for(clock.slept_until(1600.0), SECONDS)
        clock.advance(600)
        await until(lambda: of_type(session, "effect.finished"), session, rested)
        link = session._runtime.host.link("bob")
        await session.send("@bob", "two")
        await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)
        resumed = await of_type(session, "agent.resumed")
        instructed = await of_type(session, "agent.instructed")
        launches = [event for event in await of_type(session, "context.offered") if event.data["how"] == "launch"]
        said = [event.gist for event in await of_type(session, "item.recorded") if event.data["kind"] == "message"]

    assert link is None and len(resumed) == 1
    assert [spec.resume for spec in starts.specs] == [None, "scripted-bob"]
    assert len(instructed) == 2 and instructed[0].data["body"] == instructed[1].data["body"]
    assert len(launches) == 1 and said == ["first", "second"]


async def test_a_harness_that_exits_on_its_own_in_a_turn_is_resumed_once_and_told_its_turn_was_cut_off(tmp_path):
    starts = Starts([Exit("killed by signal 9")], [Say("checked")], [Say("still here")])
    async with Session.start(solo_with(starts), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        await session.send("@bob", "again")
        await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)
        gaps = await of_type(session, "gap.recorded")
        lost, began = await of_type(session, "turn.lost"), await of_type(session, "turn.started")
        told = [event.gist for event in await of_type(session, "message.sent") if event.stream == "inbox/bob"]
        rests = rested(await of_type(session, "effect.requested"))
        ending = await session.ending()

    assert [spec.resume for spec in starts.specs] == [None, "scripted-bob"]
    assert [(gap.data["what"], gap.data["since"]) for gap in gaps] == [("crash_window", began[0].seq)]
    assert len(lost) == 1 and [rest.data["data"]["exited"] for rest in rests] == ["killed by signal 9"]
    assert told[1].startswith("Your last turn was cut off by a crash.")
    assert (ending.agents[0]["state"], ending.agents[0]["status"]) == ("idle", None)


async def test_a_harness_that_cannot_reopen_its_session_is_lost_at_its_second_exit(tmp_path):
    """A harness killed before it wrote its session down exits again when its handover brings it back. That is its
    second exit on its own before a turn of its ended, which loses its agent there and says why, and no handover is
    tried again."""
    starts: list[str | None] = []

    class Forgetful(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            starts.append(spec.resume)
            if spec.resume is not None:
                await report(Exited(reason="No conversation found"))
                return
            await super().start(spec, report)

    async with Session.start(solo_with(lambda: Forgetful([[Exit("killed by signal 9")]])), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        ended = await until(lambda: of_type(session, "agent.ended"), session)
        failed = [event for event in await of_type(session, "effect.failed") if event.data["kind"] == "deliver"]

    assert starts == [None, "scripted-bob"]
    assert (ended[0].data["status"], ended[0].data["reason"]) == (
        "lost",
        "its harness exited again before a turn of its ended: No conversation found",
    )
    assert len(failed) <= 1


async def test_an_exit_before_a_retold_turn_begins_tells_it_nothing_twice(tmp_path):
    """A turn cut off is told once. A harness brought back by a resume that exits on its own when handed the notice,
    before the turn it would wake begins, cut nothing of its own, so it is told nothing new, and the notice waiting is
    what it is handed when it comes back again."""
    starts: list[str | None] = []
    turns = iter([[Say("working"), Hang()], [Say("checked")]])

    class Dying(ScriptedDriver):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            starts.append(spec.resume)
            self.heard = report
            await super().start(spec, report)

        async def deliver(self, delivery: Delivery) -> None:
            if len(starts) == 2:
                await self.heard(Exited(reason="exited with code 1"))
                raise DriverError("it exited")
            await super().deliver(delivery)

    async with Session.start(solo_with(lambda: Dying(turns)), name="s", root=tmp_path) as session:
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
    async with Session.resume("s", root=tmp_path) as session:
        await until(lambda: of_type(session, "item.recorded"), session, lambda found: found[-1].gist == "checked")
        told = [event.gist for event in await of_type(session, "message.sent") if event.stream == "inbox/bob"]

    assert starts == [None, "scripted-bob", "scripted-bob"]
    assert [gist for gist in told if gist.startswith("Your last turn was cut off")] == [
        next(gist for gist in told if gist.startswith("Your last turn was cut off by the owner stopping the session."))
    ]


async def test_a_resting_agent_comes_back_at_its_handover_and_not_at_a_runtime_start(tmp_path):
    """A resting harness has no process to bring back, so a resume of its session starts nothing for it."""
    clock, starts = ManualClock(1000.0), Starts([Say("first")], [Say("second")])
    async with Session.start(solo_with(starts), name="s", root=tmp_path, clock=clock) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "one")
        await until(lambda: of_type(session, "turn.ended"), session)
        await asyncio.wait_for(clock.slept_until(1600.0), SECONDS)
        clock.advance(600)
        await until(lambda: of_type(session, "effect.finished"), session, rested)

    async with Session.resume("s", root=tmp_path, clock=clock) as session:
        await until(lambda: of_type(session, "runtime.started"), session, lambda found: len(found) == 2)
        untouched = len(starts.specs)
        await session.send("@bob", "two")
        await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)

    assert untouched == 1 and [spec.resume for spec in starts.specs] == [None, "scripted-bob"]


# What an ended agent's folder keeps.


KEPT_CREDENTIAL = "kept-credential-" + "c" * 32


class Keeping(ScriptedDriver):
    """A harness that keeps, in its folder, scratch in its `TMPDIR`, a login and a folder of logins where its driver
    says, and a transcript of its own beside them, as pi does in its agent directory, and that cannot come back without
    its login. Each start is said in `starts`, by the native id it resumed, and every instance of a class `keeping`
    makes goes on through one script."""

    CREDENTIALS = (Path("own/auth.json"), Path("own/logins"))
    starts: list[str | None]
    script: Any

    def __init__(self) -> None:
        super().__init__(self.script)

    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"credentials": self.CREDENTIALS})

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        own = spec.folder / "own"
        self.starts.append(spec.resume)
        if spec.resume is not None and not (own / "auth.json").exists():
            raise DriverError("its login is gone, so it cannot come back")
        (tmpdir(spec.folder) / "cache").mkdir(parents=True, exist_ok=True)
        (tmpdir(spec.folder) / "cache" / "compiled").write_text("scratch")
        (own / "logins").mkdir(parents=True, exist_ok=True)
        (own / "sessions").mkdir(exist_ok=True)
        (own / "auth.json").write_text(KEPT_CREDENTIAL)
        (own / "logins" / "server.json").write_text(KEPT_CREDENTIAL)
        (own / "sessions" / f"{spec.agent}.jsonl").write_text("what it said")
        await super().start(spec, report)


def keeping(*turns: Any) -> type[Keeping]:
    return type("Kept", (Keeping,), {"starts": [], "script": iter(turns)})


def held(folder: Path) -> list[str]:
    """What of an agent's folder is scratch or a credential."""
    named = (tmpdir(Path()), *Keeping.CREDENTIALS)
    return sorted(str(path) for path in named if (folder / path).exists())


@pytest.mark.parametrize("ending", ["finish", "retire", "cancel"])
async def test_an_ended_agent_s_tmp_and_credentials_go_and_its_record_stays(tmp_path, ending):
    """Its harness's `TMPDIR` and what its driver names as credentials go with its stop, whichever way it ended, and
    its transcript and its harness's own stay, beside the journal."""
    finishing = [[Call("agent_finish", {"gist": "done"})]] if ending == "finish" else []
    async with Session.start(solo_with(keeping(*finishing)), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        folder = agent_folder(session.folder, "bob")
        before = held(folder)
        if ending == "finish":
            await session.send("@bob", "go")
        elif ending == "retire":
            await session.retire("@bob")
        else:
            await session.cancel_agent("@bob")
        await until(lambda: stops(session, "effect.finished"), session)
        status = (await ended(session, "bob"))["status"]

    assert before == ["own/auth.json", "own/logins", "tmp"]
    assert held(folder) == []
    assert status == {"finish": "finished", "retire": "retired", "cancel": "cancelled"}[ending]
    assert (folder / "own" / "sessions" / "bob.jsonl").read_text() == "what it said"


async def test_an_agent_put_to_rest_keeps_what_it_needs_to_resume_and_resumes(tmp_path):
    """A rest ends its process and nothing of its folder, so its harness comes back on its login, and so does a stop
    of its session, which ends no agent."""
    clock, kept = ManualClock(1000.0), keeping([Say("first")], [Say("second")], [Say("third")])
    async with Session.start(solo_with(kept), name="s", root=tmp_path, clock=clock) as session:
        await in_state(session, "bob", "idle")
        folder = agent_folder(session.folder, "bob")
        await session.send("@bob", "one")
        await until(lambda: of_type(session, "turn.ended"), session)
        await asyncio.wait_for(clock.slept_until(1600.0), SECONDS)
        clock.advance(600)
        await until(lambda: of_type(session, "effect.finished"), session, rested)
        rested_holds = held(folder)
        await session.send("@bob", "two")
        await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)
    stopped_holds = held(folder)
    async with Session.resume("s", root=tmp_path, clock=clock) as session:
        await session.send("@bob", "three")
        said = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 3)

    assert rested_holds == stopped_holds == ["own/auth.json", "own/logins", "tmp"]
    assert kept.starts == [None, "scripted-bob", "scripted-bob"]
    assert [event.data["reason"] for event in said] == ["stopped"] * 3


async def test_a_session_copied_after_its_agents_ended_holds_no_credential_file(tmp_path):
    """Nor anything that holds a credential its harnesses kept, and the copy is the record still."""
    team = Team.model_validate({"roles": {name: {"harness": harness(keeping())} for name in ("alice", "bob")}})
    async with Session.start(team, name="s", root=tmp_path / "root") as session:
        await in_state(session, "alice", "idle")
        await in_state(session, "bob", "idle")
        await session.cancel_agent("@alice")
        await session.retire("@bob")
        await until(lambda: stops(session, "effect.finished"), session, lambda found: len(found) == 2)
    copy = tmp_path / "copy" / "sessions" / "s"
    shutil.copytree(session.folder, copy)

    async with Session.attach("s", root=tmp_path / "copy") as history:
        ends = await of_type(history, "agent.ended")
    files = [path for path in copy.rglob("*") if path.is_file()]
    assert [held(agent_folder(copy, name)) for name in ("alice", "bob")] == [[], []]
    assert [path for path in files if KEPT_CREDENTIAL.encode() in path.read_bytes()] == []
    assert sorted(event.agent for event in ends) == ["alice", "bob"]


async def test_what_an_ended_agent_s_stop_could_not_remove_is_said_in_the_log(tmp_path, caplog):
    """And its credentials go all the same."""
    if os.geteuid() == 0:
        pytest.skip("root removes what a mode forbids")
    async with Session.start(solo_with(keeping()), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        folder = agent_folder(session.folder, "bob")
        locked = tmpdir(folder) / "cache"
        locked.chmod(0o500)
        try:
            await session.retire("@bob")
            await until(lambda: stops(session, "effect.finished"), session)
        finally:
            locked.chmod(0o700)

    assert held(folder) == ["tmp"]
    assert "bob's stop: tmp could not be removed: Permission denied" in caplog.text


async def test_a_driver_that_cannot_say_where_its_credentials_are_leaves_them_and_says_so(tmp_path, caplog):
    """Its harness's `TMPDIR` goes all the same."""
    async with Session.start(solo_with(keeping()), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        folder = agent_folder(session.folder, "bob")

        async def unsaid(role: str) -> DriverInfo:
            raise DriverError("it would not describe itself")

        session._runtime.host.describe = unsaid
        await session.retire("@bob")
        await until(lambda: stops(session, "effect.finished"), session)

    assert held(folder) == ["own/auth.json", "own/logins"]
    assert "bob's driver did not say where its harness keeps credentials, so they stay" in caplog.text


async def test_an_authority_hears_of_an_end_whose_driver_broke_saying_where_its_credentials_are(tmp_path):
    """A driver that raises what no driver should fails the stop, which says why, and its harness's `TMPDIR` goes and
    the authority hears all the same."""
    told: list[AgentOutcome] = []

    class Listening(LocalAuthority):
        async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
            told.append(outcome)

    team = solo_with(keeping())
    async with Session.start(team, authority=Listening(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        folder = agent_folder(session.folder, "bob")

        async def broken(role: str) -> DriverInfo:
            raise RuntimeError("a bug in describe")

        session._runtime.host.describe = broken
        await session.retire("@bob")
        [failed] = await until(lambda: stops(session, "effect.failed"), session)

    assert failed.data["error"] == "RuntimeError: a bug in describe"
    assert held(folder) == ["own/auth.json", "own/logins"]
    assert [outcome.status for outcome in told] == ["retired"]


async def test_an_authority_hears_of_an_end_whose_stop_a_shutdown_cut_as_its_driver_described_itself(tmp_path):
    """A wire program describes itself by running, which a shutdown can cut short, and its harness's `TMPDIR` goes and
    the authority hears all the same."""
    told: list[AgentOutcome] = []
    describing = asyncio.Event()

    class Listening(LocalAuthority):
        async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
            told.append(outcome)

    team = solo_with(keeping())
    async with Session.start(team, authority=Listening(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        folder = agent_folder(session.folder, "bob")

        async def answering(role: str) -> DriverInfo:
            describing.set()
            await asyncio.Event().wait()
            raise AssertionError

        session._runtime.host.describe = answering
        await session.retire("@bob")
        await asyncio.wait_for(describing.wait(), SECONDS)

    assert held(folder) == ["own/auth.json", "own/logins"]
    assert [outcome.status for outcome in told] == ["retired"]
