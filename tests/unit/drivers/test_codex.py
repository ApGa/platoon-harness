"""The `codex` driver, on a stand-in that speaks the real frames: what it opens, and what each frame becomes."""

import asyncio
import contextlib
import json
import os
import signal
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

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
from platoon_harness.drivers.codex import CodexDriver
from platoon_harness.tools.ph import TOKEN_VARIABLE

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

GRACE = 5.0
FAKE = Path(__file__).with_name("fake_codex.py")
KEYED = [
    "app-server",
    "-c",
    'model_provider="platoon-harness"',
    "-c",
    'model_providers.platoon-harness={name="platoon-harness", env_key="OPENAI_API_KEY", wire_api="responses"}',
]
URL = "model_providers.platoon-harness.base_url"


def notice(method: str, **params: Any) -> dict[str, Any]:
    return {"method": method, "params": {"threadId": "$thread", **params}}


def began(turn: str = "$turn", thread: str = "$thread") -> dict[str, Any]:
    return {"method": "turn/started", "params": {"threadId": thread, "turn": {"id": turn}}}


def ended(status: str = "completed", turn: str = "$turn", thread: str = "$thread", **fields: Any) -> dict[str, Any]:
    return {
        "method": "turn/completed",
        "params": {"threadId": thread, "turn": {"id": turn, "status": status, **fields}},
    }


def started(type: str, id: str = "item-1", thread: str = "$thread", **fields: Any) -> dict[str, Any]:
    return notice("item/started", threadId=thread, item={"type": type, "id": id, **fields})


def completed(type: str, id: str = "item-1", thread: str = "$thread", **fields: Any) -> dict[str, Any]:
    return notice("item/completed", threadId=thread, item={"type": type, "id": id, **fields})


def used(total: int, thread: str = "$thread", last: int = 1) -> dict[str, Any]:
    usage = {"total": {"totalTokens": total}, "last": {"totalTokens": last}}
    return notice("thread/tokenUsage/updated", threadId=thread, tokenUsage=usage)


def landed(input: str, id: str = "user-1") -> dict[str, Any]:
    return started("userMessage", id, clientId=input)


def asking(method: str = "item/commandExecution/requestApproval", id: int = 0, **params: Any) -> dict[str, Any]:
    fields = {"threadId": "$thread", "turnId": "$turn", "itemId": "item-1", "command": "touch x", **params}
    return {"method": method, "id": id, "params": fields}


def delivery(input: str = "41", boundary: str = "turn") -> Delivery:
    item = Offered(ref="inbox/ada@1", gist="hello")
    return Delivery(input=input, boundary=boundary, text=f"text of {input}", items=(item,))


class Stand:
    """A `codex` first on the PATH, and what it wrote down."""

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

    def asked(self, method: str) -> dict[str, Any]:
        return next(frame["params"] for frame in self.heard if frame.get("method") == method)

    def answers(self) -> list[dict[str, Any]]:
        return [frame for frame in self.heard if "method" not in frame]


@pytest.fixture
def stand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Stand:
    folder = tmp_path / "stand"
    folder.mkdir()
    program = folder / "codex"
    script = folder / "script.json"
    program.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "{script}" "$@"\n')
    program.chmod(0o700)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    found = Stand(folder)
    found.install()
    return found


@contextlib.asynccontextmanager
async def running(spec: AgentSpec) -> AsyncIterator[tuple[CodexDriver, Heard]]:
    driver, heard = CodexDriver(), Heard()
    await driver.start(spec, heard)
    try:
        yield driver, heard
    finally:
        await driver.stop(GRACE)


async def played(stand: Stand, tmp_path: Path, *frames: Any) -> list[Any]:
    """Every report of one turn on the goal, once it ended."""
    stand.install(turns=[[began(), *frames, ended()]])
    async with running(make_spec(tmp_path)) as (_, heard):
        await heard.until(TurnEnded)
        return heard.reports[1:]


def binding(tmp_path: Path) -> ToolBinding:
    return ToolBinding(
        url="http://127.0.0.1:1/mcp?surface=mcp__ph", token=Secret("tok-1"), namespace="ph", bin=tmp_path
    )


# What it opens.


async def test_the_launch_is_the_one_path_and_every_approval_comes_to_the_runtime(tmp_path, stand):
    spec = make_spec(tmp_path, model="fake-model", tools=binding(tmp_path), instructions="the preamble")

    async with running(spec) as (_, heard):
        ready = await heard.until(Ready)
        thread = stand.asked("thread/start")

    assert stand.launch["argv"] == ["app-server"]
    assert [frame.get("method") for frame in stand.heard[:4]] == [
        "initialize",
        "initialized",
        "config/read",
        "thread/start",
    ]
    assert stand.asked("initialize")["clientInfo"]["name"] == "platoon_harness"
    assert "jsonrpc" not in stand.heard[0]
    assert thread["approvalPolicy"] == "on-request"
    assert thread["approvalsReviewer"] == "user"
    assert thread["model"] == "fake-model"
    assert thread["developerInstructions"] == "the preamble"
    assert thread["config"]["mcp_servers"] == {
        "ph": {
            "url": "http://127.0.0.1:1/mcp?surface=mcp__ph",
            "bearer_token_env_var": TOKEN_VARIABLE,
            "default_tools_approval_mode": "approve",
            "required": True,
            "omit_tools_from": ["deferred"],
        }
    }
    assert thread["config"]["agents"] == {"enabled": False}
    assert (ready.native, ready.version, ready.effective_model) == ("thread-1", "9.9.9", "fake-model")
    assert ready.tools_visible is None


async def test_the_tool_token_is_in_the_harness_s_environment_and_in_no_frame_or_shell(tmp_path, stand):
    async with running(make_spec(tmp_path, tools=binding(tmp_path))) as (_, heard):
        await heard.until(Ready)
        frames = stand.script.with_suffix(".heard").read_text()

    assert "tok-1" not in frames
    assert "tok-1" not in " ".join(stand.launch["argv"])
    assert stand.launch["env"][TOKEN_VARIABLE] == "tok-1"
    assert stand.asked("thread/start")["config"]["shell_environment_policy"]["exclude"] == [TOKEN_VARIABLE]


async def test_what_the_user_set_stays_in_what_replaces_it(tmp_path, stand):
    policy = {"exclude": ["MY_SECRET"], "inherit": "core"}
    stand.install(config={"developer_instructions": "their words", "shell_environment_policy": policy})
    spec = make_spec(tmp_path, tools=binding(tmp_path), instructions="our words")

    async with running(spec) as (_, heard):
        await heard.until(Ready)

    assert stand.asked("config/read") == {"cwd": str(tmp_path)}
    thread = stand.asked("thread/start")
    assert thread["developerInstructions"] == "their words\n\nour words"
    assert thread["config"]["shell_environment_policy"] == {"exclude": ["MY_SECRET", TOKEN_VARIABLE]}


async def test_nothing_is_set_that_the_role_left_to_the_user(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="", allow_native_children=True)) as (_, heard):
        await heard.until(Ready)

    thread = stand.asked("thread/start")
    assert not {"model", "sandbox", "developerInstructions", "modelProvider"} & set(thread)
    assert thread["config"] == {}


async def test_a_role_s_sandbox_is_sent_as_it_stands(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="", sandbox="workspace-write")) as (_, heard):
        await heard.until(Ready)

    assert stand.asked("thread/start")["sandbox"] == "workspace-write"


async def test_access_is_a_provider_the_app_server_starts_on_so_the_key_pays(tmp_path, stand):
    access = {"OPENAI_BASE_URL": Secret("http://127.0.0.1:1/v1"), "OPENAI_API_KEY": Secret("dummy")}

    async with running(make_spec(tmp_path, goal="", model="m", access=access)) as (_, heard):
        await heard.until(Ready)

    assert stand.launch["argv"] == KEYED
    thread = stand.asked("thread/start")
    assert "modelProvider" not in thread
    assert thread["config"][URL] == "http://127.0.0.1:1/v1"
    assert stand.launch["env"]["OPENAI_API_KEY"] == "dummy"


async def test_a_key_alone_is_a_provider_on_the_default_url(tmp_path, stand):
    spec = make_spec(tmp_path, goal="", model="m", access={"OPENAI_API_KEY": Secret("dummy")})

    async with running(spec) as (_, heard):
        await heard.until(Ready)

    assert stand.launch["argv"] == KEYED
    thread = stand.asked("thread/start")
    assert "modelProvider" not in thread
    assert URL not in thread["config"]


async def test_with_access_given_an_unset_model_is_refused(tmp_path, stand):
    with pytest.raises(DriverError, match="set a model"):
        await CodexDriver().start(make_spec(tmp_path, access={"OPENAI_API_KEY": Secret("k")}), Heard())


async def test_with_no_access_an_unset_model_is_the_harness_s_own_and_ready_says_which(tmp_path, stand):
    stand.install(model="its-default")

    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        ready = await heard.until(Ready)

    assert ready.effective_model == "its-default"


async def test_a_base_url_with_no_key_is_refused(tmp_path, stand):
    spec = make_spec(tmp_path, model="m", access={"OPENAI_BASE_URL": Secret("http://127.0.0.1:1")})

    with pytest.raises(DriverError, match="OPENAI_API_KEY"):
        await CodexDriver().start(spec, Heard())


async def test_effort_goes_as_it_stands_and_one_the_harness_would_drop_is_refused(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="", effort="low")) as (_, heard):
        await heard.until(Ready)
    assert stand.asked("thread/start")["config"]["model_reasoning_effort"] == "low"

    stand.install(effort="high")
    refused = CodexDriver()
    with pytest.raises(DriverError, match="low was asked for"):
        await refused.start(make_spec(tmp_path, goal="", effort="low"), Heard())
    await refused.stop(GRACE)


async def test_what_the_shell_signs_in_with_goes_through_and_a_provider_key_does_not(tmp_path, stand, monkeypatch):
    home = str(tmp_path / "codex-home")
    monkeypatch.setenv("CODEX_HOME", home)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:1")
    monkeypatch.setenv("all_proxy", "http://proxy:2")
    monkeypatch.setenv("SSL_CERT_FILE", "/ca.pem")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/bus")
    monkeypatch.setenv("OPENAI_API_KEY", "not-for-a-harness")

    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    env = stand.launch["env"]
    assert (env["CODEX_HOME"], env["HTTPS_PROXY"], env["all_proxy"]) == (home, "http://proxy:1", "http://proxy:2")
    assert (env["SSL_CERT_FILE"], env["DBUS_SESSION_BUS_ADDRESS"]) == ("/ca.pem", "unix:path=/bus")
    assert "OPENAI_API_KEY" not in env


async def test_a_resume_sends_the_same_fields_and_waits_for_a_delivery(tmp_path, stand):
    spec = make_spec(tmp_path, model="m", tools=binding(tmp_path), instructions="words", resume="thread-1")

    async with running(spec) as (_, heard):
        ready = await heard.until(Ready)

    resumed = stand.asked("thread/resume")
    assert resumed.pop("threadId") == "thread-1"
    assert resumed.pop("excludeTurns") is True
    assert resumed == {
        "cwd": str(tmp_path),
        "approvalPolicy": "on-request",
        "approvalsReviewer": "user",
        "config": resumed["config"],
        "model": "m",
        "developerInstructions": "words",
    }
    assert "mcp_servers" in resumed["config"]
    assert ready.native == "thread-1"
    assert "turn/start" not in [frame.get("method") for frame in stand.heard]


@pytest.mark.parametrize("resume", [None, "thread-1"])
@pytest.mark.parametrize("said", ["/somewhere/else", None])
async def test_codex_refuses_a_thread_running_outside_its_workspace(tmp_path, stand, resume, said):
    """What the thread says it runs in is what its tools run in, and an agent's workspace is the one place that is."""
    stand.install(cwd=said)
    driver = CodexDriver()

    with pytest.raises(DriverError, match=f"its thread runs in {said}, and its workspace is {tmp_path}"):
        await driver.start(make_spec(tmp_path, goal="", resume=resume), Heard())
    await driver.stop(GRACE)


async def test_a_refused_thread_is_a_refused_start_with_secrets_masked(tmp_path, stand):
    stand.install(refused={"thread/start": "required MCP servers failed: tok-1"})
    driver = CodexDriver()

    with pytest.raises(DriverError, match=r"failed: \*\*\*"):
        await driver.start(make_spec(tmp_path, tools=binding(tmp_path)), Heard())
    await driver.stop(GRACE)


# What a login is.


@pytest.mark.parametrize(
    ("said", "login"),
    [
        ("Logged in using ChatGPT\n", "plan"),
        ("WARNING: something\nLogged in using ChatGPT\n", "plan"),
        ("API key configured - sk-***\n", "key"),
        ("Not logged in\n", None),
        ("Logged in using access token\n", None),
    ],
)
def test_describe_reads_the_kind_of_login_and_nothing_else(stand, said, login):
    stand.install(status=said)

    assert CodexDriver().describe().login == login


def test_describe_cannot_tell_when_the_status_hangs(stand, monkeypatch):
    stand.install(status_seconds=30)
    monkeypatch.setattr("platoon_harness.drivers.process._STATUS_SECONDS", 0.05)

    assert CodexDriver().describe().login is None


def test_the_cap_on_one_tool_call_is_declared_so_a_hold_past_it_is_refused_up_front():
    assert CodexDriver().describe().capabilities.tool_timeout_s == 300.0


def test_it_declares_where_its_harness_is_installed_with_the_release_it_resolves_into(stand, monkeypatch, tmp_path):
    """A standalone release names itself in `codex-package.json`, and holds the bwrap of Codex's own sandbox."""
    release = tmp_path / "releases" / "0.167.0"
    (release / "bin").mkdir(parents=True)
    (release / "codex-package.json").write_text("{}")
    (release / "bin" / "codex").write_bytes((stand.folder / "codex").read_bytes())
    (release / "bin" / "codex").chmod(0o700)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "codex").symlink_to(release / "bin" / "codex")
    alone = CodexDriver().describe().installed
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")

    assert alone == (stand.folder / "codex",)
    assert CodexDriver().describe().installed == (tmp_path / "bin" / "codex", release)


def test_describe_cannot_tell_with_no_binary(monkeypatch):
    monkeypatch.setenv("PATH", "")

    assert CodexDriver().describe().login is None


# What each frame becomes.


async def test_a_turn_starts_and_ends(tmp_path, stand):
    reports = await played(stand, tmp_path)

    assert reports == [TurnStarted(turn="turn-1"), TurnEnded()]
    assert stand.asked("turn/start")["input"] == [{"type": "text", "text": "do the thing"}]


async def test_a_goal_goes_out_on_a_fresh_start_and_none_waits(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (_, heard):
        await heard.until(Ready)

    assert "turn/start" not in [frame.get("method") for frame in stand.heard]


async def test_every_message_is_a_message_whatever_phase_the_harness_gives_it(tmp_path, stand):
    reports = await played(
        stand,
        tmp_path,
        notice("item/agentMessage/delta", itemId="m", delta="on"),
        completed("agentMessage", "m1", text="on it", phase="commentary"),
        completed("agentMessage", "m2", text="done", phase="final_answer"),
        completed("agentMessage", "m3", text="legacy", phase=None),
    )

    assert Delta(text="on") in reports
    items = [item for item in reports if isinstance(item, Item)]
    assert [(item.kind, item.phase, item.native_id, item.body) for item in items] == [
        ("message", None, "m1", "on it"),
        ("message", None, "m2", "done"),
        ("message", None, "m3", "legacy"),
    ]


async def test_reasoning_and_a_plan_are_thoughts_and_empty_reasoning_is_nothing(tmp_path, stand):
    reports = await played(
        stand,
        tmp_path,
        completed("reasoning", "r1", summary=["why"], content=["how"]),
        completed("reasoning", "r2", summary=[], content=[]),
        completed("plan", "p1", text="step one"),
    )

    items = [item for item in reports if isinstance(item, Item)]
    assert [(item.kind, item.body) for item in items] == [("thought", "why\nhow"), ("thought", "step one")]


async def test_a_tool_says_it_began_then_what_came_of_it(tmp_path, stand):
    reports = await played(
        stand,
        tmp_path,
        started("commandExecution", "c1", command="bash -lc ls", status="inProgress"),
        completed("commandExecution", "c1", command="bash -lc ls", status="failed", aggregatedOutput="no"),
        started("mcpToolCall", "m1", server="ph", tool="wait", arguments={"timeout": 1}),
        completed(
            "mcpToolCall",
            "m1",
            server="ph",
            tool="wait",
            status="completed",
            result={"content": [{"type": "text", "text": "parked"}]},
        ),
        completed("mcpToolCall", "m2", server="ph", tool="peers", status="failed", error={"message": "refused"}),
    )

    items = [item for item in reports if isinstance(item, Item)]
    assert [(item.kind, item.phase, item.native_id, item.outcome) for item in items] == [
        ("tool", "started", "c1", None),
        ("tool", "completed", "c1", "failed"),
        ("tool", "started", "m1", None),
        ("tool", "completed", "m1", "completed"),
        ("tool", "completed", "m2", "failed"),
    ]
    assert items[0].gist == "bash -lc ls"
    assert items[1].body == "no"
    assert items[2].gist == 'mcp__ph__wait {"timeout": 1}'
    assert items[2].body == '{"timeout": 1}'
    assert items[3].body == "parked"
    assert items[4].body == "refused"


async def test_a_patch_names_its_paths_and_holds_its_diff(tmp_path, stand):
    changes = [{"path": "a.py", "kind": {"type": "add"}, "diff": "+a"}, {"path": "b.py", "kind": {}, "diff": "+b"}]
    reports = await played(
        stand,
        tmp_path,
        started("fileChange", "f1", changes=changes, status="inProgress"),
        completed("fileChange", "f1", changes=changes, status="completed"),
    )

    items = [item for item in reports if isinstance(item, Item)]
    assert [(item.kind, item.phase, item.gist) for item in items] == [
        ("patch", "started", "a.py b.py"),
        ("patch", "completed", "a.py b.py completed"),
    ]
    assert items[1].body == "+a\n+b"


async def test_usage_is_what_the_total_rose_by_and_says_one_model_call_with_no_id(tmp_path, stand):
    reports = await played(stand, tmp_path, used(14), used(14), used(30))

    usages = [report for report in reports if isinstance(report, Usage)]
    assert [(usage.tokens, usage.label, usage.scope, usage.call_id) for usage in usages] == [
        (14, "provider", "call", None),
        (16, "provider", "call", None),
    ]
    calls = [report for report in reports if isinstance(report, ModelCall)]
    assert [(call.call_id, call.purpose) for call in calls] == [(None, None), (None, None)]


async def test_the_old_total_a_resume_sends_again_is_no_spending(tmp_path, stand):
    stand.install(on_resume=[used(100)], turns=[[began(), used(114), ended()]])

    async with running(make_spec(tmp_path, goal="", resume="thread-1")) as (driver, heard):
        await heard.until(Ready)
        await driver.deliver(delivery())
        await heard.until(TurnEnded)

    assert [usage.tokens for usage in heard.of(Usage)] == [14]


async def test_a_compaction_reports_its_call_and_leaves_what_it_forgot_unknown(tmp_path, stand):
    reports = await played(
        stand,
        tmp_path,
        started("contextCompaction", "k1"),
        used(14),
        used(14, last=6900),
        completed("contextCompaction", "k1"),
    )

    assert [call.purpose for call in reports if isinstance(call, ModelCall)] == ["compaction"]
    compacted = next(report for report in reports if isinstance(report, Compacted))
    assert (compacted.forgotten, compacted.summary) == (None, None)
    assert not [gap for gap in reports if isinstance(gap, GapReport)]


async def test_a_compaction_that_reports_no_usage_is_a_hidden_call(tmp_path, stand):
    reports = await played(stand, tmp_path, started("contextCompaction", "k1"), completed("contextCompaction", "k1"))

    assert [call.purpose for call in reports if isinstance(call, ModelCall)] == ["compaction"]
    assert GapReport(what="hidden_call") in reports


# A delivery.


async def test_a_delivery_goes_out_under_its_id_and_lands_with_its_item(tmp_path, stand):
    stand.install(turns=[[began(), landed("41"), ended()]])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        await driver.deliver(delivery())
        delivered = await heard.until(InputDelivered)
        await heard.until(TurnEnded)

    assert stand.asked("turn/start") == {
        "threadId": "thread-1",
        "input": [{"type": "text", "text": "text of 41"}],
        "clientUserMessageId": "41",
    }
    assert delivered == InputDelivered(input="41", boundary="turn", evidence="userMessage", native_id="user-1")


async def test_one_that_lands_inside_a_turn_is_at_a_model_call(tmp_path, stand):
    stand.install(turns=[[began(), started("userMessage", "goal")], [landed("41", "user-2"), ended()]])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.deliver(delivery(boundary="model_call"))
        delivered = await heard.until(InputDelivered)

    assert delivered.boundary == "model_call"
    assert len(heard.of(TurnStarted)) == 1


async def test_a_delivery_the_harness_refuses_fails_and_is_not_sent_again(tmp_path, stand):
    stand.install(refused={"turn/start": "the thread is busy"})

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        with pytest.raises(DriverError, match="the thread is busy"):
            await driver.deliver(delivery())
        await driver.interrupt()


async def test_a_delivery_that_landed_and_then_was_refused_is_a_driver_error(tmp_path, stand):
    stand.install(refused={"turn/start": "the thread is busy"}, before_refusal=[landed("41")])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        with pytest.raises(DriverError, match="the thread is busy"):
            await driver.deliver(delivery())

    assert heard.of(InputDelivered)[0].input == "41"


async def test_a_harness_that_stopped_reading_holds_a_delivery_up(tmp_path, stand):
    stand.install(deaf_after="turn/start")

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.2):
                await driver.deliver(delivery())


async def test_an_interrupt_ends_the_turn_and_lives_on(tmp_path, stand):
    stand.install(turns=[[began()]], on_interrupt=[ended("interrupted")])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.interrupt()
        turn = await heard.until(TurnEnded)

    assert stand.asked("turn/interrupt") == {"threadId": "thread-1", "turnId": "turn-1"}
    assert turn.reason == "interrupted"
    assert GapReport(what="usage_lower_bound") in heard.reports
    assert Usage(label="unavailable", scope="call") in heard.reports


async def test_what_an_interrupt_drops_is_the_runtime_s_to_offer_again(tmp_path, stand):
    stand.install(turns=[[began()], []], on_interrupt=[ended("interrupted")])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.deliver(delivery(boundary="model_call"))
        await driver.interrupt()
        await heard.until(TurnEnded)

    sent = [frame["params"].get("clientUserMessageId") for frame in stand.heard if frame.get("method") == "turn/start"]
    assert sent == ["launch", "41"]
    assert "41" not in [landed.input for landed in heard.of(InputDelivered)]


def said(stand: Stand, *frames: Any) -> None:
    """Have the stand-in say frames out of turn, as a harness does when it is ready to."""
    pipe = os.open(f"/proc/{stand.launch['pid']}/fd/1", os.O_WRONLY)
    try:
        os.write(pipe, b"".join(json.dumps(frame).replace("$thread", "thread-1").encode() + b"\n" for frame in frames))
    finally:
        os.close(pipe)


async def test_an_interrupt_as_a_handover_begins_a_turn_cuts_that_turn_once_it_has_an_id(tmp_path, stand):
    stand.install(turns=[[]], on_interrupt=[ended("interrupted")])

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        await driver.deliver(delivery())
        await driver.interrupt()
        said(stand, began("turn-1"))
        turn = await heard.until(TurnEnded)

    assert stand.asked("turn/interrupt") == {"threadId": "thread-1", "turnId": "turn-1"}
    assert turn.reason == "interrupted"


async def test_an_interrupt_of_a_handover_the_harness_then_refused_cuts_no_later_turn(tmp_path, stand):
    stand.install(turns=[[began(), ended()]], refused_once={"turn/start": "the thread is busy"})

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        handing = asyncio.create_task(driver.deliver(delivery("41")))
        await asyncio.sleep(0)  # It has sent `turn/start` and heard nothing back.
        await driver.interrupt()
        with pytest.raises(DriverError, match="the thread is busy"):
            await handing
        await driver.deliver(delivery("42"))
        turn = await heard.until(TurnEnded)

    assert turn.reason == "stopped"
    assert "turn/interrupt" not in [frame.get("method") for frame in stand.heard]


async def test_an_interrupt_refused_labels_no_turn_that_then_runs_to_its_end(tmp_path, stand):
    stand.install(turns=[[began()]], refused={"turn/interrupt": "not now"})

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        with pytest.raises(DriverError, match="not now"):
            await driver.interrupt()
        said(stand, ended(turn="turn-1"))
        turn = await heard.until(TurnEnded)

    assert turn.reason == "stopped"


async def test_a_turn_the_harness_cut_with_nobody_interrupting_reads_as_aborted(tmp_path, stand):
    stand.install(turns=[[began(), ended("interrupted")]])

    async with running(make_spec(tmp_path)) as (_, heard):
        turn = await heard.until(TurnEnded)

    assert turn.reason == "aborted"


async def test_an_answer_to_a_harness_that_died_is_a_driver_error(tmp_path, stand):
    stand.install(turns=[[began(), asking()]])
    spec = make_spec(tmp_path)

    async with running(spec) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        os.killpg(stand.launch["pid"], signal.SIGKILL)
        await heard.until(Exited)

        with pytest.raises(DriverError):
            await driver.answer(asked.id, "allow")


async def test_an_interrupt_that_comes_to_no_turn_asks_nothing(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        await driver.interrupt()

    assert "turn/interrupt" not in [frame.get("method") for frame in stand.heard]


async def test_a_turn_that_ended_as_an_interrupt_went_out_refuses_nothing(tmp_path, stand):
    refused = {"turn/interrupt": "no active turn to interrupt"}
    stand.install(turns=[[began()]], refused=refused, before_refusal=[ended()])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        await driver.interrupt()
        turn = await heard.until(TurnEnded)

    assert turn.reason == "interrupted"


async def test_an_interrupt_refused_with_the_turn_still_going_fails(tmp_path, stand):
    stand.install(turns=[[began()]], refused={"turn/interrupt": "not now"})

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(TurnStarted)
        with pytest.raises(DriverError, match="not now"):
            await driver.interrupt()


# An approval.


@pytest.mark.parametrize(
    ("verdict", "decision"),
    [("allow", {"decision": "accept"}), ("deny", {"decision": "decline"})],
)
@pytest.mark.parametrize(
    "method",
    ["item/commandExecution/requestApproval", "item/fileChange/requestApproval"],
)
async def test_a_verdict_answers_the_request_that_asked(tmp_path, stand, method, verdict, decision):
    stand.install(turns=[[began(), asking(method)]], on_answer=[ended()])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, verdict)
        await heard.until(TurnEnded)

    assert stand.answers() == [{"id": 0, "result": decision}]
    assert asked.gist == "touch x"


async def test_a_command_approval_carries_its_whole_command(tmp_path, stand):
    command = "/bin/bash -lc 'echo " + " ".join(f"word{n}" for n in range(80)) + "'"
    stand.install(turns=[[began(), asking(command=command)]], on_answer=[ended()])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "deny")
        await heard.until(TurnEnded)

    assert (asked.body, asked.gist) == (command, command[:280])


async def test_an_approval_s_id_is_its_own_across_agents_and_processes(tmp_path, stand):
    """Ids are journaled per session, and a process counts from one, so a count would collide: a report the journal
    refuses is answered `deny`, and the second agent to ask would be turned down with nobody asked."""
    asked = []
    for name in ("one", "two"):
        stand.install(turns=[[began(), asking("item/commandExecution/requestApproval")]], on_answer=[ended()])
        async with running(make_spec(tmp_path / name)) as (driver, heard):
            asked.append(await heard.until(ApprovalRequested))
            await driver.answer(asked[-1].id, "allow")
            await heard.until(TurnEnded)

    assert asked[0].id != asked[1].id


@pytest.mark.parametrize(
    ("verdict", "answer"),
    [
        ("allow", {"action": "accept", "content": {}}),
        ("deny", {"action": "decline"}),
    ],
)
async def test_a_tool_of_the_user_s_own_asks_by_elicitation(tmp_path, stand, verdict, answer):
    request = asking("mcpServer/elicitation/request", message="Allow the tool?", command=None, itemId=None)
    stand.install(turns=[[began(), request]], on_answer=[ended()])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, verdict)
        await heard.until(TurnEnded)

    assert asked.gist == "Allow the tool?" and json.loads(asked.body or "")["message"] == "Allow the tool?"
    assert stand.answers() == [{"id": 0, "result": answer}]


@pytest.mark.parametrize(
    ("verdict", "granted"),
    [("allow", {"network": {"enabled": True}}), ("deny", {})],
)
async def test_a_request_for_permissions_grants_what_it_asked_or_nothing(tmp_path, stand, verdict, granted):
    wanted = {"network": {"enabled": True}}
    request = asking("item/permissions/requestApproval", permissions=wanted, reason="to fetch", command=None)
    stand.install(turns=[[began(), request]], on_answer=[ended()])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, verdict)
        await heard.until(TurnEnded)

    assert stand.answers() == [{"id": 0, "result": {"permissions": granted, "scope": "turn"}}]
    assert json.loads(asked.body or "")["permissions"] == wanted


async def test_what_comes_of_an_answer_is_read_from_the_item(tmp_path, stand):
    stand.install(
        turns=[[began(), started("commandExecution", command="x"), asking()]],
        on_answer=[completed("commandExecution", command="x", status="failed", aggregatedOutput="EROFS"), ended()],
    )

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "allow")
        decided = await heard.until(Item, lambda item: item.approval is not None)

    assert (decided.approval, decided.outcome, decided.body) == (asked.id, "failed", "EROFS")


async def test_an_approval_goes_moot_with_its_turn_and_nothing_answers_it(tmp_path, stand):
    stand.install(turns=[[began(), asking()]], on_interrupt=[ended("interrupted")])

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.interrupt()
        await heard.until(TurnEnded)
        with pytest.raises(DriverError, match="no approval"):
            await driver.answer(asked.id, "allow")

    assert not stand.answers()


async def test_an_answer_to_nothing_is_refused(tmp_path, stand):
    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        with pytest.raises(DriverError, match="no approval approval-9"):
            await driver.answer("approval-9", "allow")


async def test_a_request_nobody_here_can_answer_is_refused_and_is_a_gap(tmp_path, stand):
    question = {"method": "item/tool/requestUserInput", "id": 3, "params": {"threadId": "$thread", "questions": []}}
    stand.install(turns=[[began(), question]], on_answer=[ended()])

    async with running(make_spec(tmp_path)) as (_, heard):
        native = await heard.until(Native)
        await heard.until(GapReport, lambda gap: gap.what == "unknown_update")
        await heard.until(TurnEnded)

    assert "requestUserInput" in native.raw
    assert stand.answers()[0]["error"]["code"] == -32601


# A native child.

CHILD = "thread-child"


async def test_a_child_is_seen_once_inferred_and_its_work_stays_its_own(tmp_path, stand):
    reports = await played(
        stand,
        tmp_path,
        began("child-1", CHILD),
        began("child-2", CHILD),
        completed("agentMessage", "m1", CHILD, text="child says"),
        notice("item/agentMessage/delta", threadId=CHILD, delta="child says"),
        ended(turn="child-1", thread=CHILD),
        ended(turn="child-2", thread=CHILD),
    )

    assert [child for child in reports if isinstance(child, ChildSeen)] == [ChildSeen(native=CHILD)]
    assert GapReport(what="native_child_unattributed") in reports
    assert not [report for report in reports if isinstance(report, Item | Delta)]


async def test_a_child_keeps_the_turn_open_until_it_stops(tmp_path, stand):
    stand.install(turns=[[began(), began("child-1", CHILD), ended(), used(14, CHILD)]])

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(Usage)
        assert not heard.of(TurnEnded)
        await driver.interrupt()

    usage = heard.of(Usage)[0]
    assert (usage.tokens, usage.scope) == (14, "tree")
    assert len(heard.of(ModelCall)) == 1


async def test_the_turn_ends_with_the_child_that_outlived_it_and_says_how_it_ended(tmp_path, stand):
    stand.install(
        turns=[[began(), began("child-1", CHILD), ended("failed", error={"message": "no quota"})]],
        on_interrupt=[ended("interrupted", "child-1", CHILD)],
    )

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(GapReport, lambda gap: gap.what == "usage_lower_bound")
        await driver.interrupt()
        turn = await heard.until(TurnEnded)

    assert stand.asked("turn/interrupt") == {"threadId": CHILD, "turnId": "child-1"}
    assert turn.reason == "no quota"
    assert len(heard.of(TurnEnded)) == 1


async def test_an_interrupt_walks_every_thread_at_work(tmp_path, stand):
    stand.install(
        turns=[[began(), began("child-1", CHILD)]],
        on_interrupt=[ended("interrupted", "$turn", "$thread"), ended("interrupted", "child-1", CHILD)],
    )

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(ChildSeen)
        await driver.interrupt()
        await heard.until(TurnEnded)

    interrupts = [frame["params"] for frame in stand.heard if frame.get("method") == "turn/interrupt"]
    assert {params["threadId"] for params in interrupts} == {"thread-1", CHILD}


def spawned(child: str, thread: str = "$thread") -> dict[str, Any]:
    """A spawn of Codex's first generation of agents, as it completes, naming a child yet to start."""
    states = {child: {"status": "pendingInit", "message": None}}
    fields = {"tool": "spawnAgent", "status": "completed", "receiverThreadIds": [child], "agentsStates": states}
    return completed("collabAgentToolCall", f"spawn-{child}", thread, **fields)


SPAWNS = {
    "first": spawned(CHILD),
    "second": started("subAgentActivity", "call_child", kind="started", agentThreadId=CHILD, agentPath="/root/child1"),
}


@pytest.mark.parametrize("generation", SPAWNS)
@pytest.mark.parametrize("child_first", [True, False], ids=["child_starts_first", "parent_ends_first"])
async def test_a_spawned_child_holds_the_turn_open_whichever_comes_first(tmp_path, stand, generation, child_first):
    """A child's `turn/started` can come after its parent's `turn/completed`, so the child counts from its spawn."""
    child, parent = [began("child-1", CHILD)], [used(14), used(28), ended()]
    rest = [used(14, CHILD), ended(turn="child-1", thread=CHILD)]
    stand.install(turns=[[began(), SPAWNS[generation], *(child + parent if child_first else parent + child), *rest]])

    async with running(make_spec(tmp_path)) as (_, heard):
        await heard.until(Usage, lambda usage: usage.scope == "tree")
        await heard.until(TurnEnded)

    told = (TurnStarted, ChildSeen, TurnEnded)
    assert [type(report) for report in heard.reports if isinstance(report, told)] == list(told)
    assert [usage.scope for usage in heard.of(Usage)] == ["call", "call", "tree"]


async def test_a_child_said_interrupted_before_its_turn_starts_still_holds_the_turn_open(tmp_path, stand):
    """Codex 0.167.0 said so of a child its parent interrupted as it spawned it, and then the child ran a turn."""
    cut = started("subAgentActivity", "call_cut", kind="interrupted", agentThreadId=CHILD, agentPath="/root/child1")
    child = [began("child-1", CHILD), used(14, CHILD), ended("interrupted", "child-1", CHILD)]
    stand.install(turns=[[began(), SPAWNS["second"], cut, used(14), ended(), *child]])

    async with running(make_spec(tmp_path)) as (_, heard):
        await heard.until(Usage, lambda usage: usage.scope == "tree")
        await heard.until(TurnEnded)

    told = (TurnStarted, ChildSeen, TurnEnded)
    assert [type(report) for report in heard.reports if isinstance(report, told)] == list(told)


async def test_a_spawn_that_names_a_child_already_heard_from_holds_nothing(tmp_path, stand):
    """A spawn saying `pendingInit` of a child whose turn has come and gone would otherwise hold the turn for good."""
    reports = await played(
        stand, tmp_path, began("child-1", CHILD), ended(turn="child-1", thread=CHILD), SPAWNS["first"]
    )

    assert [type(report) for report in reports if isinstance(report, ChildSeen | TurnEnded)] == [ChildSeen, TurnEnded]


async def test_a_child_s_own_spawn_holds_the_turn_open_too(tmp_path, stand):
    grandchild = "thread-grandchild"
    stand.install(
        turns=[
            [
                began(),
                began("child-1", CHILD),
                ended(),
                spawned(grandchild, CHILD),
                ended(turn="child-1", thread=CHILD),
                began("grandchild-1", grandchild),
                used(7, grandchild),
                ended(turn="grandchild-1", thread=grandchild),
            ]
        ]
    )

    async with running(make_spec(tmp_path)) as (_, heard):
        await heard.until(Usage)
        await heard.until(TurnEnded)

    assert [child.native for child in heard.of(ChildSeen)] == [CHILD, grandchild]
    assert len(heard.of(TurnEnded)) == len(heard.of(TurnStarted)) == 1


async def test_an_interrupt_cuts_a_spawned_child_s_turn_as_it_starts(tmp_path, stand):
    stand.install(
        turns=[[began(), SPAWNS["first"]]],
        on_interrupt_of={
            "turn-1": [ended("interrupted"), began("child-1", CHILD)],
            "child-1": [ended("interrupted", "child-1", CHILD)],
        },
    )

    async with running(make_spec(tmp_path)) as (driver, heard):
        await heard.until(ChildSeen)
        await driver.interrupt()
        turn = await heard.until(TurnEnded)

    interrupts = [frame["params"] for frame in stand.heard if frame.get("method") == "turn/interrupt"]
    assert interrupts == [{"threadId": "thread-1", "turnId": "turn-1"}, {"threadId": CHILD, "turnId": "child-1"}]
    assert turn.reason == "interrupted"
    assert len(heard.of(TurnStarted)) == 1


async def test_a_child_s_approval_comes_to_the_runtime_too(tmp_path, stand):
    request = asking(threadId=CHILD, turnId="child-1")
    stand.install(
        turns=[[began(), began("child-1", CHILD), request]],
        on_answer=[ended(), ended(turn="child-1", thread=CHILD)],
    )

    async with running(make_spec(tmp_path)) as (driver, heard):
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "allow")
        await heard.until(TurnEnded)

    assert stand.answers() == [{"id": 0, "result": {"decision": "accept"}}]


# What goes wrong.


async def test_a_failed_turn_says_why_with_secrets_masked_and_a_gap(tmp_path, stand):
    stand.install(turns=[[began(), ended("failed", error={"message": "401 for tok-1"})]])

    async with running(make_spec(tmp_path, tools=binding(tmp_path))) as (_, heard):
        turn = await heard.until(TurnEnded)

    assert turn.reason == "401 for ***"
    assert GapReport(what="usage_lower_bound") in heard.reports


async def test_an_unknown_notification_is_native_plus_a_gap(tmp_path, stand):
    reports = await played(stand, tmp_path, notice("model/rerouted", toModel="another"))

    native = next(report for report in reports if isinstance(report, Native))
    assert "model/rerouted" in native.raw
    assert GapReport(what="unknown_update") in reports


async def test_an_unknown_item_is_native_plus_a_gap(tmp_path, stand):
    reports = await played(stand, tmp_path, completed("hookPrompt", "h1"), completed("somethingNew", "h2"))

    assert len([report for report in reports if isinstance(report, Native)]) == 2


async def test_a_frame_of_the_wrong_shape_is_a_gap_and_the_read_loop_goes_on(tmp_path, stand):
    reports = await played(
        stand,
        tmp_path,
        completed("fileChange", "f1", changes=[{}]),
        "this is no frame",
        '{"no method": true}',
        completed("agentMessage", "m1", text="still here"),
    )

    assert len([report for report in reports if isinstance(report, Native)]) == 3
    assert [item.body for item in reports if isinstance(item, Item)] == ["still here"]
    assert reports[-1] == TurnEnded()


async def test_an_account_frame_never_reaches_a_report(tmp_path, stand):
    reports = await played(
        stand,
        tmp_path,
        {"method": "account/updated", "params": {"email": "someone"}},
        {"method": "account/rateLimits/updated", "params": {"plan": "a plan"}},
        {"method": "account/somethingNew", "params": {"email": "someone"}},
    )

    assert not [report for report in reports if isinstance(report, Native)]


async def test_a_harness_that_exits_is_reported_and_fails_what_is_asked_of_it(tmp_path, stand):
    stand.install(exit_on_eof=0)

    async with running(make_spec(tmp_path, goal="")) as (driver, heard):
        await heard.until(Ready)
        assert driver._process is not None
        driver._process.stdin.close()
        await heard.until(Exited)
        with pytest.raises(DriverError, match="codex is gone"):
            await driver.deliver(delivery())


async def test_a_harness_gone_before_its_handshake_fails_the_start(tmp_path, stand):
    stand.install(exit_at_once=3)
    driver = CodexDriver()

    with pytest.raises(DriverError, match="codex is gone"):
        await driver.start(make_spec(tmp_path), Heard())
    await driver.stop(GRACE)


async def test_a_driver_that_has_not_started_says_so(tmp_path):
    with pytest.raises(DriverError, match="has not started"):
        await CodexDriver().deliver(delivery())
    await CodexDriver().stop(GRACE)


async def test_stop_ends_the_harness_by_end_of_stdin(tmp_path, stand):
    stand.install(exit_on_eof=0)
    driver, heard = CodexDriver(), Heard()
    await driver.start(make_spec(tmp_path, goal=""), heard)
    await heard.until(Ready)

    await driver.stop(GRACE)

    assert heard.of(Exited)[0].reason == "exited with code 0"
    assert not [gap for gap in heard.of(GapReport) if gap.what == "crash_window"]


async def test_a_resumed_thread_says_what_landed_and_a_miss_proves_nothing(tmp_path, stand):
    user = {"type": "userMessage", "id": "u1", "clientId": "41"}
    stand.install(history=[{"id": "turn-1", "items": [user, {"type": "agentMessage", "id": "m1"}]}])

    async with running(make_spec(tmp_path, goal="", resume="thread-1")) as (driver, heard):
        await heard.until(Ready)
        assert await driver.reconcile("41") == "landed"
        assert await driver.reconcile("42") == "unknown"
        assert await driver.reconcile("an-approval") == "unknown"

    assert stand.asked("thread/turns/list") == {"threadId": "thread-1", "itemsView": "full"}
