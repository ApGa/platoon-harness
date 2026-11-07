"""What a look records, as the runtime reports it: commits, rewrites and readings on `repo/<name>`, which name no agent,
the `changes` view over them, a conflict where a person must act, and the probe that asks for each look."""

from typing import Any

import pytest

from platoon_harness.kernel import Kernel
from platoon_harness.primitives.repo import NOT_RECORDED

from .support import end_turn, events_of, of_type, refusal, result_of, send, settle_effects, spawn, start, start_turn

ONE, TWO, THREE, FOUR = ("1" * 40, "2" * 40, "3" * 40, "4" * 40)
BASE = "0" * 40


@pytest.fixture
def repo() -> dict[str, Any]:
    return {"name": "app", "top": "/work/app", "prefix": "", "head": BASE, "branch": "main", "repository": "/work/.git"}


def commit(sha: str, *parents: str, made_in: str | None = "@bob", **fields: Any) -> dict[str, Any]:
    found = {"sha": sha, "parents": list(parents) or [BASE], "subject": f"make {sha[:4]}", "author": "Bob"}
    return {
        **found,
        "branch": "platoon-harness/s/bob",
        "made_in": made_in,
        "added": 1,
        "removed": 0,
        "files": 1,
        **fields,
    }


WORKTREE = "/s/agents/bob/workspace"


def reading(head: str | None = ONE, *paths: dict[str, Any], **fields: Any) -> dict[str, Any]:
    conflicted = sum(path["state"] == "conflicted" for path in paths)
    found = {"paths": list(paths), "total": len(paths), "conflicted": conflicted}
    return {"path": WORKTREE, "head": head, "branch": "platoon-harness/s/bob", **found, **fields}


def path(name: str, state: str = "modified", added: int | None = 1, removed: int | None = 0) -> dict[str, Any]:
    return {"path": name, "state": state, "added": added, "removed": removed}


async def looked(kernel: Kernel, workspace: str = "@bob", **page: Any) -> None:
    result_of(await kernel.submit(kernel.runtime, "repo.report", {"agent": "bob", "workspace": workspace, **page}))


def changes(kernel: Kernel, after: int | None = None) -> dict[str, Any]:
    return result_of(kernel.query(kernel.runtime, "view.watch", {"name": "changes", "after": after}))


def attention(kernel: Kernel) -> list[dict[str, Any]]:
    return result_of(kernel.query(kernel.runtime, "attention.list", {}))


def probes(kernel: Kernel) -> list[dict[str, Any]]:
    requested = of_type(kernel, "effect.requested")
    return [event.data for event in requested if event.data["kind"] == "probe"]


# The probe.


async def test_a_probe_follows_every_turn_end(kernel):
    await spawn(kernel, "bob")
    for turn in ("t1", "t2"):
        await start_turn(kernel, "bob", turn)
        await end_turn(kernel, "bob")
        await settle_effects(kernel, "bob")

    ended = [event.seq for event in of_type(kernel, "turn.ended")]
    assert [probe["data"] for probe in probes(kernel)] == [{"agent": "bob", "cause": seq} for seq in ended]
    assert all(probe["on_uncertain"] == "retry" for probe in probes(kernel))


async def test_a_resume_requests_a_look(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")
    await settle_effects(kernel, "bob")

    args = {"agent": "bob", "ready": {}, "declared": {"persistent": True}, "levels": {}, "resumed": True}
    result_of(await kernel.submit(kernel.runtime, "agent.start", args))

    [resumed] = of_type(kernel, "agent.resumed")
    assert probes(kernel)[-1]["data"] == {"agent": "bob", "cause": resumed.seq}


async def test_an_agent_that_ends_is_looked_at_by_its_stop(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(kernel.runtime, "agent.cancel", {"agent": "bob"}))

    [ended] = of_type(kernel, "agent.ended")
    stops = [event.data for event in of_type(kernel, "effect.requested") if event.data["kind"] == "stop"]
    assert probes(kernel) == []
    assert stops[-1]["data"] == {"agent": "bob", "cause": ended.seq}


async def test_a_look_runs_before_anything_handed_over_after_its_turn_end(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")
    await send(kernel, alice, "@bob", "next")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    ready = [effect["kind"] for effect in result_of(kernel.query(kernel.runtime, "effect.ready", {}))]
    assert ready == ["probe"]

    await settle_effects(kernel, "bob")

    kinds = [event.data["kind"] for event in of_type(kernel, "effect.started")]
    assert kinds.index("probe") < kinds.index("deliver")


async def test_a_pending_probe_keeps_a_session_from_settling(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")

    pending = result_of(kernel.query(kernel.runtime, "session.status", {}))
    await settle_effects(kernel, "bob")
    looked_at = result_of(kernel.query(kernel.runtime, "session.status", {}))

    assert (pending["settled"], pending["blockers"]) == (False, ["open_effect"])
    assert looked_at["settled"] is True


async def test_an_unfinished_look_is_named_in_the_ending(kernel):
    await spawn(kernel, "bob")
    await spawn(kernel, "carol")
    for name in ("bob", "carol"):
        await start_turn(kernel, name)
        await end_turn(kernel, name)
    await settle_effects(kernel, "carol")

    ending = result_of(kernel.query(kernel.runtime, "session.ending", {}))

    assert ending["unobserved"] == ["bob"]


# What a look records.


async def test_a_repo_event_names_no_agent_and_claims_no_turn(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE), cause=1)

    events = [event for event in events_of(kernel) if event.stream == "repo/app"]
    assert [event.type for event in events] == ["repo.committed", "workspace.changed"]
    assert all((event.agent, event.turn, event.context_version) == (None, None, None) for event in events)
    assert [event.cause for event in events] == [(), (1,)] and all(event.actor == "runtime" for event in events)
    assert events[0].data["made_in"] == "@bob" and events[0].gist == f"{ONE[:12]} make 1111"


async def test_a_look_names_what_prompted_it_as_the_cause_of_its_reading_and_of_no_commit_it_found(kernel):
    """A commit and a rewrite were someone's act in git, which the turn end that prompted the look did not cause."""
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE), commit(TWO, ONE)], reading=reading(TWO), cause=1)
    rewrite = {"branch": "main", "was": TWO, "now": ONE, "dropped": [TWO]}
    await looked(kernel, rewrite=rewrite, reading=reading(ONE), cause=2)

    causes = {event.type: event.cause for event in events_of(kernel) if event.stream == "repo/app"}
    assert causes == {"repo.committed": (), "repo.rewritten": (), "workspace.changed": (2,)}


async def test_each_commit_is_recorded_once_parents_first(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE), commit(TWO, ONE)])
    await looked(kernel, commits=[commit(ONE), commit(TWO, ONE), commit(THREE, TWO)], reading=reading(THREE))

    recorded = [event.data["sha"] for event in of_type(kernel, "repo.committed")]
    assert recorded == [ONE, TWO, THREE]


async def test_a_repeated_look_records_nothing_new(kernel):
    await spawn(kernel, "bob")
    page = {"commits": [commit(ONE)], "reading": reading(ONE, path("a.py"))}
    await looked(kernel, **page)
    head = kernel.head

    await looked(kernel, **page)

    assert [event.type for event in events_of(kernel) if event.seq > head] == ["op.completed"]


async def test_uncommitted_state_is_recorded_only_when_it_changes(kernel):
    await spawn(kernel, "bob")
    for paths in ([], [path("a.py")], [path("a.py")], [path("a.py", added=2)], [path("a.py", added=2)]):
        await looked(kernel, reading=reading(ONE, *paths))

    changed = of_type(kernel, "workspace.changed")
    assert [[path["added"] for path in event.data["paths"]] for event in changed] == [[], [1], [2]]
    assert changed[1].gist == "@bob: 1 path uncommitted"


async def test_a_rewrite_names_only_the_journaled_commits_it_dropped(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE), commit(TWO, ONE)], reading=reading(TWO))

    rewrite = {"branch": "platoon-harness/s/bob", "was": TWO, "now": BASE, "dropped": [TWO, FOUR, ONE]}
    await looked(kernel, rewrite=rewrite, reading=reading(BASE))

    [rewritten] = of_type(kernel, "repo.rewritten")
    assert rewritten.agent is None
    assert rewritten.data == {
        "workspace": "@bob",
        "branch": "platoon-harness/s/bob",
        "was": TWO,
        "now": BASE,
        "dropped": [TWO, ONE],
        "dropped_total": 2,
    }


async def test_a_rewrite_of_nothing_the_journal_holds_records_nothing(kernel):
    await spawn(kernel, "bob")
    rewrite = {"branch": "platoon-harness/s/bob", "was": ONE, "now": None, "dropped": [ONE]}

    await looked(kernel, rewrite=rewrite)

    assert of_type(kernel, "repo.rewritten") == []


async def test_a_look_that_fails_records_workspace_unobserved_and_no_change(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, unobserved="git status failed: index is corrupt", commits=[commit(ONE)], reading=reading())

    [gap] = of_type(kernel, "gap.recorded")
    assert (gap.stream, gap.agent) == ("agent/bob", "bob")
    assert gap.data == {
        "plane": "control",
        "what": "workspace_unobserved",
        "since": None,
        "why": "git status failed: index is corrupt",
    }
    assert [event for event in events_of(kernel) if event.stream == "repo/app"] == []
    gaps = result_of(kernel.query(kernel.runtime, "session.ending", {}))["gaps"]
    assert gaps == [{"agent": "bob", "what": "workspace_unobserved", "plane": "control", "count": 1}]


async def test_ancestry_declared_dependency_observed_reads_and_credit_never_derive_from_each_other(kernel):
    """A parent is ancestry and not a declaration, a citation is a declaration and not ancestry, and neither is a
    read of the agent's, nor its credit, which no event states."""
    await spawn(kernel, "bob")
    cited = [{"written": THREE[:7], "sha": THREE}]
    head = kernel.head
    await looked(kernel, commits=[commit(ONE), commit(THREE), commit(TWO, ONE, informed_by=cited)])

    one, three, two = of_type(kernel, "repo.committed")
    assert two.data["parents"] == [ONE] and two.data["informed_by"] == [{**cited[0], "why": None}]
    assert two.based_on == (f"repo/app@{three.version}",)
    assert one.based_on == ()
    assert [event.type for event in events_of(kernel) if event.seq > head and event.type.startswith("context.")] == []


async def test_a_driver_cannot_report_changes(kernel):
    await spawn(kernel, "bob")

    outcome = await kernel.submit(
        kernel.runtime, "agent.report", {"agent": "bob", "report": {"type": "changes", "path": "a.py"}}
    )

    assert refusal(outcome).code == "invalid"


# The changes view.


async def test_the_changes_view_holds_commits_and_uncommitted_paths(kernel):
    await spawn(kernel, "bob")
    await looked(
        kernel, commits=[commit(ONE, added=None)], reading=reading(ONE, path("notes.txt", "untracked", None, None))
    )

    rows = {row["id"]: row for row in changes(kernel)["rows"]}

    assert rows[f"commit/{ONE}"] | {"seq": 0, "recorded": 0} == {
        "id": f"commit/{ONE}",
        "kind": "commit",
        "commit": ONE,
        "gist": f"{ONE[:12]} make 1111",
        "made_in": "@bob",
        "branch": "platoon-harness/s/bob",
        "added": None,
        "removed": 0,
        "files": 1,
        "recorded": 0,
        "tests": None,
        "dropped": False,
        "seq": 0,
    }
    assert rows[f"commit/{ONE}"]["recorded"] == rows[f"commit/{ONE}"]["seq"]
    assert rows["workspace/@bob"]["total"] == 1 and rows["workspace/@bob"]["head"] == ONE
    assert rows["path/@bob/notes.txt"]["state"] == "untracked" and rows["path/@bob/notes.txt"]["added"] is None


async def test_a_newer_look_replaces_a_workspace_s_paths_whole(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, reading=reading(ONE, path("a.py"), path("b.py")))
    first = changes(kernel)
    await looked(kernel, reading=reading(ONE, path("b.py"), path("c.py")))

    moved = changes(kernel, first["cursor"])

    assert sorted(row["id"] for row in moved["rows"]) == ["path/@bob/c.py", "workspace/@bob"]
    assert moved["removed"] == ["path/@bob/a.py"]
    assert sorted(row["id"] for row in changes(kernel)["rows"] if row["kind"] == "path") == [
        "path/@bob/b.py",
        "path/@bob/c.py",
    ]


async def test_a_dropped_commit_stays_in_view_marked_dropped(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE))
    rewrite = {"branch": "platoon-harness/s/bob", "was": ONE, "now": BASE, "dropped": [ONE]}
    await looked(kernel, rewrite=rewrite, reading=reading(BASE))

    [row] = [row for row in changes(kernel)["rows"] if row["kind"] == "commit"]

    assert row["dropped"] is True


async def test_changes_rows_carry_seq_and_marks_say_what_is_new(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE, path("a.py")))
    mark = kernel.head
    await looked(kernel, commits=[commit(TWO, ONE)], reading=reading(TWO, path("a.py")))

    rows = changes(kernel)["rows"]
    new = sorted(row["id"] for row in rows if row["seq"] > mark)

    assert new == [f"commit/{TWO}", "workspace/@bob"]
    assert all(row["seq"] <= kernel.head for row in rows)


async def test_your_checkout_shows_nothing_when_no_role_works_in_it(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, "shared", reading={"path": "/src/app", "head": BASE, "branch": "main"})

    assert changes(kernel)["rows"] == []
    assert result_of(kernel.query(kernel.runtime, "repo.looks", {}))["shared"]["head"] == BASE


# A conflict.


async def conflicted(kernel: Kernel, *paths: str) -> None:
    """A look of bob's that finds a merge stopped on `paths`, as its probe does it."""
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")
    found = [path(name, "conflicted") for name in paths]
    [probe] = [
        effect for effect in result_of(kernel.query(kernel.runtime, "effect.ready", {})) if effect["kind"] == "probe"
    ]
    attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": probe["id"]}))
    await looked(kernel, reading=reading(ONE, *found, under_way="merge"))
    result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": probe["id"], "attempt": attempt}))


async def test_a_conflict_needs_you_while_its_agent_rests_on_it(kernel):
    await spawn(kernel, "bob")
    await conflicted(kernel, "a.py", "b.py")

    [row] = attention(kernel)
    rostered = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))["rows"]
    assert (row["id"], row["kind"], row["agent"], row["actions"]) == ("conflict/@bob", "conflict", "bob", [])
    assert row["gist"] == f"merge stopped on conflicts in 2 files, a.py, b.py: resolve it in {WORKTREE}"
    assert next(found for found in rostered if found["agent"] == "bob")["group"] == "needs_you"

    await start_turn(kernel, "bob", "t2")

    assert attention(kernel) == []


async def test_a_conflict_left_unresolved_needs_you_again_after_the_next_look(kernel):
    await spawn(kernel, "bob")
    await conflicted(kernel, "a.py")
    await start_turn(kernel, "bob", "t2")
    assert attention(kernel) == []

    await end_turn(kernel, "bob")
    await settle_effects(kernel, "bob")

    assert [row["id"] for row in attention(kernel)] == ["conflict/@bob"]


async def test_a_resolved_conflict_needs_you_no_more(kernel):
    await spawn(kernel, "bob")
    await conflicted(kernel, "a.py")

    await looked(kernel, reading=reading(TWO))

    assert attention(kernel) == []


async def test_a_conflict_is_moot_once_its_agent_ends(kernel):
    await spawn(kernel, "bob")
    await conflicted(kernel, "a.py")

    result_of(await kernel.submit(kernel.runtime, "agent.cancel", {"agent": "bob"}))
    await settle_effects(kernel, "bob")

    assert attention(kernel) == []


async def test_a_conflict_in_your_checkout_needs_you_while_its_latest_look_found_it(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, "shared", reading={**reading(ONE, path("a.py", "conflicted")), "branch": "main"})
    assert [(row["id"], row["agent"]) for row in attention(kernel)] == [("conflict/shared", None)]

    await looked(kernel, "shared", reading={**reading(TWO), "branch": "main"})

    assert attention(kernel) == []


# The roster, the status and the Ending.


async def test_the_roster_names_each_agent_s_workspace(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", {"name": "bob", "child_role": "worker"}))
    made = {"mode": "worktree", "path": "/s/agents/bob/workspace", "host": "h", "branch": "platoon-harness/s/bob"}
    while effects := result_of(kernel.query(kernel.runtime, "effect.ready", {})):
        for effect in effects:
            attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
            result = {**made, "base": BASE, "repository": "/work/.git"} if effect["kind"] == "workspace" else None
            args = {"id": effect["id"], "attempt": attempt, "result": result}
            result_of(await kernel.submit(kernel.runtime, "effect.finish", args))
    await start(kernel, "bob")

    rows = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))["rows"]
    status = result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))

    assert next(row for row in rows if row["agent"] == "bob")["workspace"] == {
        "mode": "worktree",
        "path": "/s/agents/bob/workspace",
        "branch": "platoon-harness/s/bob",
    }
    assert status["workspace"]["base"] == BASE and status["workspace"]["assurance"] == "cooperative"
    assert status["kept"] is None


async def test_a_session_observing_a_repository_names_it(kernel):
    assert result_of(kernel.query(kernel.runtime, "session.status", {}))["repo"] == "app"


@pytest.mark.parametrize("repo", [None])
async def test_a_session_outside_a_git_repository_says_changes_are_not_observed(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")

    status = result_of(kernel.query(kernel.runtime, "session.status", {}))
    outcome = await kernel.submit(kernel.runtime, "repo.report", {"agent": "bob", "workspace": "@bob"})

    assert status["repo"] is None and status["settled"] is True
    assert probes(kernel) == []
    assert refusal(outcome).code == "unsupported"
    assert result_of(kernel.query(kernel.runtime, "session.ending", {}))["unobserved"] == []


# Runtime tests, and an agent's read of a commit.

CHECKS = ["uv", "run", "pytest", "-q"]


async def spawned_in(kernel: Kernel, name: str, mode: str) -> None:
    """Spawn an agent through to started, its workspace made in `mode` as the host makes one."""
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", {"name": name, "child_role": "worker"}))
    folder = f"/s/agents/{name}/workspace"
    made = {"mode": mode, "path": folder, "host": "h", "branch": f"platoon-harness/s/{name}", "base": BASE}
    made |= {"repository": f"{folder}/.git", "assurance": "isolated" if mode == "isolated" else "cooperative"}
    while effects := [
        row for row in result_of(kernel.query(kernel.runtime, "effect.ready", {})) if row["agent"] == name
    ]:
        for effect in effects:
            attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
            result = made if effect["kind"] == "workspace" else None
            args = {"id": effect["id"], "attempt": attempt, "result": result}
            result_of(await kernel.submit(kernel.runtime, "effect.finish", args))
    await start(kernel, name)


async def recorded_test(kernel: Kernel, sha: str, outcome: str, *, effect: int = 1) -> str:
    """Record what a runtime test came to, as the host does once it has run."""
    tested = {"effect": effect, "sha": sha, "command": CHECKS, "exit": 0 if outcome == "passed" else 1}
    tested |= {"seconds": 2.5, "outcome": outcome}
    return result_of(await kernel.submit(kernel.runtime, "repo.record", tested))


def commit_row(kernel: Kernel, sha: str) -> dict[str, Any]:
    return next(row for row in changes(kernel)["rows"] if row["id"] == f"commit/{sha}")


def requested_tests(kernel: Kernel) -> list[Any]:
    return [event for event in of_type(kernel, "effect.requested") if event.data["kind"] == "test"]


async def test_a_commit_s_tests_are_its_latest_runtime_test_or_none(kernel):
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE), commit(TWO, ONE)], reading=reading(TWO))
    untested = commit_row(kernel, ONE)
    await recorded_test(kernel, ONE, "failed", effect=1)
    ref = await recorded_test(kernel, ONE, "passed", effect=2)

    [_, tested] = of_type(kernel, "repo.tested")
    assert untested["tests"] is None and commit_row(kernel, TWO)["tests"] is None
    assert commit_row(kernel, ONE)["tests"] == "passed" and commit_row(kernel, ONE)["seq"] == tested.seq
    assert ref == f"{tested.stream}@{tested.version}" and (tested.agent, tested.turn) == (None, None)
    assert tested.gist == f"{ONE[:12]} tests passed in 2.5 s"


async def test_a_commit_row_says_why_its_test_failed_and_names_its_record(kernel):
    """So a client shows the reason, not only the outcome, and can open the record its body blob holds."""
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE), commit(TWO, ONE)], reading=reading(TWO))
    failed = {"effect": 1, "sha": ONE, "command": CHECKS, "exit": 2, "seconds": 2.5, "outcome": "failed"}
    ref = result_of(await kernel.submit(kernel.runtime, "repo.record", failed))
    erred = {"effect": 2, "sha": TWO, "command": CHECKS, "exit": None, "seconds": None, "outcome": "error"}
    erred["why"] = "its timeout of 1m came first"
    result_of(await kernel.submit(kernel.runtime, "repo.record", erred))

    one, two = commit_row(kernel, ONE), commit_row(kernel, TWO)
    assert (one["tests"], one["tests_exit"], one["tests_why"], one["tested"]) == ("failed", 2, None, ref)
    assert (two["tests"], two["tests_exit"], two["tests_why"]) == ("error", None, "its timeout of 1m came first")


@pytest.mark.parametrize("checks", [CHECKS])
async def test_a_test_is_a_person_s_or_a_program_s_act_on_a_recorded_commit(kernel, ada):
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE))

    asked = result_of(await kernel.submit(ada, "repo.test", {"commit": ONE[:7]}))
    unrecorded = await kernel.submit(ada, "repo.test", {"commit": TWO})

    [requested] = requested_tests(kernel)
    assert asked == {"effect": requested.data["id"]}
    assert requested.data["data"] == {"sha": ONE} and requested.data["on_uncertain"] == "retry"
    assert requested.agent is None
    assert refusal(unrecorded).code == "not_found"
    assert (
        refusal(unrecorded).detail == "not recorded yet: a commit is recorded at the look after the turn that made it"
    )


async def test_a_test_needs_the_team_s_test_command(kernel, ada):
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE))

    outcome = await kernel.submit(ada, "repo.test", {"commit": ONE})

    assert refusal(outcome).code == "unsupported" and "names no `test`" in refusal(outcome).detail
    assert "actions" not in commit_row(kernel, ONE)


@pytest.mark.parametrize("checks", [CHECKS])
async def test_an_agent_cannot_ask_the_runtime_to_run_its_code(kernel):
    """Not as a tool, and not as an op, even under a grant that covers it, as this fixture's `agent *` does."""
    bob = await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE))

    outcome = await kernel.submit(bob, "repo.test", {"commit": ONE})

    assert refusal(outcome).code == "not_permitted"
    assert not kernel.ops["repo.test"].tool
    assert requested_tests(kernel) == []


@pytest.mark.parametrize("checks", [CHECKS])
async def test_a_test_of_an_isolated_commit_is_refused(kernel, ada):
    """And of one built on it, which holds its code, as a merge of it does. A commit beside it is no matter."""
    await spawned_in(kernel, "bob", "isolated")
    await spawned_in(kernel, "cy", "worktree")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE))
    merge = commit(TWO, BASE, ONE, made_in="@cy", branch="platoon-harness/s/cy")
    beside = commit(THREE, BASE, made_in="@cy", branch="platoon-harness/s/cy")
    await looked(kernel, "@cy", commits=[merge, beside], reading=reading(THREE, branch="platoon-harness/s/cy"))

    made, built = [await kernel.submit(ada, "repo.test", {"commit": sha}) for sha in (ONE, TWO)]
    result_of(await kernel.submit(ada, "repo.test", {"commit": THREE}))

    assert refusal(made).code == refusal(built).code == "not_permitted"
    assert refusal(made).detail == "@bob's commit was made in an isolated workspace, so its code runs only there"
    assert refusal(built).detail == (
        "it is built on a commit @bob made in an isolated workspace, so its code runs only there"
    )
    assert [event.data["data"]["sha"] for event in requested_tests(kernel)] == [THREE]


@pytest.mark.parametrize("checks", [CHECKS])
async def test_isolation_is_decided_by_the_look_not_by_the_reflog_an_agent_writes(kernel, ada):
    """A commit an isolated agent made, and a merge of it, are refused even when their reflog names no maker: the look
    that found the code decides, since an isolated agent writes its own reflog and could clear it."""
    await spawned_in(kernel, "bob", "isolated")
    await spawned_in(kernel, "cy", "worktree")
    await looked(kernel, "@bob", commits=[commit(ONE, made_in=None)], reading=reading(ONE))
    merge = commit(TWO, BASE, ONE, made_in=None, branch="platoon-harness/s/cy")
    await looked(kernel, "@cy", commits=[merge], reading=reading(TWO, branch="platoon-harness/s/cy"))

    made, built = [await kernel.submit(ada, "repo.test", {"commit": sha}) for sha in (ONE, TWO)]

    assert refusal(made).code == refusal(built).code == "not_permitted"
    assert refusal(made).detail == "@bob's commit was made in an isolated workspace, so its code runs only there"
    assert refusal(built).detail == (
        "it is built on a commit @bob made in an isolated workspace, so its code runs only there"
    )
    assert requested_tests(kernel) == []


@pytest.mark.parametrize("checks", [CHECKS])
async def test_a_test_action_says_whose_code_it_runs(kernel):
    await spawned_in(kernel, "bob", "worktree")
    await spawned_in(kernel, "cy", "isolated")
    await looked(kernel, commits=[commit(ONE), commit(TWO, ONE, made_in=None)], reading=reading(TWO))
    await looked(kernel, "@cy", commits=[commit(THREE, made_in="@cy")], reading=reading(THREE))

    actions = {sha: commit_row(kernel, sha)["actions"] for sha in (ONE, TWO, THREE)}

    assert actions[ONE] == [
        {
            "label": "Test: runs @bob's commit as you, unconfined",
            "op": "repo.test",
            "args": {"commit": ONE},
            "disabled": None,
        }
    ]
    assert actions[TWO][0]["label"] == "Test: runs this commit as you, unconfined"
    assert actions[THREE][0] | {"args": None} == {
        "label": "Test",
        "op": "repo.test",
        "args": None,
        "disabled": "@cy's commit was made in an isolated workspace, so its code runs only there",
    }


async def test_repo_commit_gives_a_recorded_commit_s_ref_or_says_not_recorded_yet(kernel, ada):
    """An agent's read of it records exposure, and a person's records nothing. A prefix names the one commit it
    begins, or is refused for naming several."""
    bob = await spawn(kernel, "bob")
    twin = "1111" + "5" * 36
    await looked(kernel, commits=[commit(ONE), commit(twin, ONE)], reading=reading(twin))
    [recorded, _] = of_type(kernel, "repo.committed")
    head = kernel.head

    given = result_of(await kernel.submit(bob, "repo.commit", {"sha": ONE}))
    asked = result_of(kernel.query(ada, "repo.commit", {"sha": ONE[:5]}))
    missing, several = [await kernel.submit(bob, "repo.commit", {"sha": sha}) for sha in (TWO, "1111")]

    ref = f"{recorded.stream}@{recorded.version}"
    assert given == asked == {"ref": ref, "sha": ONE, "gist": f"{ONE[:12]} make 1111", "made_in": "@bob"}
    [offered] = of_type(kernel, "context.offered", after=head)
    assert offered.agent == "bob" and offered.data["how"] == "read"
    assert [item["ref"] for item in offered.data["items"]] == [ref]
    assert refusal(missing).code == "not_found"
    assert refusal(missing).detail == "not recorded yet: a commit is recorded at the look after the turn that made it"
    assert refusal(several).code == "invalid"


@pytest.mark.parametrize("repo", [None])
async def test_repo_commit_says_a_session_with_no_repository_observes_none(kernel):
    bob = await spawn(kernel, "bob")

    outcome = await kernel.submit(bob, "repo.commit", {"sha": ONE})

    assert refusal(outcome).code == "unsupported"


# Diffs read on request.


def requested_diffs(kernel: Kernel) -> list[Any]:
    return [event for event in of_type(kernel, "effect.requested") if event.data["kind"] == "diff"]


async def stopped(kernel: Kernel, name: str, *, removed: bool) -> None:
    """End an agent, its stop removing its workspace or keeping it, as the host's does."""
    result_of(await kernel.submit(kernel.runtime, "agent.cancel", {"agent": name}))
    for effect in result_of(kernel.query(kernel.runtime, "effect.ready", {})):
        attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
        kept = None if removed else {"path": f"/s/agents/{name}/workspace", "host": "h", "branch": None, "bytes": None}
        result = {"removed": removed, "kept": kept and {**kept, "why": [], "release": []}}
        args = {"id": effect["id"], "attempt": attempt, "result": result if effect["kind"] == "stop" else None}
        result_of(await kernel.submit(kernel.runtime, "effect.finish", args))


async def test_repo_diff_asks_the_runtime_for_a_diff_as_an_effect(kernel, ada):
    """A recorded commit's patch, read in the workspace whose look found it, or a workspace's uncommitted diff: each an
    effect owned by no agent and retried after a crash, as a test is."""
    await spawned_in(kernel, "bob", "snapshot")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE))

    asked = [result_of(await kernel.submit(ada, "repo.diff", {"of": of})) for of in (ONE[:7], "@bob", "shared")]
    unrecorded, neither = [await kernel.submit(ada, "repo.diff", {"of": of}) for of in (TWO, "@bob,shared")]

    requested = requested_diffs(kernel)
    assert asked == [{"effect": event.data["id"]} for event in requested]
    assert [event.data["data"] for event in requested] == [
        {"sha": ONE, "found_in": "@bob"},
        {"workspace": "@bob"},
        {"workspace": "shared"},
    ]
    assert all(event.agent is None and event.data["on_uncertain"] == "retry" for event in requested)
    assert refusal(neither).code == "invalid"
    assert (refusal(unrecorded).code, refusal(unrecorded).detail) == ("not_found", NOT_RECORDED)


async def test_an_agent_is_refused_repo_diff_saying_how_it_reads_a_commit(kernel):
    """Not as a tool, and not as an op, even under a grant that covers it, as this fixture's `agent *` does."""
    bob = await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE))

    outcome = await kernel.submit(bob, "repo.diff", {"of": ONE})

    assert refusal(outcome).code == "not_permitted"
    assert refusal(outcome).detail == "an agent reads a commit through `repo.commit` or its own git, not as a diff"
    assert not kernel.ops["repo.diff"].tool
    assert requested_diffs(kernel) == []


async def test_a_diff_of_a_workspace_the_session_holds_none_of_is_refused(kernel, ada):
    """An agent's own is read once it is made, and while its stop has kept it; your checkout is `shared`."""
    await spawned_in(kernel, "bob", "worktree")
    await spawned_in(kernel, "cy", "worktree")
    await spawned_in(kernel, "dee", "shared")
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", {"name": "eve", "child_role": "worker"}))
    await stopped(kernel, "bob", removed=True)
    await stopped(kernel, "cy", removed=False)

    outcomes = {name: await kernel.submit(ada, "repo.diff", {"of": name}) for name in ("@bob", "@dee", "@eve", "@zed")}
    kept = result_of(await kernel.submit(ada, "repo.diff", {"of": "@cy"}))

    assert {where: (refusal(outcome).code, refusal(outcome).detail) for where, outcome in outcomes.items()} == {
        "@bob": ("not_found", "@bob's workspace went at its stop"),
        "@dee": ("not_found", "dee works in your checkout, which is `shared`"),
        "@eve": ("not_found", "@eve's workspace is not made yet"),
        "@zed": ("not_found", "no agent is zed"),
    }
    assert [event.data["data"] for event in requested_diffs(kernel)] == [{"workspace": "@cy"}]
    assert kept == {"effect": requested_diffs(kernel)[0].data["id"]}


@pytest.mark.parametrize("repo", [None])
async def test_repo_diff_says_a_session_with_no_repository_observes_none(kernel, ada):
    outcome = await kernel.submit(ada, "repo.diff", {"of": "shared"})

    assert refusal(outcome).code == "unsupported"


async def test_a_message_cites_lines_of_a_diff_by_its_ref(kernel, ada):
    """A comment on a diff is a person's message whose `based_on` cites lines of its patch, checked as any citation is,
    and a person reads the patch a page at a time by the record's ref."""
    await spawn(kernel, "bob")
    await looked(kernel, commits=[commit(ONE)], reading=reading(ONE))
    effect = result_of(await kernel.submit(ada, "repo.diff", {"of": ONE}))["effect"]
    patch = b"diff --git a/x b/x\nindex 1..2 100644\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"
    body = f"sha256:{await kernel.put_body(patch)}"
    ref = result_of(await kernel.submit(kernel.runtime, "repo.keep", {"effect": effect, "sha": ONE, "body": body}))

    sent = await send(kernel, ada, "@bob", "why this change?", based_on=[f"{ref}#L6-7"])
    past = await kernel.submit(ada, "message.send", {"to": "@bob", "gist": "and this?", "based_on": [f"{ref}#L7-8"]})
    read = result_of(kernel.query(ada, "blob.get", {"ref": f"{ref}#L5-7"}))

    [diffed] = of_type(kernel, "repo.diffed")
    assert ref == f"{diffed.stream}@{diffed.version}" and diffed.stream == "repo/app"
    assert (diffed.agent, diffed.turn, diffed.gist) == (None, None, f"{ONE[:12]} patch, 7 lines")
    assert diffed.data | {"body": None} == {
        "effect": effect,
        "sha": ONE,
        "workspace": None,
        "head": None,
        "body": None,
        "cut": False,
        "why": None,
    }
    [message] = [event for event in of_type(kernel, "message.sent") if f"{event.stream}@{event.version}" == sent["ref"]]
    assert message.based_on == (f"{ref}#L6-7",)
    assert refusal(past).code == "invalid" and "past the end" in refusal(past).detail["detail"]
    assert read["text"] == "@@ -1 +1 @@\n-old\n+new\n" and read["lines"] == 7
