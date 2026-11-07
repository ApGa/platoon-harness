"""`propagate@3`: an episode's team reward split back along the record's own edges and what each span took, and kept per
agent and per span, on an ended session, by a named producer at a version, and never a fact."""

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from platoon_harness import Refused, Session, Team, credit
from platoon_harness.annotations import Annotation, Status
from platoon_harness.config import Manifest
from platoon_harness.credit import PROPAGATE, propagate
from platoon_harness.kernel import Kernel, ManualClock, Principal
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, SpawnRequest
from platoon_harness.runtime.paths import MANIFEST
from platoon_harness.testing import AskModel, Call, FakeModel, Say, ToolCall

from ..primitives import support as driven
from .support import SECONDS, Gateways, in_state, of_type, scripted, until

pytestmark = pytest.mark.timeout(60)

PROGRAM = "program:trainer"


def sends(to: str, cites: str) -> Call:
    return Call("message_send", {"to": to, "gist": f"to {to}, on {cites}", "based_on": [cites]})


async def ended(tmp_path, roles: dict[str, Sequence[Sequence[Any]]], messages: int, closing: Sequence[str]) -> Session:
    """A session of scripted agents that message each other once the program writes to `@alice`, closed, as a training
    system leaves one, once `messages` were sent and its episode closed on `closing`; and the same, attached."""
    edges = {name: ["all"] for name in roles}
    harnesses = {name: {"harness": scripted(*turns)} for name, turns in roles.items()}
    team = Team.model_validate({"roles": harnesses, "topology": {"edges": edges, "limits": {"max_hops": 16}}})
    async with Session.start(team, name="s", root=tmp_path, principal=PROGRAM) as session:
        for name in roles:
            await in_state(session, name, "idle")
        await session.open_episode("e")
        await session.send("@alice", "begin")
        await until(lambda: of_type(session, "message.sent"), session, lambda found: len(found) == messages)
        for name in roles:
            await in_state(session, name, "idle")
        await session.close_episode(based_on=closing)
        await session.close()
    return await Session.attach("s", root=tmp_path)


async def rewarded(session: Session, *statuses: tuple[Status, float | None]) -> None:
    """The team reward, as a training system writes it on the episode's close."""
    head = await session.head()
    for number, (status, value) in enumerate(statuses):
        await session.annotate(
            "episode/e@2",
            kind="reward",
            producer="environment",
            producer_version=str(number),
            scope="team",
            status=status,
            value=value,
            head_seq=head,
        )


async def credited(session: Session) -> dict[str, Annotation]:
    """Each agent's row `propagate` wrote, by the agent whose first start it targets."""
    rows = {}
    for row in await session.annotations():
        target = (await session.lineage(row.target)).event
        if row.producer == PROPAGATE and target.type == "agent.started":
            rows[target.agent or ""] = row
    return rows


async def spanned(session: Session) -> dict[str, Annotation]:
    """Each span's row `propagate` wrote, by the span's name, the `model.called` of its last call, which it targets."""
    rows = {}
    for row in await session.annotations():
        if row.producer == PROPAGATE and (await session.lineage(row.target)).event.type == "model.called":
            rows[row.target] = row
    return rows


def values(rows: dict[str, Annotation]) -> dict[str, float | None]:
    return {agent: row.value for agent, row in rows.items()}


CHAIN = {"alice": [[sends("@bob", "inbox/alice@1")]], "bob": [[sends("@alice", "inbox/bob@1")]]}
"""The program writes to alice, who writes to bob on it, who writes back on that: the episode closes on bob's."""


async def test_propagate_conserves_the_reward_over_agents_and_nobody(tmp_path):
    """Bob keeps half of the reward, alice half of the rest, and what reaches the program's message stays nobody's:
    the agents' rows and that unassigned share add up to the reward."""
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    rows = await credited(session)
    assert values(rows) == {"bob": 0.5, "alice": 0.25}
    unassigned = 1.0 - sum(row.value or 0.0 for row in rows.values())
    assert unassigned == 0.25 and (await session.lineage("inbox/alice@1")).made.maker == PROGRAM
    assert {row.status for row in rows.values()} == {"scored"}
    assert {(row.kind, row.scope, row.producer_version) for row in rows.values()} == {("credit", "local", "3")}


async def test_propagation_sums_reconverging_paths_once(tmp_path):
    """Alice's message is reached from the close and through bob's, and keeps its share of both, once."""
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2", "inbox/bob@1"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    rows = await credited(session)
    assert values(rows) == {"bob": 0.25, "alice": 0.375}
    assert rows["alice"].evidence == ("inbox/bob@1",)


async def test_propagation_keeps_retained_credit_local(tmp_path):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 2.0))

    await propagate(session, "e", judge=None, retained=0.25)

    assert values(await credited(session)) == {"bob": 0.5, "alice": 0.375}


async def test_propagation_ends_on_a_ring_of_citations(tmp_path):
    """Alice and bob answer each other twice, each on the last: a ring between agents, and a path back in time."""
    roles = {
        "alice": [[sends("@bob", "inbox/alice@1")], [sends("@bob", "inbox/alice@2")]],
        "bob": [[sends("@alice", "inbox/bob@1")], [sends("@alice", "inbox/bob@2")]],
    }
    session = await ended(tmp_path, roles, 5, ["inbox/alice@3"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    rows = await credited(session)
    assert values(rows) == {"bob": 0.5 + 0.125, "alice": 0.25 + 0.0625}
    assert rows["bob"].evidence == ("inbox/alice@3", "inbox/alice@2")


async def test_propagation_never_moves_credit_along_an_unseen_citation_or_a_handed_only_edge(tmp_path):
    """Bob was handed alice's message and cites none of it, and cites the program's message to alice, which he was
    never handed: neither is an edge, so bob keeps everything and alice is never reached."""
    roles = {
        "alice": [[Call("message_send", {"to": "@bob", "gist": "handed"})]],
        "bob": [[sends("@alice", "inbox/alice@1")]],
    }
    session = await ended(tmp_path, roles, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    cited = (await session.lineage("inbox/alice@2")).declared[0]
    assert cited.exposure is not None and cited.exposure.answer != "seen"
    assert values(await credited(session)) == {"bob": 1.0}


async def test_propagation_leaves_an_unreached_agent_unscored(tmp_path):
    roles = {**CHAIN, "carol": [[Call("message_send", {"to": "@alice", "gist": "unrelated"})]]}
    session = await ended(tmp_path, roles, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    assert set(await credited(session)) == {"alice", "bob"}


async def test_propagation_refuses_several_team_rewards(tmp_path):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0), ("scored", 0.5))

    with pytest.raises(Refused, match="2 team rewards") as refused:
        await propagate(session, "e", judge=None, retained=0.5)

    assert refused.value.refusal.code == "conflict" and await credited(session) == {}


async def test_propagation_refuses_a_reward_on_an_episode_that_closed_on_no_ref(tmp_path):
    """Its reward would reach nobody's event, so every agent would be unscored for nothing it did: that is said."""
    session = await ended(tmp_path, CHAIN, 3, [])
    await rewarded(session, ("scored", 1.0))

    with pytest.raises(Refused, match="closed on no ref") as refused:
        await propagate(session, "e", judge=None, retained=0.5)

    assert refused.value.refusal.code == "invalid" and await credited(session) == {}


async def test_propagation_with_no_team_reward_writes_nothing_and_refuses_a_share_past_one(tmp_path):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])

    await propagate(session, "e", judge=None, retained=0.5)
    with pytest.raises(Refused, match="from 0 to 1"):
        await propagate(session, "e", judge=None, retained=1.5)

    assert await session.annotations() == []


async def test_an_agents_credit_targets_its_first_start_never_its_spawn(tmp_path):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    for agent, row in (await credited(session)).items():
        target = (await session.lineage(row.target)).event
        events = session.events(streams=[f"agent/{agent}"])
        started = [event.seq async for event in events if event.type == "agent.started"]
        assert (target.type, target.seq) == ("agent.started", started[0])
        assert row.target != f"agent/{agent}@1"


async def tree(tmp_path, name: str, on: str) -> tuple[dict[str, str], dict[str, float | None]]:
    """A root that does not stay and the child it waits on, each ended with its turn, and the episode closed on each
    one's `said` or on its last message: the refs it closed on, and the credit of each."""
    spawned = Call("agent_spawn", {"name": "kid", "child_role": "helper", "goal": "craft three"})
    crafter = [[spawned, Call("wait", {"agents": ["@kid"], "timeout": 1200})], [Say("all three are crafted")]]
    roles = {
        "crafter": {"harness": scripted(*crafter), "stays": False, "may_spawn": ["helper"]},
        "helper": {"harness": scripted([Say("the ingredient chain")]), "count": 0},
    }
    topology = {"edges": {"crafter": ["children"]}, "until": "role:crafter"}
    team = Team.model_validate({"roles": roles, "topology": topology})
    clock = ManualClock(1000.0)
    async with Session.start(team, name=name, root=tmp_path, clock=clock, principal=PROGRAM) as session:
        await session.open_episode("e")
        await session.send("@crafter", "craft three")
        await asyncio.wait_for(session.settled(), SECONDS)
        said = {row["agent"]: row["said"] for row in await session.agents()}
        messages = [event for event in await of_type(session, "item.recorded") if event.data["kind"] == "message"]
        closing = said if on == "said" else {event.agent: f"{event.stream}@{event.version}" for event in messages}
        await session.close_episode(based_on=list(closing.values()))
    attached = await Session.attach(name, root=tmp_path)
    await rewarded(attached, ("scored", 1.0))
    await propagate(attached, "e", judge=None, retained=0.5)
    return closing, values(await credited(attached))


async def test_a_tree_that_does_not_stay_credits_each_agent_alike_on_its_said_or_its_last_message(tmp_path):
    """Each ends with a turn whose last words are its report, so its `said` is what its end carries, that turn's last
    message, which follows from nothing and cites nothing, and each agent keeps all its ref was handed, the child as
    the root."""
    on_said, by_said = await tree(tmp_path, "said", "said")
    on_last, by_last = await tree(tmp_path, "last", "last")

    assert {ref.partition("@")[0] for ref in on_said.values()} == {"turn/crafter", "turn/kid"}
    assert on_said == on_last
    assert by_said == by_last == {"crafter": 0.5, "kid": 0.5}


# Spans, on a journal driven op by op as drivers and a runtime drive one.


async def journal(tmp_path: Path) -> Kernel:
    """A program's session, its episode open, driven op by op in the folder `Session.attach` finds."""
    folder = tmp_path / "root" / "sessions" / "s"
    folder.mkdir(parents=True)
    manifest = Manifest(team="{}", topology_hash="", components=(), principal=PROGRAM)
    (folder / MANIFEST).write_text(manifest.model_dump_json())
    kernel = Kernel.open(folder, clock=ManualClock(1000.0), extensions=PRIMITIVES)
    driven.result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": driven.ROLES}))
    await driven.enroll(kernel, Principal(id=PROGRAM))
    await driven.grant(kernel, "agent")
    await driven.grant(kernel, "program")
    driven.result_of(await kernel.submit(kernel.runtime, "episode.open", {"episode": "e"}))
    return kernel


async def propagated(
    kernel: Kernel, tmp_path: Path, closing: Sequence[str], *statuses: tuple[Status, float | None]
) -> Session:
    """Close the episode on `closing` and leave the journal, then reward it, `scored` 1.0 unless `statuses` say, and
    propagate, as a training system does once a session has ended."""
    driven.result_of(await kernel.submit(kernel.runtime, "episode.close", {"based_on": list(closing)}))
    kernel.close()
    session = await Session.attach("s", root=tmp_path / "root")
    await rewarded(session, *(statuses or [("scored", 1.0)]))
    await propagate(session, "e", judge=None, retained=0.5)
    return session


async def called(kernel: Kernel, name: str, call_id: str) -> str:
    """A model call `name`'s harness reports, by the ref of its `model.called`."""
    await driven.report(kernel, name, "model.call", call_id=call_id)
    found = driven.of_type(kernel, "model.called")[-1]
    return f"{found.stream}@{found.version}"


async def ran(
    kernel: Kernel, name: str, call_id: str | None, op: str, args: dict[str, Any], *, tool: str | None = None
) -> dict[str, Any]:
    """An op `name` runs by the tool call `tool` its model call `call_id` chose, after the tool item its harness reports
    of that tool call, or with no `call_id` by none."""
    if call_id is None:
        return driven.result_of(await kernel.submit(driven.agent(name), op, args))
    tool = tool or f"tool-{len(driven.of_type(kernel, 'item.recorded'))}"
    await driven.report(kernel, name, "item", kind="tool", phase="started", gist=op, native_id=tool, call_id=call_id)
    return driven.result_of(await kernel.submit(driven.agent(name), op, args, native={"claudecode/toolUseId": tool}))


async def returned(kernel: Kernel, name: str, tool: str) -> None:
    """A tool item came back `completed`, holding what its call returned, which confirms a read made under it."""
    item = {"kind": "tool", "phase": "completed", "gist": "a tool", "native_id": tool, "outcome": "completed"}
    await driven.report(kernel, name, "item", **item)


async def woken(kernel: Kernel, name: str, turn: str = "t1") -> None:
    """`name` is handed what waits for it, its harness says it took it, and a turn begins on it."""
    offer = driven.result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": name}))
    await driven.confirm(kernel, name, offer["input"], evidence="message_start")
    await driven.start_turn(kernel, name, turn)


async def sent(kernel: Kernel, name: str, call_id: str | None, to: str, **fields: Any) -> str:
    """A message `name` sends by a tool call of its model call `call_id`: its ref."""
    return (await ran(kernel, name, call_id, "message.send", {"to": to, "gist": f"to {to}", **fields}))["ref"]


async def worked(kernel: Kernel) -> dict[str, str]:
    """The program writes to `w`, which answers `peer` in one model call, `peer` answers it, and `w` answers that in a
    second, then makes a third: `w`'s turn is two spans, `[c1]` and `[c2, c3]`, and its answer is the last."""
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "w")
    program = Principal(id=PROGRAM)
    begun = driven.result_of(await kernel.submit(program, "message.send", {"to": "@w", "gist": "begin"}))["ref"]
    await driven.start_turn(kernel, "w")
    c1 = await called(kernel, "w", "c1")
    first = await sent(kernel, "w", "c1", "@peer", reply_to=begun)
    answer = (await driven.send(kernel, driven.agent("peer"), "@w", "and so", reply_to=first))["ref"]
    await called(kernel, "w", "c2")
    last = await sent(kernel, "w", "c2", "@peer", reply_to=answer)
    c3 = await called(kernel, "w", "c3")
    await driven.end_turn(kernel, "w")
    return {"begun": begun, "c1": c1, "first": first, "answer": answer, "last": last, "c3": c3}


async def test_propagate_keeps_each_events_share_for_the_span_holding_the_call_that_made_it(tmp_path):
    """`w`'s last message keeps half of the reward for the span of the call that sent it, `peer`'s answer a quarter, and
    `w`'s first message an eighth for its own span, passing the rest to the program's: each span's row targets its last
    call's `model.called`."""
    kernel = await journal(tmp_path)
    refs = await worked(kernel)

    session = await propagated(kernel, tmp_path, [refs["last"]])

    agents, spans = await credited(session), await spanned(session)
    assert values(agents) == {"w": 0.625, "peer": 0.25}
    assert {target: (row.value, row.evidence) for target, row in spans.items()} == {
        refs["c1"]: (0.125, (refs["first"],)),
        refs["c3"]: (0.5, (refs["last"],)),
    }
    assert {(row.kind, row.scope, row.producer_version) for row in spans.values()} == {("credit", "local", "3")}


async def test_a_span_propagate_never_reaches_gets_no_row(tmp_path):
    """Closed on `w`'s first message alone, its second span is never reached, so it has no row, which is unscored and
    not zero."""
    kernel = await journal(tmp_path)
    refs = await worked(kernel)

    session = await propagated(kernel, tmp_path, [refs["first"]])

    assert {target: row.value for target, row in (await spanned(session)).items()} == {refs["c1"]: 0.5}
    assert values(await credited(session)) == {"w": 0.5}


async def test_a_walk_cut_short_makes_every_row_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(credit, "WALK_LIMIT", 1)
    kernel = await journal(tmp_path)
    refs = await worked(kernel)

    session = await propagated(kernel, tmp_path, [refs["last"]])

    rows = {**(await credited(session)), **(await spanned(session))}
    assert {key: (row.status, row.value) for key, row in rows.items()} == {
        "w": ("invalid", None),
        refs["c3"]: ("invalid", None),
    }


@pytest.mark.parametrize("status", ["invalid", "error", "timeout", "cancelled"])
async def test_a_team_reward_not_scored_passes_its_status_to_every_row(tmp_path, status):
    kernel = await journal(tmp_path)
    refs = await worked(kernel)

    session = await propagated(kernel, tmp_path, [refs["last"]], (status, None))

    rows = {**(await credited(session)), **(await spanned(session))}
    assert set(rows) == {"w", "peer", refs["c1"], refs["c3"]}
    assert {(row.status, row.value) for row in rows.values()} == {(status, None)}


async def reported(kernel: Kernel, lead: str, *, spans: int) -> dict[str, str]:
    """`kid`, spawned by `lead`, sends `lead` a message in one model call, unless it works in one `spans` span, and
    finishes with a report in the next, so `lead` is handed a report of it, the runtime's entry about it that carries
    its `agent.finished`; then `lead` answers that entry on a topic."""
    await driven.channel(kernel, "log", kind="topic")
    await driven.spawn(kernel, "kid", by=driven.agent(lead))
    await driven.start_turn(kernel, "kid")
    await called(kernel, "kid", "k1")
    if spans == 2:
        await sent(kernel, "kid", "k1", f"@{lead}")
        await called(kernel, "kid", "k2")
    finished = (await ran(kernel, "kid", f"k{spans}", "agent.finish", {"gist": "made it"}))["ref"]
    await driven.end_turn(kernel, "kid")
    entry = driven.of_type(kernel, "message.sent")[-1]
    assert (entry.actor, entry.agent, entry.data["carries"]) == ("runtime", "kid", finished)
    answer = (await driven.send(kernel, driven.agent(lead), "#log", "noted", reply_to=finished))["ref"]
    return {"finished": finished, "entry": f"{entry.stream}@{entry.version}", "answer": answer}


async def test_an_entry_that_carries_an_event_lies_where_that_event_lies(tmp_path):
    """The runtime's entry that reports `kid`'s finish to `lead` is `kid`'s, tied to no call and made in a turn of two
    spans, and lies where the finish it carries lies, in the span of the call that chose it."""
    kernel = await journal(tmp_path)
    await driven.spawn(kernel, "lead", role="lead")
    refs = await reported(kernel, "lead", spans=2)

    session = await propagated(kernel, tmp_path, [refs["answer"]])

    [kid] = [row for row in (await spanned(session)).values()]
    assert (kid.value, kid.evidence) == (0.5, (refs["entry"], refs["finished"]))
    assert (await session.lineage(kid.target)).event.agent == "kid"
    assert values(await credited(session)) == {"lead": 0.5, "kid": 0.5}


async def test_an_entry_that_carries_an_event_takes_nothing_of_its_own(tmp_path):
    """`kid` finished by its first call and read `peer`'s message after, in the same span: the runtime's entry that
    reports the finish to `lead` repeats the finish's words, so it passes all it hands on to the finish, which took
    nothing below its bound, and nothing to `peer`, whose message the reported words never saw."""
    kernel = await journal(tmp_path)
    await driven.channel(kernel, "log", kind="topic")
    lead = await driven.spawn(kernel, "lead", role="lead")
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "kid", by=lead)
    await driven.send(kernel, driven.agent("peer"), "@kid", "and also")
    await driven.start_turn(kernel, "kid")
    await called(kernel, "kid", "k1")
    finished = (await ran(kernel, "kid", "k1", "agent.finish", {"gist": "made it"}))["ref"]
    await ran(kernel, "kid", "k1", "message.read", {}, tool="read")
    await returned(kernel, "kid", "read")
    named = await called(kernel, "kid", "k2")
    await driven.end_turn(kernel, "kid")
    entry = driven.of_type(kernel, "message.sent")[-1]
    answer = (await driven.send(kernel, lead, "#log", "noted", reply_to=finished))["ref"]

    session = await propagated(kernel, tmp_path, [answer])

    assert values(await credited(session)) == {"lead": 0.5, "kid": 0.5}
    assert {target: (row.value, row.evidence) for target, row in (await spanned(session)).items()} == {
        named: (0.5, (f"{entry.stream}@{entry.version}", finished))
    }


async def test_a_taken_report_of_a_failed_spawn_credits_the_rest_of_the_episode(tmp_path):
    """`kid`'s launch failed, so it never started, and `lead`'s answer took the report of its end, shown by that end:
    an agent with no start has nothing for a row to target, so the half its end keeps is in no row, as nobody's is,
    and `lead`'s answer keeps its half for `lead` and its span."""
    kernel = await journal(tmp_path)
    await driven.channel(kernel, "log", kind="topic")
    await driven.spawn(kernel, "lead", role="lead")
    await driven.start_turn(kernel, "lead")
    await called(kernel, "lead", "c1")
    await ran(kernel, "lead", "c1", "agent.spawn", {"name": "kid", "child_role": "worker", "goal": "be kid"})
    [launch] = driven.result_of(kernel.query(kernel.runtime, "effect.ready", {}))
    attempt = driven.result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": launch["id"]}))
    failing = {"id": launch["id"], "attempt": attempt, "error": "refused"}
    driven.result_of(await kernel.submit(kernel.runtime, "effect.fail", failing))
    gone = {"agent": "kid", "report": {"type": "exited", "reason": "its launch failed"}}
    driven.result_of(await kernel.submit(kernel.runtime, "agent.report", gone))
    ended = driven.of_type(kernel, "agent.ended")[-1]
    await called(kernel, "lead", "c2")
    await ran(kernel, "lead", "c2", "message.read", {}, tool="read")
    await returned(kernel, "lead", "read")
    answering = await called(kernel, "lead", "c3")
    answer = await sent(kernel, "lead", "c3", "#log")
    await driven.end_turn(kernel, "lead")

    session = await propagated(kernel, tmp_path, [answer])

    assert (ended.agent, ended.data["status"]) == ("kid", "failed")
    assert values(await credited(session)) == {"lead": 0.5}
    assert {target: row.value for target, row in (await spanned(session)).items()} == {answering: 0.5}


async def test_an_agent_whose_every_kept_event_lies_in_its_one_span_gets_a_span_row_equal_to_its_agent_row(tmp_path):
    """`lead` answers the report of `kid`, whose one span chose its finish: the report and the finish both lie there."""
    kernel = await journal(tmp_path)
    await driven.spawn(kernel, "lead", role="lead")
    refs = await reported(kernel, "lead", spans=1)

    session = await propagated(kernel, tmp_path, [refs["answer"]])

    [span] = (await spanned(session)).values()
    kid = (await credited(session))["kid"]
    assert (
        (span.value, span.status, span.evidence)
        == (kid.value, kid.status, kid.evidence)
        == (
            0.5,
            "scored",
            (refs["entry"], refs["finished"]),
        )
    )


async def test_an_event_tied_to_no_call_lies_in_its_turn_only_when_the_turn_is_one_span(tmp_path):
    """A message whose op came under no tool call lies in its turn's one span, and in a turn cut in two it lies in none:
    what it kept is its agent's and no span's."""
    kernel = await journal(tmp_path)
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "w")
    await driven.start_turn(kernel, "w", "t1")
    whole = await called(kernel, "w", "c1")
    one = await sent(kernel, "w", None, "@peer")
    await driven.end_turn(kernel, "w")
    await driven.start_turn(kernel, "w", "t2")
    await called(kernel, "w", "c2")
    await sent(kernel, "w", "c2", "@peer")
    await called(kernel, "w", "c3")
    await sent(kernel, "w", "c3", "@peer")
    two = await sent(kernel, "w", None, "@peer")
    await driven.end_turn(kernel, "w")

    session = await propagated(kernel, tmp_path, [one, two])

    assert {target: (row.value, row.evidence) for target, row in (await spanned(session)).items()} == {
        whole: (0.5, (one,))
    }
    assert (await credited(session))["w"].evidence == (two, one)
    assert values(await credited(session)) == {"w": 1.0}


moves = st.lists(
    st.tuples(
        st.sampled_from(["send", "send", "revise", "wake", "wake", "turn"]),
        st.sampled_from(["a", "b", "a", "b", "trainer"]),
        st.booleans(),
        st.booleans(),
        st.integers(0, 2),
    ),
    min_size=3,
    max_size=16,
)
"""What two agents, each in a turn to begin with, and the program do: a turn ended or begun; a turn ended, if one was
under way, and the next begun on what waits, which no harness says it took, so no span takes anything; or a message or
a board entry's next version, after a model call or not, by the agent's latest call or by none, citing what was sent to
its writer, and answering it."""


async def played(kernel: Kernel, script: list[tuple[Any, ...]]) -> list[str]:
    """Each move of `script`, after the program's first message to `a`: the refs of what was written, oldest first."""
    await driven.channel(kernel, "notes", kind="board")
    await driven.spawn(kernel, "a")
    await driven.spawn(kernel, "b")
    program = Principal(id=PROGRAM)
    written = [driven.result_of(await kernel.submit(program, "message.send", {"to": "@a", "gist": "begin"}))["ref"]]
    inbox: dict[str, list[str]] = {"a": written[:1], "b": [], "trainer": written[:1]}
    calls: dict[str, str] = {}
    turns = {"a": True, "b": True}
    for name in turns:
        await driven.start_turn(kernel, name, f"{name}-0")
    for number, (move, name, calling, joined, back) in enumerate(script, 1):
        if move in ("turn", "wake") and name == "trainer":
            continue
        if move == "turn":
            turns[name] = not turns[name]
            await (
                driven.start_turn(kernel, name, f"{name}-{number}") if turns[name] else driven.end_turn(kernel, name)
            )
        elif move == "wake":
            if turns[name]:
                await driven.end_turn(kernel, name)
            await kernel.submit(kernel.runtime, "delivery.offer", {"agent": name})
            await driven.start_turn(kernel, name, f"{name}-{number}")
            turns[name] = True
        else:
            if calling and name != "trainer":
                calls[name] = f"c{number}"
                await called(kernel, name, calls[name])
            call = calls.get(name) if joined else None
            cites = inbox[name][-1 - back :][:1]
            if move == "send":
                to = "b" if name == "a" else "a"
                fields: dict[str, Any] = {"based_on": cites, "reply_to": inbox[name][-1] if inbox[name] else None}
                if name == "trainer":
                    found = await kernel.submit(program, "message.send", {"to": f"@{to}", "gist": "go", **fields})
                    ref = driven.result_of(found)["ref"]
                else:
                    ref = await sent(kernel, name, call, f"@{to}", **fields)
                inbox[to].append(ref)
            else:
                versions = len([ref for ref in written if ref.startswith("board/")])
                entry = {"board": "notes", "name": "spec", "gist": "next", "based_on": cites}
                op = "board.revise" if versions else "board.post"
                if versions:
                    entry["expected_version"] = versions
                ref = (await ran(kernel, "a" if name == "trainer" else name, call, op, entry))["ref"]
            written.append(ref)
    return written


async def walked_by_propagate_1(session: Session) -> tuple[dict[str, float], dict[str, str | None]]:
    """What each event `propagate@1` reached kept of a reward of 1 at `retained` 0.5, and who made it: RFC 0054's rule
    taken over the journal newest first, each event once, as every edge points to an older event."""
    reaching: dict[str, float] = defaultdict(float)
    closing = (await session.lineage("episode/e@2")).declared
    for cited in closing:
        reaching[cited.ref.partition("#")[0]] += 1 / len(closing)
    kept: dict[str, float] = {}
    makers: dict[str, str | None] = {}
    for event in reversed([event async for event in session.events()]):
        ref = f"{event.stream}@{event.version}"
        if ref not in reaching:
            continue
        found = await session.lineage(ref)
        edges = [step.ref for step in (*found.cause, *found.ancestry) if step.ref is not None]
        edges += [d.ref.partition("#")[0] for d in found.declared if d.exposure is None or d.exposure.answer == "seen"]
        kept[ref], makers[ref] = reaching[ref] * 0.5 if edges else reaching[ref], found.made.maker
        for edge in edges:
            reaching[edge] += (reaching[ref] - kept[ref]) / len(edges)
    return kept, makers


async def propagated_play(
    tmp_path: Path, script: list[tuple[Any, ...]]
) -> tuple[Session, dict[str, float], dict[str, str | None]]:
    """The journal `script` plays, closed on its last two writes and propagated, and what each event `propagate@1`
    reached kept, and who made it."""
    kernel = await journal(tmp_path)
    written = await played(kernel, script)
    session = await propagated(kernel, tmp_path, written[-2:])
    return session, *(await walked_by_propagate_1(session))


@settings(max_examples=25, deadline=None)
@given(script=moves)
def test_propagate_3_writes_propagate_2s_rows_where_no_span_took_another_principals_event(tmp_path_factory, script):
    """Where no span took anything, the rows are `propagate@2`'s: an agent's row is what its events kept on
    `propagate@1`'s walk, and a span's what its own events kept there."""

    async def body() -> None:
        session, kept, makers = await propagated_play(tmp_path_factory.mktemp("credit"), script)
        rows: dict[str, float] = defaultdict(float)
        for ref, share in kept.items():
            if (makers[ref] or "").startswith("agent:"):
                rows[(makers[ref] or "").removeprefix("agent:")] += share
        assert values(await credited(session)) == rows
        for span in (await spanned(session)).values():
            assert span.value == sum(kept[ref] for ref in span.evidence)
        await session.leave()

    asyncio.run(body())


@settings(max_examples=25, deadline=None)
@given(script=moves)
def test_each_agent_row_is_at_least_its_span_rows_and_the_rest_was_kept_in_no_span(tmp_path_factory, script) -> None:
    """Each span's row holds what its events kept on the walk, no event lies in two spans, and an agent's row is its
    spans' rows and what its events kept in no span."""

    async def body() -> None:
        session, kept, _ = await propagated_play(tmp_path_factory.mktemp("credit"), script)
        agents, spans = await credited(session), defaultdict[str, list[Annotation]](list)
        for row in (await spanned(session)).values():
            spans[(await session.lineage(row.target)).event.agent or ""].append(row)
        for name, row in agents.items():
            held = [ref for span in spans[name] for ref in span.evidence]
            assert len(held) == len(set(held)) and set(held) <= set(row.evidence)
            for span in spans[name]:
                assert span.value == sum(kept[ref] for ref in span.evidence)
            rest = [kept[ref] for ref in row.evidence if ref not in held]
            assert row.value == pytest.approx(sum(span.value or 0.0 for span in spans[name]) + sum(rest))
        assert set(spans) <= set(agents)
        await session.leave()

    asyncio.run(body())


QUEUE = {"kind": "queue", "writers": "all", "readers": "all", "delivery": "pull", "max_inflight": 2}


def claim(number: int) -> ToolCall:
    return ToolCall("task_claim", {"queue": "tasks"}, id=f"claim-{number}")


def complete(number: int) -> ToolCall:
    args = {"queue": "tasks", "task": str(number), "gist": f"task {number} done"}
    return ToolCall("task_complete", args, id=f"done-{number}")


async def worker(tmp_path: Path, *turns: Sequence[Any]) -> tuple[Session, list[str]]:
    """A persistent worker on ScriptedDriver, asking FakeModel as its gateway, does the three tasks the program added,
    a turn for each of `turns`, which are the model's replies in it, and the episode closes on the three results: the
    session as it ended, and each model call its harness reported."""
    roles = {"w": {"harness": scripted(*[[AskModel()]] * len(turns))}}
    team = Team.model_validate({"roles": roles, "topology": {"channels": {"tasks": QUEUE}}})
    model = FakeModel()
    start: dict[str, Any] = {"name": "queue", "root": tmp_path, "principal": PROGRAM, "authority": Gateways(model)}
    async with model, Session.start(team, **start) as session:
        await in_state(session, "w", "idle")
        await session.open_episode("e")
        for number in (1, 2, 3):
            await session.task_add("tasks", f"task {number}")
        for number, replies in enumerate(turns, 1):
            model.script(replies)
            await session.send("@w", "the tasks are open")
            await until(lambda: of_type(session, "turn.ended"), session, lambda found, n=number: len(found) == n)
            await in_state(session, "w", "idle")
        results = [f"{event.stream}@{event.version}" for event in await of_type(session, "task.completed")]
        calls = [f"{event.stream}@{event.version}" for event in await of_type(session, "model.called")]
        await session.close_episode(based_on=results)
        await session.close()
    attached = await Session.attach("queue", root=tmp_path)
    await rewarded(attached, ("scored", 1.0))
    await propagate(attached, "e", judge=None, retained=0.5)
    return attached, calls


def task(number: int) -> set[str]:
    """A task's claim and its result."""
    return {f"task/tasks/{number}@2", f"task/tasks/{number}@3"}


@pytest.mark.parametrize("turns", ["one", "three"])
async def test_a_persistent_worker_credits_each_task_to_the_span_whose_call_completed_it(tmp_path, turns):
    """The owner's case: a worker claims and completes three tasks, a model call for each step, in one turn or in a turn
    each. Each result keeps a sixth for the span of the call that completed it, and passes the rest to its claim, as its
    cause and its previous version, and to what that span took before it: the task its claim showed, and in a turn's
    first span the program's message that began the turn, each nobody's. Its claim keeps half of what reaches it, in the
    same span: a span holds 2/9, or 5/24 where it took the message."""
    if turns == "one":
        replies = [[claim(1), complete(1), claim(2), complete(2), claim(3), complete(3), "all three are done"]]
        ends, shares = (1, 3, 6), (5 / 24, 2 / 9, 2 / 9)
    else:
        replies = [[claim(number), complete(number), f"task {number} is done"] for number in (1, 2, 3)]
        ends, shares = (2, 5, 8), (5 / 24, 5 / 24, 5 / 24)

    session, calls = await worker(tmp_path, *replies)

    spans = await spanned(session)
    assert {target: (pytest.approx(row.value), set(row.evidence)) for target, row in spans.items()} == {
        calls[end]: (pytest.approx(share), task(number))
        for number, end, share in zip((1, 2, 3), ends, shares, strict=True)
    }
    assert values(await credited(session)) == {"w": pytest.approx(sum(shares))}


async def test_a_claim_made_in_the_call_that_completed_the_previous_task_gives_that_span_its_share(tmp_path):
    """One call completes the first task and claims the second: the second's claim lies in the first's span, which
    keeps the claim's share of the second's credit beside its own, 1/18 of 19/72."""
    replies = [claim(1), [complete(1), claim(2)], [complete(2), claim(3)], complete(3), "all three are done"]

    session, calls = await worker(tmp_path, replies)

    spans = await spanned(session)
    assert {target: (pytest.approx(row.value), set(row.evidence)) for target, row in spans.items()} == {
        calls[1]: (pytest.approx(19 / 72), task(1) | {"task/tasks/2@2"}),
        calls[2]: (pytest.approx(2 / 9), {"task/tasks/2@3", "task/tasks/3@2"}),
        calls[4]: (pytest.approx(1 / 6), {"task/tasks/3@3"}),
    }


async def test_two_claims_open_at_once_give_the_span_that_made_them_their_share(tmp_path):
    """One call claims two tasks, so the span holding it keeps both claims' share, 17/60 in all, and the second task's
    result its own sixth."""
    replies = [[claim(1), claim(2)], complete(1), complete(2), claim(3), complete(3), "all three are done"]

    session, calls = await worker(tmp_path, replies)

    spans = await spanned(session)
    assert {target: (pytest.approx(row.value), set(row.evidence)) for target, row in spans.items()} == {
        calls[1]: (pytest.approx(17 / 60), task(1) | {"task/tasks/2@2"}),
        calls[2]: (pytest.approx(1 / 6), {"task/tasks/2@3"}),
        calls[5]: (pytest.approx(2 / 9), task(3)),
    }


# Takes.


async def test_propagate_passes_credit_along_another_principals_event_its_span_took(tmp_path):
    """`w`'s harness took `peer`'s message as its turn began, and `w`'s answer, which cites nothing, keeps half for its
    span and passes half along that take."""
    kernel = await journal(tmp_path)
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "w")
    told = (await driven.send(kernel, driven.agent("peer"), "@w", "the plan"))["ref"]
    await woken(kernel, "w")
    named = await called(kernel, "w", "c1")
    answer = await sent(kernel, "w", "c1", "@peer")
    await driven.end_turn(kernel, "w")

    session = await propagated(kernel, tmp_path, [answer])

    agents = await credited(session)
    assert values(agents) == {"w": 0.5, "peer": 0.5} and agents["peer"].evidence == (told,)
    assert {target: (row.value, row.evidence) for target, row in (await spanned(session)).items()} == {
        named: (0.5, (answer,))
    }


async def test_propagate_passes_nothing_along_a_take_confirmed_after_the_events_bound(tmp_path):
    """One model call chose a read of `peer`'s message and an answer: the read's result came back after that call, so
    the answer took nothing, while the span's last words, said by the next call, took the message."""
    kernel = await journal(tmp_path)
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "w")
    told = (await driven.send(kernel, driven.agent("peer"), "@w", "the plan"))["ref"]
    await driven.start_turn(kernel, "w")
    await called(kernel, "w", "c1")
    await ran(kernel, "w", "c1", "message.read", {}, tool="read")
    answer = await sent(kernel, "w", "c1", "@peer")
    await returned(kernel, "w", "read")
    named = await called(kernel, "w", "c2")
    await driven.report(kernel, "w", "item", kind="message", gist="done", call_id="c2")
    said = driven.of_type(kernel, "item.recorded")[-1]
    await driven.end_turn(kernel, "w")

    session = await propagated(kernel, tmp_path, [answer, f"{said.stream}@{said.version}"])

    agents = await credited(session)
    assert values(agents) == {"w": 0.75, "peer": 0.25} and agents["peer"].evidence == (told,)
    assert {target: row.value for target, row in (await spanned(session)).items()} == {named: 0.75}


async def test_propagate_passes_nothing_along_a_take_of_its_own_agents_event(tmp_path):
    """`w` read back its own board entry before it answered: what it made is already its own, so that read is no take
    and the entry's span is never reached."""
    kernel = await journal(tmp_path)
    await driven.channel(kernel, "notes", kind="board")
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "w")
    await driven.start_turn(kernel, "w")
    await called(kernel, "w", "c1")
    await ran(kernel, "w", "c1", "board.post", {"board": "notes", "name": "plan", "gist": "the plan"})
    await called(kernel, "w", "c2")
    await ran(kernel, "w", "c2", "board.get", {"board": "notes", "name": "plan"}, tool="get")
    await returned(kernel, "w", "get")
    named = await called(kernel, "w", "c3")
    answer = await sent(kernel, "w", "c3", "@peer")
    await driven.end_turn(kernel, "w")

    session = await propagated(kernel, tmp_path, [answer])

    assert values(await credited(session)) == {"w": 1.0}
    assert {target: row.value for target, row in (await spanned(session)).items()} == {named: 1.0}


async def test_propagate_never_passes_credit_along_an_unconfirmed_offer(tmp_path):
    """`peer`'s message was offered to `w`, whose harness never said it took it: being handed something is no edge."""
    kernel = await journal(tmp_path)
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "w")
    await driven.send(kernel, driven.agent("peer"), "@w", "the plan")
    driven.result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "w"}))
    await driven.start_turn(kernel, "w")
    await called(kernel, "w", "c1")
    answer = await sent(kernel, "w", "c1", "@peer")
    await driven.end_turn(kernel, "w")

    session = await propagated(kernel, tmp_path, [answer])

    assert values(await credited(session)) == {"w": 1.0}


async def test_a_take_confirmed_before_its_agents_latest_start_or_resume_is_no_take(tmp_path):
    """`w`'s harness took `peer`'s message, then came back as a new process, which never held what the one before took:
    the call after is no take of it."""
    kernel = await journal(tmp_path)
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "w")
    await driven.send(kernel, driven.agent("peer"), "@w", "the plan")
    offer = driven.result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "w"}))
    await driven.confirm(kernel, "w", offer["input"], evidence="message_start")
    back = {"agent": "w", "ready": {}, "declared": {"persistent": True, "boundaries": ["turn"]}, "resumed": True}
    driven.result_of(await kernel.submit(kernel.runtime, "agent.start", back))
    await driven.start_turn(kernel, "w", "t2")
    await called(kernel, "w", "c1")
    answer = await sent(kernel, "w", "c1", "@peer")
    await driven.end_turn(kernel, "w")

    session = await propagated(kernel, tmp_path, [answer])

    assert values(await credited(session)) == {"w": 1.0}


async def test_a_take_counts_every_event_its_offer_showed_gist_or_body(tmp_path):
    """One read showed `peer`'s message by its gist and its body and `carol`'s by its gist: each is one take, so each
    gets an equal share of what `w`'s answer passed on."""
    kernel = await journal(tmp_path)
    for name in ("peer", "carol", "w"):
        await driven.spawn(kernel, name)
    body = f"sha256:{await kernel.put_body(b'the whole plan')}"
    await driven.send(kernel, driven.agent("peer"), "@w", "the plan", body=body)
    await driven.send(kernel, driven.agent("carol"), "@w", "a note")
    await driven.start_turn(kernel, "w")
    await called(kernel, "w", "c1")
    await ran(kernel, "w", "c1", "message.read", {"bodies": True}, tool="read")
    await returned(kernel, "w", "read")
    await called(kernel, "w", "c2")
    answer = await sent(kernel, "w", "c2", "@peer")
    await driven.end_turn(kernel, "w")
    read = driven.of_type(kernel, "context.offered")[-1]

    session = await propagated(kernel, tmp_path, [answer])

    assert sorted(item["form"] for item in read.data["items"]) == ["body", "gist", "gist"]
    assert values(await credited(session)) == {"w": 0.5, "peer": 0.25, "carol": 0.25}


async def test_a_take_newer_than_its_event_makes_every_row_invalid(tmp_path):
    """`w`'s answer committed before its harness reported the call that chose it, and before that report a read under
    the same call showed a message sent after the answer: a take that points forward, which the walk refuses rather
    than lose what it passes."""
    kernel = await journal(tmp_path)
    await driven.spawn(kernel, "peer")
    await driven.spawn(kernel, "w")
    await driven.start_turn(kernel, "w")
    answer = await sent(kernel, "w", "c1", "@peer")
    await driven.send(kernel, driven.agent("peer"), "@w", "and then")
    await ran(kernel, "w", "c1", "message.read", {}, tool="read")
    await returned(kernel, "w", "read")
    named = await called(kernel, "w", "c1")
    await driven.end_turn(kernel, "w")

    session = await propagated(kernel, tmp_path, [answer])

    rows = {**(await credited(session)), **(await spanned(session))}
    assert {key: (row.status, row.value) for key, row in rows.items()} == {
        "w": ("invalid", None),
        named: ("invalid", None),
    }


async def handed_report(kernel: Kernel, *, crafted: bool) -> dict[str, str]:
    """`kid`, spawned by `lead`, posts what it crafted in a call of its own if `crafted`, then finishes, citing nothing,
    in its next; `lead` reads the runtime's report of it, shown by the finish it carries, and answers on a topic by its
    next call, citing nothing."""
    await driven.channel(kernel, "notes", kind="board")
    await driven.channel(kernel, "log", kind="topic")
    lead = await driven.spawn(kernel, "lead", role="lead")
    await driven.spawn(kernel, "kid", by=lead)
    await driven.start_turn(kernel, "kid")
    crafting = await called(kernel, "kid", "k1")
    if crafted:
        await ran(kernel, "kid", "k1", "board.post", {"board": "notes", "name": "plan", "gist": "the plan"})
        await called(kernel, "kid", "k2")
    finished = (await ran(kernel, "kid", f"k{1 + crafted}", "agent.finish", {"gist": "the plan is up"}))["ref"]
    reporting = driven.of_type(kernel, "model.called")[-1]
    await driven.end_turn(kernel, "kid")
    await driven.start_turn(kernel, "lead")
    await called(kernel, "lead", "c1")
    await ran(kernel, "lead", "c1", "message.read", {}, tool="read")
    await returned(kernel, "lead", "read")
    leading = await called(kernel, "lead", "c2")
    answer = await sent(kernel, "lead", "c2", "#log")
    await driven.end_turn(kernel, "lead")
    return {
        "finished": finished,
        "answer": answer,
        "crafting": crafting,
        "reporting": f"{reporting.stream}@{reporting.version}",
        "leading": leading,
    }


async def test_propagate_reaches_a_helper_whose_report_a_credited_span_of_its_parent_took(tmp_path):
    """`lead`'s answer cites nothing, and its span took `kid`'s report: half of the reward reaches `kid`'s finish."""
    kernel = await journal(tmp_path)
    refs = await handed_report(kernel, crafted=False)

    session = await propagated(kernel, tmp_path, [refs["answer"]])

    agents = await credited(session)
    assert values(agents) == {"lead": 0.5, "kid": 0.5} and agents["kid"].evidence == (refs["finished"],)
    assert {target: row.value for target, row in (await spanned(session)).items()} == {
        refs["leading"]: 0.5,
        refs["reporting"]: 0.5,
    }


async def test_an_uncited_report_keeps_what_reaches_it_on_the_span_that_wrote_it(tmp_path):
    """`kid` crafted in one span and reported in another, citing nothing: all that reaches its report stays on the
    report's span, and the crafting span is never reached."""
    kernel = await journal(tmp_path)
    refs = await handed_report(kernel, crafted=True)

    session = await propagated(kernel, tmp_path, [refs["answer"]])

    spans = await spanned(session)
    assert {target: row.value for target, row in spans.items()} == {refs["leading"]: 0.5, refs["reporting"]: 0.5}
    assert refs["crafting"] not in spans


async def test_propagate_credits_a_spawn_through_the_goal_its_child_took(tmp_path):
    """`lead`'s spawn of `kid` is the goal `kid`'s launch offered, which its harness took: `kid`'s message passes half
    along that take, to the span of `lead`'s that spawned it, and nothing to its own instructions."""
    kernel = await journal(tmp_path)
    await driven.channel(kernel, "log", kind="topic")
    await driven.spawn(kernel, "lead", role="lead")
    await driven.start_turn(kernel, "lead")
    spawning = await called(kernel, "lead", "c1")
    spawn = {"name": "kid", "child_role": "worker", "goal": "craft the plan"}
    goal = (await ran(kernel, "lead", "c1", "agent.spawn", spawn))["ref"]
    await driven.end_turn(kernel, "lead")
    await driven.settle_effects(kernel, "kid")
    instructions = f"sha256:{await kernel.put_body(b'You are a worker.')}"
    launch = {"agent": "kid", "body": instructions, "goal": True}
    launched = driven.result_of(await kernel.submit(kernel.runtime, "agent.instruct", launch))
    await driven.start(kernel, "kid")
    await driven.confirm(kernel, "kid", launched, evidence="command_lifecycle")
    await driven.start_turn(kernel, "kid")
    crafting = await called(kernel, "kid", "k1")
    made = await sent(kernel, "kid", "k1", "#log")
    await driven.end_turn(kernel, "kid")

    session = await propagated(kernel, tmp_path, [made])

    agents = await credited(session)
    assert values(agents) == {"kid": 0.5, "lead": 0.5} and agents["lead"].evidence == (goal,)
    assert {target: row.value for target, row in (await spanned(session)).items()} == {
        crafting: 0.5,
        spawning: 0.5,
    }


class OwnModels:
    """An authority that admits each agent through a FakeModel of its own as its gateway, so each agent's replies come
    in its own order, however the agents' turns interleave."""

    def __init__(self, models: dict[str, FakeModel]) -> None:
        self.models = models

    async def admit(self, spawn: SpawnRequest) -> Admission:
        return await Gateways(self.models[spawn.agent]).admit(spawn)

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        return None


async def test_a_mesh_whose_peers_never_finish_reaches_the_helpers_its_closing_spans_took(tmp_path):
    """The GPU run's failure, scripted: peers that stay and never finish, closed on what each said last, which follows
    from and cites nothing. `a` spawns `h`, which posts its plan and reports; `a`, woken by the report, tells `b`, whose
    last words follow. Each closing message keeps half its share and passes the rest along what its span took: `b`'s
    along `a`'s message, and `a`'s along `h`'s report, which passes along `h`'s goal, `a`'s spawn, which passes along
    the program's first message. Without takes each peer kept its half, and `h` nothing."""
    spawning = ToolCall("agent_spawn", {"name": "h", "child_role": "helper", "goal": "craft the plan"}, id="spawn")
    posting = ToolCall("board_post", {"board": "notes", "name": "plan", "gist": "the plan"}, id="post")
    telling = ToolCall("message_send", {"to": "@b", "gist": "the plan is on the board"}, id="tell")
    models = {
        "a": FakeModel(spawning, "h is crafting the plan", telling, "b knows of the plan"),
        "h": FakeModel(posting, "the plan is on the board"),
        "b": FakeModel("I have the plan"),
    }
    roles = {
        "a": {"harness": scripted([AskModel()], [AskModel()]), "may_spawn": ["helper"]},
        "b": {"harness": scripted([AskModel()])},
        "helper": {"harness": scripted([AskModel()]), "count": 0},
    }
    notes = {"kind": "board", "writers": "all", "readers": "all"}
    topology = {"edges": {"a": ["all"], "b": ["all"]}, "channels": {"notes": notes}, "limits": {"max_hops": 8}}
    team = Team.model_validate({"roles": roles, "topology": topology})
    start: dict[str, Any] = {"root": tmp_path, "principal": PROGRAM, "authority": OwnModels(models)}
    async with contextlib.AsyncExitStack() as stack:
        for model in models.values():
            await stack.enter_async_context(model)
        session = await stack.enter_async_context(Session.start(team, name="mesh", **start))
        await session.open_episode("e")
        await session.send("@a", "make a plan, and tell b of it")
        await asyncio.wait_for(session.settled(), SECONDS)
        said = {row["agent"]: row["said"] for row in await session.agents()}
        await session.close_episode(based_on=[said["a"], said["b"]])
    attached = await Session.attach("mesh", root=tmp_path)
    await rewarded(attached, ("scored", 1.0))
    await propagate(attached, "e", judge=None, retained=0.5)

    agents = await credited(attached)
    assert values(agents) == {"a": pytest.approx(15 / 32), "b": 0.25, "h": pytest.approx(3 / 16)}
    rows = (await spanned(attached)).values()
    spans = [((await attached.lineage(row.target)).event.agent, row.value) for row in rows]
    assert sorted(spans) == [("a", 3 / 32), ("a", 3 / 8), ("b", 0.25), ("h", 3 / 16)]
