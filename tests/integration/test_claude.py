"""The `claude` driver on the real binary against FakeModel. Free: a dummy key, an isolated home, and loopback only."""

import asyncio
import fcntl
import json
import os
import re
import shutil
import signal
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
    Compacted,
    Delivery,
    DriverError,
    Exited,
    Item,
    ModelCall,
    Ready,
    TurnEnded,
    Usage,
)
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.levels import Conformance, Profile, levels
from platoon_harness.drivers.process import Record
from platoon_harness.runtime.paths import read_running
from platoon_harness.team import AuthProfile
from platoon_harness.testing import (
    NAMESPACE,
    TOOL,
    FakeModel,
    FakeTools,
    Request,
    Stall,
    Text,
    ToolCall,
    check_driver,
    goal,
)
from platoon_harness.testing.model import INPUT_TOKENS, OUTPUT_TOKENS
from platoon_harness.tools import PREAMBLE
from platoon_harness_cli.provenance import Line

from ..unit.drivers.support import Heard
from ..unit.runtime.gitting import repository
from ..unit.runtime.support import in_state, of_type, until
from . import clients, worktrees
from .scripts import TOLD, following_up, strings

pytestmark = [pytest.mark.slow, pytest.mark.timeout(120)]

BASH = "Bash"
MODEL = "fake-model"
PINNED = "2.1.316"
TIMEOUT = 60.0
CHILD = ToolCall("Agent", {"description": "a child", "prompt": "say so", "subagent_type": "general-purpose"})


@pytest.fixture(autouse=True)
def binary():
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed, so this driver met no real harness here")


def access(home: Path):
    """How a harness reaches FakeModel, on a dummy key, with a home of its own so that no login takes part."""

    def given(model: FakeModel) -> dict[str, Secret]:
        home.mkdir(exist_ok=True)
        variables = {
            "ANTHROPIC_BASE_URL": model.url,
            "ANTHROPIC_API_KEY": "dummy-key",
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        }
        return {name: Secret(value) for name, value in variables.items()}

    return given


def shell(command: str) -> ToolCall:
    return ToolCall(BASH, {"command": command, "description": "conformance"})


def gated(command: str) -> ToolCall:
    return ToolCall(BASH, {"command": command, "description": "needs an approval"}, id="call_gated")


def ours(note: str) -> ToolCall:
    return ToolCall(f"mcp__{NAMESPACE}__{TOOL}", {"note": note})


def garbling(folder: Path):
    """Write into the harness's own stdout, since nothing makes the real binary write a frame no parser knows."""

    async def garble(_: ClaudeDriver) -> None:
        record = Record.read(folder / "malformed_frame_is_a_gap" / "agent")
        assert record is not None
        pipe = os.open(f"/proc/{record.pid}/fd/1", os.O_WRONLY)
        os.write(pipe, b"this is no frame\n" + json.dumps({"type": "nobody knows"}).encode() + b"\n")
        os.close(pipe)

    return garble


async def conformance(folder: Path) -> Conformance:
    return await check_driver(
        ClaudeDriver,
        folder=folder,
        access=access(folder / "home"),
        garble=garbling(folder),
        gated=gated,
        shell=shell,
        tool=ours,
        child=CHILD,
        timeout=TIMEOUT,
    )


async def test_the_claude_driver_conforms(tmp_path):
    result = await conformance(tmp_path)

    print(result)
    assert result.failed == (), str(result)
    assert (result.driver, result.version) == ("claude", PINNED)
    skipped = {check.name for check in result.checks if check.state == "skipped"}
    assert skipped == {"one_shot_exits", "declared_but_unproven"}
    earned = levels(ClaudeDriver().describe().capabilities, Profile(driver="claude", version=result.version), result)
    assert earned.operational.state == "met", earned.operational.reasons
    assert earned.observable.state == "met", earned.observable.reasons


def keyed(home: Path, model: FakeModel, monkeypatch: pytest.MonkeyPatch, **role: Any) -> Team:
    """One agent on the real binary, reaching FakeModel the way an auth profile would."""
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setenv("ANTHROPIC_BASE_URL", model.url)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    bob = Role(harness="claude", model=MODEL, auth="fake", **role)
    return Team(roles={"bob": bob}, auth={"fake": AuthProfile(env=("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY"))})


async def test_what_the_journal_says_a_harness_was_told_is_what_it_sent_its_model(tmp_path, monkeypatch):
    """The text journaled at launch is in the first request whole, once, beside whatever the harness says itself."""
    async with FakeModel("kestrel, done") as model:
        role = {"preamble": f"{PREAMBLE}\nA team of one.", "instructions": TOLD}
        team = keyed(tmp_path / "home", model, monkeypatch, **role)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await until(lambda: of_type(session, "turn.ended"), session)
            instructed = await of_type(session, "agent.instructed")
            told = (await session.get_body(instructed[0].data["body"])).decode()

    assert told.endswith("A team of one.\n\nBegin every reply with the word kestrel, then use `mcp__ph__peers`.")
    assert sum(text.count(told) for text in strings(model.calls[0].json)) == 1


async def test_what_the_journal_says_a_resumed_harness_was_told_is_what_it_sent_its_model(tmp_path, monkeypatch):
    """A harness that reopens its own session is handed and journaled what it was told when that began, though a
    channel has come since, and that text is in the request after the resume whole, once."""
    async with FakeModel("first", "second") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, instructions=TOLD)

        async with Session.start(team, name="told", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await until(lambda: of_type(session, "turn.ended"), session)
            await session.create_channel("news", "topic", readers=["all"], writers=["all"])

        async with Session.resume("told", root=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "again")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 2)
            instructed = await of_type(session, "agent.instructed")
            told = [(await session.get_body(event.data["body"])).decode() for event in instructed]

    assert len(told) == 2 and told[0] == told[1] and "news" not in told[1]
    assert sum(text.count(told[1]) for text in strings(model.calls[-1].json)) == 1


async def test_a_real_harness_that_stays_answers_a_task_a_follow_up_and_a_question_on_one_process(
    tmp_path, monkeypatch
):
    """The owner's flow, with a scripted lead: each answer wakes the lead and nothing else does, and the helper keeps
    one process until the lead retires it."""
    async with FakeModel("first answer", "second answer", "it meant this") as model:
        team = following_up(keyed(tmp_path / "home", model, monkeypatch))

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await session.send("@lead", "go")
            ending = await session.settled(timeout=TIMEOUT)
            events = [event async for event in session.events()]

    turns = [event.agent for event in events if event.type == "turn.started"]
    reports = [event.data["delivery"] for event in events if event.type == "message.sent" and event.data["subject"]]
    assert ending.reason == "settled", ending
    assert (turns.count("lead"), turns.count("bob")) == (4, 3)
    assert [event.agent for event in events if event.type in ("agent.started", "agent.resumed")] == ["lead", "bob"]
    assert reports == ["wake", "wake", "wake", "next-turn"]
    assert {row["agent"]: row["status"] for row in ending.agents} == {"lead": "finished", "bob": "retired"}
    assert len(model.calls) == 3
    assert all(call.says("what you say last in it goes to @lead") for call in model.calls)
    assert model.calls[1].says("A follow-up task") and model.calls[2].says("A question about it")


async def test_a_real_harness_calls_our_tools_parks_wakes_and_resumes_in_a_session(tmp_path, monkeypatch):
    replies = (
        ToolCall("mcp__ph__peers", id="toolu_peers"),
        ToolCall("mcp__ph__wait", {"from": ["@you"]}, id="toolu_wait"),
        "waiting for you",
        "woken",
        "resumed",
    )

    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, name="real", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "find your peers, then wait for me")
            await in_state(session, "bob", "waiting")

            await session.send("@bob", "carry on, the word is cinnabar")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 2)

            items = await of_type(session, "item.recorded")
            placed = await of_type(session, "wait.registered")
            started = (await of_type(session, "agent.started"))[0]
            assert [event.data["reason"] for event in await of_type(session, "turn.ended")] == ["stopped", "stopped"]
            assert {"toolu_peers", "toolu_wait"} <= {event.data["native_id"] for event in items}
            assert placed[0].native["claudecode/toolUseId"] == "toolu_wait"
            assert started.data["effective_model"] == MODEL
            assert started.data["verified"]["login"] == "key"

        async with Session.resume("real", root=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "what was the word?")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 3)

    assert model.calls[-1].says("cinnabar")
    assert model.calls[0].offers("mcp__ph__wait")


async def test_a_user_s_auto_memory_reaches_the_model_as_it_does_in_their_shell(tmp_path):
    work = tmp_path / "work"
    (work / ".git").mkdir(parents=True)  # What Claude Code keys a project's memory on.
    (work / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    memory = tmp_path / "home" / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(work)) / "memory"
    memory.mkdir(parents=True)
    (memory / "MEMORY.md").write_text("- [a fact](fact.md) the word is heliotrope\n")

    async with FakeModel("ok") as model:
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go"), heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert model.calls[0].says("heliotrope")


@pytest.mark.parametrize("mode", ["acceptEdits", "bypassPermissions"])
async def test_a_denial_holds_whatever_mode_a_user_s_settings_name(tmp_path, mode):
    settings = tmp_path / "home" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"defaultMode": mode}}))

    async with FakeModel(ToolCall(BASH, {"command": "touch denied", "description": "x"}), "ok") as model:
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go"), heard)
        asked = await heard.until(ApprovalRequested)
        await driver.answer(asked.id, "deny")
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert not (tmp_path / "work" / "denied").exists()


async def test_a_question_no_verdict_can_answer_is_not_offered(tmp_path):
    async with FakeModel("ok") as model:
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go"), heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert not model.calls[0].offers("AskUserQuestion")
    assert model.calls[0].offers(BASH)


async def test_a_resumed_session_keeps_the_instructions_it_began_with(tmp_path):
    """After `--resume` Claude Code sends the text a session began with, whatever `--append-system-prompt-file` holds
    then, which is why a resume is handed that text again."""
    async with FakeModel("one", "two") as model:
        spec = on_fake_model(tmp_path, model, goal="go", instructions="ALPHA-ONE")
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(spec, heard)
        native = (await heard.until(Ready)).native
        await heard.until(TurnEnded)
        await driver.stop(2.0)

        resumed, heard = ClaudeDriver(), Heard()
        again = {"resume": native, "goal": None, "instructions": "BRAVO-TWO"}
        await resumed.start(spec.model_copy(update=again), heard)
        await heard.until(Ready)
        await resumed.deliver(Delivery(input="41", boundary="turn", text="again", items=()))
        await heard.until(TurnEnded)
        await resumed.stop(2.0)

    assert model.calls[-1].says("ALPHA-ONE") and not model.calls[-1].says("BRAVO-TWO")


NATIVE_CHILDREN = ("Agent", "Workflow", "ListAgents", "SendMessage")


async def first_request(tmp_path: Path, **fields: Any) -> Request:
    tmp_path.mkdir(exist_ok=True)
    async with FakeModel("ok") as model:
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go", **fields), heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)
    return model.calls[0]


async def test_its_own_agents_are_off_unless_a_role_allows_them_and_agent_teams_add_nothing(tmp_path):
    """`Agent` and `Workflow` start agents of the harness's own, and `ListAgents` and `SendMessage` reach them, and
    other Claude sessions on the machine too. A user who turns agent teams on in their settings gets no tool more in
    `-p`."""
    settings = tmp_path / "home" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}}))

    off = await first_request(tmp_path / "off")
    teams = await first_request(tmp_path)
    allowed = await first_request(tmp_path / "allowed", allow_native_children=True)

    assert not {*off.tools, *teams.tools} & set(NATIVE_CHILDREN)
    assert not off.says("SendMessage") and not off.says("Available agent types")
    assert {"Agent", "Workflow", "ListAgents"} <= set(allowed.tools) and allowed.says("SendMessage")
    assert set(teams.tools) == set(off.tools)


async def test_the_token_reaches_the_server_from_the_environment_and_no_file_holds_it(tmp_path):
    async with FakeModel(ours("hello"), "ok") as model, FakeTools() as tools:
        binding = tools.binding(tmp_path)
        spec = on_fake_model(tmp_path, model, goal="go", tools=binding)
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert model.calls[0].offers(TOOL)
    assert tools.calls
    token = binding.token.reveal().encode()
    assert not [path for path in spec.folder.rglob("*") if path.is_file() and token in path.read_bytes()]


async def test_a_server_that_refuses_us_fails_the_start_and_says_why(tmp_path):
    async with FakeModel() as model, FakeTools() as tools:
        binding = tools.binding(tmp_path).model_copy(update={"token": Secret("not-the-token")})
        driver = ClaudeDriver()
        with pytest.raises(DriverError, match="our tools did not connect"):
            await driver.start(on_fake_model(tmp_path, model, tools=binding), Heard())
        await driver.stop(2.0)

    assert not model.calls


async def test_a_real_harness_finishes_with_its_turn(tmp_path, monkeypatch):
    replies = (ToolCall("mcp__ph__agent_finish", {"gist": "all done"}, id="toolu_finish"), "that is all")

    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "finish")
            await in_state(session, "bob", "ended")
            ending = await session.ending()

    assert ending.agents[0]["status"] == "finished"
    assert ending.agents[0]["report"]["gist"] == "all done"


async def test_a_turn_the_owner_stopped_is_told_on_resume_and_the_harness_goes_on(tmp_path, monkeypatch):
    async with FakeModel([Stall(), Text("never heard")], "understood") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, name="stopped", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "think for a long time")
            await asyncio.wait_for(model.call(0), TIMEOUT)

        async with Session.resume("stopped", root=tmp_path) as session:
            ended = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)

    assert [event.data["reason"] for event in ended] == ["stopped by its owner", "stopped"]
    assert model.calls[-1].says("the owner stopping the session")


def taken_twice(finished: list[Any]) -> bool:
    """Whether a wake and a steer have both been handed over."""
    return len([event for event in finished if event.data["kind"] == "deliver"]) == 2


async def test_an_interrupt_as_a_handover_begins_a_turn_never_reads_as_a_failure(tmp_path, monkeypatch):
    """The interrupt lands before the turn has begun, as it begins, or once it runs, and each must read as itself. What
    was waiting for the agent then wakes nothing, and a message sent after it wakes the agent as usual."""
    async with FakeModel([Stall(), Text("first")], "after") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await until(lambda: of_type(session, "effect.started"), session, handing_over)
            await session.interrupt("@bob")
            model.release()
            await in_state(session, "bob", "idle")
            await session.send("@bob", "again")
            ended = await until(lambda: of_type(session, "turn.ended"), session, stopped_at_last)

    assert {event.data["reason"] for event in ended} <= {"interrupted", "stopped"}


def handing_over(started: list[Any]) -> bool:
    return any(event.data["kind"] == "deliver" for event in started)


def stopped_at_last(ended: list[Any]) -> bool:
    return bool(ended) and ended[-1].data["reason"] == "stopped"


async def test_an_agent_that_took_no_turn_comes_back_anew_on_a_resume(tmp_path, monkeypatch):
    """Its harness wrote no session to reopen, so a resume that asked for one would lose it."""
    async with FakeModel("here") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)

        async with Session.start(team, name="idle", root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")

        async with Session.resume("idle", root=tmp_path) as session:
            await until(lambda: of_type(session, "agent.resumed"), session)
            await session.send("@bob", "are you there?")
            ended = await until(lambda: of_type(session, "turn.ended"), session)

    assert ended[-1].data["reason"] == "stopped"
    assert model.calls[-1].says("are you there?")


async def test_a_steer_an_interrupt_cut_off_comes_with_the_next_message_and_reaches_the_model(tmp_path, monkeypatch):
    """What the harness took and never landed wakes nothing once its turn is interrupted, and is offered again, once,
    with the next message."""
    async with FakeModel([Stall()], "the next turn") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, delivery="steer")

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await in_state(session, "bob", "idle")
            await session.send("@bob", "go")
            await asyncio.wait_for(model.call(0), TIMEOUT)
            await session.send("@bob", "the word is cinnabar")
            await until(lambda: of_type(session, "effect.finished"), session, taken_twice)
            await session.interrupt("@bob")
            await until(lambda: of_type(session, "turn.ended"), session)
            await session.send("@bob", "carry on")
            ended = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)

    assert [event.data["reason"] for event in ended] == ["interrupted", "stopped"]
    assert model.calls[1].message.body.decode().count("cinnabar") == 1


def let_go(folder: Path) -> None:
    """Wait for a dead runtime's lock, which outlives its signal by a moment."""
    with (folder / "lock").open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)


async def test_a_steer_the_harness_took_and_never_landed_survives_a_killed_runtime(tmp_path, monkeypatch):
    async with FakeModel([Stall()], "noted") as model:
        team = keyed(tmp_path / "home", model, monkeypatch, delivery="steer")
        guest = await Session.start(team, name="crash", root=tmp_path, cwd=tmp_path, detach=True)
        await in_state(guest, "bob", "idle")
        await guest.send("@bob", "go")
        await asyncio.wait_for(model.call(0), TIMEOUT)
        await guest.send("@bob", "the word is cinnabar")
        await until(lambda: of_type(guest, "effect.finished"), guest, taken_twice)
        running = read_running(guest.folder)
        assert running is not None
        os.kill(running.pid, signal.SIGKILL)
        await guest.leave()
        await asyncio.to_thread(let_go, guest.folder)

        async with Session.resume("crash", root=tmp_path) as session:
            await until(lambda: of_type(session, "turn.ended"), session)
            offers = await of_type(session, "context.offered")

    assert model.calls[-1].says("cinnabar")
    assert "inbox/bob@2" in [item["ref"] for item in offers[-1].data["items"]]


def on_fake_model(tmp_path: Path, fake: FakeModel, **fields: Any) -> AgentSpec:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    spec = {"agent": "ada", "role": "worker", "goal": "", "cwd": work, "folder": tmp_path / "ada", "model": MODEL}
    given = {**spec, "access": access(tmp_path / "home")(fake), **fields}
    return AgentSpec.model_validate({**given, "goal": goal(given["goal"])})


async def test_a_resumed_harness_knows_what_landed_after_a_kill(tmp_path):
    delivery = Delivery(input="41", boundary="turn", text="remember heliotrope", items=())

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model)
        first, heard = ClaudeDriver(), Heard()
        await first.start(spec, heard)
        native = (await heard.until(Ready)).native
        await first.deliver(delivery)
        await heard.until(TurnEnded)
        record = Record.read(spec.folder)
        assert record is not None
        os.killpg(record.pid, signal.SIGKILL)
        await heard.until(Exited)
        await first.stop(2.0)

        second, heard = ClaudeDriver(), Heard()
        await second.start(spec.model_copy(update={"resume": native}), heard)
        await heard.until(Ready)
        try:
            assert await second.reconcile("41") == "landed"
            assert await second.reconcile("42") == "unknown"
        finally:
            await second.stop(2.0)


async def test_a_compaction_reports_its_summary_and_its_model_call(tmp_path):
    delivery = Delivery(input="41", boundary="turn", text="/compact", items=())

    async with FakeModel("one", "<summary>the summary</summary>") as model:
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="say one"), heard)
        await heard.until(TurnEnded)
        try:
            await driver.deliver(delivery)
            compacted = await heard.until(Compacted)
            called = await heard.until(ModelCall, lambda call: call.purpose == "compaction")
            await heard.until(TurnEnded, lambda _: len(heard.of(TurnEnded)) == 2)
        finally:
            await driver.stop(2.0)

    assert compacted.forgotten is None
    assert compacted.summary is not None and "the summary" in compacted.summary
    assert called.call_id is None
    assert sum(usage.tokens or 0 for usage in heard.of(Usage)) == len(model.calls) * (INPUT_TOKENS + OUTPUT_TOKENS)


async def test_effort_reaches_the_model_and_one_the_harness_would_drop_is_refused(tmp_path):
    async with FakeModel("ok") as model:
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, goal="go", effort="low"), heard)
        await heard.until(TurnEnded)
        await driver.stop(2.0)

        refused = ClaudeDriver()
        with pytest.raises(DriverError, match="bogus was asked for"):
            await refused.start(on_fake_model(tmp_path, model, effort="bogus"), Heard())
        await refused.stop(2.0)

    assert model.calls[0].json["output_config"]["effort"] == "low"


async def test_with_no_model_on_a_login_of_its_own_ready_says_the_harness_s_default(tmp_path):
    async with FakeModel() as model:
        given = {name: secret.reveal() for name, secret in access(tmp_path / "home")(model).items()}
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(on_fake_model(tmp_path, model, model=None, access={}, env=given), heard)
        ready = await heard.until(Ready)
        await driver.stop(2.0)

    assert ready.effective_model is not None
    assert not model.calls


async def test_a_harness_signed_in_nowhere_says_so_when_its_turn_ends(tmp_path):
    variables = {"HOME": str(tmp_path / "home"), "CLAUDE_CONFIG_DIR": str(tmp_path / "home" / ".claude")}
    (tmp_path / "home").mkdir()

    async with FakeModel() as model:
        spec = on_fake_model(tmp_path, model, access={}, env=variables, goal="go")
        driver, heard = ClaudeDriver(), Heard()
        await driver.start(spec, heard)
        ended = await heard.until(TurnEnded)
        await driver.stop(2.0)

    assert "Not logged in" in ended.reason
    assert not [item for item in heard.of(Item) if item.call_id is not None]


async def test_a_tail_of_live_text_joined_to_what_was_committed_is_the_text(tmp_path, monkeypatch):
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.a_tail_joined_to_what_was_committed_is_the_text(team, tmp_path)


async def test_stop_below_stops_the_turns_of_a_lead_and_its_child_and_keeps_both(tmp_path, monkeypatch):
    async with FakeModel([Stall()]) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.stop_below_stops_the_turns_of_a_lead_and_its_child_and_keeps_both(team, tmp_path, model)


async def test_an_interrupt_under_a_tokens_limit_leaves_the_session_to_go_on(tmp_path, monkeypatch):
    async with FakeModel([Stall()], "carried on") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.an_interrupt_under_a_tokens_limit_leaves_the_session_to_go_on(team, tmp_path, model)


async def test_a_spawn_carries_the_anchor_of_the_call_that_made_it(tmp_path, monkeypatch):
    """The spawn's anchor is the `native_id` of the tool item of the call that made it, so a client can join the two."""
    async with FakeModel(ToolCall("mcp__ph__agent_spawn", clients.SPAWN, id="toolu_spawn"), "spawned it") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        spawned, under = await clients.a_spawn_and_the_call_that_made_it(team, tmp_path)

    assert under and {item.data["native_id"] for item in under} == set(spawned.native.values())


async def test_a_read_is_confirmed_by_the_tool_item_that_holds_its_result_and_the_launch_by_the_first_input(
    tmp_path, monkeypatch
):
    async with FakeModel(ToolCall("mcp__ph__message_read", {"after": 0}, id="toolu_read"), "read it") as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        read, confirmations = await clients.a_read_and_what_confirmed_it(team, tmp_path)

    hows = {event.data["how"]: event.data for event in confirmations}
    assert read.native == {"claudecode/toolUseId": "toolu_read"}
    assert (hows["read"]["input"], hows["read"]["evidence"], hows["read"]["native_id"]) == (
        read.seq,
        "tool_item",
        "toolu_read",
    )
    assert (hows["wake"]["evidence"], hows["launch"]["evidence"]) == ("command_lifecycle", "command_lifecycle")


async def test_a_cited_write_is_traced_to_the_model_call_that_chose_it(tmp_path, monkeypatch):
    """Claude Code's tool id joins its tool item and that item's call, so each answer about the write stops at that
    call, and the read before it was confirmed by its own tool item below it."""
    read = ToolCall("mcp__ph__message_read", {"after": 0}, id="toolu_read")
    replies = (read, ToolCall("mcp__ph__message_send", clients.CITING, id="toolu_send"), "answered")
    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        traced = await clients.a_read_then_a_cited_write(team, tmp_path)

    clients.hold_their_bounds(traced, "call")
    made = traced.lineage.made
    assert made.anchor is not None and (made.anchor.key, made.anchor.id) == ("claudecode/toolUseId", "toolu_send")
    assert made.item is not None and made.call == traced.lineage.bound.call
    assert [(edge.how, edge.confirmed and edge.confirmed.evidence) for edge in traced.exposure.edges] == [
        ("wake", "command_lifecycle"),
        ("read", "tool_item"),
    ]


async def test_the_tui_shows_the_call_that_chose_a_cited_write_and_what_its_citer_was_handed(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    read = ToolCall("mcp__ph__message_read", {"after": 0}, id="toolu_read")
    replies = (read, ToolCall("mcp__ph__message_send", clients.CITING, id="toolu_send"), "answered")
    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        lines = await clients.the_tui_shows_where_a_cited_write_came_from(team, tmp_path)

    (chosen,) = [line for line in lines if line.text.startswith("chosen by the model call ")]
    (bound,) = [line for line in lines if line.text.startswith("lineage read at head ")]
    (declared,) = [line for line in lines if line.kind == "declared"]
    assert chosen.text.endswith(", of claudecode/toolUseId toolu_send") and chosen.ref is not None
    assert f"counting what was handed over below the model call {chosen.ref} that chose it" in bound.text
    assert declared.ref == clients.CITED and declared.text.startswith(f"{clients.CITED} by @you: ")
    assert "seen: wake" in declared.text and "its result returned to its harness, under toolu_read" in declared.text


async def test_a_tool_item_names_the_call_its_report_names_and_opens_the_write_its_command_made(tmp_path, monkeypatch):
    """Claude Code reports the answer as a tool item in bob's transcript, under the id the answer's command came with,
    so its panel joins the call that chose it and opens the answer, and says no id is missing."""
    read = ToolCall("mcp__ph__message_read", {"after": 0}, id="toolu_read")
    replies = (read, ToolCall("mcp__ph__message_send", clients.CITING, id="toolu_send"), "answered")
    async with FakeModel(*replies) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        lines, call, written = await clients.a_tool_item_and_what_its_command_made(team, tmp_path)

    (chosen,) = [line for line in lines if line.text.startswith("chosen by the model call ")]
    (made,) = [line for line in lines if " its agent's command made " in line.text]
    assert chosen == Line("", f"chosen by the model call {call}, which its harness's report of it names", call)
    assert made == Line("", f"under tool call toolu_send, its agent's command made {written}", written)
    assert not [line for line in lines if "no tool call's id came with it" in line.text]


async def test_the_tui_sends_from_its_composer_and_draws_the_reply_once(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await clients.the_tui_sends_from_its_composer_and_draws_the_reply_once(team, tmp_path)


async def test_claude_resumes_in_its_worktree(tmp_path, monkeypatch):
    """It commits in its worktree, its runtime is killed, and it resumes there: the same folder, the same branch."""
    repo = repository(tmp_path / "repo", monkeypatch)
    async with FakeModel(*worktrees.replies(shell)) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        await worktrees.commits_is_killed_and_resumes_in_its_worktree(team, tmp_path, repo)
