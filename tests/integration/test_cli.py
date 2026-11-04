"""The headless command line, as a terminal and CI meet it: the installed `platoon-harness`, run as processes of its own
against scripted harnesses on the real tool plane."""

import asyncio
import fcntl
import json
import os
import re
import signal
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness import Team
from platoon_harness.config import Manifest

from .cli import EXECUTABLE, SECONDS, Cli, checked, crew, finished, line_where, said, solo

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
    assert (done.lines()[-1]["reason"], done.lines()[-1]["state"]) == ("settled", "closed")
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


async def test_a_failed_commit_ends_a_run_with_74_naming_the_journal_and_a_resume_goes_on(cli: Cli):
    team = cli.write("solo.toml", solo("breaking"))

    done = await cli.run("run", "go", "--team", team, "--trust", "--name", "s", "--json")

    assert done.code == 74, done.stderr
    assert "journal.sqlite: a commit failed, so nothing more is recorded: disk I/O error" in done.stderr
    assert "ending" not in [line.get("type") for line in done.lines()]
    assert "session.stopped" not in types_of(done.lines())
    resumed = await cli.run("session", "resume", "s", "--json")
    lines = resumed.lines()
    assert (resumed.code, lines[-1]["reason"]) == (0, "settled"), resumed.stderr
    told = [line["gist"] for line in lines if line.get("type") == "message.sent"]
    assert told[0].startswith("Your last turn was cut off by a crash")


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


async def test_a_signal_during_the_owner_s_shutdown_lets_it_finish(cli: Cli):
    """A second Ctrl+C, or `session stop`'s SIGTERM, comes while the shutdown waits out its grace for a harness that
    does not hear the interrupt."""
    team = cli.write("solo.toml", solo("deaf"))
    run = await cli.start("run", "go", "--team", team, "--trust", "--name", "s", "--json")
    seen: list[dict] = []
    await line_where(run, seen, "type", "turn.started")

    os.killpg(run.pid, signal.SIGINT)
    await line_where(run, seen, "type", "wake.quieted")
    os.killpg(run.pid, signal.SIGTERM)
    done = await finished(run)

    assert (done.code, done.lines()[-1]["reason"]) == (130, "cancelled"), done.stderr
    assert types_of([*seen, *done.lines()[:-1]])[-1] == "session.stopped"


async def test_a_signal_while_a_resume_brings_its_harnesses_back_still_runs_the_owner_s_shutdown(cli: Cli):
    team = cli.write("solo.toml", solo("returning"))
    run = await cli.start("run", "go", "--team", team, "--trust", "--name", "s", "--json")
    await line_where(run, [], "type", "turn.started")
    await cli.run("session", "stop", "s")
    await finished(run)
    resuming = await cli.start("session", "resume", "s", "--json")
    await said(resuming, "bob is on its way back")

    os.killpg(resuming.pid, signal.SIGTERM)
    done = await finished(resuming)

    assert (done.code, done.lines(), done.lines()[-1]["type"]) == (130, done.lines()[-1:], "ending"), done.stderr
    assert done.lines()[-1]["reason"] == "cancelled"
    last = sqlite3.connect(journal(cli, "s")).execute("SELECT type FROM events ORDER BY seq DESC LIMIT 1")
    assert last.fetchone() == ("session.stopped",)


async def test_a_refused_run_or_resume_exits_64_and_never_the_code_of_a_failed_agent(cli: Cli):
    team = cli.write("solo.toml", solo("listening"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")

    taken = await cli.run("run", "go", "--team", team, "--trust", "--name", "s", "--json")
    unnamed = await cli.run("run", "go", "--team", team, "--trust", "--name", "no/name", "--json")
    live = await cli.run("session", "resume", "s", "--json")
    await cli.run("session", "stop", "s")
    await finished(serving)

    assert [taken.code, unnamed.code, live.code] == [64, 64, 64], live.stderr
    assert "refused conflict: session s exists" in taken.stderr and [taken.stdout, live.stdout] == ["", ""]


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


async def test_a_prompt_piped_to_run_dash_reaches_the_agent(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))

    done = await cli.run("run", "-", "--team", team, "--trust", "--json", input=b"Fix it, after a dash\n")

    sent = next(event for event in checked(done) if event["type"] == "message.sent")
    assert (done.code, sent["gist"]) == (0, "Fix it, after a dash"), done.stderr


@pytest.mark.parametrize(
    ("args", "said"),
    [
        (("--no-such-option",), "no option --no-such-option"),
        (("-",), "stdin: 'utf-8' codec can't decode"),
    ],
)
async def test_a_prompt_that_cannot_be_read_exits_64_saying_why(cli: Cli, args: tuple[str, ...], said: str):
    team = cli.write("solo.toml", solo("saying"))

    done = await cli.run("run", *args, "--team", team, "--trust", input=b"\xff\xfe go")

    assert (done.code, done.stdout) == (64, ""), done.stderr
    assert said in done.stderr and "Traceback" not in done.stderr


async def test_a_run_with_stdin_closed_exits_64_saying_so(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))
    closed = 'exec "$0" "$@" <&-'

    process = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        closed,
        EXECUTABLE,
        "run",
        "-",
        "--team",
        team,
        "--trust",
        cwd=cli.folder,
        env=cli.env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    cli.started.append(process)
    done = await finished(process)

    assert (done.code, done.stdout) == (64, ""), done.stderr
    assert "stdin is closed" in done.stderr


async def test_a_long_prompt_from_a_file_goes_whole_as_the_body(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))
    prompt = cli.write("task.md", "Fix the flaky test. " * 40)

    done = await cli.run("run", "--team", team, "--trust", "--json", "--prompt-file", prompt, "--name", "s")

    events = checked(done)
    sent = next(event for event in events if event["type"] == "message.sent")
    body = await cli.run("blob", "get", "s", "--ref", f"{sent['stream']}@{sent['version']}")
    assert len(sent["gist"]) == 280 and sent["gist"].endswith("…")
    assert json.loads(body.stdout)["text"] == ("Fix the flaky test. " * 40).strip()


async def test_the_prompt_goes_to_the_agent_named_when_a_session_starts_several(cli: Cli):
    team = cli.write("pair.toml", solo("saying", count="2"))

    named = await cli.run("run", "go", "--team", team, "--trust", "--to", "@bob-2", "--json")

    sent = next(event for event in checked(named) if event["type"] == "message.sent")
    assert sent["stream"] == "inbox/bob-2"


@pytest.mark.parametrize(
    ("team", "to", "said"),
    [
        (
            solo("saying", count="2"),
            (),
            "say which agent the prompt is for, with --to: this session starts @bob-1, @bob-2",
        ),
        (solo("saying"), ("--to", "@nobody"), "--to @nobody is no agent this session starts: it starts @bob"),
        (solo("saying"), ("--to", "bob"), "--to bob is no agent this session starts: it starts @bob"),
    ],
)
async def test_who_a_prompt_is_for_is_decided_before_any_cost(cli: Cli, team: str, to: tuple[str, ...], said: str):
    written = cli.write("team.toml", team)

    done = await cli.run("run", "go", "--team", written, "--trust", "--json", *to)

    assert (done.code, done.stdout) == (64, ""), done.stderr
    assert said in done.stderr
    assert not (cli.folder / "home" / "sessions").exists()


# Other processes.


async def test_a_person_s_message_from_a_second_process_steers_an_agent_whose_role_says_pull(cli: Cli):
    """A person's message steers whatever its reader's setting, so a role that pulls is woken by it: the run's prompt,
    which `Session.send` sends, and a message from a second process."""
    team = cli.write("solo.toml", solo("listening", delivery='"pull"'))
    run = await cli.start("run", "wait for me", "--team", team, "--trust", "--name", "s", "--json")
    seen: list[dict] = []
    await line_where(run, seen, "type", "agent.parked")

    sent = await cli.run("message", "send", "s", "--to", "@bob", "--gist", "here you are")
    done = await finished(run)

    assert sent.code == 0, sent.stderr
    ref = json.loads(sent.stdout)["ref"]
    events = [*seen, *done.lines()[:-1]]
    assert done.code == 0, done.stderr
    sent_by_you = [event for event in events if event["type"] == "message.sent" and event["actor"] == "human:you"]
    assert [(event["gist"], event["data"]["delivery"]) for event in sent_by_you] == [
        ("wait for me", "steer"),
        ("here you are", "steer"),
    ]
    offered = [event for event in events if event["type"] == "context.offered" and event["agent"] == "bob"]
    assert any(item["ref"] == ref for event in offered for item in event["data"]["items"])
    assert done.lines()[-1]["agents"][0]["report"]["gist"] == "heard you"


async def test_an_approval_is_answered_from_a_second_process_once(cli: Cli):
    team = cli.write("solo.toml", solo("asking"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
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
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
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
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
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


async def test_events_follow_ends_once_nobody_reads_it(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    reading, writing = os.pipe()
    following = await cli.start("events", "s", "--follow", "--json", stdout=writing)
    os.close(writing)
    with os.fdopen(reading, "rb") as pipe:
        await asyncio.to_thread(pipe.readline)

    await cli.run("message", "send", "s", "--to", "@bob", "--gist", "one more line for nobody")
    code = await asyncio.wait_for(following.wait(), SECONDS)
    await cli.run("session", "stop", "s")
    await finished(serving)

    assert code == 0


async def test_session_list_lists_a_session_that_never_opened_beside_the_rest(cli: Cli):
    team = cli.write("solo.toml", solo("saying"))
    await cli.run("run", "go", "--team", team, "--trust", "--name", "done")
    sessions = cli.folder / "home" / "sessions"
    (sessions / "unopened").mkdir()
    (sessions / "unopened" / "manifest.json").write_text((sessions / "done" / "manifest.json").read_text())

    listed = await cli.run("session", "list", "--json")

    assert listed.code == 0, listed.stderr
    assert json.loads(listed.stdout) == [
        {"name": "done", "live": False, "state": "closed"},
        {"name": "unopened", "live": False, "state": None},
    ]
    assert "session unopened: refused unavailable" in listed.stderr


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
        (("session", "resume", "nowhere"), 64),
        (("session", "stop", "nowhere"), 1),
        (("team", "check"), 78),
        (("attach", "s"), 64),
    ],
)
async def test_no_command_prompts_with_no_terminal(cli: Cli, args: tuple[str, ...], code: int):
    """Stdin is empty: `run -` reads it, and finds no prompt there."""
    cli.write("platoon-harness.toml", "this is no team")
    fake_harnesses(cli, "claude")

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


WITHOUT_OPENHANDS = """
import importlib.metadata

found = importlib.metadata.version


def version(name):
    if name.startswith("openhands-"):
        raise importlib.metadata.PackageNotFoundError(name)
    return found(name)


importlib.metadata.version = version
"""
"""What an interpreter finds of the SDK's `openhands` extra where nobody installed it: no metadata of either package."""


def without_openhands(cli: Cli) -> None:
    """The command line, and what it runs with its environment, on an interpreter that finds no `openhands` extra."""
    folder = cli.folder / "site"
    folder.mkdir()
    (folder / "sitecustomize.py").write_text(WITHOUT_OPENHANDS)
    cli.env["PYTHONPATH"] = f"{folder}:{cli.env['PYTHONPATH']}"


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


async def test_init_writes_through_no_link_to_a_file_that_is_not_there(cli: Cli):
    fake_harnesses(cli, "claude")
    (cli.folder / "platoon-harness.toml").symlink_to(cli.folder / "elsewhere.toml")

    done = await cli.run("init")

    assert done.code == 1 and "exists" in done.stderr
    assert not (cli.folder / "elsewhere.toml").exists()


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
    assert found["pi"] == {"name": "pi", "found": False, "reason": "not on PATH"}
    assert report["root"]["path"] == cli.env["PLATOON_HARNESS_HOME"]
    assert {component["name"] for component in report["installed"]["components"]} >= {"claude", "codex", "pi"}


async def test_openhands_is_found_by_its_extra_and_init_passes_it_over_as_it_writes_no_auth_profile(cli: Cli):
    """The OpenHands CLI is `openhands`, a command of the harness's name that is not what runs it."""
    fake_harnesses(cli, "openhands")

    doctor = await cli.run("doctor", "--json")
    init = await cli.run("init")

    found = {harness["name"]: harness for harness in json.loads(doctor.stdout)["harnesses"]}
    assert doctor.code == 0
    assert found["openhands"] == {"name": "openhands", "found": True, "version": "1.59.0", "login": None}
    assert init.code == 78 and "openhands" not in init.stderr


async def test_doctor_and_a_start_without_the_openhands_extra_name_one_interpreter_to_install_it_for(cli: Cli):
    fake_harnesses(cli, "claude")
    without_openhands(cli)
    team = cli.write("solo.toml", '[roles.bob]\nharness = "openhands"\n')

    doctor = await cli.run("doctor")
    run = await cli.run("run", "go", "--team", team, "--json")

    told = next(line for line in doctor.stdout.splitlines() if line.startswith("openhands "))
    reason = run.lines()[-1]["agents"][0]["reason"]
    interpreter = re.match(r"openhands +openhands-sdk is not installed for (.+?): ", told)
    assert doctor.code == 0 and "claude     9.9.9 (fake), login unknown" in doctor.stdout
    assert interpreter is not None and Path(interpreter[1]).is_file(), told
    assert told.endswith("install the SDK's `openhands` extra there, `platoon-harness-sdk[openhands]`")
    assert (run.code, reason) == (1, f"its spawn failed: {told.removeprefix('openhands').lstrip()}")


async def test_doctor_with_no_harness_on_path_and_no_openhands_extra_exits_78(cli: Cli):
    fake_harnesses(cli)
    without_openhands(cli)

    done = await cli.run("doctor")

    assert done.code == 78 and "problem    no harness is on PATH" in done.stdout


async def test_a_root_others_can_write_is_a_machine_that_cannot_be_used_as_it_is(cli: Cli):
    fake_harnesses(cli, "claude")
    root = cli.folder / "home"
    root.mkdir()
    root.chmod(0o777)
    team = cli.write("solo.toml", solo("saying"))

    ran = await cli.run("run", "go", "--team", team, "--trust")
    doctor = await cli.run("doctor", "--json")

    assert ran.code == 78 and "nobody else can write" in ran.stderr
    assert doctor.code == 78 and "nobody else can write" in json.loads(doctor.stdout)["root"]["problem"]


async def test_extension_list_reads_what_is_installed_from_metadata(cli: Cli):
    done = await cli.run("extension", "list", "--json")

    listed = json.loads(done.stdout)
    assert done.code == 0
    assert {"kind": "driver", "name": "claude", "distribution": "platoon-harness-sdk"} in [
        {key: component[key] for key in ("kind", "name", "distribution")} for component in listed["components"]
    ]
    assert listed["problems"] == []
