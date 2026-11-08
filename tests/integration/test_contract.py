"""The hand-off: a managed session, run as a training authority runs one, with no training system behind it.

A test-local authority admits each agent through FakeModel acting as a gateway, on a bearer of its own, with the
environment's tools and compaction headers. A program opens the session on a repository with one commit, checked for
training before any harness launches, and drives it as a training system does. Then, with no runtime, the record says
what can train, and rewards and credit go in beside it. ScriptedDriver runs it in the fast pass, and pi and OpenHands,
each on its real binary or SDK, in the slow pass.

The same session with one agent isolated, confined by the `bwrap` extension, still reaches its gateway on loopback. A
harness in the runtime's own process cannot be confined, so a scripted one on the wire runs it beside pi and OpenHands,
in the slow pass, as every session that confines one is.
"""

import contextlib
import itertools
import shutil
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from platoon_harness import ConfigError, Refused, Session, Team
from platoon_harness.config import Secret, forms
from platoon_harness.credit import PROPAGATE, propagate
from platoon_harness.drivers.env import tmpdir
from platoon_harness.drivers.levels import CHECKED, Conformance
from platoon_harness.drivers.process import Record
from platoon_harness.drivers.wire import WireDriver
from platoon_harness.primitives import CallEligibility
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, Gateway, SpawnRequest
from platoon_harness.runtime.opening import make_driver
from platoon_harness.runtime.paths import agent_folder, write_conformance
from platoon_harness.testing import (
    ENVIRONMENT_TOOL,
    AskModel,
    Call,
    Compact,
    FakeModel,
    Overflow,
    ScriptedDriver,
    Text,
    ToolCall,
    check_driver,
    check_harness,
    every_turn_asks_the_model,
)

from ..unit.runtime import support
from ..unit.runtime.gitting import repository
from ..unit.runtime.support import in_state, of_type, until
from .scripts import wire

pytestmark = pytest.mark.timeout(1800)

AGENTS = ("alice", "bob")
PROGRAM = "program:trainer"
STATUSES = ("invalid", "error", "timeout", "cancelled")


@dataclass(frozen=True)
class Harness:
    """What a role's `harness` names, what the model says in each agent's one turn, which ends on a compaction its
    harness made, how a result that proves it is kept, and how long a wait on it may take."""

    named: str | dict[str, Any]
    replies: Sequence[Any]
    proves: Callable[[Path], Awaitable[Conformance]]
    seconds: float = support.SECONDS


def _scripted() -> Harness:
    turn = [Call(f"mcp__environment__{ENVIRONMENT_TOOL}", {"note": "looked"}), AskModel(), Compact()]
    made = support.harness(lambda: ScriptedDriver(itertools.repeat(turn)))
    return Harness(
        made, (), lambda folder: check_driver(lambda: ScriptedDriver(every_turn_asks_the_model()), folder=folder)
    )


def _wire() -> Harness:
    """A scripted harness on the wire, which says where it is installed, as an isolation needs to confine it."""
    return Harness(
        wire("sealed"),
        (),
        lambda folder: check_driver(lambda: WireDriver(wire("sealed_checked")["command"]), folder=folder, timeout=20),
    )


def _pi() -> Harness:
    """A long answer that calls the environment's tool, then a refusal of the next request as too long, which pi meets
    by compacting, through our extension, and retrying."""
    long = Text(" ".join(["x" * 1000] * 100))
    replies = [
        [long, ToolCall(f"mcp__environment__{ENVIRONMENT_TOOL}", {"note": "looked"})],
        Overflow(),
        "the summary",
        "done",
    ]
    return Harness("pi", replies, lambda folder: check_harness("pi", folder), seconds=120.0)


def _openhands() -> Harness:
    """Forty calls of the environment's tool, past which OpenHands' condenser forgets, with the compaction headers. Each
    agent's turn has taken a little over 300 seconds beside another slow test, so a wait on it may take twice that."""
    calls = [ToolCall(f"environment_{ENVIRONMENT_TOOL}", {"note": f"step {n}"}, id=f"call_{n}") for n in range(40)]
    return Harness(
        "openhands", [*calls, "the summary", "done"], lambda folder: check_harness("openhands", folder), 600.0
    )


class Training:
    """An authority as a training system's: each agent through the gateway on a bearer and a backend id of its own,
    and told of each end."""

    def __init__(self, model: FakeModel) -> None:
        self.model = model
        self.admitted: list[SpawnRequest] = []
        self.gateways: dict[str, Gateway] = {}
        self.told: list[tuple[AgentRef, AgentOutcome]] = []

    async def admit(self, spawn: SpawnRequest) -> Admission:
        self.admitted.append(spawn)
        self.gateways[spawn.agent] = gateway = self.model.gateway(bearer_of(spawn.agent))
        return Admission(token=Secret(token_of(spawn.agent)), access=gateway, backend={"agent_id": f"id-{spawn.agent}"})

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        self.told.append((agent, outcome))


def bearer_of(agent: str) -> str:
    return f"bearer-of-{agent}"


def token_of(agent: str) -> str:
    """The agent's token on the session's tool plane."""
    return f"token-of-{agent}"


def trainable_team(harness: str) -> Team:
    roles = {name: {"harness": harness, "approvals": "allow"} for name in AGENTS}
    return Team.model_validate({"roles": roles})


async def every_call(session: Session, agent: str) -> list[CallEligibility]:
    answer = await session.eligibility(f"@{agent}", "task")
    calls = list(answer.calls)
    while answer.cursor is not None:
        answer = await session.eligibility(f"@{agent}", "task", after=answer.cursor)
        calls += answer.calls
    return calls


def holding(folder: Path, secrets: Sequence[str]) -> list[Path]:
    """Each file under `folder` that holds one of `secrets`, in any form text may carry it."""
    held = {form for secret in secrets for form in forms(Secret(secret))}
    found = (path for path in folder.rglob("*") if path.is_file() and not path.is_symlink())
    return [path for path in found if any(form in path.read_bytes() for form in held)]


SCRATCH_AND_CREDENTIALS = {"pi": ["pi/auth.json", "tmp"], "openhands": ["tmp"]}
"""What of an agent's folder its harness kept as scratch or as a credential its driver names, when it was idle."""


def kept(session: Path, agent: str, team: Team, cwd: Path) -> list[str]:
    """What of an agent's folder in `session` is its harness's scratch, or is where its driver says it keeps a
    credential."""
    folder = agent_folder(session, agent)
    named = make_driver(team.roles[agent], cwd).describe().credentials
    return sorted(str(path) for path in (tmpdir(Path()), *named) if (folder / path).exists())


async def stopped(session: Session) -> list[Any]:
    """Each agent's stop that has finished."""
    return [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "stop"]


@pytest.mark.parametrize(
    "made",
    [
        pytest.param(_scripted, id="scripted"),
        pytest.param(_pi, id="pi", marks=pytest.mark.slow),
        pytest.param(_openhands, id="openhands", marks=pytest.mark.slow),
    ],
)
async def test_a_managed_session_runs_as_a_training_authority_drives_it(tmp_path, monkeypatch, made):
    harness: Harness = made()
    if harness.named == "pi" and shutil.which("pi") is None:
        pytest.skip("pi is not installed, so the contract met no real harness here")
    monkeypatch.setattr(support, "SECONDS", harness.seconds)
    root, cwd = tmp_path / "root", repository(tmp_path / "work", monkeypatch)
    write_conformance(root, await harness.proves(tmp_path / "check"))
    team = trainable_team(harness.named)

    async with FakeModel() as model:
        authority = Training(model)
        start: dict[str, Any] = {"principal": PROGRAM, "authority": authority, "trainable": True, "cwd": cwd}
        async with Session.start(team, name="rollout", root=root, **start) as session:
            recipients = team.recipients()
            for agent in recipients:
                await in_state(session, agent[1:], "idle")
            await session.open_episode("task")
            guest = await Session.attach("rollout", root=root)
            with pytest.raises(Refused) as viewing:
                await guest.send("@alice", "a word from a guest")
            await guest.leave()
            for number, agent in enumerate(recipients, 1):
                model.script(harness.replies)
                await session.send(agent, "the task")
                await until(
                    lambda: of_type(session, "context.compacted"), session, lambda found, n=number: len(found) == n
                )
                await in_state(session, agent[1:], "idle")
            await session.settled()
            before = {agent: kept(session.folder, agent, team, cwd) for agent in AGENTS}
            first, *rest = recipients
            await session.cancel_agent(first)
            for agent in rest:
                await session.retire(agent)
            await until(lambda: stopped(session), session, lambda found: len(found) == len(recipients))
            said = [row["said"] for row in await session.agents() if f"@{row['agent']}" in recipients]
            await session.close_episode(based_on=said)
            if (await session.status())["state"] == "open":  # `settled` closes it at its `until`.
                await session.close()

        with pytest.raises(ConfigError) as unproven:
            await Session.start(team, name="again", root=tmp_path / "bare", **start)

    copied = tmp_path / "copy" / "sessions" / "rollout"
    shutil.copytree(root / "sessions" / "rollout", copied)
    history = await Session.attach("rollout", root=root)
    head = await history.head()
    await history.annotate(
        "episode/task@2",
        kind="reward",
        producer="environment",
        producer_version="1",
        scope="team",
        status="scored",
        value=1.0,
        head_seq=head,
    )
    for status in STATUSES:
        first = await of_type(history, "agent.started")
        await history.annotate(
            f"{first[0].stream}@{first[0].version}",
            kind="reward",
            producer=f"grader-{status}",
            producer_version="1",
            scope="local",
            status=status,
            head_seq=head,
        )
    await propagate(history, "task", judge=None, retained=0.5)

    bearers = {agent: bearer_of(agent) for agent in AGENTS}
    calls = {agent: await every_call(history, agent) for agent in AGENTS}
    for agent in AGENTS:
        eligible = await history.eligibility(f"@{agent}", "task")
        assert (eligible.attribution, eligible.verdict, eligible.reasons) == ("exact", "eligible", ()), eligible
        assert all(call.verdict == "eligible" for call in calls[agent]), calls[agent]
    headers = authority.gateways["alice"].compaction_headers
    by_id = {request.response_id: request for request in model.calls if request.response_id}
    for agent, made_calls in calls.items():
        for call in made_calls:
            if call.call_id is not None:
                assert by_id[call.call_id].bearer == bearers[agent]
                assert by_id[call.call_id].carries(headers) == (call.purpose == "compaction")
    compacting = [request for request in model.calls if request.carries(headers)]
    reported = {call.call_id for agent in AGENTS for call in calls[agent] if call.purpose == "compaction"}
    assert compacting and {request.response_id for request in compacting} <= reported
    assert {request.bearer for request in model.calls} == set(bearers.values())
    assert {request.bearer for request in model.tool_calls} == set(bearers.values())
    assert holding(root / "sessions", list(bearers.values())) == [] and holding(cwd, list(bearers.values())) == []
    assert before == {agent: SCRATCH_AND_CREDENTIALS.get(str(harness.named), []) for agent in AGENTS}
    assert {agent: kept(copied, agent, team, cwd) for agent in AGENTS} == {agent: [] for agent in AGENTS}
    assert viewing.value.refusal.code == "not_permitted"
    making = "doctor --check" if harness.named in CHECKED else "write_conformance"
    assert making in str(unproven.value)
    credited = [row for row in await history.annotations() if row.producer == PROPAGATE]
    targets = {row.target: (await history.lineage(row.target)).event for row in credited}
    spans = {agent: {span.ref for span in (await history.spans(f"@{agent}")).spans} for agent in AGENTS}
    assert {row.status for row in await history.annotations()} == {"scored", *STATUSES}
    assert {row.status for row in credited} == {"scored"}
    assert sorted((targets[row.target].agent, targets[row.target].type) for row in credited) == [
        (agent, kind) for agent in AGENTS for kind in ("agent.started", "model.called")
    ]
    named = [(targets[row.target].agent, row.target) for row in credited if targets[row.target].type == "model.called"]
    assert all(target in spans[agent or ""] for agent, target in named)
    told = {agent.agent: outcome for agent, outcome in authority.told}
    assert {agent: outcome.status for agent, outcome in told.items()} == {"alice": "cancelled", "bob": "retired"}
    assert all(outcome.report for outcome in told.values())


def files_of(folder: Path, *besides: Path) -> dict[Path, bytes]:
    """What each file under `folder` holds, but those under `besides`."""
    found = (path for path in folder.rglob("*") if path.is_file() and not path.is_symlink())
    return {path: path.read_bytes() for path in found if not any(path.is_relative_to(other) for other in besides)}


def under(pid: int) -> list[int]:
    """`pid`, then every process below it, as their parents are now."""
    below: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        with contextlib.suppress(OSError):
            if entry.name.isdecimal():
                parent = int(entry.joinpath("stat").read_text().rpartition(")")[2].split()[1])
                below.setdefault(parent, []).append(int(entry.name))
    found, left = [], [pid]
    while left:
        found.append(at := left.pop())
        left += below.get(at, [])
    return found


def command_lines(folder: Path) -> list[bytes]:
    """The command line of the process group a harness leads, as the agent's folder records it, then of each process
    below it."""
    record = Record.read(folder)
    assert record is not None
    lines = []
    for pid in under(record.pid):
        with contextlib.suppress(OSError):
            lines.append(Path(f"/proc/{pid}/cmdline").read_bytes())
    return lines


@pytest.mark.parametrize(
    "made",
    [
        pytest.param(_wire, id="wire", marks=pytest.mark.slow),
        pytest.param(_pi, id="pi", marks=pytest.mark.slow),
        pytest.param(_openhands, id="openhands", marks=pytest.mark.slow),
    ],
)
async def test_an_isolated_sealed_agent_reaches_its_gateway_on_loopback(tmp_path, monkeypatch, made):
    """Confined by `bwrap`, which binds only its folder to write and passes its environment, an agent launched sealed
    calls its gateway on loopback with its own bearer, compacts with the headers and reports each compaction by its id,
    and is eligible from the result kept where it ran unconfined, and the closed session says it ran `isolated`. No form
    of its bearer or its token is in any file or in the command line of any process of its harness, so its environment
    alone carried them, and nothing outside the session's folder was written."""
    harness: Harness = made()
    if harness.named == "pi" and shutil.which("pi") is None:
        pytest.skip("pi is not installed, so no isolated harness met its gateway here")
    support.bubblewrap()
    monkeypatch.setattr(support, "SECONDS", harness.seconds)
    root, cwd = tmp_path / "root", repository(tmp_path / "work", monkeypatch)
    write_conformance(root, await harness.proves(tmp_path / "check"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    alice = {"harness": harness.named, "workspace": "isolated", "approvals": "allow"}
    team = Team.model_validate({"extensions": ["bwrap"], "roles": {"alice": alice}})
    before = files_of(tmp_path)

    async with FakeModel() as model:
        authority = Training(model)
        start: dict[str, Any] = {"principal": PROGRAM, "authority": authority, "trainable": True, "cwd": cwd}
        async with Session.start(team, name="rollout", root=root, **start) as session:
            await in_state(session, "alice", "idle")
            await session.open_episode("task")
            model.script(harness.replies)
            await session.send("@alice", "the task")
            await until(lambda: of_type(session, "context.compacted"), session)
            await in_state(session, "alice", "idle")
            folder = agent_folder(session.folder, "alice")
            lines = command_lines(folder)
            await session.settled()
            await session.retire("@alice")
            await session.close_episode(based_on=[row["said"] for row in await session.agents()])
            if (await session.status())["state"] == "open":
                await session.close()

    history = await Session.attach("rollout", root=root)
    started = await of_type(history, "agent.started")
    eligible, calls = await history.eligibility("@alice", "task"), await every_call(history, "alice")
    argv = lines[0].decode().split("\0")[:-1]
    gateway, bearer, token = authority.gateways["alice"], bearer_of("alice"), token_of("alice")
    held = {form for secret in (bearer, token) for form in forms(Secret(secret))}
    by_id = {request.response_id: request for request in model.calls if request.response_id}
    compacting = [request for request in model.calls if request.carries(gateway.compaction_headers)]
    assert Path(argv[0]).name == "bwrap"
    assert [argv[at + 1] for at, part in enumerate(argv) if part == "--bind"] == [str(folder.resolve())]
    assert [(event.data["assurance"], event.data["levels"]["trainable"]["state"]) for event in started] == [
        ("isolated", "met")
    ]
    assert urlsplit(gateway.origin).hostname == "127.0.0.1"
    assert {request.bearer for request in (*model.calls, *model.tool_calls)} == {bearer} and model.tool_calls
    for call in calls:
        if call.call_id is not None:
            assert by_id[call.call_id].carries(gateway.compaction_headers) == (call.purpose == "compaction")
    reported = {call.call_id for call in calls if call.purpose == "compaction"}
    assert compacting and {request.response_id for request in compacting} <= reported
    assert (eligible.attribution, eligible.verdict, eligible.reasons) == ("exact", "eligible", ()), eligible
    assert all(call.verdict == "eligible" for call in calls), calls
    assert holding(tmp_path, [bearer, token]) == [] and len(lines) > 1
    assert not [line for line in lines if any(form in line for form in held)]
    assert files_of(tmp_path, root / "sessions") == before
