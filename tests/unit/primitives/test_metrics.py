"""`session.metrics`, architecture section 16: counters that are folds and the kernel's gauges, each unknown wherever
nothing measured it, read by a person or a program and never an agent."""

import shutil
from collections import Counter
from fnmatch import fnmatchcase

import pytest

from platoon_harness import Refused, Session
from platoon_harness.kernel import Kernel, ManualClock, registry, writer
from platoon_harness.kernel.view import tables_of
from platoon_harness.primitives import PRIMITIVES, Counters, Metrics
from platoon_harness.testing import Say
from platoon_harness.topology import compile

from ..runtime import support as running
from ..topology.support import PRESET_TEAMS
from .support import channel, events_of, refusal, report, result_of, send, spawn, start_turn

GROUPS = ("needs_you", "working", "blocked", "idle", "done", "failed")


def metrics(kernel: Kernel) -> Metrics:
    return Metrics.model_validate(result_of(kernel.query(kernel.runtime, "session.metrics", {})))


async def test_counters_are_folds_that_add_no_journal_write(kernel, ada):
    """Every event is counted by its type and every journaled refusal by its code, as each commits, and reading them
    writes nothing: the counts are a view's tables, which refold to the same."""
    alice = await spawn(kernel, "alice")
    await send(kernel, alice, "@ada", "hello")
    await channel(kernel, "work", kind="queue")
    assert refusal(await kernel.submit(alice, "task.claim", {"queue": "work"})).code == "queue_empty"
    assert refusal(await kernel.submit(alice, "agent.retire", {"agent": "nobody"})).code == "not_found"

    found = metrics(kernel)
    again = metrics(kernel)
    await kernel.rebuild(Counters)
    rebuilt = metrics(kernel)

    journal = events_of(kernel)
    assert found.events == dict(sorted(Counter(event.type for event in journal).items()))
    assert found.refused == {"not_found": 1, "queue_empty": 1}
    assert sum(found.events.values()) == found.head == again.head == rebuilt.head == kernel.head
    assert (found.events, found.refused) == (rebuilt.events, rebuilt.refused)
    assert Counters in next(extension for extension in PRIMITIVES if extension.name == "session").views
    assert set(tables_of(Counters)) == {"v_counters", "v_counters_refused"}


async def test_a_metric_nothing_measured_is_unknown_never_zero(kernel, folder, tmp_path, monkeypatch):
    """No gauge before the runtime answered a write, none where the system cannot say, and none at all with no runtime,
    each named with why; what an agent's harness uses is never measured."""
    fresh = Kernel.open(tmp_path / "fresh", clock=ManualClock(1.0), extensions=PRIMITIVES)
    unanswered = metrics(fresh)
    fresh.close()
    monkeypatch.setattr(writer, "_peak_resident_bytes", lambda: None)
    unsaid = metrics(kernel)
    kernel.close()
    shutil.copytree(folder, tmp_path / "copy")
    closed = Kernel.open(tmp_path / "copy", extensions=PRIMITIVES, read_only=True)
    unheld = metrics(closed)
    closed.close()

    gauges = unanswered.gauges
    assert gauges is not None and gauges.acks == 0
    assert gauges.ack_p50 is gauges.ack_p99 is gauges.ack_max is None
    assert set(unanswered.unknown) == {"ack_latency", "harness_resources"}
    assert unsaid.gauges is not None and unsaid.gauges.acks > 0 and unsaid.gauges.peak_resident_bytes is None
    assert set(unsaid.unknown) == {"peak_resident_bytes", "harness_resources"}
    assert unheld.gauges is None and set(unheld.unknown) == {"gauges", "harness_resources"}
    assert unheld.events == unsaid.events and unheld.head == unsaid.head
    assert all(why for why in (*unanswered.unknown.values(), *unheld.unknown.values()))


async def test_active_and_blocked_agents_are_the_roster_s_groups(kernel, ada):
    """Each agent counts once, in the group the roster draws it in, and a group nobody stands in is a counted zero."""
    await spawn(kernel, "idle", goal="")
    await spawn(kernel, "busy")
    await start_turn(kernel, "busy")
    await spawn(kernel, "asking")
    await kernel.submit(kernel.runtime, "approval.request", {"id": "a1", "agent": "asking", "gist": "may I"})
    holding = await spawn(kernel, "holding", goal="")
    await channel(kernel, "work", kind="queue")
    await kernel.submit(kernel.runtime, "task.add", {"queue": "work", "gist": "x"})
    result_of(await kernel.submit(holding, "task.claim", {"queue": "work"}))
    talking = await spawn(kernel, "talking", goal="")
    await send(kernel, talking, "@ada", "got a minute?")
    await spawn(kernel, "lost")
    await report(kernel, "lost", "exited", reason="the harness crashed")

    found = metrics(kernel).agents
    rows = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))["rows"]

    assert found == {group: Counter(row["group"] for row in rows)[group] for group in GROUPS}
    assert found == {"needs_you": 1, "working": 1, "blocked": 1, "idle": 2, "done": 0, "failed": 1}


async def test_metrics_on_a_view_credential_write_nothing(tmp_path):
    """A view link reads the metrics as the owner does, its runtime's gauges among them, and the reading writes
    nothing."""
    team = running.solo([Say("on it")])
    async with Session.start(team, name="s", root=tmp_path, clock=ManualClock(1000.0)) as session:
        await running.in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await running.until(lambda: running.of_type(session, "turn.ended"), session)
        await running.in_state(session, "bob", "idle")
        owned = await session.metrics()
        async with Session.attach("s", root=tmp_path, view=True) as viewer:
            viewed = await viewer.metrics()
            with pytest.raises(Refused) as refused:
                await viewer.send("@bob", "a view link cannot say this")
        after = await session.head()

    assert viewed.head == owned.head == after
    assert (viewed.events, viewed.refused, viewed.agents) == (owned.events, owned.refused, owned.agents)
    assert viewed.gauges is not None and viewed.gauges.acks > 0 and "gauges" not in viewed.unknown
    assert refused.value.refusal.code == "not_permitted"


async def test_no_agent_holds_a_grant_for_metrics(kernel, ada):
    """No grant any preset compiles reaches it for an agent, no tool shows it, and it refuses an agent whatever its
    grants, as this session's grant every op to every agent."""
    alice = await spawn(kernel, "alice")

    for name, team in PRESET_TEAMS.items():
        reaching = [
            g for g in compile(team) if g.who not in ("human", "program") and fnmatchcase("session.metrics", g.ops)
        ]
        assert reaching == [], name
    operation = registry(PRIMITIVES)["session.metrics"]
    assert operation.query and not operation.tool
    assert refusal(kernel.query(alice, "session.metrics", {})).code == "not_permitted"
    assert result_of(kernel.query(ada, "session.metrics", {}))["head"] == kernel.head
