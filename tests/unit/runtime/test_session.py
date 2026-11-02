"""The Session facade: thin wrappers held to the registry, and what a session came to."""

import asyncio
import inspect
from typing import Any

import pytest
from pydantic_core import PydanticUndefined

import platoon_harness
from platoon_harness import Ending, Refused, Role, Session, Team, on
from platoon_harness.config import Manifest
from platoon_harness.kernel import Args, Extension, Kernel, ManualClock, Op, Outcome, Txn, op
from platoon_harness.kernel.core import CORE, list_ops
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime.opening import prepare
from platoon_harness.runtime.paths import MANIFEST
from platoon_harness.testing import Ask, Call, Exit, Hang, Say

from .support import SECONDS, in_state, of_type, scripted, solo, until

pytestmark = pytest.mark.timeout(30)

COVERED = {
    "agent.cancel": "cancel",
    "agent.finish": "finish",
    "agent.interrupt": "interrupt",
    "agent.list": "agents",
    "agent.release": "release_agent",
    "agent.retire": "retire",
    "agent.spawn": "spawn",
    "agent.status": "status",
    "agent.takeover": "takeover",
    "approval.resolve": "resolve",
    "attention.list": "attention",
    "blob.get": "blob",
    "board.get": "get",
    "board.post": "post",
    "board.query": "query",
    "board.revise": "revise",
    "body.tombstone": "tombstone",
    "budget.set": "set_budget",
    "budget.status": "budgets",
    "channel.create": "create_channel",
    "channel.list": "channels",
    "episode.close": "close_episode",
    "episode.open": "open_episode",
    "message.read": "read",
    "message.send": "send",
    "ops.list": "ops",
    "peers": "peers",
    "session.cancel": "cancel",
    "session.close": "close",
    "session.ending": "ending",
    "session.manifest": "manifest",
    "session.status": "status",
    "task.add": "enqueue",
    "task.claim": "claim",
    "task.complete": "complete",
    "task.fail": "fail",
    "task.list": "tasks",
    "task.release": "release",
    "task.renew": "renew",
    "view.watch": "watch",
    "wait": "wait",
    "wait.cancel": "cancel_wait",
    "wait.progress": "wait_progress",
}
DERIVED = {
    "approvals": "attention.list",
    "broadcast": "message.send",
    "deltas": "the link",
    "events": "the link",
    "get_body": "the link",
    "join": "wait",
    "leave": "the runtime",
    "put_body": "the link",
    "reply": "message.send",
    "resume": "a verb of its own",
    "settled": "session.status",
    "start": "a verb of its own",
    "attach": "a verb of its own",
    "submit": "the one way in",
    "wait_any": "wait",
}
OPS = {operation.name: operation for extension in (*CORE, *PRIMITIVES) for operation in extension.ops}
OPS["ops.list"] = list_ops({})
CLIENT_OPS = {name: operation for name, operation in OPS.items() if not operation.runtime}
RENAMED = {"view": "name"}


def public_methods() -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(Session)
        if not name.startswith("_") and (inspect.isfunction(member) or inspect.ismethod(member))
    }


def parameters_of(method: Any) -> dict[str, inspect.Parameter]:
    found = dict(inspect.signature(method).parameters)
    found.pop("self", None)
    return found


def test_every_op_a_client_may_use_has_a_method():
    assert set(CLIENT_OPS) == set(COVERED), "a new op needs a method here, or a method here lost its op"


def test_every_method_is_an_op_or_says_what_it_rests_on():
    assert public_methods() == set(COVERED.values()) | set(DERIVED)


def test_nothing_runtime_only_has_a_method():
    assert not {name for name, operation in OPS.items() if operation.runtime} & set(COVERED)


@pytest.mark.parametrize(("name", "method"), COVERED.items(), ids=COVERED.keys())
def test_a_method_takes_what_its_op_declares(name: str, method: str):
    operation: Op = OPS[name]
    fields = operation.input.model_fields
    given = parameters_of(getattr(Session, method))

    stated = {RENAMED.get(parameter, parameter) for parameter in given}
    if method not in ("status", "cancel"):  # Each wraps two ops, and says which by whether `agent` is given.
        assert stated <= set(fields), f"{method} states what {name} does not declare: {stated - set(fields)}"
    required = {field for field, info in fields.items() if info.is_required()}
    assert required <= stated, f"{method} cannot state {required - stated}"


@pytest.mark.parametrize(("name", "method"), COVERED.items(), ids=COVERED.keys())
def test_a_default_is_the_op_s_own(name: str, method: str):
    fields = OPS[name].input.model_fields
    for parameter, found in parameters_of(getattr(Session, method)).items():
        default = fields[parameter].default if parameter in fields else PydanticUndefined
        if found.default is inspect.Parameter.empty or default is PydanticUndefined:
            continue
        if found.default is None and default in ({}, ()):
            continue  # A mutable default has no place in a signature, so None stands for it.
        assert found.default == default, f"{method}({parameter}=) drifted from {name}"


def test_what_a_user_needs_is_at_the_top():
    assert set(platoon_harness.__all__) == {
        "Ending",
        "Refused",
        "Role",
        "Session",
        "Team",
        "__version__",
        "load_team",
        "on",
    }
    assert platoon_harness.Session.__module__ == "platoon_harness.session"


# Entering and leaving.


async def test_a_session_can_be_awaited_with_no_extra_verb(tmp_path):
    session = await Session.start(solo(), name="s", root=tmp_path)

    assert isinstance(session, Session)
    assert session.name == "s" and session.owner
    await session.leave()


async def test_leaving_stops_the_agents_and_keeps_the_folder(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        folder = session.folder

    assert (folder / "journal.sqlite").exists()
    assert not (folder / "runtime.json").exists()
    kernel = Kernel.open(folder, read_only=True, extensions=PRIMITIVES)
    events = [event.type for event in kernel.read(kernel.runtime, after=0, limit=4096).events]
    kernel.close()
    assert events[-1] == "session.stopped"


async def test_a_session_left_is_refused_and_says_what_to_do(tmp_path):
    session = await Session.start(solo(), root=tmp_path)
    await session.leave()

    with pytest.raises(Refused, match="attach to it again"):
        await session.status()


async def test_leaving_twice_is_harmless(tmp_path):
    session = await Session.start(solo(), root=tmp_path)

    await session.leave()
    await session.leave()


async def test_a_turn_is_interrupted_by_an_owner_s_exit_and_its_reservation_comes_back(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": scripted([Hang()])}}, "budget": {"turns": 5}})

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
        folder = session.folder

    kernel = Kernel.open(folder, read_only=True, extensions=PRIMITIVES)
    rows = kernel.query(kernel.runtime, "budget.status", {}).result
    types = [event.type for event in kernel.read(kernel.runtime, after=0, limit=4096).events]
    kernel.close()
    assert rows[0]["held"] == 0.0 and rows[0]["spent"] == 1.0
    assert "turn.ended" in types
    assert "turn.lost" not in types


async def test_a_handover_that_never_started_is_queued_again_and_its_reservation_returned(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": scripted([Say("heard")])}}, "budget": {"turns": 5}})
    session = await Session.start(team, root=tmp_path)
    await in_state(session, "bob", "idle")
    runtime = session._runtime
    runtime.host._dispatch = lambda: None

    await session.send("@bob", "too late")
    await until(lambda: of_type(session, "agent.woken"), session)
    folder = session.folder
    await session.leave()

    kernel = Kernel.open(folder, read_only=True, extensions=PRIMITIVES)
    rows = kernel.query(kernel.runtime, "budget.status", {}).result
    kernel.close()
    assert rows[0]["held"] == 0.0
    async with Session.resume(folder.name, root=tmp_path) as resumed:
        item = await until(lambda: of_type(resumed, "item.recorded"), resumed)
        assert item[0].gist == "heard"


async def test_a_detached_runtime_takes_nothing_it_could_not_keep(tmp_path):
    with pytest.raises(Refused) as refused:
        Session.start(solo(), detach=True, clock=ManualClock(), root=tmp_path)

    assert refused.value.refusal.code == "unsupported"


async def test_a_human_is_a_name_in_the_journal(tmp_path):
    async with Session.start(solo(), human="ada", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        sent = await session.send("@bob", "hello")
        event = (await of_type(session, "message.sent"))[0]

    assert sent["ref"] == "inbox/bob@1"
    assert (event.actor, event.data["sender"]) == ("human:ada", "@ada")


async def test_a_human_cannot_take_a_name_that_is_taken(tmp_path):
    with pytest.raises(Refused) as refused:
        await Session.start(solo(), human="bob", root=tmp_path)

    assert refused.value.refusal.code == "conflict"


# Attaching and resuming.


async def test_attach_to_nothing_is_refused(tmp_path):
    with pytest.raises(Refused) as refused:
        await Session.attach("nowhere", root=tmp_path)

    assert refused.value.refusal.code == "not_found"


async def test_with_no_runtime_attach_gives_history_and_starts_nothing(tmp_path):
    async with Session.start(solo([Say("said")]), name="s", root=tmp_path) as session:
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)

    async with Session.attach("s", root=tmp_path) as history:
        assert not history.owner
        assert (await history.status("@bob"))["state"] == "idle"
        assert [event.gist for event in await of_type(history, "item.recorded")] == ["said"]
        assert (history.folder / "lock").exists() and not (history.folder / "runtime.json").exists()


async def test_with_no_runtime_a_write_is_refused_naming_what_restarts_it(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path):
        pass

    async with Session.attach("s", root=tmp_path) as history:
        outcome = await history.submit("message.send", to="@bob", gist="hello?")
        with pytest.raises(Refused) as refused:
            await history.send("@bob", "hello?")
        with pytest.raises(Refused) as stored:
            await history.put_body(b"a body")

    assert outcome.refusal is not None and outcome.refusal.code == "unavailable"
    assert "platoon-harness resume s" in str(outcome.refusal.detail)
    assert refused.value.refusal.code == "unavailable"
    assert stored.value.refusal.code == "unavailable"


async def test_history_ends_where_the_journal_does(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path):
        pass

    async with Session.attach("s", root=tmp_path) as history:
        followed = [event async for event in history.events(follow=True)]
        frames = [frame async for frame in history.deltas("bob")]

    assert followed[-1].type == "session.stopped"
    assert frames == []


async def test_a_guest_on_history_finds_a_runtime_that_came_back(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path):
        pass
    history = await Session.attach("s", root=tmp_path)

    async with Session.resume("s", root=tmp_path) as resumed:
        await in_state(resumed, "bob", "idle")

        await history.send("@bob", "you are back")

        assert len(await of_type(resumed, "message.sent")) == 1
    await history.leave()


async def test_a_resume_refuses_a_session_that_has_a_runtime(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path):
        with pytest.raises(Refused) as refused:
            await Session.resume("s", root=tmp_path)

    assert refused.value.refusal.code == "unavailable"


async def test_a_resume_of_a_stopped_session_goes_on_where_it_stopped(tmp_path):
    async with Session.start(solo([Say("one")], [Say("two")]), name="s", root=tmp_path) as session:
        await session.send("@bob", "first")
        await until(lambda: of_type(session, "turn.ended"), session)

    async with Session.resume("s", root=tmp_path) as session:
        assert (await session.status())["state"] == "open"
        await in_state(session, "bob", "idle")
        assert len(await of_type(session, "runtime.started")) == 2
        assert len(await of_type(session, "agent.resumed")) == 1


async def test_fresh_credentials_are_issued_on_resume(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        first = (session.folder / "owner.token").read_text()

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")

        assert (session.folder / "owner.token").read_text() != first
        with pytest.raises(Refused, match="unknown credential"):
            session._runtime.kernel.authenticate(first)
        issued = [event for event in await of_type(session, "principal.issued") if event.data["id"] == "agent:bob"]
        assert len({event.data["token_hash"] for event in issued}) == 2


async def test_a_session_folder_with_a_manifest_and_no_journal_opens_on_resume(tmp_path):
    folder = prepare(solo(), name="s", root=tmp_path)

    with pytest.raises(Refused, match="never opened"):
        await Session.attach("s", root=tmp_path)

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
    assert Manifest.model_validate_json((folder / MANIFEST).read_text()).human == "human:you"


# One way in.


async def test_submit_returns_the_kernel_s_outcome_and_never_raises_a_refusal(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        outcome = await session.submit("message.send", to="@nobody", gist="hello?")

    assert isinstance(outcome, Outcome)
    assert outcome.refusal is not None and outcome.refusal.code == "not_found"


async def test_submit_reaches_a_query_as_well(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        assert (await session.submit("session.status")).result["state"] == "open"


async def test_a_typed_method_raises_the_refusal(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        with pytest.raises(Refused) as refused:
            await session.send("@nobody", "hello?")

    assert refused.value.refusal.code == "not_found"
    assert refused.value.refusal.op == "message.send"


# Typed wrappers, end to end.


def worker_team(**fields: Any) -> Team:
    channels = {
        "tasks": {"kind": "queue", "writers": ["human"], "readers": ["human"]},
        "notes": {"kind": "board", "writers": "all", "readers": "all"},
        "news": {"kind": "topic", "writers": "all", "readers": "all"},
    }
    return Team.model_validate(
        {
            "roles": {"bob": {"harness": scripted(), **fields}},
            "topology": {"channels": channels, "groups": {"crew": {"roles": ["bob"]}}},
        }
    )


async def test_a_board_through_the_facade(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        posted = await session.post("notes", "spec", "the spec", body="line one\nline two\n", fields={"state": "draft"})
        revised = await session.revise(
            "notes", "spec", "the spec, revised", posted["version"], fields={"state": "done"}
        )

        with pytest.raises(Refused) as stale:
            await session.revise("notes", "spec", "too late", posted["version"])

        got = await session.get("notes", "spec")
        old = await session.get("notes", "spec", version=1, range="L2-2")
        found = await session.query("notes", where={"state": "done"})

    assert revised["version"] == 2
    assert stale.value.refusal.code == "conflict"
    assert (got["version"], got["gist"]) == (2, "the spec, revised")
    assert old["text"] == "line two\n"
    assert [row["name"] for row in found["results"]] == ["spec"]


async def test_a_queue_through_the_facade(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        added = await session.enqueue("tasks", "do it", body="in detail")
        claim = await session.claim("tasks")
        renewed = await session.renew("tasks")
        await session.release("tasks")
        await session.claim("tasks", task=added["task"])
        await session.complete("tasks", gist="done", body="how it went")
        await session.enqueue("tasks", "do it again")
        await session.claim("tasks")
        await session.fail("tasks", gist="it broke")
        listed = await session.tasks("tasks", state="done")

    assert claim["task"] == added["task"] and renewed["fence"] == claim["fence"]
    assert [task["result"] for task in listed["tasks"]] == ["done"]


async def test_messages_through_the_facade(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.broadcast("crew", "to the crew")
        await session.send("#news", "in the news", body="at length")
        inbox = await session.send("@you", "note to self")
        read = await session.read()
        await session.reply(read["entries"][0], "answered")
        news = await session.read("#news", bodies=True)

    assert inbox["ref"] == "inbox/you@1"
    assert [entry["gist"] for entry in (await asyncio.sleep(0, read))["entries"]] == ["note to self"]
    assert news["entries"][0]["text"] == "at length"


async def test_a_body_that_is_a_ref_is_cited_and_not_stored_again(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        sha256 = await session.put_body(b"already here")
        ref = f"sha256:{sha256}"

        await session.send("#news", "with a ref", body=ref)

        assert (await of_type(session, "message.sent"))[-1].data["body"] == ref


async def test_lifecycle_through_the_facade(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": scripted()}, "lead": {"harness": scripted(), "count": 0}}})

    async with Session.start(team, root=tmp_path) as session:
        await session.spawn("ada", "bob")
        await in_state(session, "ada", "idle")
        await session.retire("@ada")
        await in_state(session, "ada", "ended")
        await session.spawn("eve", "bob")
        await in_state(session, "eve", "idle")
        await session.cancel("@eve")

        rows = {row["name"]: row["status"] for row in await session.agents()}
        assert rows["@ada"] == "retired" and rows["@eve"] == "cancelled"
        assert await session.peers() is not None
        assert await session.channels() == []
        assert "session.status" in {op["name"] for op in await session.ops()}
        assert (await session.manifest())["manifest"].startswith("sha256:")


async def test_channels_and_budgets_through_the_facade(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await session.create_channel("later", "topic", delivery="next-turn")
        await session.set_budget(limits={"turns": 10})
        await session.open_episode("first")
        await session.close_episode({"score": 1})

        assert [row["name"] for row in await session.channels()] == ["#later"]
        assert (await session.budgets())[0]["limit"] == 10.0


async def test_a_body_can_be_read_and_redacted(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        sha256 = await session.put_body(b"line\n")

        assert (await session.blob(f"sha256:{sha256}"))["text"] == "line\n"

        await session.tombstone(sha256)

        with pytest.raises(Refused):
            await session.get_body(sha256)


async def test_join_waits_for_every_agent_and_says_how_it_closed(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": scripted([Call("agent_finish", {})]), "count": 0}}})

    async with Session.start(team, root=tmp_path) as session:
        await session.spawn("ada", "bob", "be quick")
        await session.spawn("eve", "bob", "be quick")

        closed = await asyncio.wait_for(session.join("@ada", "@eve"), SECONDS)

    assert closed["state"] == "released"


async def test_wait_any_stops_at_the_first(tmp_path):
    roles = {
        "bob": {"harness": scripted([Call("agent_finish", {})]), "count": 0},
        "slow": {"harness": scripted([Hang()]), "count": 0},
    }

    async with Session.start(Team.model_validate({"roles": roles}), root=tmp_path) as session:
        await session.spawn("ada", "bob", "be quick")
        await session.spawn("eve", "slow", "take your time")

        closed = await asyncio.wait_for(session.wait_any("@ada", "@eve"), SECONDS)

    assert closed["state"] == "released"


async def test_a_wait_on_a_condition_stated_outright(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        closed = await asyncio.wait_for(session.wait(on=[on("agent/bob", ("agent.started",))]), SECONDS)

    assert closed["state"] == "released"


async def test_a_wait_times_out_on_the_kernel_s_clock(tmp_path):
    clock = ManualClock(1000.0)

    async with Session.start(solo(), root=tmp_path, clock=clock) as session:
        await in_state(session, "bob", "idle")
        waiting = asyncio.ensure_future(session.wait(agents=["@bob"], timeout="30s"))
        await until(lambda: of_type(session, "wait.registered"), session)
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1030.0)

        clock.advance(30.0)

        assert (await asyncio.wait_for(waiting, SECONDS))["state"] == "expired"


async def test_a_wait_can_be_read_and_cancelled(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        waiting = asyncio.ensure_future(session.wait(agents=["@bob"]))
        placed = await until(lambda: of_type(session, "wait.registered"), session)

        assert (await session.wait_progress(placed[0].seq))["state"] == "open"

        await session.cancel_wait(placed[0].seq)

        assert (await asyncio.wait_for(waiting, SECONDS))["state"] == "cancelled"


# What a session came to.


async def test_settled_is_exit_0_and_says_what_it_used(tmp_path):
    async with Session.start(solo([Say("done")]), root=tmp_path) as session:
        await session.send("@bob", "go")

        ending = await session.settled(timeout="10s")

    assert isinstance(ending, Ending)
    assert (ending.state, ending.reason) == ("closing", "settled")
    assert [(row["agent"], row["state"]) for row in ending.agents] == [("bob", "idle")]
    assert ending.gaps == ()


async def test_until_a_role_closes_the_session_when_that_role_ends(tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "lead": {"harness": scripted([Call("agent_finish", {"gist": "done"})]), "may_spawn": ["worker"]},
                "worker": {"harness": scripted([Hang()]), "count": 1},
            },
            "topology": {"until": "role:lead"},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@lead", "go")

        ending = await session.settled(timeout="10s")

    assert (ending.state, ending.reason) == ("closing", "settled")


async def test_an_agent_that_failed_is_exit_1(tmp_path):
    async with Session.start(solo([Exit("it fell over")]), root=tmp_path) as session:
        await session.send("@bob", "go")

        ending = await session.settled(timeout="10s")

    assert ending.reason == "agent_failed"
    assert (ending.agents[0]["status"], ending.agents[0]["reason"]) == ("lost", "it fell over")


async def test_a_budget_spent_is_exit_2(tmp_path):
    team = Team.model_validate(
        {
            "roles": {"bob": {"harness": scripted([Say("spending")], [Say("more")]), "count": 1}},
            "budget": {"turns": 1},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@bob", "go")

        ending = await session.settled(timeout="10s")

    assert ending.reason == "budget_exhausted"


async def test_a_quiet_session_past_its_wall_limit_ends_and_does_not_hang(tmp_path):
    clock = ManualClock(1000.0)
    team = Team.model_validate({"roles": {"bob": {"harness": scripted()}}, "budget": {"wall": "1m"}})

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        await in_state(session, "bob", "idle")
        settling = asyncio.ensure_future(session.settled())
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1060.0)

        clock.advance(60.0)

        ending = await asyncio.wait_for(settling, SECONDS)

    assert (ending.state, ending.reason) == ("closing", "budget_exhausted")


async def test_timing_out_is_exit_3_and_leaves_the_session_as_it_is(tmp_path):
    clock = ManualClock(1000.0)

    async with Session.start(solo([Hang()]), root=tmp_path, clock=clock) as session:
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
        settling = asyncio.ensure_future(session.settled(timeout="30m"))
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(2800.0)

        clock.advance(1800.0)
        ending = await asyncio.wait_for(settling, SECONDS)

        assert (ending.state, ending.reason) == ("open", "timed_out")
        assert await session.status("@bob") is not None


async def test_an_ask_nobody_can_answer_is_exit_4_and_never_a_hang(tmp_path):
    async with Session.start(solo([Ask("may I?")]), root=tmp_path) as session:
        await session.send("@bob", "go")

        ending = await asyncio.wait_for(session.settled(), SECONDS)

    assert ending.reason == "needs_human"


async def test_a_stated_policy_leaves_nobody_to_ask(tmp_path):
    async with Session.start(solo([Ask("may I?"), Say("thanks")]), approvals="deny", root=tmp_path) as session:
        await session.send("@bob", "go")

        ending = await session.settled(timeout="10s")

        assert ending.reason == "settled"
        assert [event.gist for event in await of_type(session, "item.recorded")][-1] == "thanks"


async def test_an_ask_a_guest_could_answer_waits_for_it(tmp_path):
    async with Session.start(solo([Ask("may I?"), Say("thanks")]), name="s", root=tmp_path) as session:
        guest = await Session.attach("s", root=tmp_path)
        await session.send("@bob", "go")
        settling = asyncio.ensure_future(session.settled(timeout="10s"))

        asked = (await until(guest.approvals, guest))[0]
        assert not settling.done()
        await guest.resolve(asked["id"], "allow", expected_version=asked["version"])

        assert (await asyncio.wait_for(settling, SECONDS)).reason == "settled"
        await guest.leave()


async def test_cancelling_is_exit_130(tmp_path):
    async with Session.start(solo([Hang()]), root=tmp_path) as session:
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
        settling = asyncio.ensure_future(session.settled(timeout="10s"))
        await session.cancel()

        ending = await asyncio.wait_for(settling, SECONDS)

    assert (ending.state, ending.reason) == ("cancelled", "cancelled")
    assert ending.agents[0]["status"] == "cancelled"


async def test_a_guest_can_settle_and_close(tmp_path):
    async with Session.start(solo([Say("done")]), name="s", root=tmp_path) as session:
        await session.send("@bob", "go")
        async with Session.attach("s", root=tmp_path) as guest:
            ending = await guest.settled(timeout="10s")

    assert ending.reason == "settled"


class Vote(Args):
    choice: str


@op("ballot.cast", on=lambda a: "ballot/votes")
def cast(txn: Txn, a: Vote) -> dict[str, str]:
    """Cast a vote."""
    txn.emit("ballot.voted", "ballot/votes", gist=f"a vote for {a.choice}", data=a)
    return {"choice": a.choice}


ballot = Extension("ballot", ops=[cast])


async def test_an_op_a_team_s_extension_adds_works_with_no_core_edit(tmp_path):
    role = Role(harness=scripted())
    team = Team(roles={"bob": role}, extensions=(f"{__name__}:ballot",))

    async with Session.start(team, root=tmp_path) as session:
        outcome = await session.submit("ballot.cast", choice="yes")

        assert outcome.result == {"choice": "yes"}
        assert [event.gist for event in await of_type(session, "ballot.voted")] == ["a vote for yes"]


async def test_a_role_is_a_role(tmp_path):
    role = Role(harness=scripted([Say("from a Role")]))

    async with Session.start(Team(roles={"bob": role}), root=tmp_path) as session:
        await session.send("@bob", "go")
        items = await until(lambda: of_type(session, "item.recorded"), session)

    assert items[0].gist == "from a Role"
