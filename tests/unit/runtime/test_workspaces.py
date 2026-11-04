"""Workspaces on real git under `tmp_path`: checked before any cost, made in steps git keeps a fact of and adopted after
a crash, and ended only when nothing would go with them."""

import os
import shlex
import shutil
import socket
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.drivers import AgentSpec, Reporter
from platoon_harness.primitives import Repo, Workspace
from platoon_harness.runtime import workspaces
from platoon_harness.runtime.git import GitError
from platoon_harness.runtime.opening import check, make_driver
from platoon_harness.testing import ScriptedDriver

from .gitting import commit, git, repository
from .support import harness, in_state, of_type, scripted, until

pytestmark = pytest.mark.timeout(60)

HOST = socket.gethostname()


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


def repo_of(cwd: Path) -> Repo:
    found = workspaces.read_repo(cwd)
    assert found is not None
    return Repo(**found[0], tips=f"sha256:{'0' * 64}")


def made(repo: Path, folder: Path, effect: int = 7, agent: str = "ada") -> Workspace:
    return workspaces.make_worktree(repo_of(repo), folder, f"platoon-harness/s/{agent}", effect)


def registration(repo: Path, root: Path) -> str:
    """What `git worktree list` says of one worktree."""
    records = git("worktree", "list", "--porcelain", cwd=repo).split("\n\n")
    return next((record for record in records if record.startswith(f"worktree {root}\n")), "")


def workspace_team(**role: Any) -> Team:
    return Team.model_validate({"roles": {"bob": {"harness": scripted(), "workspace": "worktree", **role}}})


def workspace_of(session: Session, agent: str) -> Workspace:
    runtime = session._runtime
    assert runtime is not None
    return runtime.host._workspace_of(agent)


# Before any cost.


def problems_of(team: Team, cwd: Path, root: Path, name: str | None = "s", **options: Any) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for problem in check(team, cwd=cwd, root=root, name=name, **options):
        found.setdefault(problem.level, []).append(str(problem))
    return found


def test_a_git_mode_outside_a_git_repository_is_refused_before_any_cost(tmp_path):
    (tmp_path / "plain").mkdir()

    found = problems_of(workspace_team(), tmp_path / "plain", tmp_path / "home")

    assert found["error"] == [
        f"roles.bob.workspace: `worktree` needs a git work tree, and {tmp_path / 'plain'} is in no git work tree"
    ]
    assert not (tmp_path / "home").exists()


def test_a_bare_repository_or_one_with_no_commit_is_refused_before_any_cost(tmp_path, monkeypatch):
    repository(tmp_path / "made", monkeypatch)
    git("init", "-q", "--bare", "bare.git", cwd=tmp_path)
    (tmp_path / "empty").mkdir()
    git("init", "-q", cwd=tmp_path / "empty")

    bare = problems_of(workspace_team(), tmp_path / "bare.git", tmp_path / "home")
    empty = problems_of(workspace_team(), tmp_path / "empty", tmp_path / "home")

    assert "a bare repository, which has no work tree" in bare["error"][0]
    assert empty["error"] == [f"cwd: {tmp_path / 'empty'} has no commit yet for a workspace to start at: commit first"]


def test_lfs_files_without_an_lfs_filter_are_refused_before_any_cost(repo, tmp_path):
    commit(repo, ".gitattributes", "*.bin filter=lfs diff=lfs merge=lfs -text\n")
    commit(repo, "model.bin", "version https://git-lfs.github.com/spec/v1\n")

    found = problems_of(workspace_team(), repo, tmp_path / "home")

    assert any("1 file tracked by LFS and no LFS filter configured" in what for what in found["error"])


def test_a_session_whose_branches_exist_is_refused_before_any_cost(repo, tmp_path):
    git("branch", "platoon-harness/s/bob", cwd=repo)
    git("branch", "platoon-harness/other/bob", cwd=repo)

    found = problems_of(workspace_team(), repo, tmp_path / "home")
    other = problems_of(workspace_team(), repo, tmp_path / "home", name="fresh")

    assert found["error"] == [
        "cwd: a workspace's branch would collide with platoon-harness/s/bob: give the session another name, or, once "
        "nothing on them is wanted, `git branch -d platoon-harness/s/bob`"
    ]
    assert "error" not in other


def test_a_reused_name_s_refusal_names_the_kept_worktree_that_holds_its_branch(repo, tmp_path):
    root = tmp_path / "kept place"
    git("worktree", "add", "-q", "--lock", "-b", "platoon-harness/s/bob", str(root), cwd=repo)

    [refused] = problems_of(workspace_team(), repo, tmp_path / "home")["error"]
    commands = refused.split("wanted, ")[1].split("; ")

    assert commands == [
        f"`git worktree unlock '{root}'`",
        f"`git worktree remove '{root}'`",
        "`git branch -d platoon-harness/s/bob`",
    ]
    for command in commands:
        git(*shlex.split(command.strip("`"))[1:], cwd=repo)
    assert "error" not in problems_of(workspace_team(), repo, tmp_path / "home")


def test_a_branch_at_the_top_of_every_session_s_is_refused_for_all(repo, tmp_path):
    git("branch", "platoon-harness", cwd=repo)

    found = problems_of(workspace_team(), repo, tmp_path / "home", name=None)

    assert "`git branch -d platoon-harness`" in found["error"][0]


@pytest.mark.parametrize("mode", ["shared", "worktree"])
def test_a_session_folder_inside_the_work_tree_is_refused_before_any_cost(repo, mode):
    """In every mode: a shared agent's `git add -A` would take the session's credentials as well."""
    found = problems_of(workspace_team(workspace=mode), repo, repo / "state")
    commit(repo, ".gitignore", "state/\n")
    ignored = problems_of(workspace_team(workspace=mode), repo, repo / "state")

    assert found["error"] == [
        f"PLATOON_HARNESS_HOME: the session folder {repo / 'state/sessions/s'} lies inside {repo}, which does not "
        "ignore it, so an agent's `git add -A` would commit its credentials: choose a root outside it with "
        "PLATOON_HARNESS_HOME, or ignore it there"
    ]
    assert "error" not in ignored


def test_submodules_and_uncommitted_changes_are_warned_of_before_any_cost(repo, tmp_path, monkeypatch):
    inner = repository(tmp_path / "inner", monkeypatch)
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "inner", cwd=repo)
    git("commit", "-q", "-m", "submodule", cwd=repo)
    (repo / "README").write_text("changed\n")

    found = problems_of(workspace_team(), repo, tmp_path / "home")

    assert "error" not in found
    assert found["warning"] == [
        "cwd: each workspace leaves 1 submodule uninitialized",
        "cwd: your checkout has 1 uncommitted path, README, which a worktree does not carry: commit them first, or use "
        "`snapshot`, which carries them",
    ]


def test_uncommitted_changes_are_warned_of_whatever_status_config_says(repo, tmp_path):
    git("config", "status.showUntrackedFiles", "no", cwd=repo)
    (repo / "notes.md").write_text("mine\n")

    found = problems_of(workspace_team(), repo, tmp_path / "home")

    assert "1 uncommitted path, notes.md," in found["warning"][0]


def test_a_mode_that_cannot_be_given_is_refused_before_any_cost(repo, tmp_path):
    found = problems_of(workspace_team(workspace="isolated"), repo, tmp_path / "home")

    assert found["error"] == [f"roles.bob.workspace: {workspaces.NOT_YET['isolated']}"]


def test_isolated_with_no_extension_that_confines_is_refused_before_any_cost(repo, tmp_path):
    found = problems_of(workspace_team(workspace="isolated"), repo, tmp_path / "home")

    assert "needs an extension whose isolation confines a harness" in found["error"][0]


CODEX = {"harness": "codex", "model": "gpt-6-luna", "workspace": "worktree"}


@pytest.mark.parametrize(
    ("role", "approvals", "warned"),
    [
        ({}, None, True),
        ({"sandbox": "workspace-write"}, None, True),
        ({"sandbox": "read-only"}, None, True),
        ({"sandbox": "danger-full-access"}, None, False),
        ({"approvals": "allow"}, None, False),
        ({}, "allow", False),
        ({"workspace": "shared"}, None, False),
    ],
)
def test_a_codex_role_that_cannot_commit_in_its_workspace_is_warned_before_any_cost(
    repo, tmp_path, role, approvals, warned
):
    team = Team.model_validate({"roles": {"bob": {**CODEX, **role}}})

    found = [
        str(problem)
        for problem in workspaces.problems(team, cwd=repo, folder=tmp_path, session="s", approvals=approvals)
    ]

    said = [what for what in found if "keeps `.git` read-only" in what]
    assert bool(said) == warned
    if warned:
        assert said[0].startswith(
            "roles.bob.sandbox: codex keeps `.git` read-only under `workspace-write` and `read-only`"
        )
        for choice in ('`sandbox = "danger-full-access"`', '`approvals = "allow"`', "keep `ask`", "`needs_human`"):
            assert choice in said[0]


@pytest.mark.parametrize("approvals", [None, "deny"])
def test_a_codex_role_whose_commits_would_be_refused_is_warned_before_any_cost(repo, tmp_path, approvals):
    role = {**CODEX, "sandbox": "workspace-write"} | ({} if approvals else {"approvals": "deny"})
    team = Team.model_validate({"roles": {"bob": role}})

    found = [
        str(problem)
        for problem in workspaces.problems(team, cwd=repo, folder=tmp_path, session="s", approvals=approvals)
    ]

    assert found == [
        "roles.bob.sandbox: codex keeps `.git` read-only under `workspace-write` and `read-only`, so each commit in "
        'its workspace is refused under `approvals = "deny"`. Choose one: `sandbox = "danger-full-access"` runs its '
        'commands with no sandbox, or `approvals = "allow"` keeps the sandbox and allows each escalation'
    ]


# The repository a session opens on.


async def test_the_repository_is_recorded_once_at_open(repo, tmp_path):
    (repo / "src" / "deep").mkdir()
    cwd = repo / "src" / "deep"
    async with Session.start(workspace_team(workspace="shared"), name="s", root=tmp_path, cwd=cwd) as session:
        await in_state(session, "bob", "idle")
    commit(repo, "later")

    async with Session.resume("s", root=tmp_path) as session:
        opened = await of_type(session, "session.opened")
        tips = (await session.get_body(opened[0].data["repo"]["tips"])).decode()

    record = opened[0].data["repo"]
    assert len(opened) == 1 and opened[0].v == 2
    assert record | {"tips": None} == {
        "name": "repo",
        "top": str(repo),
        "prefix": "src/deep/",
        "head": git("rev-parse", "HEAD~1", cwd=repo).strip(),
        "branch": "refs/heads/main",
        "repository": str(repo / ".git"),
        "tips": None,
    }
    assert tips == f"{record['head']} refs/heads/main\n"


async def test_a_session_outside_any_repository_records_none(tmp_path):
    async with Session.start(workspace_team(workspace="shared"), root=tmp_path, cwd=tmp_path) as session:
        await in_state(session, "bob", "idle")
        opened = await of_type(session, "session.opened")

    assert opened[0].data["repo"] is None


# Making a worktree.


async def test_a_shared_agent_works_in_the_session_s_cwd(repo, tmp_path):
    async with Session.start(workspace_team(workspace="shared"), name="s", root=tmp_path, cwd=repo) as session:
        await in_state(session, "bob", "idle")
        workspace = workspace_of(session, "bob")

    assert workspace == Workspace(mode="shared", path=str(repo), host=HOST, repository=str(repo / ".git"))


async def test_a_worktree_is_a_locked_branch_of_its_own_in_its_agent_s_folder(repo, tmp_path):
    async with Session.start(workspace_team(), name="s", root=tmp_path / "home", cwd=repo) as session:
        await in_state(session, "bob", "idle")
        workspace = workspace_of(session, "bob")

    root = (tmp_path / "home" / "sessions" / "s" / "agents" / "bob" / "workspace").resolve()
    assert workspace.model_dump(exclude={"base"}) == {
        "mode": "worktree",
        "path": str(root),
        "host": HOST,
        "branch": "platoon-harness/s/bob",
        "repository": str(repo / ".git"),
        "objects": None,
        "assurance": "cooperative",
    }
    assert f"\nbranch refs/heads/platoon-harness/s/bob\nlocked platoon-harness: {HOST}:{root}" in registration(
        repo, root
    )
    assert (root / "src" / "main.py").read_text() == "print('hello')\n"
    assert git("status", "--porcelain", cwd=repo) == ""


async def test_a_worktree_starts_at_the_checkout_s_head_when_it_is_made(repo, tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "lead": {"harness": scripted()},
                "worker": {"harness": scripted(), "workspace": "worktree", "count": 0},
            }
        }
    )
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await in_state(session, "lead", "idle")
        integrated = commit(repo, "integrated")
        await session.spawn("ada", "worker")
        await in_state(session, "ada", "idle")
        workspace = workspace_of(session, "ada")

    assert workspace.base == integrated
    assert git("rev-parse", "platoon-harness/s/ada", cwd=repo).strip() == integrated
    assert (Path(workspace.path) / "integrated").exists()


async def test_an_agent_works_in_the_session_s_subfolder_of_its_workspace(repo, tmp_path, recording):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(recording), "workspace": "worktree"}}})
    async with Session.start(team, name="s", root=tmp_path / "home", cwd=repo / "src") as session:
        await in_state(session, "bob", "idle")
        workspace = workspace_of(session, "bob")

    root = (tmp_path / "home" / "sessions" / "s" / "agents" / "bob" / "workspace").resolve()
    assert workspace.path == str(root / "src")
    assert [spec.cwd for spec in recording.specs] == [root / "src"]


def test_a_subfolder_nothing_is_committed_in_is_refused_before_any_cost(repo, tmp_path):
    (repo / "notes").mkdir()
    (repo / "notes" / "draft").write_text("unsaved\n")
    (repo / "empty").mkdir()

    worktree = problems_of(workspace_team(), repo / "notes", tmp_path / "home")
    snapshot = problems_of(workspace_team(workspace="snapshot"), repo / "notes", tmp_path / "home")
    nothing = problems_of(workspace_team(workspace="snapshot"), repo / "empty", tmp_path / "home")

    assert worktree["error"] == [
        "roles.bob.workspace: notes/ holds nothing committed, so a worktree's agent would have nowhere to work: commit "
        "there first"
    ]
    assert "error" not in snapshot
    assert nothing["error"] == [
        "roles.bob.workspace: empty/ holds nothing tracked or unignored, so a snapshot's agent would have nowhere "
        "to work"
    ]


async def test_a_spawn_with_nowhere_to_work_makes_nothing(repo, tmp_path):
    """The subfolder went from your HEAD after the session opened: the spawn fails before it makes a branch."""
    team = Team.model_validate(
        {
            "roles": {
                "lead": {"harness": scripted()},
                "worker": {"harness": scripted(), "workspace": "worktree", "count": 0},
            }
        }
    )
    async with Session.start(team, name="s", root=tmp_path, cwd=repo / "src") as session:
        await in_state(session, "lead", "idle")
        git("rm", "-q", "-r", "src", cwd=repo)
        git("commit", "-q", "-m", "no src", cwd=repo)
        await session.spawn("ada", "worker")
        await in_state(session, "ada", "ended")
        failed = (await of_type(session, "effect.failed"))[0]
        ending = await session.ending()

    assert failed.data["error"].startswith("src/ holds nothing committed at")
    assert git("branch", "--list", "platoon-harness/*", cwd=repo) == ""
    assert git("worktree", "list", "--porcelain", cwd=repo).count("worktree ") == 1
    assert ending.workspaces == ()


def test_a_fill_that_fails_takes_its_worktree_back(repo, tmp_path, monkeypatch):
    real = workspaces.git

    def failing(*args: str, **options: Any) -> str:
        if args[:2] == ("reset", "--hard"):
            raise GitError("git reset failed: No space left on device")
        return real(*args, **options)

    monkeypatch.setattr(workspaces, "git", failing)
    with pytest.raises(GitError) as refused:
        made(repo, tmp_path / "ada")

    root = (tmp_path / "ada" / "workspace").resolve()
    assert str(refused.value) == (
        "git reset failed: No space left on device: its worktree is taken back, and its branch platoon-harness/s/ada "
        "stays"
    )
    assert registration(repo, root) == "" and not root.exists()
    assert "error" not in problems_of(workspace_team(), repo, tmp_path / "home", name="other")


async def test_the_workspace_effect_records_the_mode_that_ran(repo, tmp_path):
    team = Team.model_validate(
        {"roles": {"lead": {"harness": scripted()}, "worker": {"harness": scripted(), "workspace": "worktree"}}}
    )
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await in_state(session, "worker", "idle")
        finished = [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "workspace"]
        started = {event.agent: event.data["assurance"] for event in await of_type(session, "agent.started")}

    assert {event.agent: event.data["result"]["mode"] for event in finished} == {"lead": "shared", "worker": "worktree"}
    assert started == {"lead": "cooperative", "worker": "cooperative"}


async def test_a_branch_made_mid_session_by_something_else_fails_the_spawn_naming_it(repo, tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "lead": {"harness": scripted()},
                "worker": {"harness": scripted(), "workspace": "worktree", "count": 0},
            }
        }
    )
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await in_state(session, "lead", "idle")
        git("branch", "platoon-harness/s/ada", cwd=repo)
        await session.spawn("ada", "worker")
        await in_state(session, "ada", "ended")
        failed = (await of_type(session, "effect.failed"))[0]
        status = await session.status("ada")

    assert status["status"] == "failed"
    assert failed.data["error"] == (
        "a branch platoon-harness/s/ada is in the way, which the runtime did not make: once nothing on it is wanted, "
        "`git branch -d platoon-harness/s/ada`"
    )


def test_a_crash_after_the_branch_is_made_is_adopted(repo, tmp_path):
    reason = "platoon-harness: made by effect 7"
    workspaces._branch(repo, "platoon-harness/s/ada", "", reason, {})

    workspace = made(repo, tmp_path / "ada")

    assert workspace.base == git("rev-parse", "main", cwd=repo).strip()
    assert git("reflog", "show", "--format=%gs", "platoon-harness/s/ada", cwd=repo).split("\n")[:1] == [reason]
    assert (Path(workspace.path) / "README").exists()


def test_a_branch_that_moved_is_never_adopted(repo, tmp_path):
    workspaces._branch(repo, "platoon-harness/s/ada", "", "platoon-harness: made by effect 7", {})
    git("branch", "-f", "platoon-harness/s/ada", commit(repo, "moved"), cwd=repo)

    with pytest.raises(GitError) as refused:
        made(repo, tmp_path / "ada")

    assert "a branch platoon-harness/s/ada is in the way, which the runtime did not make" in str(refused.value)
    assert not (tmp_path / "ada" / "workspace").exists()


def test_a_branch_another_effect_made_is_never_adopted(repo, tmp_path):
    workspaces._branch(repo, "platoon-harness/s/ada", "", "platoon-harness: made by effect 6", {})

    with pytest.raises(GitError):
        made(repo, tmp_path / "ada")


def admin_of(repo: Path, root: Path) -> Path:
    """The folder where git keeps a worktree's registration."""
    return Path(git("rev-parse", "--path-format=absolute", "--git-path", "HEAD", cwd=root).strip()).parent


def half_registered(repo: Path, folder: Path, *kept: str) -> Path:
    """What a `git worktree add` killed part of the way leaves: its registration, holding only `kept` of what git
    writes into it, in the order it writes them, and the folder's `.git` once `gitdir` is there."""
    root = (folder / "workspace").resolve()
    reason = workspaces._reason(root)
    workspaces._branch(repo, "platoon-harness/s/ada", "", "platoon-harness: made by effect 7", {})
    git(
        "worktree",
        "add",
        "-q",
        "--no-checkout",
        "--lock",
        "--reason",
        reason,
        str(root),
        "platoon-harness/s/ada",
        cwd=repo,
    )
    admin = admin_of(repo, root)
    for part in sorted(os.listdir(admin)):
        if part not in kept:
            path = admin / part
            path.unlink() if path.is_file() else shutil.rmtree(path)
    if "gitdir" not in kept:
        (root / ".git").unlink()
    return admin


@pytest.mark.parametrize("kept", [("locked",), ("locked", "gitdir"), ("locked", "gitdir", "commondir")])
def test_a_crash_mid_registration_is_made_again(repo, tmp_path, kept):
    admin = half_registered(repo, tmp_path / "ada", *kept)

    workspace = made(repo, tmp_path / "ada")

    root = Path(workspace.path)
    assert (root / "README").read_text() == "hello\n"
    assert "branch refs/heads/platoon-harness/s/ada" in registration(repo, root)
    worktrees = sorted(os.listdir(admin.parent))
    assert len(worktrees) == 1, worktrees  # Nothing half-written is left behind, seen or unseen.


def test_a_crash_mid_fill_is_finished(repo, tmp_path):
    root = (tmp_path / "ada" / "workspace").resolve()
    reason = workspaces._reason(root)
    workspaces._branch(repo, "platoon-harness/s/ada", "", "platoon-harness: made by effect 7", {})
    git(
        "worktree",
        "add",
        "-q",
        "--no-checkout",
        "--lock",
        "--reason",
        reason,
        str(root),
        "platoon-harness/s/ada",
        cwd=repo,
    )
    (root / "README").write_text("hel")
    (admin_of(repo, root) / "index.lock").write_text("")

    workspace = made(repo, tmp_path / "ada")

    assert (root / "README").read_text() == "hello\n"
    assert (root / "src" / "main.py").exists()
    assert git("status", "--porcelain", cwd=root) == ""
    assert workspace.path == str(root)


def test_a_worktree_the_runtime_did_not_make_is_never_adopted(repo, tmp_path):
    root = (tmp_path / "ada" / "workspace").resolve()
    git("worktree", "add", "-q", "-b", "theirs", str(root), cwd=repo)

    with pytest.raises(GitError) as refused:
        made(repo, tmp_path / "ada")

    assert f"{root} is a worktree the runtime did not make" in str(refused.value)


def test_a_folder_in_the_way_fails_with_git_s_words(repo, tmp_path):
    root = tmp_path / "ada" / "workspace"
    root.mkdir(parents=True)
    (root / "mine").write_text("keep me\n")

    with pytest.raises(GitError) as refused:
        made(repo, tmp_path / "ada")

    assert "already exists" in str(refused.value)
    assert (root / "mine").read_text() == "keep me\n"


def test_the_runtime_s_git_runs_no_hook_no_fsmonitor_and_no_gc(repo, tmp_path, monkeypatch):
    """Ground truth twice over: what each git call was given, and that no hook or fsmonitor of the repository ran."""
    real = git("--exec-path", cwd=repo).strip()
    shims = tmp_path / "shims"
    shims.mkdir()
    log = tmp_path / "calls"
    (shims / "git").write_text(
        f'#!/bin/sh\nprintf "%s|%s|%s|%s\\n" "$GIT_OPTIONAL_LOCKS" "$LC_ALL" "$GIT_TERMINAL_PROMPT" "$*" >> {log}\n'
        f'exec {real}/git "$@"\n'
    )
    (shims / "git").chmod(0o755)
    marker = tmp_path / "ran"
    for hook in ("post-checkout", "reference-transaction", "pre-commit"):
        script = repo / ".git" / "hooks" / hook
        script.write_text(f"#!/bin/sh\necho {hook} >> {marker}\n")
        script.chmod(0o755)
    monitor = tmp_path / "monitor"
    monitor.write_text(f"#!/bin/sh\necho fsmonitor >> {marker}\n")
    monitor.chmod(0o755)
    git("config", "core.fsmonitor", str(monitor), cwd=repo)
    git("config", "gc.auto", "1", cwd=repo)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")

    workspace = made(repo, tmp_path / "ada")
    workspaces.end_worktree(workspace, tmp_path / "ada", repo, ())

    calls = log.read_text().splitlines()
    assert calls and not marker.exists()
    flags = "-c gc.auto=0 -c maintenance.auto=false -c core.hooksPath=/dev/null -c core.fsmonitor=false"
    assert all(call.startswith(f"0|C|0|{flags} -c core.logAllRefUpdates=true ") for call in calls), calls


# Launching and resuming in a workspace.


class Recording(ScriptedDriver):
    specs: list[AgentSpec] = []

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        Recording.specs.append(spec)
        return await super().start(spec, report)


@pytest.fixture
def recording() -> type[Recording]:
    Recording.specs = []
    return Recording


async def test_a_launch_and_a_resume_run_in_the_journaled_workspace(repo, tmp_path, recording):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(recording), "workspace": "worktree"}}})
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        workspace = workspace_of(session, "bob")

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        resumed = workspace_of(session, "bob")

    assert resumed == workspace
    assert [spec.cwd for spec in recording.specs] == [Path(workspace.path)] * 2
    assert recording.specs[1].resume is not None


async def test_a_workspace_path_never_changes_while_its_agent_lives(repo, tmp_path, recording):
    team = Team.model_validate({"roles": {"bob": {"harness": harness(recording), "workspace": "worktree"}}})
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)

    for _ in range(2):
        async with Session.resume("s", root=tmp_path) as session:
            await in_state(session, "bob", "idle")
            made = [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "workspace"]

    assert len(made) == 1
    assert len({spec.cwd for spec in recording.specs}) == 1


async def worked_then_left(repo: Path, tmp_path: Path) -> Path:
    """A session whose worktree agent took a turn, then whose runtime stopped, and the agent's workspace root."""
    async with Session.start(workspace_team(), name="s", root=tmp_path, cwd=repo) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        return Path(workspace_of(session, "bob").path)


async def test_a_resume_whose_workspace_is_gone_fails_loudly(repo, tmp_path):
    root = await worked_then_left(repo, tmp_path)
    root.rename(tmp_path / "away")

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        status = await session.status("bob")
        ending = await session.ending()

    assert status["status"] == "lost"
    bob = next(row for row in ending.agents if row["agent"] == "bob")
    assert bob["reason"] == f"its workspace {root} has gone: put it back, and its agent can resume there"
    assert git("rev-parse", "platoon-harness/s/bob", cwd=repo)


async def test_a_resume_whose_repository_moved_fails_naming_the_fix(repo, tmp_path):
    root = await worked_then_left(repo, tmp_path)
    git("worktree", "unlock", str(root), cwd=repo)
    (root / ".git").write_text(f"gitdir: {tmp_path / 'nowhere'}\n")

    async with Session.resume("s", root=tmp_path) as session:
        await in_state(session, "bob", "ended")
        ending = await session.ending()

    bob = next(row for row in ending.agents if row["agent"] == "bob")
    assert bob["status"] == "lost"
    assert bob["reason"] == f"{root} is no longer a work tree of {repo / '.git'}: `git worktree repair {root}`"


@pytest.mark.parametrize("mode", ["shared", "worktree"])
async def test_a_relative_command_resolves_against_the_session_s_cwd_in_every_mode(repo, tmp_path, mode):
    """The program is untracked, so a worktree does not hold it: only the session's cwd does."""
    (repo / "tools").mkdir()
    program = repo / "tools" / "say"
    program.write_text(f"#!{sys.executable}\nimport os, sys\nprint(os.getcwd(), sys.argv[1])\n")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    harnessed = {"command": ["./tools/say", "{goal}"], "mode": "oneshot"}
    team = Team.model_validate({"roles": {"bob": {"harness": harnessed, "count": 0, "workspace": mode}}})

    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "bob", "hello")
        await in_state(session, "ada", "ended")
        said = [event.gist for event in await of_type(session, "item.recorded")]
        status = await session.status("ada")

    assert status["status"] == "finished"
    assert said[-1].endswith(" hello")
    assert said[-1].startswith(
        str(repo) if mode == "shared" else str(tmp_path.resolve() / "sessions/s/agents/ada/workspace")
    )
    assert make_driver(team.roles["bob"], repo)._command[0] == str(repo / "tools" / "say")  # type: ignore[attr-defined]
