"""Boards: objects with stable names and immutable versions."""

import pytest

from platoon_harness.primitives import boards

from .support import channel, of_type, refusal, result_of, spawn


@pytest.fixture
async def notes(kernel) -> str:
    await channel(kernel, "notes", kind="board")
    return "notes"


def post(name: str = "spec", gist: str = "first", **fields) -> dict:
    return {"board": "notes", "name": name, "gist": gist, **fields}


async def test_an_object_starts_at_version_one(kernel, notes):
    bob = await spawn(kernel, "bob")

    assert result_of(await kernel.submit(bob, "board.post", post())) == {"ref": "board/notes/spec@1", "version": 1}


async def test_a_post_needs_a_board(kernel):
    bob = await spawn(kernel, "bob")

    assert refusal(await kernel.submit(bob, "board.post", post())).code == "not_found"


async def test_a_second_post_conflicts_and_names_the_current_version(kernel, notes):
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(bob, "board.post", post()))

    refused = refusal(await kernel.submit(bob, "board.post", post(gist="again")))

    assert refused.code == "conflict" and refused.detail["current"] == 1


async def test_versions_are_immutable(kernel, notes):
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(bob, "board.post", post()))
    result_of(await kernel.submit(bob, "board.revise", post(gist="second", expected_version=1)))

    old = result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec", "version": 1}))
    new = result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"}))

    assert (old["gist"], old["ref"]) == ("first", "board/notes/spec@1")
    assert (new["gist"], new["ref"]) == ("second", "board/notes/spec@2")


async def test_revise_requires_expected_version(kernel, notes):
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(bob, "board.post", post()))

    assert refusal(await kernel.submit(bob, "board.revise", post(gist="blind"))).code == "invalid"


async def test_a_stale_revise_conflicts_returns_the_current_version_and_overwrites_nothing(kernel, notes):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    result_of(await kernel.submit(alice, "board.post", post()))
    result_of(await kernel.submit(alice, "board.revise", post(gist="alice's", expected_version=1)))

    refused = refusal(await kernel.submit(bob, "board.revise", post(gist="bob's", expected_version=1)))

    assert refused.code == "conflict"
    assert refused.detail == {"expected": 1, "current": 2, "ref": "board/notes/spec@2"}
    latest = result_of(await kernel.submit(alice, "board.get", {"board": "notes", "name": "spec"}))
    assert latest["gist"] == "alice's"


async def test_concurrent_revises_let_exactly_one_win(kernel, notes):
    import asyncio

    agents = [await spawn(kernel, f"a{index}") for index in range(4)]
    result_of(await kernel.submit(agents[0], "board.post", post()))

    outcomes = await asyncio.gather(
        *(kernel.submit(agent, "board.revise", post(gist=agent.name, expected_version=1)) for agent in agents)
    )

    assert sorted(outcome.refusal is None for outcome in outcomes) == [False, False, False, True]


async def test_a_revise_of_nothing_is_not_found(kernel, notes):
    bob = await spawn(kernel, "bob")

    assert refusal(await kernel.submit(bob, "board.revise", post(expected_version=1))).code == "not_found"


async def body_of(kernel, text: str) -> str:
    return f"sha256:{await kernel.put_body(text.encode())}"


async def test_get_returns_a_range_with_an_exact_ref(kernel, notes):
    bob = await spawn(kernel, "bob")
    body = await body_of(kernel, "".join(f"line {index}\n" for index in range(1, 11)))
    result_of(await kernel.submit(bob, "board.post", post(body=body)))

    got = result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec", "range": "L3-4"}))

    assert got["text"] == "line 3\nline 4\n" and got["lines"] == 10
    assert got["ref"] == "board/notes/spec@1#L3-4"


async def test_a_range_ref_is_recorded_as_body_exposure(kernel, notes):
    bob = await spawn(kernel, "bob")
    body = await body_of(kernel, "a\nb\nc\n")
    result_of(await kernel.submit(bob, "board.post", post(body=body)))

    await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec", "range": "L2-3"})

    items = of_type(kernel, "context.offered")[-1].data["items"]
    assert [(item["ref"], item["form"]) for item in items] == [
        ("board/notes/spec@1", "gist"),
        ("board/notes/spec@1#L2-3", "body"),
    ]


async def test_a_body_too_big_for_a_result_comes_back_cut_with_a_ref_saying_so(kernel, notes):
    bob = await spawn(kernel, "bob")
    body = await body_of(kernel, "".join(f"{index:060}\n" for index in range(1000)))
    result_of(await kernel.submit(bob, "board.post", post(body=body)))

    got = result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"}))

    assert got["lines"] == 1000 and got["ref"].startswith("board/notes/spec@1#L1-")
    assert got["text"].count("\n") == int(got["ref"].rpartition("-")[2])


async def test_a_long_body_beside_long_fields_is_cut_and_not_refused(kernel, notes):
    bob = await spawn(kernel, "bob")
    body = await body_of(kernel, f"{'x' * 60}\n" * 1000)
    long = post(gist="g" * 280, body=body, fields={"note": "y" * 4000})
    result_of(await kernel.submit(bob, "board.post", long))

    got = result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"}))

    assert got["lines"] == 1000 and "#L1-" in got["ref"]


@pytest.mark.parametrize("wanted", ["L10-40", "L3-1"])
async def test_a_range_no_line_stands_in_is_refused_with_how_many_there_are(kernel, notes, wanted):
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(bob, "board.post", post(body=await body_of(kernel, "one\ntwo\nthree\n"))))

    refused = refusal(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec", "range": wanted}))

    assert refused.code == "invalid" and refused.detail["lines"] == 3


async def test_a_wait_counts_only_versions_you_have_not_read(kernel, notes):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    result_of(await kernel.submit(alice, "board.post", post()))
    result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"}))

    placed = result_of(await kernel.submit(bob, "wait", {"board": ["notes/spec"]}))

    assert placed["state"] == "parked"


async def test_a_wait_after_a_query_counts_only_what_the_query_did_not_show(kernel, notes):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    result_of(await kernel.submit(alice, "board.post", post()))
    result_of(await kernel.submit(bob, "board.query", {"board": "notes"}))

    placed = result_of(await kernel.submit(bob, "wait", {"board": ["notes/spec"]}))

    assert placed["state"] == "parked"


async def test_a_version_you_never_read_holds_a_wait_at_once(kernel, notes):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    result_of(await kernel.submit(alice, "board.post", post()))

    assert result_of(await kernel.submit(bob, "wait", {"board": ["notes/spec"]}))["state"] == "released"


async def test_a_board_that_wakes_says_which_object_changed(kernel):
    await channel(kernel, "notes", kind="board", delivery="wake")
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")

    result_of(await kernel.submit(alice, "board.post", post()))

    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["agents"] == ["bob"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    assert [item["gist"] for item in handed["items"]] == ["spec: first"]


@pytest.mark.parametrize("spelling", ["alice", "@alice", "agent:alice"])
async def test_a_query_takes_any_spelling_of_an_author(kernel, notes, spelling):
    alice = await spawn(kernel, "alice")
    result_of(await kernel.submit(alice, "board.post", post()))

    found = result_of(await kernel.submit(alice, "board.query", {"board": "notes", "author": spelling}))

    assert found["total"] == 1 and found["results"][0]["author"] == "@alice"


async def test_a_read_of_no_board_is_refused_even_for_a_human(kernel, ada):
    assert refusal(await kernel.submit(ada, "board.query", {"board": "nots"})).code == "not_found"
    assert refusal(await kernel.submit(ada, "board.get", {"board": "nots", "name": "x"})).code == "not_found"


async def test_a_body_in_blobs_comes_back_as_its_hash(kernel, notes):
    bob = await spawn(kernel, "bob")
    body = await body_of(kernel, "x" * (70 * 1024))
    result_of(await kernel.submit(bob, "board.post", post(body=body)))

    got = result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"}))

    assert got["body"] == body and "text" not in got
    assert [item["form"] for item in of_type(kernel, "context.offered")[-1].data["items"]] == ["gist"]


async def test_a_redacted_body_stops_at_commit(kernel, notes):
    bob = await spawn(kernel, "bob")
    body = await body_of(kernel, "a secret")
    result_of(await kernel.submit(bob, "board.post", post(body=body)))
    tombstone = {"sha256": body.removeprefix("sha256:")}
    result_of(await kernel.submit(kernel.runtime, "body.tombstone", tombstone))

    got = result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"}))

    assert got["body"] == body and "text" not in got


async def test_an_agents_get_is_a_command_and_a_humans_is_a_query(kernel, notes, ada):
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(bob, "board.post", post()))
    head = kernel.head

    outcome = await kernel.submit(ada, "board.get", {"board": "notes", "name": "spec"})
    assert outcome.seq is None and kernel.head == head

    outcome = await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"})
    assert outcome.seq is not None and of_type(kernel, "context.offered", after=head)


async def posted(kernel, by, count: int = 5) -> None:
    for index in range(count):
        fields = {"kind": "note" if index % 2 else "spec", "rank": index}
        result_of(
            await kernel.submit(by, "board.post", post(f"topic/{index}", f"object number {index}", fields=fields))
        )


async def test_query_carries_exact_refs_the_true_total_and_a_cursor(kernel, notes):
    bob = await spawn(kernel, "bob")
    await posted(kernel, bob)

    page = result_of(await kernel.submit(bob, "board.query", {"board": "notes", "limit": 2}))
    rest = result_of(await kernel.submit(bob, "board.query", {"board": "notes", "after": page["cursor"], "limit": 5}))

    assert [row["ref"] for row in page["results"]] == ["board/notes/topic/0@1", "board/notes/topic/1@1"]
    assert page["total"] == rest["total"] == 5 and len(rest["results"]) == 3


async def test_query_filters_on_fields_and_author(kernel, notes):
    bob, carol = await spawn(kernel, "bob"), await spawn(kernel, "carol")
    await posted(kernel, bob)
    result_of(await kernel.submit(carol, "board.post", post("topic/9", "carol's", fields={"kind": "spec"})))

    specs = result_of(await kernel.submit(bob, "board.query", {"board": "notes", "where": {"kind": "spec"}}))
    mine = result_of(await kernel.submit(bob, "board.query", {"board": "notes", "author": "agent:carol"}))
    prefix = result_of(await kernel.submit(bob, "board.query", {"board": "notes", "prefix": "topic/1"}))

    assert specs["total"] == 4 and mine["total"] == 1 and prefix["total"] == 1


async def test_query_sees_the_latest_version_unless_asked_for_history(kernel, notes):
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(bob, "board.post", post()))
    result_of(await kernel.submit(bob, "board.revise", post(gist="second", expected_version=1)))

    latest = result_of(await kernel.submit(bob, "board.query", {"board": "notes"}))
    history = result_of(await kernel.submit(bob, "board.query", {"board": "notes", "history": True}))

    assert [row["version"] for row in latest["results"]] == [2]
    assert [row["version"] for row in history["results"]] == [1, 2]


async def test_text_search_uses_fts5(kernel, notes):
    bob = await spawn(kernel, "bob")
    await posted(kernel, bob)
    result_of(await kernel.submit(bob, "board.post", post("unique", "a zebra crossed")))

    found = result_of(await kernel.submit(bob, "board.query", {"board": "notes", "text": "zebra"}))

    assert [row["name"] for row in found["results"]] == ["unique"] and found["total"] == 1


@pytest.mark.parametrize("text", ['"', "AND", "a OR", "(", "NEAR(", "*", "col:x"])
async def test_text_search_treats_its_query_as_data(kernel, notes, text):
    bob = await spawn(kernel, "bob")

    assert result_of(await kernel.submit(bob, "board.query", {"board": "notes", "text": text}))["total"] == 0


async def test_text_search_without_fts5_is_refused_with_the_reason(kernel, notes, monkeypatch):
    bob = await spawn(kernel, "bob")
    monkeypatch.setattr(boards, "FTS5", False)

    refused = refusal(await kernel.submit(bob, "board.query", {"board": "notes", "text": "zebra"}))

    assert refused.code == "unsupported" and "FTS5" in refused.detail


async def test_a_where_value_must_be_a_scalar(kernel, notes):
    bob = await spawn(kernel, "bob")

    outcome = await kernel.submit(bob, "board.query", {"board": "notes", "where": {"kind": ["a"]}})

    assert refusal(outcome).code == "invalid"


async def test_a_query_stays_inside_the_result_limit(kernel, notes):
    bob = await spawn(kernel, "bob")
    for index in range(32):
        fields = {"long": "é" * 1000}
        result_of(await kernel.submit(bob, "board.post", post(f"o{index}", "é" * 280, fields=fields)))

    page = result_of(await kernel.submit(bob, "board.query", {"board": "notes", "limit": 32}))

    assert 0 < len(page["results"]) < 32 and page["total"] == 32 and page["cursor"] is not None
