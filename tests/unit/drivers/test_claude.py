"""The `claude` driver, on a stand-in that speaks the real frames: what it launches, and what each frame becomes."""

import asyncio
import contextlib
import json
import os
import stat
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
    ChildSeen,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    Exited,
    GapReport,
    InputDelivered,
    Item,
    ModelCall,
    Native,
    Offered,
    Ready,
    ToolBinding,
    TurnEnded,
    TurnStarted,
    Usage,
)
from platoon_harness.drivers import claude as module
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.process import Record

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

GRACE = 5.0
FAKE = Path(__file__).with_name("fake_claude.py")
STARTED = {"type": "command_lifecycle", "state": "started", "command_uuid": "$input"}
INIT = {"type": "system", "subtype": "init", "uuid": "init-1", "model": "fake-model"}
REQUESTING = {"type": "system", "subtype": "status", "status": "requesting"}
SPENT = {"m": {"inputTokens": 10, "cacheReadInputTokens": 20, "cacheCreationInputTokens": 30, "outputTokens": 5}}


def stream(event: dict[str, Any]) -> dict[str, Any]:
    return {"type": "stream_event", "event": event, "parent_tool_use_id": None}


def called(id: str = "msg_1") -> dict[str, Any]:
    message = {"id": id, "model": "m", "usage": {"input_tokens": 10, "cache_read_input_tokens": 20, "output_tokens": 1}}
    return stream({"type": "message_start", "message": message})


def text_delta(text: str) -> dict[str, Any]:
    return stream({"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


def finished(output: int = 5, stop_reason: str | None = "end_turn") -> dict[str, Any]:
    usage = {"cache_creation_input_tokens": 30, "output_tokens": output}
    return stream({"type": "message_delta", "delta": {"stop_reason": stop_reason}, "usage": usage})


def assistant(*blocks: dict[str, Any], id: str = "msg_1", model: str = "m", **fields: Any) -> dict[str, Any]:
    message = {"id": id, "model": model, "content": list(blocks)}
    return {"type": "assistant", "message": message, "parent_tool_use_id": None, **fields}


def said(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def using(id: str = "toolu_1", name: str = "Bash", **input: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": id, "name": name, "input": input}


def tool_result(id: str = "toolu_1", text: Any = "done", **fields: Any) -> dict[str, Any]:
    block = {"type": "tool_result", "tool_use_id": id, "content": text, **fields}
    return {"type": "user", "message": {"role": "user", "content": [block]}, "parent_tool_use_id": None}


def result(**fields: Any) -> dict[str, Any]:
    ending = {"subtype": "success", "is_error": False, "model_usage_since_last_result": {}}
    return {"type": "result", **ending, **fields}


def spend(usd: float = 0.5) -> dict[str, Any]:
    return result(model_usage_since_last_result={"m": {**SPENT["m"], "costUSD": usd}})


def asking(id: str = "ask-1", tool: str = "toolu_1") -> dict[str, Any]:
    request = {"subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "touch x"}, "tool_use_id": tool}
    return {"type": "control_request", "request_id": id, "request": request}


def delivery(input: str = "41", boundary: str = "turn") -> Delivery:
    item = Offered(ref="inbox/ada@1", gist="hello")
    return Delivery(input=input, boundary=boundary, text="New message", items=(item,))


class Stand:
    """A `claude` first on the PATH, and what it wrote down."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.script = folder / "script.json"

    def install(self, **script: Any) -> None:
        self.script.write_text(json.dumps(script))

    @property
    def launch(self) -> dict[str, Any]:
        return json.loads(self.script.with_suffix(".launch").read_text())

    @property
    def heard(self) -> list[dict[str, Any]]:
        lines = self.script.with_suffix(".heard").read_text().splitlines()
        return [json.loads(line) for line in lines]


@pytest.fixture
def stand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Stand:
    folder = tmp_path / "stand"
    folder.mkdir()
    program = folder / "claude"
    script = folder / "script.json"
    program.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "{script}" "$@"\n')
    program.chmod(0o700)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    found = Stand(folder)
    found.install()
    return found


@contextlib.asynccontextmanager
async def running(spec: AgentSpec) -> AsyncIterator[tuple[ClaudeDriver, Heard]]:
    driver, heard = ClaudeDriver(), Heard()
    await driver.start(spec, heard)
    try:
        yield driver, heard
    finally:
        await driver.stop(GRACE)


async def played(stand: Stand, tmp_path: Path, *frames: Any) -> list[Any]:
    """Every report of one turn on the goal, once it ended."""
    stand.install(turns=[[STARTED, *frames]])
    async with running(make_spec(tmp_path)) as (_, heard):
        await heard.until(TurnEnded)
        return heard.reports[1:]


def kinds(reports: list[Any]) -> list[type]:
    return [type(report) for report in reports]


# What it launches.


async def test_the_launch_is_the_one_path(tmp_path, stand):
    tools = ToolBinding(
        url="http://127.0.0.1:1/mcp?surface=mcp__ph", token=Secret("tok-1"), namespace="ph", bin=tmp_path
    )
    spec = make_spec(tmp_path, model="fake-model", tools=tools, instructions="the preamble")

    async with running(spec) as (_, heard):
        ready = await heard.until(Ready)

    argv = stand.launch["argv"]
    assert argv[:10] == [
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--permission-prompt-tool",
        "stdio",
        "--session-id",
    ]
    assert argv[10] == ready.native
    assert argv[argv.index("--model") + 1] == "fake-model"
    assert argv[argv.index("--allowedTools") + 1] == "mcp__ph__*"
    assert Path(argv[argv.index("--append-system-prompt-file") + 1]).read_text() == "the preamble"


async def test_it_leaves_the_user_s_setup_and_the_runtime_s_approvals_alone(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    forbidden = ("--setting-sources", "--strict-mcp-config", "--max-turns", "--permission-mode", "--permission-prompts")
    assert not [flag for flag in stand.launch["argv"] if flag in forbidden or "dangerously" in flag]


async def test_the_tool_token_is_in_a_private_file_and_never_in_argv(tmp_path, stand):
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret("tok-1"), namespace="ph", bin=tmp_path)

    async with running(make_spec(tmp_path, tools=tools)) as (_, heard):
        await heard.until(Ready)
        argv = stand.launch["argv"]
        path = Path(argv[argv.index("--mcp-config") + 1])
        servers = json.loads(path.read_text())["mcpServers"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert "tok-1" not in " ".join(argv)
    assert servers == {
        "ph": {
            "type": "http",
            "url": "http://127.0.0.1:1/mcp",
            "headers": {"Authorization": "Bearer tok-1"},
            "alwaysLoad": True,
        }
    }


async def test_a_stop_leaves_no_token_at_rest(tmp_path, stand):
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret("tok-1"), namespace="ph", bin=tmp_path)
    spec = make_spec(tmp_path, tools=tools)

    async with running(spec) as (_, heard):
        await heard.until(Ready)

    assert not (spec.folder / "mcp.json").exists()


async def test_an_unset_model_on_the_harness_s_own_login_is_its_own_default_and_ready_says_which(tmp_path, stand):
    stand.install(applied={"model": "the-default", "effort": "high"})

    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        ready = await heard.until(Ready)

    assert "--model" not in stand.launch["argv"]
    assert ready.effective_model == "the-default"


async def test_an_unset_model_is_refused_where_access_was_given(tmp_path, stand):
    spec = make_spec(tmp_path, access={"ANTHROPIC_API_KEY": Secret("a-key")})

    with pytest.raises(DriverError, match="set a model"):
        await ClaudeDriver().start(spec, Heard())


async def test_a_gateway_url_with_no_credential_is_refused(tmp_path, stand):
    spec = make_spec(tmp_path, model="m", access={"ANTHROPIC_BASE_URL": Secret("http://gateway")})

    with pytest.raises(DriverError, match="saved login"):
        await ClaudeDriver().start(spec, Heard())


async def test_resuming_reopens_the_native_session_and_begins_no_turn(tmp_path, stand):
    native = str(uuid4())
    stand.install(turns=[[STARTED]])

    async with running(make_spec(tmp_path, resume=native)) as (_, heard):
        ready = await heard.until(Ready)

        assert ready.native == native
        argv = stand.launch["argv"]
        assert argv[argv.index("--resume") + 1] == native
        assert "--session-id" not in argv
        assert not heard.of(TurnStarted)


async def test_no_goal_takes_no_turn(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    assert [frame for frame in stand.heard if frame["type"] == "user"] == []


async def test_what_the_shell_needs_to_sign_in_gets_through_and_a_key_does_not(tmp_path, stand, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/a/config")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/a/ca.pem")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must not pass")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "must not pass")
    monkeypatch.setenv("CLAUDECODE", "must not pass")

    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    env = stand.launch["env"]
    assert (env["CLAUDE_CONFIG_DIR"], env["HTTPS_PROXY"], env["NODE_EXTRA_CA_CERTS"]) == (
        "/a/config",
        "http://proxy",
        "/a/ca.pem",
    )
    assert not {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDECODE"} & set(env)


async def test_auto_memory_and_background_tasks_are_off(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    env = stand.launch["env"]
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"


async def test_effort_goes_to_the_harness_as_it_stands(tmp_path, stand):
    stand.install(applied={"model": "m", "effort": "low"})

    async with running(make_spec(tmp_path, goal="", effort="low")) as (_, heard):
        await heard.until(Ready)

    argv = stand.launch["argv"]
    assert argv[argv.index("--effort") + 1] == "low"


async def test_an_effort_the_harness_dropped_is_refused(tmp_path, stand):
    stand.install(applied={"model": "m", "effort": "high"})
    driver = ClaudeDriver()

    with pytest.raises(DriverError, match="effort high, and bogus was asked for"):
        await driver.start(make_spec(tmp_path, goal="", effort="bogus"), Heard())

    await driver.stop(GRACE)


async def test_a_harness_that_is_not_installed_fails_its_start_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(DriverError, match="claude is not an executable"):
        await ClaudeDriver().start(make_spec(tmp_path), Heard())


# What it says of itself.


@pytest.mark.parametrize(
    ("status", "login"),
    [
        ({"loggedIn": True, "authMethod": "claude.ai", "email": "someone"}, "plan"),
        ({"loggedIn": True, "authMethod": "api_key"}, "key"),
        ({"loggedIn": False, "authMethod": "none"}, None),
        ({"subscriptionType": "max"}, None),
        (["no", "object"], None),
        ({"authMethod": ["no", "name"]}, None),
    ],
)
def test_the_login_kind_comes_from_the_harness_s_own_word(stand, status, login):
    stand.install(status=json.dumps(status))

    assert ClaudeDriver().describe().login == login


def test_a_status_that_says_nothing_readable_is_no_login_we_know_of(stand):
    stand.install(status="Not JSON at all", status_code=1)

    assert ClaudeDriver().describe().login is None


def test_a_status_that_hangs_is_cut_short(stand, monkeypatch):
    monkeypatch.setattr(module, "_STATUS_SECONDS", 0.2)
    stand.install(status_seconds=30)

    assert ClaudeDriver().describe().login is None


def test_a_harness_that_is_not_installed_describes_no_login(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))

    assert ClaudeDriver().describe().login is None


def test_describing_runs_no_harness_and_answers_alike(stand):
    stand.install(status=json.dumps({"authMethod": "api_key"}))
    driver = ClaudeDriver()

    assert driver.describe() == driver.describe()
    assert not stand.script.with_suffix(".launch").exists()


# Coming up.


async def test_ready_says_what_was_observed(tmp_path, stand):
    stand.install(version="2.1.316", applied={"model": "fake-model", "effort": "high"})

    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        ready = await heard.until(Ready)

    assert (ready.version, ready.effective_model, ready.tools_visible) == ("2.1.316", "fake-model", None)


async def test_a_connected_server_proves_nothing_and_a_failed_one_hides_our_tools(tmp_path, stand):
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret("t"), namespace="ph", bin=tmp_path)
    for status, shown in (("connected", None), ("failed", ())):
        stand.install(servers=[{"name": "ph", "status": status}, {"name": "theirs", "status": "failed"}])

        async with running(make_spec(tmp_path, tools=tools, goal="")) as (_, heard):
            ready = await heard.until(Ready)

        assert ready.tools_visible == shown


async def test_a_harness_that_dies_coming_up_says_where_to_look(tmp_path, stand):
    stand.install(exit_at_once=1)
    driver = ClaudeDriver()

    with pytest.raises(DriverError, match=r"claude is gone: see .*stderr\.log"):
        await driver.start(make_spec(tmp_path), Heard())

    await driver.stop(GRACE)


# What each frame becomes.


async def test_a_turn_with_text_reports_its_call_its_words_and_its_cost(tmp_path, stand):
    reports = await played(
        stand,
        tmp_path,
        INIT,
        REQUESTING,
        called(),
        text_delta("hello "),
        text_delta("world"),
        assistant(said("hello world")),
        finished(),
        spend(),
    )

    assert kinds(reports) == [TurnStarted, ModelCall, Delta, Delta, Item, Usage, Usage, TurnEnded]
    _, call, _, _, item, tokens, usd, ended = reports
    assert (call.call_id, call.model) == ("msg_1", "m")
    assert (item.kind, item.phase, item.body, item.call_id) == ("message", "final", "hello world", "msg_1")
    assert (tokens.tokens, tokens.label, tokens.scope, tokens.call_id) == (65, "provider", "call", "msg_1")
    assert (usd.usd, usd.label) == (0.5, "estimated")
    assert ended.reason == "stopped"


async def test_a_long_message_has_a_short_gist_and_a_whole_body(tmp_path, stand):
    reports = await played(stand, tmp_path, assistant(said("x" * 1000)), result())

    item = next(report for report in reports if isinstance(report, Item))
    assert (len(item.gist), len(item.body)) == (280, 1000)


async def test_a_tool_is_started_then_completed_under_the_model_s_id(tmp_path, stand):
    reports = await played(
        stand, tmp_path, assistant(using(command="ls")), tool_result(text=[{"type": "text", "text": "pong"}]), result()
    )

    started, completed = [report for report in reports if isinstance(report, Item)]
    assert (started.kind, started.phase, started.native_id, started.call_id) == ("tool", "started", "toolu_1", "msg_1")
    assert started.gist == 'Bash {"command": "ls"}'
    assert (completed.phase, completed.native_id, completed.outcome, completed.body) == (
        "completed",
        "toolu_1",
        "completed",
        "pong",
    )
    assert completed.gist == "Bash completed"


async def test_a_tool_that_failed_says_so(tmp_path, stand):
    reports = await played(stand, tmp_path, assistant(using()), tool_result(is_error=True), result())

    assert [report.outcome for report in reports if isinstance(report, Item)] == [None, "failed"]


async def test_an_empty_thought_is_no_thought_and_a_real_one_is_kept(tmp_path, stand):
    empty, real = {"type": "thinking", "thinking": ""}, {"type": "thinking", "thinking": "hm"}

    reports = await played(stand, tmp_path, assistant(empty, real), result())

    assert [report.body for report in reports if isinstance(report, Item)] == ["hm"]


async def test_a_message_the_harness_made_up_names_no_model_call(tmp_path, stand):
    reports = await played(stand, tmp_path, assistant(said("Not logged in"), model="<synthetic>"), result())

    assert next(report for report in reports if isinstance(report, Item)).call_id is None


async def test_a_child_s_spend_is_what_the_calls_left_out(tmp_path, stand):
    reports = await played(stand, tmp_path, called(), finished(output=0), spend())

    tree = [report for report in reports if isinstance(report, Usage) and report.scope == "tree"]
    assert (tree[0].tokens, tree[0].label) == (5, "provider")


async def test_tokens_nobody_reported_are_a_gap_and_no_guess(tmp_path, stand):
    reports = await played(stand, tmp_path, {"type": "result", "subtype": "success", "is_error": False})

    assert GapReport(plane="model", what="usage_lower_bound") in reports
    assert not [report for report in reports if isinstance(report, Usage)]


async def test_a_call_the_harness_stopped_hearing_is_unknown_and_not_zero(tmp_path, stand):
    reports = await played(
        stand, tmp_path, REQUESTING, called(), result(subtype="error_during_execution", is_error=True)
    )

    usage = next(report for report in reports if isinstance(report, Usage))
    assert (usage.tokens, usage.label, usage.call_id) == (None, "unavailable", "msg_1")


async def test_the_close_the_harness_writes_for_a_stream_it_aborted_is_no_measurement(tmp_path, stand):
    aborted = result(subtype="error_during_execution", is_error=True, terminal_reason="aborted_streaming")

    reports = await played(stand, tmp_path, called(), finished(stop_reason=None), aborted)

    usages = [report for report in reports if isinstance(report, Usage)]
    assert [(usage.tokens, usage.label) for usage in usages] == [(None, "unavailable")]


async def test_a_call_cut_off_before_it_streamed_is_still_a_call_and_names_no_id(tmp_path, stand):
    reports = await played(stand, tmp_path, REQUESTING, result(is_error=True))

    usage = next(report for report in reports if isinstance(report, Usage))
    assert (usage.tokens, usage.label, usage.call_id) == (None, "unavailable", None)
    assert ModelCall() in reports


async def test_a_turn_that_failed_says_what_went_wrong(tmp_path, stand):
    failure = result(is_error=True, terminal_reason="api_error", result="Not logged in · Please run /login")

    reports = await played(stand, tmp_path, failure)

    assert reports[-1] == TurnEnded(reason="api_error: Not logged in · Please run /login")


async def test_a_failure_with_only_an_error_list_still_says_it(tmp_path, stand):
    failure = result(subtype="error_during_execution", is_error=True, errors=["it broke"], terminal_reason="aborted")

    assert (await played(stand, tmp_path, failure))[-1] == TurnEnded(reason="aborted: it broke")


async def test_a_turn_begun_by_the_harness_itself_is_a_turn(tmp_path, stand):
    stand.install(turns=[[INIT, result()]])

    async with running(make_spec(tmp_path)) as (_, heard):
        started = await heard.until(TurnStarted)
        await heard.until(TurnEnded)

    assert started.turn == "init-1"


async def test_compaction_keeps_its_summary_and_leaves_what_it_forgot_unknown(tmp_path, stand):
    summary = {"type": "user", "isSynthetic": True, "message": {"role": "user", "content": "the summary"}}

    reports = await played(
        stand,
        tmp_path,
        {"type": "system", "subtype": "status", "status": "compacting"},
        {"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "manual"}},
        summary,
        result(),
    )

    assert ModelCall(purpose="compaction") in reports
    assert Compacted(forgotten=None, summary="the summary") in reports


async def test_a_compaction_with_no_summary_is_still_reported(tmp_path, stand):
    reports = await played(stand, tmp_path, {"type": "system", "subtype": "compact_boundary"}, result())

    assert Compacted(forgotten=None, summary=None) in reports


async def test_a_native_child_is_seen_under_the_call_that_started_it(tmp_path, stand):
    started = {
        "type": "system",
        "subtype": "task_started",
        "task_id": "a1",
        "tool_use_id": "toolu_child",
        "task_type": "local_agent",
        "is_backgrounded": False,
    }

    reports = await played(stand, tmp_path, started, result())

    assert ChildSeen(native="a1", parent="toolu_child", attribution="inferred") in reports
    assert GapReport(plane="model", what="native_child_unattributed") in reports


async def test_a_child_that_could_outlive_its_turn_is_labelled(tmp_path, stand):
    started = {
        "type": "system",
        "subtype": "task_started",
        "task_id": "a1",
        "tool_use_id": "toolu_child",
        "task_type": "local_agent",
        "is_backgrounded": True,
    }

    reports = await played(stand, tmp_path, started, result())

    assert not [report for report in reports if isinstance(report, ChildSeen)]
    assert next(report for report in reports if isinstance(report, Native)).kind == "system/task_started"


async def test_what_a_child_does_is_not_this_agent_s_item(tmp_path, stand):
    child = {"parent_tool_use_id": "toolu_child", "agent_id": "a1"}

    reports = await played(stand, tmp_path, {**assistant(said("mine")), **child}, {**called(), **child}, result())

    assert kinds(reports) == [TurnStarted, TurnEnded]


async def test_frames_with_nothing_for_us_say_nothing(tmp_path, stand):
    quiet = [
        {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}},
        {"type": "tool_progress", "tool_use_id": "t-heartbeat-0", "parent_tool_use_id": "t"},
        {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 1},
        {"type": "system", "subtype": "api_retry", "attempt": 1},
        {"type": "system", "subtype": "task_updated", "patch": {}},
        {"type": "system", "subtype": "task_notification", "status": "completed"},
    ]

    assert kinds(await played(stand, tmp_path, *quiet, result())) == [TurnStarted, TurnEnded]


async def test_an_unknown_frame_is_native_plus_a_gap(tmp_path, stand):
    reports = await played(stand, tmp_path, {"type": "nobody knows"}, "this is no frame", result())

    natives = [report for report in reports if isinstance(report, Native)]
    assert [native.kind for native in natives] == ["nobody knows", "frame"]
    assert reports.count(GapReport(plane="control", what="unknown_update")) == 2


async def test_a_frame_of_a_known_type_that_does_not_read_is_native_too(tmp_path, stand):
    reports = await played(stand, tmp_path, {"type": "assistant", "message": "not a message"}, result())

    assert next(report for report in reports if isinstance(report, Native)).kind == "assistant"


async def test_a_block_nobody_knows_is_native_too(tmp_path, stand):
    reports = await played(stand, tmp_path, assistant({"type": "new_block", "x": 1}), result())

    assert next(report for report in reports if isinstance(report, Native)).kind == "assistant"


async def test_a_credential_in_an_unknown_frame_is_masked_before_it_is_cut(tmp_path, stand):
    secret = "k" * 40
    stand.install(turns=[[STARTED, {"type": "nobody", "pad": "x" * 2030, "key": secret}, result()]])
    spec = make_spec(tmp_path, model="m", access={"ANTHROPIC_API_KEY": Secret(secret)})

    async with running(spec) as (_, heard):
        await heard.until(TurnEnded)

    assert "kkk" not in heard.of(Native)[0].raw


async def test_a_control_request_nobody_answers_is_refused_so_the_harness_does_not_wait(tmp_path, stand):
    asked = {"type": "control_request", "request_id": "r1", "request": {"subtype": "elicitation"}}
    stand.install(turns=[[STARTED, asked, result()]])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnEnded)
        await heard.until(Native)
        await driver.interrupt()

    refused = next(frame for frame in stand.heard if frame["type"] == "control_response")
    assert refused["response"]["request_id"] == "r1"
    assert refused["response"]["subtype"] == "error"
    assert heard.of(Native)[0].kind == "control_request"


async def test_account_details_in_the_handshake_reach_no_report(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    assert "someone" not in repr(heard.reports)


# Deliveries.


async def test_a_delivery_lands_as_a_turn_with_its_id_on_the_frame(tmp_path, stand):
    stand.install(turns=[[STARTED, result()]])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)

        receipt = await driver.deliver(delivery())

        landed = await heard.until(InputDelivered)
        await heard.until(TurnEnded)

    sent = next(frame for frame in stand.heard if frame["type"] == "user")
    assert sent["message"] == {"role": "user", "content": "New message"}
    assert (receipt.boundary, receipt.queued) == ("turn", ("41",))
    assert (landed.input, landed.boundary, landed.evidence) == ("41", "turn", "command_lifecycle")
    assert landed.native_id == sent["uuid"]
    assert kinds(heard.reports[1:3]) == [InputDelivered, TurnStarted]


async def test_a_delivery_in_a_turn_lands_at_a_tool_boundary(tmp_path, stand):
    stand.install(turns=[[STARTED, assistant(using())], [tool_result(), STARTED, result()]])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(Item)

        await driver.deliver(delivery(boundary="tool"))

        landed = await heard.until(InputDelivered)
        await heard.until(TurnEnded)

    assert landed.boundary == "tool"
    assert len(heard.of(TurnStarted)) == 1


async def test_a_steer_that_missed_every_tool_says_it_landed_as_a_turn(tmp_path, stand):
    stand.install(turns=[[STARTED, result()], [STARTED, result()]])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnEnded)

        await driver.deliver(delivery(boundary="tool"))

        landed = await heard.until(InputDelivered)

    assert landed.boundary == "turn"


async def test_a_boundary_nobody_declared_is_refused(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)

        with pytest.raises(DriverError, match="no model_call boundary"):
            await driver.deliver(delivery(boundary="model_call"))


async def test_a_harness_that_stopped_reading_holds_up_a_delivery_and_no_stop(tmp_path, stand):
    stand.install(deaf_after="user")
    spec = make_spec(tmp_path, goal="")

    async with running(spec) as (driver, heard):
        await heard.until(Ready)

        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.5):
                await driver.deliver(delivery())

    assert Record.read(spec.folder) is None


async def test_a_harness_that_is_gone_refuses_a_delivery(tmp_path, stand):
    spec = make_spec(tmp_path, goal="")

    async with running(spec) as (driver, heard):
        await heard.until(Ready)
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, 9)
        await heard.until(Exited)

        with pytest.raises(DriverError, match="claude is gone"):
            await driver.deliver(delivery())


# Interrupts.


async def test_an_interrupt_ends_the_turn_interrupted_and_says_what_was_queued(tmp_path, stand):
    ended = result(subtype="error_during_execution", is_error=True, terminal_reason="aborted_streaming")
    stand.install(turns=[[STARTED, REQUESTING]], on_interrupt=[ended])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        receipt = await driver.interrupt()
        reason = await heard.until(TurnEnded)

    assert reason == TurnEnded(reason="interrupted")
    assert (receipt.boundary, receipt.queued) == ("turn", ())


async def test_what_stays_queued_past_an_interrupt_is_named_by_its_input(tmp_path, stand):
    stand.install(turns=[[STARTED]], queued_from=1)

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.deliver(delivery())

        receipt = await driver.interrupt()

    assert receipt.queued == ("41",)


async def test_a_turn_that_finished_as_an_interrupt_came_stopped_on_its_own(tmp_path, stand):
    stand.install(turns=[[STARTED]], on_interrupt=[result()])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.interrupt()
        ended = await heard.until(TurnEnded)

    assert ended.reason == "stopped"


async def test_an_interrupt_between_turns_labels_no_later_failure(tmp_path, stand):
    failure = result(is_error=True, terminal_reason="api_error")
    stand.install(turns=[[STARTED, failure]])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        await driver.interrupt()
        await driver.deliver(delivery())
        ended = await heard.until(TurnEnded)

    assert ended.reason == "api_error"


# Approvals.


async def test_an_approval_goes_to_the_runtime_and_its_answer_to_the_harness(tmp_path, stand):
    stand.install(turns=[[STARTED, assistant(using()), asking()]], on_answer=[tool_result(), result()])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "allow")
        decided = await heard.until(Item, lambda item: item.phase == "decided")
        await heard.until(TurnEnded)

    reply = next(frame for frame in stand.heard if frame["type"] == "control_response")["response"]
    assert (asked.id, asked.gist) == ("ask-1", 'Bash {"command": "touch x"}')
    assert (reply["request_id"], reply["subtype"]) == ("ask-1", "success")
    assert reply["response"] == {"behavior": "allow", "updatedInput": {"command": "touch x"}}
    assert (decided.approval, decided.outcome, decided.native_id) == ("ask-1", "completed", "toolu_1")


async def test_a_denial_says_so_and_its_outcome_is_read_from_the_harness(tmp_path, stand):
    stand.install(
        turns=[[STARTED, assistant(using()), asking()]],
        on_answer=[tool_result(text="The runtime denied this.", is_error=True), result()],
    )

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "deny")
        decided = await heard.until(Item, lambda item: item.phase == "decided")

    reply = next(frame for frame in stand.heard if frame["type"] == "control_response")["response"]
    assert reply["response"]["behavior"] == "deny"
    assert decided.outcome == "failed"


async def test_an_approval_the_harness_withdrew_cannot_be_answered(tmp_path, stand):
    withdrawn = {"type": "control_cancel_request", "request_id": "ask-1"}
    stand.install(turns=[[STARTED, asking(), withdrawn, result()]])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await heard.until(TurnEnded)

        with pytest.raises(DriverError, match="no approval ask-1 is waiting"):
            await driver.answer(asked.id, "allow")


# Reconcile.


async def test_reconcile_finds_an_input_in_the_harness_s_own_transcript(tmp_path, stand, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    stand.install(turns=[[STARTED, result()]])
    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        ready = await heard.until(Ready)
        await driver.deliver(delivery())
        await heard.until(TurnEnded)
    assert ready.native
    sent = next(frame for frame in stand.heard if frame["type"] == "user")
    transcript = config / "projects" / "some-project" / f"{ready.native}.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({"type": "user", "uuid": sent["uuid"]}, separators=(",", ":")) + "\n")

    async with running(make_spec(tmp_path, resume=ready.native)) as (driver, heard):
        await heard.until(Ready)

        assert await driver.reconcile("41") == "landed"
        assert await driver.reconcile("42") == "unknown"


async def test_reconcile_with_no_transcript_says_it_does_not_know(tmp_path, stand, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nowhere"))

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)

        assert await driver.reconcile("41") == "unknown"


# Stopping.


async def test_a_stop_interrupts_an_open_turn_and_ends_stdin(tmp_path, stand):
    stand.install(turns=[[STARTED]], exit_on_eof=1)
    spec = make_spec(tmp_path)

    async with running(spec) as (_, heard):
        await heard.until(TurnStarted)

    assert [frame["request"]["subtype"] for frame in stand.heard if frame["type"] == "control_request"][
        -1
    ] == "interrupt"
    assert Record.read(spec.folder) is None


async def test_a_stop_with_no_turn_open_interrupts_nothing(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    assert "interrupt" not in [
        frame["request"]["subtype"] for frame in stand.heard if frame["type"] == "control_request"
    ]


async def test_stopping_twice_or_never_started_is_no_error(tmp_path, stand):
    await ClaudeDriver().stop(GRACE)
    driver = ClaudeDriver()
    await driver.start(make_spec(tmp_path, goal=""), Heard())

    await driver.stop(GRACE)
    await driver.stop(GRACE)


async def test_an_exit_is_reported(tmp_path, stand):
    spec = make_spec(tmp_path, goal="")

    async with running(spec) as (_, heard):
        await heard.until(Ready)
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, 9)

        assert (await heard.until(Exited)).reason == "killed by signal 9"
