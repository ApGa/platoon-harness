"""Workspaces from git and the filesystem alone: checked before any cost, made in steps git keeps a fact of, so a retry
adopts what an earlier attempt made, and ended only when nothing would go with them.

Every git call goes through the one runner, which runs no hook, no fsmonitor and no gc. See architecture section 13.
"""

import os
import re
import shutil
import socket
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

from platoon_harness.primitives import Kept, Policy, Repo, Workspace
from platoon_harness.schema import Problem
from platoon_harness.team import Team

from .git import GitError, git
from .paths import HOME_VARIABLE

BRANCHES = "platoon-harness"
BUNDLE = "commits.bundle"
NOT_YET = MappingProxyType(
    {
        "snapshot": "`snapshot` is not built yet: use `worktree`, which shares your repository, or `shared`",
        "isolated": "`isolated` needs an extension whose isolation confines a harness, and none exists yet",
    }
)

_OLDEST_GIT = (2, 36)
_CODEX_FREE = "danger-full-access"
_UNDER_WAY = MappingProxyType(
    {
        "MERGE_HEAD": "a merge",
        "rebase-merge": "a rebase",
        "rebase-apply": "a rebase",
        "CHERRY_PICK_HEAD": "a cherry-pick",
        "REVERT_HEAD": "a revert",
        "BISECT_LOG": "a bisect",
        "sequencer": "a sequence of picks",
    }
)
_FIELDS = MappingProxyType({"1": 8, "2": 9, "u": 10})  # How many fields come before a path in each kind of entry.
_NAMED = 8

__all__ = [
    "BRANCHES",
    "BUNDLE",
    "NOT_YET",
    "branch_of",
    "end_worktree",
    "make_worktree",
    "present",
    "problems",
    "read_repo",
    "write_bundle",
]


def branch_of(session: str, agent: str) -> str:
    """An agent's branch, which no other session's can be, since a session's name is its own."""
    return f"{BRANCHES}/{session}/{agent}"


def _lines(text: str) -> list[str]:
    return [line for line in text.split("\0") if line]


def _listed(names: Sequence[str]) -> str:
    more = f" and {len(names) - _NAMED} more" if len(names) > _NAMED else ""
    return ", ".join(names[:_NAMED]) + more


# What a session opens on.


def read_repo(cwd: Path) -> tuple[dict[str, Any], str] | None:
    """The repository `cwd` is in, as git says now, all but its `tips`, and the text that names every ref and its tip,
    to store as the body `tips` cites. None outside any work tree, and with no git to ask, where nothing is observed."""
    if shutil.which("git") is None or not _in_a_work_tree(cwd):
        return None
    top, repository, prefix = git(
        "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir", "--show-prefix", cwd=cwd
    ).split("\n")[:3]
    record = {
        "name": re.sub(r"[\s@#]", "-", Path(top).name),
        "top": top,
        "prefix": prefix,
        "head": git("rev-parse", "-q", "--verify", "HEAD^{commit}", cwd=cwd, ok=(0, 1)).strip() or None,
        "branch": git("symbolic-ref", "-q", "HEAD", cwd=cwd, ok=(0, 1)).strip() or None,
        "repository": repository,
    }
    return record, git("for-each-ref", "--format=%(objectname) %(refname)", cwd=cwd)


def _in_a_work_tree(cwd: Path) -> bool:
    return git("rev-parse", "--is-inside-work-tree", cwd=cwd, ok=(0, 128)).strip() == "true"


# Before any cost.


def problems(team: Team, *, cwd: Path, folder: Path, session: str | None, approvals: Policy | None) -> list[Problem]:
    """What stops a team's workspaces, before any cost, and what a workspace will not carry, as warnings. `folder` is
    where the session's folder will be, and `session` its name, when it has one yet. A mode that cannot be given is
    refused here, wherever that can be seen, and never degrades to another."""
    found = [*_postures(team, approvals)]
    modes = {name: role.workspace for name, role in team.roles.items() if role.workspace != "shared"}
    found += [Problem(f"roles.{name}.workspace", NOT_YET[mode]) for name, mode in modes.items() if mode in NOT_YET]
    on_git = sorted(name for name, mode in modes.items() if mode not in NOT_YET)
    if shutil.which("git") is None:
        return found + [Problem(f"roles.{name}.workspace", "git is not on PATH") for name in on_git]
    if not _in_a_work_tree(cwd):
        bare = git("rev-parse", "--is-bare-repository", cwd=cwd, ok=(0, 128)).strip() == "true"
        where = "a bare repository, which has no work tree" if bare else "no git work tree"
        return found + [
            Problem(f"roles.{name}.workspace", f"`{modes[name]}` needs a git work tree, and {cwd} is in {where}")
            for name in on_git
        ]
    top = Path(git("rev-parse", "--show-toplevel", cwd=cwd).strip())
    found += _inside(top, folder)
    if on_git:
        found += _repository(top, session)
    return found


def _postures(team: Team, approvals: Policy | None) -> Iterable[Problem]:
    """Codex keeps `.git` read-only under its sandboxes, so each commit in a workspace of its own waits on an approval,
    which a headless run has nobody to give."""
    for name, role in team.roles.items():
        sandboxed, asking = role.sandbox != _CODEX_FREE, (approvals or role.approvals) == "ask"
        if role.driver == "codex" and role.workspace in ("worktree", "snapshot") and sandboxed and asking:
            yours = " and, unless your codex config says otherwise, under yours" if role.sandbox is None else ""
            what = (
                f"codex keeps `.git` read-only under `workspace-write` and `read-only`{yours}, so each commit in its "
                "workspace waits on an approval, and a headless run ends `needs_human` at the first. Choose one: "
                f'`sandbox = "{_CODEX_FREE}"` runs its commands with no sandbox, `approvals = "allow"` keeps the '
                "sandbox and allows each escalation, or keep `ask` and approve each commit yourself"
            )
            yield Problem(f"roles.{name}.sandbox", what, "warning")


def _inside(top: Path, folder: Path) -> list[Problem]:
    """A session folder in the work tree, unignored, is what an agent's `git add -A` would commit, credentials and
    all."""
    folder = folder.resolve()
    if not folder.is_relative_to(top) or git("check-ignore", f"{folder}/", cwd=top, ok=(0, 1)):
        return []
    what = (
        f"the session folder {folder} lies inside {top}, which does not ignore it, so an agent's `git add -A` would "
        f"commit its credentials: choose a root outside it with {HOME_VARIABLE}, or ignore it there"
    )
    return [Problem(HOME_VARIABLE, what)]


def _repository(top: Path, session: str | None) -> list[Problem]:
    """What every git mode needs of the repository: a git that knows the runner's flags, a commit to start at, the
    filters its files name, and no branch where a workspace's goes."""
    found = []
    version = tuple(int(part) for part in re.findall(r"\d+", git("--version", cwd=top))[:2])
    if version < _OLDEST_GIT:
        oldest = ".".join(map(str, _OLDEST_GIT))
        found.append(
            Problem("cwd", f"git {'.'.join(map(str, version))} is older than {oldest}, which a workspace needs")
        )
    if not git("rev-parse", "-q", "--verify", "HEAD^{commit}", cwd=top, ok=(0, 1)).strip():
        found.append(Problem("cwd", f"{top} has no commit yet for a workspace to start at: commit first"))
    lfs = _lines(git("ls-files", "-z", ":(attr:filter=lfs)", cwd=top))
    filters = ("filter.lfs.process", "filter.lfs.smudge")
    if lfs and not any(git("config", "--get", name, cwd=top, ok=(0, 1)).strip() for name in filters):
        what = (
            f"{len(lfs)} files are tracked by LFS and no LFS filter is configured, so a workspace would hold their "
            "pointers: install git-lfs and run `git lfs install`"
        )
        found.append(Problem("cwd", what))
    refs = git("for-each-ref", "--format=%(refname:short)", f"refs/heads/{BRANCHES}", cwd=top).split()
    ours = f"{BRANCHES}/{session}"
    if taken := [ref for ref in refs if ref == BRANCHES or (session and (ref == ours or ref.startswith(f"{ours}/")))]:
        commands = "; ".join(f"`git branch -D {ref}`" for ref in taken)
        what = f"a workspace's branch would collide with {_listed(taken)}: once nothing on them is wanted, {commands}"
        found.append(Problem("cwd", what))
    submodules = [line for line in _lines(git("ls-files", "-s", "-z", cwd=top)) if line.startswith("160000 ")]
    if submodules:
        what = f"{len(submodules)} submodules stay uninitialized in each workspace"
        found.append(Problem("cwd", what, "warning"))
    if changed := _lines(git("status", "--porcelain", "-z", cwd=top)):
        what = f"your checkout has {len(changed)} uncommitted paths, which a worktree does not carry: commit them first"
        found.append(Problem("cwd", what, "warning"))
    return found


# Making a worktree.


def _worktrees(checkout: Path) -> dict[str, dict[str, str]]:
    """Each worktree git knows of, by its path, with its fields as `worktree list` says them."""
    found = {}
    for record in git("worktree", "list", "--porcelain", "-z", cwd=checkout).split("\0\0"):
        fields = dict(field.partition(" ")[::2] for field in record.split("\0") if field)
        if "worktree" in fields:
            found[fields["worktree"]] = fields
    return found


def _reason(root: Path) -> str:
    """The lock's reason, so that a `git worktree prune` where its folder cannot be seen leaves it alone, and anyone
    reading it knows whose it is and where."""
    return f"platoon-harness: {socket.gethostname()}:{root}"


def make_worktree(repo: Repo, folder: Path, branch: str, effect: int) -> Workspace:
    """Make an agent's worktree at `<folder>/workspace`, on a new `branch` at your checkout's HEAD, in three steps git
    keeps a fact of: the branch, made with a reflog naming `effect`; the registration, locked from its start with our
    reason; and the fill. An attempt adopts what an earlier one of the same effect made, and fails, naming it, on a
    branch, registration or folder the runtime did not make. No agent has run in it, which is what lets a fill reset
    it, and a half-written registration be made again."""
    checkout, root = Path(repo.top), (folder / "workspace").resolve()
    ref, reason = f"refs/heads/{branch}", _reason(root)
    worktrees = _worktrees(checkout)
    entry = worktrees.get(str(root))
    if entry is not None and entry.get("locked") != reason:
        raise GitError(
            f"{root} is a worktree the runtime did not make: `git worktree remove {root}` once it is unwanted"
        )
    if entry is None or entry.get("branch") != ref:
        if entry is None:
            _forget_unseen(checkout, reason)
        else:
            _empty(root)
        _branch(checkout, branch, f"platoon-harness: made by effect {effect}", worktrees)
        forced = () if entry is None else ("-f", "-f")  # Git takes back its own half-written registration then.
        git("worktree", "add", *forced, "--no-checkout", "--lock", "--reason", reason, str(root), branch, cwd=checkout)
    lock = git("rev-parse", "--path-format=absolute", "--git-path", "index.lock", cwd=root).strip()
    Path(lock).unlink(missing_ok=True)
    git("reset", "--hard", "-q", cwd=root)
    base = git("rev-parse", "--verify", f"{ref}^{{commit}}", cwd=checkout).strip()
    path = root / repo.prefix
    if not path.is_dir():
        raise GitError(f"{repo.prefix} holds nothing committed at {base[:12]}, so its agent has nowhere to work")
    host = socket.gethostname()
    return Workspace(mode="worktree", path=str(path), host=host, branch=branch, base=base, repository=repo.repository)


def _forget_unseen(checkout: Path, reason: str) -> None:
    """Take back a registration git began under our reason and never wrote its folder's name into, which no git
    command can see, and nothing would ever prune, since it is locked."""
    worktrees = Path(git("rev-parse", "--path-format=absolute", "--git-path", "worktrees", cwd=checkout).strip())
    for locked in worktrees.glob("*/locked"):
        if not (locked.parent / "gitdir").exists() and locked.read_text().removesuffix("\n") == reason:
            shutil.rmtree(locked.parent)


def _empty(root: Path) -> None:
    """Leave the folder of a half-written registration empty, which holds only the `.git` file git wrote there."""
    held = sorted(path.name for path in root.iterdir()) if root.exists() else []
    if held not in ([], [".git"]):
        raise GitError(f"{root} holds {_listed(held)}, which no make of its worktree left: move them away")
    (root / ".git").unlink(missing_ok=True)


def _branch(checkout: Path, branch: str, made: str, worktrees: Mapping[str, Mapping[str, str]]) -> None:
    """Make the branch at your checkout's HEAD, or adopt ours: checked out nowhere, with one reflog entry, ours."""
    ref = f"refs/heads/{branch}"
    if not git("rev-parse", "-q", "--verify", ref, cwd=checkout, ok=(0, 1)).strip():
        head = git("rev-parse", "--verify", "HEAD^{commit}", cwd=checkout).strip()
        git("update-ref", "--create-reflog", "-m", made, ref, head, "", cwd=checkout)
        return
    moved = git("log", "-g", "--format=%gs", ref, cwd=checkout).splitlines() != [made]
    if moved or any(entry.get("branch") == ref for entry in worktrees.values()):
        what = "which the runtime did not make" if moved else "which is checked out elsewhere"
        raise GitError(
            f"a branch {branch} is in the way, {what}: `git branch -D {branch}` once nothing on it is wanted"
        )


def present(workspace: Workspace) -> None:
    """Refuse a git workspace a harness cannot run in: its folder gone, or no longer a work tree of its repository. Its
    branch and commits stay either way."""
    if workspace.mode == "shared":
        return
    path = Path(workspace.path)
    if not path.is_dir():
        raise GitError(f"its workspace {path} has gone: put it back, and its agent can resume there")
    found = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=path, ok=(0, 128)).strip()
    if found != workspace.repository:
        raise GitError(f"{path} is no longer a work tree of {workspace.repository}: `git worktree repair {path}`")


# Ending a worktree.


def end_worktree(workspace: Workspace, folder: Path, checkout: Path, left: Sequence[str]) -> dict[str, Any]:
    """Remove an ended agent's worktree only when nothing would go with it, as git says: its processes gone, which
    `left` says were not, no path in its status, ignored ones included, no operation under way, no index entry hidden
    from status, and no commit its own HEAD, reflog or refs hold that is not its base or reachable from a ref of your
    repository. Otherwise it stays, locked, and is named with why. Its branch always stays."""
    root = (folder / "workspace").resolve()
    reason = _reason(root)
    if not root.exists():
        if str(root) not in _worktrees(checkout):
            return {"removed": True, "kept": None}  # An earlier stop removed it.
        why = ["its folder has gone, and git still holds its reflog: `git worktree prune` forgets it once unlocked"]
    else:
        try:
            why = [*(["a process of its may still run"] if left else []), *_losses(root, checkout, workspace.base)]
        except GitError as error:
            why = [f"could not be read: {error}"]
    if not why:
        git("worktree", "unlock", str(root), cwd=checkout)
        try:
            git("worktree", "remove", str(root), cwd=checkout)
            return {"removed": True, "kept": None}
        except GitError as error:
            git("worktree", "lock", "--reason", reason, str(root), cwd=checkout)
            why = [f"git would not remove it: {error}"]
    kept = Kept(path=str(root), host=socket.gethostname(), branch=workspace.branch, bytes=_bytes(root), why=tuple(why))
    return {"removed": False, "kept": kept.model_dump(mode="json")}


def _losses(root: Path, checkout: Path, base: str | None) -> list[str]:
    """What removing a worktree would lose, each in words."""
    found = []
    uncommitted, ignored, entries = [], [], iter(_lines(git("status", "--porcelain=v2", "--ignored", "-z", cwd=root)))
    for entry in entries:
        kind = entry[0]
        path = entry.split(" ", _FIELDS[kind])[-1] if kind in _FIELDS else entry[2:]
        (ignored if kind == "!" else uncommitted).append(path)
        if kind == "2":
            next(entries)  # A rename's other path.
    if uncommitted:
        found.append(f"{len(uncommitted)} uncommitted paths")
    if ignored:
        found.append(f"ignored: {_listed(ignored)}")
    names = list(_UNDER_WAY)
    asked = (part for name in names for part in ("--git-path", name))
    paths = git("rev-parse", "--path-format=absolute", *asked, cwd=root).splitlines()
    found += sorted(
        {f"{_UNDER_WAY[name]} under way" for name, path in zip(names, paths, strict=True) if Path(path).exists()}
    )
    hidden = [entry for entry in _lines(git("ls-files", "-v", "-z", cwd=root)) if entry[0].islower() or entry[0] == "S"]
    if hidden:
        found.append(f"{len(hidden)} index entries hidden from status")
    held = {
        *git("log", "-g", "--format=%H", "HEAD", cwd=root).split(),
        *git("for-each-ref", "--format=%(objectname)", "refs/worktree", "refs/bisect", cwd=root).split(),
        git("rev-parse", "--verify", "HEAD", cwd=root).strip(),
    }
    given = "".join(f"{sha}\n" for sha in held) + (f"^{base}\n" if base else "")
    alone = git("rev-list", "--ignore-missing", "--stdin", "--not", "--glob=refs/*", cwd=checkout, input=given).split()
    if alone:
        found.append(f"{len(alone)} commits only it holds, in its HEAD, reflog or own refs")
    return found


def _bytes(root: Path) -> int | None:
    """What a folder takes on disk, as `du` counts it, or None when part of it cannot be read."""
    total = 0
    try:
        for top, folders, files in os.walk(root, onerror=_raise):
            total += sum(os.lstat(os.path.join(top, name)).st_blocks * 512 for name in (*folders, *files))
    except OSError:
        return None
    return total


def _raise(error: OSError) -> None:
    raise error


# Keeping what the journal recorded.


def write_bundle(folder: Path, repo: Repo, commits: Sequence[str], repositories: Iterable[str]) -> dict[str, Any]:
    """Keep every commit the journal recorded, past the session's starting HEAD, in one bundle in the session folder,
    so that a commit an agent rewrote outlives git's pruning. It replaces the last one, and holds what that held, and
    it is built in a repository of its own beside it that borrows the objects of `repositories`, so nothing is written
    into yours."""
    scratch = Path(tempfile.mkdtemp(dir=folder, prefix=".bundle-"))
    bundle, part = folder / BUNDLE, folder / f"{BUNDLE}.part"
    try:
        git("init", "-q", "--bare", str(scratch), cwd=folder)
        objects = [
            git("rev-parse", "--path-format=absolute", "--git-path", "objects", cwd=Path(repository)).strip()
            for repository in dict.fromkeys((repo.repository, *repositories))
        ]
        (scratch / "objects" / "info" / "alternates").write_text("".join(f"{path}\n" for path in objects))
        if bundle.exists():
            git("bundle", "unbundle", str(bundle), cwd=scratch)
        asked = "".join(f"{sha}\n" for sha in commits)
        kinds = git("cat-file", "--batch-check=%(objectname) %(objecttype)", cwd=scratch, input=asked).splitlines()
        held = list(dict.fromkeys(line.split()[0] for line in kinds if line.endswith(" commit")))
        if held:
            git(
                "update-ref",
                "--stdin",
                cwd=scratch,
                input="".join(f"create refs/commits/{sha} {sha}\n" for sha in held),
            )
            excluded = [f"^{repo.head}"] if repo.head else []
            git("bundle", "create", "-q", str(part), "--all", *excluded, cwd=scratch)
            part.replace(bundle)
        return {"file": BUNDLE if held else None, "commits": len(held), "missing": len(set(commits)) - len(held)}
    except (GitError, OSError) as error:
        return {"file": None, "commits": None, "missing": None, "why": str(error)}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        part.unlink(missing_ok=True)
