"""A snapshot on real git under `tmp_path`: a repository of its own holding your tree as your git sees it, refused
where its git would see another tree, built aside and adopted after a crash, and ended without loss."""

import os
import shlex
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.primitives import Workspace
from platoon_harness.runtime import looks, workspaces

from .gitting import commit, git, repository, working
from .support import in_state, of_type, scripted, until
from .test_workspaces import problems_of, repo_of

pytestmark = pytest.mark.timeout(60)

HOST = socket.gethostname()


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


def tips(repo: Path) -> list[str]:
    return looks.tips_of(git("for-each-ref", "--format=%(objectname) %(refname)", cwd=repo))


def snapshot(repo: Path, folder: Path, agent: str = "ada", opened: list[str] | None = None) -> Workspace:
    branch = f"platoon-harness/s/{agent}"
    return workspaces.make_snapshot(
        repo_of(repo), folder, branch, tips(repo) if opened is None else opened, f"s/{agent}"
    )


def shown(root: Path, path: str) -> str:
    """A file as the snapshot's own HEAD holds it."""
    return git("cat-file", "-p", f"HEAD:{path}", cwd=root)


def has(repo: Path, sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", sha], cwd=repo, capture_output=True).returncode == 0


def pruned(repo: Path) -> None:
    git("reflog", "expire", "--expire=now", "--expire-unreachable=now", "--all", cwd=repo)
    git("gc", "-q", "--prune=now", cwd=repo)


# What a snapshot holds.


def test_a_snapshot_holds_the_tree_as_git_sees_it_uncommitted_work_included(repo, tmp_path):
    (repo / "README").write_text("edited\n")
    (repo / "staged.txt").write_text("staged\n")
    git("add", "staged.txt", cwd=repo)
    (repo / "untracked.txt").write_text("untracked\n")
    (repo / "src" / "main.py").unlink()

    made = snapshot(repo, tmp_path / "ada")
    root = Path(made.path)

    assert (shown(root, "README"), shown(root, "staged.txt"), shown(root, "untracked.txt")) == (
        "edited\n",
        "staged\n",
        "untracked\n",
    )
    assert not (root / "src" / "main.py").exists()
    assert (root / "untracked.txt").read_text() == "untracked\n"
    assert git("status", "--porcelain", cwd=root) == ""
    head = git("rev-parse", "HEAD", cwd=repo).strip()
    assert git("rev-parse", "HEAD^", cwd=root).strip() == head == git("rev-parse", "HEAD", cwd=repo).strip()
    assert made.base == git("rev-parse", "HEAD", cwd=root).strip() != head
    assert git("log", "-1", "--format=%an <%ae>%n%s", cwd=root).splitlines() == [
        "platoon-harness <runtime@platoon-harness.invalid>",
        "platoon-harness: s/ada starts from your tree",
    ]
    assert (made.mode, made.branch, made.repository) == ("snapshot", "platoon-harness/s/ada", str(root / ".git"))
    assert made.objects == str(repo / ".git" / "objects")


def test_a_snapshot_of_a_clean_tree_is_its_head(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")

    assert made.base == git("rev-parse", "HEAD", cwd=repo).strip()
    assert git("symbolic-ref", "HEAD", cwd=Path(made.path)).strip() == "refs/heads/platoon-harness/s/ada"


def test_a_snapshot_leaves_ignored_and_locally_excluded_files_out(repo, tmp_path):
    commit(repo, ".gitignore", "*.log\n")
    (repo / ".git" / "info" / "exclude").write_text("scratch/\n")
    (repo / "run.log").write_text("noise\n")
    (repo / "scratch").mkdir()
    (repo / "scratch" / "notes.txt").write_text("mine\n")

    root = Path(snapshot(repo, tmp_path / "ada").path)

    assert not (root / "run.log").exists() and not (root / "scratch").exists()
    assert (root / ".git" / "info" / "exclude").read_text() == "scratch/\n"


def test_a_snapshot_is_captured_under_the_origin_s_own_config(repo, tmp_path):
    git("config", "core.autocrlf", "input", cwd=repo)
    (repo / "dos.txt").write_bytes(b"one\r\ntwo\r\n")

    root = Path(snapshot(repo, tmp_path / "ada").path)

    assert shown(root, "dos.txt") == "one\ntwo\n"


def test_a_snapshot_reads_files_as_the_checkout_s_git_does(repo, tmp_path):
    git("config", "core.autocrlf", "input", cwd=repo)
    git("config", "core.fileMode", "false", cwd=repo)
    (repo / ".git" / "info" / "attributes").write_text("*.txt text eol=lf\n")

    root = Path(snapshot(repo, tmp_path / "ada").path)

    carried = {key: git("config", "--get", key, cwd=root).strip() for key in ("core.autocrlf", "core.filemode")}
    assert carried == {"core.autocrlf": "input", "core.filemode": "false"}
    assert (root / ".git" / "info" / "attributes").read_text() == "*.txt text eol=lf\n"


def test_an_agent_commits_in_a_snapshot_as_it_would_in_a_worktree(repo, tmp_path, monkeypatch):
    root = Path(snapshot(repo, tmp_path / "ada").path)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)

    work = commit(root, "work")

    assert git("log", "-1", "--format=%an <%ae>", work, cwd=root).strip() == "Tester <tester@example.invalid>"
    assert not has(repo, work)


def test_a_snapshot_has_no_remote(repo, tmp_path):
    root = Path(snapshot(repo, tmp_path / "ada").path)

    assert git("remote", cwd=root) == ""


def test_making_a_snapshot_changes_no_ref_index_or_object_of_the_origin(repo, tmp_path):
    (repo / "README").write_text("edited\n")
    (repo / "staged.txt").write_text("staged\n")
    git("add", "staged.txt", cwd=repo)
    (repo / "untracked.txt").write_text("untracked\n")
    index = (repo / ".git" / "index").read_bytes()
    before = (
        git("for-each-ref", cwd=repo),
        git("count-objects", "-v", cwd=repo),
        git("status", "--porcelain", cwd=repo),
    )

    made = snapshot(repo, tmp_path / "ada")

    after = (
        git("for-each-ref", cwd=repo),
        git("count-objects", "-v", cwd=repo),
        git("status", "--porcelain", cwd=repo),
    )
    assert after == before and (repo / ".git" / "index").read_bytes() == index
    assert not has(repo, made.base or "")


def test_a_snapshot_holds_every_object_the_origin_s_refs_did_not_reach(repo, tmp_path):
    (repo / "staged.txt").write_text("only ever staged\n")
    git("add", "staged.txt", cwd=repo)
    blob = git("rev-parse", ":staged.txt", cwd=repo).strip()

    root = Path(snapshot(repo, tmp_path / "ada").path)
    git("rm", "-q", "--cached", "staged.txt", cwd=repo)
    (repo / "staged.txt").unlink()
    pruned(repo)

    assert not has(repo, blob)
    assert shown(root, "staged.txt") == "only ever staged\n"


# Refused before any cost.


def snapshot_team() -> Team:
    return Team.model_validate({"roles": {"bob": {"harness": scripted(), "workspace": "snapshot"}}})


def test_a_snapshot_is_refused_where_its_git_would_see_another_tree(repo, tmp_path):
    commit(repo, ".gitattributes", "*.secret filter=crypt\n")
    commit(repo, "key.secret", "ciphertext\n")
    git("config", "core.sparseCheckout", "true", cwd=repo)
    nested = repo / "vendor" / "lib"
    nested.mkdir(parents=True)
    git("init", "-q", cwd=nested)

    found = problems_of(snapshot_team(), repo, tmp_path / "home")

    assert found["error"] == [
        "roles.bob.workspace: a snapshot cannot hold 1 file a filter cleans and smudges, key.secret, as only your "
        "config runs that filter: use `worktree`",
        "roles.bob.workspace: a snapshot would hold the whole of your sparse checkout: use `worktree`",
        "roles.bob.workspace: a snapshot would leave out the untracked repositories vendor/lib/: use `worktree`",
    ]


def test_a_snapshot_carries_uncommitted_changes_so_none_is_warned_of(repo, tmp_path):
    (repo / "README").write_text("edited\n")

    assert problems_of(snapshot_team(), repo, tmp_path / "home") == {}


def conflicted(repo: Path) -> None:
    """Your checkout stopped on a merge's conflict in README."""
    git("checkout", "-q", "-b", "other", cwd=repo)
    commit(repo, "README", "other\n")
    git("checkout", "-q", "main", cwd=repo)
    commit(repo, "README", "main\n")
    with pytest.raises(subprocess.CalledProcessError):
        git("merge", "-q", "other", cwd=repo)


def test_a_snapshot_of_a_checkout_mid_merge_is_refused_before_any_cost(repo, tmp_path):
    conflicted(repo)

    found = problems_of(snapshot_team(), repo, tmp_path / "home")

    assert found["error"] == [
        "roles.bob.workspace: a snapshot would take a merge under way and 1 conflicted path in your checkout as "
        "settled: finish or abort it first, or use `worktree`"
    ]


def test_a_snapshot_made_while_your_checkout_is_mid_merge_is_refused_and_leaves_nothing(repo, tmp_path):
    conflicted(repo)

    with pytest.raises(workspaces.GitError, match="would take a merge under way"):
        snapshot(repo, tmp_path / "ada")

    assert not (tmp_path / "ada").exists()


def test_a_snapshot_of_a_split_index_writes_nothing_into_your_git_directory(repo, tmp_path):
    git("config", "core.splitIndex", "true", cwd=repo)
    git("update-index", "--split-index", cwd=repo)
    (repo / "README").write_text("edited\n")
    before = sorted(os.listdir(repo / ".git"))

    root = Path(snapshot(repo, tmp_path / "ada").path)

    assert sorted(os.listdir(repo / ".git")) == before
    assert shown(root, "README") == "edited\n"
    assert git("status", "--porcelain", cwd=root) == ""


def test_a_snapshot_with_nowhere_to_work_leaves_nothing(repo, tmp_path):
    (repo / "empty").mkdir()

    with pytest.raises(workspaces.GitError, match="empty/ holds nothing tracked or unignored at"):
        workspaces.make_snapshot(
            repo_of(repo / "empty"), tmp_path / "ada", "platoon-harness/s/ada", tips(repo), "s/ada"
        )

    assert sorted(os.listdir(tmp_path / "ada")) == []


# Made in steps, and adopted.


def test_a_snapshot_renamed_before_its_effect_finished_is_adopted(repo, tmp_path):
    (repo / "README").write_text("edited\n")
    first = snapshot(repo, tmp_path / "ada")
    (repo / "README").write_text("edited again\n")

    again = snapshot(repo, tmp_path / "ada")

    assert again == first
    assert shown(Path(again.path), "README") == "edited\n"


def test_a_leftover_part_is_taken_back_and_built_again(repo, tmp_path):
    part = tmp_path / "ada" / "workspace.part"
    (part / ".git").mkdir(parents=True)
    (part / "half.txt").write_text("half\n")

    made = snapshot(repo, tmp_path / "ada")

    assert not part.exists() and not (Path(made.path) / "half.txt").exists()
    assert made.base == git("rev-parse", "HEAD", cwd=repo).strip()


def test_a_folder_the_runtime_did_not_make_is_never_adopted(repo, tmp_path):
    (tmp_path / "ada" / "workspace").mkdir(parents=True)

    with pytest.raises(workspaces.GitError, match="is no snapshot the runtime made"):
        snapshot(repo, tmp_path / "ada")


# A look in a snapshot.


def test_a_look_in_one_snapshot_ignores_commits_only_another_holds(repo, tmp_path):
    opened = tips(repo)
    ada, bob = Path(snapshot(repo, tmp_path / "ada").path), Path(snapshot(repo, tmp_path / "bob", "bob").path)
    theirs = commit(bob, "theirs")
    mine = commit(ada, "mine", cites=theirs)

    found = looks.look(
        ada,
        base=opened[0],
        tips=[*opened, theirs],
        last={"head": theirs, "branch": "platoon-harness/s/ada"},
        makers={"@ada": (ada, ()), "@bob": (bob, ()), "shared": (repo, ())},
        record=True,
    )

    assert [(commit["sha"], commit["made_in"]) for commit in found.commits] == [(mine, "@ada")]
    assert found.commits[0]["informed_by"] == [{"written": theirs, "sha": None}]


# Ending one.


def end(
    repo: Path, tmp_path: Path, made: Workspace, left: tuple[str, ...] = (), retried: bool = False
) -> dict[str, Any]:
    return workspaces.end_snapshot(made, tmp_path / "ada", repo, left, retried=retried)


def test_an_ended_agent_s_clean_snapshot_is_removed(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")

    assert end(repo, tmp_path, made) == {"removed": True, "kept": None}
    assert sorted(path.name for path in (tmp_path / "ada").iterdir()) == []


def test_a_snapshot_its_agent_committed_in_is_kept_and_made_whole(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")
    root = Path(made.path)
    commit(root, "work")

    kept = end(repo, tmp_path, made)["kept"]

    assert kept["why"] == ["1 commit only its branch holds"]
    assert (kept["path"], kept["host"], kept["branch"]) == (str(root), HOST, "platoon-harness/s/ada")
    assert not (root / ".git" / "objects" / "info" / "alternates").exists()
    git("fsck", "--connectivity-only", "--no-dangling", cwd=root)


def test_a_kept_snapshot_survives_its_origin_pruning(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")
    root = Path(made.path)
    work = commit(root, "work")
    end(repo, tmp_path, made)
    git("commit", "-q", "--amend", "-m", "rewritten", cwd=repo)
    pruned(repo)

    assert git("log", "--format=%s", work, cwd=root).splitlines() == ["add work", "first"]
    git("fsck", "--connectivity-only", "--no-dangling", cwd=root)


def test_a_snapshot_with_a_ref_of_its_own_is_kept(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")
    root = Path(made.path)
    scratch = commit(root, "scratch")
    git("tag", "scratch", scratch, cwd=root)
    git("reset", "-q", "--hard", "HEAD~1", cwd=root)

    assert end(repo, tmp_path, made)["kept"]["why"] == [
        f"1 commit only it holds, in its other refs, stash or reflogs: {scratch[:12]}"
    ]


def test_a_snapshot_with_a_stash_is_kept(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")
    root = Path(made.path)
    (root / "README").write_text("stashed\n")
    git("stash", "-q", cwd=root)
    stashed = git("rev-list", "refs/stash", f"^{made.base}", cwd=root).split()

    kept = end(repo, tmp_path, made)["kept"]

    assert kept["why"] == [
        f"2 commits only it holds, in its other refs, stash or reflogs: {', '.join(sha[:12] for sha in stashed)}"
    ]
    assert kept["release"] == []


def test_a_snapshot_whose_commits_were_fetched_is_removed(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")
    root = Path(made.path)
    commit(root, "work")
    branch = "platoon-harness/s/ada"
    git("fetch", "-q", str(root), f"{branch}:{branch}", cwd=repo)

    assert end(repo, tmp_path, made) == {"removed": True, "kept": None}
    assert git("log", "-1", "--format=%s", branch, cwd=repo).strip() == "add work"


def test_a_snapshot_with_uncommitted_work_is_kept_as_it_was(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")
    root = Path(made.path)
    (root / "notes.txt").write_text("unfinished\n")

    kept = end(repo, tmp_path, made)["kept"]
    again = end(repo, tmp_path, made)["kept"]

    assert kept["why"] == again["why"] == ["1 uncommitted path: notes.txt"]
    assert kept["release"] == []
    assert (root / "notes.txt").read_text() == "unfinished\n"


def test_a_snapshot_stop_cut_after_its_rename_finishes_its_removal(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")
    Path(made.path).rename(tmp_path / "ada" / "workspace.gone")

    assert end(repo, tmp_path, made) == {"removed": True, "kept": None}
    assert not (tmp_path / "ada" / "workspace.gone").exists()


def test_a_snapshot_whose_folder_went_is_named_unless_its_own_stop_removed_it(repo, tmp_path):
    made = snapshot(repo, tmp_path / "ada")
    Path(made.path).rename(tmp_path / "moved aside")

    first = end(repo, tmp_path, made)
    retried = end(repo, tmp_path, made, retried=True)

    assert first["kept"]["why"] == ["its folder has gone, which only its stop removes"]
    assert (first["kept"]["bytes"], first["kept"]["release"]) == (None, [])
    assert retried == {"removed": True, "kept": None}


def test_a_kept_snapshot_s_release_commands_keep_what_it_was_kept_for(repo, tmp_path, monkeypatch):
    """Run as a person would paste them, from another folder, where every path has a space in it."""
    repo = repository(tmp_path / "my repo", monkeypatch)
    made = workspaces.make_snapshot(
        repo_of(repo), tmp_path / "my home" / "ada", "platoon-harness/s/ada", tips(repo), "s/ada"
    )
    root = Path(made.path)
    work = commit(root, "work")
    commit(root, ".gitignore", "*.log\n")
    (root / "run.log").write_text("noise\n")
    elsewhere = tmp_path / "else where"
    elsewhere.mkdir()

    kept = workspaces.end_snapshot(made, tmp_path / "my home" / "ada", repo, (), retried=False)["kept"]
    for command in kept["release"]:
        subprocess.run(shlex.split(command), cwd=elsewhere, check=True, capture_output=True)

    assert kept["why"] == ["2 commits only its branch holds", "ignored: run.log"]
    assert not root.exists() and (tmp_path / "my home").exists()
    assert has(repo, work)
    assert git("log", "-1", "--format=%s", "platoon-harness/s/ada", cwd=repo).strip() == "add .gitignore"


def uncommitted(root: Path) -> None:
    (root / "notes.txt").write_text("unfinished\n")


def stashed(root: Path) -> None:
    (root / "notes.txt").write_text("stash me\n")
    git("stash", "-q", "-u", cwd=root)


def branched(root: Path) -> None:
    git("checkout", "-q", "-b", "side", cwd=root)
    commit(root, "side")


@pytest.mark.parametrize("work", [uncommitted, stashed, branched])
def test_a_snapshot_kept_for_work_no_command_keeps_is_given_no_release(repo, tmp_path, work):
    made = snapshot(repo, tmp_path / "ada")
    work(Path(made.path))

    kept = end(repo, tmp_path, made)["kept"]

    assert kept["release"] == [] and kept["why"]
    assert Path(made.path).exists()


# Through a session.


async def test_a_snapshot_agent_s_commits_are_its_own_and_its_end_keeps_them(repo, tmp_path):
    (repo / "README").write_text("edited, uncommitted\n")
    worker = {"harness": working(lambda cwd: commit(cwd, "work")), "workspace": "snapshot", "count": 0}
    team = Team.model_validate({"roles": {"lead": {"harness": scripted(), "workspace": "snapshot"}, "worker": worker}})
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work", stays=True)
        await until(lambda: of_type(session, "repo.committed"), session)
        [found] = await of_type(session, "repo.committed")
        workspace = (await session.status("ada"))["workspace"]
        await session.cancel_agent("@ada")
        await in_state(session, "ada", "ended")

        async def stops() -> list[Any]:
            return [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "stop"]

        await until(stops, session)
        ending = await session.ending()

    root = Path(workspace["path"])
    assert workspace["mode"] == "snapshot"
    assert found.data["made_in"] == "@ada" and found.data["parents"] == [workspace["base"]]
    assert (root / "README").read_text() == "edited, uncommitted\n"
    kept = next(left for left in ending.workspaces if left["agent"] == "ada")
    assert kept["why"] == ["1 commit only its branch holds"]
    assert kept["release"] == [
        f"git -C {repo} fetch {root} platoon-harness/s/ada:platoon-harness/s/ada",
        f"rm -rf {root}",
    ]
