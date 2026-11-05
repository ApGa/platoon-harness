"""The `pi` driver, on a stand-in that speaks the real frames: what it launches, and what each frame becomes."""

import asyncio
import contextlib
import json
import os
import stat
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
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
from platoon_harness.drivers.pi import PiDriver, _forgotten
from platoon_harness.tools import SHIM, delivery_heading

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

GRACE = 5.0
FAKE = Path(__file__).with_name("fake_pi.py")
BEGAN = {"type": "agent_start"}
ENDED = {"type": "agent_settled", "aborted": False}
ABORTED = {"type": "agent_settled", "aborted": True}
ZERO = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0}


def usage(tokens: int = 14, usd: float = 0.0, *, billed: bool = False) -> dict[str, Any]:
    cost = {"total": usd, "totalFromProvider": billed}
    return {"input": 11, "output": 3, "cacheRead": 0, "cacheWrite": 0, "totalTokens": tokens, "cost": cost}


def said(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def message_end(*blocks: dict[str, Any], id: str | None = "resp_1", **fields: Any) -> dict[str, Any]:
    message = {"role": "assistant", "content": list(blocks), "model": "m", "stopReason": "stop", "usage": usage()}
    return {"type": "message_end", "message": {**message, **({} if id is None else {"responseId": id}), **fields}}


def user(text: str) -> list[dict[str, Any]]:
    """A user message, as pi says one lands: its start, then its end, once it has written it down."""
    message = {"role": "user", "content": [said(text)]}
    return [{"type": "message_start", "message": message}, {"type": "message_end", "message": message}]


def delta(text: str) -> dict[str, Any]:
    event = {"type": "text_delta", "contentIndex": 0, "delta": text}
    return {"type": "message_update", "usage": usage(), "assistantMessageEvent": event}


def calling(id: str = "call_1", name: str = "bash") -> dict[str, Any]:
    return {"type": "toolCall", "id": id, "name": name, "arguments": {"command": "ls"}}


def tool_began(id: str = "call_1", name: str = "bash") -> dict[str, Any]:
    return {"type": "tool_execution_start", "toolCallId": id, "toolName": name, "args": {"command": "ls"}}


def tool_ended(id: str = "call_1", name: str = "bash", *, failed: bool = False) -> dict[str, Any]:
    result = {"content": [said("the output")], "details": {}}
    return {"type": "tool_execution_end", "toolCallId": id, "toolName": name, "result": result, "isError": failed}


def confirm(id: str = "ask-1", title: str = "call_1", message: str = 'bash {"command":"ls"}') -> dict[str, Any]:
    return {"type": "extension_ui_request", "id": id, "method": "confirm", "title": title, "message": message}


def compaction(first_kept: str = "kept", **result: Any) -> dict[str, Any]:
    done = {"summary": "the summary", "firstKeptEntryId": first_kept, "usage": usage(28), **result}
    return {"type": "compaction_end", "reason": "threshold", "result": done, "aborted": False, "willRetry": False}


def entry(id: str, parent: str | None, kind: str = "message", role: str | None = "user", **fields: Any) -> Any:
    message = {} if role is None else {"message": {"role": role, "content": [said(id)]}}
    return {"type": kind, "id": id, "parentId": parent, **message, **fields}


def delivery(input: str = "41", boundary: str = "turn", text: str = "New message") -> Delivery:
    return Delivery(input=input, boundary=boundary, text=text, items=(Offered(ref="inbox/ada@1", gist="hello"),))


class Stand:
    """A `pi` first on the PATH, and what it wrote down."""

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

    def sent(self, command: str) -> list[dict[str, Any]]:
        return [frame for frame in self.heard if frame["type"] == command]


@pytest.fixture
def stand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Stand:
    folder = tmp_path / "stand"
    folder.mkdir()
    program = folder / "pi"
    script = folder / "script.json"
    program.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "{script}" "$@"\n')
    program.chmod(0o700)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    found = Stand(folder)
    found.install()
    return found


@contextlib.asynccontextmanager
async def running(spec: AgentSpec) -> AsyncIterator[tuple[PiDriver, Heard]]:
    driver, heard = PiDriver(), Heard()
    await driver.start(spec, heard)
    try:
        yield driver, heard
    finally:
        await driver.stop(GRACE)


async def played(stand: Stand, tmp_path: Path, *frames: Any, **script: Any) -> list[Any]:
    """Every report of one turn on the goal, once it ended, after `ready` and `turn.started`."""
    stand.install(turns=[[BEGAN, *frames, ENDED]], **script)
    async with running(make_spec(tmp_path)) as (_, heard):
        await heard.until(TurnEnded)
        return heard.reports[2:]


def kinds(reports: list[Any]) -> list[type]:
    return [type(report) for report in reports]


# What it launches.


async def test_the_launch_is_the_one_path(tmp_path, stand):
    spec = make_spec(tmp_path, model="fake-model", effort="low", goal="")
    stand.install(thinking="low")

    async with running(spec) as (_, heard):
        ready = await heard.until(Ready)

    argv = stand.launch["argv"]
    assert argv[:4] == ["--mode", "rpc", "--session-id", ready.native]
    assert argv[argv.index("--model") + 1] == "fake-model"
    assert argv[argv.index("--thinking") + 1] == "low"
    assert Path(argv[argv.index("-e") + 1]).name == "pi_extension.js"


async def test_a_resume_opens_the_session_it_names_and_takes_no_goal(tmp_path, stand):
    async with running(make_spec(tmp_path, resume="s-1")) as (_, heard):
        ready = await heard.until(Ready)

    assert stand.launch["argv"][:4] == ["--mode", "rpc", "--session", "s-1"]
    assert ready.native == "s-1"
    assert not stand.sent("prompt")


async def test_it_leaves_the_user_s_setup_alone(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    launch = stand.launch
    forbidden = ("--no-extensions", "--no-skills", "--no-context-files", "--no-approve", "--approve", "--no-mcp")
    assert not [flag for flag in launch["argv"] if flag in forbidden or flag == "--session-dir"]
    assert "--append-system-prompt" not in launch["argv"]
    assert "PI_CODING_AGENT_DIR" not in launch["env"]


async def test_what_pi_does_on_its_own_is_left_to_it(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    assert not {"PI_OFFLINE", "PI_TELEMETRY", "PI_SKIP_VERSION_CHECK"} & set(stand.launch["env"])


async def test_what_signs_it_in_comes_from_the_shell_and_a_provider_key_does_not(tmp_path, stand, monkeypatch):
    monkeypatch.setenv("PI_CODING_AGENT_DIR", "/their/agent")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/their/ca.pem")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key-in-the-shell")

    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    env = stand.launch["env"]
    assert env["PI_CODING_AGENT_DIR"] == "/their/agent"
    assert env["HTTPS_PROXY"] == "http://proxy"
    assert env["NODE_EXTRA_CA_CERTS"] == "/their/ca.pem"
    assert "ANTHROPIC_API_KEY" not in env


async def test_our_tools_are_a_server_the_extension_adds_and_the_token_stays_in_the_environment(tmp_path, stand):
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret("tok-1"), namespace="ph", bin=tmp_path)

    async with running(make_spec(tmp_path, goal="", tools=tools)) as (_, heard):
        await heard.until(Ready)

    launch = stand.launch
    config = json.loads(launch["env"]["PLATOON_HARNESS_PI"])
    assert config["namespace"] == "ph"
    assert config["server"] == {
        "command": sys.executable,
        "args": ["-I", str(SHIM)],
        "exposure": "direct",
        "timeout": PiDriver().describe().capabilities.tool_timeout_s,
    }
    assert "tok-1" not in " ".join(launch["argv"])
    assert "tok-1" not in launch["env"]["PLATOON_HARNESS_PI"]
    assert launch["env"]["PLATOON_HARNESS_TOKEN"] == "tok-1"


async def test_access_by_url_is_a_provider_of_the_agent_s_own(tmp_path, stand):
    access = {"OPENAI_BASE_URL": Secret("http://gateway/v1"), "OPENAI_API_KEY": Secret("a-key")}
    stand.install(provider="platoon-harness")

    async with running(make_spec(tmp_path, goal="", model="m", access=access)) as (_, heard):
        await heard.until(Ready)

    launch = stand.launch
    name, provider = json.loads(launch["env"]["PLATOON_HARNESS_PI"])["provider"]
    argv = launch["argv"]
    assert argv[argv.index("--provider") + 1] == name == "platoon-harness"
    assert (provider["baseUrl"], provider["apiKey"]) == ("http://gateway/v1", "$OPENAI_API_KEY")
    assert "a-key" not in launch["env"]["PLATOON_HARNESS_PI"]
    assert provider["models"][0]["id"] == "m"


async def test_a_url_with_no_key_is_refused(tmp_path, stand):
    with pytest.raises(DriverError, match="name one too"):
        await PiDriver().start(make_spec(tmp_path, model="m", access={"OPENAI_BASE_URL": Secret("http://x")}), Heard())


async def test_an_unset_model_on_the_harness_s_own_login_is_its_own_default_and_ready_says_which(tmp_path, stand):
    stand.install(model="the-default")

    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        ready = await heard.until(Ready)

    assert "--model" not in stand.launch["argv"]
    assert ready.effective_model == "the-default"


async def test_an_unset_model_is_refused_where_access_was_given(tmp_path, stand):
    with pytest.raises(DriverError, match="set a model"):
        await PiDriver().start(make_spec(tmp_path, access={"OPENAI_API_KEY": Secret("a-key")}), Heard())


async def test_a_model_named_with_its_provider_reads_as_asked(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="", model="fake/fake-model")) as (_, heard):
        ready = await heard.until(Ready)

    assert ready.effective_model == "fake/fake-model"


async def test_another_model_than_the_one_asked_for_is_said_for_the_host_to_refuse(tmp_path, stand):
    stand.install(model="fake-model-2")

    async with running(make_spec(tmp_path, goal="", model="fake")) as (_, heard):
        ready = await heard.until(Ready)

    assert ready.effective_model == "fake-model-2"


async def test_a_provider_pi_holds_no_login_for_is_refused_and_no_prompt_goes(tmp_path, stand):
    stand.install(available=[], provider="unknown", model="unknown")
    driver = PiDriver()

    with pytest.raises(DriverError, match="no login for unknown"):
        await driver.start(make_spec(tmp_path), Heard())
    await driver.stop(GRACE)

    assert not stand.sent("prompt")


async def test_an_effort_pi_did_not_take_is_refused(tmp_path, stand):
    stand.install(thinking="off")
    driver = PiDriver()

    with pytest.raises(DriverError, match="runs at effort off, and high was asked for"):
        await driver.start(make_spec(tmp_path, effort="high"), Heard())
    await driver.stop(GRACE)


async def test_a_harness_that_is_not_installed_fails_its_start_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(DriverError, match="pi is not an executable"):
        await PiDriver().start(make_spec(tmp_path), Heard())


async def test_a_session_nobody_can_find_says_where_to_look(tmp_path, stand):
    stand.install(exit_at_once=1, stderr="No session found matching 's-1'")
    driver = PiDriver()

    with pytest.raises(DriverError, match=r"pi is gone: see .*stderr\.log"):
        await driver.start(make_spec(tmp_path, resume="s-1"), Heard())
    await driver.stop(GRACE)


async def test_a_refused_goal_fails_the_start_with_what_pi_said(tmp_path, stand):
    stand.install(refuses={"prompt": "No API key found"})
    driver = PiDriver()

    with pytest.raises(DriverError, match="No API key found"):
        await driver.start(make_spec(tmp_path), Heard())
    await driver.stop(GRACE)


# What `describe` asks.


def settled_on(home: Path, monkeypatch: pytest.MonkeyPatch, provider: str | None) -> None:
    (home / ".pi" / "agent").mkdir(parents=True)
    settings = {} if provider is None else {"defaultProvider": provider}
    (home / ".pi" / "agent" / "settings.json").write_text(json.dumps(settings))
    monkeypatch.setenv("HOME", str(home))


@pytest.mark.parametrize(("kind", "login"), [("oauth", "plan"), ("api_key", "key"), ("other", None)])
def test_the_login_kind_comes_from_the_harness_s_own_check(tmp_path, stand, monkeypatch, kind, login):
    settled_on(tmp_path / "home", monkeypatch, "openai")
    stand.install(status=json.dumps({"status": "ready", "provider": "openai", "authType": kind}))

    assert PiDriver().describe().login == login

    asked = json.loads(stand.script.with_suffix(".status").read_text())
    assert asked == ["auth", "check", "--provider", "openai", "--json", "--no-refresh"]


def test_it_reads_the_settings_of_the_agent_directory_the_shell_names(tmp_path, stand, monkeypatch):
    settled_on(tmp_path / "home", monkeypatch, "openai")
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "home" / ".pi" / "agent"))
    monkeypatch.setenv("HOME", str(tmp_path))
    stand.install(status=json.dumps({"status": "ready", "authType": "api_key"}))

    assert PiDriver().describe().login == "key"


def test_with_no_default_provider_it_cannot_tell_and_asks_nothing(tmp_path, stand, monkeypatch):
    settled_on(tmp_path / "home", monkeypatch, None)

    assert PiDriver().describe().login is None
    assert not stand.script.with_suffix(".status").exists()


def test_with_no_settings_it_cannot_tell(tmp_path, stand, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert PiDriver().describe().login is None


def test_a_status_that_says_nothing_readable_is_no_login_we_know_of(tmp_path, stand, monkeypatch):
    settled_on(tmp_path / "home", monkeypatch, "openai")
    stand.install(status="not json")

    assert PiDriver().describe().login is None


def test_a_status_that_hangs_is_cut_short(tmp_path, stand, monkeypatch):
    settled_on(tmp_path / "home", monkeypatch, "openai")
    monkeypatch.setattr("platoon_harness.drivers.process._STATUS_SECONDS", 0.1)
    stand.install(status_seconds=5)

    assert PiDriver().describe().login is None


def test_a_harness_that_is_not_installed_describes_no_login(tmp_path, monkeypatch):
    settled_on(tmp_path / "home", monkeypatch, "openai")
    monkeypatch.setenv("PATH", str(tmp_path))

    assert PiDriver().describe().login is None


def test_describing_answers_alike_and_declares_what_ran(stand):
    driver = PiDriver()

    assert driver.describe() == driver.describe()
    capabilities = driver.describe().capabilities
    assert capabilities.boundaries == {"turn", "model_call"}
    assert capabilities.approvals == "gated"
    assert capabilities.tool_paths == {"mcp-stdio"}
    assert capabilities.native_children == "none"
    assert not stand.script.with_suffix(".launch").exists()


# What each frame becomes.


async def test_ready_says_what_was_observed(tmp_path, stand):
    stand.install(version="1.5.0", model="m")

    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        ready = await heard.until(Ready)

    assert (ready.version, ready.effective_model, ready.tools_visible) == ("1.5.0", "m", None)


async def test_a_turn_with_text_reports_its_call_its_words_and_what_it_spent(tmp_path, stand):
    reports = await played(stand, tmp_path, delta("hello "), message_end(said("hello there")))

    assert kinds(reports) == [Delta, ModelCall, Usage, Item, TurnEnded]
    call, spent, item = reports[1], reports[2], reports[3]
    assert (call.call_id, call.model, call.purpose) == ("resp_1", "m", None)
    assert (spent.tokens, spent.label, spent.scope, spent.call_id) == (14, "provider", "call", "resp_1")
    assert (item.kind, item.phase, item.body, item.call_id) == ("message", None, "hello there", "resp_1")
    assert reports[-1].reason == "stopped"


async def test_a_turn_is_one_from_the_first_start_to_settled_however_many_runs_it_took(tmp_path, stand):
    frames = [{"type": "agent_end", "willRetry": True}, BEGAN, message_end(said("x")), {"type": "agent_end"}]
    stand.install(turns=[[BEGAN, *frames, ENDED]])

    async with running(make_spec(tmp_path)) as (_, heard):
        await heard.until(TurnEnded)

    assert len(heard.of(TurnStarted)) == 1


async def test_a_call_a_price_stands_behind_is_estimated_in_dollars(tmp_path, stand):
    reports = await played(stand, tmp_path, message_end(usage=usage(usd=0.25)))
    money = [report for report in reports if isinstance(report, Usage) and report.usd is not None]

    assert [(usage.usd, usage.label, usage.call_id) for usage in money] == [(0.25, "estimated", "resp_1")]


async def test_a_call_the_provider_billed_says_so(tmp_path, stand):
    reports = await played(stand, tmp_path, message_end(usage=usage(usd=0.25, billed=True)))
    money = [report for report in reports if isinstance(report, Usage) and report.usd is not None]

    assert [(usage.usd, usage.label) for usage in money] == [(0.25, "provider")]


async def test_a_free_call_the_provider_billed_is_zero_and_an_unpriced_one_is_unknown(tmp_path, stand):
    billed = await played(stand, tmp_path, message_end(usage=usage(billed=True)))
    unpriced = await played(stand, tmp_path, message_end())

    assert [report.usd for report in billed if isinstance(report, Usage) and report.usd is not None] == [0.0]
    assert [report.usd for report in unpriced if isinstance(report, Usage) and report.usd is not None] == []


async def test_a_zero_on_a_call_nobody_heard_is_unknown(tmp_path, stand):
    reports = await played(stand, tmp_path, message_end(id=None, usage=ZERO, stopReason="aborted"), ABORTED)
    usages = [report for report in reports if isinstance(report, Usage)]

    assert [(usage.tokens, usage.label, usage.call_id) for usage in usages] == [(None, "unavailable", None)]


async def test_a_call_that_names_no_response_has_no_id(tmp_path, stand):
    reports = await played(stand, tmp_path, message_end(id=None))

    assert [report.call_id for report in reports if isinstance(report, ModelCall)] == [None]


async def test_a_tool_is_started_then_completed_under_the_call_that_made_it(tmp_path, stand):
    frames = (message_end(calling()), tool_began(), tool_ended())
    reports = await played(stand, tmp_path, *frames)
    started, completed = (report for report in reports if isinstance(report, Item))

    assert (started.kind, started.phase, started.native_id, started.call_id) == ("tool", "started", "call_1", "resp_1")
    assert (completed.phase, completed.outcome, completed.body) == ("completed", "completed", "the output")
    assert completed.gist == "bash completed"


async def test_a_tool_that_failed_says_so(tmp_path, stand):
    reports = await played(stand, tmp_path, tool_began(), tool_ended(failed=True))

    assert [report.outcome for report in reports if isinstance(report, Item)][-1] == "failed"


async def test_a_tool_no_model_call_named_has_no_call_id(tmp_path, stand):
    reports = await played(stand, tmp_path, tool_began())

    assert next(report for report in reports if isinstance(report, Item)).call_id is None


async def test_an_empty_thought_is_no_thought_and_a_real_one_is_kept(tmp_path, stand):
    empty, real = {"type": "thinking", "thinking": ""}, {"type": "thinking", "thinking": "hm"}
    reports = await played(stand, tmp_path, message_end(empty, real))

    assert [report.body for report in reports if isinstance(report, Item)] == ["hm"]


async def test_a_long_message_has_a_short_gist_and_a_whole_body(tmp_path, stand):
    reports = await played(stand, tmp_path, message_end(said("x" * 5000)))
    item = next(report for report in reports if isinstance(report, Item))

    assert (len(item.gist), len(item.body or "")) == (280, 5000)


async def test_a_turn_that_failed_says_what_went_wrong(tmp_path, stand):
    failed = message_end(stopReason="error", errorMessage="529 overloaded")
    reports = await played(stand, tmp_path, failed)

    assert reports[-1].reason == "529 overloaded"


async def test_a_retry_that_worked_leaves_no_failure(tmp_path, stand):
    failed = message_end(stopReason="error", errorMessage="529 overloaded")
    retry = {"type": "auto_retry_start", "attempt": 1, "maxAttempts": 3, "delayMs": 1, "errorMessage": "529"}
    reports = await played(stand, tmp_path, failed, retry, message_end(said("fine")))

    assert reports[-1].reason == "stopped"
    assert not [report for report in reports if isinstance(report, Native)]


async def test_frames_with_nothing_for_us_say_nothing(tmp_path, stand):
    quiet = (
        {"type": "turn_start"},
        {"type": "turn_end", "message": {}, "toolResults": []},
        {"type": "message_start", "message": {"role": "system", "content": "", "sections": {}}},
        {"type": "message_end", "message": {"role": "user", "content": []}},
        {"type": "message_end", "message": {"role": "toolResult", "content": []}},
        {"type": "queue_update", "steering": [], "followUp": []},
        {"type": "compaction_start", "reason": "threshold"},
        {"type": "tool_execution_update", "toolCallId": "call_1", "partialResult": {}},
        {"type": "extension_ui_request", "id": "1", "method": "setStatus", "statusKey": "x"},
        {"type": "extension_ui_request", "id": "2", "method": "notify", "message": "fyi", "notifyType": "info"},
    )
    reports = await played(stand, tmp_path, *quiet)

    assert kinds(reports) == [TurnEnded]


async def test_a_warning_nobody_is_there_to_read_is_native_plus_a_gap(tmp_path, stand):
    notice = {"type": "extension_ui_request", "id": "1", "method": "notify", "notifyType": "warning"}
    reports = await played(stand, tmp_path, {**notice, "message": "MCP servers need attention: ph failed"})

    assert kinds(reports) == [Native, GapReport, TurnEnded]
    assert reports[0].kind == "notify"
    assert "ph failed" in reports[0].raw


@pytest.mark.parametrize(
    "frame",
    ["this is no frame", {"type": "nobody_knows"}, {"nothing": 1}, {"type": "response", "command": "parse"}, [1]],
)
async def test_an_unknown_frame_is_native_plus_a_gap(tmp_path, stand, frame):
    reports = await played(stand, tmp_path, frame)

    assert kinds(reports) == [Native, GapReport, TurnEnded]
    assert reports[1].what == "unknown_update"


@pytest.mark.parametrize(
    "frame",
    [
        {"type": "tool_execution_end", "toolCallId": "call_1", "result": "no mapping"},
        {"type": "message_start", "message": {"role": "user", "content": [1]}},
        {"type": "extension_ui_request", "id": 1, "method": "confirm", "title": 2},
    ],
)
async def test_a_frame_of_a_known_type_that_does_not_read_is_native_too(tmp_path, stand, frame):
    reports = await played(stand, tmp_path, frame)

    assert kinds(reports) == [Native, GapReport, TurnEnded]
    assert reports[0].kind == frame["type"]


async def test_a_block_nobody_knows_is_native_too(tmp_path, stand):
    reports = await played(stand, tmp_path, message_end({"type": "hologram"}))

    assert Native in kinds(reports)


async def test_a_credential_in_an_unknown_frame_is_masked(tmp_path, stand):
    stand.install(turns=[[BEGAN, {"type": "nobody_knows", "said": "tok-1"}, ENDED]])
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret("tok-1"), namespace="ph", bin=tmp_path)

    async with running(make_spec(tmp_path, tools=tools)) as (_, heard):
        native = await heard.until(Native)

    assert "tok-1" not in native.raw


# What it hands over.


async def test_a_delivery_lands_as_a_turn(tmp_path, stand):
    stand.install(turns=[[BEGAN, *user("New message"), message_end(), ENDED]])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await driver.deliver(delivery())
        delivered = await heard.until(InputDelivered)

    assert (delivered.input, delivered.boundary, delivered.evidence) == ("41", "turn", "message_start")
    assert stand.sent("prompt")[0]["message"] == "New message"


async def test_a_delivery_lands_as_the_entry_pi_wrote_it_down_as(tmp_path, stand):
    """Pi names an entry only when asked, so the driver asks for what is new since the last one it saw."""
    stand.install(turns=[[BEGAN, *user("New message"), message_end(), ENDED], [*user("again"), ENDED]])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await driver.deliver(delivery())
        await heard.until(TurnEnded)
        await driver.deliver(delivery("42", text="again"))
        await heard.until(InputDelivered, lambda delivered: delivered.input == "42")

    assert [(landed.input, landed.native_id) for landed in heard.of(InputDelivered)] == [
        ("41", "entry-1"),
        ("42", "entry-2"),
    ]
    assert [frame.get("since") for frame in stand.sent("get_entries")] == [None, "entry-1"]


async def test_what_pi_says_after_an_input_lands_waits_behind_it_in_pi_s_order(tmp_path, stand):
    """The stand-in says the whole turn before it reads the driver's question, as a fast model can."""
    call = message_end(calling(), id="resp_1")
    stand.install(turns=[[BEGAN, *user("New message"), call, tool_began(), tool_ended(), ENDED]])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await driver.deliver(delivery())
        await heard.until(TurnEnded)

    assert kinds(heard.reports[1:5]) == [TurnStarted, InputDelivered, ModelCall, Usage]
    assert heard.of(InputDelivered)[0].native_id == "entry-1"


def replaced(text: str) -> list[dict[str, Any]]:
    """A user message whose end an extension of the user's replaced, so pi writes down other text than it began with."""
    started, _ = user(text)
    return [started, user("what an extension made of it")[1]]


@pytest.mark.parametrize(
    ("frames", "script"),
    [
        (user("New message"), {"refuses": {"get_entries": "no"}}),
        (user("New message"), {"gone_at": "get_entries"}),
        (replaced("New message"), {}),
    ],
)
async def test_an_input_whose_entry_pi_never_names_lands_with_no_id_in_its_place(tmp_path, stand, frames, script):
    stand.install(turns=[[BEGAN, *frames, message_end(), ENDED]], **script)

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await driver.deliver(delivery())
        await heard.until(ModelCall)

    assert kinds(heard.reports[1:4]) == [TurnStarted, InputDelivered, ModelCall]
    assert heard.of(InputDelivered)[0].native_id is None


async def test_a_delivery_inside_a_turn_lands_before_the_next_model_call(tmp_path, stand):
    stand.install(turns=[[BEGAN, *user("the goal"), message_end()], [*user("steered"), message_end(), ENDED]])

    async with running(make_spec(tmp_path, goal="the goal")) as (driver, heard):
        await driver.deliver(delivery(boundary="model_call", text="steered"))
        delivered = await heard.until(InputDelivered, lambda delivered: delivered.input != "launch")

    assert delivered.boundary == "model_call"
    assert len(heard.of(TurnStarted)) == 1


@pytest.mark.parametrize("boundary", ["turn", "model_call"])
async def test_one_way_in_either_begins_a_turn_or_queues_in_one(tmp_path, stand, boundary):
    async with running(make_spec(tmp_path, goal="")) as (driver, _):
        await driver.deliver(delivery(boundary=boundary))

    assert stand.sent("prompt")[0]["streamingBehavior"] == "steer"


async def test_a_delivery_pi_refused_says_why_and_stays_on_nobody_s_list(tmp_path, stand):
    stand.install(refuses={"prompt": "the key is tok-1"})
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret("tok-1"), namespace="ph", bin=tmp_path)

    async with running(make_spec(tmp_path, goal="", tools=tools)) as (driver, _):
        with pytest.raises(DriverError, match=r"the key is \*\*\*"):
            await driver.deliver(delivery())
        await driver.interrupt()


async def test_an_input_an_extension_took_reached_no_model_and_says_so(tmp_path, stand):
    stand.install(disposition="handled")

    async with running(make_spec(tmp_path, goal="")) as (driver, _):
        with pytest.raises(DriverError, match="reached no model"):
            await driver.deliver(delivery())


async def test_a_harness_that_is_gone_refuses_a_delivery(tmp_path, stand):
    stand.install(turns=[[BEGAN]])
    spec = make_spec(tmp_path)

    async with running(spec) as (driver, heard):
        driver._process.stdin.close()
        await heard.until(Exited)
        with pytest.raises(DriverError, match="pi is gone"):
            await driver.deliver(delivery())


async def test_a_harness_that_stopped_reading_holds_up_a_delivery_and_no_stop(tmp_path, stand):
    stand.install(deaf_to="abort")

    async with running(make_spec(tmp_path, goal="")) as (driver, _):
        waiting = asyncio.create_task(driver.interrupt())
        await asyncio.sleep(0)

    with pytest.raises(DriverError, match="pi is gone"):
        await waiting


# Interrupts, and what they leave.


async def test_an_interrupt_ends_the_turn_interrupted_and_says_what_was_queued(tmp_path, stand):
    stand.install(turns=[[BEGAN, *user("the goal")]], after_abort=[ABORTED])

    async with running(make_spec(tmp_path, goal="the goal")) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.deliver(delivery("41", "model_call", "queued"))
        await driver.interrupt()
        ended = await heard.until(TurnEnded)

    assert ended.reason == "interrupted"


async def test_what_an_interrupt_stranded_is_cleared_from_its_queue_for_the_runtime_to_offer_again(tmp_path, stand):
    stand.install(turns=[[BEGAN, *user("the goal")], []], after_abort=[ABORTED])

    async with running(make_spec(tmp_path, goal="the goal")) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.deliver(delivery("41", "model_call", "queued"))
        await driver.interrupt()
        await heard.until(TurnEnded)

    types = [frame["type"] for frame in stand.heard]
    assert types.index("abort") < types.index("clear_queue")
    assert [frame["message"] for frame in stand.sent("prompt")] == ["the goal", "queued"]
    assert [landed.input for landed in heard.of(InputDelivered)] == ["launch"]


async def test_what_a_failed_turn_stranded_is_cleared_too(tmp_path, stand):
    failed = message_end(stopReason="error", errorMessage="boom")
    stand.install(turns=[[BEGAN, *user("the goal")], [failed, ENDED]])

    async with running(make_spec(tmp_path, goal="the goal")) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.deliver(delivery("41", "model_call", "queued"))
        await heard.until(TurnEnded)

    assert heard.of(TurnEnded)[0].reason == "boom"
    assert len(stand.sent("prompt")) == 2


async def test_a_turn_that_ended_on_its_own_clears_nothing(tmp_path, stand):
    stand.install(turns=[[BEGAN, *user("the goal")], [*user("queued"), message_end(), ENDED]])

    async with running(make_spec(tmp_path, goal="the goal")) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.deliver(delivery("41", "model_call", "queued"))
        await heard.until(TurnEnded)

    assert not stand.sent("clear_queue")


async def test_an_interrupt_cancels_a_dialog_that_would_hold_it_up(tmp_path, stand):
    stand.install(turns=[[BEGAN, tool_began(), confirm(title="their question")]], after_abort=[ABORTED])

    async with running(make_spec(tmp_path, goal="go")) as (driver, heard):
        await heard.until(ApprovalRequested)
        await driver.interrupt()
        await heard.until(TurnEnded)

    answered = stand.sent("extension_ui_response")
    assert answered == [{"type": "extension_ui_response", "id": "ask-1", "cancelled": True}]


# Approvals.


async def test_an_approval_goes_to_the_runtime_and_its_answer_to_the_harness(tmp_path, stand):
    stand.install(turns=[[BEGAN, message_end(calling()), tool_began(), confirm()]], on_answer=[tool_ended(), ENDED])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "allow")
        decided = await heard.until(Item, lambda item: item.approval is not None)
        await heard.until(TurnEnded)

    assert (asked.id, asked.gist) == ("ask-1", 'bash {"command":"ls"}')
    assert stand.sent("extension_ui_response")[0]["confirmed"] is True
    assert (decided.approval, decided.outcome, decided.native_id) == ("ask-1", "completed", "call_1")


async def test_a_denial_says_so_and_its_outcome_is_read_from_the_harness(tmp_path, stand):
    stand.install(turns=[[BEGAN, tool_began(), confirm()]], on_answer=[tool_ended(failed=True), ENDED])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "deny")
        decided = await heard.until(Item, lambda item: item.approval is not None)

    assert stand.sent("extension_ui_response")[0]["confirmed"] is False
    assert decided.outcome == "failed"


async def test_a_confirm_of_a_user_s_own_is_an_approval_with_no_tool_behind_it(tmp_path, stand):
    stand.install(turns=[[BEGAN, confirm(title="Clear session?", message="All will be lost.")]], on_answer=[ENDED])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "allow")
        await heard.until(TurnEnded)

    assert asked.gist == "Clear session? All will be lost."
    assert not [item for item in heard.of(Item) if item.approval is not None]


async def test_a_confirm_with_no_title_is_asked_all_the_same(tmp_path, stand):
    frame = {"type": "extension_ui_request", "id": "ask-1", "method": "confirm", "message": "may it?"}
    stand.install(turns=[[BEGAN, frame, ENDED]])

    async with running(make_spec(tmp_path)) as (_, heard):
        asked = await heard.until(ApprovalRequested)

    assert asked.gist == "may it?"


async def test_an_approval_nobody_is_waiting_on_is_refused(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (driver, _):
        with pytest.raises(DriverError, match="no approval x is waiting"):
            await driver.answer("x", "allow")


async def test_an_approval_goes_moot_with_its_turn(tmp_path, stand):
    stand.install(turns=[[BEGAN, confirm(), ENDED]])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await heard.until(TurnEnded)
        with pytest.raises(DriverError, match="is waiting"):
            await driver.answer(asked.id, "allow")


@pytest.mark.parametrize("method", ["select", "input", "editor"])
async def test_a_dialog_a_verdict_cannot_answer_is_cancelled_so_pi_does_not_wait(tmp_path, stand, method):
    frame = {"type": "extension_ui_request", "id": "d-1", "method": method, "title": "Pick"}
    stand.install(turns=[[BEGAN, frame, ENDED]])

    async with running(make_spec(tmp_path)) as (_, heard):
        native = await heard.until(Native)
        await heard.until(TurnEnded)

    assert native.kind == f"extension_ui_request/{method}"
    assert {"type": "extension_ui_response", "id": "d-1", "cancelled": True} in stand.heard


# Compaction.


async def test_a_compaction_is_a_model_call_with_a_purpose_and_names_what_left(tmp_path, stand):
    entries = [
        entry("system", None, role="system"),
        entry("u1", "system"),
        entry("a1", "u1", role="assistant"),
        entry("kept", "a1"),
        entry("c1", "kept", "compaction", role=None, firstKeptEntryId="kept"),
    ]
    stand.install(turns=[[BEGAN, compaction(), ENDED]], entries=entries, leaf="c1")

    async with running(make_spec(tmp_path)) as (_, heard):
        compacted = await heard.until(Compacted)

    called = heard.of(ModelCall)[0]
    spent = heard.of(Usage)[0]
    assert (called.purpose, called.call_id) == ("compaction", None)
    assert (spent.tokens, spent.label, spent.call_id) == (28, "provider", None)
    assert (compacted.forgotten, compacted.summary) == (("u1", "a1"), "the summary")


async def test_what_cannot_be_named_stays_unknown_and_the_summary_is_kept(tmp_path, stand):
    stand.install(turns=[[BEGAN, compaction(), ENDED]], refuses={"get_entries": "no"})

    async with running(make_spec(tmp_path)) as (_, heard):
        compacted = await heard.until(Compacted)

    assert (compacted.forgotten, compacted.summary) == (None, "the summary")


async def test_a_compaction_whose_listing_does_not_read_is_still_reported(tmp_path, stand):
    stand.install(turns=[[BEGAN, compaction(), ENDED]], entries=[5], leaf="c1")

    async with running(make_spec(tmp_path)) as (_, heard):
        compacted = await heard.until(Compacted)

    assert compacted.forgotten is None


async def test_a_compaction_keeps_its_place_before_an_input_that_landed_after_it(tmp_path, stand):
    """Pi names what a compaction forgot only when asked, and an input may land before it answers: the compaction waits
    in its place, so no report says a handover that came after it was there for it to keep."""
    entries = [
        entry("u1", None),
        entry("kept", "u1"),
        entry("c1", "kept", "compaction", role=None, firstKeptEntryId="kept"),
    ]
    stand.install(turns=[[BEGAN, compaction(), *user("New message"), message_end(), ENDED]], entries=entries, leaf="c1")

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await driver.deliver(delivery())
        await heard.until(TurnEnded)

    assert kinds(heard.reports[1:9]) == [
        TurnStarted,
        ModelCall,
        Usage,
        Compacted,
        InputDelivered,
        ModelCall,
        Usage,
        TurnEnded,
    ]
    assert heard.of(Compacted)[0].forgotten == ("u1",)
    assert heard.of(InputDelivered)[0].native_id == "entry-4"


async def test_what_waits_on_an_answer_pi_never_gives_goes_on_as_it_is_known_before_the_exit(tmp_path, stand):
    stand.install(turns=[[BEGAN, compaction(), *user("New message"), message_end()]], gone_at="get_entries")

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await driver.deliver(delivery())
        await heard.until(Exited)

    assert kinds(heard.reports[1:]) == [
        TurnStarted,
        ModelCall,
        Usage,
        Compacted,
        InputDelivered,
        ModelCall,
        Usage,
        Exited,
    ]
    assert (heard.of(Compacted)[0].forgotten, heard.of(InputDelivered)[0].native_id) == (None, None)


async def test_a_run_pi_aborted_with_nobody_interrupting_reads_as_aborted(tmp_path, stand):
    reports = await played(stand, tmp_path, ABORTED)

    assert reports[-1] == TurnEnded(reason="aborted")


async def test_an_interrupt_that_found_no_turn_labels_no_later_abort(tmp_path, stand):
    stand.install(turns=[[BEGAN, *user("go"), ABORTED]])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        await driver.interrupt()
        await driver.deliver(delivery("41", "turn", "go"))
        ended = await heard.until(TurnEnded)

    assert ended.reason == "aborted"


async def test_a_compaction_that_came_to_nothing_spent_what_nobody_can_say(tmp_path, stand):
    failed = {"type": "compaction_end", "reason": "threshold", "aborted": False, "errorMessage": "boom"}
    reports = await played(stand, tmp_path, failed)

    assert kinds(reports) == [ModelCall, Usage, TurnEnded]
    assert (reports[1].tokens, reports[1].label) == (None, "unavailable")


def test_what_left_starts_where_the_compaction_before_kept():
    entries = [
        entry("u1", None),
        entry("a1", "u1", role="assistant"),
        entry("c1", "a1", "compaction", role=None, firstKeptEntryId="a1"),
        entry("u2", "c1"),
        entry("a2", "u2", role="assistant"),
        entry("c2", "a2", "compaction", role=None, firstKeptEntryId="a2"),
    ]

    assert _forgotten(entries, "c2", "a1") == ("u1",)
    assert _forgotten(entries, "c2", "a2") == ("a1", "u2")


def test_what_left_is_on_the_branch_that_is_live():
    entries = [
        entry("u1", None),
        entry("abandoned", "u1", role="assistant"),
        entry("a1", "u1", role="assistant"),
        entry("kept", "a1"),
        entry("c1", "kept", "compaction", role=None, firstKeptEntryId="kept"),
    ]

    assert _forgotten(entries, "c1", "kept") == ("u1", "a1")


def test_a_position_nobody_can_find_is_unknown():
    entries = [entry("u1", None), entry("c1", "u1", "compaction", role=None, firstKeptEntryId="gone")]

    assert _forgotten(entries, "c1", "gone") is None


# After a crash.


def said_entries(*texts: str) -> list[dict[str, Any]]:
    message = lambda text: {"message": {"role": "user", "content": [said(text)]}}  # noqa: E731
    return [entry(f"e{index}", None) | message(text) for index, text in enumerate(texts)]


async def test_an_input_in_the_session_s_entries_landed(tmp_path, stand):
    stand.install(entries=said_entries(f"{delivery_heading(41)}\n- inbox/ada@3 from @lead: hello"))

    async with running(make_spec(tmp_path, resume="s-1")) as (driver, heard):
        await heard.until(Ready)
        assert await driver.reconcile("41") == "landed"


async def test_an_id_not_in_the_session_s_entries_is_unknown_as_it_may_be_an_approval_s(tmp_path, stand):
    stand.install(entries=said_entries(f"{delivery_heading(411)}\n- inbox/ada@3 from @lead: hello", "some goal"))

    async with running(make_spec(tmp_path, resume="s-1")) as (driver, heard):
        await heard.until(Ready)
        assert await driver.reconcile("41") == "unknown"
        assert await driver.reconcile("approval-7") == "unknown"


async def test_an_answer_that_cannot_be_had_is_no_verdict_on_an_input(tmp_path, stand):
    stand.install(refuses={"get_entries": "no"})

    async with running(make_spec(tmp_path, resume="s-1")) as (driver, heard):
        await heard.until(Ready)
        with pytest.raises(DriverError):
            await driver.reconcile("41")


# Ending.


async def test_a_stop_asks_by_ending_stdin_first(tmp_path, stand):
    spec = make_spec(tmp_path, goal="")

    async with running(spec) as (_, heard):
        await heard.until(Ready)
    exited = await heard.until(Exited)

    assert exited.reason == "exited with code 0"
    assert not heard.of(GapReport)


async def test_a_harness_that_outlives_stdin_is_termed(tmp_path, stand):
    stand.install(outlives_stdin=True)
    driver, heard = PiDriver(), Heard()
    await driver.start(make_spec(tmp_path, goal=""), heard)
    await heard.until(Ready)

    await driver.stop(0.1)

    exited = await heard.until(Exited)
    assert exited.reason == "killed by signal 15"
    assert not heard.of(GapReport)


async def test_a_stop_that_comes_to_a_kill_reports_the_crash_window(tmp_path, stand):
    """A tool leads a group of its own, and pi gets no chance to end it, so what runs on is a gap."""
    stand.install(outlives_stdin=True, ignores_term=True)
    driver, heard = PiDriver(), Heard()
    await driver.start(make_spec(tmp_path, goal=""), heard)
    await heard.until(Ready)

    await driver.stop(0.2)

    assert (await heard.until(GapReport)).what == "crash_window"
    assert (await heard.until(Exited)).reason == "killed by signal 9"


async def test_a_stop_before_a_start_does_nothing(tmp_path):
    await PiDriver().stop(GRACE)


async def test_the_instructions_are_in_a_file_only_this_user_can_read(tmp_path, stand):
    spec = make_spec(tmp_path, goal="", instructions="the preamble")

    async with running(spec) as (_, heard):
        await heard.until(Ready)
        path = Path(json.loads(stand.launch["env"]["PLATOON_HARNESS_PI"])["instructions"])
        assert path.read_text() == "the preamble"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
