"""The page's server, route by route and refusal by refusal, over a session the test owns, on a real socket."""

import asyncio
import errno
import json
import socket
import sqlite3
from pathlib import Path

import pytest

from platoon_harness import Session
from platoon_harness.http import SECONDS
from platoon_harness.kernel import ManualClock
from platoon_harness.runtime.control import BODY_LIMIT
from platoon_harness_cli.ops import cut
from platoon_harness_cli.web import LOOK
from platoon_harness_cli.web import server as server_module
from platoon_harness_cli.web.credentials import LINK_SECONDS, SESSION_SECONDS
from platoon_harness_cli.web.page import load
from platoon_harness_cli.web.projection import Projection
from platoon_harness_cli.web.server import Web

from ..runtime.support import in_state, of_type, until
from .support import QUIET, Browser, caught_up, scenario, served, team

pytestmark = pytest.mark.timeout(60)

VIEWS = (
    "view_page",
    "view_info",
    "view_snapshot",
    "view_messages",
    "view_thread",
    "view_receipts",
    "view_search",
    "view_as",
    "view_knew",
    "view_text",
    "view_download",
    "view_feed",
)


def key(n: int) -> str:
    """A key as the page makes one for an act: 32 lowercase hex."""
    return f"{n:032x}"


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
async def session(root):
    async with Session.start(QUIET, name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        yield session


@pytest.fixture
def clock():
    return ManualClock(1_000_000.0)


@pytest.fixture
async def web(session, root, clock):
    async with served(session, root, clock) as web:
        yield web


async def test_the_gate_is_served_under_the_policy_and_kept_by_no_cache(web):
    reply = await Browser(web).request("GET", "/view")

    assert reply.status == 200 and reply.body == load().gate
    assert reply.headers["content-security-policy"] == load().policy
    assert reply.headers["cache-control"] == "no-store"
    assert (reply.headers["x-content-type-options"], reply.headers["referrer-policy"]) == ("nosniff", "no-referrer")


async def test_health_answers_with_no_token(web):
    reply = await Browser(web).request("GET", "/v1/health")

    assert reply.status == 200
    assert reply.json() == {
        "ok": True,
        "name": "platoon-harness",
        "version": reply.json()["version"],
        "limits": {"max_text": 20_000, "max_attachment": BODY_LIMIT, "max_attachments": 1},
    }


async def test_a_link_opens_once_for_a_session_token_of_its_class(web):
    browser = Browser(web)
    link = web.link("view")

    first = await browser.exchange(link)
    again = await browser.exchange(link)

    assert first.status == 200 and first.json()["class"] == "view"
    token = first.json()["token"]
    assert len(token) == 64 and token == token.lower() and int(token, 16) >= 0
    assert again.status == 401 and "used already" in again.json()["error"]


async def test_a_link_nobody_spent_expires(web, clock):
    link = web.link("control")
    clock.advance(LINK_SECONDS)

    assert (await Browser(web).exchange(link)).status == 401


async def test_a_session_token_expires(web, clock):
    browser = await Browser(web).opened("view")
    assert (await browser.request("POST", "/v1/view_info", {})).status == 200

    clock.advance(SESSION_SECONDS)

    reply = await browser.request("POST", "/v1/view_info", {})
    assert reply.status == 401 and "expired" in reply.json()["error"]


@pytest.mark.parametrize("token", ["", "0" * 64, "not a token"])
async def test_a_view_route_needs_a_session_token(web, token):
    reply = await Browser(web).request("POST", "/v1/view_snapshot", {}, token=token)

    assert reply.status == 401


@pytest.mark.parametrize("route", ["/x/command", "/x/body", "/x/link"])
async def test_a_view_credential_reaches_no_route_that_acts_or_mints(web, session, route):
    browser = await Browser(web).opened("view")
    head = await session.head()

    reply = await browser.request("POST", route, {"op": "session.close", "args": {}, "key": "k", "class": "control"})

    assert reply.status == 403 and "acts on nothing" in reply.json()["error"]
    assert await session.head() == head


async def test_a_view_credential_never_becomes_a_control_one(web):
    browser = await Browser(web).opened("view")

    info = await browser.view("view_info")

    assert info["x"]["credential"] == "view" and info["x"]["may"] == []
    assert "acts on nothing" in info["x"]["cannot"]
    assert (await browser.exchange(f"#link={browser.token}")).status == 401


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1:1", None])
async def test_a_foreign_host_is_refused(web, host):
    browser = await Browser(web).opened("view")

    for method, path in (("GET", "/view"), ("POST", "/v1/view_info")):
        reply = await browser.request(method, path, {}, headers={"Host": host})
        assert reply.status == 421, path


@pytest.mark.parametrize("origin", ["http://evil.example", "https://127.0.0.1", None])
async def test_a_post_from_another_origin_or_none_is_refused(web, origin):
    browser = await Browser(web).opened("control")

    reply = await browser.request("POST", "/x/command", {"op": "session.close", "key": "k"}, headers={"Origin": origin})

    assert reply.status == 403


async def test_localhost_is_this_server_too(web):
    browser = await Browser(web).opened("view")
    localhost = f"localhost:{web.port}"

    reply = await browser.request(
        "POST", "/v1/view_info", {}, headers={"Host": localhost, "Origin": f"http://{localhost}"}
    )

    assert reply.status == 200


async def test_every_address_a_name_has_is_served_on_the_one_port_said(session, clock):
    """`localhost` names two addresses here, and a port left free on one would be anyone's to take."""
    projection = Projection(session.folder, session.name, "you")
    web = Web(session, projection, load(), clock, host="localhost")
    await web.listen("localhost")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo("localhost", web.port, type=socket.SOCK_STREAM)}
        statuses = []
        for address in sorted(addresses):
            reader, writer = await asyncio.open_connection(address, web.port)
            writer.write(f"GET /v1/health HTTP/1.1\r\nHost: localhost:{web.port}\r\n\r\n".encode())
            statuses.append((await reader.read()).split(b" ")[1])
            writer.close()
    finally:
        await web.stop()
        projection.close()

    assert statuses == [b"200"] * len(addresses)


async def test_a_port_one_address_got_and_another_has_taken_is_left_for_one_free_on_both(session, clock, monkeypatch):
    """On a busy host, the free port the first address got is often taken on the second."""
    projection = Projection(session.folder, session.name, "you")
    web = Web(session, projection, load(), clock, host="localhost")
    start, calls = asyncio.start_server, []

    async def busy(serve, address, port, **options):
        if getattr(serve, "__self__", None) is web:
            calls.append((address, port))
            if len(calls) == 2:
                raise OSError(errno.EADDRINUSE, "taken")
        return await start(serve, address, port, **options)

    monkeypatch.setattr(asyncio, "start_server", busy)
    await web.listen("localhost")
    port = web.port
    await web.stop()
    projection.close()

    first, taken, *_, again, last = calls
    assert first[1] == again[1] == 0 and taken[1] != 0 and last[1] == port


async def test_the_scheme_s_own_port_is_left_out_of_the_host_as_a_browser_leaves_it(web, monkeypatch):
    monkeypatch.setattr(Web, "port", property(lambda self: 80))

    assert web.authorities == ("127.0.0.1", "localhost")
    assert web.link("view").startswith("http://127.0.0.1/view#link=")


async def test_a_body_too_large_is_refused_before_it_is_read(web):
    browser = await Browser(web).opened("control")
    head = f"POST /x/body HTTP/1.1\r\nHost: {browser.authority}\r\nOrigin: http://{browser.authority}\r\n"
    head += f"Authorization: Bearer {browser.token}\r\nContent-Length: {BODY_LIMIT + 1}\r\n\r\n"

    reply = await browser.send(head.encode())

    assert reply.status == 413


async def test_a_body_that_keeps_coming_is_read_however_long_it_takes(web, session, clock):
    """Each part of a body has `SECONDS` from the part before, so a large file can cross a slow link."""
    browser = await Browser(web).opened("control")
    data = bytes(range(256)) * 1200
    head = f"POST /x/body HTTP/1.1\r\nHost: {browser.authority}\r\nOrigin: http://{browser.authority}\r\n"
    head += f"Authorization: Bearer {browser.token}\r\nContent-Length: {len(data)}\r\n\r\n"
    reader, writer = await asyncio.open_connection("127.0.0.1", web.port)
    writer.write(head.encode())
    for start in range(0, len(data), 100_000):
        writer.write(data[start : start + 100_000])
        await writer.drain()
        await clock.slept_until(clock.now() + SECONDS)
        clock.advance(SECONDS - 1)
    async with asyncio.timeout(10):
        reply = await reader.read()
    writer.close()

    status, _, body = reply.partition(b"\r\n\r\n")
    assert status.startswith(b"HTTP/1.1 200") and clock.now() - 1_000_000.0 > SECONDS
    assert await session.get_body(json.loads(body)["ref"], limit=BODY_LIMIT) == data


async def test_a_body_that_stops_is_cut_once_nothing_has_come_for_the_deadline(web, clock):
    """The clock moves between parts, so that the wait for each is told apart from the one before."""
    browser = await Browser(web).opened("control")
    head = f"POST /x/body HTTP/1.1\r\nHost: {browser.authority}\r\nOrigin: http://{browser.authority}\r\n"
    head += f"Authorization: Bearer {browser.token}\r\nContent-Length: 100\r\n\r\n"
    reader, writer = await asyncio.open_connection("127.0.0.1", web.port)
    start = clock.now()
    for n, part in enumerate((head.encode(), b"x" * 50)):
        await clock.slept_until(start + n + SECONDS)
        clock.advance(1)
        writer.write(part)
        await writer.drain()
    await clock.slept_until(start + 2 + SECONDS)

    clock.advance(SECONDS)

    async with asyncio.timeout(10):
        assert await reader.read() == b""
    writer.close()


async def test_every_view_the_page_reaches_answers_from_the_projection(root, clock):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root, clock) as web:
        await scenario(session)
        await caught_up(web, session)
        browser = await Browser(web).opened("view")
        snapshot = await browser.view("view_snapshot")
        chats = {chat["name"] or " & ".join(chat["members"]): chat for chat in snapshot["chats"]}
        general = chats["general"]["id"]
        messages = (await browser.view("view_messages", {"chat": general}))["messages"]
        said = next(message for message in messages if message["kind"] == "message")
        with_file = (await browser.view("view_search", {"files": True}))["messages"]
        file = with_file[0]["attachments"][0]["id"]

        answers = {
            "view_page": await browser.view("view_page"),
            "view_thread": await browser.view("view_thread", {"id": said["id"]}),
            "view_receipts": await browser.view("view_receipts", {"id": said["id"]}),
            "view_as": await browser.view("view_as", {"user": "lead", "unread": True}),
            "view_knew": await browser.view("view_knew", {"id": said["id"]}),
            "view_text": await browser.view("view_text", {"id": file}),
            "view_feed": await browser.view("view_feed", {"after": 0, "feed_id": snapshot["server"]["feed_id"]}),
        }
        download = await browser.request("POST", "/v1/view_download", {"id": file})
        unbuilt = [await browser.request("POST", f"/v1/{name}", {}) for name in ("view_posts", "view_activity")]

    assert said["from"] == "lead" and said["x_ref"].startswith("channel/general@")
    assert "js" in answers["view_page"] and answers["view_thread"]["messages"][0]["depth"] == 0
    assert answers["view_receipts"]["id"] == said["id"]
    assert answers["view_as"]["user"]["id"] == "lead" and "unread_left" in answers["view_as"]
    assert answers["view_knew"]["user"] == "lead"
    assert answers["view_text"]["text"] and not answers["view_text"]["cut"]
    assert answers["view_feed"]["events"] and answers["view_feed"]["x"]["live"]
    assert download.status == 200 and json.loads(download.headers["x-attachment"])["id"] == file
    assert [reply.status for reply in unbuilt] == [404, 404]
    assert "not built yet" in unbuilt[0].json()["error"]


async def test_a_person_is_no_agent_to_be_seen_as(web):
    browser = await Browser(web).opened("view")

    reply = await browser.request("POST", "/v1/view_as", {"user": "you"})

    assert reply.status == 400 and "no agent" in reply.json()["error"]


async def test_browsing_writes_no_event_and_moves_no_cursor_or_mark(root, clock):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root, clock) as web:
        await scenario(session)
        await caught_up(web, session)
        journal = sqlite3.connect(f"{(session.folder / 'journal.sqlite').as_uri()}?mode=ro", uri=True)
        cursors = journal.execute("SELECT * FROM v_deliveries_cursors").fetchall()
        head = await session.head()
        browser = await Browser(web).opened("control")
        snapshot = await browser.view("view_snapshot")
        for chat in snapshot["chats"]:
            for message in (await browser.view("view_messages", {"chat": chat["id"]}))["messages"]:
                if message["kind"] == "message":
                    for name in ("view_thread", "view_receipts"):
                        await browser.view(name, {"id": message["id"]})
        await browser.view("view_as", {"user": "w1", "unread": True})
        await browser.view("view_search", {"text": "flaky"})
        await browser.view("view_info")

        assert await session.head() == head
        assert journal.execute("SELECT * FROM v_deliveries_cursors").fetchall() == cursors
        journal.close()
        assert not (session.folder / "marks.sqlite").exists()


async def test_a_command_runs_one_op_through_the_session(web, session):
    browser = await Browser(web).opened("control")

    reply = await browser.request(
        "POST", "/x/command", {"op": "message.send", "args": {"to": "#general", "gist": "hi"}, "key": key(1)}
    )

    outcome = reply.json()
    assert reply.status == 200 and outcome["refusal"] is None and outcome["result"]["ref"] == "channel/general@1"
    sent = [event for event in await of_type(session, "message.sent")]
    assert [(event.actor, event.gist) for event in sent] == [("human:you", "hi")]


async def test_a_command_retried_under_its_key_is_one_operation(web, session):
    browser = await Browser(web).opened("control")
    command = {"op": "message.send", "args": {"to": "#general", "gist": "once"}, "key": key(2)}

    first = (await browser.request("POST", "/x/command", command)).json()
    again = (await browser.request("POST", "/x/command", command)).json()

    assert first["seq"] == again["seq"] and first["result"] == again["result"]
    assert len(await of_type(session, "message.sent")) == 1


async def test_an_act_s_key_is_its_own_whichever_link_sends_it(web, session):
    """A new link is a new session token, and an act a page kept goes again from it under its key."""
    one, other = await Browser(web).opened("control"), await Browser(web).opened("control")
    command = {"op": "message.send", "args": {"to": "#general", "gist": "once"}, "key": key(3)}

    first = (await one.request("POST", "/x/command", command)).json()
    again = (await other.request("POST", "/x/command", command)).json()

    assert first["key"] == f"web/{key(3)}" and again == first
    assert len(await of_type(session, "message.sent")) == 1


@pytest.mark.parametrize(
    "command",
    [
        {"op": "message.send", "args": {"to": "#general", "gist": "x"}},
        {"op": "message.send", "args": {"to": "#general", "gist": "x"}, "key": "draft-1"},
        {"op": "message.send", "args": {"to": "#general", "gist": "x"}, "key": "A" * 32},
        {"op": "message.send", "args": [], "key": key(1)},
        {"op": "approval.resolve", "args": {"id": "a", "verdict": "allow", "via": "tui"}, "key": key(1)},
        {"op": "approval.resolve", "args": {"id": "a", "expected_version": 1}, "expected_version": 1, "key": key(1)},
    ],
)
async def test_a_command_not_as_the_page_sends_one_is_refused(web, session, command):
    browser = await Browser(web).opened("control")
    head = await session.head()

    assert (await browser.request("POST", "/x/command", command)).status == 400
    assert await session.head() == head


@pytest.mark.parametrize(
    "body",
    [
        b'{"op": "message.send", "args": {"to": "#general", "gist": "half \\ud800 of a character' + b"!" * 300 + b'"}}',
        b"[" * 100_000 + b"]" * 100_000,
    ],
)
async def test_a_body_that_is_not_json_of_unicode_text_is_refused_with_no_event(web, session, body):
    browser = await Browser(web).opened("control")
    head = await session.head()

    reply = await browser.request("POST", "/x/command", body)

    assert reply.status == 400 and "Unicode" in reply.json()["error"]
    assert await session.head() == head


@pytest.mark.parametrize(
    "params",
    [
        b'{"chats": 5}',
        b'{"from": [7]}',
        b'{"until": ["x", "c", 1]}',
        b'{"until": [1.0, "c", "x"]}',
        b'{"until": [1.0, "c", 1e400]}',
        b'{"limit": 1e400}',
    ],
)
async def test_a_search_the_page_could_not_have_made_is_refused_as_such(web, params):
    reply = await (await Browser(web).opened("view")).request("POST", "/v1/view_search", params)

    assert reply.status == 400


async def test_the_kernel_decides_what_a_person_may_run(web):
    browser = await Browser(web).opened("control")

    reply = await browser.request("POST", "/x/command", {"op": "agent.start", "args": {}, "key": key(1)})

    assert reply.status == 200 and reply.json()["refusal"]["code"] in ("not_permitted", "invalid")


async def test_an_approval_takes_its_version_and_says_browser_and_the_loser_hears_who_won(root, clock):
    from platoon_harness.testing import Ask, Hang

    async with Session.start(team([[Ask("Ship it?"), Hang()]], [[Hang()]]), name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        await session.send("@lead", "go")
        async with served(session, root, clock) as web:
            approval = (await until(session.approvals, session))[0]
            one, other = await Browser(web).opened("control"), await Browser(web).opened("control")
            args = {"id": approval["id"], "verdict": "allow"}
            command = {"op": "approval.resolve", "args": args, "expected_version": approval["version"]}

            won = (await one.request("POST", "/x/command", command | {"key": key(1)})).json()
            lost = (await other.request("POST", "/x/command", command | {"key": key(2)})).json()
            resolved = await of_type(session, "approval.resolved")

    assert won["refusal"] is None
    assert lost["refusal"]["code"] == "conflict"
    assert lost["refusal"]["detail"] | {"state": "?"} == {"state": "?", "resolved_by": "human:you", "via": "browser"}
    assert [(event.data["via"], event.data["verdict"]) for event in resolved] == [("browser", "allow")]


async def test_a_message_too_long_for_a_gist_is_cut_as_the_terminal_cuts_it(web, session):
    browser = await Browser(web).opened("control")
    text = "a long line " * 40
    command = {"op": "message.send", "args": {"to": "#general", "gist": text}, "key": key(4)}

    first = (await browser.request("POST", "/x/command", command)).json()
    again = (await browser.request("POST", "/x/command", command)).json()

    sent = await of_type(session, "message.sent")
    assert first["refusal"] is None and again == first and len(sent) == 1
    assert (sent[0].gist, await session.get_body(sent[0].data["body"])) == (cut(text)[0], text.encode())


async def test_a_long_message_beside_a_file_is_refused_with_no_event(web, session):
    browser = await Browser(web).opened("control")
    stored = (await browser.request("POST", "/x/body", b"a file")).json()["ref"]
    head = await session.head()
    args = {"to": "#general", "gist": "x" * 300, "body": stored}

    reply = await browser.request("POST", "/x/command", {"op": "message.send", "args": args, "key": key(5)})

    assert reply.status == 400 and "two bodies" in reply.json()["error"]
    assert await session.head() == head


async def test_a_body_is_stored_for_a_command_to_cite(web, session):
    browser = await Browser(web).opened("control")

    stored = (await browser.request("POST", "/x/body", b"the whole of it")).json()
    command = {"op": "message.send", "args": {"to": "#general", "gist": "a file", "body": stored["ref"]}, "key": key(6)}
    sent = (await browser.request("POST", "/x/command", command)).json()

    assert stored["ref"].startswith("sha256:") and sent["refusal"] is None
    assert await session.get_body(stored["ref"]) == b"the whole of it"


@pytest.mark.parametrize("kind", ["view", "control"])
async def test_a_control_session_mints_a_link_of_either_class(web, kind):
    browser = await Browser(web).opened("control")

    minted = (await browser.request("POST", "/x/link", {"class": kind})).json()
    opened = await Browser(web).exchange(minted["link"])

    assert minted["link"].startswith(f"http://{browser.authority}/view#link=")
    assert opened.json()["class"] == kind


async def test_the_feed_holds_until_something_comes(web, session, clock):
    browser = await Browser(web).opened("view")
    info = await browser.view("view_info")
    waiting = asyncio.ensure_future(browser.view("view_feed", {"after": info["feed"], "feed_id": info["feed_id"]}))
    await clock.slept_until(clock.now() + 25)
    assert not waiting.done()

    await session.send("#general", "news")

    fed = await asyncio.wait_for(waiting, 10)
    assert [event["message"]["text"] for event in fed["events"] if event["kind"] == "message"] == ["news"]


async def test_the_feed_holds_no_longer_than_the_page_asks(web, clock):
    browser = await Browser(web).opened("view")
    info = await browser.view("view_info")
    waiting = asyncio.ensure_future(browser.view("view_feed", {"after": info["feed"], "timeout": 5}))
    await clock.slept_until(clock.now() + 5)

    clock.advance(5)

    assert (await asyncio.wait_for(waiting, 10))["events"] == []


async def test_the_feed_holds_a_bounded_number_and_refuses_one_past_it(web, clock, monkeypatch):
    monkeypatch.setattr(server_module, "HOLDING", 1)
    browser = await Browser(web).opened("view")
    info = await browser.view("view_info")
    held = asyncio.ensure_future(browser.view("view_feed", {"after": info["feed"]}))
    await clock.slept_until(clock.now() + 25)

    reply = await browser.request("POST", "/v1/view_feed", {"after": info["feed"]})

    assert reply.status == 503
    held.cancel()


async def test_a_page_of_another_projection_takes_a_new_snapshot(web):
    browser = await Browser(web).opened("view")

    fed = await browser.view("view_feed", {"after": 0, "feed_id": "0" * 16})

    assert fed["reset"] is True


async def test_on_history_the_page_may_do_nothing_and_names_the_command_that_resumes(root, clock):
    async with Session.start(QUIET, name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
    async with Session.attach("s", root=root) as history, served(history, root, clock) as web:
        browser = await Browser(web).opened("control")
        info = await browser.view("view_info")
        command = {"op": "message.send", "args": {"to": "#general", "gist": "x"}, "key": key(1)}
        refused = (await browser.request("POST", "/x/command", command)).json()["refusal"]

    assert info["read_only"] is True and info["x"]["live"] is False and info["x"]["may"] == []
    assert "platoon-harness session resume s" in info["x"]["cannot"]
    assert refused["code"] == "unavailable" and "session resume s" in refused["detail"]


async def test_capabilities_name_the_person_their_grants_and_what_is_asked_first(web):
    browser = await Browser(web).opened("control")

    x = (await browser.view("view_info"))["x"]

    assert x["person"] == "you" and x["live"] is True and x["cannot"] is None
    assert {"message.send", "approval.resolve", "agent.interrupt"} <= set(x["may"])
    assert x["confirmed"] == ["agent.cancel", "agent.retire", "body.tombstone", "session.cancel", "session.close"]
    assert x["body_limit"] == BODY_LIMIT


async def test_web_folds_what_a_runtime_wrote_and_left_between_two_looks(root, clock):
    async with Session.start(QUIET, name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
    async with Session.attach("s", root=root) as history, served(history, root, clock) as web:
        await caught_up(web, history)
        await clock.slept_until(clock.now() + LOOK)
        async with Session.resume("s", root=root) as owner:
            await in_state(owner, "lead", "idle")
            await owner.send("#general", "while web looked away")

        clock.advance(LOOK)
        await caught_up(web, history)
        found = await (await Browser(web).opened("view")).view("view_search", {"text": "looked away"})

    assert [message["text"] for message in found["messages"]] == ["while web looked away"]
