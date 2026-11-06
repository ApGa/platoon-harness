"""Runtime tests of a commit on real git under `tmp_path`: the team's `test` command, run when a person asks, in a clean
detached checkout of that commit, what it came to recorded on `repo/<name>`, and its checkout gone after."""

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.kernel import Effect, Extension, ManualClock
from platoon_harness.runtime.paths import TESTS

from .gitting import commit, repository, working
from .support import SECONDS, extension, harness, of_type, scripted, until

pytestmark = pytest.mark.timeout(60)


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


def team_of(command: list[str], *pieces: Any, timeout: str = "1m", workspace: str = "worktree") -> Team:
    """A lead, and workers in a workspace of their own, a worktree unless a test says, each turn of whose doing the next
    of `pieces` there, under a team whose test runs `command`."""
    worker = {"harness": working(*pieces), "workspace": workspace, "count": 0}
    roles = {"lead": {"harness": scripted()}, "worker": worker}
    return Team.model_validate({"roles": roles, "test": {"command": command, "timeout": timeout}})


async def committed(session: Session, count: int) -> list[str]:
    """The commits the looks recorded, once there are `count`, oldest first."""
    found = await until(lambda: of_type(session, "repo.committed"), session, lambda found: len(found) >= count)
    return [event.data["sha"] for event in found]


async def records(session: Session, count: int = 1) -> list[Any]:
    """The test records, once there are `count`, and each one's effect finished."""

    async def finished() -> list[Any]:
        done = {event.data["id"] for event in await of_type(session, "effect.finished") if event.data["kind"] == "test"}
        return [event for event in await of_type(session, "repo.tested") if event.data["effect"] in done]

    return await until(finished, session, lambda found: len(found) >= count)


async def printed(session: Session, record: Any) -> str:
    """What a test printed, which its record carries as its body."""
    return (await session.submit("blob.get", ref=f"{record.stream}@{record.version}")).result["text"]


def runs_of(path: Path) -> int:
    return len(path.read_text().split()) if path.exists() else 0


async def test_a_runtime_test_runs_at_the_exact_commit_in_a_clean_checkout(repo, tmp_path):
    """At the commit asked for, and not at a later one of its branch, without the files its worktree holds untracked,
    and in the session's subfolder of it."""

    def work(cwd: Path) -> None:
        commit(cwd, "value.txt", "first\n")
        commit(cwd, "value.txt", "later\n")
        (cwd / "untracked.txt").write_text("left out\n")

    check = ["sh", "-c", "cat value.txt; ls -A; pwd"]
    async with Session.start(team_of(check, work), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        first, _ = await committed(session, 2)
        asked = (await session.submit("repo.test", commit=first)).result
        [record] = await records(session)
        text = await printed(session, record)

    value, *listed, where = text.splitlines()
    assert record.data["effect"] == asked["effect"] and record.data["sha"] == first
    assert value == "first"
    assert sorted(listed) == [".git", "README", "src", "value.txt"]
    assert Path(where) == tmp_path / "sessions" / "s" / TESTS / str(asked["effect"]) / "checkout"


async def test_a_runtime_test_s_exit_time_and_output_are_recorded_and_its_checkout_removed(repo, tmp_path):
    """The command a commit holds is that commit's own: one that fails, and the next, that passes."""

    def failing(cwd: Path) -> None:
        commit(cwd, "check.sh", "echo out; echo err >&2; exit 3\n")

    def passing(cwd: Path) -> None:
        commit(cwd, "check.sh", "echo fine\n")

    async with Session.start(team_of(["sh", "check.sh"], failing), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "fail")
        [fails] = await committed(session, 1)
        await session.submit("repo.test", commit=fails)
        [failed] = await records(session)
        failed_text = await printed(session, failed)
        rows = {row["id"]: row for row in (await session.submit("view.watch", name="changes")).result["rows"]}
    async with Session.start(team_of(["sh", "check.sh"], passing), name="t", root=tmp_path, cwd=repo) as session:
        await session.spawn("bob", "worker", "pass")
        [passes] = await committed(session, 1)
        await session.submit("repo.test", commit=passes)
        [passed] = await records(session)

    assert failed.data | {"seconds": None, "body": None} == {
        "effect": failed.data["effect"],
        "sha": fails,
        "command": ["sh", "check.sh"],
        "exit": 3,
        "seconds": None,
        "outcome": "failed",
        "why": None,
        "body": None,
        "printed": len("out\nerr\n"),
    }
    assert failed.data["seconds"] >= 0 and failed_text == "out\nerr\n"
    assert rows[f"commit/{fails}"]["tests"] == "failed"
    assert (passed.data["exit"], passed.data["outcome"]) == (0, "passed")
    assert [list((tmp_path / "sessions" / name / TESTS).iterdir()) for name in ("s", "t")] == [[], []]


async def test_what_a_test_printed_past_what_its_record_holds_is_cut_saying_how_much(repo, tmp_path):
    """Its record keeps the last of it, which is where a test runner says what failed."""
    check = ["sh", "-c", "yes failing | head -c 70000; echo summary"]
    async with Session.start(
        team_of(check, lambda cwd: commit(cwd, "work.txt")), name="s", root=tmp_path, cwd=repo
    ) as session:
        await session.spawn("ada", "worker", "work")
        [sha] = await committed(session, 1)
        await session.submit("repo.test", commit=sha)
        [record] = await records(session)
        kept = await session.get_body(record.data["body"])

    assert record.data["printed"] == 70000 + len("summary\n")
    assert len(kept) == 64 * 1024 and kept.endswith(b"failing\nsummary\n")


async def test_a_snapshot_s_commit_is_tested_from_the_repository_that_holds_it(repo, tmp_path):
    """Only the snapshot holds its agent's commit, so the checkout borrows its objects, and through them yours."""
    team = team_of(
        ["sh", "-c", "cat work.txt README"], lambda cwd: commit(cwd, "work.txt", "snapshot's\n"), workspace="snapshot"
    )
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        [sha] = await committed(session, 1)
        await session.submit("repo.test", commit=sha)
        [record] = await records(session)
        text = await printed(session, record)

    assert record.data["outcome"] == "passed" and text == "snapshot's\nhello\n"


async def test_a_test_past_its_timeout_is_an_error_not_a_failure(repo, tmp_path):
    """And nothing it started runs on."""
    clock = ManualClock(1000.0)
    pid = tmp_path / "pid"
    check = ["sh", "-c", f"echo $$ > {pid}; exec sleep 100"]
    team = team_of(check, lambda cwd: commit(cwd, "work.txt"), timeout="2m")
    async with Session.start(team, name="s", root=tmp_path, cwd=repo, clock=clock) as session:
        await session.spawn("ada", "worker", "work")
        [sha] = await committed(session, 1)
        await session.submit("repo.test", commit=sha)
        await asyncio.wait_for(clock.slept_until(clock.now() + 120), SECONDS)
        clock.advance(120)
        [record] = await records(session)

    assert (record.data["outcome"], record.data["exit"]) == ("error", None)
    assert record.data["why"] == "its timeout of 2m came first"
    assert record.gist == f"{sha[:12]} tests error: its timeout of 2m came first in 120.0 s"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid.read_text()), 0)


async def test_a_test_the_journal_recorded_is_not_run_again(repo, tmp_path):
    """A crash between its record and its finish leaves its effect started, which the next runtime retries, and the
    retry finds the record and runs nothing."""
    from .test_recovery import abandon

    ran = tmp_path / "ran"
    team = team_of(["sh", "-c", f"echo once >> {ran}"], lambda cwd: commit(cwd, "work.txt"))
    session = await Session.start(team, name="s", root=tmp_path, cwd=repo)
    runtime = session._runtime
    assert runtime is not None
    real, recorded = runtime.host._acts["test"], asyncio.Event()

    async def dies(effect: Any) -> None:
        await real(effect)
        recorded.set()
        await asyncio.Event().wait()

    runtime.host._acts["test"] = dies
    await session.spawn("ada", "worker", "work")
    [sha] = await committed(session, 1)
    await session.submit("repo.test", commit=sha)
    await asyncio.wait_for(recorded.wait(), SECONDS)
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        [record] = await records(session)
        [finished] = [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "test"]

    assert runs_of(ran) == 1
    assert finished.data["result"] == {"ref": f"{record.stream}@{record.version}"}
    assert list((tmp_path / "sessions" / "s" / TESTS).iterdir()) == []


async def test_a_commit_only_an_isolated_workspace_holds_is_never_checked_out(repo, tmp_path):
    """Should a test of one be asked for despite `repo.test`'s refusal, it reads no isolated workspace's objects, so
    the commit an isolated agent made in its snapshot, which only that holds, is never checked out."""
    from .test_isolation import Fence, Placed

    fence = extension(Extension("fence", isolation=Fence(tmp_path / "fence.log")))
    bob = {"harness": harness(lambda: Placed(lambda cwd: commit(cwd, "work.txt"))), "workspace": "isolated"}
    team = Team.model_validate(
        {"extensions": [fence], "roles": {"bob": bob}, "test": {"command": ["true"], "timeout": "1m"}}
    )
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.send("@bob", "work")
        [sha] = await committed(session, 1)
        host = session._runtime.host  # type: ignore[union-attr]
        effect = Effect(
            id=10**9,
            kind="test",
            state="requested",
            on_uncertain="retry",
            timeout=None,
            priority=0,
            agent=None,
            attempts=0,
            after=None,
            data={"sha": sha},
        )
        await host._test(effect)
        [record] = await of_type(session, "repo.tested")

    assert record.data["outcome"] == "error"
    assert record.data["why"] == f"no repository a test may read from holds {sha[:12]}"
