"""Metrics: how a session runs, from counters that are folds and the kernel's gauges, each unknown wherever nothing
measured it. See architecture section 16."""

import json
from collections import Counter
from collections.abc import Sequence
from typing import get_args

from platoon_harness.kernel import Args, Event, Gauges, Refused, Stamps, Txn, View, fold, op
from platoon_harness.schema import Model

from .agents import Agent, Agents
from .clients import Gaps, Group, roster
from .exposures import Exposures
from .provenance import PROVED
from .reports import Surface

_LEVELS = ("met", "unmet", "unverified", "unrecorded")
_DECLARED = ("observed", "partial", "none", "undeclared")
_HARNESSES = "nothing measures what an agent's harness processes use, only the process holding the journal"
_NO_RUNTIME = "no runtime answered this: only the runtime holding a session measures its writer and its process"


class Counters(View):
    """How many events of each type the journal holds, and of the refusals among them how many of each code, counted as
    each commits, so reading them walks nothing and writes nothing."""

    schema = """
    CREATE TABLE v_counters(type TEXT PRIMARY KEY, events INTEGER NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_counters_refused(code TEXT PRIMARY KEY, events INTEGER NOT NULL) WITHOUT ROWID, STRICT;
    """

    @fold("*")
    def counted(self, event: Event) -> None:
        self.db.execute(
            "INSERT INTO v_counters VALUES (?, 1) ON CONFLICT (type) DO UPDATE SET events = events + 1", (event.type,)
        )
        if event.type == "op.refused":
            self.db.execute(
                "INSERT INTO v_counters_refused VALUES (?, 1) ON CONFLICT (code) DO UPDATE SET events = events + 1",
                (event.data["code"],),
            )

    def by_type(self) -> dict[str, int]:
        return {row["type"]: row["events"] for row in self.db.execute("SELECT * FROM v_counters ORDER BY type")}

    def refused(self) -> dict[str, int]:
        rows = self.db.execute("SELECT * FROM v_counters_refused ORDER BY code")
        return {row["code"]: row["events"] for row in rows}


class Metrics(Model):
    """How a session runs, read at `head`.

    Counted from the record as each event commits: `events`, how many of each type the journal holds, and `refused`,
    how many commands it holds refused, by code. Read from its views: `agents`, how many agents stand in each of the
    roster's groups; `trainable`, how many agents' latest start recorded their trainable level `met`, `unmet` or
    `unverified`, or recorded none, `unrecorded`; `coverage`, for each surface, how many agents' latest start declared
    it `observed`, `partial` or `none`, or declared nothing, `undeclared`, beside `proved`, the surfaces a stored result
    proves observed; and `gaps`, how many the record holds, by kind. Measured by the runtime holding the session, as
    they stand now: `gauges`, of its writer and its process since it started. None is unknown and never zero, and
    `unknown` names each metric nothing measured, with why."""

    head: int
    events: dict[str, int]
    refused: dict[str, int]
    agents: dict[Group, int]
    trainable: dict[str, int]
    coverage: dict[Surface, dict[str, int]]
    proved: tuple[Surface, ...]
    gaps: dict[str, int]
    gauges: Gauges | None
    unknown: dict[str, str]


def _grouped(txn: Txn) -> dict[Group, int]:
    counted = Counter(row["group"] for row in roster(txn))
    return {group: counted[group] for group in get_args(Group)}


def _trainable(agents: Sequence[Agent]) -> dict[str, int]:
    counted = Counter((agent.levels.get("trainable") or {}).get("state", "unrecorded") for agent in agents)
    return {**dict.fromkeys(_LEVELS, 0), **counted}


def _coverage(txn: Txn, agents: Sequence[Agent], head: int) -> dict[Surface, dict[str, int]]:
    exposures = txn.view(Exposures)
    counted: dict[Surface, Counter[str]] = {surface: Counter() for surface in get_args(Surface)}
    for agent in agents:
        start = exposures.start(agent.name, head + 1)
        declared = {} if start is None else json.loads(start["coverage"])
        for surface, found in counted.items():
            found[declared.get(surface, "undeclared")] += 1
    return {surface: {**dict.fromkeys(_DECLARED, 0), **found} for surface, found in counted.items()}


def _gaps(txn: Txn, head: int) -> dict[str, int]:
    counted: Counter[str] = Counter()
    for kinds in txn.view(Gaps).held(head).values():
        counted.update(kinds)
    return dict(sorted(counted.items()))


def _unknown(gauges: Gauges | None) -> dict[str, str]:
    """Each metric nothing measured, with why."""
    if gauges is None:
        return {"gauges": _NO_RUNTIME, "harness_resources": _HARNESSES}
    unknown = {"harness_resources": _HARNESSES}
    if not gauges.acks:
        unknown["ack_latency"] = "no write has been answered since the runtime started"
    if gauges.peak_resident_bytes is None:
        unknown["peak_resident_bytes"] = "this system gives it in no unit checked here, which is anywhere but Linux"
    return unknown


@op("session.metrics", query=True)
def session_metrics(txn: Txn, a: Args) -> Metrics:
    """Say how this session runs, from its record and from what its runtime measures. Read at `head`: `events`, how many
    of each type its journal holds, and `refused`, how many commands it holds refused, by code, counted as each commits;
    `agents`, how many stand in each of the roster's groups; `trainable`, `coverage` beside `proved`, and `gaps`, what
    agents' starts recorded of their trainable level and of their harnesses' coverage, and the gaps by kind; and
    `gauges`, what the runtime holding the session has measured of its writer and its process since it started: events
    and commits, depth, commands in flight, `busy` refusals, ack latency, CPU and memory. What nothing measured is None,
    never zero, and `unknown` says why. A person or a program reads this, never an agent: refused `not_permitted` to
    one, as an agent's read is evidence and a query records none."""
    if txn.me.kind == "agent":
        raise Refused(
            "not_permitted",
            "a person or a program reads metrics: an agent's read is evidence, which a query never records",
        )
    head = txn.view(Stamps).head()
    agents = txn.view(Agents).listed()
    counters = txn.view(Counters)
    gauges = txn.gauges()
    return Metrics(
        head=head,
        events=counters.by_type(),
        refused=counters.refused(),
        agents=_grouped(txn),
        trainable=_trainable(agents),
        coverage=_coverage(txn, agents, head),
        proved=PROVED,
        gaps=_gaps(txn, head),
        gauges=gauges,
        unknown=_unknown(gauges),
    )
