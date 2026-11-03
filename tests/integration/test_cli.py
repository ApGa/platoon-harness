"""The headless command line, as a terminal and CI meet it: the installed `platoon-harness`, run as processes of its own
against scripted harnesses on the real tool plane."""

import asyncio
import fcntl
import json
import os
import signal
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness import Team
from platoon_harness.config import Manifest

from .cli import Cli, checked, crew, finished, line_where, said, solo

pytestmark = pytest.mark.timeout(120)


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    made = Cli(tmp_path)
    yield made
    await asyncio.to_thread(made.end)


def journal(cli: Cli, session: str) -> Path:
    return cli.folder / "home" / "sessions" / session / "journal.sqlite"


def types_of(events: list[dict]) -> list[str]:
    return [event["type"] for event in events]


# Exit codes, one per way a session ends.


async def test_a_run_that_settles_exits_0_and_prints_the_journal_then_its_ending(cli: Cli):
    team = cli.write("crew.toml", crew())

    done = await cli.run("run", "Fix the flaky test", "--team", team, "--trust", "--name", "s1", "--json")

    events = checked(done)
    assert done.code == 0, done.stderr
    assert done.lines()[-1]["reason"] == "settled"
    assert "session s1" in done.stderr and "platoon-harness events s1 --follow" in done.stderr
    sent = [event for event in events if event["type"] == "message.sent" and event["actor"] == "human:you"]
    assert [event["gist"] for event in sent] == ["Fix the flaky test"]
    assert types_of(events)[-1] == "session.stopped"


@pytest.mark.parametrize(
    ("harness", "args", "reason", "code"),
    [
        ("exiting", (), "agent_failed", 1),
        ("saying", ("--set", "budget.turns = 1"), "budget_exhausted", 2),
        ("listening", ("--timeout", "1s"), "timed_out", 3),
        ("asking", (), "needs_human", 4),
    ],
)
async def test_each_way_a_run_ends_has_its_exit_code(
    cli: Cli, harness: str, args: tuple[str, ...], reason: str, code: int
):
    team = cli.write("solo.toml", solo(harness))

    done = await cli.run("run", "go", "--team", team, "--trust", "--json", *args)

    checked(done)
    assert (done.lines()[-1]["reason"], done.code) == (reason, code), done.stderr


async def test_a_session_cancelled_from_another_process_ends_its_run_with_130(cli: Cli):
    team = cli.write("solo.toml", solo("listening"))
    run = await cli.start("run", "go", "--team", team, "--trust", "--name", "s", "--json")
    seen: list[dict] = []
    await line_where(run, seen, "type", "agent.parked")

    cancelled = await cli.run("session", "cancel", "s")
    done = await finished(run)

    assert cancelled.code == 0, cancelled.stderr
    assert (done.code, done.lines()[-1]["reason"]) == (130, "cancelled")
    assert "session.cancelled" in types_of(seen + done.lines())


async def test_ctrl_c_runs_the_owner_s_shutdown_and_exits_130(cli: Cli):
    team = cli.write("crew.toml", crew(worker="hanging"))
    run = await cli.start("run", "go", "--team", team, "--trust", "--name", "s", "--json")
    seen: list[dict] = []
    await line_where(run, seen, "type", "task.claimed")

    os.killpg(run.pid, signal.SIGINT)
    done = await finished(run)

    events = [*seen, *done.lines()[:-1]]
    ending = done.lines()[-1]
    assert (done.code, ending["reason"], ending["state"]) == (130, "cancelled", "stopped"), done.stderr
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert types_of(events)[-1] == "session.stopped"
    assert "stopped by its owner" in [event["data"]["reason"] for event in events if event["type"] == "turn.ended"]
    listed = await cli.run("session", "list", "--json")
    assert json.loads(listed.stdout) == [{"name": "s", "live": False, "state": "stopped"}]
    assert list((cli.folder / "home" / "sessions" / "s").rglob("proc.json")) == []


async def test_a_reader_of_stdout_that_falls_behind_holds_up_nothing(cli: Cli):
    """A run prints its events as a guest of its own runtime, so its session goes on while nobody reads them, here
    through a pipe of one page, and every line is there once someone does."""
    team = cli.write("solo.toml", solo("listening"))
    reading, writing = os.pipe()
    fcntl.fcntl(writing, fcntl.F_SETPIPE_SZ, 4096)
    run = await cli.start("run", "wait for me", "--team", team, "--trust", "--name", "s", "--json", stdout=writing)
    os.close(writing)
    await said(run, "session s")

    sent = await cli.run("message", "send", "s", "--to", "@bob", "--gist", "here you are")
    with os.fdopen(reading, "rb") as pipe:
        printed = await asyncio.to_thread(pipe.read)
    code = await asyncio.wait_for(run.wait(), 60)

    assert (sent.code, code) == (0, 0), sent.stderr
    lines = [json.loads(line) for line in printed.splitlines()]
    assert lines[-1]["reason"] == "settled" and len(printed) > 4096


# The prompt.


async def test_a_prompt_on_stdin_reaches_the_agent(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))

    done = await cli.run("run", "--team", team, "--trust", "--json", input=b"Fix it, from stdin\n")

    events = checked(done)
    assert done.code == 0, done.stderr
    sent = next(event for event in events if event["type"] == "message.sent")
    assert (sent["stream"], sent["gist"]) == ("inbox/bob", "Fix it, from stdin")
    assert any(event["type"] == "context.delivered" and event["agent"] == "bob" for event in events)


async def test_a_long_prompt_from_a_file_goes_whole_as_the_body(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))
    prompt = cli.write("task.md", "Fix the flaky test. " * 40)

    done = await cli.run("run", "--team", team, "--trust", "--json", "--prompt-file", prompt, "--name", "s")

    events = checked(done)
    sent = next(event for event in events if event["type"] == "message.sent")
    body = await cli.run("blob", "get", "s", "--ref", sent["data"]["body"])
    assert len(sent["gist"]) == 280 and sent["gist"].endswith("…")
    assert json.loads(body.stdout)["text"] == ("Fix the flaky test. " * 40).strip()


async def test_the_prompt_goes_to_the_agent_named_when_a_session_starts_several(cli: Cli):
    team = cli.write("pair.toml", solo("saying", count="2"))

    unnamed = await cli.run("run", "go", "--team", team, "--trust")
    named = await cli.run("run", "go", "--team", team, "--trust", "--to", "@bob-2", "--json")

    assert unnamed.code == 64 and "@bob-1, @bob-2" in unnamed.stderr
    sent = next(event for event in checked(named) if event["type"] == "message.sent")
    assert sent["stream"] == "inbox/bob-2"


# Other processes.


async def test_a_person_s_message_from_a_second_process_reaches_an_agent_mid_run(cli: Cli):
    team = cli.write("solo.toml", solo("listening"))
    run = await cli.start("run", "wait for me", "--team", team, "--trust", "--name", "s", "--json")
    seen: list[dict] = []
    await line_where(run, seen, "type", "agent.parked")

    sent = await cli.run("message", "send", "s", "--to", "@bob", "--gist", "here you are")
    done = await finished(run)

    assert sent.code == 0, sent.stderr
    ref = json.loads(sent.stdout)["ref"]
    events = [*seen, *done.lines()[:-1]]
    assert done.code == 0, done.stderr
    offered = [event for event in events if event["type"] == "context.offered" and event["agent"] == "bob"]
    assert any(item["ref"] == ref for event in offered for item in event["data"]["items"])
    assert done.lines()[-1]["agents"][0]["report"]["gist"] == "heard you"


async def test_an_approval_is_answered_from_a_second_process_once(cli: Cli):
    team = cli.write("solo.toml", solo("asking"))
    serving = await cli.start("serve", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    watching = await cli.start("events", "s", "--follow", "--json")
    asked = await cli.run("message", "send", "s", "--to", "@bob", "--gist", "ship it?")
    await line_where(watching, [], "type", "approval.requested")
    rows = json.loads((await cli.run("attention", "list", "s")).stdout)
    action = next(action for action in rows[0]["actions"] if action["label"] == "Allow")
    args = action["args"]
    resolve = ("approval", "resolve", "s", "--id", args["id"], "--verdict", "allow")

    first = await cli.run(*resolve, "--expected-version", str(args["expected_version"]))
    second = await cli.run(*resolve, "--expected-version", str(args["expected_version"]))
    stopped = await cli.run("session", "stop", "s")
    served = await finished(serving)

    assert asked.code == 0 and first.code == 0, first.stderr
    assert second.code == 1 and "refused conflict" in second.stderr
    assert stopped.code == 0 and served.code == 0, served.stderr
    resolved = (
        sqlite3.connect(journal(cli, "s"))
        .execute("SELECT actor FROM events WHERE type = 'approval.resolved'")
        .fetchall()
    )
    assert resolved == [("human:you",)]


async def test_interrupting_retiring_and_cancelling_from_a_second_process(cli: Cli):
    """An agent interrupted stays, and is retired once it has stopped. The lead's wait on both workers then holds, and
    the run settles."""
    team = cli.write("crew.toml", crew(worker="hanging"))
    run = await cli.start("run", "go", "--team", team, "--trust", "--name", "s", "--json")
    seen: list[dict] = []
    while sum(event["type"] == "task.claimed" for event in seen) < 2:
        await line_where(run, seen, "type", "task.claimed")

    interrupted = await cli.run("agent", "interrupt", "s", "--agent", "@w1")
    while not (seen[-1]["type"] == "turn.ended" and seen[-1]["agent"] == "w1"):
        await line_where(run, seen, "type", "turn.ended")
    retired = await cli.run("agent", "retire", "s", "--agent", "@w1")
    cancelled = await cli.run("agent", "cancel", "s", "--agent", "@w2")
    done = await finished(run)

    assert [interrupted.code, retired.code, cancelled.code, done.code] == [0, 0, 0, 0], done.stderr
    events = [*seen, *done.lines()[:-1]]
    statuses = {event["agent"]: event["data"]["status"] for event in events if event["type"] == "agent.ended"}
    assert statuses == {"w1": "retired", "w2": "cancelled", "lead": "finished"}
    assert seen[-1]["data"]["reason"] == "interrupted"


async def test_a_board_post_with_a_file_from_a_second_process(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))
    serving = await cli.start("serve", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    spec = cli.write("spec.md", "# The spec\n\nKeep the public API stable.\n")

    board = await cli.run("channel", "create", "s", "--name", "notes", "--kind", "board", "--readers", "all")
    posted = await cli.run(
        "board", "post", "s", "--board", "notes", "--name", "spec", "--gist", "The spec", "--body-file", spec
    )
    got = await cli.run("board", "get", "s", "--board", "notes", "--name", "spec")
    await cli.run("session", "stop", "s")

    assert (board.code, posted.code, got.code) == (0, 0, 0), posted.stderr
    assert json.loads(got.stdout)["text"] == "# The spec\n\nKeep the public API stable.\n"
    assert (await finished(serving)).code == 0


async def test_a_command_run_again_under_its_key_is_one_operation(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))
    serving = await cli.start("serve", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    send = ("message", "send", "s", "--to", "@bob", "--gist", "once", "--key", "retry-1")

    first = await cli.run(*send)
    again = await cli.run(*send)
    await cli.run("session", "stop", "s")
    await finished(serving)

    assert (first.code, again.code) == (0, 0), again.stderr
    assert json.loads(first.stdout) == json.loads(again.stdout)
    sent = sqlite3.connect(journal(cli, "s")).execute("SELECT count(*) FROM events WHERE type = 'message.sent'")
    assert sent.fetchone() == (1,)


async def test_approvals_answered_by_a_flag_are_kept_in_the_manifest(cli: Cli):
    team = cli.write("solo.toml", solo("asking"))

    done = await cli.run("run", "go", "--team", team, "--trust", "--approvals", "allow", "--name", "s", "--json")

    assert done.code == 0, done.stderr
    manifest = Manifest.model_validate_json((cli.folder / "home" / "sessions" / "s" / "manifest.json").read_text())
    assert manifest.approvals == "allow"
    assert any(event["type"] == "approval.resolved" for event in checked(done))


# Following a session.


async def test_events_follow_resumes_from_its_cursor_across_a_stop_and_a_resume(cli: Cli):
    team = cli.write("crew.toml", crew(worker="hanging"))
    run = await cli.start("run", "go", "--team", team, "--trust", "--name", "s", "--json")
    await line_where(run, [], "type", "task.claimed")
    following = await cli.start("events", "s", "--follow", "--json")
    await line_where(following, [], "type", "task.claimed")

    stopped = await cli.run("session", "stop", "s")
    before = (await finished(following)).lines()
    ran = await finished(run)
    resumed = await cli.run("session", "resume", "s", "--json")
    after = (await cli.run("events", "s", "--after", str(before[-1]["seq"]), "--json")).lines()

    assert (stopped.code, ran.code, resumed.code) == (0, 130, 0), resumed.stderr
    assert types_of(before)[-1] == "session.stopped"
    seqs = [event["seq"] for event in after]
    assert seqs == list(range(before[-1]["seq"] + 1, before[-1]["seq"] + 1 + len(seqs)))
    assert [event["seq"] for event in checked(resumed, first=seqs[0])] == seqs
    assert types_of(after)[0] == "runtime.started" and resumed.lines()[-1]["reason"] == "settled"


async def test_events_on_a_closed_session_reads_history_and_writes_nothing(cli: Cli):
    team = cli.write("crew.toml", crew())
    await cli.run("run", "go", "--team", team, "--trust", "--name", "s")
    path = journal(cli, "s")
    before = path.read_bytes(), path.stat().st_mtime_ns

    read = await cli.run("events", "s", "--json")
    shown = await cli.run("session", "show", "s")
    tasks = await cli.run("task", "list", "s", "--queue", "tasks")
    written = await cli.run("message", "send", "s", "--to", "@lead", "--gist", "too late")

    assert (read.code, shown.code, tasks.code) == (0, 0, 0)
    assert read.lines()[-1]["type"] == "session.stopped"
    assert json.loads(tasks.stdout)["total"] == 2
    assert written.code == 1 and "platoon-harness session resume s" in written.stderr
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


# Nothing waits on a person who is not there.


@pytest.mark.parametrize(
    ("args", "code"),
    [
        (("run",), 64),
        (("run", "-"), 64),
        (("run", "go", "--team", "nowhere.toml"), 78),
        (("init",), 1),
        (("session", "resume", "nowhere"), 1),
        (("session", "stop", "nowhere"), 1),
        (("team", "check"), 78),
        (("attach", "s"), 64),
    ],
)
async def test_no_command_prompts_with_no_terminal(cli: Cli, args: tuple[str, ...], code: int):
    cli.write("platoon-harness.toml", "this is no team")

    done = await cli.run(*args)

    assert done.code == code, done.stderr
    assert done.stdout == ""


async def test_several_agents_on_a_plan_login_exit_78_naming_the_fix_unless_said(cli: Cli):
    team = cli.write("pair.toml", solo("planned", count="2"))

    refused = await cli.run("run", "go", "--team", team, "--trust", "--to", "@bob-1")
    said = await cli.run("run", "go", "--team", team, "--trust", "--to", "@bob-1", "--plan-login")

    assert refused.code == 78 and "--plan-login" in refused.stderr
    assert said.code == 0, said.stderr


async def test_a_bare_command_prints_help_and_usage_errors_exit_64(cli: Cli):
    bare = await cli.run()
    unknown = await cli.run("run", "go", "--no-such-flag")

    assert bare.code == 0 and "Usage: platoon-harness COMMAND" in bare.stdout
    assert unknown.code == 64 and unknown.stdout == ""


# A team, before any cost.


async def test_team_check_says_every_problem_at_once_and_exits_78(cli: Cli):
    bad = cli.write("bad.toml", '[roles.lead]\nharness = "nobody"\nmay_spawn = ["lead"]\n')

    done = await cli.run("team", "check", bad)

    assert done.code == 78
    assert "error: roles.lead.harness: no driver `nobody`" in done.stdout
    assert "recursive may_spawn with no limit" in done.stdout


async def test_team_show_resolved_loads_back_to_the_same_team(cli: Cli):
    team = cli.write("crew.toml", crew())

    plain = await cli.run("team", "show", team, "--trust")
    resolved = await cli.run("team", "show", team, "--trust", "--resolved")
    again = await cli.run("team", "show", cli.write("again.toml", resolved.stdout), "--trust", "--resolved")

    assert plain.code == 0 and "Closes when lead finishes." in plain.stdout
    assert resolved.stdout == again.stdout
    assert Team.loads(resolved.stdout).topology.until == "role:lead"


async def test_team_told_says_what_each_role_would_be_told(cli: Cli):
    team = cli.write("crew.toml", crew())

    done = await cli.run("team", "told", team, "--trust")

    assert done.code == 0, done.stderr
    assert done.stdout.startswith("# lead\n\nYou are @lead.")
    assert "# worker\n\nYou are @worker." in done.stdout


# This machine.


def fake_harnesses(cli: Cli, *names: str) -> None:
    """Harnesses on PATH that say a version and no login, and nothing else on it but the system's own."""
    folder = cli.folder / "bin"
    folder.mkdir()
    for name in names:
        (folder / name).write_text('#!/bin/sh\n[ "$1" = --version ] && echo "9.9.9 (fake)"\nexit 0\n')
        (folder / name).chmod(0o755)
    cli.env["PATH"] = f"{folder}:/usr/bin:/bin"


async def test_init_writes_a_starter_from_the_harnesses_found_and_never_overwrites(cli: Cli):
    fake_harnesses(cli, "claude", "codex")

    first = await cli.run("init")
    written = (cli.folder / "platoon-harness.toml").read_text()
    second = await cli.run("init")
    checked = await cli.run("team", "check")

    assert first.code == 0 and "a lead on claude, which starts workers on codex" in first.stderr
    assert Team.loads(written).roles["worker"].harness == "codex"
    assert second.code == 1 and (cli.folder / "platoon-harness.toml").read_text() == written
    assert checked.code == 0, checked.stdout


async def test_init_with_no_harness_on_path_exits_78_naming_them(cli: Cli):
    fake_harnesses(cli)

    done = await cli.run("init")

    assert done.code == 78 and "claude, codex, pi" in done.stderr
    assert not (cli.folder / "platoon-harness.toml").exists()


async def test_doctor_says_each_harness_its_version_and_login_kind_and_whether_it_is_usable(cli: Cli):
    fake_harnesses(cli, "claude", "codex")

    done = await cli.run("doctor", "--json")
    report = json.loads(done.stdout)

    assert done.code == 0 and report["usable"]
    found = {harness["name"]: harness for harness in report["harnesses"]}
    assert found["claude"] == {"name": "claude", "found": True, "version": "9.9.9 (fake)", "login": None}
    assert found["pi"] == {"name": "pi", "found": False}
    assert report["root"]["path"] == cli.env["PLATOON_HARNESS_HOME"]
    assert {component["name"] for component in report["installed"]["components"]} >= {"claude", "codex", "pi"}


async def test_doctor_with_no_harness_on_path_exits_78(cli: Cli):
    fake_harnesses(cli)

    done = await cli.run("doctor")

    assert done.code == 78 and "problem    no harness is on PATH" in done.stdout


async def test_extension_list_reads_what_is_installed_from_metadata(cli: Cli):
    done = await cli.run("extension", "list", "--json")

    listed = json.loads(done.stdout)
    assert done.code == 0
    assert {"kind": "driver", "name": "claude", "distribution": "platoon-harness-sdk"} in [
        {key: component[key] for key in ("kind", "name", "distribution")} for component in listed["components"]
    ]
    assert listed["problems"] == []
