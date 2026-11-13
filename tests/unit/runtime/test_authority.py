"""The authority contract a training system's authority builds on: what it is asked, what it gives, and what the record
keeps of it."""

import asyncio
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import pytest
from pydantic import ValidationError

from platoon_harness import Refused, Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers import AgentSpec, Capabilities, Gateway, Item, Ready, Reporter
from platoon_harness.kernel import is_held
from platoon_harness.runtime import Admission, LocalAuthority, SpawnRequest
from platoon_harness.testing import Exit, Say, ScriptedDriver

from .support import harness, in_state, journal, of_type, state_of, until
from .training import IN_ENVIRONMENT, ORIGIN, SEALED, UNSEALED, Gating, Sealed

pytestmark = pytest.mark.timeout(30)


def team_on(make: Any, **role: Any) -> Team:
    return Team.model_validate({"roles": {"bob": {"harness": harness(make), **role}}})


def starting(specs: list[AgentSpec], capabilities: Capabilities = SEALED) -> Callable[[], Sealed]:
    """A sealed harness of `capabilities` that keeps the spec of each harness it starts."""

    class Starting(Sealed):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            specs.append(spec)
            await super().start(spec, report)

    return lambda: Starting(capabilities=capabilities)


async def admitted(session: Session) -> dict[str, Any]:
    """Each agent's admit result, as its `effect.finished` records it."""
    finished = await of_type(session, "effect.finished")
    return {event.agent: event.data["result"] for event in finished if event.data["kind"] == "admit"}


async def test_the_admit_result_records_backend_ids_and_never_a_key(tmp_path):
    team = team_on(Sealed)
    authority = Gating(team)
    async with Session.start(team, authority=authority, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        results = await admitted(session)
        text = json.dumps([event.model_dump(mode="json") for event in await journal(session)])

    assert results == {"bob": {"agent_id": "id-of-bob"}}
    assert "bearer-of-bob" not in text and "token-1" not in text


@pytest.mark.parametrize(
    "backend",
    [
        {"agent_id": "the-key"},
        {"agent_id": "the bearer"},
        {"route": "https://gateway/s/the%20bearer/v1"},
        {"agent_id": "dGhlIGJlYXJlcg"},
        {"the bearer": "a1"},
    ],
)
def test_an_admission_whose_backend_names_a_key_is_refused(backend):
    """A secret of its own in a backend's id or name, in any form, would reach the journal and so the export."""
    gateway = Gateway(origin=ORIGIN, bearer=Secret("the bearer"), model="m")

    with pytest.raises(ValidationError, match="never a key") as refused:
        Admission(token=Secret("the-key"), access=gateway, backend=backend)

    assert "the-key" not in str(refused.value) and "the bearer" not in str(refused.value)


def test_a_gateway_admission_names_the_backend_ids_of_its_agent():
    gateway = Gateway(origin=ORIGIN, bearer=Secret("b"), model="m")

    with pytest.raises(ValidationError, match="backend's ids"):
        Admission(token=Secret("t"), access=gateway)


@pytest.mark.parametrize(
    "origin", ["http://127.0.0.1:9/v1", "http://127.0.0.1:9/s/secret", "http://user:pw@host", "http://h?k=v", "file:/x"]
)
def test_a_gateway_s_origin_is_an_origin_and_nothing_more(origin):
    with pytest.raises(ValidationError, match="gateway's URL"):
        Gateway(origin=origin, bearer=Secret("b"), model="m")


async def test_the_gateway_bearer_is_masked_in_every_form(tmp_path):
    """Whatever a harness says of its bearer, raw, JSON-escaped or percent-encoded, reaches the journal masked."""
    bearer = 'b/e+a r"er'
    forms = (bearer, json.dumps(bearer)[1:-1], quote(bearer, safe=""))

    class Telling(Sealed):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await super().start(spec, report)
            await report(Item(kind="message", gist=" ".join(forms)[:280], body=" | ".join(forms)))

    class Plain(Gating):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            admission = await super().admit(spawn)
            gateway = Gateway(origin=ORIGIN, bearer=Secret(bearer), model="m")
            return admission.model_copy(update={"access": gateway})

    team = team_on(Telling)
    async with Session.start(team, authority=Plain(team), root=tmp_path) as session:
        [item] = await until(lambda: of_type(session, "item.recorded"), session)
        body = (await session.get_body(item.data["body"])).decode()
        text = json.dumps([event.model_dump(mode="json") for event in await journal(session)])

    assert item.gist == "*** *** ***" and body == "*** | *** | ***"
    assert not any(form in text for form in forms)


async def test_a_session_whose_admissions_name_backend_ids_is_never_resumed(tmp_path):
    """Its agents' keys went with the authority that admitted them, so a resume would run them on nothing of theirs: it
    is refused before anything runs, and the session stays history."""
    team = team_on(Sealed)
    async with Session.start(team, name="s", authority=Gating(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
    async with Session.attach("s", root=tmp_path) as history:
        head = await history.head()

    with pytest.raises(Refused, match="never resumed: an authority that has gone admitted bob") as refused:
        await Session.resume("s", root=tmp_path)

    async with Session.attach("s", root=tmp_path) as history:
        assert await history.head() == head
    assert refused.value.refusal.code == "unsupported"
    assert not is_held(tmp_path / "sessions" / "s")


async def test_an_agent_is_admitted_with_its_parent_and_its_goal(tmp_path):
    team = team_on(Sealed)
    authority = Gating(team)
    async with Session.start(team, authority=authority, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.spawn("ada", "bob", "Fix the test")
        await in_state(session, "ada", "idle")

    assert [(spawn.agent, spawn.parent, spawn.goal) for spawn in authority.asked] == [
        ("bob", None, ""),
        ("ada", "human:you", "Fix the test"),
    ]


async def test_a_resumed_admission_keeps_its_model_access_and_never_mints(tmp_path):
    """A harness that exits on its own rests its agent, and the handover that brings it back asks its authority for
    its access again as a resume, which records no second admission."""
    specs: list[AgentSpec] = []
    turns = iter([[Exit("killed by signal 9")], [Say("back")]])

    class Kept(Sealed):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            specs.append(spec)
            await super().start(spec, report)

    team = team_on(lambda: Kept(turns))
    authority = Gating(team)
    async with Session.start(team, authority=authority, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.lost"), session)
        await session.send("@bob", "again")
        await until(lambda: of_type(session, "item.recorded"), session)
        results = await admitted(session)

    assert [(spawn.resumed, spawn.parent, spawn.goal) for spawn in authority.asked] == [
        (False, None, ""),
        (True, None, ""),
    ]
    assert [spec.access.bearer.reveal() for spec in specs if isinstance(spec.access, Gateway)] == ["bearer-of-bob"] * 2
    assert results == {"bob": {"agent_id": "id-of-bob"}}


@pytest.mark.parametrize(
    ("bearers", "ids", "why"),
    [
        (("bearer-1", "bearer-2"), ("id-1", "id-2"), "bob came back under other backend ids than its admit recorded"),
        (("bearer-1", "bearer-2"), ("id-1", "id-1"), "bob came back on other model access than it was admitted on"),
    ],
)
async def test_a_resumed_admission_that_mints_anew_loses_its_agent(tmp_path, bearers, ids, why):
    """An authority that mints again when a harness comes back would put its calls on an identity the record does not
    name, so the agent is lost, saying why, and its harness never comes back on that access."""
    specs: list[AgentSpec] = []
    turns = iter([[Exit("killed by signal 9")], [Say("back")]])

    class Kept(Sealed):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            specs.append(spec)
            await super().start(spec, report)

    class Minting(Gating):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            self.asked.append(spawn)
            n = len(self.asked) - 1
            gateway = Gateway(origin=ORIGIN, bearer=Secret(bearers[n]), model=self.model)
            return Admission(token=Secret(f"token-{n}"), access=gateway, backend={"agent_id": ids[n]})

    team = team_on(lambda: Kept(turns))
    authority = Minting(team)
    async with Session.start(team, authority=authority, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.lost"), session)
        await session.send("@bob", "again")
        await in_state(session, "bob", "ended")

        async def stopped() -> list[Any]:
            return [e for e in await of_type(session, "effect.finished") if e.data["kind"] == "stop"]

        # The stop effect's `finally` tells the authority the agent is lost, so wait for the stop to finish.
        await until(stopped, session)
        row = (await session.ending()).agents[0]
        results = await admitted(session)

    assert [spawn.resumed for spawn in authority.asked] == [False, True]
    assert [spec.access.bearer.reveal() for spec in specs if isinstance(spec.access, Gateway)] == ["bearer-1"]
    assert (row["status"], row["reason"]) == ("lost", why)
    assert results == {"bob": {"agent_id": "id-1"}}
    assert [(agent.agent, outcome.status) for agent, outcome in authority.told] == [("bob", "lost")]


async def test_two_agents_on_one_key_are_refused(tmp_path):
    """A gateway records every call on a bearer as one agent's, so a second agent admitted on a bearer another holds
    fails its spawn, in words that name no key, whatever backend ids it names."""

    class Sharing(Gating):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            admission = await super().admit(spawn)
            gateway = Gateway(origin=ORIGIN, bearer=Secret("one-shared-bearer"), model=self.model)
            return admission.model_copy(update={"access": gateway})

    team = team_on(Sealed)
    async with Session.start(team, authority=Sharing(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.spawn("ada", "bob")
        await in_state(session, "ada", "ended")
        rows = {row["agent"]: row for row in (await session.ending()).agents}
        results = await admitted(session)

    assert rows["ada"]["status"] == "failed"
    assert rows["ada"]["reason"] == (
        "its spawn failed: ada's gateway bearer is another agent's, so no call on it is tied to one agent"
    )
    assert results == {"bob": {"agent_id": "id-of-bob"}}


async def test_a_driver_without_a_sealed_launch_refuses_a_gateway(tmp_path):
    team = team_on(lambda: ScriptedDriver(capabilities=UNSEALED))
    async with Session.start(team, authority=Gating(team), root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        row = (await session.ending()).agents[0]
        started = await of_type(session, "agent.started")

    assert row["reason"] == "its spawn failed: `scripted` has no sealed launch, which a gateway admission needs"
    assert started == []


async def test_only_a_gateway_keeps_a_harness_s_own_tools_on_a_sealed_launch(tmp_path, monkeypatch):
    """The word that a session runs in the environment, where a sealed launch keeps its harness's own tools, reaches a
    driver on its gateway alone, which only an authority gives: a team or a role that names it is refused,
    `Session.start` takes no such word, and an agent on a key, as `LocalAuthority` admits each agent of a role with an
    auth profile, or on a gateway that does not say it, is told nothing of it and starts so."""
    specs: list[AgentSpec] = []
    harnessed = harness(starting(specs, IN_ENVIRONMENT))
    for named in (
        {"roles": {"bob": {"harness": harnessed, "in_environment": True}}},
        {"roles": {"bob": {"harness": harnessed}}, "in_environment": True},
    ):
        with pytest.raises(ValidationError, match="in_environment"):
            Team.model_validate(named)
    keyed = {"harness": harnessed, "auth": "keyed", "model": "m"}
    team = Team.model_validate({"roles": {"bob": keyed}, "auth": {"keyed": {"env": ["KEY"]}}})
    with pytest.raises(TypeError, match="in_environment"):
        Session.start(team, in_environment=True)
    monkeypatch.setenv("KEY", "a-key")
    recorded = []
    for authority in (LocalAuthority(team), Gating(team), Gating(team, in_environment=True)):
        async with Session.start(team, authority=authority, root=tmp_path) as session:
            await in_state(session, "bob", "idle")
            recorded += [event.data["verified"]["in_environment"] for event in await of_type(session, "agent.started")]

    assert [isinstance(spec.access, Gateway) and spec.access.in_environment for spec in specs] == [False, False, True]
    assert recorded == [False, False, True]


@pytest.mark.parametrize(
    ("first", "why"),
    [
        (
            True,
            "ada's gateway does not say its session runs in the environment, and the first gateway this runtime "
            "admitted says so",
        ),
        (
            False,
            "ada's gateway says its session runs in the environment, and the first gateway this runtime admitted does "
            "not say so",
        ),
    ],
)
async def test_an_admission_whose_gateway_says_another_place_than_the_first_is_refused(tmp_path, first, why):
    """A session runs in one place, so its gateways say one thing: the host keeps the word of the first gateway it
    admits, and an admission whose gateway says otherwise fails its spawn, saying so, before its harness launches, and
    the agents admitted before it run on."""

    class Disagreeing(Gating):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            admission = await super().admit(spawn)
            assert isinstance(admission.access, Gateway)
            gateway = admission.access.model_copy(update={"in_environment": first == (spawn.agent == "bob")})
            return admission.model_copy(update={"access": gateway})

    specs: list[AgentSpec] = []
    team = team_on(starting(specs, IN_ENVIRONMENT))
    async with Session.start(team, authority=Disagreeing(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.spawn("ada", "bob")
        await in_state(session, "ada", "ended")
        row = next(row for row in (await session.ending()).agents if row["agent"] == "ada")
        started = await of_type(session, "agent.started")
        bob = await state_of(session, "bob")

    assert (row["status"], row["reason"]) == ("failed", f"its spawn failed: {why}: a session runs in one place")
    assert [spec.agent for spec in specs] == [event.agent for event in started] == ["bob"]
    assert bob == "idle"


SHARED = Secret("one-shared-bearer")


@pytest.mark.parametrize(
    ("first", "second", "why"),
    [
        (
            {"in_environment": True},
            {},
            "bob-2's gateway does not say its session runs in the environment, and the first gateway this runtime "
            "admitted says so: a session runs in one place",
        ),
        (
            {"bearer": SHARED},
            {"bearer": SHARED},
            "bob-2's gateway bearer is another agent's, so no call on it is tied to one agent",
        ),
    ],
    ids=["places", "a bearer"],
)
async def test_admissions_under_way_at_once_are_held_to_one_place_and_a_bearer_each(tmp_path, first, second, why):
    """Several admissions can be under way at once, as a role that starts two agents admits both together, and each is
    held all the same to what was admitted before it: of two whose gateways say different places, or share a bearer,
    the one checked second fails its spawn, saying why, and the first runs."""

    class Together(Gating):
        """Gives bob-1's gateway `first` and bob-2's `second`, and bob-2's only once bob-1's admission is under way, so
        that bob-2's is checked while bob-1's is."""

        def __init__(self, team: Team) -> None:
            super().__init__(team)
            self.under_way = asyncio.Event()

        async def admit(self, spawn: SpawnRequest) -> Admission:
            admission = await super().admit(spawn)
            assert isinstance(admission.access, Gateway)
            if spawn.agent == "bob-1":
                self.under_way.set()
            else:
                await self.under_way.wait()
            given = first if spawn.agent == "bob-1" else second
            return admission.model_copy(update={"access": admission.access.model_copy(update=given)})

    specs: list[AgentSpec] = []
    team = team_on(starting(specs, IN_ENVIRONMENT), count=2)
    # Its harness says it is signed in on a plan, which the check before the start counts, but both run on a gateway.
    async with Session.start(team, authority=Together(team), root=tmp_path, plan_login=True) as session:
        await in_state(session, "bob-1", "idle")
        await in_state(session, "bob-2", "idle", "ended")
        rows = {row["agent"]: row for row in (await session.ending()).agents}

    assert (rows["bob-2"]["status"], rows["bob-2"]["reason"]) == ("failed", f"its spawn failed: {why}")
    assert [spec.agent for spec in specs] == ["bob-1"]


async def test_a_driver_with_no_launch_in_the_environment_refuses_a_gateway_in_it(tmp_path):
    """A gateway that says its session runs in the environment goes only to a driver that declares a launch there: a
    sealed driver that does not fails its spawn, saying so, before its harness launches."""
    specs: list[AgentSpec] = []
    team = team_on(starting(specs))
    async with Session.start(team, authority=Gating(team, in_environment=True), root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        row = (await session.ending()).agents[0]
        started = await of_type(session, "agent.started")

    assert row["reason"] == "its spawn failed: `scripted` has no launch in the environment, which its gateway asks for"
    assert started == [] and specs == []


def test_an_environment_path_outside_the_environment_is_refused(tmp_path):
    """A gateway names the `PATH` the environment gives its own commands for the model's commands in the environment,
    so one that does not say its session runs there is refused it, as nothing would carry it out, a copy made without
    that check among them, which an agent's spec refuses before any driver is given it; an empty one is refused, as it
    names no folder; one that does says it."""
    path = "/usr/local/bin:/usr/bin:/bin"

    with pytest.raises(ValidationError, match="nothing would carry it out"):
        Gateway(origin=ORIGIN, bearer=Secret("b"), model="m", environment_path=path)
    with pytest.raises(ValidationError, match="its own commands, and this one is empty"):
        Gateway(origin=ORIGIN, bearer=Secret("b"), model="m", in_environment=True, environment_path="")

    gateway = Gateway(origin=ORIGIN, bearer=Secret("b"), model="m", in_environment=True, environment_path=path)
    copied = gateway.model_copy(update={"in_environment": False})
    with pytest.raises(ValidationError, match="nothing would carry it out"):
        AgentSpec(agent="bob", role="bob", cwd=tmp_path, folder=tmp_path, access=copied)
    assert gateway.environment_path == path


async def test_a_gateway_admission_is_a_gateway_login_and_no_plan_login(tmp_path):
    """Two agents of a harness signed in on a plan run headless all the same when a gateway admits them, as neither runs
    on that login."""
    team = team_on(Sealed)
    async with Session.start(team, authority=Gating(team), root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.spawn("ada", "bob")
        await in_state(session, "ada", "idle")
        started = await of_type(session, "agent.started")

    assert [(event.agent, event.data["verified"]["login"]) for event in started] == [
        ("bob", "gateway"),
        ("ada", "gateway"),
    ]
    assert all("exact data needs a gateway" not in reason for event in started for reason in reasons(event))


def reasons(started: Any) -> list[str]:
    return started.data["levels"]["trainable"]["reasons"]


async def test_the_pinned_model_is_checked_against_the_gateways(tmp_path):
    """The model a gateway serves is the one pinned: a harness that runs another fails its spawn, and so does a role
    that names another."""

    class Elsewhere(Sealed):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            await report(Ready(native="n", effective_model="some-other"))

    ran: list[str] = []
    for make, role in ((Elsewhere, {}), (Sealed, {"model": "named"})):
        team = team_on(make, **role)
        async with Session.start(team, authority=Gating(team, model="served"), root=tmp_path) as session:
            await in_state(session, "bob", "ended")
            ran.append((await session.ending()).agents[0]["reason"])

    assert ran == [
        "its spawn failed: it runs some-other, and served is pinned",
        "its spawn failed: its role pins named, and its gateway serves served",
    ]


async def test_a_gateway_s_model_is_the_one_its_harness_is_given(tmp_path):
    specs: list[AgentSpec] = []

    class Given(Sealed):
        async def start(self, spec: AgentSpec, report: Reporter) -> None:
            specs.append(spec)
            await super().start(spec, report)

    team = team_on(Given)
    async with Session.start(team, authority=Gating(team, model="served"), root=tmp_path) as session:
        await in_state(session, "bob", "idle")

    assert [spec.model for spec in specs] == ["served"]
