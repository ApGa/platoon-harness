"""A population: workers of one role, started by the program that owns the session and each given one outcome, which
the program records on board `outcomes`. It keeps nothing: it reads the record from its start on every run, so run again
after a crash it starts no worker and records no outcome that the record holds. See RFC 0070."""

from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Literal

from platoon_harness.config import Manifest
from platoon_harness.kernel import GIST_LIMIT, Event, Refused
from platoon_harness.schema import ConfigError, Problem, nearest
from platoon_harness.session import Session
from platoon_harness.team import Team

__all__ = ["Outcome", "population"]

Outcome = Literal["contribute", "nominate", "abstain", "invalid", "failed"]
"""What a worker came to: commits of its own and no nomination; one nomination, citing one recorded commit, and no
commit; neither; anything else; or an end other than finishing, or a last look that never finished."""

TOLD = """\
You are one worker of a population, and your attempt comes to one outcome, which the program that started you reads from
the record once you have ended:

- contribute: commit your work on your own branch, and nominate nothing;
- nominate: send one message to `#nominations` whose `based_on` holds the ref of one recorded commit, which
  `repo.commit` gives for its SHA, and commit nothing;
- abstain: do neither, and say why as you finish.

Anything else is invalid, and an end other than finishing is failed. Every outcome counts as one of the population's
attempts. Board `outcomes` holds each worker's outcome once it has one."""
"""What each worker is told beside its goal: how its outcome is read."""

_SETTLED = ("finished", "failed", "cancelled")


def _ref(event: Event) -> str:
    return f"{event.stream}@{event.version}"


@dataclass
class _Worker:
    """One worker as the record holds it: its end, the last state its stop reached, whether a turn of its is open, the
    seq that ended its last while it lived and how that turn ended, the refs of the commits its worktree made and its
    nominations, in the record's order, whether it has an outcome, and the turn end at which the population last asked
    how it stood."""

    name: str
    ended: Event | None = None
    stop: str | None = None
    turn: bool = False
    turn_ended: int | None = None
    turn_reason: str | None = None
    commits: list[str] = field(default_factory=list)
    nominations: list[Event] = field(default_factory=list)
    outcome: Outcome | None = None
    asked: int | None = None


class _Record:
    """What a population reads of the record, folded from the journal's start: the workers of its role, in the order
    they were spawned, every name an agent has taken, the agents live, how many have ended, and each recorded commit."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.workers: dict[str, _Worker] = {}
        self.taken: set[str] = set()
        self.live: set[str] = set()
        self.ends = 0
        self.commits: dict[str, Event] = {}
        self.cursor = 0

    def fold(self, event: Event) -> None:
        self.cursor = event.seq
        worker = self.workers.get(event.agent or "")
        match event.type:
            case "agent.spawned":
                name = event.data["name"]
                self.taken.add(name)
                self.live.add(name)
                if event.data["role"] == self.role:
                    self.workers[name] = _Worker(name)
            case "agent.ended":
                self.live.discard(event.agent or "")
                self.ends += 1
                if worker is not None:
                    worker.ended = event
            case "turn.started" if worker is not None:
                worker.turn = True
            case "turn.ended" | "turn.lost" if worker is not None and worker.ended is None:
                worker.turn, worker.turn_ended = False, event.seq
                worker.turn_reason = event.data["reason"] if event.type == "turn.ended" else "lost"
            case "effect.finished" | "effect.failed" | "effect.cancelled" if event.data["kind"] == "stop":
                if worker is not None:
                    worker.stop = event.type.removeprefix("effect.")
            case "repo.committed":
                self.commits[_ref(event)] = event
                made_in = event.data.get("made_in") or ""
                if made_in.startswith("@") and (maker := self.workers.get(made_in[1:])) is not None:
                    maker.commits.append(_ref(event))
            case "message.sent" if event.stream == "channel/nominations":
                kind, _, name = event.actor.partition(":")
                if kind == "agent" and (sender := self.workers.get(name)) is not None:
                    sender.nominations.append(event)
            case "board.posted" if event.stream.startswith("board/outcomes/"):
                posted = self.workers.get(event.stream.removeprefix("board/outcomes/"))
                if posted is not None:
                    posted.outcome = event.data["fields"].get("outcome")

    def next_name(self) -> str:
        """The first of `<role>-1`, `<role>-2` and on that no agent has taken."""
        number = 1
        while f"{self.role}-{number}" in self.taken:
            number += 1
        return f"{self.role}-{number}"

    def outcome_of(self, worker: _Worker) -> tuple[Outcome, str, list[str]]:
        """A worker's outcome, once it has ended and its stop has settled, in words, and the refs it rests on: its end
        and what it came to."""
        ended = worker.ended
        assert ended is not None
        cites = [_ref(ended)]
        status = ended.data["status"]
        if status != "finished":
            reason = ended.data.get("reason")
            what = f"it ended {status}" + (f": {reason}" if reason else "")
            if worker.turn_reason not in (None, "stopped"):
                what = f"its turn ended {worker.turn_reason}, and {what}"
            return "failed", what, cites
        if worker.stop != "finished":
            return "failed", "its last look never finished, so what it left in its worktree is unknown", cites
        made, nominated = worker.commits, worker.nominations
        last = made[-1:]
        cited = [ref for ref in nominated[0].based_on if ref in self.commits] if nominated else []
        if made and nominated:
            why = "it both committed and nominated, and an attempt does one"
            return "invalid", why, [*cites, *last, *map(_ref, nominated)]
        if len(nominated) > 1:
            why = f"it nominated {len(nominated)} times, and an attempt nominates once"
            return "invalid", why, [*cites, *map(_ref, nominated)]
        if nominated and len(cited) != 1:
            why = (
                "its nomination cites no recorded commit"
                if not cited
                else f"its nomination cites {len(cited)} recorded commits"
            )
            return "invalid", why, [*cites, _ref(nominated[0])]
        if nominated:
            return "nominate", self.commits[cited[0]].gist, [*cites, _ref(nominated[0]), *cited]
        if made:
            what = self.commits[last[0]].gist
            return "contribute", what if len(made) == 1 else f"{len(made)} commits, the last {what}", [*cites, *last]
        return "abstain", ended.data.get("report") or "it finished with no commit and no nomination", cites


def _unfit(team: Team, role: str) -> list[Problem]:
    """Why a population of `role` cannot run in a session of `team`."""
    if role not in team.roles:
        return [Problem("roles", f"no role `{role}`.{nearest(role, team.roles)}")]
    problems = []
    if team.starts(role):
        what = (
            f"`{role}` starts with the session, with no goal, and a population starts each of its workers with its "
            "goal: set `count = 0`"
        )
        problems.append(Problem(f"roles.{role}.count", what))
    for name, kind, what in (
        ("nominations", "topic", "reads its workers' nominations on topic `nominations`"),
        ("outcomes", "board", "writes each worker's outcome on board `outcomes`"),
    ):
        channel = team.topology.channels.get(name)
        if channel is None or channel.kind != kind:
            problems.append(Problem(f"topology.channels.{name}", f"a population {what}, as `git-swarm` makes it"))
    return problems


async def _team(session: Session) -> Team:
    """The team the session runs, as its manifest keeps it."""
    ref = (await session.manifest())["manifest"]
    if ref is None:
        raise Refused("unsupported", "this session keeps no manifest, so its team is unknown")
    return Team.loads(Manifest.model_validate_json(await session.get_body(ref)).team)


class _Population:
    """One run of a population: the record it reads, and what this run alone has learned, that a spawn waits for an
    agent to end, or that starting is over, and why."""

    def __init__(self, session: Session, record: _Record, goal: str, told: str, attempts: int, live: int | None):
        self.session, self.record, self.goal, self.told = session, record, goal, told
        self.attempts, self.live = attempts, live
        self.waiting: int | None = None
        self.stopped: Refused | None = None

    async def act(self) -> None:
        """Record each outcome that is due, retire each worker left idle, and start the next worker if there is room."""
        for worker in self.record.workers.values():
            if worker.outcome is None and worker.ended is not None and worker.stop in _SETTLED:
                await self._post(worker)
            elif worker.ended is None and not worker.turn and worker.turn_ended not in (None, worker.asked):
                await self._retire_if_idle(worker)
        await self._start()

    async def _post(self, worker: _Worker) -> None:
        outcome, what, cites = self.record.outcome_of(worker)
        gist = f"{outcome}: {what}"[:GIST_LIMIT]
        fields = {"outcome": outcome}
        posted = await self.session.submit(
            "board.post", board="outcomes", name=worker.name, gist=gist, fields=fields, based_on=cites
        )
        if posted.refusal is not None and posted.refusal.code != "conflict":
            raise Refused.of(posted.refusal)

    async def _retire_if_idle(self, worker: _Worker) -> None:
        """A worker whose turn ended with nothing more to come for it, as a failed turn leaves one, is retired, and
        its outcome is then `failed`. One waiting on something is left to it, and one that is at work again the kernel
        refuses to retire."""
        worker.asked = worker.turn_ended
        if (await self.session.status(worker.name))["state"] == "idle":
            await self.session.submit("agent.retire", agent=worker.name)

    async def _start(self) -> None:
        record = self.record
        if self.stopped is not None or len(record.workers) >= self.attempts or self.waiting == record.ends:
            return
        if self.live is not None and len(record.live) >= self.live:
            return
        try:
            await self.session.spawn(record.next_name(), record.role, self.goal, body=self.told)
        except Refused as refused:
            if refused.refusal.code == "not_permitted":
                self.waiting = record.ends
            else:
                self.stopped = refused

    def done(self) -> bool:
        workers = self.record.workers.values()
        over = self.stopped is not None or len(workers) >= self.attempts
        return over and all(worker.outcome is not None for worker in workers)


async def population(session: Session, role: str, goal: str, *, attempts: int) -> dict[str, Outcome]:
    """Start workers of `role` with `goal`, as many at once as the session's `max_live` allows, and all at once with
    none, until `attempts` have started, and give each one outcome once it has ended and its stop has looked at what it
    left: each worker's, by its name, in the order they started.

    A worker is `<role>-1`, `<role>-2` and on, the first name no agent has taken, told beside its goal how its outcome
    is read. Its outcome is recorded once, as an entry of board `outcomes` by its name, `<outcome>: <what>`, with the
    outcome in `fields` and citing the worker's end and what it came to, and the board refuses a second. Every outcome
    counts against `attempts`, abstaining and failing too, so a population whose every worker abstains ends. A worker
    whose turn ended with nothing more to come for it is retired, and is `failed`. A spawn refused `not_permitted` is
    tried again once an agent has ended. Any other refusal ends the starting, and is raised once each worker started
    has its outcome. The population chooses nothing among the nominations: that is the person's.

    Refused `invalid` for `attempts` below 1, and `ConfigError` names each reason the session's team cannot run it: no
    such role, a role that starts with the session, or no topic `nominations` or board `outcomes`."""
    if attempts < 1:
        raise Refused("invalid", f"`attempts` counts the workers to start, and {attempts} is none")
    team = await _team(session)
    if problems := _unfit(team, role):
        raise ConfigError(problems)
    told = await session.put_body(TOLD.encode())
    record = _Record(role)
    run = _Population(session, record, goal, told, attempts, team.topology.limits.max_live)
    head = await session.head()
    async with aclosing(session.events(follow=True)) as events:
        async for event in events:
            record.fold(event)
            if event.seq < head:
                continue
            await run.act()
            if run.done():
                break
            head = await session.head()
        else:
            raise Refused("unavailable", f"the runtime of session {session.name} went before its population ended")
    if run.stopped is not None and len(record.workers) < attempts:
        raise run.stopped
    return {name: worker.outcome for name, worker in record.workers.items() if worker.outcome is not None}
