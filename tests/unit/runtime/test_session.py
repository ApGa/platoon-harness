"""The Session facade: thin wrappers held to the registry, and what a session came to."""

import asyncio
import inspect
import threading
from typing import Any

import pytest
from pydantic_core import PydanticUndefined

import platoon_harness
from platoon_harness import Ending, Refused, Role, Session, Team, on
from platoon_harness import session as session_module
from platoon_harness.config import Manifest
from platoon_harness.drivers import Usage
from platoon_harness.kernel import Args, Extension, Kernel, ManualClock, Op, Outcome, Txn, is_held, op, registry
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime.opening import prepare
from platoon_harness.runtime.paths import MANIFEST, MARKS
from platoon_harness.testing import Ask, Call, Exit, Hang, Say, ScriptedDriver

from ...integration.scripts import wire
from .support import SECONDS, harness, in_state, of_type, scripted, solo, until

pytestmark = pytest.mark.timeout(30)

COVERED = {
    "agent.cancel": "cancel_agent",
    "agent.interrupt": "interrupt",
    "agent.list": "agents",
    "agent.release": "release",
    "agent.retire": "retire",
    "agent.spawn": "spawn",
    "agent.status": "status",
    "agent.takeover": "takeover",
    "agent.unread": "unread",
    "approval.resolve": "resolve",
    "attention.list": "attention",
    "blob.get": "blob",
    "board.get": "board_get",
    "board.post": "board_post",
    "board.query": "board_query",
    "board.revise": "board_revise",
    "body.tombstone": "tombstone",
    "budget.set": "set_budget",
    "budget.status": "budgets",
    "contributors": "contributors",
    "channel.create": "create_channel",
    "channel.list": "channels",
    "effect.settle": "settle_effect",
    "episode.close": "close_episode",
    "episode.open": "open_episode",
    "exposure": "exposure",
    "lineage": "lineage",
    "message.read": "read",
    "message.send": "send",
    "ops.list": "ops",
    "peers": "peers",
    "session.cancel": "cancel",
    "session.close": "close",
    "session.ending": "ending",
    "session.manifest": "manifest",
    "session.status": "status",
    "task.add": "task_add",
    "task.claim": "task_claim",
    "task.complete": "task_complete",
    "task.fail": "task_fail",
    "task.list": "task_list",
    "task.release": "task_release",
    "task.renew": "task_renew",
    "uses": "uses",
    "view.watch": "watch",
    "wait": "wait",
    "wait.cancel": "cancel_wait",
    "wait.progress": "wait_progress",
}
DERIVED = {
    "annotate": "annotations.sqlite",
    "annotations": "annotations.sqlite",
    "approvals": "attention.list",
    "deltas": "the link",
    "events": "the link",
    "get_body": "the link",
    "head": "the link",
    "leave": "the runtime",
    "mark": "marks.sqlite",
    "marks": "marks.sqlite",
    "page": "the link",
    "put_body": "the link",
    "reply": "message.send",
    "resume": "a verb of its own",
    "settled": "session.status",
    "start": "a verb of its own",
    "attach": "a verb of its own",
    "submit": "the one way in",
}
OPS = registry(PRIMITIVES)
CLIENT_OPS = {name: operation for name, operation in OPS.items() if not (operation.runtime or operation.agent)}
RENAMED = {"watch": {"view": "name"}, "spawn": {"role": "child_role"}, "tombstone": {"ref": "sha256"}}


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

    stated = {RENAMED.get(method, {}).get(parameter, parameter) for parameter in given}
    if method != "status":  # It wraps two ops, and says which by whether `agent` is given.
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
        "ConfigError",
        "Ending",
        "JournalError",
        "Refused",
        "Role",
        "Session",
        "Team",
        "__version__",
        "load_team",
        "on",
        "told",
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


async def test_a_session_left_is_refused_and_says_so(tmp_path):
    session = await Session.start(solo(), root=tmp_path)
    await session.leave()

    assert not session.owner
    with pytest.raises(Refused, match="this session was left"):
        await session.status()


async def test_a_session_never_entered_says_how_to_start_it(tmp_path):
    session = Session.start(solo(), root=tmp_path)

    with pytest.raises(Refused, match="not started: `await` it"):
        await session.send("@bob", "hello")


async def test_awaiting_a_session_left_starts_nothing(tmp_path):
    session = await Session.start(solo(), root=tmp_path)
    await session.leave()

    await session

    assert len(list((tmp_path / "sessions").iterdir())) == 1
    with pytest.raises(Refused, match="this session was left"):
        await session.status()


async def test_grace_takes_a_span_as_every_other_wait_does(tmp_path):
    session = await Session.start(solo(), root=tmp_path)
    folder = session.folder

    await session.leave("1s")

    assert not is_held(folder)


async def test_a_grace_that_makes_no_sense_stops_nothing_halfway(tmp_path):
    session = await Session.start(solo(), root=tmp_path)

    with pytest.raises(ValueError, match="a duration"):
        await session.leave("soon")

    assert session.owner and is_held(session.folder)
    await session.leave()


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


async def test_a_start_cancelled_while_it_prepares_leaves_no_session(tmp_path, monkeypatch):
    """Preparing runs in a thread that nothing can cut short, so what it makes after the cancel is taken back."""
    began, release = threading.Event(), threading.Event()

    def slow(*args: Any, **options: Any) -> Any:
        began.set()
        release.wait(SECONDS)
        return prepare(*args, **options)

    monkeypatch.setattr(session_module, "prepare", slow)
    starting = asyncio.ensure_future(Session.start(solo(), name="s", root=tmp_path))
    await asyncio.to_thread(began.wait, SECONDS)

    starting.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await starting
    assert list((tmp_path / "sessions").iterdir()) == []


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
    assert 'Session.resume("s")' in str(outcome.refusal.detail)
    assert refused.value.refusal.code == "unavailable"
    assert stored.value.refusal.code == "unavailable"


async def test_history_pages_back_as_a_runtime_does(tmp_path):
    async with Session.start(solo([Say("said")]), name="s", root=tmp_path) as session:
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        live = [event async for event in session.events()]

    async with Session.attach("s", root=tmp_path) as history:
        before, back = (await history.head()) + 1, []
        while before:
            page = await history.page(before=before, limit=3)
            back, before = [*page.events, *back], page.cursor

    assert [event.seq for event in back[: len(live)]] == [event.seq for event in live]


async def test_moving_a_persons_mark_never_acknowledges_a_delivery(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": scripted([Hang()]), "delivery": "next-turn"}}})
    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.create_channel("news", "topic", readers=["role:bob"])
        await session.send("#news", "for bob's next turn")
        head = await session.head()
        unread = await until(lambda: roster(session), session, lambda rows: rows["bob"]["unread"] == 1)

        await session.mark("channel/news", head)

        after = [event async for event in session.events(head)]
        assert await session.marks() == {"channel/news": head}
        assert [event for event in after if event.actor == "human:you" or event.type == "message.acked"] == []
        assert (await roster(session))["bob"]["unread"] == unread["bob"]["unread"]


async def test_a_mark_is_a_persons_own(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()

    session_module._mark(folder, "human:ada", "inbox/ada", 3)
    session_module._mark(folder, "human:bea", "inbox/ada", 9)

    assert session_module._marks_of(folder, "human:ada") == {"inbox/ada": 3}
    assert session_module._marks_of(folder, "human:cy") == {}


async def test_a_mark_only_moves_forward(tmp_path):
    """A second terminal of the same person that drew less marks less, and takes back nothing the first marked read."""
    folder = tmp_path / "s"
    folder.mkdir()

    session_module._mark(folder, "human:ada", "inbox/ada", 10)
    session_module._mark(folder, "human:ada", "inbox/ada", 5)

    assert session_module._marks_of(folder, "human:ada") == {"inbox/ada": 10}


async def test_losing_the_marks_loses_only_badges(tmp_path):
    async with Session.start(solo([Say("still here")]), root=tmp_path) as session:
        await session.mark("inbox/bob", 1)
        (session.folder / MARKS).unlink()

        assert await session.marks() == {}
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "item.recorded"), session)


async def test_a_marks_file_that_holds_no_marks_yet_has_none(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()
    (folder / MARKS).write_bytes(b"")

    assert session_module._marks_of(folder, "human:ada") == {}


async def test_marks_need_no_runtime_and_reading_them_writes_nothing(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path):
        pass

    async with Session.attach("s", root=tmp_path) as history:
        assert await history.marks() == {}
        assert not (history.folder / MARKS).exists()
        await history.mark("agent/bob", 2)
        assert await history.marks() == {"agent/bob": 2}


async def test_a_view_credential_moves_no_mark(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path):
        pass

    async with Session.attach("s", view=True, root=tmp_path) as viewer:
        with pytest.raises(Refused) as refused:
            await viewer.mark("agent/bob", 2)

        assert refused.value.refusal.code == "not_permitted"
        assert await viewer.marks() == {}
        assert not (viewer.folder / MARKS).exists()


@pytest.mark.parametrize(("stream", "seq"), [("", 1), ("x" * 513, 1), ("inbox/\n", 1), ("inbox/bob", -1)])
async def test_a_mark_that_names_no_stream_or_seq_is_refused(tmp_path, stream, seq):
    with pytest.raises(Refused) as refused:
        session_module._mark(tmp_path, "human:ada", stream, seq)

    assert refused.value.refusal.code == "invalid"


async def roster(session: Session) -> dict[str, dict[str, Any]]:
    rows = (await anext(aiter(session.watch("roster"))))["rows"]
    return {row["agent"]: row for row in rows}


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
        posted = await session.board_post(
            "notes", "spec", "the spec", body="line one\nline two\n", fields={"state": "draft"}
        )
        revised = await session.board_revise(
            "notes", "spec", "the spec, revised", posted["version"], fields={"state": "done"}
        )

        with pytest.raises(Refused) as stale:
            await session.board_revise("notes", "spec", "too late", posted["version"])

        got = await session.board_get("notes", "spec")
        old = await session.board_get("notes", "spec", version=1, range="L2-2")
        found = await session.board_query("notes", where={"state": "done"})

    assert revised["version"] == 2
    assert stale.value.refusal.code == "conflict"
    assert (got["version"], got["gist"]) == (2, "the spec, revised")
    assert old["text"] == "line two\n"
    assert [row["name"] for row in found["results"]] == ["spec"]


async def test_a_queue_through_the_facade(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        added = await session.task_add("tasks", "do it", body="in detail")
        claim = await session.task_claim("tasks")
        renewed = await session.task_renew("tasks")
        await session.task_release("tasks")
        await session.task_claim("tasks", task=added["task"])
        await session.task_complete("tasks", gist="done", body="how it went")
        await session.task_add("tasks", "do it again")
        await session.task_claim("tasks")
        await session.task_fail("tasks", gist="it broke")
        listed = await session.task_list("tasks", state="done")

    assert claim["task"] == added["task"] and renewed["fence"] == claim["fence"]
    assert [task["result"] for task in listed["tasks"]] == ["done"]


async def test_messages_through_the_facade(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("+crew", "to the crew")
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
        ref = await session.put_body(b"already here")

        await session.send("#news", "with a ref", body=ref)

        assert (await of_type(session, "message.sent"))[-1].data["body"] == ref


async def test_a_body_is_its_hash_to_the_body_api_and_read_by_the_ref_of_its_event(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        body = await session.put_body(b"the real content\n")
        posted = await session.board_post("notes", "a", "gist", body=body)

        got = await session.board_get("notes", "a")

        assert (got["ref"], got["body"], got["text"]) == (posted["ref"], True, "the real content\n")
        assert await session.get_body(body) == b"the real content\n"
        assert (await session.blob(posted["ref"]))["text"] == "the real content\n"
        await session.tombstone(body)
        with pytest.raises(Refused):
            await session.get_body(body)


async def test_lifecycle_through_the_facade(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": scripted()}, "lead": {"harness": scripted(), "count": 0}}})

    async with Session.start(team, root=tmp_path) as session:
        await session.spawn("ada", "bob")
        await in_state(session, "ada", "idle")
        await session.retire("@ada")
        await in_state(session, "ada", "ended")
        await session.spawn("eve", "bob")
        await in_state(session, "eve", "idle")
        await session.cancel_agent("@eve")

        rows = {row["agent"]: row["status"] for row in await session.agents()}
        assert rows["ada"] == "retired" and rows["eve"] == "cancelled"
        assert await session.peers() is not None
        assert (await session.channels())["channels"] == []
        assert "session.status" in {op["name"] for op in await session.ops()}
        assert (await session.manifest())["manifest"].startswith("sha256:")


async def test_channels_and_budgets_through_the_facade(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await session.create_channel("later", "topic", delivery="next-turn")
        await session.set_budget(limits={"turns": 10})
        await session.open_episode("first")
        await session.close_episode({"score": 1})

        assert [row["name"] for row in (await session.channels())["channels"]] == ["#later"]
        assert (await session.budgets())[0]["limit"] == 10.0


async def test_a_body_can_be_read_and_redacted(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        body = await session.put_body(b"line\n")
        sent = await session.send("@bob", "read this", body=body)

        assert (await session.blob(sent["ref"]))["text"] == "line\n"

        await session.tombstone(body)

        with pytest.raises(Refused):
            await session.get_body(body)
        with pytest.raises(Refused):
            await session.blob(sent["ref"])


async def test_a_wait_for_every_agent_says_how_it_closed(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": scripted([Call("agent_finish", {})]), "count": 0}}})

    async with Session.start(team, root=tmp_path) as session:
        await session.spawn("ada", "bob", "be quick")
        await session.spawn("eve", "bob", "be quick")

        closed = await asyncio.wait_for(session.wait(agents=["@ada", "@eve"]), SECONDS)

    assert closed["state"] == "released"


async def test_a_wait_for_any_stops_at_the_first(tmp_path):
    roles = {
        "bob": {"harness": scripted([Call("agent_finish", {})]), "count": 0},
        "slow": {"harness": scripted([Hang()]), "count": 0},
    }

    async with Session.start(Team.model_validate({"roles": roles}), root=tmp_path) as session:
        await session.spawn("ada", "bob", "be quick")
        await session.spawn("eve", "slow", "take your time")

        closed = await asyncio.wait_for(session.wait(agents=["@ada", "@eve"], mode="any"), SECONDS)

    assert closed["state"] == "released"


async def test_a_wait_on_a_condition_stated_outright(tmp_path):
    async with Session.start(worker_team(), root=tmp_path) as session:
        closed = await asyncio.wait_for(session.wait(on=[on("agent/bob", ("agent.started",))]), SECONDS)

    assert closed["state"] == "released"


async def test_a_guest_can_wait_on_a_condition_stated_outright(tmp_path):
    async with Session.start(worker_team(), name="s", root=tmp_path), Session.attach("s", root=tmp_path) as guest:
        closed = await asyncio.wait_for(guest.wait(on=[on("agent/bob", ("agent.started",))]), SECONDS)

    assert closed["state"] == "released"


async def test_a_wait_for_an_agent_nobody_spawned_is_refused_and_hangs_nothing(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        with pytest.raises(Refused) as refused:
            await asyncio.wait_for(session.wait(agents=["@nobody"]), SECONDS)

    assert refused.value.refusal.code == "not_found"


async def test_live_text_of_nobody_is_refused_and_hangs_nothing(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        with pytest.raises(Refused) as refused:
            await asyncio.wait_for(anext(session.deltas("@nobody")), SECONDS)

    assert refused.value.refusal.code == "not_found"


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
    reason = "its harness exited again before a turn of its ended: it fell over"
    assert (ending.agents[0]["status"], ending.agents[0]["reason"]) == ("lost", reason)


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


async def test_a_join_of_three_workers_costs_its_lead_one_turn_after_the_first(tmp_path):
    """The workers start idle and are told to go once the wait is placed, as a scripted worker is quicker than any."""
    names = ["a", "b", "c"]
    spawned = [Call("agent_spawn", {"name": name, "child_role": "worker"}) for name in names]
    told = [Call("message_send", {"to": f"@{name}", "gist": "go"}) for name in names]
    team = Team.model_validate(
        {
            "roles": {
                "lead": {
                    "harness": scripted([*spawned, Call("wait", {"agents": names}), *told], [Say("all three are in")]),
                    "may_spawn": ["worker"],
                },
                "worker": {"harness": scripted([Call("agent_finish", {"gist": "done"})])},
            },
            "topology": {"edges": {"lead": ["children"]}},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@lead", "go")
        ending = await session.settled(timeout="10s")
        turns = [event for event in await of_type(session, "turn.started") if event.agent == "lead"]
        said = [event.gist for event in await of_type(session, "item.recorded") if event.agent == "lead"]

    assert ending.reason == "settled"
    assert len(turns) == 2
    assert "all three are in" in said


async def test_a_child_that_stays_answers_a_task_a_follow_up_and_a_question_on_one_harness(tmp_path):
    """The owner's flow: each answer wakes the lead, nothing else does, and the lead retires the helper at the end."""
    spawned = Call("agent_spawn", {"name": "helper", "child_role": "helper", "goal": "first task", "stays": True})
    lead = [
        [spawned],
        [Call("message_send", {"to": "@helper", "gist": "a follow-up task"})],
        [Call("message_send", {"to": "@helper", "gist": "what did you mean?"})],
        [Call("agent_retire", {"agent": "@helper"}), Call("agent_finish", {"gist": "all done"})],
    ]
    helper = [[Say("first answer")], [Say("second answer")], [Say("it meant this")]]
    team = Team.model_validate(
        {
            "roles": {
                "lead": {"harness": scripted(*lead), "may_spawn": ["helper"]},
                "helper": {"harness": scripted(*helper)},
            },
            "topology": {"edges": {"lead": ["children"]}, "limits": {"max_hops": 8}},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@lead", "go")
        ending = await session.settled(timeout="10s")
        events = [event async for event in session.events()]

    turns = [event.agent for event in events if event.type == "turn.started"]
    reports = [event.data["delivery"] for event in events if event.type == "message.sent" and event.data["subject"]]
    statuses = {row["agent"]: row["status"] for row in ending.agents}
    assert ending.reason == "settled"
    assert (turns.count("lead"), turns.count("helper")) == (4, 3)
    assert [event.agent for event in events if event.type in ("agent.started", "agent.resumed")] == ["lead", "helper"]
    assert reports == ["wake", "wake", "wake", "next-turn"]
    assert statuses == {"lead": "finished", "helper": "retired"}


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


def until_lead(*turns: Any, **fields: Any) -> Team:
    """A team that closes when `lead` ends."""
    roles = {"lead": {"harness": scripted(*turns)}}
    return Team.model_validate({"roles": roles, "topology": {"until": "role:lead"}, **fields})


async def stalled_in(session: Session) -> None:
    await until(session.status, session, lambda status: status["stalled"])


async def test_a_session_settled_short_of_until_is_exit_4_and_never_a_hang(tmp_path):
    async with Session.start(until_lead([Say("I think we are done")]), root=tmp_path) as session:
        await session.send("@lead", "go")

        ending = await asyncio.wait_for(session.settled(), SECONDS)

    assert (ending.state, ending.reason) == ("open", "needs_human")


async def test_two_agents_waiting_on_each_other_is_exit_4_and_never_a_hang(tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "lead": {"harness": scripted([Call("wait", {"from": ["peer"]})])},
                "peer": {"harness": scripted([Call("wait", {"from": ["lead"]})])},
            },
            "topology": {"until": "role:lead"},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@lead", "go")
        await session.send("@peer", "go")

        ending = await asyncio.wait_for(session.settled(), SECONDS)

    assert ending.reason == "needs_human"


def lead_over(lead: str, worker: str) -> Team:
    roles = {"lead": {"harness": lead, "may_spawn": ["worker"]}, "worker": {"harness": worker, "count": 0}}
    return Team.model_validate(
        {"roles": roles, "topology": {"manager-worker": {"manager": "lead", "workers": "worker"}}}
    )


async def said(session: Session, text: str) -> None:
    await until(
        lambda: of_type(session, "item.recorded"), session, lambda found: text in [event.gist for event in found]
    )


async def test_a_report_a_held_wait_held_back_reaches_a_turn(tmp_path):
    spawned = Call("agent_spawn", {"name": "w1", "child_role": "worker", "goal": "go"})
    lead = scripted([spawned, Call("wait", {"agents": ["w1"], "hold": 5.0})], [Say("the lead heard it")])
    worker = scripted([Call("agent_finish", {"gist": "the answer is 42"})])

    async with Session.start(lead_over(lead, worker), root=tmp_path) as session:
        await session.send("@lead", "go")
        await said(session, "the lead heard it")


async def test_a_join_on_tasks_whose_only_worker_stops_short_wakes_the_lead(tmp_path):
    added = [Call("task_add", {"queue": "tasks", "gist": gist}) for gist in ("one", "two")]
    spawned = Call("agent_spawn", {"name": "w1", "child_role": "worker", "goal": "do one"})
    joined = Call("wait", {"tasks": ["tasks/1", "tasks/2"]})
    lead = scripted([*added, spawned, joined], [Say("the lead heard it")])
    claimed = Call("task_claim", {"queue": "tasks"})
    worker = scripted([claimed, Call("task_complete", {"queue": "tasks"}), Call("agent_finish", {"gist": "enough"})])

    async with Session.start(lead_over(lead, worker), root=tmp_path) as session:
        await session.send("@lead", "go")
        await said(session, "the lead heard it")


async def test_two_agents_parked_on_each_other_end_a_session_with_no_root_needs_human(tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "a": {"harness": scripted([Call("wait", {"from": ["b"]})])},
                "b": {"harness": scripted([Call("wait", {"from": ["a"]})])},
            }
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@a", "go")
        await session.send("@b", "go")

        ending = await asyncio.wait_for(session.settled(), SECONDS)

    assert ending.reason == "needs_human"


async def test_a_worker_parked_for_more_work_leaves_a_session_with_no_root_to_close(tmp_path):
    channels = {"tasks": {"kind": "queue", "writers": "all", "readers": "all"}}
    team = Team.model_validate(
        {
            "roles": {"bob": {"harness": scripted([Call("wait", {"queue": ["tasks"]})])}},
            "topology": {"channels": channels},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@bob", "go")

        ending = await asyncio.wait_for(session.settled(), SECONDS)

    assert ending.reason == "settled"


async def test_a_wall_limit_to_come_does_not_hold_off_a_stall(tmp_path):
    clock = ManualClock(1000.0)
    team = until_lead([Say("I think we are done")], budget={"wall": "1m"})

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        await session.send("@lead", "go")

        ending = await asyncio.wait_for(session.settled(), SECONDS)

    assert (ending.state, ending.reason) == ("open", "needs_human")


async def test_a_wake_the_budget_refuses_under_a_wall_limit_ends_the_session_needs_human_at_once(tmp_path):
    """Live run 42 waited out its wall limit here. A scripted turn reports no usage, so each is charged its estimate."""
    clock = ManualClock(1000.0)
    budget = {"wall": "1m", "tokens": 100, "estimate": {"tokens": 60}}
    team = Team.model_validate({"roles": {"bob": {"harness": scripted([Say("one")], [Say("two")])}}, "budget": budget})

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        await session.send("@bob", "and again")

        ending = await asyncio.wait_for(session.settled(), SECONDS)
        refused = await of_type(session, "wake.refused")

    assert (ending.state, ending.reason) == ("open", "needs_human")
    assert [event.data["why"] for event in refused] == ["over_budget"]


async def test_a_wait_deadline_to_come_is_waited_for_and_then_it_is_a_human_s_turn(tmp_path):
    clock = ManualClock(1000.0)
    team = until_lead([Call("wait", {"from": ["you"], "timeout": 60.0})], [Say("nobody came")])

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        await session.send("@lead", "go")
        settling = asyncio.ensure_future(session.settled())
        await in_state(session, "lead", "waiting")
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1060.0)
        assert not settling.done()

        clock.advance(60.0)

        ending = await asyncio.wait_for(settling, SECONDS)
        said = [event.gist for event in await of_type(session, "item.recorded")]

    assert ending.reason == "needs_human"
    assert "nobody came" in said


async def test_a_finish_cut_off_by_its_timer_brings_the_session_to_until(tmp_path):
    clock = ManualClock(1000.0)
    team = until_lead([Call("agent_finish", {"gist": "done"}), Hang()])

    async with Session.start(team, root=tmp_path, clock=clock) as session:
        await session.send("@lead", "go")
        settling = asyncio.ensure_future(session.settled())
        await until(lambda: of_type(session, "agent.finished"), session)
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1060.0)

        clock.advance(60.0)

        ending = await asyncio.wait_for(settling, SECONDS)

    assert ending.reason == "settled"
    assert ending.agents[0]["status"] == "finished"


async def test_a_guest_that_could_act_holds_off_needs_human(tmp_path):
    team = until_lead([Say("I think we are done")], [Call("agent_finish", {"gist": "done"})])

    async with Session.start(team, name="s", root=tmp_path) as session:
        guest = await Session.attach("s", root=tmp_path)
        await session.send("@lead", "go")
        settling = asyncio.ensure_future(session.settled())
        await stalled_in(session)
        assert not settling.done()

        await guest.send("@lead", "finish up")

        assert (await asyncio.wait_for(settling, SECONDS)).reason == "settled"
        await guest.leave()


@pytest.mark.parametrize("wanted", ["a stall", "an ask"])
async def test_a_guest_that_leaves_having_done_nothing_ends_the_wait_for_it(tmp_path, wanted):
    clock = ManualClock(1000.0)
    team = until_lead([Say("I think we are done") if wanted == "a stall" else Ask("may I?")])

    async with Session.start(team, name="s", root=tmp_path, clock=clock) as session:
        guest = await Session.attach("s", root=tmp_path)
        await session.send("@lead", "go")
        settling = asyncio.ensure_future(session.settled())
        await until(session.status, session, lambda status: status["stalled"] or status["asking"])
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1001.0)
        assert not settling.done()

        serving = tuple(session._runtime.control._serving)
        await guest.leave()
        await asyncio.wait_for(asyncio.gather(*serving), SECONDS)
        clock.advance(1.0)

        assert (await asyncio.wait_for(settling, SECONDS)).reason == "needs_human"


async def test_two_guests_in_settled_wait_on_each_other_until_one_gives_up(tmp_path, monkeypatch):
    monkeypatch.setattr(session_module, "_CLIENT_SECONDS", 0.01)

    async with Session.start(until_lead([Say("I think we are done")]), name="s", root=tmp_path) as session:
        await session.send("@lead", "go")
        await stalled_in(session)
        patient, hurried = [await Session.attach("s", root=tmp_path) for _ in range(2)]
        waiting = asyncio.ensure_future(patient.settled())

        assert (await hurried.settled(timeout=0.01)).reason == "timed_out"
        await hurried.leave()

        assert (await asyncio.wait_for(waiting, SECONDS)).reason == "needs_human"
        await patient.leave()


async def test_a_view_credential_cannot_act_so_it_holds_nothing_off(tmp_path):
    async with Session.start(until_lead([Say("I think we are done")]), name="s", root=tmp_path) as session:
        viewer = await Session.attach("s", view=True, root=tmp_path)
        await session.send("@lead", "go")

        ending = await asyncio.wait_for(session.settled(), SECONDS)

        await viewer.leave()

    assert ending.reason == "needs_human"


async def test_cancel_stops_the_session_and_cannot_be_handed_an_agent_by_accident(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        with pytest.raises(TypeError):
            await session.cancel(None)

        assert (await session.status())["state"] == "open"


async def test_cancelling_one_agent_says_which(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")

        await session.cancel_agent("@bob")

        await in_state(session, "bob", "ended")
        assert (await session.status())["state"] == "open"


async def test_cancelling_is_exit_130(tmp_path):
    async with Session.start(solo([Hang()]), root=tmp_path) as session:
        await session.send("@bob", "go")
        await in_state(session, "bob", "running")
        settling = asyncio.ensure_future(session.settled(timeout="10s"))
        await session.cancel()

        ending = await asyncio.wait_for(settling, SECONDS)

    assert (ending.state, ending.reason) == ("cancelled", "cancelled")
    assert ending.agents[0]["status"] == "cancelled"


async def test_what_a_guest_reads_of_a_stalled_session_says_what_settled_says(tmp_path):
    async with Session.start(until_lead([Say("I think we are done")]), name="s", root=tmp_path) as session:
        await session.send("@lead", "go")
        await stalled_in(session)

        assert (await session.ending()).reason == "needs_human"


async def test_a_closed_session_short_of_until_has_not_stalled(tmp_path):
    async with Session.start(until_lead([Say("I think we are done")]), name="s", root=tmp_path) as session:
        await session.send("@lead", "go")
        await stalled_in(session)

        await session.close()

        status = await until(session.status, session, lambda status: status["settled"])
        assert status["stalled"] is False
        assert (await session.ending()).reason == "settled"


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


# What a harness says after `agent_finish`.


class ReportsAsItsTurnEnds(ScriptedDriver):
    """A harness that reports usage when its turn ends, as a real one does."""

    async def _walk(self, steps: Any) -> str:
        reason = await super()._walk(steps)
        await self._report(Usage(tokens=1000, label="provider", scope="turn"))
        return reason


async def test_usage_after_agent_finish_is_charged_and_a_teammate_s_next_wake_runs(tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "ada": {"harness": harness(lambda: ReportsAsItsTurnEnds([[Say("done"), Call("agent_finish", {})]]))},
                "bob": {"harness": scripted([Say("bob ran")])},
            },
            "budget": {"tokens": 100_000, "estimate": {"tokens": 1000}},
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.send("@ada", "go")
        await until(lambda: of_type(session, "agent.ended"), session)
        await session.send("@bob", "your turn")

        ending = await session.settled(timeout="10s")

    assert ending.reason == "settled"
    rows = {row["agent"]: row for row in ending.agents}
    assert rows["ada"]["usage"]["tokens"] == {"amount": 1000.0, "label": "provider", "unmeasured": 0}
    assert rows["ada"]["report"] == {"gist": "done", "body": rows["ada"]["report"]["body"]}
    assert rows["bob"]["report"]["gist"] == "bob ran"


async def test_an_exec_agent_that_finishes_keeps_what_it_printed(tmp_path):
    script = tmp_path / "agent.sh"
    script.write_text('#!/bin/sh\nph agent.finish >/dev/null\necho "my last words"\n')
    script.chmod(0o700)
    team = Team.model_validate(
        {
            "roles": {
                "bob": {"harness": scripted()},
                "ada": {"harness": {"command": [str(script), "{goal}"], "mode": "oneshot"}, "count": 0},
            }
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.spawn("ada", "ada", "go")
        await until(lambda: of_type(session, "agent.ended"), session)
        ending = await session.ending()

    row = next(row for row in ending.agents if row["agent"] == "ada")
    assert row["status"] == "finished"
    assert row["report"]["gist"] == "my last words"


async def test_a_session_that_ran_a_harness_with_no_meter_says_nothing_of_tokens(tmp_path):
    async with Session.start(solo([Say("done")]), root=tmp_path) as session:
        await session.send("@bob", "go")

        ending = await session.settled(timeout="10s")

    assert ending.usage["tokens"] == {"amount": None, "label": "unavailable", "unmeasured": 1}
    assert ending.usage["turns"] == {"amount": 1.0, "label": "counted", "unmeasured": 0}


async def test_a_failed_spawn_says_why_in_the_ending(tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "bob": {"harness": {"command": ["true", "{goal}"], "mode": "oneshot"}, "count": 0},
                "z": {"harness": scripted()},
            }
        }
    )

    async with Session.start(team, root=tmp_path) as session:
        await session.spawn("ada", "bob")
        await in_state(session, "ada", "ended")
        ending = await session.ending()

    row = next(row for row in ending.agents if row["agent"] == "ada")
    assert row["reason"].startswith("its spawn failed: a one-shot harness takes nothing after its goal")


async def test_a_message_that_gets_in_ahead_of_a_close_keeps_the_session_open(tmp_path):
    async with Session.start(solo([Say("first")], [Say("second")]), root=tmp_path) as session:
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        real, raced = session._do, []

        async def racing(op: str, **args: Any) -> Any:
            if op == "session.close" and not raced:
                raced.append(await session.send("@bob", "one more thing"))
            return await real(op, **args)

        session._do = racing

        ending = await session.settled(timeout="10s")

        said = [event.gist for event in await of_type(session, "item.recorded")]

    assert said == ["first", "second"]
    assert ending.reason == "settled"


async def test_a_message_after_a_close_is_refused_and_not_dropped_in_silence(tmp_path):
    async with Session.start(solo(), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.close()

        with pytest.raises(Refused) as refused:
            await session.send("@bob", "too late")

    assert refused.value.refusal.code == "conflict"


async def test_a_guest_on_history_outlives_a_writer(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path):
        pass
    history = await Session.attach("s", root=tmp_path)

    async with Session.resume("s", root=tmp_path) as resumed:
        await in_state(resumed, "bob", "idle")

    assert (await history.status())["state"] == "stopped"
    await history.leave()


async def test_a_detached_runtime_cannot_be_fooled_by_a_module_in_the_working_directory(tmp_path, monkeypatch):
    planted = tmp_path / "planted"
    planted.mkdir()
    marker = tmp_path / "ran"
    (planted / "secrets.py").write_text(f"open({str(marker)!r}, 'w').close()\nraise SystemExit(9)\n")
    monkeypatch.chdir(planted)
    team = Team.model_validate({"roles": {"bob": {"harness": wire("saying")}}})

    guest = await Session.start(team, root=tmp_path / "root", detach=True)
    await guest.cancel()
    await guest.leave()

    assert not marker.exists()
