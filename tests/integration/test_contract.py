"""The hand-off: a managed session, run as a training authority runs one, with no training system behind it.

A test-local authority admits each agent through FakeModel acting as a gateway, on a bearer of its own, with the
environment's tools and compaction headers. A program opens the session on a repository with one commit, checked for
training before any harness launches, and drives it as a training system does. Then, with no runtime, the record says
what can train, and rewards and credit go in beside it. ScriptedDriver runs it in the fast pass, and pi and OpenHands,
each on its real binary or SDK, in the slow pass.
"""

import itertools
import shutil
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import ConfigError, Refused, Session, Team
from platoon_harness.config import Secret, forms
from platoon_harness.credit import PROPAGATE, propagate
from platoon_harness.drivers.levels import CHECKED, Conformance
from platoon_harness.primitives import CallEligibility
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, Gateway, SpawnRequest
from platoon_harness.runtime.paths import write_conformance
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

pytestmark = pytest.mark.timeout(1800)

AGENTS = ("alice", "bob")
PROGRAM = "program:trainer"
STATUSES = ("invalid", "error", "timeout", "cancelled")


@dataclass(frozen=True)
class Harness:
    """What a role's `harness` names, what the model says in each agent's one turn, which ends on a compaction its
    harness made, how a result that proves it is kept, and how long a wait on it may take."""

    named: str
    replies: Sequence[Any]
    proves: Callable[[Path], Awaitable[Conformance]]
    seconds: float = support.SECONDS


def _scripted() -> Harness:
    turn = [Call(f"mcp__environment__{ENVIRONMENT_TOOL}", {"note": "looked"}), AskModel(), Compact()]
    made = support.harness(lambda: ScriptedDriver(itertools.repeat(turn)))
    return Harness(
        made, (), lambda folder: check_driver(lambda: ScriptedDriver(every_turn_asks_the_model()), folder=folder)
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
        return Admission(
            token=Secret(f"token-{len(self.admitted)}"), access=gateway, backend={"agent_id": f"id-{spawn.agent}"}
        )

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        self.told.append((agent, outcome))


def bearer_of(agent: str) -> str:
    return f"bearer-of-{agent}"


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
            first, *rest = recipients
            await session.cancel_agent(first)
            for agent in rest:
                await session.retire(agent)
            said = [row["said"] for row in await session.agents() if f"@{row['agent']}" in recipients]
            await session.close_episode(based_on=said)
            if (await session.status())["state"] == "open":  # `settled` closes it at its `until`.
                await session.close()

        with pytest.raises(ConfigError) as unproven:
            await Session.start(team, name="again", root=tmp_path / "bare", **start)

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
    assert viewing.value.refusal.code == "not_permitted"
    making = "doctor --check" if harness.named in CHECKED else "write_conformance"
    assert making in str(unproven.value)
    credited = [row for row in await history.annotations() if row.producer == PROPAGATE]
    assert {row.status for row in await history.annotations()} == {"scored", *STATUSES}
    assert len(credited) == len(AGENTS) and {row.status for row in credited} == {"scored"}
    told = {agent.agent: outcome for agent, outcome in authority.told}
    assert {agent: outcome.status for agent, outcome in told.items()} == {"alice": "cancelled", "bob": "retired"}
    assert all(outcome.report for outcome in told.values())
