"""Which call made a spawn, joined here for the terminal's transcript, and for the page's Tool activity once it is
built: the tool item of its spawner's whose `native_id` is the id the spawn's anchor holds. Either may be recorded
first, so each waits for the other. A spawn that joins no call a client holds says so, as one of OpenHands' and one of
an `exec` harness's do: their calls come through the shim and `ph`, each under an id of its own, which no item holds."""

from bisect import insort
from collections.abc import Hashable, Set
from typing import NamedTuple

from platoon_harness.kernel import Event

UNJOINED = "joins no known call"
"""What a spawn says that joins no call a client holds: none holds the id its anchor holds, or it came under no id."""


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
