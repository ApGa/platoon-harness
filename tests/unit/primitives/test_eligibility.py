"""Eligibility: whether an agent's work in one episode can train, from the record alone, for the agent and each of its
calls, with an attribution and every reason it cannot, of a closed set. The fixture refolds each test's views and
compares them, so each answer here is also the answer after a rebuild."""

from typing import Any

from platoon_harness.kernel import Kernel, Principal
from platoon_harness.primitives import Eligibility

from ..kernel.support import enroll, grant
from .support import (
    agent,
    end_turn,
    of_type,
    refusal,
    report,
    result_of,
    send,
    start,
    start_turn,
)

MET = {"trainable": {"state": "met", "reasons": []}}
UNVERIFIED = {"trainable": {"state": "unverified", "reasons": ["tools unverified"]}}


async def admitted(
    kernel: Kernel, name: str, *, backend: dict[str, str] | None = None, levels: dict[str, Any] = MET
) -> Principal:
    """Spawn an agent through to started as a training authority would admit it, its admit naming `backend`."""
    args = {"name": name, "child_role": "worker"}
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", args))
    for effect in result_of(kernel.query(kernel.runtime, "effect.ready", {})):
        if effect["agent"] == name:
            attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
            result = (backend or {"agent_id": f"id-of-{name}"}) if effect["kind"] == "admit" else None
            finished = {"id": effect["id"], "attempt": attempt, "result": result}
            result_of(await kernel.submit(kernel.runtime, "effect.finish", finished))
    await start(kernel, name, levels=levels, resume=True)
    return agent(name)


async def call(kernel: Kernel, name: str, call_id: str = "c1", purpose: str | None = None) -> None:
    await report(kernel, name, "model.call", call_id=call_id, purpose=purpose)


async def episode(kernel: Kernel, name: str = "e1") -> None:
    result_of(await kernel.submit(kernel.runtime, "episode.open", {"episode": name}))


async def close(kernel: Kernel) -> None:
    result_of(await kernel.submit(kernel.runtime, "episode.close", {}))


async def finish(kernel: Kernel, name: str) -> None:
    result_of(await kernel.submit(kernel.runtime, "agent.retire", {"agent": name}))


def eligibility(kernel: Kernel, name: str, episode: str = "e1", after: str | None = None) -> Eligibility:
    asked = {"agent": name, "episode": episode, "after": after}
    return Eligibility.model_validate(result_of(kernel.query(kernel.runtime, "eligibility", asked)))


def reasons(found: Any) -> list[str]:
    return [bar.reason for bar in found.reasons]


async def worked(kernel: Kernel, name: str, *calls: tuple[str, str | None], read: bool = False) -> None:
    """One turn of an agent's with a model call for each of `calls`, after a read of its inbox, if `read`, which hands
    it what is there."""
    await start_turn(kernel, name)
    if read:
        result_of(await kernel.submit(agent(name), "message.read", {}))
    for call_id, purpose in calls:
        await call(kernel, name, call_id, purpose)
    await end_turn(kernel, name)


async def test_attribution_is_exact_only_where_trainable_is_met_and_the_backend_identity_is_its_own(kernel):
    await episode(kernel)
    for name, backend, levels in (
        ("ada", {"agent_id": "a"}, MET),
        ("bob", {"agent_id": "b"}, UNVERIFIED),
        ("cy", {"agent_id": "shared"}, MET),
        ("di", {"agent_id": "shared", "trajectory": "t"}, MET),
    ):
        await admitted(kernel, name, backend=backend, levels=levels)
        await worked(kernel, name, ("c1", None))
        await finish(kernel, name)
    await close(kernel)

    found = {name: eligibility(kernel, name) for name in ("ada", "bob", "cy", "di")}

    assert {name: (answer.attribution, answer.verdict) for name, answer in found.items()} == {
        "ada": ("exact", "eligible"),
        "bob": (None, "ineligible"),
        "cy": (None, "ineligible"),
        "di": (None, "ineligible"),
    }
    assert found["bob"].reasons[0].level == UNVERIFIED["trainable"]
    assert (found["cy"].reasons[0].reason, found["cy"].reasons[0].refs) == ("shared_key", ("agent/di@1",))
    assert [call.verdict for call in found["ada"].calls] == ["eligible"]


async def test_attribution_is_forked_once_a_native_child_is_seen(kernel):
    await episode(kernel)
    await admitted(kernel, "ada")
    await start_turn(kernel, "ada")
    await call(kernel, "ada")
    await report(kernel, "ada", "child.seen", native="n1", parent="tool-1")
    await end_turn(kernel, "ada")
    await finish(kernel, "ada")

    found = eligibility(kernel, "ada")
    [seen] = of_type(kernel, "child.seen")

    assert (found.attribution, reasons(found)) == ("forked", ["forked"])
    assert found.reasons[0].refs == (f"{seen.stream}@{seen.version}",)
    assert [(call.attribution, call.verdict) for call in found.calls] == [("forked", "ineligible")]


async def test_eligibility_names_each_reason(kernel, ada):
    """One agent for each, and the calls of one for each of a call's own."""
    await admitted(kernel, "early")
    await worked(kernel, "early", ("before", None))
    await episode(kernel)
    await admitted(kernel, "untrained", levels=UNVERIFIED)
    await admitted(kernel, "twin", backend={"agent_id": "same"})
    await admitted(kernel, "other", backend={"agent_id": "same"})
    await worked(kernel, "early", ("inside", None), ("titled", "title"))
    await send(kernel, ada, "@early", "a person's word")
    await worked(kernel, "early", ("after", None), read=True)
    for name in ("early", "untrained", "twin", "other"):
        await finish(kernel, name)
    await admitted(kernel, "forking")
    await start_turn(kernel, "forking")
    await report(kernel, "forking", "child.seen", native="n1")
    await end_turn(kernel, "forking")
    await finish(kernel, "forking")
    await admitted(kernel, "unended")

    agents = {name: reasons(eligibility(kernel, name)) for name in ("untrained", "twin", "forking", "unended")}
    calls = {call.call_id: reasons(call) for call in eligibility(kernel, "early").calls}

    assert agents == {
        "untrained": ["not_trainable"],
        "twin": ["shared_key"],
        "forking": ["forked"],
        "unended": ["no_end"],
    }
    assert calls == {"before": ["outside_episode"], "inside": [], "titled": ["purpose"], "after": ["person"]}


async def test_a_compaction_call_is_eligible_and_a_call_of_an_undeclared_purpose_is_not(kernel):
    await episode(kernel)
    await admitted(kernel, "ada")
    await worked(kernel, "ada", ("turn", None), ("compacting", "compaction"), ("naming", "title"))
    await finish(kernel, "ada")

    found = eligibility(kernel, "ada")

    assert [(call.call_id, call.purpose, call.verdict) for call in found.calls] == [
        ("turn", None, "eligible"),
        ("compacting", "compaction", "eligible"),
        ("naming", "title", "ineligible"),
    ]


async def test_a_person_entry_handed_below_a_call_makes_it_ineligible_unless_not_seen(kernel, ada):
    """A person's entry handed over is seen or unknown, never `not_seen`, so each call after it is a person's, and a
    call before it is not. A program's word is no person's, and a turn a person held is a person's."""
    program = Principal(id="program:platoon")
    await enroll(kernel, program)
    await grant(kernel, "program")
    await episode(kernel)
    await admitted(kernel, "bob")
    await send(kernel, program, "@bob", "a program's word")
    await worked(kernel, "bob", ("after the program", None), read=True)
    await send(kernel, ada, "@bob", "a person's word")
    await worked(kernel, "bob", ("after the person", None), read=True)
    await admitted(kernel, "cy")
    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "@cy"}))
    await worked(kernel, "cy", ("held", None))
    result_of(await kernel.submit(ada, "agent.release", {"agent": "@cy"}))
    for name in ("bob", "cy"):
        await finish(kernel, name)

    bob, cy = eligibility(kernel, "bob"), eligibility(kernel, "cy")

    assert [(call.call_id, reasons(call)) for call in bob.calls] == [
        ("after the program", []),
        ("after the person", ["person"]),
    ]
    assert bob.calls[1].reasons[0].refs == ("inbox/bob@2",)
    assert [(call.call_id, reasons(call)) for call in cy.calls] == [("held", ["person"])]
    assert cy.calls[0].reasons[0].refs == ("turn/cy@1",)


async def test_calls_come_a_page_at_a_time_with_the_true_total(kernel):
    await episode(kernel)
    await admitted(kernel, "ada")
    await worked(kernel, "ada", *((f"c{n}", None) for n in range(40)))
    await finish(kernel, "ada")

    first = eligibility(kernel, "ada")
    rest = eligibility(kernel, "ada", after=first.cursor)

    assert (len(first.calls), first.total, len(rest.calls), rest.cursor) == (32, 40, 8, None)
    assert [call.call_id for call in (*first.calls, *rest.calls)] == [f"c{n}" for n in range(40)]


async def test_eligibility_is_asked_of_an_agent_in_an_episode_that_exists(kernel, ada):
    await episode(kernel)
    await admitted(kernel, "bob")
    asked = (("@nobody", "e1"), ("@ada", "e1"), ("@bob", "never"))

    found = [refusal(kernel.query(kernel.runtime, "eligibility", {"agent": a, "episode": e})) for a, e in asked]

    assert [refused.code for refused in found] == ["not_found", "invalid", "not_found"]
