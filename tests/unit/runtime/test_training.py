"""A session as a training system starts it: checked for training before any harness launches, and read afterwards for
what can train, from the record alone."""

import asyncio
import shutil
from typing import Any

import pytest

from platoon_harness import ConfigError, Refused, Session, Team
from platoon_harness.drivers import levels
from platoon_harness.drivers.levels import implementation
from platoon_harness.runtime import Admission, SpawnRequest
from platoon_harness.runtime.opening import check
from platoon_harness.runtime.paths import CONFORMANCE
from platoon_harness.testing import Say

from .support import SECONDS, harness, in_state, of_type, rebuilt_equals_live, scripted, until
from .training import UNSEALED, Gating, Sealed, kept

pytestmark = pytest.mark.timeout(30)

MAKING = "`check_driver` checks it, and `write_conformance` keeps what it found here"


def trainable(make: Any = Sealed, **role: Any) -> Team:
    return Team.model_validate({"roles": {"bob": {"harness": harness(make), "approvals": "allow", **role}}})


def said(problems: Any) -> list[tuple[str, str]]:
    return [(problem.where, problem.what) for problem in problems if problem.level == "error"]


@pytest.mark.parametrize(
    ("made", "failed", "version", "what"),
    [
        (False, (), "1", f"no conformance result for scripted is kept: {MAKING}"),
        (True, (), "0", f"conformance ran on scripted 0, and this is scripted 1: {MAKING}"),
        (True, ("call_ids_reported",), "1", "`call_ids_reported` failed: "),
        (True, ("sealed_first_request_holds_only_ours",), "1", "`sealed_first_request_holds_only_ours` failed: "),
        (True, ("environment_tools_in_first_request",), "1", "`environment_tools_in_first_request` failed: "),
        (True, (), "1", None),
    ],
)
def test_check_trainable_refuses_what_the_machine_decides(tmp_path, made, failed, version, what):
    """Each role's driver is asked for a sealed launch, and the result kept under the root for the harness it would run
    must prove trainable, as the levels of its start will need, naming what makes one where none does."""
    if made:
        kept(tmp_path, *failed, version=version)

    found = said(check(trainable(), trainable=True, root=tmp_path, cwd=tmp_path))

    assert found == ([] if what is None else [("roles.bob.harness", what)])


@pytest.mark.parametrize(
    ("role", "stated", "where"),
    [
        ("allow", "ask", ["approvals"]),
        ("ask", "allow", []),
        ("ask", "deny", []),
        ("ask", None, ["roles.bob.approvals"]),
    ],
)
def test_check_trainable_judges_the_approvals_the_session_runs(tmp_path, role, stated, where):
    """A session's own `approvals` overrules each role's, so `ask` stated there waits for a person whatever the roles
    say, and `allow` or `deny` stated there leaves no role's `ask` to wait."""
    kept(tmp_path)

    found = said(check(trainable(approvals=role), trainable=True, approvals=stated, root=tmp_path, cwd=tmp_path))

    assert [where for where, _ in found] == where


def test_check_trainable_refuses_a_driver_with_no_sealed_launch(tmp_path):
    team = Team.model_validate({"roles": {"bob": {"harness": scripted(capabilities=UNSEALED), "approvals": "allow"}}})

    found = said(check(team, trainable=True, root=tmp_path, cwd=tmp_path))

    assert found == [("roles.bob.harness", "`scripted` has no sealed launch, which a trainable session needs")]


def test_check_trainable_names_doctor_for_a_harness_whose_check_ships(tmp_path, monkeypatch):
    monkeypatch.setitem(levels.CHECKED, "scripted", implementation(Sealed()))

    [(_, what)] = said(check(trainable(), trainable=True, root=tmp_path, cwd=tmp_path))

    assert what.endswith("`platoon-harness doctor --check` checks it here and keeps what it found")


def test_check_trainable_reads_the_team_too_and_no_plan_login_is_its(tmp_path):
    """A trainable session's agents run on its authority's gateway, so several of a harness on a plan are no problem,
    and what keeps the team from training is said with the rest."""
    kept(tmp_path)
    team = trainable(count=2, model="m")

    found = said(check(team, trainable=True, root=tmp_path, cwd=tmp_path))
    untrained = said(check(team, root=tmp_path, cwd=tmp_path))

    assert found == [("roles.bob.model", "a trainable team names no model: its gateway serves one")]
    assert [where for where, _ in untrained] == ["plan_login"]


async def test_session_start_trainable_refuses_before_any_harness_launches(tmp_path):
    started: list[Any] = []

    class Recorded(Sealed):
        async def start(self, spec: Any, report: Any) -> None:
            started.append(spec)
            await super().start(spec, report)

    team = trainable(Recorded)
    with pytest.raises(ConfigError, match="no conformance result for scripted is kept"):
        await Session.start(team, trainable=True, authority=Gating(team), root=tmp_path)
    with pytest.raises(Refused, match="through an authority's gateway") as unled:
        Session.start(team, trainable=True, root=tmp_path)

    assert started == [] and not (tmp_path / "sessions").exists()
    assert unled.value.refusal.code == "invalid"


async def test_eligibility_answers_alike_after_rebuild_on_a_closed_copy_and_without_the_conformance_store(tmp_path):
    """The levels its start recorded are what it reads, so a result kept or lost since changes nothing."""
    kept(tmp_path)
    team = trainable(lambda: Sealed([[Say("done")]]))
    authority, program = Gating(team), "program:trainer"
    async with Session.start(
        team, name="s", principal=program, trainable=True, authority=authority, root=tmp_path
    ) as session:
        await in_state(session, "bob", "idle")
        await session.open_episode("e")
        await session.send("@bob", "go")
        [message] = await until(lambda: of_type(session, "item.recorded"), session)
        await in_state(session, "bob", "idle")
        await session.retire("@bob")
        await session.close_episode(based_on=[f"{message.stream}@{message.version}"])
        live = await session.eligibility("@bob", "e")
        await session.close()

    async def read() -> Any:
        async with Session.attach("s", root=tmp_path) as history:
            return await history.eligibility("@bob", "e")

    closed = await read()
    shutil.rmtree(tmp_path / CONFORMANCE)
    without = await read()
    await rebuilt_equals_live(tmp_path / "sessions" / "s")
    rebuilt = await read()

    assert (live.attribution, live.verdict, live.reasons) == ("exact", "eligible", ())
    assert [(call.call_id, call.verdict) for call in live.calls] == [("call-done", "eligible")]
    assert closed == without == rebuilt == live.model_copy(update={"head": closed.head})


async def test_a_trainable_session_is_never_resumed_even_when_a_stop_cut_its_admits_short(tmp_path):
    """An admit a stop cut short may have named backend ids nobody knows, so a session started trainable is history once
    it has run, whatever its admit results say."""
    kept(tmp_path)
    asking = asyncio.Event()

    class Slow(Gating):
        async def admit(self, spawn: SpawnRequest) -> Admission:
            asking.set()
            await asyncio.Event().wait()
            raise AssertionError

    team = trainable()
    start: dict[str, Any] = {"principal": "program:trainer", "trainable": True, "authority": Slow(team)}
    session = await Session.start(team, name="s", root=tmp_path, **start)
    await asyncio.wait_for(asking.wait(), SECONDS)
    await session.leave()
    async with Session.attach("s", root=tmp_path) as history:
        head = await history.head()
        admits = [event for event in await of_type(history, "effect.started") if event.data["kind"] == "admit"]

    with pytest.raises(Refused, match="never resumed: it was started trainable") as refused:
        await Session.resume("s", root=tmp_path)

    async with Session.attach("s", root=tmp_path) as history:
        assert await history.head() == head
    assert admits and refused.value.refusal.code == "unsupported"
