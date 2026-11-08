"""From a team to a live session: checked before any cost, and safe to repeat."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team, told
from platoon_harness.config import Manifest
from platoon_harness.drivers import Capabilities, DriverError, DriverInfo
from platoon_harness.kernel import Event, Kernel, Refused, is_held
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime import opening
from platoon_harness.runtime.opening import PLAN_LOGIN_FIX, check, open_session, prepare
from platoon_harness.runtime.paths import MANIFEST
from platoon_harness.schema import ConfigError
from platoon_harness.testing import Say, ScriptedDriver
from platoon_harness.topology import compile

from ..primitives.support import result_of
from .support import harness, in_state, journal, of_type, scripted, state_of

pytestmark = pytest.mark.timeout(30)

MEASURING = Capabilities(persistent=True, measures={"tokens"})


def team_of(**fields) -> Team:
    fields.setdefault("roles", {"lead": {"harness": scripted()}})
    return Team.model_validate(fields)


def query(kernel: Kernel, op: str, **args):
    return result_of(kernel.query(kernel.runtime, op, args))


def events_of(kernel: Kernel, event_type: str) -> list[Event]:
    return [event for event in kernel.read(kernel.runtime, after=0, limit=4096).events if event.type == event_type]


def test_an_unknown_harness_is_refused_before_any_cost(tmp_path):
    team = team_of(roles={"lead": {"harness": "cluade"}})

    with pytest.raises(ConfigError, match="no driver `cluade`"):
        prepare(team, root=tmp_path)

    assert not (tmp_path / "sessions").exists()


def test_every_problem_is_reported_at_once(tmp_path):
    team = team_of(
        roles={"lead": {"harness": "cluade"}, "other": {"harness": scripted(), "auth": "nobody"}},
    )

    with pytest.raises(ConfigError) as error:
        prepare(team, root=tmp_path)

    assert {problem.where for problem in error.value.problems} == {"roles.lead.harness", "roles.other.auth"}
    assert sum("harness" in problem.where for problem in error.value.problems) == 1


def test_capabilities_come_from_each_role_s_driver():
    blind, measuring = Capabilities(persistent=True), MEASURING
    budget = {"tokens": 10, "estimate": {"tokens": 5}}
    roles = {
        "reads": {"harness": scripted(capabilities=measuring), "budget": budget},
        "guesses": {"harness": scripted(capabilities=blind), "budget": budget},
    }

    found = check(team_of(roles=roles))

    assert [problem.where for problem in found if problem.where.endswith(".tokens")] == ["roles.guesses.budget.tokens"]


def test_a_driver_that_cannot_describe_itself_is_a_problem_at_its_role(tmp_path):
    class Mute(ScriptedDriver):
        def describe(self) -> DriverInfo:
            raise DriverError("it will not say")

    with pytest.raises(ConfigError) as error:
        prepare(team_of(roles={"lead": {"harness": harness(Mute)}}), root=tmp_path)

    assert str(error.value) == "roles.lead.harness: it will not say"


async def test_what_a_role_would_be_told_is_said_of_a_driver_that_cannot_describe_itself_at_its_role():
    class Mute(ScriptedDriver):
        def describe(self) -> DriverInfo:
            raise DriverError("it will not say")

    with pytest.raises(ConfigError) as error:
        await told(team_of(roles={"lead": {"harness": harness(Mute)}}))

    assert str(error.value) == "roles.lead.harness: it will not say"


@pytest.mark.parametrize(
    "bounds",
    [
        {"topology": {"limits": {"max_live": 1}}},
        {"topology": {"limits": {"max_children": 1}}},
        {"budget": {"agents": 1}},
    ],
)
async def test_what_each_role_would_be_told_is_said_whatever_limits_one_agent_of_each(bounds):
    """No limit and no budget is in what an agent is told, and a team that runs within them is shown whole."""
    roles = {"lead": {"harness": scripted(), "may_spawn": ["critic", "worker"]}, "critic": {"harness": scripted()}}
    team = team_of(roles={**roles, "worker": {"harness": scripted()}}, **bounds)

    assert sorted(await told(team)) == ["critic", "lead", "worker"]


async def test_a_role_only_a_role_nothing_starts_may_spawn_is_shown_as_its_child():
    roles = {"lead": {"harness": scripted(), "may_spawn": ["critic"], "count": 0}, "critic": {"harness": scripted()}}

    edges = {"lead": ["children"], "critic": ["parent"]}

    shown = await told(team_of(roles=roles, topology={"edges": edges}))

    assert "You can message: @lead." in shown["critic"] and "When your goal is done" in shown["critic"]
    assert "You can start agents in these roles: critic." in shown["lead"]


def test_a_warning_stops_nothing(tmp_path, caplog):
    roles = {"lead": {"harness": scripted()}, "alone": {"harness": scripted(), "count": 0}}

    assert prepare(team_of(roles=roles), root=tmp_path).exists()
    assert "has no path to anyone" in caplog.text


class OnAPlan(ScriptedDriver):
    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"login": "plan"})


def planned(**role: Any) -> dict[str, Any]:
    return {"harness": harness(OnAPlan), **role}


def test_several_agents_on_a_plan_login_are_refused_naming_the_fix(tmp_path):
    with pytest.raises(ConfigError, match="plan_login=True") as error:
        prepare(team_of(roles={"worker": planned(count=2)}), root=tmp_path)

    assert f"worker would run several agents headless on one plan login: {PLAN_LOGIN_FIX}" in str(error.value)
    assert not (tmp_path / "sessions").exists()


def test_two_roles_on_a_plan_login_count_together(tmp_path):
    with pytest.raises(ConfigError, match="a, b would run several agents"):
        prepare(team_of(roles={"a": planned(), "b": planned()}), root=tmp_path)


def test_a_role_that_can_be_spawned_counts_as_several(tmp_path):
    roles = {"lead": planned(may_spawn=["worker"]), "worker": planned()}

    with pytest.raises(ConfigError, match="plan_login=True"):
        prepare(team_of(roles=roles), root=tmp_path)


def test_a_role_a_written_grant_lets_spawn_counts_as_several_too(tmp_path):
    grant = {"who": "role:lead", "ops": "agent.spawn", "on": "role/lead"}
    team = team_of(roles={"lead": planned()}, topology={"grants": [grant], "limits": {"max_depth": 2}})

    with pytest.raises(ConfigError, match="plan_login=True"):
        prepare(team, root=tmp_path)


def test_one_agent_alone_on_a_plan_login_is_ordinary_use(tmp_path):
    assert prepare(team_of(roles={"lead": planned()}), root=tmp_path).exists()


def test_the_owner_can_say_several_agents_on_a_plan_login_are_their_own_work(tmp_path):
    assert prepare(team_of(roles={"worker": planned(count=2)}), root=tmp_path, plan_login=True).exists()


def test_a_role_with_an_auth_profile_is_on_no_login(tmp_path, monkeypatch):
    monkeypatch.setenv("KEY", "a-key")
    fields = {"auth": {"keyed": {"env": ["KEY"]}}, "roles": {"worker": planned(count=2, auth="keyed")}}

    assert prepare(team_of(**fields), root=tmp_path).exists()


async def test_session_start_says_so_for_its_owner(tmp_path):
    async with Session.start(team_of(roles={"worker": planned(count=2)}), root=tmp_path, plan_login=True) as session:
        await in_state(session, "worker-1", "idle")


async def test_a_spawn_that_would_put_a_second_agent_on_a_plan_login_fails_naming_the_fix(tmp_path):
    async with Session.start(team_of(roles={"lead": planned()}), root=tmp_path) as session:
        await in_state(session, "lead", "idle")
        await session.spawn("extra", "lead")
        await in_state(session, "extra", "ended")
        extra = next(agent for agent in (await session.ending()).agents if agent["agent"] == "extra")

    assert extra["status"] == "failed"
    assert extra["reason"].endswith(f"extra would join lead headless on one plan login: {PLAN_LOGIN_FIX}")


async def test_an_owner_who_said_so_spawns_more_on_a_plan_login(tmp_path):
    async with Session.start(team_of(roles={"lead": planned()}), root=tmp_path, plan_login=True) as session:
        await in_state(session, "lead", "idle")
        await session.spawn("extra", "lead")
        await in_state(session, "extra", "idle")


class SignedIn(ScriptedDriver):
    """A harness whose login is whatever its shell says now, as a user can sign a harness in again between runs."""

    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"login": os.environ.get("PLATOON_HARNESS_TEST_LOGIN")})


@pytest.mark.parametrize("said", [False, True])
async def test_a_resume_that_would_bring_back_several_agents_on_a_plan_login_needs_the_owner_s_word(
    tmp_path, monkeypatch, said
):
    team = team_of(roles={"worker": {"harness": harness(SignedIn), "count": 2}})
    async with Session.start(team, name="s", root=tmp_path, plan_login=said) as session:
        await in_state(session, "worker-2", "idle")
    head = len(await journal(await Session.attach("s", root=tmp_path)))
    monkeypatch.setenv("PLATOON_HARNESS_TEST_LOGIN", "plan")

    if said:
        async with Session.resume("s", root=tmp_path) as session:
            await in_state(session, "worker-2", "idle")
        return
    with pytest.raises(ConfigError, match="worker-1, worker-2 would run headless on one plan login") as error:
        await Session.resume("s", root=tmp_path)

    assert PLAN_LOGIN_FIX in str(error.value)

    assert not is_held(tmp_path / "sessions" / "s")
    assert len(await journal(await Session.attach("s", root=tmp_path))) == head


@pytest.mark.parametrize("principal", ["human:not/a/name", "agent:bob", "you"])
def test_a_principal_is_a_person_or_a_program_by_a_name(tmp_path, principal):
    with pytest.raises(ConfigError, match="neither `human:<name>` nor `program:<name>`"):
        prepare(team_of(), root=tmp_path, principal=principal)


def test_a_session_left_to_its_program_needs_a_program_to_own_it(tmp_path):
    """`until = "program"` waits for a close only the program that owns the session makes, so a person's start is
    refused before any cost, naming the script way, and a program's goes ahead."""
    team = team_of(topology={"until": "program"})

    with pytest.raises(ConfigError) as refused:
        prepare(team, root=tmp_path, principal="human:ada")
    folder = prepare(team, name="s", root=tmp_path, principal="program:reviews")

    assert [str(problem) for problem in refused.value.problems] == [
        "topology.until: `program` leaves the session to the program that owns it, and `human:ada` is a person: start "
        'it from a script, with `Session.start(team, principal="program:<name>")`'
    ]
    assert [path.name for path in (tmp_path / "sessions").iterdir()] == ["s"]
    assert Manifest.model_validate_json((folder / MANIFEST).read_text()).principal == "program:reviews"


def test_the_manifest_says_how_the_session_was_started(tmp_path):
    folder = prepare(team_of(), name="s", root=tmp_path, principal="human:ada", approvals="deny", cwd=tmp_path)

    manifest = Manifest.model_validate_json((folder / MANIFEST).read_text())

    assert (manifest.principal, manifest.approvals, manifest.cwd) == ("human:ada", "deny", str(tmp_path))
    assert Team.loads(manifest.team).topology.hash == manifest.topology_hash
    assert folder.stat().st_mode & 0o077 == 0


def described(team: Team) -> dict[str, Capabilities]:
    """What each role's driver says it can do, as a runtime asks before it opens a session."""
    return {name: opening.make_driver(role, Path.cwd()).describe().capabilities for name, role in team.roles.items()}


@pytest.fixture
async def opened(tmp_path: Path):
    """A session opened by a runtime with no daemons, so nothing happens but what opening did."""

    async def open_team(team: Team, **started) -> tuple[Kernel, Team, Manifest, str]:
        folder = prepare(team, name="s", root=tmp_path, **started)
        text = (folder / MANIFEST).read_text()
        manifest = Manifest.model_validate_json(text)
        resolved = Team.loads(manifest.team)
        kernel = Kernel.open(folder, extensions=PRIMITIVES)
        kernels.append(kernel)
        await open_session(kernel, resolved, manifest, text, described(resolved), None)
        return kernel, resolved, manifest, text

    kernels: list[Kernel] = []
    yield open_team
    for kernel in kernels:
        kernel.close()


TEAM = """
[roles.lead]
may_spawn = ["worker"]
approvals = "deny"
budget = { tokens = 500, estimate = { tokens = 50 } }

[roles.worker]
tools = ["task.*", "wait"]
delivery = "pull"
inbox_depth = 7
count = 0
stays = true

[budget]
turns = 9
wall = "2h"

[topology]
until = "role:lead"
edges = { lead = ["children", "human"], worker = ["parent"] }

[topology.limits]
max_depth = 2
max_hops = 5

[topology.channels.tasks]
kind = "queue"
writers = "role:lead"
readers = "role:worker"
lease = "30m"
lease_max = "2h"
max_attempts = 4
max_inflight = 2

[topology.channels.news]
kind = "topic"
writers = "role:lead"
readers = "role:worker"
delivery = "wake"
history = "full"
coalesce = "90s"

[topology.channels.notes]
kind = "board"
writers = "all"
readers = "all"

[topology.groups.crew]
roles = ["worker"]
"""


def full_team() -> Team:
    lines = TEAM.replace("[roles.lead]\n", f'[roles.lead]\nharness = "{scripted(capabilities=MEASURING)}"\n')
    return Team.loads(lines.replace("[roles.worker]\n", f'[roles.worker]\nharness = "{scripted()}"\n'))


async def test_roles_limits_and_until_reach_the_session(opened):
    kernel, *_ = await opened(full_team())

    assert query(kernel, "session.status")["until"] == "role:lead"
    event = events_of(kernel, "session.opened")[0]
    assert event.data["limits"]["max_depth"] == 2 and event.data["limits"]["max_hops"] == 5
    worker = event.data["roles"]["worker"]
    assert (worker["delivery"], worker["inbox_depth"]) == ("pull", 7)
    assert (worker["stays"], worker["persistent"]) == (True, True)
    assert event.data["roles"]["lead"]["stays"] is None
    assert set(worker["tools"]) == {"task.*", "wait", "ops.list"}


async def test_a_role_keeps_its_own_policy_unless_one_is_stated(opened):
    kernel, *_ = await opened(full_team())
    event = events_of(kernel, "session.opened")[0]

    assert {name: role["approvals"] for name, role in event.data["roles"].items()} == {"lead": "deny", "worker": "ask"}


async def test_a_stated_policy_holds_over_every_role(opened):
    kernel, *_ = await opened(full_team(), approvals="allow")
    event = events_of(kernel, "session.opened")[0]

    assert {role["approvals"] for role in event.data["roles"].values()} == {"allow"}


async def test_every_compiled_grant_goes_through_an_op(opened):
    kernel, team, *_ = await opened(full_team())

    added = [
        event.data for event in kernel.read(kernel.runtime, after=0, limit=4096).events if event.type == "grant.added"
    ]

    assert {(row["who"], row["ops"], row["on"]) for row in added} == {
        (grant.who, grant.ops, grant.on) for grant in compile(team)
    }


async def test_channels_arrive_with_their_durations_in_seconds(opened):
    kernel, *_ = await opened(full_team())

    created = {event.data["stream"]: event.data for event in events_of(kernel, "channel.created")}

    tasks = created["queue/tasks"]
    assert (tasks["lease"], tasks["lease_max"], tasks["max_attempts"], tasks["max_inflight"]) == (1800.0, 7200.0, 4, 2)
    news = created["channel/news"]
    assert (news["coalesce"], news["history"], news["delivery"]) == (90.0, "full", "wake")
    assert created["board/notes"]["kind"] == "board"


async def test_groups_reach_their_topic(opened):
    kernel, *_ = await opened(full_team())

    assert "channel/+crew" in {
        event.data["stream"]
        for event in kernel.read(kernel.runtime, after=0, limit=4096).events
        if event.type == "channel.created"
    }


async def test_budgets_are_set_shared_and_per_role_in_seconds(opened):
    kernel, *_ = await opened(full_team())

    assert {(row["scope"], row["unit"]): row["limit"] for row in query(kernel, "budget.status")} == {
        ("shared", "turns"): 9.0,
        ("shared", "wall"): 7200.0,
        ("role:lead", "tokens"): 500.0,
    }


async def test_a_role_s_estimate_reaches_the_session_with_or_without_a_limit_of_its_own(opened):
    """A role's estimate is what its turns are reserved and charged, so it goes to the session whether or not the role
    has a limit, and a role's limit may hold on the shared estimate."""
    measuring = scripted(capabilities=MEASURING)
    roles = {
        "lead": {"harness": measuring, "budget": {"estimate": {"tokens": 50}}},
        "other": {"harness": measuring, "count": 0, "budget": {"tokens": 500}},
    }
    team = team_of(roles=roles, budget={"tokens": 1000, "estimate": {"tokens": 10}})
    kernel, *_ = await opened(team)

    given = {event.data["scope"]: event.data for event in events_of(kernel, "budget.set")}
    assert (given["role:lead"]["limits"], given["role:lead"]["estimate"]) == ({}, {"tokens": 50})
    assert given["role:other"]["limits"] == {"tokens": 500}


async def test_agents_start_with_no_goal(opened):
    roles = {"lead": {"harness": scripted()}, "worker": {"harness": scripted(), "count": 2}}
    kernel, *_ = await opened(team_of(roles=roles))

    agents = query(kernel, "agent.records")

    assert [(agent["name"], agent["role"], agent["goal"]) for agent in agents] == [
        ("lead", "lead", ""),
        ("worker-1", "worker", ""),
        ("worker-2", "worker", ""),
    ]


async def test_a_second_opening_changes_nothing(opened):
    kernel, team, manifest, text = await opened(full_team())
    head = kernel.head

    await open_session(kernel, team, manifest, text, described(team), None)

    assert kernel.head == head


async def test_a_step_that_ran_under_an_older_sdk_stands_as_it_ran(opened, monkeypatch):
    kernel, team, manifest, text = await opened(full_team())
    grants = compile(team)
    monkeypatch.setattr(opening, "compile", lambda _: (*grants[1:], grants[0]))

    await open_session(kernel, team, manifest, text, described(team), None)

    assert len(events_of(kernel, "grant.added")) == len(grants)


async def test_a_step_refused_for_any_other_reason_is_loud(opened, tmp_path):
    roles = {"lead": {"harness": scripted()}, "worker": {"harness": scripted(), "count": 2}}

    with pytest.raises(Refused) as refused:
        await opened(team_of(roles=roles, budget={"agents": 1}))

    assert refused.value.refusal.code == "over_budget"


async def test_a_crash_part_way_through_is_finished_by_the_next_opening(tmp_path, monkeypatch):
    folder = prepare(full_team(), name="s", root=tmp_path)
    text = (folder / MANIFEST).read_text()
    manifest = Manifest.model_validate_json(text)
    team = Team.loads(manifest.team)
    real = opening._steps

    async def dying(kernel, op, *steps):
        await real(kernel, op, *steps[:1])
        if op == "channel.create":
            raise ConnectionError("the machine went")
        await real(kernel, op, *steps[1:])

    kernel = Kernel.open(folder, extensions=PRIMITIVES)
    with monkeypatch.context() as patched:
        patched.setattr(opening, "_steps", dying)
        with pytest.raises(ConnectionError):
            await open_session(kernel, team, manifest, text, described(team), None)
    kernel.close()

    kernel = Kernel.open(folder, extensions=PRIMITIVES)
    await open_session(kernel, team, manifest, text, described(team), None)
    events = kernel.read(kernel.runtime, after=0, limit=4096).events
    types = [event.type for event in events]
    kernel.close()

    assert types.count("session.opened") == 1
    assert types.count("channel.created") == 4  # Three channels, and the topic of a group.
    assert types.count("agent.spawned") == 1
    assert "op.refused" not in types


async def test_an_agent_with_no_goal_takes_no_turn_until_a_message_wakes_it(tmp_path):
    team = team_of(roles={"bob": {"harness": scripted([Say("awake")])}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")

        assert await of_type(session, "turn.started") == []
        assert await state_of(session, "bob") == "idle"

        await session.send("@bob", "wake up")
        await in_state(session, "bob", "idle", "running")
        ending = await session.settled(timeout="10s")

        assert ending.reason == "settled"
        assert [event.gist for event in await of_type(session, "item.recorded")] == ["awake"]
        assert json.loads((await journal(session, "session"))[0].model_dump_json())["type"] == "session.opened"
