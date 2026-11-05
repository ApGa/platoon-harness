"""The authority contract a training system's authority builds on: what it is asked, what it gives, and what the record
keeps of it."""

import json
from typing import Any
from urllib.parse import quote

import pytest
from pydantic import ValidationError

from platoon_harness import Refused, Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers import AgentSpec, Gateway, Item, Ready, Reporter
from platoon_harness.kernel import is_held
from platoon_harness.runtime import Admission, SpawnRequest
from platoon_harness.testing import Exit, Say, ScriptedDriver

from .support import harness, in_state, journal, of_type, until
from .training import ORIGIN, Gating, Sealed

pytestmark = pytest.mark.timeout(30)


def team_on(make: Any, **role: Any) -> Team:
    return Team.model_validate({"roles": {"bob": {"harness": harness(make), **role}}})


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


@pytest.mark.parametrize("backend", [{"agent_id": "the-key"}, {"agent_id": "the-bearer"}])
def test_an_admission_whose_backend_names_a_key_is_refused(backend):
    gateway = Gateway(origin=ORIGIN, bearer=Secret("the-bearer"), model="m")

    with pytest.raises(ValidationError, match="never a key") as refused:
        Admission(token=Secret("the-key"), access=gateway, backend=backend)

    assert "the-key" not in str(refused.value) and "the-bearer" not in str(refused.value)


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


async def test_a_driver_without_a_sealed_launch_refuses_a_gateway(tmp_path):
    team = team_on(ScriptedDriver)
    async with Session.start(team, authority=Gating(team), root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        row = (await session.ending()).agents[0]
        started = await of_type(session, "agent.started")

    assert row["reason"] == "its spawn failed: `scripted` has no sealed launch, which a gateway admission needs"
    assert started == []


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
