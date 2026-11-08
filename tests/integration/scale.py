"""A team at the size of the brief's Scale case: 100 scripted members on the real tool plane, which a person wakes a
round at a time until the journal holds 100,000 events, and what the run read as it went."""

import os
import platform
import sqlite3
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from platoon_harness import Session, Team
from platoon_harness.kernel import filesystem
from platoon_harness.primitives import Metrics

from .scripts import MEMBERS, inside

EVENTS = 100_000
"""How many events the brief's Scale case asks a journal to hold."""


def team() -> Team:
    """The members in a mesh, each woken by the person's post to `#rounds`, with a board for their notes and a queue for
    their work. A member's inbox is pulled, so what the one before it says waits for its read and wakes nothing."""
    return Team.model_validate(
        {
            "roles": {"member": {"harness": inside("member"), "count": MEMBERS, "delivery": "pull"}},
            "topology": {
                "mesh": {"role": "member", "board": "notes"},
                "channels": {
                    "rounds": {"kind": "topic", "writers": "human", "readers": "role:member", "delivery": "wake"},
                    "work": {"kind": "queue", "writers": "role:member", "readers": "role:member"},
                },
            },
        }
    )


@dataclass(frozen=True)
class Round:
    """One round: the seconds from the person's post to the last member's end of turn, the round trip of a message the
    person sent while the members worked, and `session.metrics` read at its end, with the seconds that read took."""

    seconds: float
    said: float
    metrics: Metrics
    asked: float


async def nth(guest: Session, after: int, match: str, kind: str, count: int) -> int:
    """The seq of the `count`th event of type `kind` past `after`, on the streams `match` globs, once it has come."""
    seen = 0
    async with aclosing(guest.events(after, match=match, follow=True)) as events:
        async for event in events:
            seen += event.type == kind
            if seen == count:
                return event.seq
    raise AssertionError(f"the session ended before {count} {kind}")


async def drive(guest: Session) -> list[Round]:
    """Rounds until the journal holds `EVENTS`. Each wakes every member with the person's post to `#rounds`, and ends
    when each has ended its turn. Once half have begun, the person tells the first member something, which its next read
    finds, as its inbox wakes nothing."""
    rounds: list[Round] = []
    head = after = await guest.head()
    while head < EVENTS:
        began = perf_counter()
        number = len(rounds) + 1
        await guest.send("#rounds", f"round {number}")
        await nth(guest, after, "turn/*", "turn.started", MEMBERS // 2)
        sending = perf_counter()
        await guest.send("@member-1", f"round {number} is under way")
        said = perf_counter() - sending
        after = await nth(guest, after, "turn/*", "turn.ended", MEMBERS)
        seconds = perf_counter() - began
        asking = perf_counter()
        metrics = await guest.metrics()
        rounds.append(Round(seconds, said, metrics, perf_counter() - asking))
        head = metrics.head
    return rounds


def hardware(folder: Path) -> dict[str, str]:
    """The machine a run measures, by its specs alone, which is how docs/reference/scale.md describes it."""
    cpus = Path("/proc/cpuinfo").read_text().splitlines()
    memory = Path("/proc/meminfo").read_text().splitlines()
    return {
        "cpu": next(line.split(":", 1)[1].strip() for line in cpus if line.startswith("model name")),
        "cores": f"{len(os.sched_getaffinity(0))} of {os.cpu_count()}",
        "memory": f"{next(int(line.split()[1]) for line in memory if line.startswith('MemTotal')) / 2**20:.0f} GiB",
        "filesystem": filesystem(folder).name,
        "kernel": platform.release(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
    }
