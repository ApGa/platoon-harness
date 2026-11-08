"""The sessions page's server, which `web` with no session serves: its one link and its own credentials, the list, and
opening a session on a port of its own, over sessions the test owns, on a real socket."""

import asyncio
import base64
import hashlib
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from platoon_harness import Session
from platoon_harness.kernel import ManualClock
from platoon_harness_cli.web import hold
from platoon_harness_cli.web.sessions import EXPIRED, Sessions

from ...integration.test_web import call, opened
from ..runtime.support import in_state
from .support import QUIET, Browser, served

pytestmark = pytest.mark.timeout(60)


@pytest.fixture
async def page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Sessions]:
    """The sessions page served on loopback, over the sessions under `tmp_path`, from `tmp_path`."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    server = Sessions(ManualClock(1_000_000.0))
    await server.listen("127.0.0.1")
    try:
        yield server
    finally:
        await server.stop()


async def test_only_the_sessions_link_opens_the_sessions_page_and_no_link_of_a_session_s_page_does(page, tmp_path):
    """Each server keeps its own credentials, so neither's link or token opens the other's, and the sessions page makes
    no link and answers no route of a session's page."""
    async with Session.start(QUIET, name="s", root=tmp_path) as owner, served(owner, tmp_path) as web:
        theirs = await Browser(web).opened("control")
        ours = Browser(page)

        their_link = await ours.exchange(web.link("control"))
        their_token = await ours.request("POST", "/x/sessions", {}, token=theirs.token)
        await ours.opened()
        listed = await ours.request("POST", "/x/sessions", {})
        our_token = await theirs.request("POST", "/v1/view_info", {}, token=ours.token)
        routes = {route: (await ours.request("POST", route, {})).status for route in ("/x/link", "/v1/view_info")}
        link = page.link()
        await Browser(page).exchange(link)
        spent = await Browser(page).exchange(link)

    assert (their_link.status, their_token.status, our_token.status) == (401, 401, 401)
    assert their_token.json()["error"] == EXPIRED
    assert listed.status == 200 and [row["name"] for row in listed.json()["rows"]] == ["s"]
    assert routes == {"/x/link": 404, "/v1/view_info": 404}
    assert spent.status == 401


async def test_the_sessions_page_is_served_under_a_policy_that_lets_only_its_own_script_run(page):
    reply = await Browser(page).request("GET", "/")
    policy = reply.headers["content-security-policy"]
    scripts = re.findall(rb"<script>(.*?)</script>", reply.body, re.S)
    digest = base64.b64encode(hashlib.sha256(scripts[0]).digest()).decode()

    assert reply.status == 200 and reply.headers["cache-control"] == "no-store"
    assert len(scripts) == 1 and f"script-src 'sha256-{digest}';" in policy
    assert "default-src 'none'" in policy and "connect-src 'self'" in policy and "form-action 'none'" in policy


async def test_the_sessions_page_lists_every_session_whether_a_runtime_holds_it_and_its_state(page, tmp_path):
    """As the terminal's sessions screen does: a session whose journal cannot be read is listed, its state unknown,
    saying why."""
    async with Session.start(QUIET, name="before", root=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
    sessions = tmp_path / "sessions"
    (sessions / "unopened").mkdir()
    (sessions / "unopened" / "manifest.json").write_bytes((sessions / "before" / "manifest.json").read_bytes())
    ours = await Browser(page).opened()

    async with Session.start(QUIET, name="now", root=tmp_path) as owner:
        listed = (await ours.request("POST", "/x/sessions", {})).json()

    rows = {row["name"]: row for row in listed["rows"]}
    assert listed["root"] == str(tmp_path) and listed["here"] == str(tmp_path) and listed["project"] is None
    assert rows["before"] == {"name": "before", "live": False, "state": "stopped"}
    assert rows["now"] == {"name": "now", "live": True, "state": "open"}
    assert rows["unopened"]["live"] is False
    assert rows["unopened"]["state"].startswith("unknown: refused unavailable: session unopened never opened")


async def test_opening_a_session_serves_it_on_a_port_of_its_own_and_answers_a_control_link_of_it(page, tmp_path):
    """Opened again, the one server makes another link. A session no runtime holds opens as its history, and one that
    is not there is refused, saying why."""
    async with Session.start(QUIET, name="before", root=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
    ours = await Browser(page).opened()

    async with Session.start(QUIET, name="s", root=tmp_path) as owner:
        first = (await ours.request("POST", "/x/open", {"name": "s"})).json()["link"]
        again = (await ours.request("POST", "/x/open", {"name": "s"})).json()["link"]
        token = await asyncio.to_thread(opened, first)
        _, info = await asyncio.to_thread(call, again, "POST", "/v1/view_info", {}, token)
        second = await asyncio.to_thread(opened, again)
        history = (await ours.request("POST", "/x/open", {"name": "before"})).json()["link"]
        _, past = await asyncio.to_thread(
            call, history, "POST", "/v1/view_info", {}, await asyncio.to_thread(opened, history)
        )
        missing = (await ours.request("POST", "/x/open", {"name": "nobody"})).json()
        malformed = await ours.request("POST", "/x/open", {"name": 7})

    assert urlsplit(first).port == urlsplit(again).port != page.port and first != again
    assert urlsplit(first).path == "/view" and urlsplit(history).port not in (page.port, urlsplit(first).port)
    assert info["x"]["credential"] == "control" and info["x"]["session"] == "s" and info["x"]["live"] is True
    assert second and second != token
    assert past["x"]["live"] is False and "platoon-harness session resume before" in past["x"]["cannot"]
    assert missing == {"refused": f"refused not_found: no session nobody under {tmp_path}"}
    assert malformed.status == 400


async def test_opening_a_session_another_web_serves_is_refused_saying_where(page, tmp_path):
    ours = await Browser(page).opened()

    async with Session.start(QUIET, name="s", root=tmp_path) as owner:
        lock = hold(owner.folder, "s")
        try:
            os.write(lock, b", at 127.0.0.1:8484 in process 4242")
            refused = (await ours.request("POST", "/x/open", {"name": "s"})).json()
        finally:
            os.close(lock)
        then = (await ours.request("POST", "/x/open", {"name": "s"})).json()

    assert refused == {
        "refused": "web serves session s already, at 127.0.0.1:8484 in process 4242, and one serves a session at a "
        "time: your own page there makes new links, or stop that one first"
    }
    assert "link" in then
