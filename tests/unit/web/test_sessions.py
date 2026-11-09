"""The sessions page's server, which `web` with no session serves: its one link and its own credentials, the list,
opening a session on a port of its own, starting, resuming and stopping one, each asking first what only the person may
allow, and reading, checking and saving the project's team, over sessions the test owns or starts, on a real socket."""

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
from platoon_harness_cli import team_editor
from platoon_harness_cli.team_editor import SAVING, Harness
from platoon_harness_cli.web import hold
from platoon_harness_cli.web.sessions import EXPIRED, TRUST, Sessions

from ...integration.cli import solo
from ...integration.scripts import inside
from ...integration.test_web import call, opened
from ..runtime.support import in_state
from .support import QUIET, Browser, served

pytestmark = pytest.mark.timeout(60)

HARNESSES = (Harness("claude", "not on PATH", ()),)
"""What `doctor` finds of this machine's harnesses, as the team editor is told it."""


@pytest.fixture
async def page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Sessions]:
    """The sessions page served on loopback, over the sessions under `tmp_path`, from `tmp_path`, where a runtime it
    starts finds the scripted harnesses."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[3]))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(team_editor, "harnesses", lambda: HARNESSES)
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


async def test_the_sessions_page_refuses_a_foreign_host_and_a_post_from_another_origin_or_none_and_starts_nothing(
    page, tmp_path
):
    """It acts as you on every session here, so a rebinding name is refused 421, and a POST from another site, from
    another port of loopback, as a session's page is served on, from `null` or with no `Origin` is refused 403, each
    before its bearer is read: a start that holds its trust starts nothing, and an exchange spends no link."""
    (tmp_path / "solo.toml").write_text(solo("saying"))
    ours = await Browser(page).opened()
    start = {"team": "solo.toml", "name": "s"}
    start |= (await ours.request("POST", "/x/start", start)).json()["ask"]["answer"]
    save = {"base": None, "edits": [{"add": ["roles", "lead"], "to": "claude"}]}
    link = page.link()
    secret = link.partition("#link=")[2]
    rebound = f"rebound.localhost:{page.port}"
    foreign = [{"Host": rebound, "Origin": f"http://{rebound}"}, {"Host": f"127.0.0.1:{page.port % 65535 + 1}"}]
    origins = [
        "http://evil.example",
        f"http://127.0.0.1:{page.port % 65535 + 1}",
        f"https://127.0.0.1:{page.port}",
        "null",
        None,
    ]

    hosts, posts = [], []
    for route, body, token in (
        ("/x/exchange", {}, secret),
        ("/x/start", start, ours.token),
        ("/x/save", save, ours.token),
    ):
        for headers in foreign:
            hosts.append((await ours.request("POST", route, body, token=token, headers=headers)).status)
        for origin in origins:
            posts.append((await ours.request("POST", route, body, token=token, headers={"Origin": origin})).status)
    hosts.append((await ours.request("GET", "/", headers={"Host": rebound})).status)
    spent = await Browser(page).exchange(link)

    assert hosts == [421] * 7 and posts == [403] * 15
    assert spent.status == 200 and not (tmp_path / "sessions" / "s").exists()
    assert not (tmp_path / "platoon-harness.toml").exists()


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


def edit(where: str, text: str) -> dict:
    return {"set": where.split("."), "to": text}


def field(answer: dict, where: str) -> dict:
    """A field of the team editor's answer, by its place."""
    found = (field for section in answer["sections"] for group in section["groups"] for field in group["fields"])
    return next(field for field in found if field["where"] == where)


async def test_the_team_editor_reads_checks_and_saves_the_project_s_team_and_a_start_runs_what_it_saved(page, tmp_path):
    """The read gives each field as the file has it, a check of edits gives the diff a save makes, problems at their
    fields and `team show`'s sentences, the save writes the file, keeping its comments, and a start from the project's
    team runs what was saved, which the session's manifest keeps."""
    project = tmp_path / "platoon-harness.toml"
    project.write_text(f"# Bob, alone.\n{solo('saying')}")
    ours = await Browser(page).opened()

    read = (await ours.request("POST", "/x/team", {})).json()
    edits = [edit("roles.bob.model", "m1"), edit("roles.bob.count", "two")]
    wrong = (await ours.request("POST", "/x/check", {"edits": edits})).json()
    edits[1] = edit("roles.bob.approvals", "allow")
    checked = (await ours.request("POST", "/x/check", {"edits": edits})).json()
    saved = (await ours.request("POST", "/x/save", {"base": checked["base"], "edits": edits})).json()
    given = {"team": "", "name": "s"}
    given |= (await ours.request("POST", "/x/start", given)).json()["ask"]["answer"]
    started = (await ours.request("POST", "/x/start", given)).json()
    manifest = Manifest.model_validate_json((tmp_path / "sessions" / "s" / "manifest.json").read_bytes())
    malformed = await ours.request("POST", "/x/check", {"edits": [{"set": "roles.bob.model"}]})
    await ours.request("POST", "/x/stop", {"name": "s"})

    assert (read["file"], read["here"], read["diff"], read["unmade"]) == ("platoon-harness.toml", str(tmp_path), "", [])
    assert read["base"] == hashlib.sha256(f"# Bob, alone.\n{solo('saying')}".encode()).hexdigest()
    assert field(read, "roles.bob.harness")["choices"][0] == {
        "value": "tests.integration.scripts:saying",
        "said": "tests.integration.scripts:saying, as the file has it",
    }
    assert field(wrong, "roles.bob.count")["problems"] == [
        {"level": "error", "said": "error: roles.bob.count: is a whole number"}
    ]
    assert wrong["blocked"] == "Fix each change marked first: the editor could not make it." and wrong["unmade"] == [1]
    assert '+model = "m1"' in checked["diff"] and checked["blocked"] is None and checked["shown"]
    assert saved == {"said": f"Saved platoon-harness.toml in {tmp_path}."}
    assert project.read_text() == f'# Bob, alone.\n{solo("saying")}model = "m1"\napprovals = "allow"\n'
    assert "link" in started
    assert Team.loads(manifest.team).roles["bob"].model == "m1"
    assert malformed.status == 400


async def test_a_save_of_a_file_changed_since_it_was_read_is_refused_and_one_that_writes_a_test_command_asks_once(
    page, tmp_path
):
    """Nothing is written over a file that changed since the check the person saw, and the next check shows the edits
    on what it holds now. A save that writes what would run as you asks once, naming it, and the answer covers it."""
    project = tmp_path / "platoon-harness.toml"
    project.write_text(solo("saying"))
    ours = await Browser(page).opened()
    edits = [edit("test.command", "make test"), edit("test.timeout", "5m")]

    checked = (await ours.request("POST", "/x/check", {"edits": edits})).json()
    project.write_text(solo("listening"))
    refused = (await ours.request("POST", "/x/save", {"base": checked["base"], "edits": edits})).json()
    untouched = project.read_text()
    again = (await ours.request("POST", "/x/check", {"edits": edits})).json()
    asked = (await ours.request("POST", "/x/save", {"base": again["base"], "edits": edits})).json()
    saved = (
        await ours.request("POST", "/x/save", {"base": again["base"], "edits": edits, **asked["ask"]["answer"]})
    ).json()

    assert refused["refused"].startswith("platoon-harness.toml: changed since it was read, so nothing was saved")
    assert untouched == solo("listening") and again["base"] != checked["base"]
    assert field(again, "roles.bob.harness")["text"] == "tests.integration.scripts:listening"
    assert asked["ask"]["question"] == f'{SAVING}\ntest.command = ["make", "test"]\nSave it, as shown here?'
    assert asked["ask"]["yes"] == "Save it"
    assert saved == {"said": f"Saved platoon-harness.toml in {tmp_path}."}
    assert project.read_text() == f'{solo("listening")}\n[test]\ncommand = ["make", "test"]\ntimeout = "5m"\n'
