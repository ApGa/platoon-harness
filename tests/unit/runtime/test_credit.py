"""`propagate@2`: an episode's team reward split back along the record's own edges and kept per agent and per span, on
an ended session, by a named producer at a version, and never a fact."""

import asyncio
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
    assert {(row.kind, row.scope, row.producer_version) for row in rows.values()} == {("credit", "local", "2")}


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


async def ran(kernel: Kernel, name: str, call_id: str | None, op: str, args: dict[str, Any]) -> dict[str, Any]:
    """An op `name` runs by a tool call its model call `call_id` chose, after the tool item its harness reports of that
    tool call, or with no `call_id` by none."""
    if call_id is None:
        return driven.result_of(await kernel.submit(driven.agent(name), op, args))
    tool = f"tool-{len(driven.of_type(kernel, 'item.recorded'))}"
    await driven.report(kernel, name, "item", kind="tool", phase="started", gist=op, native_id=tool, call_id=call_id)
    return driven.result_of(await kernel.submit(driven.agent(name), op, args, native={"claudecode/toolUseId": tool}))


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
    assert {(row.kind, row.scope, row.producer_version) for row in spans.values()} == {("credit", "local", "2")}


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
under way, and the next begun on what waits, which its harness took; or a message or a board entry's next version,
after a model call or not, by the agent's latest call or by none, citing what was sent to its writer, and answering
it."""


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
            offer = (await kernel.submit(kernel.runtime, "delivery.offer", {"agent": name})).result
            if offer:
                await driven.confirm(kernel, name, offer["input"], evidence="message_start")
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
def test_propagate_2_writes_the_agent_rows_propagate_1_wrote(tmp_path_factory, script) -> None:
    """Whatever the journal, an agent's row is what its events kept on `propagate@1`'s walk, which keeping a share per
    span leaves as it was."""

    async def body() -> None:
        session, kept, makers = await propagated_play(tmp_path_factory.mktemp("credit"), script)
        rows: dict[str, float] = defaultdict(float)
        for ref, share in kept.items():
            if (makers[ref] or "").startswith("agent:"):
                rows[(makers[ref] or "").removeprefix("agent:")] += share
        assert values(await credited(session)) == rows
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
    each. Each result keeps a sixth for the span of the call that completed it, and its claim, which that span's first
    call made, a twelfth, passing the rest to the program's task, which is nobody's: three spans of a quarter."""
    if turns == "one":
        replies = [[claim(1), complete(1), claim(2), complete(2), claim(3), complete(3), "all three are done"]]
        ends = (1, 3, 6)
    else:
        replies = [[claim(number), complete(number), f"task {number} is done"] for number in (1, 2, 3)]
        ends = (2, 5, 8)

    session, calls = await worker(tmp_path, *replies)

    spans = await spanned(session)
    assert {target: (row.value, set(row.evidence)) for target, row in spans.items()} == {
        calls[end]: (0.25, task(number)) for number, end in zip((1, 2, 3), ends, strict=True)
    }
    assert values(await credited(session)) == {"w": 0.75}


async def test_a_claim_made_in_the_call_that_completed_the_previous_task_gives_that_span_its_share(tmp_path):
    """One call completes the first task and claims the second: the second's claim lies in the first's span, which
    keeps the claim's twelfth of the second's credit beside its own quarter."""
    replies = [claim(1), [complete(1), claim(2)], [complete(2), claim(3)], complete(3), "all three are done"]

    session, calls = await worker(tmp_path, replies)

    spans = await spanned(session)
    assert {target: (pytest.approx(row.value), set(row.evidence)) for target, row in spans.items()} == {
        calls[1]: (pytest.approx(1 / 3), task(1) | {"task/tasks/2@2"}),
        calls[2]: (pytest.approx(1 / 4), {"task/tasks/2@3", "task/tasks/3@2"}),
        calls[4]: (pytest.approx(1 / 6), {"task/tasks/3@3"}),
    }


async def test_two_claims_open_at_once_give_the_span_that_made_them_their_share(tmp_path):
    """One call claims two tasks, so the span holding it keeps both claims' share, and the second task's result its
    own."""
    replies = [[claim(1), claim(2)], complete(1), complete(2), claim(3), complete(3), "all three are done"]

    session, calls = await worker(tmp_path, replies)

    spans = await spanned(session)
    assert {target: (pytest.approx(row.value), set(row.evidence)) for target, row in spans.items()} == {
        calls[1]: (pytest.approx(1 / 3), task(1) | {"task/tasks/2@2"}),
        calls[2]: (pytest.approx(1 / 6), {"task/tasks/2@3"}),
        calls[5]: (pytest.approx(1 / 4), task(3)),
    }
