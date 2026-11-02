"""`authorize`: grants, relations on the live graph, scopes and credentials."""

import asyncio

import pytest

from platoon_harness.kernel import Principal, Refused, hash_token

from .support import ALICE, BOB, HUMAN, enroll, events_of, grant, refusal_of, refused_code, result_of

LEAD = Principal(id="agent:lead")
WORKER = Principal(id="agent:worker")
PEER = Principal(id="agent:peer")
GRANDCHILD = Principal(id="agent:grandchild")


async def family(kernel):
    await enroll(kernel, LEAD, role="lead")
    await enroll(kernel, WORKER, role="worker", parent="agent:lead")
    await enroll(kernel, PEER, role="worker", parent="agent:lead")
    await enroll(kernel, GRANDCHILD, role="worker", parent="agent:worker")
    await enroll(kernel, HUMAN)


async def allowed(kernel, principal, stream):
    outcome = await kernel.submit(principal, "note.add", {"stream": stream})
    return outcome.refusal is None


async def test_absence_of_a_grant_means_deny(kernel):
    await enroll(kernel, ALICE)
    assert refusal_of(await kernel.submit(ALICE, "note.add", {})) == "not_permitted"


async def test_an_unenrolled_principal_is_denied(kernel):
    await grant(kernel, "all")
    assert refusal_of(await kernel.submit(ALICE, "note.add", {})) == "not_permitted"


async def test_grants_name_an_id_a_kind_a_role_or_all(kernel):
    await family(kernel)
    await grant(kernel, "human", "note.add", "note/a")
    await grant(kernel, "agent:worker", "note.add", "note/b")
    await grant(kernel, "role:lead", "note.add", "note/c")
    await grant(kernel, "all", "note.add", "note/d")

    assert await allowed(kernel, HUMAN, "note/a")
    assert not await allowed(kernel, LEAD, "note/a")
    assert await allowed(kernel, WORKER, "note/b")
    assert not await allowed(kernel, PEER, "note/b")
    assert await allowed(kernel, LEAD, "note/c")
    assert await allowed(kernel, PEER, "note/d")


async def test_ops_and_objects_match_by_glob(kernel):
    await family(kernel)
    await grant(kernel, "human", "note.*", "note/x/*")

    assert await allowed(kernel, HUMAN, "note/x/deep/down")
    assert not await allowed(kernel, HUMAN, "note/y")
    assert refusal_of(await kernel.submit(HUMAN, "grant.add", {"who": "all", "ops": "*"})) == "not_permitted"


@pytest.mark.parametrize(
    ("pattern", "actor", "reachable", "unreachable"),
    [
        ("inbox/{self}", WORKER, "worker", "peer"),
        ("inbox/{parent}", WORKER, "lead", "peer"),
        ("inbox/{children}", LEAD, "worker", "grandchild"),
        ("inbox/{siblings}", WORKER, "peer", "worker"),
        ("inbox/{ancestors}", GRANDCHILD, "lead", "peer"),
        ("inbox/{descendants}", LEAD, "grandchild", "lead"),
        ("inbox/{all}", PEER, "ada", "nobody"),
        ("inbox/{human}", PEER, "ada", "lead"),
        ("inbox/{role:worker}", LEAD, "peer", "lead"),
    ],
)
async def test_relations_are_evaluated_on_the_live_graph(kernel, pattern, actor, reachable, unreachable):
    await family(kernel)
    await grant(kernel, "all", "note.add", pattern)

    assert await allowed(kernel, actor, f"inbox/{reachable}")
    assert not await allowed(kernel, actor, f"inbox/{unreachable}")


async def test_a_relation_stays_true_as_the_graph_changes(kernel):
    await family(kernel)
    await grant(kernel, "agent:lead", "note.add", "inbox/{children}")
    assert not await allowed(kernel, LEAD, "inbox/newcomer")

    await enroll(kernel, Principal(id="agent:newcomer"), parent="agent:lead")
    assert await allowed(kernel, LEAD, "inbox/newcomer")

    result_of(await kernel.submit(kernel.runtime, "principal.revoke", {"id": "agent:newcomer"}))
    assert not await allowed(kernel, LEAD, "inbox/newcomer")


async def test_a_path_prefix_does_not_confuse_descendants(kernel):
    await enroll(kernel, Principal(id="agent:a"))
    await enroll(kernel, Principal(id="agent:ab"))
    await grant(kernel, "agent:a", "note.add", "inbox/{descendants}")
    assert not await allowed(kernel, Principal(id="agent:a"), "inbox/ab")


async def test_a_namesake_of_another_kind_is_not_a_relative(kernel):
    await enroll(kernel, Principal(id="agent:x"))
    await enroll(kernel, Principal(id="human:x"))
    await grant(kernel, "agent:x", "note.add", "inbox/{descendants}")
    assert not await allowed(kernel, Principal(id="agent:x"), "inbox/x")

    await enroll(kernel, Principal(id="agent:y"), parent="agent:x")
    assert await allowed(kernel, Principal(id="agent:x"), "inbox/y")


async def test_an_unknown_relation_is_refused_at_the_grant(kernel):
    outcome = await kernel.submit(kernel.runtime, "grant.add", {"who": "all", "ops": "*", "on": "inbox/{next}"})
    assert refusal_of(outcome) == "unsupported"


async def test_removing_a_grant_removes_the_permission(kernel):
    await family(kernel)
    await grant(kernel, "human", "note.add", "note/a")
    result_of(await kernel.submit(kernel.runtime, "grant.remove", {"who": "human", "ops": "note.add", "on": "note/a"}))
    assert not await allowed(kernel, HUMAN, "note/a")


async def test_scopes_only_attenuate(kernel):
    await enroll(kernel, ALICE, scopes=["note.list"])
    await enroll(kernel, BOB, scopes=["note.*"])
    await grant(kernel, "agent:alice", "note.*")

    assert result_of(kernel.query(ALICE, "note.list", {})) == []
    assert refusal_of(await kernel.submit(ALICE, "note.add", {})) == "not_permitted"
    assert refusal_of(await kernel.submit(BOB, "note.add", {})) == "not_permitted"


async def test_runtime_only_ops_cannot_be_granted(kernel):
    await enroll(kernel, HUMAN)
    await grant(kernel, "all", "*", "*")

    for op_name, args in (("note.reset", {}), ("effect.start", {"id": 1}), ("principal.revoke", {"id": "x"})):
        assert refusal_of(await kernel.submit(HUMAN, op_name, args)) == "not_permitted"
    assert result_of(await kernel.submit(kernel.runtime, "note.reset", {})) is None


async def test_the_runtime_takes_no_grant(kernel):
    assert result_of(await kernel.submit(kernel.runtime, "note.add", {}))


async def test_credentials_resolve_by_hash(kernel):
    await enroll(kernel, ALICE, token="s3cret", role="worker")

    principal = kernel.authenticate("s3cret")

    assert principal.id == "agent:alice"
    assert principal.role == "worker"
    with pytest.raises(Refused) as error:
        kernel.authenticate("wrong")
    assert refused_code(error) == "not_permitted"


async def test_revoking_ends_a_credential_and_its_permissions(kernel):
    await enroll(kernel, ALICE, token="s3cret")
    await grant(kernel, "all")
    principal = kernel.authenticate("s3cret")

    result_of(await kernel.submit(kernel.runtime, "principal.revoke", {"id": "agent:alice"}))

    with pytest.raises(Refused):
        kernel.authenticate("s3cret")
    assert refusal_of(await kernel.submit(principal, "note.add", {})) == "not_permitted"


async def test_an_ended_agent_loses_its_token_in_the_same_event(kernel):
    await enroll(kernel, ALICE, token="s3cret")
    args = {"type": "agent.ended", "stream": "agent/alice", "agent": "alice"}
    result_of(await kernel.submit(kernel.runtime, "note.mark", args))

    with pytest.raises(Refused):
        kernel.authenticate("s3cret")


async def test_tokens_never_enter_the_journal(kernel, folder):
    await enroll(kernel, ALICE, token="s3cret-value")
    await asyncio.gather(kernel.submit(kernel.runtime, "note.add", {}))
    kernel.close()

    stored = b"".join(path.read_bytes() for path in folder.iterdir() if path.is_file())

    assert b"s3cret-value" not in stored
    assert hash_token("s3cret-value").encode() in stored


async def test_adding_a_principal_is_checked(kernel):
    await enroll(kernel, ALICE)
    add = "principal.add"
    assert refusal_of(await kernel.submit(kernel.runtime, add, {"id": "agent:alice"})) == "conflict"
    assert refusal_of(await kernel.submit(kernel.runtime, add, {"id": "runtime"})) == "invalid"
    assert refusal_of(await kernel.submit(kernel.runtime, add, {"id": "agent:x", "parent": "agent:y"})) == "not_found"
    assert [e.type for e in events_of(kernel)].count("principal.added") == 1


async def test_one_token_names_one_principal(kernel):
    await enroll(kernel, ALICE, token="s3cret")
    args = {"id": "agent:bob", "token_hash": hash_token("s3cret")}
    assert refusal_of(await kernel.submit(kernel.runtime, "principal.add", args)) == "conflict"


async def test_ops_list_shows_what_a_caller_holds(kernel):
    await enroll(kernel, ALICE, scopes=["note.*", "ops.list"])
    await grant(kernel, "agent:alice", "note.add")
    await grant(kernel, "agent:alice", "ops.list")

    listed = result_of(kernel.query(ALICE, "ops.list", {}))

    entries = {entry["name"]: entry for entry in listed}
    assert set(entries) == {"note.add", "ops.list"}
    assert entries["note.add"]["tool"] is True
    assert entries["note.add"]["schema"]["additionalProperties"] is False
    assert entries["note.add"]["description"].startswith("Add copies")
