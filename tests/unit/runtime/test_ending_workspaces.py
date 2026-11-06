"""An ended agent's worktree goes only when nothing would go with it, as git says, and a kept one is named with where it
is, what it takes and why. The commits the journal recorded outlive git's pruning in a bundle of the session's."""

import os
import shlex
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.primitives import Workspace
from platoon_harness.runtime import LocalAuthority, host, workspaces

from .gitting import commit, git, repository, working
from .support import in_state, of_type, scripted, until
from .test_workspaces import made, registration, repo_of, workspace_of

pytestmark = pytest.mark.timeout(60)

HOST = socket.gethostname()


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


@pytest.fixture
def workspace(repo, tmp_path) -> Workspace:
    """An agent's worktree, made, with nothing in it yet but its base."""
    return made(repo, tmp_path / "ada")


@pytest.fixture
def root(workspace) -> Path:
    return Path(workspace.path)


def end(repo: Path, tmp_path: Path, workspace: Workspace, left: tuple[str, ...] = ()) -> dict[str, Any]:
    return workspaces.end_worktree(workspace, tmp_path / "ada", repo, left)


def kept_for(result: dict[str, Any]) -> list[str]:
    assert result["removed"] is False
    return result["kept"]["why"]


def test_an_ended_agent_s_clean_worktree_is_removed_and_its_branch_kept(repo, tmp_path, workspace, root):
    work = commit(root, "work")

    result = end(repo, tmp_path, workspace)

    assert result == {"removed": True, "kept": None}
    assert not root.exists()
    assert registration(repo, root) == ""
    assert git("rev-parse", "platoon-harness/s/ada", cwd=repo).strip() == work


def test_a_worktree_with_an_ignored_file_is_kept_and_named(repo, tmp_path, workspace, root):
    commit(root, ".gitignore", ".venv/\n*.pyc\n")
    (root / ".venv").mkdir()
    (root / ".venv" / "pyvenv.cfg").write_text("home = /usr\n")
    (root / "main.pyc").write_bytes(b"\0")

    assert kept_for(end(repo, tmp_path, workspace)) == ["ignored: .venv/, main.pyc"]
    assert (root / ".venv" / "pyvenv.cfg").exists()


def test_a_worktree_kept_for_its_ignored_files_alone_is_released_by_its_commands_from_anywhere(tmp_path, monkeypatch):
    """Run as a person would paste them, from another folder, where every path has a space in it."""
    repo = repository(tmp_path / "my repo", monkeypatch)
    folder = tmp_path / "my home" / "ada"
    workspace = made(repo, folder)
    root = Path(workspace.path)
    work = commit(root, ".gitignore", "*.log\n")
    (root / "run.log").write_text("noise\n")
    elsewhere = tmp_path / "else where"
    elsewhere.mkdir()

    kept = workspaces.end_worktree(workspace, folder, repo, ())["kept"]
    for command in kept["release"]:
        subprocess.run(shlex.split(command), cwd=elsewhere, check=True, capture_output=True)

    assert kept["why"] == ["ignored: run.log"]
    assert not root.exists() and folder.exists()
    assert registration(repo, root) == ""
    assert git("rev-parse", "platoon-harness/s/ada", cwd=repo).strip() == work


def test_a_worktree_on_a_detached_head_with_new_commits_is_kept(repo, tmp_path, workspace, root):
    git("checkout", "-q", "--detach", cwd=root)
    one = commit(root, "one")
    two = commit(root, "two")

    assert kept_for(end(repo, tmp_path, workspace)) == [
        f"2 commits only it holds, in its HEAD, reflog or own refs: {two[:12]}, {one[:12]}"
    ]


def test_a_commit_only_a_workspace_s_reflog_holds_keeps_it_named_and_with_no_release(repo, tmp_path, workspace, root):
    """`git worktree remove` would succeed on its clean tree and drop the commit, so no release is offered."""
    dropped = commit(root, "dropped")
    git("reset", "-q", "--hard", "HEAD~1", cwd=root)

    kept = end(repo, tmp_path, workspace)["kept"]

    assert kept["why"] == [f"1 commit only it holds, in its HEAD, reflog or own refs: {dropped[:12]}"]
    assert kept["release"] == []


def test_a_ref_only_a_worktree_holds_keeps_it(repo, tmp_path, workspace, root):
    git("checkout", "-q", "--detach", cwd=root)
    scratch = commit(root, "scratch")
    git("update-ref", "refs/worktree/scratch", scratch, cwd=root)
    git("checkout", "-q", "platoon-harness/s/ada", cwd=root)

    assert kept_for(end(repo, tmp_path, workspace)) == [
        f"1 commit only it holds, in its HEAD, reflog or own refs: {scratch[:12]}"
    ]


def test_a_worktree_mid_rebase_is_kept(repo, tmp_path, workspace, root):
    (root / "README").write_text("ours\n")
    commit(root, "README", "ours\n")
    (repo / "README").write_text("theirs\n")
    commit(repo, "README", "theirs\n")
    with pytest.raises(Exception):  # noqa: B017  The rebase stops on its conflict, which is the point.
        git("rebase", "-q", "main", cwd=root)

    why = kept_for(end(repo, tmp_path, workspace))

    assert "a rebase under way" in why
    assert "1 uncommitted path: README" in why


def test_a_skip_worktree_edit_keeps_its_worktree(repo, tmp_path, workspace, root):
    git("update-index", "--skip-worktree", "README", cwd=root)
    (root / "README").write_text("hidden from status\n")

    assert kept_for(end(repo, tmp_path, workspace)) == ["1 path hidden from status: README"]
    assert (root / "README").read_text() == "hidden from status\n"


def test_an_untouched_worktree_of_a_sparse_checkout_is_removed(repo, tmp_path):
    """Sparse checkout hides what it leaves out of the tree, and a path that is not there holds nothing to lose."""
    (repo / "docs").mkdir()
    commit(repo, "docs/a.md")
    git("sparse-checkout", "set", "src", cwd=repo)
    workspace = made(repo, tmp_path / "ada")

    assert end(repo, tmp_path, workspace) == {"removed": True, "kept": None}


def test_a_workspace_whose_processes_may_run_on_is_kept(repo, tmp_path, workspace, root):
    left = ("process group 4242 outlived its leader and cannot be proved ours",)

    assert kept_for(end(repo, tmp_path, workspace, left)) == ["a process of its may still run"]


def test_uncommitted_work_is_never_discarded(repo, tmp_path, workspace, root):
    (root / "README").write_text("edited\n")
    (root / "new.txt").write_text("new\n")
    git("add", "new.txt", cwd=root)
    (root / "untracked.txt").write_text("loose\n")

    assert kept_for(end(repo, tmp_path, workspace)) == ["3 uncommitted paths: README, new.txt, untracked.txt"]
    assert (root / "README").read_text() == "edited\n"
    assert (root / "new.txt").read_text() == "new\n"
    assert (root / "untracked.txt").read_text() == "loose\n"


@pytest.mark.parametrize("mode", ["worktree", "snapshot"])
def test_uncommitted_work_is_never_discarded_whatever_status_config_says(repo, tmp_path, mode):
    """Git's own `worktree remove` would discard it under these settings, as its check reads status as configured."""
    for setting in ("status.showUntrackedFiles=no", "diff.ignoreSubmodules=all"):
        git("config", "--global", *setting.split("="), cwd=repo)
    folder = tmp_path / "ada"
    if mode == "worktree":
        workspace = made(repo, folder)
    else:
        branch = "platoon-harness/s/ada"
        workspace = workspaces.make_snapshot(repo_of(repo), folder, branch, [], "s/ada")
    root = Path(workspace.path)
    (root / "notes.md").write_text("an agent's uncommitted work\n")

    if mode == "worktree":
        result = workspaces.end_worktree(workspace, folder, repo, ())
    else:
        result = workspaces.end_snapshot(workspace, folder, repo, (), retried=False)

    assert kept_for(result) == ["1 uncommitted path: notes.md"]
    assert (root / "notes.md").read_text() == "an agent's uncommitted work\n"


def test_a_kept_worktree_stays_locked(repo, tmp_path, workspace, root):
    (root / "untracked.txt").write_text("loose\n")

    result = end(repo, tmp_path, workspace)

    assert result["kept"]["path"] == str(root)
    assert f"locked platoon-harness: {HOST}:{root}" in registration(repo, root)
    git("worktree", "prune", cwd=repo)
    assert registration(repo, root)


def test_a_kept_worktree_is_named_with_its_host_size_and_branch(repo, tmp_path, workspace, root):
    (root / "big").write_bytes(os.urandom(64 * 1024))

    kept = end(repo, tmp_path, workspace)["kept"]

    assert kept["host"] == HOST
    assert kept["branch"] == "platoon-harness/s/ada"
    assert kept["bytes"] >= 64 * 1024
    assert kept["why"] == ["1 uncommitted path: big"]


def test_a_repeated_stop_removes_nothing_twice(repo, tmp_path, workspace, root):
    first = workspaces.end_worktree(workspace, tmp_path / "ada", repo, ())
    again = workspaces.end_worktree(workspace, tmp_path / "ada", repo, ())

    assert first == again == {"removed": True, "kept": None}
    assert git("rev-parse", "platoon-harness/s/ada", cwd=repo)


def test_a_stop_retried_after_its_unlock_finishes_the_removal(repo, tmp_path, workspace, root):
    git("worktree", "unlock", str(root), cwd=repo)  # What the attempt a crash cut did.

    assert end(repo, tmp_path, workspace) == {"removed": True, "kept": None}
    assert registration(repo, root) == ""


def test_a_worktree_whose_folder_went_is_named_and_left_registered(repo, tmp_path, workspace, root):
    root.rename(tmp_path / "away")

    why = kept_for(workspaces.end_worktree(workspace, tmp_path / "ada", repo, ()))

    assert why == ["its folder has gone, and git still holds its reflog: `git worktree prune` forgets it once unlocked"]
    assert registration(repo, root)


# Through a session.


def team_of(**worker: Any) -> Team:
    worker = {"harness": scripted(), "workspace": "worktree", "count": 0, **worker}
    return Team.model_validate({"roles": {"lead": {"harness": scripted()}, "worker": worker}})


async def test_an_ended_agent_s_stop_removes_a_clean_worktree(repo, tmp_path):
    async with Session.start(team_of(), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker")
        await in_state(session, "ada", "idle")
        root = Path(workspace_of(session, "ada").path)
        commit(root, "done")
        await session.cancel_agent("@ada")
        await until(lambda: stops(session), session)
        ending = await session.ending()

    assert not root.exists()
    assert ending.workspaces == ()
    assert git("log", "-1", "--format=%s", "platoon-harness/s/ada", cwd=repo).strip() == "add done"


async def stops(session: Session) -> list[Any]:
    return [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "stop"]


async def test_a_kept_workspace_is_named_with_its_host_size_and_reason_in_the_ending(repo, tmp_path):
    async with Session.start(team_of(), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker")
        await in_state(session, "ada", "idle")
        root = Path(workspace_of(session, "ada").path)
        (root / "notes.txt").write_text("unfinished\n")
        await session.cancel_agent("@ada")
        await until(lambda: stops(session), session)
        ending = await session.ending()

    [kept] = ending.workspaces
    assert kept["agent"] == "ada" and kept["mode"] == "worktree"
    assert kept["path"] == str(root) and kept["host"] == HOST and kept["branch"] == "platoon-harness/s/ada"
    assert kept["bytes"] > 0
    assert kept["why"] == ["1 uncommitted path: notes.txt"]
    assert kept["release"] == []
    assert (root / "notes.txt").read_text() == "unfinished\n"


async def test_a_session_that_closes_keeps_the_workspaces_of_agents_that_never_ended(repo, tmp_path):
    async with Session.start(team_of(), name="s", root=tmp_path, cwd=repo / "src") as session:
        await session.spawn("ada", "worker")
        await in_state(session, "ada", "idle")
        root = Path(workspace_of(session, "ada").path).parent
        ending = await session.settled(timeout="10s")

    [kept] = ending.workspaces
    assert ending.state == "closing"
    assert kept["path"] == str(root)
    assert kept["why"] == ["its agent has not ended"]
    assert (kept["bytes"], kept["release"]) == (None, [])
    assert root.exists()


async def test_a_stop_that_fails_still_tells_the_authority_and_its_workspace_is_named(repo, tmp_path, monkeypatch):
    heard = []

    class Hearing(LocalAuthority):
        async def finish(self, agent, outcome) -> None:
            heard.append((agent.agent, outcome.status))

    def failing(*args: Any) -> dict[str, Any]:
        raise workspaces.GitError("git worktree failed: the disk went away")

    monkeypatch.setattr(host, "end_worktree", failing)
    team = team_of()
    async with Session.start(team, name="s", root=tmp_path, cwd=repo, authority=Hearing(team)) as session:
        await session.spawn("ada", "worker")
        await in_state(session, "ada", "idle")
        await session.cancel_agent("@ada")
        await until(lambda: failed_stops(session), session)
        [kept] = (await session.ending()).workspaces

    assert heard == [("ada", "cancelled")]
    assert kept["why"] == ["its stop has not finished"] and kept["release"] == []


async def failed_stops(session: Session) -> list[Any]:
    return [event for event in await of_type(session, "effect.failed") if event.data["kind"] == "stop"]


# The commits the journal recorded.


def bundled(repo: Path, folder: Path) -> set[str]:
    """The commits a bundle names, read in a clone of its own, after it gave that clone what it holds."""
    reader = folder.parent / f"{folder.name}-reader"
    git("clone", "-q", "--no-checkout", str(repo), str(reader), cwd=folder.parent)
    bundle = str(folder / workspaces.BUNDLE)
    git("bundle", "unbundle", bundle, cwd=reader)
    return {line.split()[0] for line in git("bundle", "list-heads", bundle, cwd=reader).splitlines()}


def has(repo: Path, sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo).returncode == 0


def pruned(repo: Path) -> None:
    git("reflog", "expire", "--expire=now", "--expire-unreachable=now", "--all", cwd=repo)
    git("gc", "-q", "--prune=now", cwd=repo)


async def test_a_commit_the_agent_rewrote_and_git_then_pruned_is_still_in_the_bundle(repo, tmp_path):
    def amend(cwd: Path) -> None:
        git("commit", "-q", "--amend", "-m", "second try", cwd=cwd)

    team = team_of(harness=working(lambda cwd: commit(cwd, "work", message="first try"), amend))
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        await until(lambda: of_type(session, "repo.committed"), session)
        await session.send("@ada", "amend it")
        await until(lambda: of_type(session, "repo.rewritten"), session)
        first, second = (event.data["sha"] for event in await of_type(session, "repo.committed"))
        folder = session.folder
    async with Session.attach("s", root=tmp_path) as guest:
        stopped = (await of_type(guest, "session.stopped"))[-1]

    pruned(repo)

    assert not has(repo, first)
    assert stopped.data["bundle"] == {"file": "commits.bundle", "commits": 2, "missing": 0, "why": None}
    assert bundled(repo, folder) == {first, second}


def test_the_bundle_writes_nothing_into_your_repository(repo, tmp_path):
    work = commit(repo, "work")
    refs, objects = git("for-each-ref", cwd=repo), git("count-objects", "-v", cwd=repo)
    record = repo_of(repo).model_copy(update={"head": git("rev-parse", "HEAD~1", cwd=repo).strip()})
    folder = tmp_path / "session"
    folder.mkdir()

    written = workspaces.write_bundle(folder, record, [work], {})

    assert written == {"file": "commits.bundle", "commits": 1, "missing": 0}
    assert (git("for-each-ref", cwd=repo), git("count-objects", "-v", cwd=repo)) == (refs, objects)
    assert sorted(path.name for path in folder.iterdir()) == ["commits.bundle"]


def test_a_bundle_holds_what_the_last_one_held(repo, tmp_path):
    start = git("rev-parse", "HEAD", cwd=repo).strip()
    git("checkout", "-q", "-b", "side", cwd=repo)
    dropped = commit(repo, "dropped")
    git("checkout", "-q", "main", cwd=repo)
    git("branch", "-q", "-D", "side", cwd=repo)
    record = repo_of(repo).model_copy(update={"head": start})
    folder = tmp_path / "session"
    folder.mkdir()
    workspaces.write_bundle(folder, record, [dropped], {})
    pruned(repo)
    kept = commit(repo, "kept")

    written = workspaces.write_bundle(folder, record, [dropped, kept], {})

    assert not has(repo, dropped)
    assert written == {"file": "commits.bundle", "commits": 2, "missing": 0}
    assert bundled(repo, folder) == {dropped, kept}


def test_a_commit_git_no_longer_has_is_counted_missing(repo, tmp_path):
    folder = tmp_path / "session"
    folder.mkdir()

    written = workspaces.write_bundle(folder, repo_of(repo), ["f" * 40], {})

    assert written == {"file": None, "commits": 0, "missing": 1}
    assert not (folder / workspaces.BUNDLE).exists()


def test_a_bundle_borrows_only_from_repositories_still_there(repo, tmp_path):
    """A snapshot its stop removed held nothing your repository does not, so its going takes nothing from the bundle."""
    work = commit(repo, "work")
    record = repo_of(repo).model_copy(update={"head": git("rev-parse", "HEAD~1", cwd=repo).strip()})
    folder = tmp_path / "session"
    folder.mkdir()

    written = workspaces.write_bundle(folder, record, [work], {str(tmp_path / "gone" / ".git"): ()})

    assert written == {"file": "commits.bundle", "commits": 1, "missing": 0}
