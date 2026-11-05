"""How provenance reads in both clients, from what the four queries answer of a journal the test writes: each link by
how it is known, each answer's head, bound, open turn and what its page left out, unknown with its reasons, and credit
only as what an estimator said."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.primitives import PRIMITIVES
from platoon_harness_cli.provenance import Line, lines_of

from ..kernel.support import grant, result_of
from ..primitives.support import ROLES, channel, confirm, of_type, report, send, spawn, start_turn
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


def lines(kernel: Kernel, ref: str, estimates: list[dict[str, Any]] = ()) -> list[Line]:
    """What a panel says of `ref`, from the queries' answers as both clients take them."""
    answers = [ask(kernel, query, ref=ref) for query in ("lineage", "uses", "contributors")]
    return lines_of("s", *answers, list(estimates))


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
