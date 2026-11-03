"""The control socket: one link, a credential checked once, and clients that cost only their own lag."""

import asyncio
import json
import os
import stat
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Refused, Session, rpc
from platoon_harness.kernel import ManualClock, Outcome, hash_token
from platoon_harness.rpc import Closed, Peer
from platoon_harness.runtime import control
from platoon_harness.runtime.control import REFUSED, Remote
from platoon_harness.runtime.paths import OWNER_TOKEN, VIEW_TOKEN, read_running
from platoon_harness.testing import Say

from .support import SECONDS, in_state, journal, of_type, solo, until

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
async def owner(tmp_path: Path) -> AsyncIterator[Session]:
    async with Session.start(solo([Say("hello")]), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        yield session


@pytest.fixture
async def guest(owner: Session, tmp_path: Path) -> AsyncIterator[Session]:
    async with Session.attach("s", root=tmp_path) as session:
        yield session


@pytest.fixture
async def viewer(owner: Session, tmp_path: Path) -> AsyncIterator[Session]:
    async with Session.attach("s", view=True, root=tmp_path) as session:
        yield session


class Raw:
    """The client's side of the socket, frame by frame."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader, self.writer = reader, writer
        self.sent = 0

    @classmethod
    async def connect(cls, folder: Path) -> "Raw":
        running = read_running(folder)
        assert running is not None
        return cls(*await asyncio.open_unix_connection(running.socket))

    def send(self, method: str, params: Any = None) -> None:
        self.sent += 1
        frame = {"jsonrpc": "2.0", "id": self.sent, "method": method, "params": params or {}}
        self.writer.write(json.dumps(frame).encode() + b"\n")

    async def answer(self) -> dict[str, Any]:
        async with asyncio.timeout(SECONDS):
            return json.loads(await self.reader.readline())

    async def call(self, method: str, params: Any = None) -> dict[str, Any]:
        self.send(method, params)
        return await self.answer()

    async def hello(self, token: str, protocol: int = control.PROTOCOL) -> dict[str, Any]:
        return await self.call("hello", {"token": token, "protocol": protocol})

    def close(self) -> None:
        self.writer.close()


@pytest.fixture
async def raw(owner: Session) -> AsyncIterator[Raw]:
    connection = await Raw.connect(owner.folder)
    yield connection
    connection.close()


def token(session: Session, name: str = OWNER_TOKEN) -> str:
    return (session.folder / name).read_text()


def refusal_of(frame: dict[str, Any]) -> dict[str, Any]:
    assert frame["error"]["code"] == REFUSED, frame
    return frame["error"]["data"]


async def test_a_guest_is_the_same_class_with_no_power_over_the_runtime(owner, guest):
    assert type(guest) is type(owner)
    assert owner.owner and not guest.owner


async def test_the_socket_lives_apart_and_only_this_user_can_reach_it(owner):
    running = read_running(owner.folder)
    assert running is not None
    path = Path(running.socket)

    assert not path.is_relative_to(owner.folder)
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert (running.pid, running.incarnation) == (os.getpid(), 1)


async def test_tokens_are_files_only_this_user_can_read(owner):
    for name in (OWNER_TOKEN, VIEW_TOKEN):
        assert stat.S_IMODE((owner.folder / name).stat().st_mode) == 0o600


async def test_nothing_is_answered_before_hello(raw):
    assert refusal_of(await raw.call("read", {"after": 0}))["code"] == "not_permitted"


async def test_an_unknown_credential_is_refused_and_binds_nothing(raw):
    assert refusal_of(await raw.hello("not a token"))["code"] == "not_permitted"
    assert refusal_of(await raw.call("read", {"after": 0}))["code"] == "not_permitted"


async def test_a_credential_is_checked_once_per_connection(raw, owner):
    assert (await raw.hello(token(owner)))["result"]["principal"] == "human:you"
    assert refusal_of(await raw.hello(token(owner)))["code"] == "conflict"


async def test_an_unknown_protocol_is_refused(raw, owner):
    assert refusal_of(await raw.hello(token(owner), protocol=99))["code"] == "unsupported"


async def test_an_agent_s_token_is_for_the_tool_plane_alone(raw, owner):
    kernel = owner._runtime.kernel
    await kernel.submit(kernel.runtime, "principal.issue", {"id": "agent:bob", "token_hash": hash_token("agent-token")})

    assert "tool plane" in refusal_of(await raw.hello("agent-token"))["detail"]


async def test_a_connection_that_never_says_who_it_is_is_dropped(tmp_path):
    clock = ManualClock(1000.0)

    async with Session.start(solo(), name="s", root=tmp_path, clock=clock) as session:
        connection = await Raw.connect(session.folder)
        async with asyncio.timeout(SECONDS):
            await clock.slept_until(1010.0)

        clock.advance(10.0)

        assert await asyncio.wait_for(connection.reader.read(), SECONDS) == b""
        connection.close()


async def test_a_view_token_reads(viewer):
    assert (await viewer.status())["state"] == "open"
    assert [row["agent"] for row in await viewer.agents()] == ["bob"]
    assert (await journal(viewer))[0].type == "runtime.started"


async def test_a_view_token_can_never_submit_and_a_try_writes_nothing(viewer, owner):
    kernel = owner._runtime.kernel
    head = kernel.head

    outcome = await viewer.submit("message.send", to="@bob", gist="from a viewer")

    assert outcome.refusal is not None and outcome.refusal.code == "not_permitted"
    assert kernel.head == head
    with pytest.raises(Refused) as refused:
        await viewer.send("@bob", "typed")
    assert refused.value.refusal.code == "not_permitted"
    with pytest.raises(Refused):
        await viewer.put_body(b"a body")
    assert kernel.head == head


@pytest.mark.parametrize("op", ["session.status", "message.read", "task.list"])
async def test_a_read_submitted_is_answered_as_a_query_and_writes_nothing(viewer, guest, owner, op):
    """No client is an agent, so its reads are queries, which a view credential may ask too."""
    kernel = owner._runtime.kernel
    head = kernel.head
    args = {"queue": "nowhere"} if op == "task.list" else {}

    answers = [await client.submit(op, **args) for client in (viewer, guest)]

    assert [outcome.refusal for outcome in answers] == [answers[0].refusal] * 2
    assert all(outcome.seq is None for outcome in answers)
    assert [event.type async for event in owner.events(after=head) if event.actor != "runtime"] == []


async def test_a_control_credential_cannot_be_had_with_a_view_token(raw, owner):
    hello = await raw.hello(token(owner, VIEW_TOKEN))

    assert hello["result"]["writes"] is False
    assert (await raw.call("submit", {"op": "session.close", "args": {}}))["result"]["refusal"][
        "code"
    ] == "not_permitted"
    assert (await owner.status())["state"] == "open"


async def test_a_view_client_could_not_answer_an_approval(viewer, guest, owner):
    assert await owner._link.others() == 1
    assert await guest._link.others() == 0


async def test_a_refusal_crosses_the_socket_as_data(guest):
    outcome = await guest.submit("message.send", to="@nobody", gist="hello?")

    assert isinstance(outcome, Outcome)
    assert outcome.refusal is not None and outcome.refusal.code == "not_found"
    assert outcome.seq is not None


async def test_a_typed_call_raises_what_crossed(guest):
    with pytest.raises(Refused) as refused:
        await guest.send("@nobody", "hello?")

    assert refused.value.refusal.code == "not_found"
    assert refused.value.refusal.op == "message.send"


async def test_what_read_refuses_crosses_too(guest):
    with pytest.raises(Refused) as refused:
        await guest._link.read(-1)

    assert refused.value.refusal.code == "invalid"


async def test_a_method_nobody_defined_is_named(raw, owner):
    await raw.hello(token(owner))

    assert (await raw.call("shout"))["error"]["code"] == -32601


async def test_bad_params_are_no_crash(raw, owner):
    await raw.hello(token(owner))

    assert (await raw.call("read", {}))["error"]["code"] == -32602
    assert "result" in await raw.call("read", {"after": 0})


async def test_a_page_is_capped_so_it_fits_a_line(raw, owner):
    await raw.hello(token(owner))

    page = (await raw.call("read", {"after": 0, "limit": 4096}))["result"]

    assert len(page["events"]) <= 256 and page["cursor"] > 0


async def test_a_retry_under_one_key_is_one_operation(guest):
    first = await guest.submit("message.send", key="once", to="@bob", gist="only once")
    second = await guest.submit("message.send", key="once", to="@bob", gist="only once")

    assert first.seq == second.seq
    assert len(await of_type(guest, "message.sent")) == 1


async def test_a_retry_after_a_lost_ack_is_one_operation_and_gets_the_first_answer(guest, monkeypatch):
    real = Remote.submit
    lost = []

    async def losing(self: Remote, op: str, args: Any, **keys: Any) -> Outcome:
        outcome = await real(self, op, args, **keys)
        if not lost:
            lost.append(outcome)
            self._peer.close()
            raise Closed("the ack went with the connection")
        return outcome

    monkeypatch.setattr(Remote, "submit", losing)

    answered = await guest.send("@bob", "once, despite everything")

    assert lost[0].result == answered
    assert len(await of_type(guest, "message.sent")) == 1


async def test_a_retry_whose_runtime_went_for_good_after_it_committed_gets_the_first_answer(guest, owner, monkeypatch):
    """The ack goes with the runtime, so the retry finds history, which answers what the journal holds under its key
    and refuses anything else, naming what restarts the session."""
    real = Remote.submit
    lost = []

    async def losing(self: Remote, op: str, args: Any, **keys: Any) -> Outcome:
        lost.append(await real(self, op, args, **keys))
        await owner.leave()
        raise Closed("the ack went with the runtime")

    monkeypatch.setattr(Remote, "submit", losing)

    answered = await guest.submit("message.send", key="once", to="@bob", gist="once, though it went")
    other = await guest.submit("message.send", key="twice", to="@bob", gist="never sent")

    assert (answered.result, answered.seq) == (lost[0].result, lost[0].seq)
    assert other.refusal is not None and "platoon-harness session resume s" in other.refusal.detail
    assert [event.gist for event in await of_type(guest, "message.sent")] == ["once, though it went"]


async def test_calls_that_find_a_connection_gone_together_share_one_new_one(guest, owner):
    gone = guest._link
    gone._peer.close()

    answers = await asyncio.gather(*(guest.status("@bob") for _ in range(8)))

    assert [answer["state"] for answer in answers] == ["idle"] * 8
    assert guest._link is not gone
    assert await owner._link.others() == 1


async def test_a_client_that_reconnects_resumes_from_its_cursor(guest, owner):
    seen = [event async for event in guest.events()]
    guest._link._peer.close()

    await owner.send("@bob", "while you were away")

    after = [event async for event in guest.events(seen[-1].seq)]
    assert any(event.type == "message.sent" for event in after)
    assert not {event.seq for event in seen} & {event.seq for event in after}


async def test_following_is_a_read_plus_a_long_poll(guest, owner):
    events = guest.events(follow=True, match="inbox/*")
    next_event = asyncio.ensure_future(anext(events))

    await owner.send("@bob", "follow this")

    assert (await asyncio.wait_for(next_event, SECONDS)).gist == "follow this"
    await events.aclose()


async def test_a_long_poll_comes_back_empty_and_goes_round_again(guest, owner, monkeypatch):
    monkeypatch.setattr(control, "_POLL_SECONDS", 0.001)
    real = Remote._call
    twice = asyncio.Event()
    polls = []

    async def counting(self: Remote, method: str, params: Any) -> Any:
        answer = await real(self, method, params)
        if method == "changed" and answer["again"]:
            polls.append(answer)
            if len(polls) == 2:
                twice.set()
        return answer

    monkeypatch.setattr(Remote, "_call", counting)
    await until(owner.status, owner, lambda status: status["settled"])
    head = owner._runtime.kernel.head
    changed = asyncio.ensure_future(guest._link.changed(head))
    await asyncio.wait_for(twice.wait(), SECONDS)

    await owner.send("@bob", "a move")

    assert await asyncio.wait_for(changed, SECONDS) > head


async def test_live_text_crosses_the_socket(guest, owner):
    kernel = owner._runtime.kernel
    frames = guest.deltas("@bob")
    next_frame = asyncio.ensure_future(anext(frames))

    kernel.push_delta("bob", "typing")

    assert (await asyncio.wait_for(next_frame, SECONDS)).text == "typing"
    await frames.aclose()


async def test_live_text_of_an_agent_that_ended_says_so_once_across_the_socket(guest, owner):
    owner._runtime.kernel.push_delta("bob", "last words")
    frames = guest.deltas("@bob")
    assert (await asyncio.wait_for(anext(frames), SECONDS)).text == "last words"

    await owner.cancel_agent("@bob")

    rest = await asyncio.wait_for(alist(frames), SECONDS)
    ended = [event for event in await journal(owner) if event.type == "agent.ended"]
    assert [(frame.text, frame.ended) for frame in rest] == [("", ended[0].seq)]


async def alist[T](items: AsyncIterator[T]) -> list[T]:
    return [item async for item in items]


async def test_a_body_crosses_both_ways(guest):
    body = bytes(range(256)) * 16

    sha256 = await guest.put_body(body)

    assert await guest.get_body(sha256) == body


async def test_a_body_too_big_for_a_line_is_refused_before_it_is_sent(guest, monkeypatch):
    monkeypatch.setattr(control, "_BODY_LIMIT", 8)

    with pytest.raises(Refused) as refused:
        await guest.put_body(b"nine bytes")

    assert refused.value.refusal.code == "invalid"


async def test_a_client_that_stops_reading_is_dropped_and_costs_nobody_else(owner, monkeypatch):
    monkeypatch.setattr(rpc, "LINE_LIMIT", 64 * 1024)
    connection = await Raw.connect(owner.folder)
    await connection.hello(token(owner))
    outcomes = []

    async with asyncio.timeout(SECONDS):
        while not connection.reader.at_eof():
            connection.send("read", {"after": 0})
            try:
                await connection.writer.drain()
            except ConnectionError:
                break
            outcomes.append((await owner.send("@bob", "still moving"))["seq"])
            if len(outcomes) > 512:
                raise AssertionError("it was never dropped")

    assert outcomes == sorted(outcomes)
    assert (await owner.status())["state"] == "open"
    connection.close()


async def test_nothing_is_pushed_to_a_client_that_did_not_ask(owner):
    connection = await Raw.connect(owner.folder)
    await connection.hello(token(owner))
    await connection.call("changed", {"after": 0})

    await owner.send("@bob", "nobody asked for this")

    assert (await connection.call("others"))["id"] == connection.sent
    connection.close()


async def test_too_many_clients_are_turned_away(owner, monkeypatch):
    monkeypatch.setattr(control, "_CLIENT_LIMIT", 1)
    first = await Raw.connect(owner.folder)
    await first.hello(token(owner))

    second = await Raw.connect(owner.folder)

    assert await asyncio.wait_for(second.reader.read(), SECONDS) == b""
    first.close()
    second.close()


async def test_a_runtime_that_stops_drops_its_clients_and_they_find_history(tmp_path):
    owner = await Session.start(solo(), name="s", root=tmp_path)
    await in_state(owner, "bob", "idle")
    guest = await Session.attach("s", root=tmp_path)

    await owner.leave()

    assert (await guest.status())["state"] == "stopped"
    await guest.leave()


async def test_watching_a_view_needs_no_session_of_its_own(guest, owner):
    views = guest.watch("attention")
    first = await asyncio.wait_for(anext(views), SECONDS)
    assert first["snapshot"] is True

    changed = asyncio.ensure_future(anext(views))
    await owner.send("@you", "a note to self")

    assert (await asyncio.wait_for(changed, SECONDS))["snapshot"] is False
    await views.aclose()


# What no client may hold, and what shutdown cannot be made to wait on.


async def test_a_name_nobody_holds_gets_no_ring(owner):
    connection = await Raw.connect(owner.folder)
    await connection.hello((owner.folder / VIEW_TOKEN).read_text())
    kernel = owner._runtime.kernel
    before = len(kernel._rings)

    for index in range(32):
        answer = await connection.call("delta", {"agent": f"nobody{index}"})
        assert answer["error"]["code"] == REFUSED

    assert len(kernel._rings) == before


async def test_a_client_that_stopped_reading_cannot_hold_up_a_stop(owner, monkeypatch):
    peers = []

    class Kept(Peer):
        def __init__(self, *arguments: Any, **options: Any) -> None:
            super().__init__(*arguments, **options)
            peers.append(self)

    monkeypatch.setattr(control, "Peer", Kept)
    for _ in range(50):
        await owner.send("@bob", "x" * 200)
    stalled, other = await Raw.connect(owner.folder), await Raw.connect(owner.folder)
    await stalled.hello(token(owner))
    await other.hello(token(owner))

    while peers[0]._writer.transport.get_write_buffer_size() < 1024 * 1024:
        stalled.send("read", {"after": 0})
        await stalled.writer.drain()
        await other.call("others")

    await asyncio.wait_for(owner.leave(), SECONDS)


@pytest.mark.parametrize("turns", range(5))
async def test_a_connection_accepted_as_a_runtime_stops_is_dropped(owner, turns):
    running = read_running(owner.folder)
    assert running is not None
    reader, writer = await asyncio.open_unix_connection(running.socket)
    for _ in range(turns):
        await asyncio.sleep(0)

    await asyncio.wait_for(owner.leave(), SECONDS)

    assert await asyncio.wait_for(reader.read(), SECONDS) == b""
    writer.close()


async def test_a_refusal_the_transport_makes_is_a_refusal_like_any_other():
    assert control._refused(rpc.RpcError(rpc.BUSY, "too many requests in flight")).refusal.code == "busy"
    assert control._refused(rpc.RpcError(rpc.INVALID_PARAMS, "bad params")).refusal.code == "unavailable"


async def test_a_protocol_nobody_here_speaks_is_said_at_once(owner, monkeypatch):
    async def older(self: Remote, token: str) -> None:
        await self._call("hello", {"token": token, "protocol": control.PROTOCOL + 1})

    monkeypatch.setattr(Remote, "hello", older)
    guest = Session.attach(owner.name, root=owner.folder.parent.parent)

    with pytest.raises(Refused) as refused:
        await asyncio.wait_for(guest._entered(), SECONDS)

    assert refused.value.refusal.code == "unsupported"
