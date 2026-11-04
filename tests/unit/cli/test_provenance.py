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
from ..primitives.support import ROLES, confirm, report, send, spawn, start_turn
from ..primitives.test_provenance import (
    CHILD,
    CITED,
    REPO,
    ROOT,
    ask,
    commit,
    committed,
    done,
    scenario,
    stored,
    tool,
)

ESTIMATE = {"kind": "credit", "scope": "team", "status": "scored", "head_seq": 49, "producer_version": "0"}


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
    assert "taken by command_lifecycle n1, then 1 compaction: forgot" in declared.text
    assert "taken by tool_item t1, then 1 compaction: unsaid" in declared.text


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
        f"{unseen} by @alice: a note to self; unknown: never handed over through us; 7 surfaces of its harness no "
        "stored conformance result proves observed"
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
    assert "@bob was handed 40 offers below the bound, 0 said taken and 40 never, with 4 gaps in its record" in [
        line.text for line in sources
    ]


@pytest.mark.parametrize("repo", [REPO])
async def test_a_link_that_opens_nothing_says_why(kernel):
    trailers = [{"written": "the spec", "sha": None}]
    refs = await committed(kernel, [commit(ROOT, [], "@alice", [])], [commit(CHILD, [ROOT, CITED], "@alice", trailers)])

    sources = part(lines(kernel, refs[CHILD]), "Sources")
    unopened = [line for line in sources if line.ref is None and line.kind]

    assert unopened == [
        Line("unresolved", "Informed-By 'the spec' names no recorded commit and no event of the session", warn=True),
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
        Line("credit", "0.5 by even-split 0, team, of the trace at head 49"),
        Line("reward", "no value, invalid, by judge 0, local, of the trace at head 49"),
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
        "content could come through lies below it"
    )
    assert said.warn, "not seen is no evidence the citer used what it cites"
    assert Line("", "the walk stopped at its limit, so more may lie beyond what it reached", warn=True) in found
