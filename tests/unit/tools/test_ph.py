"""`ph` as an agent runs it: a real process against a real server."""

import asyncio
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from platoon_harness.tools import PH, shim
from platoon_harness.tools.ph import TOKEN_VARIABLE, URL_VARIABLE

from ..primitives.support import of_type, send, start_turn
from .support import check_stands_alone, enrolled, finished, value_of

OTHER_PYTHON = shutil.which("python3", path=os.defpath)


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


async def ph(client, *argv: str, python: str = sys.executable, env: dict[str, str] | None = None) -> Run:
    environment = {URL_VARIABLE: client.url, TOKEN_VARIABLE: client.token} if env is None else env
    command = (python, str(PH)) if python else ("ph",)
    process = await asyncio.create_subprocess_exec(
        *command, *argv, env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await finished(process)
    return Run(process.returncode, out.decode(), err.decode())


async def add_task(lead, gist: str = "do it") -> None:
    value_of(await lead[1].call("task_add", {"queue": "tasks", "gist": gist}))


def test_ph_stands_alone():
    check_stands_alone(PH)


def test_ph_and_the_shim_read_the_same_variables():
    assert (shim.URL_VARIABLE, shim.TOKEN_VARIABLE) == (URL_VARIABLE, TOKEN_VARIABLE)


def test_ph_reads_the_variables_a_harness_is_given():
    env = pytest.importorskip("platoon_harness.drivers.env")

    assert (env.URL_VARIABLE, env.TOKEN_VARIABLE) == (URL_VARIABLE, TOKEN_VARIABLE)


async def test_spawned_with_no_token_it_says_so(lead):
    run = await ph(lead[1], "--help", env={})

    assert run.code == 78
    assert "no token" in run.stderr and TOKEN_VARIABLE in run.stderr


async def test_help_lists_what_this_agent_may_do(kernel, server, lead):
    _, narrow = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])

    led = await ph(lead[1], "--help")
    held = await ph(narrow, "--help")

    assert led.code == 0
    assert "task.add" in led.stdout and "agent.spawn" in led.stdout
    assert "message.send" in held.stdout and "task.add" not in held.stdout


async def test_help_documents_the_exit_codes(lead):
    run = await ph(lead[1], "--help")

    assert "69  the runtime cannot be reached" in run.stdout


async def test_help_on_an_op_shows_its_arguments(worker):
    run = await ph(worker[1], "task.claim", "--help")

    assert run.code == 0
    assert "usage: ph task.claim" in run.stdout
    assert "--queue (string, required)" in run.stdout
    assert "--task (string)" in run.stdout
    assert "`ph wait`" in run.stdout, "a description is in the words of its surface"


async def test_a_bare_ph_prints_usage_and_fails(lead):
    run = await ph(lead[1])

    assert run.code == 2
    assert "usage: ph" in run.stdout


async def test_a_call_prints_json_on_stdout(lead, worker):
    await add_task(lead)

    run = await ph(worker[1], "task.claim", "--queue", "tasks")

    assert run.code == 0
    assert json.loads(run.stdout)["task"] == "1"
    assert run.stderr == ""


async def test_a_flag_can_be_written_with_an_equals_sign(lead, worker):
    await add_task(lead)

    assert (await ph(worker[1], "task.claim", "--queue=tasks")).code == 0


async def test_a_refusal_is_plain_text_on_stderr(worker):
    run = await ph(worker[1], "task.claim", "--queue", "tasks")

    assert run.code == 1
    assert run.stdout == ""
    assert run.stderr.startswith("Refused queue_empty")
    assert "`ph wait`" in run.stderr


async def test_flags_are_typed_by_the_schema(kernel, lead, worker):
    await add_task(lead, "one")
    await add_task(lead, "two")
    await ph(worker[1], "task.claim", "--queue", "tasks")

    listed = await ph(lead[1], "task.list", "--queue", "tasks", "--limit", "1", "--state", "claimed")

    assert [task["gist"] for task in json.loads(listed.stdout)["tasks"]] == ["one"]


async def test_a_repeated_flag_builds_a_list(kernel, lead, worker):
    run = await ph(lead[1], "wait", "--agents", "w1", "--agents", "@w1", "--mode", "any")

    assert json.loads(run.stdout)["state"] == "parked"


async def test_a_boolean_flag_can_stand_alone(kernel, lead, worker):
    await lead[1].call("message_send", {"to": "@w1", "gist": "see body", "body": "the detail"})

    run = await ph(worker[1], "message.read", "--bodies")

    assert json.loads(run.stdout)["entries"][0]["text"] == "the detail"


async def test_a_boolean_flag_can_say_false(kernel, lead, worker):
    await lead[1].call("message_send", {"to": "@w1", "gist": "see body", "body": "the detail"})

    run = await ph(worker[1], "message.read", "--bodies", "false")

    assert "text" not in json.loads(run.stdout)["entries"][0]


async def test_an_object_flag_is_json(kernel, lead):
    arguments = ("--board", "notes", "--name", "spec", "--gist", "v1", "--fields", '{"status": "draft"}')

    assert (await ph(lead[1], "board.post", *arguments)).code == 0
    found = await ph(lead[1], "board.query", "--board", "notes", "--where", '{"status": "draft"}')

    assert json.loads(found.stdout)["total"] == 1


async def test_a_body_is_given_as_text(kernel, lead):
    await ph(lead[1], "task.add", "--queue", "tasks", "--gist", "x", "--body", "some detail")

    cited = of_type(kernel, "task.added")[-1].data["body"]
    assert kernel.get_body(cited.removeprefix("sha256:")) == b"some detail"


async def test_what_will_not_parse_goes_to_the_runtime_to_refuse(lead):
    run = await ph(lead[1], "task.list", "--queue", "tasks", "--limit", "many")

    assert run.code == 1
    assert run.stderr.startswith("Refused invalid")


async def test_a_flag_it_does_not_declare_is_refused_and_journaled(kernel, lead):
    head = kernel.head

    run = await ph(lead[1], "peers", "--caller", "root")

    assert run.code == 1
    assert "caller" in run.stderr
    assert [event.data["code"] for event in of_type(kernel, "op.refused", after=head)] == ["invalid"]


async def test_an_op_this_token_does_not_hold_is_refused_and_journaled(kernel, lead, worker):
    head = kernel.head

    run = await ph(worker[1], "task.add", "--queue", "tasks", "--gist", "x")

    assert run.code == 1
    assert run.stderr.startswith("Refused not_permitted")
    assert [event.data["op"] for event in of_type(kernel, "op.refused", after=head)] == ["task.add"]


async def test_what_is_no_op_is_a_usage_error(lead):
    run = await ph(lead[1], "no.such")

    assert run.code == 2
    assert "ph --help" in run.stderr


@pytest.mark.parametrize("argv", [("peers", "stray"), ("peers", "--"), ("task.list", "--queue")])
async def test_argv_that_makes_no_sense_is_a_usage_error(lead, argv):
    run = await ph(lead[1], *argv)

    assert run.code == 2
    assert run.stderr.startswith("ph: ")


async def test_a_second_claim_is_a_second_call_not_a_retry(kernel, lead, worker):
    await add_task(lead, "one")
    await add_task(lead, "two")
    await start_turn(kernel, "w1")

    first = await ph(worker[1], "task.claim", "--queue", "tasks")
    await ph(worker[1], "task.complete", "--queue", "tasks")
    second = await ph(worker[1], "task.claim", "--queue", "tasks")

    assert [json.loads(run.stdout)["task"] for run in (first, second)] == ["1", "2"]


async def test_its_own_id_cannot_pass_for_a_harnesss(kernel, lead, worker):
    await add_task(lead)

    await ph(worker[1], "task.claim", "--queue", "tasks")

    assert [*of_type(kernel, "task.claimed")[-1].native] == ["platoon-harness/callId"]


async def test_notices_go_to_stderr_and_leave_stdout_as_json(kernel, server, lead):
    _, client = await enrolled(kernel, server, "s1", role="steered", by=lead[0])
    await start_turn(kernel, "s1")
    await send(kernel, lead[0], "@s1", "stop that")

    run = await ph(client, "channel.list")

    assert run.code == 0
    assert json.loads(run.stdout) == [{"name": "notes", "kind": "board"}]
    assert "stop that" in run.stderr


async def test_a_token_of_an_ended_agent_is_refused(worker):
    await worker[1].call("agent_finish")

    run = await ph(worker[1], "--help")

    assert run.code == 1
    assert "not valid" in run.stderr


async def test_a_runtime_that_is_gone_is_reported(lead):
    env = {URL_VARIABLE: "http://127.0.0.1:1/mcp", TOKEN_VARIABLE: "x"}

    run = await ph(lead[1], "--help", env=env)

    assert run.code == 69
    assert "cannot be reached" in run.stderr


async def test_it_runs_from_an_agents_bin_directory(lead, tmp_path):
    copied = tmp_path / "bin" / "ph"
    copied.parent.mkdir()
    shutil.copy(PH, copied)
    copied.chmod(copied.stat().st_mode | stat.S_IEXEC)
    path = os.pathsep.join((str(copied.parent), str(Path(sys.executable).parent), os.defpath))
    env = {URL_VARIABLE: lead[1].url, TOKEN_VARIABLE: lead[1].token, "PATH": path}

    run = await ph(lead[1], "--help", python="", env=env)

    assert run.code == 0 and "task.add" in run.stdout


@pytest.mark.skipif(OTHER_PYTHON is None, reason="this host has no system python3")
async def test_it_runs_on_the_system_python(lead, worker):
    assert OTHER_PYTHON is not None
    await add_task(lead)

    run = await ph(worker[1], "task.claim", "--queue", "tasks", python=OTHER_PYTHON)

    assert (run.code, json.loads(run.stdout)["task"]) == (0, "1")


async def test_it_prints_text_that_is_not_ascii(lead, worker):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "café ☕"})

    run = await ph(worker[1], "task.claim", "--queue", "tasks")

    assert json.loads(run.stdout)["gist"] == "café ☕"
