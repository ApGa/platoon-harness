"""What a look records, as the runtime reports it: commits, rewrites and readings on `repo/<name>`, which name no agent,
the `changes` view over them, a conflict where a person must act, and the probe that asks for each look."""

from typing import Any

import pytest

from platoon_harness.kernel import Kernel

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
