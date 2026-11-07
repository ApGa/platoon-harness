"""Diffs read on request, on real git under `tmp_path`: a recorded commit's patch, or a workspace's uncommitted diff,
read where that workspace lives, with nothing a repository's config names run to show it, and kept on `repo/<name>` as
`repo.diffed`, whose body is the patch, cut at a line's end past its bound."""

import asyncio
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Refused, Session, Team
from platoon_harness.kernel import ManualClock

from .gitting import commit, git, repository, working
from .support import SECONDS, of_type, scripted, until
from .test_commit_tests import committed

pytestmark = pytest.mark.timeout(60)

LIMIT = 64 * 1024


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


def team_of(*pieces: Any, workspace: str = "worktree") -> Team:
    """A lead in your checkout, and workers in a workspace of their own, a worktree unless a test says, each turn of
    whose doing the next of `pieces` there."""
    worker = {"harness": working(*pieces), "workspace": workspace, "count": 0}
    return Team.model_validate({"roles": {"lead": {"harness": scripted()}, "worker": worker}})


async def diffed(session: Session, count: int = 1) -> list[Any]:
    """The diff records, once there are `count`, and each one's effect finished."""

    async def finished() -> list[Any]:
        done = {event.data["id"] for event in await of_type(session, "effect.finished") if event.data["kind"] == "diff"}
        return [event for event in await of_type(session, "repo.diffed") if event.data["effect"] in done]

    return await until(finished, session, lambda found: len(found) >= count)


async def diff_of(session: Session, of: str) -> Any:
    """The record of a diff asked for now, once it is kept, whichever other diff is read beside it."""
    effect = (await session.repo_diff(of))["effect"]

    async def kept() -> list[Any]:
        return [event for event in await of_type(session, "repo.diffed") if event.data["effect"] == effect]

    [record] = await until(kept, session)
    return record


async def patch_of(session: Session, record: Any) -> bytes:
    """The patch a diff's record keeps as its body."""
    return await session.get_body(record.data["body"])


def changed(cwd: Path, name: str, text: str) -> None:
    """Change a file and leave it uncommitted, as an agent leaves its work."""
    (cwd / name).write_text(text)


async def test_an_uncommitted_diff_says_when_it_was_read(repo, tmp_path):
    """And the HEAD it is against. It is a moment's reading, so each ask reads again, where a commit's patch, which
    never changes, is kept once and asked for again gives its ref."""
    clock = ManualClock(1000.0)

    def work(cwd: Path) -> None:
        commit(cwd, "value.txt", "first\n")
        changed(cwd, "value.txt", "second\n")

    async with Session.start(team_of(work), name="s", root=tmp_path, cwd=repo, clock=clock) as session:
        await session.spawn("ada", "worker", "work")
        [sha] = await committed(session, 1)
        earlier = await diff_of(session, "@ada")
        clock.advance(60)
        changed(Path((await session.status("@ada"))["workspace"]["path"]), "value.txt", "third\n")
        later, of_commit = await diff_of(session, "@ada"), await diff_of(session, sha)
        again = await session.repo_diff(sha[:7])
        patches = [await patch_of(session, record) for record in (earlier, later)]

    assert (earlier.data["read_at"], later.data["read_at"]) == (1000.0, 1060.0)
    assert earlier.data["head"] == later.data["head"] == sha and earlier.data["workspace"] == "@ada"
    assert earlier.gist == f"@ada uncommitted against {sha[:12]}, {patches[0].count(b'\n')} lines"
    assert patches[0].endswith(b"-first\n+second\n") and patches[1].endswith(b"-first\n+third\n")
    assert of_commit.data["read_at"] is None
    assert again == {"ref": f"{of_commit.stream}@{of_commit.version}"}


async def test_a_patch_past_its_bound_is_cut_and_says_where(repo, tmp_path):
    """At the end of the last line within 64 KiB, so a citation's lines are whole and no character is split. An
    untracked file past the bound is not read, and the record says it was cut."""
    lines = "".join(f"line {number} of a long file\n" for number in range(4000))

    def work(cwd: Path) -> None:
        commit(cwd, "long.txt", lines)
        changed(cwd, "long.txt", lines.replace("line", "row"))
        changed(cwd, "later.txt", "past the bound\n")

    async with Session.start(team_of(work), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        [sha] = await committed(session, 1)
        cut, uncommitted = await diff_of(session, sha), await diff_of(session, "@ada")
        kept, held = await patch_of(session, cut), await patch_of(session, uncommitted)

    whole = git("diff-tree", "-p", "--root", "--no-commit-id", "-M", sha, cwd=repo).encode()
    assert len(whole) > LIMIT and whole.startswith(kept)
    assert LIMIT - len(kept) < len(whole[len(kept) :].split(b"\n", 1)[0]) + 1 and kept.endswith(b"\n")
    assert cut.data["cut"] is True
    assert cut.gist == f"{sha[:12]} patch, cut after {kept.count(b'\n')} lines at 64 KiB"
    assert uncommitted.data["cut"] is True and len(held) <= LIMIT and held.endswith(b"\n")
    assert b"later.txt" not in held


async def test_a_binary_file_is_named_in_a_patch_and_never_shown(repo, tmp_path):
    """As git names one, in a commit's patch and among a workspace's untracked files."""
    secret = "\x00\x01 bytes nobody reads \x00" * 8

    def work(cwd: Path) -> None:
        commit(cwd, "blob.bin", secret)
        changed(cwd, "fresh.bin", secret)

    async with Session.start(team_of(work), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        [sha] = await committed(session, 1)
        patches = [await patch_of(session, await diff_of(session, of)) for of in (sha, "@ada")]

    assert b"Binary files /dev/null and b/blob.bin differ\n" in patches[0]
    assert b"Binary files /dev/null and b/fresh.bin differ\n" in patches[1]
    assert b"bytes nobody reads" not in b"".join(patches)


async def test_a_hostile_repository_config_runs_no_external_diff_textconv_or_hook(repo, tmp_path):
    """A snapshot agent writes its repository's config: an external diff, a diff driver's command and textconv for every
    file, an fsmonitor, hooks, a pager, colour and no prefixes. None of it runs or shapes the patch, of its commit or of
    what it left uncommitted."""
    ran, hooks, program = tmp_path / "ran", tmp_path / "hooks", tmp_path / "program"
    program.write_text(f'#!/bin/sh\necho "$0 $*" >> {ran}\ncat "$1"\n')
    hooks.mkdir()
    for name in ("post-index-change", "reference-transaction", "post-checkout", "pre-commit"):
        (hooks / name).write_text(f"#!/bin/sh\necho {name} >> {ran}\n")
    for made in (program, *hooks.iterdir()):
        made.chmod(made.stat().st_mode | stat.S_IXUSR)

    def hostile(cwd: Path) -> None:
        commit(cwd, "value.txt", "old\n")
        with (cwd / ".git" / "config").open("a") as config:
            config.write(
                f"[diff]\n\texternal = {program}\n\tnoprefix = true\n"
                f'[diff "evil"]\n\ttextconv = {program}\n\tcommand = {program}\n'
                f"[core]\n\tfsmonitor = {program}\n\thooksPath = {hooks}\n\tpager = {program}\n"
                f"[pager]\n\tdiff = {program}\n[color]\n\tui = always\n\tdiff = always\n"
                f"[log]\n\tshowSignature = true\n[gpg]\n\tprogram = {program}\n"
            )
        (cwd / ".git" / "info" / "attributes").write_text("* diff=evil\n")
        changed(cwd, "value.txt", "new\n")
        changed(cwd, "fresh.txt", "fresh\n")

    async with Session.start(team_of(hostile, workspace="snapshot"), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        [sha] = await committed(session, 1)
        patches = [await patch_of(session, await diff_of(session, of)) for of in (sha, "@ada")]

    assert not ran.exists()
    assert patches[0].startswith(b"diff --git a/value.txt b/value.txt\nnew file mode 100644\n")
    assert patches[0].endswith(b"+++ b/value.txt\n@@ -0,0 +1 @@\n+old\n")
    assert patches[1].startswith(b"diff --git a/value.txt b/value.txt\n")
    assert b"--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n-old\n+new\n" in patches[1]
    assert patches[1].endswith(b"--- /dev/null\n+++ b/fresh.txt\n@@ -0,0 +1 @@\n+fresh\n")
    assert b"\x1b" not in b"".join(patches)


async def test_a_snapshot_s_diff_is_read_in_its_own_repository(repo, tmp_path):
    """Only the snapshot holds its agent's commit, so its patch is read there, as is what it left uncommitted."""

    def work(cwd: Path) -> None:
        commit(cwd, "work.txt", "snapshot's\n")
        changed(cwd, "README", "changed in the snapshot\n")

    async with Session.start(team_of(work, workspace="snapshot"), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        [sha] = await committed(session, 1)
        of_commit, of_workspace = await diff_of(session, sha), await diff_of(session, "@ada")
        patches = [await patch_of(session, record) for record in (of_commit, of_workspace)]

    with pytest.raises(subprocess.CalledProcessError):
        git("cat-file", "-e", f"{sha}^{{commit}}", cwd=repo)
    assert of_commit.data["sha"] == sha and patches[0].endswith(b"@@ -0,0 +1 @@\n+snapshot's\n")
    assert of_workspace.data["head"] == sha
    assert patches[1].endswith(b"@@ -1 +1 @@\n-hello\n+changed in the snapshot\n")
    assert of_workspace.gist == f"@ada uncommitted against {sha[:12]}, {patches[1].count(b'\n')} lines"


async def test_a_diff_that_cannot_be_read_says_why(repo, tmp_path):
    """A workspace gone from under its agent records why and no patch."""

    team = team_of(lambda cwd: commit(cwd, "work.txt"))
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        await committed(session, 1)
        tree = Path((await session.status("@ada"))["workspace"]["path"])
        os.rename(tree, tmp_path / "moved")
        record = await diff_of(session, "@ada")
        os.rename(tmp_path / "moved", tree)

    assert record.data["body"] is None and record.data["why"].startswith(f"git cannot run in {tree}")
    assert record.gist.startswith(f"@ada uncommitted could not be read: git cannot run in {tree}")


async def test_your_checkout_s_diff_is_refused_while_no_role_works_there(repo, tmp_path):
    """What it holds uncommitted is then yours, which no look records either."""
    team = Team.model_validate({"roles": {"worker": {"harness": scripted(), "workspace": "worktree", "count": 0}}})
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        with pytest.raises(Refused) as refused:
            await session.repo_diff("shared")

    assert refused.value.refusal.code == "not_found"
    assert refused.value.refusal.detail == "no role works in your checkout, so what it holds uncommitted is yours alone"


async def test_a_diff_the_journal_recorded_is_not_read_again(repo, tmp_path):
    """A crash between its record and its finish leaves its effect started, which the next runtime retries, and the
    retry finds the record and reads nothing."""
    from .test_recovery import abandon

    (repo / "README").write_text("first\n")
    session = await Session.start(team_of(), name="s", root=tmp_path, cwd=repo)
    runtime = session._runtime
    assert runtime is not None
    real, recorded = runtime.host._acts["diff"], asyncio.Event()

    async def dies(effect: Any) -> None:
        await real(effect)
        recorded.set()
        await asyncio.Event().wait()

    runtime.host._acts["diff"] = dies
    asked = await session.repo_diff("shared")
    await asyncio.wait_for(recorded.wait(), SECONDS)
    await abandon(session)
    (repo / "README").write_text("second\n")

    async with Session.resume("s", root=tmp_path) as session:
        [record] = await diffed(session)
        [finished] = [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "diff"]
        kept = await patch_of(session, record)

    assert record.data["effect"] == asked["effect"] and b"+first\n" in kept
    assert finished.data["result"] == {"ref": f"{record.stream}@{record.version}"}
