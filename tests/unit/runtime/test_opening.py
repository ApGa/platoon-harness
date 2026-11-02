"""From a team to a live session: checked before any cost, and safe to repeat."""

import json
from pathlib import Path

import pytest

from platoon_harness import Session, Team
from platoon_harness.config import Manifest
from platoon_harness.drivers import Capabilities, DriverError, DriverInfo
from platoon_harness.kernel import Event, Kernel
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime import LocalAuthority, opening
from platoon_harness.runtime.opening import open_session, prepare
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


def test_capabilities_come_from_each_role_s_driver(tmp_path):
    blind, measuring = Capabilities(persistent=True), MEASURING
    roles = {
        "reads": {"harness": scripted(capabilities=measuring), "budget": {"tokens": 10}},
        "guesses": {"harness": scripted(capabilities=blind), "budget": {"tokens": 10}},
    }

    with pytest.raises(ConfigError) as error:
        prepare(team_of(roles=roles), root=tmp_path)

    assert [problem.where for problem in error.value.problems] == ["roles.guesses.budget.tokens"]


def test_a_driver_that_cannot_describe_itself_is_a_problem_at_its_role(tmp_path):
    class Mute(ScriptedDriver):
        def describe(self) -> DriverInfo:
            raise DriverError("it will not say")

    with pytest.raises(ConfigError) as error:
        prepare(team_of(roles={"lead": {"harness": harness(Mute)}}), root=tmp_path)

    assert str(error.value) == "roles.lead.harness: it will not say"


def test_a_warning_stops_nothing(tmp_path, caplog):
    roles = {"lead": {"harness": scripted()}, "alone": {"harness": scripted(), "count": 0}}

    assert prepare(team_of(roles=roles), root=tmp_path).exists()
    assert "never starts" in caplog.text


def test_a_name_for_the_human_must_be_one(tmp_path):
    with pytest.raises(ConfigError, match="cannot name a principal"):
        prepare(team_of(), root=tmp_path, human="not/a/name")


def test_the_manifest_says_how_the_session_was_started(tmp_path):
    folder = prepare(team_of(), name="s", root=tmp_path, human="ada", approvals="deny", cwd=tmp_path)

    manifest = Manifest.model_validate_json((folder / MANIFEST).read_text())

    assert (manifest.human, manifest.approvals, manifest.cwd) == ("human:ada", "deny", str(tmp_path))
    assert Team.loads(manifest.team).topology.hash == manifest.topology_hash
    assert folder.stat().st_mode & 0o077 == 0


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
        await open_session(kernel, resolved, manifest, LocalAuthority(resolved), text)
        return kernel, resolved, manifest, text

    kernels: list[Kernel] = []
    yield open_team
    for kernel in kernels:
        kernel.close()


TEAM = """
[roles.lead]
may_spawn = ["worker"]
approvals = "deny"
budget = { tokens = 500 }

[roles.worker]
tools = ["task.*", "wait"]
delivery = "pull"
inbox_depth = 7
count = 0

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


async def test_a_resource_the_authority_owns_is_no_limit_of_the_session(opened, tmp_path):
    class Managed(LocalAuthority):
        def budget_owner(self, resource: str):
            return "authority" if resource == "tokens" else "session"

    team = team_of(roles={"lead": {"harness": scripted(capabilities=MEASURING), "budget": {"tokens": 5, "turns": 5}}})
    folder = prepare(team, name="managed", root=tmp_path)
    text = (folder / MANIFEST).read_text()
    manifest = Manifest.model_validate_json(text)
    resolved = Team.loads(manifest.team)
    kernel = Kernel.open(folder, extensions=PRIMITIVES)

    await open_session(kernel, resolved, manifest, Managed(resolved), text)

    assert [row["unit"] for row in query(kernel, "budget.status")] == ["turns"]
    kernel.close()


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

    await open_session(kernel, team, manifest, LocalAuthority(team), text)

    assert kernel.head == head


async def test_a_crash_part_way_through_is_finished_by_the_next_opening(tmp_path, monkeypatch):
    folder = prepare(full_team(), name="s", root=tmp_path)
    text = (folder / MANIFEST).read_text()
    manifest = Manifest.model_validate_json(text)
    team = Team.loads(manifest.team)
    authority = LocalAuthority(team)
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
            await open_session(kernel, team, manifest, authority, text)
    kernel.close()

    kernel = Kernel.open(folder, extensions=PRIMITIVES)
    await open_session(kernel, team, manifest, authority, text)
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
