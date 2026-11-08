"""The sessions page's server, which `web` with no session serves: its one link and its own credentials, the list,
opening a session on a port of its own, and starting, resuming and stopping one, each asking first what only the
person may allow, over sessions the test owns or starts, on a real socket."""

import asyncio
import base64
import hashlib
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from platoon_harness import Session, Team, config
from platoon_harness.config import Manifest
from platoon_harness.kernel import ManualClock, is_held
from platoon_harness.runtime.paths import read_running
from platoon_harness_cli.web import hold
from platoon_harness_cli.web.sessions import EXPIRED, TRUST, Sessions

from ...integration.cli import solo
from ...integration.scripts import inside
from ...integration.test_web import call, opened
from ..runtime.support import in_state
from .support import QUIET, Browser, served

pytestmark = pytest.mark.timeout(60)


@pytest.fixture
async def page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Sessions]:
    """The sessions page served on loopback, over the sessions under `tmp_path`, from `tmp_path`, where a runtime it
    starts finds the scripted harnesses."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[3]))
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


def asked(names: str) -> str:
    """What a start asks of a team whose files name `names`, each a value that needs trust, as the team holds it."""
    return f"{TRUST}\n{names}\nTrust it, as shown here, and start?"


async def test_a_team_that_names_what_runs_as_you_is_asked_about_once_naming_it_before_anything_runs(page, tmp_path):
    """Nothing starts until the start comes again with the digest of what was shown. Then the session runs on a runtime
    of its own, which outlives `web`, and opens on a control link of its own page. A team that cannot load even trusted
    is refused with its problems, and a name that is taken as `run` refuses it."""
    (tmp_path / "solo.toml").write_text(solo("saying"))
    ours = await Browser(page).opened()

    first = (await ours.request("POST", "/x/start", {"team": "solo.toml", "name": "s"})).json()
    nothing = (tmp_path / "sessions" / "s").exists()
    given = {"team": "solo.toml", "name": "s", **first["ask"]["answer"]}
    started = (await ours.request("POST", "/x/start", given)).json()
    running = read_running(tmp_path / "sessions" / "s")
    token = await asyncio.to_thread(opened, started["link"])
    _, info = await asyncio.to_thread(call, started["link"], "POST", "/v1/view_info", {}, token)
    taken = (await ours.request("POST", "/x/start", given)).json()
    missing = (await ours.request("POST", "/x/start", {"team": "nowhere.toml", "name": ""})).json()
    malformed = await ours.request("POST", "/x/start", {"team": "solo.toml", "name": "s", "plan_login": "yes"})
    await ours.request("POST", "/x/stop", {"name": "s"})

    assert first == {
        "ask": {
            "question": asked('roles.bob.harness = "tests.integration.scripts:saying"'),
            "yes": "Trust and start",
            "answer": {"trust": first["ask"]["answer"]["trust"]},
        }
    }
    assert not nothing and running is not None and running.pid != os.getpid()
    assert (info["x"]["session"], info["x"]["live"], info["x"]["credential"]) == ("s", True, "control")
    assert taken == {"refused": "refused conflict: session s exists: resume it, or choose another name"}
    assert missing == {"refused": "nowhere.toml: no such file\nroles: Field required"}
    assert malformed.status == 400


async def test_trust_covers_what_was_shown_and_a_team_changed_since_is_asked_about_again(page, tmp_path):
    team = tmp_path / "solo.toml"
    team.write_text(solo("saying"))
    ours = await Browser(page).opened()

    shown = (await ours.request("POST", "/x/start", {"team": "solo.toml", "name": "s"})).json()["ask"]
    team.write_text(solo("listening"))
    again = (await ours.request("POST", "/x/start", {"team": "solo.toml", "name": "s", **shown["answer"]})).json()

    assert again["ask"]["question"] == asked('roles.bob.harness = "tests.integration.scripts:listening"')
    assert again["ask"]["answer"] != shown["answer"] and not (tmp_path / "sessions" / "s").exists()


async def test_what_a_start_asks_to_trust_and_the_team_it_would_run_come_from_one_read_of_its_files(
    page, tmp_path, monkeypatch
):
    """A file rewritten as it is read cannot leave out of the question what the team would run: what needs trust is
    found in the very read that gives the team, so a team that names code to run is asked about even when the file
    names none by the time it is read again, and nothing starts."""
    team = tmp_path / "solo.toml"
    team.write_text(solo("saying"))
    read = config._file

    def rewritten(path: Path, problems: list, *, required: bool = False) -> dict:
        found = read(path, problems, required=required)
        if path == Path("solo.toml"):
            path.write_text('[roles.bob]\nharness = "claude"\n')
        return found

    monkeypatch.setattr(config, "_file", rewritten)
    ours = await Browser(page).opened()

    answer = (await ours.request("POST", "/x/start", {"team": "solo.toml", "name": "s"})).json()

    assert answer["ask"]["question"] == asked('roles.bob.harness = "tests.integration.scripts:saying"')
    assert 'harness = "claude"' in team.read_text() and not (tmp_path / "sessions" / "s").exists()


async def test_several_agents_on_a_plan_login_are_asked_about_once_and_the_answer_is_plan_login(page, tmp_path):
    """After trust, as the terminal's sessions screen asks it, before any harness launches."""
    (tmp_path / "planned.toml").write_text(solo("planned", count="2"))
    ours = await Browser(page).opened()
    given = {"team": "planned.toml", "name": "s"}

    trusting = (await ours.request("POST", "/x/start", given)).json()["ask"]
    given |= trusting["answer"]
    planning = (await ours.request("POST", "/x/start", given)).json()["ask"]
    nothing = (tmp_path / "sessions" / "s").exists()
    started = (await ours.request("POST", "/x/start", given | planning["answer"])).json()
    manifest = Manifest.model_validate_json((tmp_path / "sessions" / "s" / "manifest.json").read_bytes())
    await ours.request("POST", "/x/stop", {"name": "s"})

    assert planning == {
        "question": "bob would run several agents headless on one plan login. Is this your own work?",
        "yes": "It is my own work",
        "answer": {"plan_login": True},
    }
    assert not nothing and "link" in started and manifest.plan_login is True


async def test_resuming_a_session_a_runtime_holds_is_refused_naming_open(page, tmp_path):
    """A session no runtime holds resumes on a runtime of its own and opens on its own control link."""
    saying = Team.model_validate({"roles": {"lead": {"harness": inside("saying")}}})
    guest = await Session.start(saying, name="s", root=tmp_path, detach=True)
    await in_state(guest, "lead", "idle")
    await guest.leave()
    ours = await Browser(page).opened()

    live = (await ours.request("POST", "/x/resume", {"name": "s"})).json()
    await ours.request("POST", "/x/stop", {"name": "s"})
    resumed = (await ours.request("POST", "/x/resume", {"name": "s"})).json()
    held = is_held(tmp_path / "sessions" / "s")
    missing = (await ours.request("POST", "/x/resume", {"name": "nobody"})).json()
    await ours.request("POST", "/x/stop", {"name": "s"})

    assert live == {"refused": "A runtime holds s already: Open opens it."}
    assert "link" in resumed and held
    assert missing == {"refused": f"refused not_found: no session nobody under {tmp_path}"}


async def test_a_stop_answers_once_the_runtime_has_let_go(page, tmp_path):
    """As `session stop` does, as the owner, leaving the session resumable. A session no runtime holds is refused."""
    saying = Team.model_validate({"roles": {"lead": {"harness": inside("saying")}}})
    guest = await Session.start(saying, name="s", root=tmp_path, detach=True)
    await in_state(guest, "lead", "idle")
    await guest.leave()
    ours = await Browser(page).opened()

    stopped = (await ours.request("POST", "/x/stop", {"name": "s"})).json()
    held = is_held(tmp_path / "sessions" / "s")
    again = (await ours.request("POST", "/x/stop", {"name": "s"})).json()
    listed = (await ours.request("POST", "/x/sessions", {})).json()["rows"]

    assert stopped == {"said": "Stopped s. Resume restarts it, which can spend money."} and not held
    assert again == {"refused": "refused conflict: no runtime holds session s: it has stopped"}
    assert listed == [{"name": "s", "live": False, "state": "stopped"}]
