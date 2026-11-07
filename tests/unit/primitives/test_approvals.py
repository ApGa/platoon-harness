"""Approvals: four facts, one winner, a policy stated at open, and the whole of what each asks."""

import json

import pytest

from platoon_harness import Session
from platoon_harness.kernel import Kernel, ManualClock, Principal
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.primitives.approvals import ASK_LIMIT
from platoon_harness.testing import Ask

from ..runtime import support as running
from .support import approval, enroll, grant, of_type, refusal, report, result_of, send, spawn, start_turn


async def ask(kernel, id: str = "a1", agent: str = "bob", **fields) -> None:
    args = {"id": id, "agent": agent, "gist": "May I run this?", **fields}
    result_of(await kernel.submit(kernel.runtime, "approval.request", args))


def resolving(verdict: str = "allow", version: int = 1, **fields) -> dict:
    return {"id": "a1", "verdict": verdict, "expected_version": version, **fields}


async def test_an_answer_does_not_wait_behind_a_hung_delivery(kernel, ada):
    await spawn(kernel, "bob", role="steerer", ready={"boundaries": ["tool", "turn"]})
    await start_turn(kernel, "bob")
    await send(kernel, kernel.runtime, "@bob", "steer")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    deliver = result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"}))[0]
    result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": deliver["id"]}))
    await ask(kernel)

    result_of(await kernel.submit(ada, "approval.resolve", resolving()))

    assert [effect["kind"] for effect in result_of(kernel.query(kernel.runtime, "effect.ready", {}))] == ["answer"]


@pytest.mark.parametrize("ending", ["a crash", "the turn's end"])
async def test_an_approval_goes_moot_with_the_turn_that_asked(kernel, ada, ending):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await ask(kernel)

    if ending == "a crash":
        result_of(await kernel.recover())
    else:
        await report(kernel, "bob", "turn.ended")

    assert result_of(kernel.query(kernel.runtime, "session.status", {}))["asking"] == 0
    assert [row for row in result_of(kernel.query(ada, "attention.list", {})) if row["kind"] == "approval"] == []
    assert refusal(await kernel.submit(ada, "approval.resolve", resolving(version=1))).code == "conflict"


async def test_a_request_is_shown_with_actions_carrying_the_version(kernel, ada):
    await spawn(kernel, "bob")

    await ask(kernel)

    row = result_of(kernel.query(ada, "attention.list", {}))[0]
    assert row["kind"] == "approval" and row["version"] == 1
    assert [action["args"] for action in row["actions"]] == [
        {"id": "a1", "verdict": "allow", "expected_version": 1},
        {"id": "a1", "verdict": "deny", "expected_version": 1},
    ]


async def test_four_facts_stay_apart(kernel, ada):
    await spawn(kernel, "bob")
    await ask(kernel)
    assert approval(kernel).state == "pending"

    result_of(await kernel.submit(ada, "approval.resolve", resolving()))
    decided = approval(kernel)
    assert decided.state == "resolved" and not decided.answered and decided.outcome is None

    effect = result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "answer"}))[0]
    started = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
    result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": effect["id"], "attempt": started}))
    assert approval(kernel).answered and approval(kernel).outcome is None

    await report(kernel, "bob", "item", kind="tool", gist="command ran", approval="a1", outcome="declined")
    assert approval(kernel).outcome == "declined"


async def test_the_first_commit_wins_and_the_loser_gets_conflict_naming_the_winner(kernel, ada):
    bea = Principal(id="human:bea")
    await enroll(kernel, bea)
    await spawn(kernel, "bob")
    await ask(kernel)
    result_of(await kernel.submit(ada, "approval.resolve", resolving(via="tui")))

    refused = refusal(await kernel.submit(bea, "approval.resolve", resolving("deny", via="web")))

    assert refused.code == "conflict"
    assert refused.detail == {"state": "resolved", "resolved_by": "human:ada", "via": "tui"}
    assert approval(kernel).verdict == "allow"


async def test_resolve_requires_expected_version(kernel, ada):
    await spawn(kernel, "bob")
    await ask(kernel)

    outcome = await kernel.submit(ada, "approval.resolve", {"id": "a1", "verdict": "allow"})

    assert refusal(outcome).code == "invalid"


async def test_a_stale_expected_version_is_a_conflict(kernel, ada):
    await spawn(kernel, "bob")
    await ask(kernel)

    assert refusal(await kernel.submit(ada, "approval.resolve", resolving(version=7))).code == "conflict"


async def test_a_resolved_approval_leaves_attention(kernel, ada):
    await spawn(kernel, "bob")
    await ask(kernel)

    result_of(await kernel.submit(ada, "approval.resolve", resolving()))

    assert result_of(kernel.query(ada, "attention.list", {})) == []


async def test_a_message_from_an_agent_can_never_carry_an_approval(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await ask(kernel)

    assert refusal(await kernel.submit(alice, "approval.resolve", resolving())).code == "not_permitted"
    assert not kernel.ops["approval.resolve"].tool
    assert "verdict" not in kernel.ops["message.send"].input.model_fields


async def test_ending_an_agent_closes_its_pending_requests_as_moot(kernel, ada):
    await spawn(kernel, "bob")
    await ask(kernel)

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    assert approval(kernel).state == "moot"
    assert refusal(await kernel.submit(ada, "approval.resolve", resolving())).code == "conflict"


async def test_a_request_from_nobody_is_refused(kernel):
    args = {"id": "a1", "agent": "ghost", "gist": "x"}

    assert refusal(await kernel.submit(kernel.runtime, "approval.request", args)).code == "not_found"


async def test_a_request_id_is_used_once(kernel):
    await spawn(kernel, "bob")
    await ask(kernel)
    args = {"id": "a1", "agent": "bob", "gist": "again"}

    assert refusal(await kernel.submit(kernel.runtime, "approval.request", args)).code == "conflict"


@pytest.mark.parametrize(("policy", "verdict"), [("allow", "allow"), ("deny", "deny")])
async def test_policy_is_a_durable_session_setting_journaled_at_open(tmp_path, policy, verdict):
    folder = tmp_path / "policy"
    kernel = Kernel.open(folder, clock=ManualClock(1.0), extensions=PRIMITIVES)
    args = {"roles": {"worker": {"approvals": policy}}}
    result_of(await kernel.submit(kernel.runtime, "session.open", args))
    await grant(kernel, "agent")
    await spawn(kernel, "bob")
    kernel.close()

    kernel = Kernel.open(folder, clock=ManualClock(2.0), extensions=PRIMITIVES)
    await ask(kernel)

    decided = approval(kernel)
    assert (decided.state, decided.verdict, decided.resolved_by, decided.via) == (
        "resolved",
        verdict,
        "policy",
        "policy",
    )
    assert of_type(kernel, "session.opened")[0].data["roles"]["worker"]["approvals"] == policy
    assert result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "answer"}))
    kernel.close()


async def test_a_policy_decision_never_reaches_attention(tmp_path):
    kernel = Kernel.open(tmp_path / "policy", clock=ManualClock(1.0), extensions=PRIMITIVES)
    result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"worker": {"approvals": "allow"}}}))
    await spawn(kernel, "bob")

    await ask(kernel)

    assert result_of(kernel.query(kernel.runtime, "attention.list", {})) == []
    kernel.close()


async def test_an_approval_s_whole_ask_is_its_body_redacted_and_bounded(kernel, ada):
    """The ask is the body of the approval's first event, which `blob.get` reads whole. One the journal does not hold in
    its row is refused, as nobody could read it, and a person redacts one as any body."""
    await spawn(kernel, "bob")
    whole = "Edit " + json.dumps({"file_path": "app.py", "new_string": "line of the new file\n" * 40})
    body = f"sha256:{await kernel.put_body(whole.encode())}"
    past = f"sha256:{await kernel.put_body(b'x' * (ASK_LIMIT + 1))}"

    await ask(kernel, body=body)
    refused = await kernel.submit(
        kernel.runtime, "approval.request", {"id": "a2", "agent": "bob", "gist": "", "body": past}
    )

    asked = of_type(kernel, "approval.requested")[0]
    assert (asked.v, asked.data["body"], asked.data["cut"]) == (2, body, 0)
    assert result_of(await kernel.submit(ada, "blob.get", {"ref": "approval/a1@1"}))["text"] == whole
    assert refusal(refused).code == "invalid"
    result_of(await kernel.submit(ada, "body.tombstone", {"sha256": body.removeprefix("sha256:")}))
    assert refusal(await kernel.submit(ada, "blob.get", {"ref": "approval/a1@1"})).code == "not_found"


async def test_an_ask_past_its_bound_is_cut_and_says_where(tmp_path):
    """At the end of the last whole character within 64 KiB, which here falls inside a line and between a character's
    two bytes, so the ask stays text that `blob.get` reads, and its record counts the bytes it left out, so a reader can
    say where it was cut and how much followed."""
    whole = "xy" + ("é" * 99 + "\n") * 400
    team = running.solo([Ask("run the long one?", body=whole)])

    async with Session.start(team, root=tmp_path, clock=ManualClock(1000.0)) as session:
        await running.in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        [asked] = await running.until(lambda: running.of_type(session, "approval.requested"), session)
        kept = await session.get_body(asked.data["body"])
        read = await session.blob(f"{asked.stream}@{asked.version}")

    assert len(kept) == ASK_LIMIT - 1 and whole.encode().startswith(kept)
    assert asked.data["cut"] == len(whole.encode()) - len(kept)
    assert kept.decode().startswith(read["text"]) and read["lines"] == kept.count(b"\n") + 1
    assert asked.gist == "run the long one?"
