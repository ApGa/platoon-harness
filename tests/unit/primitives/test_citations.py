"""One ref names what a model is shown, a message that carries another event's words is shown by that event's ref, and a
citation is checked and kept as its citer's claim: architecture section 7, Refs and citations."""

import hashlib
import json
import re

import pytest

from platoon_harness.kernel import Kernel, Principal, Tombstones
from platoon_harness.primitives import PRIMITIVES, REF, maker

from .support import (
    channel,
    end_turn,
    enroll,
    events_of,
    grant,
    of_type,
    read,
    refusal,
    report,
    result_of,
    send,
    settle_effects,
    spawn,
    start,
    start_turn,
)

WRITES = {
    "message.send",
    "board.post",
    "board.revise",
    "task.add",
    "task.complete",
    "task.fail",
    "agent.spawn",
    "agent.finish",
}


async def stored(kernel: Kernel, text: str) -> str:
    return f"sha256:{await kernel.put_body(text.encode())}"


async def made(kernel: Kernel, by: Principal, text: str) -> str:
    """The ref of a message `by` sent to the person `ada`, with `text` as its body."""
    return (await send(kernel, by, "@ada", "see the body", body=await stored(kernel, text)))["ref"]


def last_offer_items(kernel: Kernel) -> list[dict]:
    return of_type(kernel, "context.offered")[-1].data["items"]


# Refs on every write.


async def test_every_write_of_content_returns_its_ref(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    await channel(kernel, "notes", kind="board")
    await channel(kernel, "work", kind="queue")
    await start_turn(kernel, "lead")

    refs = [
        (await send(kernel, lead, "@ada", "hi"))["ref"],
        result_of(await kernel.submit(lead, "board.post", {"board": "notes", "name": "spec", "gist": "v1"}))["ref"],
        result_of(
            await kernel.submit(
                lead, "board.revise", {"board": "notes", "name": "spec", "gist": "v2", "expected_version": 1}
            )
        )["ref"],
        result_of(await kernel.submit(lead, "task.add", {"queue": "work", "gist": "one"}))["ref"],
        result_of(await kernel.submit(lead, "task.add", {"queue": "work", "gist": "two"}))["ref"],
    ]
    result_of(await kernel.submit(lead, "task.claim", {"queue": "work", "task": "1"}))
    refs.append(result_of(await kernel.submit(lead, "task.complete", {"queue": "work", "task": "1"}))["ref"])
    result_of(await kernel.submit(lead, "task.claim", {"queue": "work", "task": "2"}))
    refs.append(result_of(await kernel.submit(lead, "task.fail", {"queue": "work", "task": "2"}))["ref"])
    refs.append(result_of(await kernel.submit(lead, "agent.spawn", {"name": "w", "child_role": "worker"}))["ref"])
    refs.append(result_of(await kernel.submit(lead, "agent.finish", {"gist": "all done"}))["ref"])

    by_ref = {f"{event.stream}@{event.version}": event.type for event in events_of(kernel)}
    assert [by_ref[ref] for ref in refs] == [
        "message.sent",
        "board.posted",
        "board.revised",
        "task.added",
        "task.added",
        "task.completed",
        "task.failed",
        "agent.spawned",
        "agent.finished",
    ]
    assert refs[-2] == "agent/w@1"


async def test_an_episode_closes_on_refs_never_on_a_reward(kernel, ada):
    """What an episode came to is cited, checked as any citation is, and what it was worth is no part of it."""
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(ada, "episode.open", {"episode": "e1"}))
    said = (await send(kernel, bob, "@ada", "the answer"))["ref"]

    worth = refusal(await kernel.submit(ada, "episode.close", {"outcome": {"score": 1}}))
    missing = refusal(await kernel.submit(ada, "episode.close", {"based_on": ["inbox/nobody@9"]}))
    result_of(await kernel.submit(ada, "episode.close", {"based_on": [said]}))

    [closed] = of_type(kernel, "episode.closed")
    assert (worth.code, missing.code) == ("invalid", "not_found")
    assert (closed.based_on, closed.data, closed.v) == ((said,), {"episode": "e1"}, 2)


async def test_a_finish_out_of_a_turn_returns_the_ref_of_the_end_that_holds_its_report(kernel):
    bob = await spawn(kernel, "bob")

    ref = result_of(await kernel.submit(bob, "agent.finish", {"gist": "done"}))["ref"]

    ended = of_type(kernel, "agent.ended")[-1]
    assert ref == f"{ended.stream}@{ended.version}" and ended.data["report"] == "done"


async def test_a_task_s_ref_comes_back_from_add_claim_list_and_complete(kernel):
    await channel(kernel, "work", kind="queue")
    bob = await spawn(kernel, "bob")

    added = result_of(await kernel.submit(bob, "task.add", {"queue": "work", "gist": "do it"}))
    claimed = result_of(await kernel.submit(bob, "task.claim", {"queue": "work"}))
    done = result_of(await kernel.submit(bob, "task.complete", {"queue": "work", "gist": "did it"}))
    listed = result_of(await kernel.submit(bob, "task.list", {"queue": "work"}))["tasks"][0]

    assert added["ref"] == claimed["ref"] == listed["ref"] == "task/work/1@1"
    assert done["ref"] == listed["result_ref"] == "task/work/1@3"
    assert (claimed["body"], listed["body"], listed["result_body"]) == (False, False, False)
    assert "text" not in claimed


# Carried messages.


async def test_a_board_write_s_wake_hands_over_the_write_s_ref(kernel):
    await channel(kernel, "notes", kind="board", delivery="wake")
    writer, _ = await spawn(kernel, "writer"), await spawn(kernel, "bob")

    posted = result_of(await kernel.submit(writer, "board.post", {"board": "notes", "name": "spec", "gist": "v1"}))
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    assert posted["ref"] == "board/notes/spec@1"
    assert [item["ref"] for item in handed["items"]] == ["board/notes/spec@1"]
    assert [item["ref"] for item in last_offer_items(kernel)] == ["board/notes/spec@1"]
    announce = of_type(kernel, "message.sent")[-1]
    assert announce.stream == "board/notes" and announce.data["carries"] == "board/notes/spec@1"
    assert announce.cause == (of_type(kernel, "board.posted")[0].seq,)


async def test_a_child_s_report_is_handed_over_by_the_ref_of_what_it_carries(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "said", by=lead)
    await spawn(kernel, "finished", by=lead)
    await spawn(kernel, "cancelled", by=lead)

    await start_turn(kernel, "said")
    await report(kernel, "said", "item", kind="message", gist="here it is")
    await end_turn(kernel, "said")
    await start_turn(kernel, "finished")
    finish = {"gist": "all done", "body": await stored(kernel, "the long report")}
    finished = result_of(await kernel.submit(Principal(id="agent:finished"), "agent.finish", finish))["ref"]
    await end_turn(kernel, "finished")
    result_of(await kernel.submit(lead, "agent.cancel", {"agent": "@cancelled"}))

    entries = (await read(kernel, lead, "@lead"))["entries"]
    item = of_type(kernel, "item.recorded")[-1]
    ended = next(event for event in of_type(kernel, "agent.ended") if event.agent == "cancelled")
    assert [(entry["subject"], entry["ref"]) for entry in entries] == [
        ("said", f"{item.stream}@{item.version}"),
        ("finished", finished),
        ("cancelled", f"{ended.stream}@{ended.version}"),
    ]
    read_on = result_of(await kernel.submit(lead, "blob.get", {"ref": finished}))
    assert read_on["text"] == "the long report"


async def test_a_turn_that_said_nothing_is_reported_by_the_ref_of_its_end(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", by=lead)

    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob", "failed: it broke")

    entry = (await read(kernel, lead, "@lead"))["entries"][0]
    ended = of_type(kernel, "turn.ended")[-1]
    assert entry["ref"] == f"{ended.stream}@{ended.version}" and "turn failed: it broke" in entry["gist"]


async def test_a_retold_goal_is_handed_over_by_its_spawn_s_ref(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    body = await stored(kernel, "the whole goal")
    spawned = {"name": "bob", "child_role": "worker", "goal": "do it", "body": body}
    result_of(await kernel.submit(lead, "agent.spawn", spawned))
    await settle_effects(kernel, "bob")
    await start(kernel, "bob")

    result_of(await kernel.submit(kernel.runtime, "agent.retell", {"agent": "bob"}))

    told = of_type(kernel, "message.sent")[-1]
    assert (told.stream, told.data["carries"], told.cause) == (
        "inbox/bob",
        "agent/bob@1",
        (of_type(kernel, "agent.spawned")[-1].seq,),
    )
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    assert [(item["ref"], item["body"]) for item in handed["items"]] == [("agent/bob@1", True)]
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "input.delivered", input=str(handed["input"]), boundary="turn", evidence="userMessage")
    first = (await send(kernel, Principal(id="agent:bob"), "@lead", "on it"))["ref"]
    history = result_of(kernel.query(kernel.runtime, "lineage", {"ref": first}))["history"]
    reached = result_of(kernel.query(kernel.runtime, "contributors", {"ref": first}))
    assert [shown["ref"] for row in history for shown in row["shown"]] == ["agent/bob@1"]
    assert [(row["maker"], row["to"]) for row in reached["handed_only"]] == [("agent:lead", ["agent:bob"])]


async def test_a_reply_to_a_carried_message_finds_it_by_the_ref_it_was_shown_by(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", by=lead, stays=True)
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="a question")
    await end_turn(kernel, "bob")
    entry = (await read(kernel, lead, "@lead"))["entries"][0]

    replied = await send(kernel, lead, "@bob", "an answer", reply_to=entry["ref"])

    sent = of_type(kernel, "message.sent")[-1]
    assert entry["ref"].startswith("turn/bob@")
    assert sent.cause == (entry["seq"],) and sent.correlation == entry["ref"]
    assert replied["ref"] == "inbox/bob@1"
    missing = await kernel.submit(lead, "message.send", {"to": "@bob", "gist": "x", "reply_to": "turn/bob@999"})
    assert refusal(missing).code == "not_found"


# Reading a body by its event.


async def test_blob_get_reads_only_what_its_caller_was_handed_or_made(kernel, ada):
    bob, carol = await spawn(kernel, "bob"), await spawn(kernel, "carol")
    mine = await made(kernel, bob, "bob's own words")
    sent = await send(kernel, ada, "@carol", "for carol", body=await stored(kernel, "carol's words"))

    assert result_of(await kernel.submit(bob, "blob.get", {"ref": mine}))["text"] == "bob's own words"
    never = refusal(await kernel.submit(carol, "blob.get", {"ref": mine}))
    unread = refusal(await kernel.submit(carol, "blob.get", {"ref": sent["ref"]}))
    nothing = refusal(await kernel.submit(carol, "blob.get", {"ref": "inbox/ada@99"}))
    await read(kernel, carol, "@carol")
    handed = result_of(await kernel.submit(carol, "blob.get", {"ref": sent["ref"]}))

    assert {never.code, unread.code, nothing.code} == {"not_found"}
    assert never.detail == f"no body you were handed is at {mine}"
    assert handed["text"] == "carol's words"


async def test_a_group_member_cannot_read_on_in_an_entry_not_addressed_to_it(kernel):
    result_of(await kernel.submit(kernel.runtime, "group.define", {"name": "crew", "roles": ["worker"]}))
    alice = await spawn(kernel, "alice")
    sent = await send(kernel, alice, "+crew", "before you came", body=await stored(kernel, "the plan"))
    late = await spawn(kernel, "late")

    assert refusal(await kernel.submit(late, "blob.get", {"ref": sent["ref"]})).code == "not_found"


async def test_a_person_may_read_any_body_by_its_event(kernel, ada):
    bob = await spawn(kernel, "bob")
    ref = await made(kernel, bob, "anyone may read this")
    head = kernel.head

    assert result_of(await kernel.submit(ada, "blob.get", {"ref": ref}))["text"] == "anyone may read this"
    assert kernel.head == head


async def test_a_body_hash_is_no_ref_for_blob_get(kernel):
    bob = await spawn(kernel, "bob")

    assert refusal(await kernel.submit(bob, "blob.get", {"ref": await stored(kernel, "x")})).code == "invalid"


async def test_a_blob_comes_back_cut_with_a_ref_to_the_rest(kernel, ada):
    bob = await spawn(kernel, "bob")
    ref = await made(kernel, bob, "a line of a long body\n" * 2000)

    first = result_of(await kernel.submit(bob, "blob.get", {"ref": ref}))
    last = int(first["ref"].rpartition("-")[2])

    assert first["ref"].startswith(f"{ref}#L1-")
    assert first["lines"] == 2000
    assert first["rest"] == f"{ref}#L{last + 1}-2000"
    assert result_of(await kernel.submit(bob, "blob.get", {"ref": first["rest"]}))["rest"] is not None


async def test_the_exposure_of_a_cut_blob_names_the_lines_shown(kernel, ada):
    bob = await spawn(kernel, "bob")
    ref = await made(kernel, bob, "one\ntwo\nthree\n")

    result_of(await kernel.submit(bob, "blob.get", {"ref": f"{ref}#L2-2"}))

    assert last_offer_items(kernel)[0] == {
        "ref": f"{ref}#L2-2",
        "form": "body",
        "digest": hashlib.sha256(b"two\n").hexdigest(),
    }


async def test_a_blob_range_past_the_end_says_how_many_lines_there_are(kernel, ada):
    bob = await spawn(kernel, "bob")
    ref = await made(kernel, bob, "one\ntwo\n")

    assert refusal(await kernel.submit(bob, "blob.get", {"ref": f"{ref}#L9-10"})).detail["lines"] == 2


async def test_an_empty_blob_is_text(kernel, ada):
    bob = await spawn(kernel, "bob")

    assert result_of(await kernel.submit(bob, "blob.get", {"ref": await made(kernel, bob, "")}))["text"] == ""


async def test_a_blob_held_outside_the_journal_comes_back_for_a_surface_to_fetch(kernel, ada):
    bob = await spawn(kernel, "bob")
    body = await stored(kernel, "x" * (70 * 1024))
    ref = (await send(kernel, bob, "@ada", "big", body=body))["ref"]
    head = kernel.head

    assert result_of(await kernel.submit(bob, "blob.get", {"ref": ref})) == {"ref": ref, "text": None}
    assert of_type(kernel, "context.offered", after=head) == []
    assert result_of(kernel.query(kernel.runtime, "blob.hash", {"ref": ref})) == body


async def test_a_blob_too_long_for_a_result_comes_back_without_text(kernel, ada):
    bob = await spawn(kernel, "bob")

    assert (
        result_of(await kernel.submit(bob, "blob.get", {"ref": await made(kernel, bob, "x" * (20 * 1024))}))["text"]
        is None
    )


async def test_a_surface_records_what_it_showed_of_a_body_by_its_event(kernel, ada):
    bob = await spawn(kernel, "bob")
    ref = await made(kernel, bob, "x" * (70 * 1024))
    offer = {"agent": "bob", "ref": f"{ref}#L1-3", "digest": "0" * 64}

    result_of(await kernel.submit(kernel.runtime, "blob.offer", offer))

    offered = of_type(kernel, "context.offered")[-1]
    assert offered.data["how"] == "read"
    assert offered.data["items"] == [{"ref": offer["ref"], "form": "body", "digest": offer["digest"]}]
    assert refusal(await kernel.submit(bob, "blob.offer", offer)).code == "not_permitted"


async def test_a_body_exposure_has_one_spelling(kernel, ada):
    await channel(kernel, "notes", kind="board")
    bob = await spawn(kernel, "bob")
    body = await stored(kernel, "line one\nline two\n")
    sent = await send(kernel, ada, "@bob", "with a body", body=body)
    post = {"board": "notes", "name": "spec", "gist": "v1", "body": body}
    result_of(await kernel.submit(bob, "board.post", post))
    head = kernel.head

    await read(kernel, bob, "@bob", bodies=True)
    result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec", "range": "L2-2"}))
    result_of(await kernel.submit(bob, "blob.get", {"ref": f"{sent['ref']}#L1-1"}))
    offer = {"agent": "bob", "ref": "board/notes/spec@1#L1-2", "digest": "0" * 64}
    result_of(await kernel.submit(kernel.runtime, "blob.offer", offer))

    bodies = [
        item["ref"]
        for event in of_type(kernel, "context.offered", after=head)
        for item in event.data["items"]
        if item["form"] == "body"
    ]
    assert bodies == ["inbox/bob@1", "board/notes/spec@1#L2-2", "inbox/bob@1#L1-1", "board/notes/spec@1#L1-2"]
    assert all(re.fullmatch(REF, ref) for ref in bodies)
    assert {event.v for event in of_type(kernel, "context.offered", after=head)} == {3}


async def test_an_offered_item_s_digest_covers_what_was_shown(kernel):
    await channel(kernel, "notes", kind="board")
    bob = await spawn(kernel, "bob")
    post = {"board": "notes", "name": "spec", "gist": "v1", "fields": {"state": "draft"}}
    result_of(await kernel.submit(bob, "board.post", post))

    result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"}))
    got = last_offer_items(kernel)[0]
    result_of(await kernel.submit(bob, "board.query", {"board": "notes"}))
    found = last_offer_items(kernel)[0]

    shown = json.dumps(["v1", {"state": "draft"}], ensure_ascii=False, sort_keys=True).encode()
    assert got == found == {"ref": "board/notes/spec@1", "form": "gist", "digest": hashlib.sha256(shown).hexdigest()}


# Citations.


def test_every_write_of_content_takes_based_on():
    """So does `episode.close`, which writes no content and cites what its part of the session came to."""
    takes = {
        operation.name
        for extension in PRIMITIVES
        for operation in extension.ops
        if "based_on" in operation.input.model_json_schema().get("properties", {})
    }
    described = {
        operation.input.model_json_schema()["properties"]["based_on"]["description"]
        for extension in PRIMITIVES
        for operation in extension.ops
        if operation.name in takes
    }

    assert takes == WRITES | {"episode.close"}
    assert described == {"Refs this write rests on.", "The refs of what this part of the session came to."}
    assert not [op.name for ext in PRIMITIVES for op in ext.ops if op.tool and "Cite" in (op.fn.__doc__ or "")]


@pytest.mark.parametrize(
    ("cited", "code", "said"),
    [
        ("{body}", "invalid", "a body's hash is no ref"),
        ("{ref}#L5-3", "invalid", "names no lines"),
        ("{ref}#banana", "invalid", "names no lines"),
        ("{ref}#L2-9", "invalid", "names lines past the end of its body"),
        ("agent/bob@1#L1-1", "invalid", "names lines of an event that has no body"),
        ("inbox/ada@99", "not_found", "nothing is inbox/ada@99"),
        ("no ref at all", "invalid", "is no ref"),
    ],
)
async def test_a_citation_must_name_an_existing_event_and_lines_that_exist(kernel, ada, cited, code, said):
    bob = await spawn(kernel, "bob")
    body = await stored(kernel, "one\ntwo\n")
    ref = (await send(kernel, bob, "@ada", "two lines", body=body))["ref"]
    named = cited.format(body=body, ref=ref)
    head = kernel.head

    refused = refusal(await kernel.submit(bob, "message.send", {"to": "@ada", "gist": "x", "based_on": [named]}))

    assert refused.code == code
    detail = refused.detail if isinstance(refused.detail, str) else refused.detail["detail"]
    assert said in detail and (named[:20] in detail or named.startswith("sha256:"))
    assert "sha256:" not in detail
    assert of_type(kernel, "message.sent", after=head) == []
    if "past the end" in said:
        assert refused.detail["lines"] == 2


async def test_each_ref_cited_and_each_body_it_names_is_looked_at_once(kernel, ada, monkeypatch):
    """A citation is checked in the writer, so repeating a ref or naming one body by many ranges costs no more."""
    bob = await spawn(kernel, "bob")
    ref = (await send(kernel, bob, "@ada", "two lines", body=await stored(kernel, "one\ntwo\n")))["ref"]
    looked: list[str] = []
    inline = Tombstones.inline
    monkeypatch.setattr(Tombstones, "inline", lambda self, sha256: looked.append(sha256) or inline(self, sha256))
    based_on = [f"{ref}#L1-1"] * 200 + [f"{ref}#L1-2", f"{ref}#L2-2"]

    await send(kernel, bob, "@ada", "on those lines", based_on=based_on)

    assert len(looked) == 1 and of_type(kernel, "message.sent")[-1].based_on == tuple(based_on)


async def test_a_citation_too_long_for_an_event_is_refused_before_any_ref_is_looked_at(kernel, ada):
    bob = await spawn(kernel, "bob")
    based_on = [f"inbox/nobody@{n}" for n in range(1, 2000)]

    refused = refusal(await kernel.submit(bob, "message.send", {"to": "@ada", "gist": "x", "based_on": based_on}))

    assert refused.code == "invalid" and "based_on exceeds 16384 bytes" in str(refused.detail)


async def test_a_citation_of_lines_of_a_body_in_blobs_is_kept_as_given(kernel, ada):
    bob = await spawn(kernel, "bob")
    ref = (await send(kernel, bob, "@ada", "big", body=await stored(kernel, "x\n" * 40000)))["ref"]
    ranged = f"{ref}#L1-999999"

    await send(kernel, bob, "@ada", "on it", based_on=[ranged])

    assert of_type(kernel, "message.sent")[-1].based_on == (ranged,)


async def test_a_citation_of_what_its_citer_was_never_handed_is_kept_as_its_claim(kernel, ada):
    bob, carol = await spawn(kernel, "bob"), await spawn(kernel, "carol")
    ref = await made(kernel, bob, "bob's words")

    await send(kernel, carol, "@ada", "I rest on it", based_on=[ref])

    sent = of_type(kernel, "message.sent")[-1]
    assert sent.based_on == (ref,) and maker(sent) == "agent:carol"


async def test_a_person_or_a_program_may_cite_any_event(kernel, ada):
    bob = await spawn(kernel, "bob")
    ref = await made(kernel, bob, "bob's words")
    program = Principal(id="program:driver")
    await enroll(kernel, program)
    await grant(kernel, "program")

    await send(kernel, ada, "@bob", "from a person", based_on=[ref])
    await send(kernel, program, "@bob", "from a program", based_on=[f"{ref}#L1-1"])
    refused = refusal(await kernel.submit(ada, "message.send", {"to": "@bob", "gist": "x", "based_on": ["x@9"]}))

    assert [event.based_on for event in of_type(kernel, "message.sent")[-2:]] == [(ref,), (f"{ref}#L1-1",)]
    assert refused.code == "not_found"


async def test_a_spawn_and_a_finish_carry_their_citations(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    ref = await made(kernel, lead, "the plan")
    await start_turn(kernel, "lead")

    spawned = {"name": "bob", "child_role": "worker", "goal": "do it", "based_on": [ref]}
    result_of(await kernel.submit(lead, "agent.spawn", spawned))
    result_of(await kernel.submit(lead, "agent.finish", {"gist": "handed off", "based_on": ["agent/bob@1"]}))

    assert of_type(kernel, "agent.spawned")[-1].based_on == (ref,)
    assert of_type(kernel, "agent.finished")[-1].based_on == ("agent/bob@1",)


# Makers.


async def test_the_maker_of_a_spawn_is_its_spawner_in_its_spawner_s_turn(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await start_turn(kernel, "lead", "t7")

    result_of(await kernel.submit(lead, "agent.spawn", {"name": "bob", "child_role": "worker"}))

    spawned = of_type(kernel, "agent.spawned")[-1]
    added = of_type(kernel, "principal.added")[-1]
    assert (spawned.agent, spawned.turn, maker(spawned)) == ("lead", "t7", "agent:lead")
    assert spawned.context_version == of_type(kernel, "turn.started")[-1].context_version
    assert added.agent == "bob" and spawned.v == 3
    assert (await send(kernel, lead, "@bob", "hello"))["ref"] == "inbox/bob@1"


async def test_the_maker_of_a_runtime_event_is_the_agent_it_is_about(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", by=lead)
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="done")
    await end_turn(kernel, "bob")

    told = of_type(kernel, "message.sent")[-1]

    assert (told.actor, maker(told)) == ("runtime", "agent:bob")
    assert maker(of_type(kernel, "turn.ended")[-1]) == "agent:bob"
