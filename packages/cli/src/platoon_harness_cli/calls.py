"""An agent's tool calls: which call made a spawn, joined here once for both clients, and a page of an agent's calls in
words, which the page's Tool activity draws. A spawn joins the tool item of its spawner's whose `native_id` is the id
the spawn's anchor holds. Either may be recorded first, so each waits for the other. A spawn that joins no call a client
holds says so, as one of OpenHands' and one of an `exec` harness's do: their calls come through the shim and `ph`, each
under an id of its own, which no item holds."""

from bisect import insort
from collections.abc import Hashable, Set
from dataclasses import dataclass
from typing import NamedTuple

from platoon_harness import Session
from platoon_harness.kernel import Event

from .provenance import Line

UNJOINED = "joins no known call"
"""What a spawn says that joins no call a client holds: none holds the id its anchor holds, or it came under no id."""
PAGE = 100
"""The most calls a page of an agent's calls lists."""
_READ = 4096
"""The most events one read of a page asks for: as many as a read that names streams scans."""
_ENDS = ("turn.ended", "turn.lost")


class _Call(NamedTuple):
    """A tool call, by its agent and the id its harness gave it."""

    agent: str
    id: str


def _call_of(event: Event) -> _Call | None:
    """The call a tool item reports, by its agent and `native_id`, or the call an agent's spawn came under, by its
    spawner and the id its anchor holds. None for any other event, and for a spawn that came under no id."""
    data = event.data if isinstance(event.data, dict) else {}
    if event.type == "item.recorded" and data.get("kind") == "tool" and data.get("native_id") and event.agent:
        return _Call(event.agent, data["native_id"])
    if event.type == "agent.spawned" and event.native and event.actor.startswith("agent:"):
        return _Call(event.actor.removeprefix("agent:"), next(iter(event.native.values())))
    return None


class Join[T: Hashable]:
    """The tool calls and the spawns a client holds, each as its own `T`, a line or a row, and each spawn joined to the
    call that made it, whichever the client took first. A call is held by the first of its items taken."""

    def __init__(self) -> None:
        self._calls: dict[_Call, T] = {}
        self._called: dict[T, _Call] = {}
        self._spawns: dict[_Call, list[tuple[int, T]]] = {}
        self._anchors: dict[T, _Call] = {}

    def take(self, event: Event, held: T) -> None:
        """Hold what the client holds for a tool item or a spawn. Anything else joins nothing."""
        if (call := _call_of(event)) is None:
            return
        if event.type == "agent.spawned":
            insort(self._spawns.setdefault(call, []), (event.seq, held), key=lambda spawn: spawn[0])
            self._anchors[held] = call
        elif call not in self._calls:
            self._calls[call] = held
            self._called[held] = call

    def call_of(self, spawn: T) -> T | None:
        """The call a spawn joins, or None where it joins no known call."""
        call = self._anchors.get(spawn)
        return None if call is None else self._calls.get(call)

    def spawns_of(self, call: T) -> list[T]:
        """The spawns that join a call, in the journal's order."""
        called = self._called.get(call)
        return [] if called is None else [spawn for _, spawn in self._spawns.get(called, ())]

    def keep(self, held: Set[T]) -> None:
        """Let go of what the client let go, keeping what it still holds."""
        self._calls = {call: kept for call, kept in self._calls.items() if kept in held}
        self._called = {kept: call for call, kept in self._calls.items()}
        self._anchors = {spawn: call for spawn, call in self._anchors.items() if spawn in held}
        spawns = {call: [spawn for spawn in spawns if spawn[1] in held] for call, spawns in self._spawns.items()}
        self._spawns = {call: kept for call, kept in spawns.items() if kept}


@dataclass(frozen=True)
class Calls:
    """A page of an agent's tool calls, in words: its lines, newest first, and `cursor`, the `before` of the page
    before it, or None once the journal's start is read."""

    lines: list[Line]
    cursor: int | None


async def page(session: Session, agent: str, *, before: int | None = None) -> Calls:
    """`agent`'s tool calls before the seq `before`, or the newest: whole turns, newest first, as many as `PAGE` calls
    take and one at least, as a harness reports a call, and what it spawned, within the turn that made it. Each turn
    is a heading over its calls, newest first: each call one line, from the first of its items to the last, with what
    joins it under it, and a spawn that joins no call where the journal has it, saying so. A turn of more than `PAGE`
    calls is listed in its newest, saying how many it leaves out and what prints them."""
    turns: list[list[Event]] = []
    turn: list[Event] = []
    calls = 0
    at = await session.head() + 1 if before is None else before
    while at > 1:
        read = await session.page(before=at, streams=(f"turn/{agent}",), match="agent/*", limit=_READ)
        for event in reversed(read.events):
            if not _taken(event, agent):
                continue
            turn.append(event)
            if event.type != "turn.started":
                continue
            if turns and calls + _count(turn) > PAGE:
                return Calls(_lines(session.name, agent, turns, before), turns[-1][-1].seq)
            turns.append(turn)
            calls, turn = calls + _count(turn), []
            if calls >= PAGE:
                return Calls(_lines(session.name, agent, turns, before), event.seq)
        at = read.cursor
    if turn and turns and calls + _count(turn) > PAGE:
        return Calls(_lines(session.name, agent, turns, before), turns[-1][-1].seq)
    return Calls(_lines(session.name, agent, [*turns, turn] if turn else turns, before), None)


def _taken(event: Event, agent: str) -> bool:
    """Whether a page of `agent`'s calls takes `event`: a tool item or a patch of its, where one of its turns begins or
    ends, or a child it spawned."""
    if event.stream == f"turn/{agent}":
        data = event.data if isinstance(event.data, dict) else {}
        return event.type in ("turn.started", *_ENDS) or data.get("kind") in ("tool", "patch")
    return event.type == "agent.spawned" and event.actor == f"agent:{agent}"


def _id(item: Event) -> str | int:
    """The call an item is of: the id its harness gave the call, or for one that names none, the item alone."""
    return item.data.get("native_id") or item.seq


def _count(events: list[Event]) -> int:
    return len({_id(event) for event in events if event.type == "item.recorded"})


def _lines(session: str, agent: str, turns: list[list[Event]], before: int | None) -> list[Line]:
    lines = [line for turn in turns for line in _turn(session, turn)]
    return lines or [Line("", f"The journal holds no tool call of @{agent}'s{' before these' if before else ''}.")]


def _turn(session: str, held: list[Event]) -> list[Line]:
    """One turn's lines, from its events newest first, or none for a turn that made no call and spawned nothing."""
    events = held[::-1]
    items: dict[str | int, list[Event]] = {}
    spawns: dict[int, Event] = {}
    join: Join[int] = Join()
    for event in events:
        join.take(event, event.seq)
        if event.type == "item.recorded":
            items.setdefault(_id(event), []).append(event)
        elif event.type == "agent.spawned":
            spawns[event.seq] = event
    if not items and not spawns:
        return []
    calls = sorted(items.values(), key=lambda call: call[0].seq, reverse=True)
    left = len(calls) - PAGE
    oldest = calls[PAGE - 1][0].seq if left > 0 else 0
    standing = [(seq, [_spawned(spawn, joined=False)]) for seq, spawn in spawns.items() if join.call_of(seq) is None]
    standing = [(seq, said) for seq, said in standing if seq >= oldest]
    for call in calls[:PAGE]:
        under = [_spawned(spawns[seq], joined=True) for seq in join.spawns_of(call[0].seq)]
        standing.append((call[0].seq, [_call(call), *under]))
    lines = [_heading(events), *(line for _, said in sorted(standing, key=lambda at: -at[0]) for line in said)]
    if left > 0:
        command = f"platoon-harness events {session} --after {events[0].seq - 1}"
        said = (
            f"The rest of this turn, {left:,} {'call' if left == 1 else 'calls'} before these and what they spawned, "
            f"is not listed: `{command}` prints it, among the session's other events."
        )
        lines.append(Line("", said, warn=True))
    return lines


def _heading(events: list[Event]) -> Line:
    """A turn, by the id its harness gave it, and how it ended, or that the journal holds no end of it."""
    started = next((event for event in events if event.type == "turn.started"), None)
    ended = next((event for event in events if event.type in _ENDS), None)
    turn = "before its first turn" if started is None else f"turn {started.data.get('turn')}"
    end = "not ended" if ended is None else "lost" if ended.type == "turn.lost" else ended.data.get("reason", "ended")
    return Line("heading", f"{turn}: {end}")


def _call(items: list[Event]) -> Line:
    """A call: what it was called with, as its first item says it, and how it ended, as its last end does, or that it
    has no end in the journal, `started`. One that did not complete, or that its approval denied, is a warning."""
    first, last = items[0], items[-1]
    ends = [item for item in items if item.data.get("phase") != "started"]
    outcome = (ends[-1].data.get("outcome") or "completed") if ends else "started"
    said = first if first.data.get("phase") == "started" else last
    warn = bool(ends) and outcome not in ("completed", "allow")
    return Line(outcome, " ".join(said.gist.split()), f"{last.stream}@{last.version}", warn)


def _spawned(event: Event, *, joined: bool) -> Line:
    """A child an agent spawned: under the call that made it, or standing alone, saying it joins no known call."""
    gist = " ".join(event.gist.split())
    return Line("spawned", f"↳ {gist}" if joined else f"{gist} · {UNJOINED}", f"{event.stream}@{event.version}")
