"""How provenance reads in both clients, from what the four queries answer of a journal the test writes: each link by
how it is known, each answer's head, bound, open turn and what its page left out, unknown with its reasons, and credit
only as what an estimator said."""

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Refused
from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.primitives import PRIMITIVES, Contributors, Interactions, Lineage, Spans, Uses
from platoon_harness_cli.provenance import (
    FROM_TEXT,
    REF_IN_TEXT,
    Line,
    interaction_lines,
    lines_of,
    no_provenance,
    read,
    who_reached_whom,
)
from platoon_harness_cli.replay import Playhead

from ..kernel.support import grant, result_of
from ..primitives.support import ROLES, channel, confirm, end_turn, of_type, report, send, spawn, start_turn
from ..primitives.test_interactions import handed
from ..primitives.test_provenance import (
    CHILD,
    CITED,
    REPO,
    ROOT,
    ask,
    commit,
    committed,
    done,
    ref_of,
    scenario,
    stored,
    tool,
)
from ..primitives.test_spans import called, wrote
from ..primitives.test_spans import team as spanned

ESTIMATE = {"kind": "credit", "scope": "team", "status": "scored", "head_seq": 49, "producer_version": "0"}
ESTIMATE |= {"params_hash": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"}


@pytest.fixture
def repo() -> dict[str, Any] | None:
    return None


async def opened(folder: Path, repo: dict[str, Any] | None = None) -> Kernel:
    """A session's kernel on a manual clock, so that every seq it writes is the same each run."""
    kernel = Kernel.open(folder, clock=ManualClock(1000.0), extensions=PRIMITIVES)
    settings: dict[str, Any] = {"roles": ROLES, "limits": {}}
    if repo is not None:
        settings["repo"] = {**repo, "tips": f"sha256:{await kernel.put_body(b'')}"}
    result_of(await kernel.submit(kernel.runtime, "session.open", settings))
    await grant(kernel, "agent")
    await grant(kernel, "human")
    return kernel


@pytest.fixture
async def kernel(tmp_path: Path, repo: dict[str, Any] | None) -> AsyncIterator[Kernel]:
    found = await opened(tmp_path / "session", repo)
    yield found
    found.close()


def lines(
    kernel: Kernel, ref: str, estimates: Sequence[dict[str, Any]] = (), spans: list[dict[str, Any]] | None = None
) -> list[Line]:
    """What a panel says of `ref`, from the queries' answers as both clients take them."""
    answers = [ask(kernel, query, ref=ref) for query in ("lineage", "uses", "contributors")]
    return lines_of("s", *answers, list(estimates), spans)


class Asked:
    """What a panel asks of a session, answered by `kernel` as a session answers, with nothing an estimator said, and
    each `after` it read `spans` from."""

    name = "s"

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel
        self.read_from: list[str | None] = []

    def _ask(self, op: str, **args: Any) -> Any:
        outcome = self.kernel.query(self.kernel.runtime, op, args)
        if outcome.refusal is not None:
            raise Refused.of(outcome.refusal)
        return outcome.result

    async def lineage(self, ref: str) -> Lineage:
        return Lineage.model_validate(self._ask("lineage", ref=ref))

    async def uses(self, ref: str) -> Uses:
        return Uses.model_validate(self._ask("uses", ref=ref))

    async def contributors(self, ref: str) -> Contributors:
        return Contributors.model_validate(self._ask("contributors", ref=ref))

    async def annotations(self, target: str) -> list[Any]:
        return []

    async def spans(self, agent: str, *, after: str | None = None) -> Spans:
        self.read_from.append(after)
        return Spans.model_validate(self._ask("spans", agent=agent, after=after))

    async def interactions(self, *, after: str | None = None) -> Interactions:
        return Interactions.model_validate(self._ask("interactions", after=after))


def turn_of(kernel: Kernel, call: str) -> list[dict[str, Any]]:
    """The spans of the turn `w`'s model call `call` was reported in, which a panel on it is given."""
    turn = ask(kernel, "lineage", ref=call)["made"]["turn"]
    return [span for span in ask(kernel, "spans", agent="@w")["spans"] if span["turn"] == turn]


def credit(kernel: Kernel, call: str, *estimates: dict[str, Any]) -> list[Line]:
    """What a panel on `w`'s model call `call` says under Credit and rewards."""
    return part(lines(kernel, call, estimates, turn_of(kernel, call)), "Credit and rewards")


def part(found: list[Line], heading: str) -> list[Line]:
    """The lines under one heading."""
    start = found.index(Line("heading", heading)) + 1
    end = next((at for at in range(start, len(found)) if found[at].kind == "heading"), len(found))
    return found[start:end]


async def test_each_link_is_labelled_by_how_it_is_known_and_opens_its_event(kernel):
    refs = await scenario(kernel)

    sources = part(lines(kernel, refs["message"]), "Sources")
    uses = part(lines(kernel, refs["posted"]), "Uses")

    assert [(line.kind, line.ref) for line in sources if line.ref is not None] == [
        ("", refs["c2"]),
        ("declared", refs["posted"]),
        ("gap", "agent/bob@4"),
        ("observed", "context/bob@3"),
        ("observed", "context/bob@1"),
    ]
    assert [(line.kind, line.ref) for line in uses if line.ref is not None] == [
        ("cause", "board/notes@1"),
        ("observed", "context/bob@1"),
        ("declared", refs["message"]),
    ]
    declared = next(line for line in sources if line.kind == "declared")
    assert declared.text.startswith("board/notes/spec@1 by @alice: v1; seen: wake context/bob@1 showed")
    assert "taken, as its harness's command_lifecycle report n1 says, then 1 compaction: forgot" in declared.text
    assert "its result returned to its harness, under t1, then 1 compaction: unsaid" in declared.text


async def test_every_answer_says_its_head_where_it_stops_and_whether_its_turn_was_open(kernel):
    refs = await scenario(kernel)

    found = lines(kernel, refs["message"])
    read_at = [line for line in found if " read at head " in line.text]

    assert [line.text.partition(" read at head ")[0] for line in read_at] == ["lineage", "uses", "contributors"]
    assert all(line.text.partition(" read at head ")[2].startswith("49") for line in read_at)
    assert "counting what was handed over below the model call turn/bob@5 that chose it" in read_at[0].text
    later = "its turn had not ended, so a later report can still confirm an offer or join a call"
    assert all(later in line.text and line.warn for line in read_at)
    chosen = "chosen by the model call turn/bob@5, through its tool item turn/bob@6, of claudecode/toolUseId t2"
    assert Line("", chosen, refs["c2"]) in found


async def test_unknown_is_spelled_out_with_its_reasons_and_a_claim_is_never_drawn_as_seen(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    unseen = (await send(kernel, alice, "@alice", "a note to self"))["ref"]
    cited = (await send(kernel, bob, "@alice", "I rest on that", based_on=[unseen]))["ref"]

    (declared,) = [line for line in lines(kernel, cited) if line.kind == "declared"]

    assert declared.text == (
        f"{unseen} by @alice: a note to self; unknown: not handed over through us below the bound; 7 surfaces of its "
        "harness no stored conformance result proves observed"
    )
    assert declared.warn and declared.ref == unseen


async def test_what_a_page_left_out_is_said_with_the_command_that_reads_on(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    for n in range(40):
        await send(kernel, alice, "@bob", f"note {n}")
        result_of(await kernel.submit(bob, "message.read", {}, native=tool(f"t{n}")))
        if n % 10 == 0:
            await report(kernel, "bob", "gap", what="unknown_update")
    final = (await send(kernel, bob, "@alice", "read them all"))["ref"]
    cursor = ask(kernel, "lineage", ref=final)["cursor"]

    sources = part(lines(kernel, final), "Sources")

    assert sum(line.kind in ("observed", "gap") for line in sources) == 32
    said = f"32 of 44 shown, newest first: `platoon-harness lineage s --ref {final} --after {cursor}` reads on"
    assert Line("", said, warn=True) == sources[-1]
    assert "@bob was handed 40 offers below the bound, 0 said taken there and 40 not, with 4 gaps in its record" in [
        line.text for line in sources
    ]


@pytest.mark.parametrize("repo", [REPO])
async def test_a_link_that_opens_nothing_says_why(kernel):
    trailers = [{"written": "the spec", "sha": None}]
    refs = await committed(kernel, [commit(ROOT, [], "@alice", [])], [commit(CHILD, [ROOT, CITED], "@alice", trailers)])

    sources = part(lines(kernel, refs[CHILD]), "Sources")
    unopened = [line for line in sources if line.ref is None and line.kind]

    assert unopened == [
        Line(
            "unresolved",
            "Informed-By 'the spec' cites nothing: it names no commit git could resolve and no event of the session",
            warn=True,
        ),
        Line("ancestry", f"commit {CITED[:12]}, which git holds and the journal has no record of"),
    ]
    assert any("below the look that recorded it" in line.text for line in sources)


async def test_contributors_weigh_and_rank_nobody_and_list_those_only_handed_apart(kernel):
    refs = await scenario(kernel)

    contributors = part(lines(kernel, refs["message"]), "Contributors")

    assert "weighing and ranking nobody" in contributors[0].text
    assert [(line.text.partition(":")[0], line.ref) for line in contributors[1:]] == [
        ("@bob", refs["message"]),
        ("@alice", refs["posted"]),
    ]
    assert "declared, 1 event, the first board/notes/spec@1, 1 hop back" in contributors[2].text
    assert not any(word in line.text for line in contributors for word in ("share", "weight", "rank 1", "%"))


async def test_an_estimate_is_shown_by_its_producer_and_version_beside_another_and_never_summed(kernel):
    refs = await scenario(kernel)
    estimates = [
        {**ESTIMATE, "producer": "even-split", "value": 0.5},
        {**ESTIMATE, "producer": "judge", "value": None, "status": "invalid", "kind": "reward", "scope": "local"},
    ]

    said = part(lines(kernel, refs["message"], estimates), "Credit and rewards")

    assert said[1:] == [
        Line("credit", "0.5 by even-split, version 0, params 44136fa3, team, of the trace at head 49"),
        Line("reward", "no value, invalid, by judge, version 0, params 44136fa3, local, of the trace at head 49"),
    ]
    assert part(lines(kernel, refs["message"]), "Credit and rewards")[1:] == [
        Line("", "no estimator has said anything of it")
    ]


async def test_in_a_replay_each_estimate_says_when_it_was_written_and_whether_that_was_after_where_it_stands(kernel):
    """An estimator writes beside the journal, after the session as often as not, so a replay standing at an earlier
    point shows each estimate with when it was written, and one written after that point, or of a trace past it, however
    its clock ran, as not known there."""
    refs = await scenario(kernel)
    estimates = [
        {**ESTIMATE, "producer": "even-split", "value": 0.5, "wall_time": 1_000.0},
        {**ESTIMATE, "producer": "judge", "value": 1.0, "wall_time": 5_000.0},
        {**ESTIMATE, "producer": "skewed", "value": 0.0, "wall_time": 1_500.0, "head_seq": 60},
    ]
    answers = [ask(kernel, query, ref=refs["message"]) for query in ("lineage", "uses", "contributors")]

    said = part(lines_of("s", *answers, estimates, playhead=Playhead(49, 2_000.0)), "Credit and rewards")

    written = "of the trace at head 49, written 1970-01-01 00:16:40 UTC, by this point of the replay"
    later = "after this point of the replay, so it was not known here"
    assert said[1:] == [
        Line("credit", f"0.5 by even-split, version 0, params 44136fa3, team, {written}"),
        Line(
            "credit",
            f"1 by judge, version 0, params 44136fa3, team, of the trace at head 49, written 1970-01-01 01:23:20 UTC, "
            f"{later}",
            warn=True,
        ),
        Line(
            "credit",
            f"0 by skewed, version 0, params 44136fa3, team, of the trace at head 60, written 1970-01-01 00:25:00 UTC, "
            f"{later}",
            warn=True,
        ),
    ]
    assert part(lines(kernel, refs["message"], estimates), "Credit and rewards")[1].text.endswith("at head 49")


async def test_a_ranged_citation_says_whether_its_lines_were_shown_as_exposure_does(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    body = await stored(kernel, "one\ntwo\nthree\n")
    sent = (await send(kernel, alice, "@bob", "see the body", body=body))["ref"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", handed["input"], evidence="command_lifecycle")
    gist_only = (await send(kernel, bob, "@alice", "lines two to three", based_on=[f"{sent}#L2-3"]))["ref"]
    result_of(await kernel.submit(bob, "message.read", {"bodies": True, "after": 0}, native=tool("t1")))
    await done(kernel, "bob", "t1")
    whole = (await send(kernel, bob, "@alice", "and again", based_on=[f"{sent}#L2-3"]))["ref"]

    (before,) = [line for line in lines(kernel, gist_only) if line.kind == "declared"]
    (after,) = [line for line in lines(kernel, whole) if line.kind == "declared"]

    assert before.text.endswith("; whether its lines were shown is unknown") and before.warn
    assert after.text.endswith("; its lines were shown") and not after.warn and after.ref == sent


async def test_not_seen_and_a_walk_cut_short_are_said_as_the_answers_say_them(kernel):
    refs = await scenario(kernel)
    lineage = ask(kernel, "lineage", ref=refs["message"])
    declared = lineage["declared"][0]
    proved = {"answer": "not_seen", "proved": [], "bound": lineage["bound"], "head": 49, "open": False}
    lineage["declared"] = [declared | {"exposure": proved}]
    contributors = ask(kernel, "contributors", ref=refs["message"]) | {"stopped_short": True}

    found = lines_of("s", lineage, ask(kernel, "uses", ref=refs["message"]), contributors, [])

    (said,) = [line for line in found if line.kind == "declared"]
    assert said.text.endswith(
        "; not seen: nothing offered it below the bound, every surface of its harness is proved observed, and no gap "
        "below it could have let content through"
    )
    assert said.warn, "not seen is no evidence the citer used what it cites"
    assert Line("", "the walk stopped at its limit, so more may lie beyond what it reached", warn=True) in found


async def test_no_line_says_never_where_the_record_holds_only_nothing_below_the_bound(kernel):
    """A citation made before its event was handed over, and one made before its handover was confirmed: each answer
    counts below its bound, and the harness's report that came after is in the record, so nothing reads as never."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "the spec"))["ref"]
    early = (await send(kernel, bob, "@alice", "resting on it", based_on=[sent]))["ref"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    later = (await send(kernel, bob, "@alice", "again", based_on=[sent]))["ref"]
    await confirm(kernel, "bob", handed["input"], evidence="message_start", native_id="entry-1")

    said = {ref: [line.text for line in lines(kernel, ref)] for ref in (early, later, sent)}

    assert not [text for found in said.values() for text in found if "never" in text]
    assert any("unknown: not handed over through us below the bound" in text for text in said[early])
    assert any("unknown: handed 1 time and not said taken below the bound" in text for text in said[later])
    assert any("its harness had not said it took it below the bound" in text for text in said[later])
    assert any(text.endswith("and its harness said it took an offer of it") for text in said[sent])


@pytest.mark.parametrize("repo", [REPO])
async def test_a_commit_nobody_s_workspace_made_alone_is_cited_by_nobody_the_record_names(kernel):
    trailers = [{"written": CITED[:8], "sha": CITED}, {"written": "agent/alice@1", "sha": None}]
    refs = await committed(kernel, [commit(CITED, [], "@alice", [])], [commit(CHILD, [], None, trailers)])

    sources = part(lines(kernel, refs[CHILD]), "Sources")

    (declared,) = [line for line in sources if line.kind == "declared"]
    (unresolved,) = [line for line in sources if line.kind == "unresolved"]
    assert sources[0] == Line("", "made by nobody the record names")
    assert declared.text.endswith("; its citer is nobody the record names, so no reading of it is evidence")
    assert unresolved.text == (
        "Informed-By 'agent/alice@1' cites nothing: it names an event, and nobody the record names made the commit, so "
        "nobody can be shown to have read it"
    )
    assert not [line for line in sources if "no agent" in line.text]


@pytest.mark.parametrize("repo", [REPO])
async def test_each_informed_by_value_that_cites_nothing_says_why(kernel):
    bob = await spawn(kernel, "bob")
    await channel(kernel, "notes", kind="board")
    post = {"board": "notes", "name": "spec", "gist": "the spec", "body": await stored(kernel, "one\n")}
    spec = result_of(await kernel.submit(bob, "board.post", post))["ref"]
    written = [("e" * 12, "e" * 40), ("the spec", None), (f"{spec}#L2-5", None), (spec, None)]
    trailers = [{"written": value, "sha": sha} for value, sha in written]
    refs = await committed(kernel, [commit(CHILD, [], "@alice", trailers)])

    said = [line for line in part(lines(kernel, refs[CHILD]), "Sources") if line.kind == "unresolved"]

    assert [(line.text.partition(" cites nothing: it ")[2], line.ref) for line in said] == [
        ("names commit eeeeeeeeeeee, which git holds and the journal held no record of", None),
        ("names no commit git could resolve and no event of the session", None),
        ("names lines its event's body does not hold", spec),
        ("names an event @alice had neither made nor been handed when the look ran", spec),
    ]
    assert all(line.warn for line in said)


async def test_a_read_that_returned_to_a_code_mode_script_says_it_went_to_the_script(kernel):
    """Codex's `callId` names the script that made a call, so a result taken under it went to that script, which may
    never have shown it to the model, and every call of the script shares it."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "the spec"))["ref"]
    await start_turn(kernel, "bob")
    for _ in range(2):
        result_of(await kernel.submit(bob, "message.read", {"after": 0}, native={"callId": "exec-1"}))
    await done(kernel, "bob", "exec-1")
    cited = (await send(kernel, bob, "@alice", "read it", based_on=[sent]))["ref"]

    (declared,) = [line for line in lines(kernel, cited) if line.kind == "declared"]

    shared = "its result returned to the Code Mode script that made call exec-1, which 2 of its agent's commands share"
    assert shared in declared.text and "returned to its harness" not in declared.text


async def test_an_outcome_s_own_maker_made_it_whatever_else_reached_it(kernel):
    await spawn(kernel, "alice")
    bob = await spawn(kernel, "bob")
    await channel(kernel, "notes", kind="board")
    noted = result_of(await kernel.submit(bob, "board.post", {"board": "notes", "name": "n", "gist": "mine"}))["ref"]
    answer = (await send(kernel, bob, "@alice", "as I noted", based_on=[noted]))["ref"]

    (row,) = [line for line in part(lines(kernel, answer), "Contributors") if line.text.startswith("@bob:")]

    assert row.text.startswith(f"@bob: made it, and reached by declared, 2 events, the first {answer}, 0 hops back")


async def test_a_reader_is_named_by_its_first_offer_and_whether_its_harness_took_any(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "twice"))["ref"]
    for anchor in ("t1", "t2"):
        result_of(await kernel.submit(bob, "message.read", {"after": 0}, native=tool(anchor)))
    await done(kernel, "bob", "t2")
    first = ref_of(next(event for event in of_type(kernel, "context.offered") if event.agent == "bob"))

    (row,) = [line for line in part(lines(kernel, sent), "Uses") if line.kind == "observed"]

    assert row == Line("observed", f"@bob, first by {first}, and its harness said it took an offer of it", first)


async def test_a_tool_item_names_the_call_its_report_names_and_what_its_agent_s_command_made(kernel):
    refs = await scenario(kernel)
    items = [event for event in of_type(kernel, "item.recorded") if event.data["native_id"] == "t2"]
    called = of_type(kernel, "model.called")[0]

    item, call = part(lines(kernel, ref_of(items[-1])), "Sources"), part(lines(kernel, ref_of(called)), "Sources")

    assert item[1:3] == [
        Line("", f"chosen by the model call {refs['c2']}, which its harness's report of it names", refs["c2"]),
        Line("", f"under tool call t2, its agent's command made {refs['message']}", refs["message"]),
    ]
    assert "below the model call" in item[3].text
    assert call[1] == Line("", "no model call is joined: the runtime recorded it, not a command of its agent's")
    assert not [line for line in (*item, *call) if "no tool call's id came with it" in line.text]


@pytest.mark.parametrize("repo", [REPO])
async def test_a_commit_s_maker_is_joined_to_no_call_as_a_look_found_it_in_git(kernel):
    refs = await committed(kernel, [commit(ROOT, [], "@alice", [])])

    sources = part(lines(kernel, refs[ROOT]), "Sources")

    assert sources[1] == Line("", "no model call is joined: a look found it in git, which names no tool call")


async def test_estimates_that_differ_only_in_their_params_say_so(kernel):
    refs = await scenario(kernel)
    estimates = [
        {**ESTIMATE, "producer": "even-split", "value": 0.25},
        {**ESTIMATE, "producer": "even-split", "value": 0.75, "params_hash": "e070fd" + "0" * 58},
    ]

    said = part(lines(kernel, refs["message"], estimates), "Credit and rewards")

    assert [line.text.partition(", team")[0] for line in said[1:]] == [
        "0.25 by even-split, version 0, params 44136fa3",
        "0.75 by even-split, version 0, params e070fd00",
    ]


async def test_a_span_s_credit_row_is_said_to_be_the_whole_span_s_with_its_bounds(kernel):
    """A row on the model call that names a span is the whole span's, from its first call to that one, with the writes
    the record ties to its calls; a call that names none says which span it lies in, and one out of a turn lies in
    none."""
    await spanned(kernel)
    outside = await called(kernel, "c0")
    await start_turn(kernel, "w", "t1")
    c1, c2 = await called(kernel, "c1"), await called(kernel, "c2")
    one = await wrote(kernel, "c2", "one")
    c3 = await called(kernel, "c3")
    two = await wrote(kernel, "c3", "two")
    await end_turn(kernel, "w")
    row = {**ESTIMATE, "scope": "local", "producer": "propagate", "value": 0.25}

    named, alone, inside = credit(kernel, c2, row), credit(kernel, c3), credit(kernel, c1)
    out_of_a_turn = credit(kernel, outside)

    whole = "it names a span of @w's, so a credit row on it is the whole span's:"
    assert named[1:] == [
        Line("", f"{whole} the model calls in turn t1 from {c1} to this one", c1),
        Line("", f"one of the span's calls chose the write {one}", one),
        Line("credit", "0.25 by propagate, version 0, params 44136fa3, local, of the trace at head 49"),
    ]
    assert alone[1:] == [
        Line("", f"{whole} this one model call, in turn t1"),
        Line("", f"one of the span's calls chose the write {two}", two),
        Line("", "no estimator has said anything of it"),
    ]
    assert inside[1:] == [
        Line("", f"it names no span, so no credit row on it is a span's: it lies in the one {c2} names", c2),
        Line("", "no estimator has said anything of it"),
    ]
    assert out_of_a_turn[1:] == [
        Line("", "it lies in no span, so no credit row on it is a span's: a span holds only calls reported in a turn"),
        Line("", "no estimator has said anything of it"),
    ]


async def test_a_span_in_a_turn_under_way_says_a_later_call_can_join_it_and_a_later_report_cut_it(kernel):
    """While its turn is under way, the turn's last span takes each later call of it, which then names it, so the call
    that names that span names it only so far, and no reason a turn is one span is given before it ends; a later
    report can tie a write to a call of any of its spans, which cuts that span there."""
    await spanned(kernel)
    await start_turn(kernel, "w", "t1")
    c1 = await called(kernel, "c1")
    alone = credit(kernel, c1)
    c2 = await called(kernel, "c2")
    joined, extended = credit(kernel, c1), credit(kernel, c2)
    one = await wrote(kernel, "c2", "one")
    await called(kernel, "c3")
    await wrote(kernel, "c3", "two")
    before_the_last = credit(kernel, c2)

    whole = "it names a span of @w's, so a credit row on it is the whole span's:"
    can_change = (
        "its turn had not ended, so a later call of it can still join this span and name it, and a later report can "
        "still cut this span"
    )
    assert alone[1:] == [
        Line("", f"so far {whole} this one model call, in turn t1"),
        Line("", "the record ties no write to the span's calls"),
        Line("", can_change, warn=True),
        Line("", "no estimator has said anything of it"),
    ]
    assert joined[1:] == [
        Line("", f"it names no span, so no credit row on it is a span's: it lies in the one {c2} names", c2),
        Line("", can_change, warn=True),
        Line("", "no estimator has said anything of it"),
    ]
    assert extended[1] == Line("", f"so far {whole} the model calls in turn t1 from {c1} to this one", c1)
    assert before_the_last[1:] == [
        Line("", f"{whole} the model calls in turn t1 from {c1} to this one", c1),
        Line("", f"one of the span's calls chose the write {one}", one),
        Line("", "its turn had not ended, so a later report can still cut this span", warn=True),
        Line("", "no estimator has said anything of it"),
    ]


async def test_a_turn_of_one_span_says_why_its_harness_cuts_it_no_further(kernel):
    """A turn whose writes the record ties to no call, as each turn of a harness that joins no tool call to its call
    is, and one whose writes one call alone chose, are each one span, and say why."""
    await spanned(kernel)
    await start_turn(kernel, "w", "t1")
    await called(kernel, "c1")
    await wrote(kernel, "c1", "unanchored", how="unanchored")
    c2 = await called(kernel, "c2")
    await wrote(kernel, "c2", "unnamed", how="unnamed")
    await end_turn(kernel, "w")
    await start_turn(kernel, "w", "t2")
    await called(kernel, "c3")
    one, two = await wrote(kernel, "c3", "one"), await wrote(kernel, "c3", "two")
    c4 = await called(kernel, "c4")
    await end_turn(kernel, "w")

    unjoined, chosen_once = credit(kernel, c2), credit(kernel, c4)

    assert unjoined[2:] == [
        Line("", "the record ties no write to the span's calls"),
        Line(
            "",
            "its turn is one span, as the record ties no write of it to the call that chose it: @w wrote nothing in "
            "it, or its harness joins no tool call to the model call that chose it, which makes each of its turns one "
            "span",
        ),
        Line("", "no estimator has said anything of it"),
    ]
    assert [line.ref for line in chosen_once[2:4]] == [one, two]
    assert chosen_once[4] == Line(
        "",
        "its turn is one span, as one call alone chose the writes the record ties to it, and a turn is cut after each "
        "call that chose one but the last",
    )


async def test_a_span_is_found_on_whichever_page_of_its_agent_s_spans_holds_it(kernel):
    """`spans` answers a page at a time, so the panel reads on until the turn of the call it asks about has ended, and
    no further."""
    await spanned(kernel)
    calls = []
    for turn in range(40):
        await start_turn(kernel, "w", f"t{turn}")
        calls.append(await called(kernel, f"c{turn}"))
        await end_turn(kernel, "w")

    pages, named = [], []
    for at in (0, 33, 39):
        session = Asked(kernel)
        said = await read(session, calls[at])  # type: ignore[arg-type]
        pages.append(len(session.read_from))
        named += [line.text for line in said.lines if line.text.startswith("it names a span")]

    assert pages == [1, 2, 2]
    whole = "it names a span of @w's, so a credit row on it is the whole span's: this one model call"
    assert named == [f"{whole}, in turn t{at}" for at in (0, 33, 39)]


async def test_a_ref_opened_from_text_says_it_records_no_link(kernel):
    """A ref a text names is found standing apart from the words around it, never in a link's address, and its panel
    says first that it was opened from text, which records no link, and then all a panel opened by hand says."""
    refs = await scenario(kernel)
    text = f"as {refs['message']} says, see board/notes/spec@1#L1-2, not https://x/{refs['message']} or a@3"

    found = [(match[0], match[1]) for match in REF_IN_TEXT.finditer(text)]
    by_hand = await read(Asked(kernel), refs["message"])  # type: ignore[arg-type]
    from_text = await read(Asked(kernel), refs["message"], from_text=True)  # type: ignore[arg-type]

    assert found == [(refs["message"], refs["message"]), ("board/notes/spec@1#L1-2", "board/notes/spec@1")]
    assert from_text.lines == [by_hand.lines[0], Line("", FROM_TEXT), *by_hand.lines[1:]]
    assert FROM_TEXT == (
        "opened from a ref in text, which records no link: naming an event in text is no citation, and joins nothing "
        "in the record"
    )


async def test_a_ref_in_text_that_names_no_event_says_so(kernel):
    """Text can name what nothing is, as nothing checks it, where a citation is checked to name an event."""
    await scenario(kernel)

    with pytest.raises(Refused) as missing:
        await read(Asked(kernel), "board/notes/nothing@9", from_text=True)  # type: ignore[arg-type]

    assert no_provenance("board/notes/nothing@9", missing.value, from_text=True) == (
        "board/notes/nothing@9 names no event of this session: text can name what nothing is, as only a citation is "
        "checked"
    )
    assert no_provenance("board/notes/nothing@9", missing.value) == (
        "board/notes/nothing@9 has no provenance to show: not_found: nothing is board/notes/nothing@9"
    )


UNPROVED = "7 surfaces of its harness no stored conformance result proves observed, " + ", ".join(
    ("prompt", "tool_results", "shell_reads", "files", "native_children", "compaction", "external")
)
"""Why what reached an agent is unknown today: no stored result proves any surface of a harness."""


async def reached(kernel: Kernel) -> dict[str, str]:
    """Alice posts an entry and asks Bob, whose harness takes it; Bob revises her entry citing her question, and replies
    citing it and two ranges of her entry, which is handed to her and not said taken. Each kind of edge leads from
    Alice to Bob, and one unconfirmed offer from Bob to Alice. The refs of the offer taken, the revision, the reply and
    the offer not said taken."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "notes", kind="board", delivery="pull")
    body = f"sha256:{await kernel.put_body(b'line one\nline two\n')}"
    post = {"board": "notes", "name": "spec", "gist": "v1", "body": body}
    posted = result_of(await kernel.submit(alice, "board.post", post))["ref"]
    asked = (await send(kernel, alice, "@bob", "the plan"))["ref"]
    taken = await handed(kernel, "bob", taken=True)
    revise = {"board": "notes", "name": "spec", "gist": "v2", "expected_version": 1, "based_on": [asked]}
    revised = result_of(await kernel.submit(bob, "board.revise", revise))["ref"]
    cited = [asked, f"{posted}#L1-1", f"{posted}#L2-2"]
    replied = (await send(kernel, bob, "@alice", "agreed", reply_to=asked, based_on=cited))["ref"]
    offered = await handed(kernel, "alice", taken=False)
    return {"taken": taken, "revised": revised, "replied": replied, "offered": offered}


async def test_who_reached_whom_is_worded_pair_by_pair_with_how_each_is_known(kernel):
    """Each pair says whose events reached whose, then a line for each kind of edge between them, labelled by its kind,
    saying how that kind is known and opening the event that holds the first of them, and apart from them the offers no
    harness said it took, as unknown. Nothing sums the kinds, and an answer a later report can still change says so."""
    refs = await reached(kernel)
    taken, revised, replied, offered = refs["taken"], refs["revised"], refs["replied"], refs["offered"]

    found = await who_reached_whom(Asked(kernel))  # type: ignore[arg-type]

    head = ask(kernel, "interactions")["head"]
    assert found[:1] == [
        Line(
            "",
            f"interactions read at head {head:,}: 2 pairs of makers, oldest first, each counting the edges that lead "
            "from the first's events to the second's, each kind apart and never summed: reach in the record, never "
            "credit or influence; an offer it counts as unconfirmed went to an agent that had not ended, whose harness "
            "can still say it took it",
            warn=True,
        ),
    ]
    assert found[1 : found.index(Line("heading", "Each agent's unknowns"))] == [
        Line("heading", "events by @alice reached events by @bob"),
        Line("declared", f"3 citations, each its citer's claim, the first in {revised}", revised),
        Line(
            "observed",
            f"1 offer @bob's harness said it took, handed over and taken, never understood, the first by {taken}",
            taken,
        ),
        Line("cause", f"1 cause named, as a reply names what it answers, the first in {replied}", replied),
        Line(
            "ancestry",
            "1 edge of ancestry, a next version of an entry or a task, or a commit naming a commit its parent, the "
            f"first in {revised}",
            revised,
        ),
        Line("heading", "events by @bob reached events by @alice"),
        Line(
            "unconfirmed",
            "1 offer @alice's harness had not said it took, which is unknown, neither observed nor none, the first by "
            f"{offered}",
            offered,
            warn=True,
        ),
    ]


async def test_each_agent_s_unknowns_are_said_so_no_pair_reads_as_unknown_never_as_no_reach(kernel, tmp_path):
    """Each agent comes with why what reached it beyond the edges counted is unknown, the gaps content could come
    through among them, so an agent no pair names reads as unknown; a record with no pair says that this does not say
    nobody reached anybody, and an agent nothing leaves unknown would say so."""
    await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await report(kernel, "bob", "gap", what="stream_lost")
    empty = await opened(tmp_path / "empty")

    found = await who_reached_whom(Asked(kernel))  # type: ignore[arg-type]
    none = await who_reached_whom(Asked(empty))  # type: ignore[arg-type]
    answer = ask(kernel, "interactions")
    proved = {**answer, "unknowns": [{"agent": "carol", "unproved": [], "incidents": {}, "older_offers": 0}]}
    empty.close()

    reasons = Line(
        "",
        f"each agent spawned by head {answer['head']:,}, in the order they were, with why what reached it beyond the "
        "edges above is unknown, so an agent no pair names is not shown to be reached by nobody; a person's or a "
        "program's reading is no evidence, so neither is listed",
    )
    assert found[1] == Line(
        "",
        "no edge leads from one maker's events to another's here, which does not say nobody reached anybody: each "
        "agent's unknowns are below",
    )
    assert part(found, "Each agent's unknowns") == [
        reasons,
        Line("", f"@alice: unknown beyond the edges counted: {UNPROVED}", warn=True),
        Line(
            "",
            f"@bob: unknown beyond the edges counted: {UNPROVED}; 1 gap content could have come through, stream_lost 1",
            warn=True,
        ),
    ]
    assert part(none, "Each agent's unknowns")[1:] == [Line("", "no agent was spawned by then")]
    assert part(interaction_lines("s", proved), "Each agent's unknowns")[1:] == [
        Line(
            "",
            "@carol: every surface of its harness is proved observed, and its record holds no gap content could come "
            "through",
        )
    ]


async def test_what_a_page_of_who_reached_whom_left_out_is_said_with_the_command_that_reads_on(kernel):
    """Seven agents each cite each other's message, 42 pairs: the panel shows the first page, and says how much of it
    that is and the command that reads on from it, at the same head."""
    agents = [await spawn(kernel, f"a{n}") for n in range(7)]
    said = [(await send(kernel, agent, f"@{agent.name}", "mine"))["ref"] for agent in agents]
    for citer in agents:
        for maker, ref in zip(agents, said, strict=True):
            if maker != citer:
                await send(kernel, citer, f"@{citer.name}", "citing", based_on=[ref])

    found = await who_reached_whom(Asked(kernel))  # type: ignore[arg-type]

    cursor = ask(kernel, "interactions")["cursor"]
    assert len([line for line in found if line.kind == "heading" and line.text.startswith("events by ")]) == 32
    assert found[-1] == Line(
        "",
        "32 of 42 pairs and the unknowns of 7 agents shown; the rest come a page at a time, read at the same head: "
        f"`platoon-harness interactions s --after {cursor}` reads on",
        warn=True,
    )
