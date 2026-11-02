"""One resolved config, three projections: the compiled table, checked by the real `authorize`."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.kernel import Args, Extension, Grant, Kernel, Principal, Txn, op
from platoon_harness.schema import ConfigError
from platoon_harness.team import Role, Team
from platoon_harness.topology import (
    PRESETS,
    Board,
    Group,
    Queue,
    Topic,
    Topology,
    compile,
    manager_worker,
    map_reduce,
    mesh,
    pipeline,
    scopes,
    star,
)

from .support import MANAGER_WORKER, PRESET_TEAMS

RUNTIME = Principal(id="runtime")
HUMAN = Principal(id="human:ada")


class Target(Args):
    on: str


def stub(txn: Txn, a: Target) -> None:
    """A stand-in with the name of a real op, which only asks `authorize`."""


def stubs(*names: str) -> list[Extension]:
    """Extensions holding one stand-in per op, each under its own namespace."""
    namespaces: dict[str, list] = {}
    for name in names:
        namespaces.setdefault(name.partition(".")[0], []).append(op(name, on=lambda a: a.on)(stub))
    return [Extension(namespace, ops=ops) for namespace, ops in namespaces.items()]


OPS = stubs(
    "agent.cancel",
    "agent.finish",
    "agent.interrupt",
    "agent.retire",
    "agent.spawn",
    "agent.status",
    "blob.get",
    "blob.put",
    "board.get",
    "board.post",
    "board.query",
    "board.revise",
    "channel.create",
    "channel.list",
    "message.read",
    "message.send",
    "peers",
    "session.close",
    "session.status",
    "task.add",
    "task.claim",
    "task.complete",
    "task.fail",
    "task.list",
    "task.release",
    "task.renew",
    "wait",
    "wait.cancel",
    "wait.progress",
)


async def install(kernel: Kernel, team: Team) -> None:
    for grant in compile(team):
        outcome = await kernel.submit(RUNTIME, "grant.add", grant.model_dump())
        assert outcome.refusal is None, grant


async def enroll(
    kernel: Kernel, id: str, role: str | None = None, parent: str | None = None, scopes=("*",)
) -> Principal:
    principal = Principal(id=id)
    args = {"id": id, "role": role, "parent": parent, "scopes": scopes}
    assert (await kernel.submit(RUNTIME, "principal.add", args)).refusal is None
    return principal


async def may(kernel: Kernel, who: Principal, op_name: str, on: str) -> bool:
    outcome = await kernel.submit(who, op_name, {"on": on})
    assert outcome.refusal is None or outcome.refusal.code == "not_permitted"
    return outcome.refusal is None


@pytest.fixture
async def kernel(tmp_path: Path) -> AsyncIterator[Kernel]:
    opened = Kernel.open(tmp_path / "session", extensions=OPS)
    yield opened
    opened.close()


def roles(*names: str) -> dict[str, Role]:
    return {name: Role(harness="pi") for name in names}


def grants_of(team: Team, who: str) -> set[tuple[str, str]]:
    return {(grant.ops, grant.on) for grant in compile(team) if grant.who == who}


@pytest.mark.parametrize("name", PRESETS)
async def test_the_kernel_accepts_every_grant_of_every_preset(kernel, name):
    await install(kernel, PRESET_TEAMS[name])


async def test_edges_check_message_send_against_the_targets_relations(kernel):
    team = Team.loads(MANAGER_WORKER)
    await install(kernel, team)
    lead = await enroll(kernel, "agent:lead", "lead")
    one = await enroll(kernel, "agent:one", "worker", "agent:lead")
    two = await enroll(kernel, "agent:two", "worker", "agent:lead")
    await enroll(kernel, "human:ada")

    assert await may(kernel, lead, "message.send", "inbox/one")
    assert await may(kernel, lead, "message.send", "inbox/ada")
    assert await may(kernel, one, "message.send", "inbox/lead")
    assert not await may(kernel, one, "message.send", "inbox/two")
    assert not await may(kernel, two, "message.send", "inbox/ada")


async def test_relations_stay_true_as_agents_come_and_go(kernel):
    await install(kernel, Team.loads(MANAGER_WORKER))
    lead = await enroll(kernel, "agent:lead", "lead")
    assert not await may(kernel, lead, "message.send", "inbox/late")
    await enroll(kernel, "agent:late", "worker", "agent:lead")
    assert await may(kernel, lead, "message.send", "inbox/late")


async def test_every_agent_holds_what_a_turn_cannot_do_without(kernel):
    await install(kernel, Team(roles=roles("solo")))
    solo = await enroll(kernel, "agent:solo", "solo")
    for op_name, target in (
        ("agent.finish", "session"),
        ("blob.put", "blob/ab"),
        ("blob.get", "blob/ab"),
        ("channel.list", "session"),
        ("session.status", "session"),
        ("wait.cancel", "session"),
        ("wait.progress", "session"),
    ):
        assert await may(kernel, solo, op_name, target), op_name


async def test_the_roster_stays_out_of_reach_of_an_agent_with_no_edges(kernel):
    await install(kernel, Team(roles=roles("solo")))
    solo = await enroll(kernel, "agent:solo", "solo")
    assert not await may(kernel, solo, "peers", "session")
    assert not await may(kernel, solo, "message.send", "inbox/solo")


async def test_an_agent_reads_its_own_inbox_and_no_other(kernel):
    await install(kernel, Team.loads(MANAGER_WORKER))
    lead = await enroll(kernel, "agent:lead", "lead")
    await enroll(kernel, "agent:one", "worker", "agent:lead")
    assert await may(kernel, lead, "message.read", "inbox/lead")
    assert not await may(kernel, lead, "message.read", "inbox/one")


async def test_channels_give_verbs_by_kind_and_selector(kernel):
    await install(kernel, Team.loads(MANAGER_WORKER))
    lead = await enroll(kernel, "agent:lead", "lead")
    worker = await enroll(kernel, "agent:one", "worker", "agent:lead")

    assert await may(kernel, lead, "task.add", "queue/tasks")
    assert not await may(kernel, lead, "task.claim", "queue/tasks")
    assert await may(kernel, worker, "task.claim", "queue/tasks")
    assert await may(kernel, worker, "task.complete", "queue/tasks")
    assert not await may(kernel, worker, "task.add", "queue/tasks")
    assert await may(kernel, worker, "board.post", "board/notes/spec")
    assert await may(kernel, lead, "board.get", "board/notes/spec")
    assert not await may(kernel, lead, "board.get", "board/other/spec")


async def test_a_topic_separates_writers_from_readers(kernel):
    team = Team(
        roles=roles("anchor", "viewer"),
        topology=Topology(channels={"news": Topic(writers="role:anchor", readers="role:viewer", delivery="wake")}),
    )
    await install(kernel, team)
    anchor = await enroll(kernel, "agent:anchor", "anchor")
    viewer = await enroll(kernel, "agent:viewer", "viewer")
    assert await may(kernel, anchor, "message.send", "channel/news")
    assert not await may(kernel, viewer, "message.send", "channel/news")
    assert await may(kernel, viewer, "message.read", "channel/news")
    assert not await may(kernel, anchor, "message.read", "channel/news")


async def test_groups_become_their_roles_on_the_live_graph(kernel):
    team = Team(roles={"peer": Role(harness="pi", count=2), "outsider": Role(harness="pi")}, topology=mesh("peer"))
    await install(kernel, team)
    one = await enroll(kernel, "agent:one", "peer")
    two = await enroll(kernel, "agent:two", "peer")
    outsider = await enroll(kernel, "agent:out", "outsider")
    assert await may(kernel, one, "message.send", "inbox/two")
    assert await may(kernel, two, "message.send", "channel/general")
    assert not await may(kernel, outsider, "message.send", "inbox/one")
    assert not await may(kernel, one, "message.send", "inbox/out")


async def test_a_group_has_an_implicit_topic_for_its_members(kernel):
    await install(kernel, Team(roles=roles("peer", "outsider"), topology=mesh("peer")))
    peer = await enroll(kernel, "agent:peer", "peer")
    outsider = await enroll(kernel, "agent:out", "outsider")
    assert await may(kernel, peer, "message.send", "channel/+peers")
    assert await may(kernel, peer, "message.read", "channel/+peers")
    assert not await may(kernel, outsider, "message.read", "channel/+peers")


async def test_next_and_prev_walk_a_groups_order(kernel):
    team = Team(
        roles=roles("a", "b", "c"),
        topology=Topology(
            groups={"chain": Group(order=("a", "b", "c"))}, edges={"a": ["next"], "b": ["next", "prev"], "c": ["prev"]}
        ),
    )
    assert ("message.send", "inbox/{role:b}") in grants_of(team, "role:a")
    assert grants_of(team, "role:b") >= {("message.send", "inbox/{role:a}"), ("message.send", "inbox/{role:c}")}
    await install(kernel, team)
    a = await enroll(kernel, "agent:a", "a")
    await enroll(kernel, "agent:b", "b")
    await enroll(kernel, "agent:c", "c")
    assert await may(kernel, a, "message.send", "inbox/b")
    assert not await may(kernel, a, "message.send", "inbox/c")


def test_a_group_of_named_principals_compiles_to_their_ids():
    team = Team(
        roles=roles("lead"),
        topology=Topology(
            groups={"owners": Group(members=("human:ada", "agent:ops"))},
            edges={"lead": ["group:owners"]},
            channels={"audit": Board(writers="group:owners", readers="group:owners")},
        ),
    )
    assert grants_of(team, "role:lead") >= {
        ("message.send", "inbox/ada"),
        ("message.send", "inbox/ops"),
        ("message.send", "channel/+owners"),
    }
    assert ("board.post", "board/audit/*") in grants_of(team, "agent:ops")


def test_a_role_with_no_edges_gets_no_message_send_and_no_peers():
    team = Team(
        roles=roles("author", "reviewer"),
        topology=pipeline(["author", "reviewer"]),
    )
    assert not {ops for ops, _ in grants_of(team, "role:author")} & {"message.send", "peers"}


def test_a_role_with_edges_gets_peers():
    assert ("peers", "*") in grants_of(Team.loads(MANAGER_WORKER), "role:worker")


async def test_spawn_is_granted_only_by_may_spawn(kernel):
    await install(kernel, Team.loads(MANAGER_WORKER))
    lead = await enroll(kernel, "agent:lead", "lead")
    worker = await enroll(kernel, "agent:one", "worker", "agent:lead")
    assert await may(kernel, lead, "agent.spawn", "role/worker")
    assert not await may(kernel, lead, "agent.spawn", "role/lead")
    assert not await may(kernel, worker, "agent.spawn", "role/worker")


async def test_a_parent_steers_only_its_own_subtree(kernel):
    await install(kernel, Team(roles={"a": Role(harness="pi", may_spawn=["a"])}, topology=Topology()))
    root = await enroll(kernel, "agent:root", "a")
    child = await enroll(kernel, "agent:child", "a", "agent:root")
    await enroll(kernel, "agent:grandchild", "a", "agent:child")
    other = await enroll(kernel, "agent:other", "a")
    assert await may(kernel, root, "agent.cancel", "agent/grandchild")
    assert await may(kernel, child, "agent.interrupt", "agent/grandchild")
    assert await may(kernel, root, "agent.status", "agent/child")
    assert not await may(kernel, other, "agent.retire", "agent/child")
    assert not await may(kernel, child, "agent.cancel", "agent/root")


def test_no_may_spawn_means_no_lifecycle_grants():
    ops = {ops for ops, _ in grants_of(Team.loads(MANAGER_WORKER), "role:worker")}
    assert not ops & {"agent.spawn", "agent.cancel", "agent.interrupt", "agent.retire"}


async def test_humans_and_programs_are_bound_by_no_topology(kernel):
    await install(kernel, Team(roles=roles("a"), topology=star("a", "a")))
    human = await enroll(kernel, "human:ada")
    program = await enroll(kernel, "program:run")
    assert await may(kernel, human, "session.close", "session")
    assert await may(kernel, program, "task.add", "queue/anything")


async def test_writers_program_means_no_agent_writes(kernel):
    team = Team(roles=roles("mapper", "reducer"), topology=map_reduce("mapper", "reducer"))
    await install(kernel, team)
    mapper = await enroll(kernel, "agent:m", "mapper")
    reducer = await enroll(kernel, "agent:r", "reducer")
    program = await enroll(kernel, "program:map_reduce")

    assert await may(kernel, program, "task.add", "queue/map")
    assert not await may(kernel, mapper, "task.add", "queue/map")
    assert await may(kernel, mapper, "task.claim", "queue/map")
    assert await may(kernel, mapper, "board.post", "board/results/shard-1")
    assert not await may(kernel, mapper, "board.get", "board/results/shard-1")
    assert await may(kernel, reducer, "board.get", "board/results/shard-1")


async def test_role_tools_become_scopes_that_only_narrow(kernel):
    team = Team(
        roles={"lead": Role(harness="pi", tools=["board.*"]), "worker": Role(harness="pi", may_spawn=[])},
        topology=manager_worker("lead", "worker"),
    )
    await install(kernel, team)
    lead = await enroll(kernel, "agent:lead", "lead", scopes=scopes(team.roles["lead"]))
    assert await may(kernel, lead, "board.get", "board/notes/x")
    assert not await may(kernel, lead, "task.add", "queue/tasks")


def test_ops_list_is_always_in_scope_and_granted_to_all():
    assert scopes(Role(harness="pi", tools=["board.get"])) == ("board.get", "ops.list")
    team = Team(roles=roles("a"))
    assert ("ops.list", "*") in grants_of(team, "all")


def test_extension_ops_are_granted_by_glob_with_no_new_vocabulary():
    team = Team(
        roles=roles("voter"),
        topology=Topology(grants=[Grant(who="role:voter", ops="ballot.*", on="ballot/{role:voter}")]),
    )
    assert ("ballot.*", "ballot/{role:voter}") in grants_of(team, "role:voter")


async def test_an_agent_may_wait_only_on_what_it_can_read(kernel):
    team = Team.loads(MANAGER_WORKER)
    await install(kernel, team)
    lead = await enroll(kernel, "agent:lead", "lead")
    worker = await enroll(kernel, "agent:one", "worker", "agent:lead")

    assert await may(kernel, lead, "wait", "inbox/lead")
    assert not await may(kernel, lead, "wait", "inbox/one")
    assert await may(kernel, lead, "wait", "task/tasks/7")
    assert await may(kernel, lead, "wait", "agent/one")
    assert await may(kernel, worker, "wait", "task/tasks/7")
    assert await may(kernel, worker, "wait", "board/notes/spec")
    assert not await may(kernel, worker, "wait", "agent/lead")
    assert not await may(kernel, worker, "wait", "task/other/7")


async def test_a_group_member_may_watch_the_group(kernel):
    await install(kernel, Team(roles=roles("peer", "outsider"), topology=mesh("peer")))
    peer = await enroll(kernel, "agent:peer", "peer")
    outsider = await enroll(kernel, "agent:out", "outsider")
    assert await may(kernel, peer, "wait", "group/peers")
    assert await may(kernel, peer, "wait", "channel/+peers")
    assert not await may(kernel, outsider, "wait", "group/peers")


def test_a_grant_the_kernel_cannot_evaluate_is_refused_before_any_cost():
    team = Team(roles=roles("a"), topology=Topology(grants=[Grant(who="role:a", ops="x.*", on="x/{group:g}")]))
    with pytest.raises(ConfigError, match="no evaluator"):
        compile(team)


def test_compilation_is_deterministic():
    team = Team.loads(MANAGER_WORKER)
    grants = compile(team)
    assert grants == compile(Team.loads(team.show(resolved=True)))
    assert list(grants) == sorted(grants, key=lambda grant: (grant.who, grant.ops, grant.on))
    assert len(set(grants)) == len(grants)


def test_compile_refuses_what_cannot_be_enforced():
    team = Team(
        roles=roles("a"),
        topology=Topology(
            edges={"a": ["role:ghost", "next"]},
            channels={"x": Queue(writers="children", readers="group:ghost")},
        ),
    )
    with pytest.raises(ConfigError) as caught:
        compile(team)
    text = str(caught.value)
    assert "unknown role `ghost`" in text
    assert "unknown group `ghost`" in text
    assert "`next` needs a group" in text
    assert "`children` needs an agent" in text


def test_compile_refuses_an_unexpanded_preset():
    team = Team.loads('[roles.a]\nharness = "pi"\n[topology.ballot]\nvoters = "a"')
    with pytest.raises(ConfigError, match="not resolved"):
        compile(team)
