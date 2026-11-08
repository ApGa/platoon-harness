"""The brief's Scale case on the real stack: 100 ScriptedDriver agents on the real tool plane drive 100,000 events
through the real kernel and runtime, and what that costs is measured and held to budgets twice the most
docs/reference/scale.md publishes. The run is slow and its budgets fit the hardware that page describes, so it runs by
hand before each release and no CI job runs it. Each test prints what it measured."""

import asyncio
import contextlib
import json
import os
import signal
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest

from platoon_harness import Session
from platoon_harness.kernel import Kernel, SystemClock, registry
from platoon_harness.primitives import PRIMITIVES, Counters
from platoon_harness.rpc import LINE_LIMIT
from platoon_harness.runtime.paths import read_running
from platoon_harness_cli.web import follow
from platoon_harness_cli.web.projection import Projection

from ..conftest import end_runtimes
from .scale import EVENTS, Round, drive, hardware, nth, team
from .scripts import MEMBERS

pytestmark = [pytest.mark.slow, pytest.mark.timeout(1800)]

KiB, MiB = 2**10, 2**20
WALKED = 8
"""The most pages of one query timed, each from the cursor of the one before."""

# Each budget is twice the most that docs/reference/scale.md says was measured, and a time is never under 50 ms, as
# twice a few milliseconds would fail on a busy host's noise alone.
PEAK = 194 * MiB
"""The most memory the runtime may have held at 100,000 events."""
GROWTH = 44 * MiB
"""The most the runtime's peak memory may grow over the second half of the events."""
THROUGHPUT = 615
"""The fewest events a second the writer may have committed since the runtime started: half the fewest measured."""
ACK_P99 = 0.140
SAID = 0.145
"""The slowest round trip of a person's message sent while the members work."""
PAGES = {
    "board.query": 0.050,
    "channel.list": 0.050,
    "contributors": 0.050,
    "eligibility": 0.050,
    "interactions": 4.1,
    "lineage": 0.050,
    "message.read": 0.060,
    "peers": 0.050,
    "spans": 0.050,
    "task.list": 0.050,
    "uses": 0.050,
    "read": 0.050,
    "read before": 0.050,
    "read streams": 0.050,
}
"""The slowest page each query that pages may answer, by op, and the journal's own read three ways: forward from the
start, back from the head, and of one member's stream."""
SNAPSHOTS = {"roster": (0.050, 208 * KiB), "attention": (0.090, 1358 * KiB), "changes": (0.050, 126)}
"""The seconds and bytes each whole snapshot may take."""
PROJECTION = 37.0
METRICS_READ = 0.100
COUNTING = 0.028
"""The most that counting an event again from the journal may cost, as a share of the CPU the runtime spent on each:
a bound on what the fold costs the writer, as it decodes each event too."""
RESUMED = (7.5, 7.5)
"""The seconds from a resume after a SIGKILL until the runtime answers, and until every member is back."""


@dataclass(frozen=True)
class Measured:
    """What one run measured: the machine, each round, each query's pages, the snapshots, the page's projection, a
    resume after a kill, and counting the journal again."""

    hardware: Mapping[str, str]
    rounds: list[Round]
    pages: dict[str, list[float]]
    snapshots: dict[str, tuple[float, int, int]]
    projection: float
    resumed: tuple[float, float]
    counting: tuple[float, int]


def paging() -> set[str]:
    """Each op a person may ask that answers a page and takes an earlier answer's cursor as `after`, as the op table
    lists them, but `view.watch`, whose snapshot is whole."""
    ops = registry(PRIMITIVES).items()
    found = {
        name for name, op in ops if (op.query or op.exposes) and not op.runtime and "after" in op.input.model_fields
    }
    return found - {"view.watch"}


async def walk(guest: Session, op: str, args: dict[str, Any]) -> list[float]:
    """The seconds each page took, up to `WALKED`, each from the cursor of the one before, until one gives none."""
    seconds: list[float] = []
    after = None
    while len(seconds) < WALKED:
        began = perf_counter()
        outcome = await guest.submit(op, **args, **({} if after is None else {"after": after}))
        seconds.append(perf_counter() - began)
        assert outcome.refusal is None, (op, outcome.refusal)
        cursor = outcome.result["cursor"]
        if cursor is None or cursor == after:
            break
        after = cursor
    return seconds


async def read_pages(guest: Session, **args: Any) -> list[float]:
    """The seconds each page of the journal's own read took, up to `WALKED`, each from the cursor of the one before."""
    seconds: list[float] = []
    while len(seconds) < WALKED:
        began = perf_counter()
        page = await guest.page(**args)
        seconds.append(perf_counter() - began)
        if not page.events:
            break
        args |= {"before": page.cursor} if "before" in args else {"after": page.cursor}
    return seconds


async def asked(guest: Session) -> dict[str, list[float]]:
    """Each query that pages, asked as the person on what the run left, and the journal's own read."""
    notes = await guest.submit("board.get", board="notes", name="member-1")
    latest = notes.result["ref"]
    args = {
        "board.query": {"board": "notes", "history": True},
        "channel.list": {},
        "contributors": {"ref": latest},
        "eligibility": {"agent": "@member-1", "episode": "scale"},
        "interactions": {},
        "lineage": {"ref": latest},
        "message.read": {},
        "peers": {},
        "spans": {"agent": "@member-1"},
        "task.list": {"queue": "work"},
        "uses": {"ref": "channel/rounds@1"},
    }
    pages = {op: await walk(guest, op, args[op]) for op in sorted(args)}
    head = await guest.head()
    pages["read"] = await read_pages(guest, after=0)
    pages["read before"] = await read_pages(guest, before=head + 1)
    pages["read streams"] = await read_pages(guest, after=0, streams=["agent/member-1"])
    return pages


async def snapshots(guest: Session) -> dict[str, tuple[float, int, int]]:
    """Each whole snapshot's seconds, rows and bytes, as `view.watch` answers it first."""
    found = {}
    for name in SNAPSHOTS:
        began = perf_counter()
        outcome = await guest.submit("view.watch", name=name)
        seconds = perf_counter() - began
        assert outcome.refusal is None, outcome.refusal
        found[name] = (seconds, len(outcome.result["rows"]), len(json.dumps(outcome.result).encode()))
    return found


async def projected(guest: Session) -> float:
    """The seconds the page's projection took to fold the journal, from nothing, as `web` folds it."""
    projection = Projection(guest.folder, guest.name, "you")
    moved, head = asyncio.Condition(), await guest.head()
    began = perf_counter()
    following = asyncio.ensure_future(follow(guest, projection, moved, SystemClock()))
    async with moved:
        await moved.wait_for(lambda: projection.through >= head)
    seconds = perf_counter() - began
    following.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await following
    projection.close()
    return seconds


async def killed_and_resumed(guest: Session, root: Path) -> tuple[float, float]:
    """A round cut by a SIGKILL of the runtime once half the members have begun it, then the seconds until a runtime
    resumed in its place answers, and until every member is back."""
    head = await guest.head()
    await guest.send("#rounds", "a round the kill cuts")
    await nth(guest, head, "turn/*", "turn.started", MEMBERS // 2)
    running = read_running(guest.folder)
    assert running is not None
    os.kill(running.pid, signal.SIGKILL)
    killed = await guest.head()  # Read from history, which answers once the lock has gone with the runtime.
    began = perf_counter()
    resumed = await Session.resume(guest.name, root=root, detach=True)
    try:
        answered = perf_counter() - began
        await nth(resumed, killed, "agent/*", "agent.resumed", MEMBERS)
        return answered, perf_counter() - began
    finally:
        await resumed.leave()


async def counted_again(folder: Path) -> tuple[float, int]:
    """The seconds a writer took to count every event of the journal again, once no runtime holds it, and how many."""
    kernel = Kernel.open(folder, extensions=PRIMITIVES)
    try:
        began = perf_counter()
        await kernel.rebuild(Counters)
        return perf_counter() - began, kernel.head
    finally:
        kernel.close()


async def run(root: Path) -> Measured:
    """The rounds to 100,000 events, then each read the person makes of what they left, then a kill and a resume, and
    last the journal counted again, once no runtime holds it."""
    cwd = root / "cwd"
    cwd.mkdir()
    measured: dict[str, Any] = {"hardware": hardware(root)}
    guest = await Session.start(team(), name="scale", root=root, cwd=cwd, detach=True)
    try:
        await guest.open_episode("scale")
        measured["rounds"] = await drive(guest)
        measured["pages"] = await asked(guest)
        measured["snapshots"] = await snapshots(guest)
        measured["projection"] = await projected(guest)
        measured["resumed"] = await killed_and_resumed(guest, root)
    finally:
        await guest.leave()
        await asyncio.to_thread(end_runtimes, root)
    measured["counting"] = await counted_again(guest.folder)
    return Measured(**measured)


@pytest.fixture(scope="module")
def measured(tmp_path_factory: pytest.TempPathFactory) -> Measured:
    """One run, which every test reads. Its runtime imports this checkout's harnesses."""
    root = tmp_path_factory.mktemp("scale")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[2]))
        monkeypatch.setenv("PLATOON_HARNESS_HOME", str(root))
        done = asyncio.run(run(root))
    print("\nhardware:", ", ".join(f"{key} {value}" for key, value in done.hardware.items()))
    return done


def peak(round: Round) -> int:
    """The most memory the runtime had held by a round's end, as `session.metrics` read it there."""
    gauges = round.metrics.gauges
    assert gauges is not None and gauges.peak_resident_bytes is not None
    return gauges.peak_resident_bytes


def test_100_scripted_agents_reach_100000_events_with_the_runtime_s_memory_bounded(measured: Measured):
    """Every member takes one turn a round and none fails. The runtime's peak memory, which `session.metrics` reads at
    each round's end, stays within its budget, and so does what the second half of the events adds to it."""
    rounds = measured.rounds
    last = rounds[-1].metrics
    peaks = [peak(round) for round in rounds]
    half = next(held for round, held in zip(rounds, peaks, strict=True) if round.metrics.head >= EVENTS / 2)
    print(
        f"{len(rounds)} rounds to {last.head} events, {statistics.median(r.seconds for r in rounds):.1f} s a round; "
        f"peak memory at each round's end {', '.join(f'{held / MiB:.0f}' for held in peaks)} MiB"
    )
    assert last.head >= EVENTS
    assert last.events["turn.ended"] == MEMBERS * len(rounds)
    assert [last.agents[group] for group in ("needs_you", "done", "failed")] == [0, 0, 0]
    assert last.refused == {}
    assert peaks[-1] <= PEAK
    assert peaks[-1] - half <= GROWTH, "memory grew with the journal"


def test_writer_throughput_and_ack_latency_stay_within_their_budgets(measured: Measured):
    """The writer's own gauges at the last round, and a person's message sent while the members work, end to end."""
    gauges = measured.rounds[-1].metrics.gauges
    assert gauges is not None and gauges.ack_p99 is not None
    said = [round.said for round in measured.rounds]
    print(
        f"{gauges.events} events in {gauges.commits} commits over {gauges.seconds:.0f} s: "
        f"{gauges.events / gauges.seconds:.0f} events a second; ack p50 {gauges.ack_p50 * 1000:.1f} ms, "
        f"p99 {gauges.ack_p99 * 1000:.1f} ms, max {gauges.ack_max * 1000:.0f} ms; deepest queue {gauges.deepest}, "
        f"busy {gauges.busy}; a person's message p50 {statistics.median(said) * 1000:.0f} ms, "
        f"max {max(said) * 1000:.0f} ms"
    )
    assert gauges.events / gauges.seconds >= THROUGHPUT
    assert gauges.ack_p99 <= ACK_P99
    assert max(said) <= SAID


def test_every_query_that_pages_answers_a_page_within_its_budget_at_100000_events(measured: Measured):
    """Each op a person may ask that pages, as the op table lists them, and the journal's own read, each walked a page
    at a time on what the run left."""
    pages = measured.pages
    for name, seconds in pages.items():
        print(f"{name}: {len(seconds)} pages, first {seconds[0] * 1000:.0f} ms, slowest {max(seconds) * 1000:.0f} ms")
    assert paging() <= pages.keys()
    assert {name: max(seconds) for name, seconds in pages.items() if max(seconds) > PAGES[name]} == {}


def test_the_roster_attention_and_changes_snapshots_are_measured_at_100_agents(measured: Measured):
    """Each is whole, not paged: its rows and bytes are measured, and it must fit one line of the RPC."""
    for name, (seconds, rows, size) in measured.snapshots.items():
        print(f"{name}: {rows} rows, {size} bytes, {seconds * 1000:.0f} ms")
        budget, most = SNAPSHOTS[name]
        assert size < min(most, LINE_LIMIT) and seconds <= budget, name


def test_the_page_s_projection_folds_100000_events_within_its_budget(measured: Measured):
    print(f"the page's projection folded {measured.rounds[-1].metrics.head} events in {measured.projection:.0f} s")
    assert measured.projection <= PROJECTION


def test_who_reached_whom_answers_within_its_budget_at_100000_events(measured: Measured):
    """`interactions` walks the journal to its head on every page, and folds nothing."""
    seconds = measured.pages["interactions"]
    print(f"interactions: {len(seconds)} pages, {', '.join(f'{page:.1f}' for page in seconds)} s")
    assert max(seconds) <= PAGES["interactions"]


def test_metrics_cost_the_writer_no_more_than_their_budget(measured: Measured):
    """Counting every event again from the journal, which decodes each too, bounds what the fold costs the writer, set
    beside the CPU the runtime spent writing them. A read of `session.metrics`, as each round's end asks it."""
    gauges = measured.rounds[-1].metrics.gauges
    assert gauges is not None
    seconds, events = measured.counting
    share = (seconds / events) / (gauges.cpu_seconds / gauges.events)
    reads = [round.asked for round in measured.rounds]
    print(
        f"counting {events} events again took {seconds:.2f} s, {seconds / events * 1e6:.0f} us an event, "
        f"{share:.1%} of the {gauges.cpu_seconds / gauges.events * 1e6:.0f} us of CPU the runtime spent on each; "
        f"a metrics read p50 {statistics.median(reads) * 1000:.0f} ms, max {max(reads) * 1000:.0f} ms"
    )
    assert share <= COUNTING
    assert max(reads) <= METRICS_READ


def test_a_runtime_killed_at_scale_resumes_within_its_budget(measured: Measured):
    """A round cut by a SIGKILL of the runtime once half the members have begun it, then `Session.resume`: the seconds
    until the runtime it starts answers, and until every member's harness is back."""
    answered, back = measured.resumed
    print(f"resumed after a SIGKILL: answering in {answered:.1f} s, every member back in {back:.1f} s")
    assert answered <= RESUMED[0] and back <= RESUMED[1]
