"""A population: workers of one role, each in a worktree of its own, started by the program that owns the session, and
each given one outcome that the program records on board `outcomes`. On real git under `tmp_path`, with scripted
harnesses doing what an agent's own git and tools would."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import ConfigError, Refused, Session, Team
from platoon_harness.patterns import population
from platoon_harness.testing import ScriptedDriver

from ..runtime.gitting import commit, git, repository
from ..runtime.support import harness, of_type
from ..runtime.test_recovery import abandon

pytestmark = pytest.mark.timeout(60)

PROGRAM = "program:swarm"
GOAL = "Make the tests pass."

type Plan = Callable[["Worker"], Awaitable[str]]


class Worker(ScriptedDriver):
    """A worker whose one turn does what its plan says, by its name, through its own git and our tools."""

    def __init__(self, plans: Mapping[str, Plan]) -> None:
        super().__init__([[]])
        self._plans = plans

    @property
    def name(self) -> str:
        return self._spec.agent

    @property
    def cwd(self) -> Path:
        return self._spec.cwd

    async def _walk(self, steps: Any) -> str:
        return await self._plans[self.name](self)

    async def tool(self, tool: str, /, **arguments: Any) -> Any:
        """Call one of our tools and give what it answered, refusal and all."""
        result = await self._call(tool, arguments)
        return json.loads(result["content"][0]["text"])

    async def outcome_of(self, peer: str) -> dict[str, Any]:
        """A peer's entry on `outcomes`, once its program has recorded it."""
        await self.tool("wait", board=[f"outcomes/{peer}"], after=0, hold=30.0)
        return await self.tool("board_get", board="outcomes", name=peer)

    async def nominate(self, *based_on: str) -> None:
        await self.tool("message_send", to="#nominations", gist="the best so far", based_on=list(based_on))


async def contribute(worker: Worker) -> str:
    await asyncio.to_thread(commit, worker.cwd, f"{worker.name}.txt")
    return "stopped"


async def abstain(worker: Worker) -> str:
    await worker._say("nothing worth adding")
    return "stopped"


async def fail(worker: Worker) -> str:
    return "failed: its model went away"


def nominating(peer: str) -> Plan:
    """Nominate the commit a peer contributed, by the ref `repo.commit` gives for the SHA its entry on `outcomes`
    records."""

    async def plan(worker: Worker) -> str:
        made = (await worker.outcome_of(peer))["fields"]["sha"]
        await worker.nominate((await worker.tool("repo_commit", sha=made))["ref"])
        return "stopped"

    return plan


def building_on(peer: str) -> Plan:
    """Build on the commit a peer nominated: check out the SHA its entry on `outcomes` records, on the worker's own
    branch in its own worktree, and commit on it."""

    async def plan(worker: Worker) -> str:
        nominated = (await worker.outcome_of(peer))["fields"]["sha"]
        await asyncio.to_thread(git, "reset", "-q", "--hard", nominated, cwd=worker.cwd)
        await asyncio.to_thread(commit, worker.cwd, f"{worker.name}.txt")
        return "stopped"

    return plan


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


def swarm(plans: Mapping[str, Plan], *, live: int) -> Team:
    """git-swarm over workers in worktrees of their own, each doing its plan."""
    worker = {"harness": harness(lambda: Worker(plans)), "workspace": "worktree", "count": 0}
    return Team.model_validate(
        {"roles": {"worker": worker}, "topology": {"git-swarm": {"role": "worker", "live": live}}}
    )


async def outcomes_posted(session: Session) -> list[Any]:
    return [event for event in await of_type(session, "board.posted") if event.stream.startswith("board/outcomes/")]


async def test_each_worker_gets_one_outcome_and_never_a_second(repo, tmp_path):
    plans = {
        "worker-1": contribute,
        "worker-2": nominating("worker-1"),
        "worker-3": abstain,
        "worker-4": fail,
    }
    async with Session.start(swarm(plans, live=1), name="s", principal=PROGRAM, root=tmp_path, cwd=repo) as session:
        came_to = await population(session, "worker", GOAL, attempts=4)
        posted = await outcomes_posted(session)
        again = await session.submit("board.post", board="outcomes", name="worker-1", gist="contribute: twice")
        committed = await of_type(session, "repo.committed")
        nominated = await of_type(session, "message.sent")

    assert came_to == {"worker-1": "contribute", "worker-2": "nominate", "worker-3": "abstain", "worker-4": "failed"}
    assert [event.stream for event in posted] == [f"board/outcomes/worker-{n}" for n in (1, 2, 3, 4)]
    assert {event.actor for event in posted} == {PROGRAM}
    assert again.refusal is not None and again.refusal.code == "conflict"
    [made] = committed
    [nomination] = [event for event in nominated if event.stream == "channel/nominations"]
    entries = {event.stream.removeprefix("board/outcomes/"): event for event in posted}
    assert made.data["made_in"] == "@worker-1"
    assert entries["worker-1"].gist == f"contribute: {made.gist}"
    assert f"{made.stream}@{made.version}" in entries["worker-1"].based_on
    assert entries["worker-1"].data["fields"]["sha"] == made.data["sha"]
    assert entries["worker-2"].gist == f"nominate: {made.gist}"
    assert entries["worker-2"].data["fields"]["sha"] == made.data["sha"]
    assert {f"{made.stream}@{made.version}", f"{nomination.stream}@{nomination.version}"} <= {
        *entries["worker-2"].based_on
    }
    assert entries["worker-3"].gist == "abstain: nothing worth adding"
    assert entries["worker-4"].gist == (
        "failed: its turn ended failed: its model went away, and it ended retired: retired by program:swarm"
    )
    assert {entry.data["fields"]["outcome"] for entry in entries.values()} == {*came_to.values()}


async def test_a_worker_builds_on_a_peer_s_nominated_commit_by_its_recorded_sha(repo, tmp_path):
    plans = {"worker-1": contribute, "worker-2": nominating("worker-1"), "worker-3": building_on("worker-2")}
    async with Session.start(swarm(plans, live=1), name="s", principal=PROGRAM, root=tmp_path, cwd=repo) as session:
        came_to = await population(session, "worker", GOAL, attempts=3)
        committed = await of_type(session, "repo.committed")
        rewritten = await of_type(session, "repo.rewritten")
        entries = {event.stream: event.data["fields"] for event in await outcomes_posted(session)}

    assert came_to == {"worker-1": "contribute", "worker-2": "nominate", "worker-3": "contribute"}
    nominated, built = (event.data for event in committed)
    assert (nominated["made_in"], built["made_in"]) == ("@worker-1", "@worker-3")
    assert built["parents"] == [nominated["sha"]]
    assert entries["board/outcomes/worker-2"]["sha"] == nominated["sha"]
    assert entries["board/outcomes/worker-3"]["sha"] == built["sha"]
    tree = git("ls-tree", "--name-only", built["sha"], cwd=repo).split()
    assert {"worker-1.txt", "worker-3.txt"} <= {*tree}
    assert rewritten == []


@pytest.mark.parametrize(
    ("workspace", "why"),
    [
        ("shared", "in `shared`, every worker works in one checkout, with no branch or commits of its own"),
        ("snapshot", "a `snapshot` is a repository of its own, which holds no peer's commits"),
    ],
)
async def test_a_population_outside_worktrees_is_refused_saying_why(repo, tmp_path, workspace, why):
    worker = {"harness": harness(lambda: Worker({})), "workspace": workspace, "count": 0}
    team = Team.model_validate({"roles": {"worker": worker}, "topology": {"git-swarm": {"role": "worker", "live": 2}}})
    async with Session.start(team, name="s", principal=PROGRAM, root=tmp_path, cwd=repo) as session:
        with pytest.raises(ConfigError) as caught:
            await population(session, "worker", GOAL, attempts=2)
        spawned = await of_type(session, "agent.spawned")

    assert [str(problem) for problem in caught.value.problems] == [
        "roles.worker.workspace: a worker builds on a peer's commit by checking out its SHA on its own branch, which a "
        f"worktree reaches, as every worktree shares the repository's objects, and {why}: use `worktree`"
    ]
    assert spawned == []


async def test_a_nomination_that_cites_no_recorded_commit_is_invalid(repo, tmp_path):
    async def citing_nothing(worker: Worker) -> str:
        await worker.nominate()
        return "stopped"

    async def citing_its_spawn(worker: Worker) -> str:
        await worker.nominate(f"agent/{worker.name}@1")
        return "stopped"

    plans = {"worker-1": citing_nothing, "worker-2": citing_its_spawn}
    async with Session.start(swarm(plans, live=2), name="s", principal=PROGRAM, root=tmp_path, cwd=repo) as session:
        came_to = await population(session, "worker", GOAL, attempts=2)
        posted = await outcomes_posted(session)

    assert came_to == {"worker-1": "invalid", "worker-2": "invalid"}
    assert {event.gist for event in posted} == {"invalid: its nomination cites no recorded commit"}


async def test_every_outcome_abstaining_included_counts_against_attempts_so_a_population_that_all_abstain_ends(
    repo, tmp_path
):
    plans = {f"worker-{n}": abstain for n in (1, 2, 3)}
    async with Session.start(swarm(plans, live=2), name="s", principal=PROGRAM, root=tmp_path, cwd=repo) as session:
        came_to = await population(session, "worker", GOAL, attempts=3)
        spawned = await of_type(session, "agent.spawned")

    assert came_to == {f"worker-{n}": "abstain" for n in (1, 2, 3)}
    assert [event.data["name"] for event in spawned] == ["worker-1", "worker-2", "worker-3"]


class Crashed(Exception):
    """The program's process, gone."""


async def test_a_population_run_again_after_a_crash_gives_no_worker_a_second_outcome(repo, tmp_path, monkeypatch):
    plans = {"worker-1": contribute, "worker-2": abstain, "worker-3": abstain}
    session = await Session.start(swarm(plans, live=1), name="s", principal=PROGRAM, root=tmp_path, cwd=repo)
    submit = session.submit

    async def crashing(op: str, /, **args: Any) -> Any:
        """Record the second outcome, and die before the program learns that it did."""
        outcome = await submit(op, **args)
        if op == "board.post" and args["name"] == "worker-2":
            raise Crashed
        return outcome

    monkeypatch.setattr(session, "submit", crashing)
    with pytest.raises(Crashed):
        await population(session, "worker", GOAL, attempts=3)
    before = [event.stream for event in await outcomes_posted(session)]
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        came_to = await population(session, "worker", GOAL, attempts=3)
        posted = [event.stream for event in await outcomes_posted(session)]
        spawned = await of_type(session, "agent.spawned")

    assert before == ["board/outcomes/worker-1", "board/outcomes/worker-2"]
    assert came_to.keys() == {"worker-1", "worker-2", "worker-3"}
    assert (came_to["worker-1"], came_to["worker-2"]) == ("contribute", "abstain")
    assert posted == [f"board/outcomes/worker-{n}" for n in (1, 2, 3)]
    assert [event.data["name"] for event in spawned] == ["worker-1", "worker-2", "worker-3"]


async def test_a_population_names_each_reason_its_team_cannot_run_it_before_it_starts_anyone(repo, tmp_path):
    worker = {"harness": harness(lambda: Worker({})), "workspace": "worktree", "count": 2}
    team = Team.model_validate({"roles": {"worker": worker}, "topology": {"until": "program"}})
    async with Session.start(team, name="s", principal=PROGRAM, root=tmp_path, cwd=repo) as session:
        with pytest.raises(Refused, match="invalid: `attempts` counts the workers to start, and 0 is none"):
            await population(session, "worker", GOAL, attempts=0)
        with pytest.raises(ConfigError) as caught:
            await population(session, "worker", GOAL, attempts=1)
        with pytest.raises(ConfigError, match=re.escape("roles: no role `workers`. Did you mean `worker`?")):
            await population(session, "workers", GOAL, attempts=1)
        spawned = await of_type(session, "agent.spawned")

    assert [str(problem) for problem in caught.value.problems] == [
        "roles.worker.count: `worker` starts with the session, with no goal, and a population starts each of its "
        "workers with its goal: set `count = 0`",
        "topology.channels.nominations: a population reads its workers' nominations on topic `nominations`, as "
        "`git-swarm` makes it",
        "topology.channels.outcomes: a population writes each worker's outcome on board `outcomes`, as `git-swarm` "
        "makes it",
    ]
    assert [event.actor for event in spawned] == ["runtime", "runtime"]
