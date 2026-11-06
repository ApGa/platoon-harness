"""Workspaces from git and the filesystem alone: checked before any cost, made in steps git keeps a fact of, so a retry
adopts what an earlier attempt made, and ended only when nothing would go with them.

Every git call goes through the one runner, which runs no hook, no fsmonitor and no gc. See architecture section 13.
"""

import os
import re
import shlex
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

_OLDEST_GIT = (2, 36)
_CODEX_FREE = "danger-full-access"
_CARRIED = ("user.name", "user.email", "core.autocrlf", "core.eol", "core.fileMode", "core.symlinks", "core.ignoreCase")
"""What a snapshot's repository takes of what your checkout's git resolves: who commits, and how files are read and
written."""
_RUNTIME = MappingProxyType(
    {
        "GIT_AUTHOR_NAME": "platoon-harness",
        "GIT_AUTHOR_EMAIL": "runtime@platoon-harness.invalid",
        "GIT_COMMITTER_NAME": "platoon-harness",
        "GIT_COMMITTER_EMAIL": "runtime@platoon-harness.invalid",
    }
)
"""Who makes a snapshot's capture commit, which is the runtime's own act."""
_WHOLE = MappingProxyType(
    {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.splitIndex", "GIT_CONFIG_VALUE_0": "false"}
)
"""What has a capture write its index whole, so that a split index of yours puts no shared index into your git
directory."""
STATUS = ("status", "--porcelain=v2", "-z", "--untracked-files=normal", "--ignore-submodules=none")
"""How the runtime asks for a work tree's status, whatever your config says of untracked files and submodules, so that
a look and a stop read the same paths."""
UNDER_WAY = MappingProxyType(
    {
        "MERGE_HEAD": "merge",
        "rebase-merge": "rebase",
        "rebase-apply": "rebase",
        "CHERRY_PICK_HEAD": "cherry-pick",
        "REVERT_HEAD": "revert",
        "BISECT_LOG": "bisect",
        "sequencer": "sequence",
    }
)
"""What git keeps under a work tree's git directory while an operation is under way, and which operation it is. A
`sequence` is a cherry-pick or revert of several commits, between its picks."""
_FIELDS = MappingProxyType({"1": 8, "2": 9, "u": 10})  # How many fields come before a path in each kind of entry.
_NAMED = 8

__all__ = [
    "BRANCHES",
    "BUNDLE",
    "STATUS",
    "UNDER_WAY",
    "branch_of",
    "checkout",
    "end_snapshot",
    "end_worktree",
    "make_snapshot",
    "make_worktree",
    "operations",
    "present",
    "problems",
    "read_repo",
    "status_of",
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


def _some(count: int, what: str) -> str:
    return f"{count} {what}{'' if count == 1 else 's'}"


def _command(*words: str) -> str:
    """A command as a shell reads it, each word quoted where it needs to be."""
    return shlex.join(words)


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
    refused here, wherever that can be seen, and never degrades to another. An isolated workspace is a snapshot, and
    what its isolation needs is the isolation's to check."""
    found = [*_postures(team, approvals)]
    modes = {name: role.workspace for name, role in team.roles.items() if role.workspace != "shared"}
    on_git = sorted(modes)
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
        found += _repository(top, session, worktrees="worktree" in modes.values())
        prefix = git("rev-parse", "--show-prefix", cwd=cwd).strip()
        found += [
            Problem(f"roles.{name}.workspace", what) for name in on_git if (what := _nowhere(top, prefix, modes[name]))
        ]
    snapshots = sorted(name for name, mode in modes.items() if mode in ("snapshot", "isolated"))
    if snapshots:
        found += [Problem(f"roles.{name}.workspace", what) for what in _seen_otherwise(top) for name in snapshots]
    return found


def _postures(team: Team, approvals: Policy | None) -> Iterable[Problem]:
    """Codex keeps `.git` read-only under its sandboxes, so each commit in a workspace of its own escalates, which a
    headless run has nobody to approve, and `deny` refuses."""
    for name, role in team.roles.items():
        policy = approvals or role.approvals
        if role.driver != "codex" or role.workspace == "shared" or role.sandbox == _CODEX_FREE:
            continue
        yours = "" if role.sandbox else f", as under the sandbox your Codex config sets unless it is `{_CODEX_FREE}`"
        kept = f"codex keeps `.git` read-only under `workspace-write` and `read-only`{yours}, so each commit in its "
        if policy == "ask":
            what = (
                f"{kept}workspace waits on an approval, and a headless run ends `needs_human` at the first. Choose "
                f'one: `sandbox = "{_CODEX_FREE}"` runs its commands with no sandbox, `approvals = "allow"` keeps the '
                "sandbox and allows each escalation, or keep `ask` and approve each commit yourself"
            )
            yield Problem(f"roles.{name}.sandbox", what, "warning")
        elif policy == "deny":
            what = (
                f'{kept}workspace is refused under `approvals = "deny"`. Choose one: `sandbox = "{_CODEX_FREE}"` '
                'runs its commands with no sandbox, or `approvals = "allow"` keeps the sandbox and allows each '
                "escalation"
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


def _repository(top: Path, session: str | None, *, worktrees: bool) -> list[Problem]:
    """What every git mode needs of the repository: a git that knows the runner's flags, a commit to start at, the
    filters its files name, and no branch where a workspace's goes. With `worktrees`, uncommitted changes in your
    checkout are warned of, which a worktree does not carry."""
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
            f"{_some(len(lfs), 'file')} tracked by LFS and no LFS filter configured, so a workspace would hold their "
            "pointers: install git-lfs and run `git lfs install`"
        )
        found.append(Problem("cwd", what))
    refs = git("for-each-ref", "--format=%(refname:short)", f"refs/heads/{BRANCHES}", cwd=top).split()
    ours = f"{BRANCHES}/{session}"
    if taken := [ref for ref in refs if ref == BRANCHES or (session and (ref == ours or ref.startswith(f"{ours}/")))]:
        what = (
            f"a workspace's branch would collide with {_listed(taken)}: give the session another name, or, once "
            f"nothing on them is wanted, {_unbranched(top, taken)}"
        )
        found.append(Problem("cwd", what))
    submodules = [line for line in _lines(git("ls-files", "-s", "-z", cwd=top)) if line.startswith("160000 ")]
    if submodules:
        what = f"each workspace leaves {_some(len(submodules), 'submodule')} uninitialized"
        found.append(Problem("cwd", what, "warning"))
    if worktrees and (changed := [path for _, _, path in status_of(git(*STATUS, cwd=top))]):
        what = (
            f"your checkout has {_some(len(changed), 'uncommitted path')}, {_listed(changed)}, which a worktree does "
            "not carry: commit them first, or use `snapshot`, which carries them"
        )
        found.append(Problem("cwd", what, "warning"))
    return found


def _unbranched(top: Path, branches: Sequence[str]) -> str:
    """The commands that delete `branches`, each after the release of a worktree that has it checked out. `-d` refuses
    a branch whose commits are merged nowhere."""
    held = {entry.get("branch"): (path, entry) for path, entry in _worktrees(top).items()}
    commands = []
    for branch in branches:
        if (found := held.get(f"refs/heads/{branch}")) is not None:
            path, entry = found
            commands += [_command("git", "worktree", "unlock", path)] if "locked" in entry else []
            commands.append(_command("git", "worktree", "remove", path))
        commands.append(_command("git", "branch", "-d", branch))
    return "; ".join(f"`{command}`" for command in commands)


def _nowhere(top: Path, prefix: str, mode: str) -> str | None:
    """Why the session's subfolder would be missing from a workspace in `mode`, if it would: a worktree holds what your
    HEAD does, and a snapshot what is tracked or untracked and not ignored."""
    if not prefix or not git("rev-parse", "-q", "--verify", "HEAD^{commit}", cwd=top, ok=(0, 1)).strip():
        return None
    if mode == "worktree":
        if git("cat-file", "-t", f"HEAD:{prefix}", cwd=top, ok=(0, 128)).strip() == "tree":
            return None
        return f"{prefix} holds nothing committed, so a worktree's agent would have nowhere to work: commit there first"
    if _lines(git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", prefix, cwd=top)):
        return None
    return f"{prefix} holds nothing tracked or unignored, so a snapshot's agent would have nowhere to work"


def _seen_otherwise(top: Path) -> list[str]:
    """What git in a snapshot would see otherwise than git in your checkout, each in words: a tracked file a filter
    cleans and smudges, which only your config can run, a sparse checkout, which a snapshot holds whole, an untracked
    repository inside the tree, which a capture leaves out, and an operation under way or a conflict, which a capture
    would take as settled."""
    found = []
    unsettled = [f"a {kind} under way" for kind in dict.fromkeys(UNDER_WAY[name] for name in operations(top))]
    if conflicted := {entry.partition("\t")[2] for entry in _lines(git("ls-files", "-u", "-z", cwd=top))}:
        unsettled.append(_some(len(conflicted), "conflicted path"))
    if unsettled:
        found.append(
            f"a snapshot would take {' and '.join(unsettled)} in your checkout as settled: finish or abort it first, "
            "or use `worktree`"
        )
    named = git("check-attr", "-z", "--stdin", "filter", cwd=top, input=git("ls-files", "-z", cwd=top)).split("\0")
    filtered = [named[at] for at in range(0, len(named) - 2, 3) if named[at + 2] not in ("unspecified", "unset")]
    if filtered:
        found.append(
            f"a snapshot cannot hold {_some(len(filtered), 'file')} a filter cleans and smudges, "
            f"{_listed(filtered)}, as only your config runs that filter: use `worktree`"
        )
    if git("config", "--type=bool", "--get", "core.sparseCheckout", cwd=top, ok=(0, 1)).strip() == "true":
        found.append("a snapshot would hold the whole of your sparse checkout: use `worktree`")
    untracked = _lines(git("ls-files", "-z", "--others", "--exclude-standard", cwd=top))
    nested = [path for path in untracked if path.endswith("/") and (top / path / ".git").exists()]
    if nested:
        found.append(f"a snapshot would leave out the untracked repositories {_listed(nested)}: use `worktree`")
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
    it, a half-written registration be made again, and a fill that failed take its worktree back. A branch is made only
    where the session's subfolder is committed, so a spawn with nowhere to work makes nothing."""
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
        _branch(checkout, branch, repo.prefix, f"platoon-harness: made by effect {effect}", worktrees)
        forced = () if entry is None else ("-f", "-f")  # Git takes back its own half-written registration then.
        git("worktree", "add", *forced, "--no-checkout", "--lock", "--reason", reason, str(root), branch, cwd=checkout)
    try:
        lock = git("rev-parse", "--path-format=absolute", "--git-path", "index.lock", cwd=root).strip()
        Path(lock).unlink(missing_ok=True)
        git("reset", "--hard", "-q", cwd=root)
    except GitError as error:
        try:
            git("worktree", "remove", "-f", "-f", str(root), cwd=checkout)
        except GitError as stuck:
            raise GitError(f"{error}, and its worktree {root} could not be taken back: {stuck}") from None
        raise GitError(f"{error}: its worktree is taken back, and its branch {branch} stays") from None
    base = git("rev-parse", "--verify", f"{ref}^{{commit}}", cwd=checkout).strip()
    path = root / repo.prefix
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


def _branch(checkout: Path, branch: str, prefix: str, made: str, worktrees: Mapping[str, Mapping[str, str]]) -> None:
    """Make the branch at your checkout's HEAD, where `prefix` must be committed, or adopt ours: checked out nowhere,
    with one reflog entry, ours."""
    ref = f"refs/heads/{branch}"
    if not git("rev-parse", "-q", "--verify", ref, cwd=checkout, ok=(0, 1)).strip():
        head = git("rev-parse", "--verify", "HEAD^{commit}", cwd=checkout).strip()
        if git("cat-file", "-t", f"{head}:{prefix}", cwd=checkout, ok=(0, 128)).strip() != "tree":
            raise GitError(f"{prefix} holds nothing committed at {head[:12]}, so its agent has nowhere to work")
        git("update-ref", "--create-reflog", "-m", made, ref, head, "", cwd=checkout)
        return
    moved = git("log", "-g", "--format=%gs", ref, cwd=checkout).splitlines() != [made]
    if moved or any(entry.get("branch") == ref for entry in worktrees.values()):
        what = "which the runtime did not make" if moved else "which is checked out elsewhere"
        commands = _unbranched(checkout, [branch])
        raise GitError(f"a branch {branch} is in the way, {what}: once nothing on it is wanted, {commands}")


def present(workspace: Workspace, wrap: Sequence[str] = ()) -> None:
    """Refuse a git workspace a harness cannot run in: its folder gone, or no longer a work tree of its repository, as
    git run under `wrap` says. Its branch and commits stay either way."""
    if workspace.mode == "shared":
        return
    path = Path(workspace.path)
    if not path.is_dir():
        raise GitError(f"its workspace {path} has gone: put it back, and its agent can resume there")
    found = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=path, ok=(0, 128), wrap=wrap).strip()
    if found != workspace.repository:
        fix = f"`git worktree repair {path}`" if workspace.mode == "worktree" else "put its repository back"
        raise GitError(f"{path} is no longer a work tree of {workspace.repository}: {fix}")


# Making a snapshot.


def make_snapshot(repo: Repo, folder: Path, branch: str, tips: Sequence[str], made_for: str) -> Workspace:
    """Make an agent's snapshot at `<folder>/workspace`: a repository of its own, on `branch`, holding your tree as your
    git sees it now, uncommitted and untracked work included, as your HEAD or one runtime commit over it, captured
    under your repository's own config, reading your objects through alternates and holding in its own store every
    object the session's `tips` at open did not reach. It has no remote. It is built aside and renamed into place last,
    so it is whole or absent: an attempt adopts a whole one, and takes back a part, which only the runtime writes, as
    does one that fails. What `team check` refuses for a snapshot is refused again here, since your checkout may have
    changed since. `made_for` names the session and the agent in its capture commit's message."""
    checkout, root, part = Path(repo.top), folder / "workspace", folder / "workspace.part"
    objects = git("rev-parse", "--path-format=absolute", "--git-path", "objects", cwd=checkout).strip()
    if root.exists():
        on = git("symbolic-ref", "-q", "HEAD", cwd=root, ok=(0, 1, 128)).strip()
        if on != f"refs/heads/{branch}":
            raise GitError(f"{root} is no snapshot the runtime made: move it away")
    else:
        if part.exists():
            shutil.rmtree(part)
        if refused := _seen_otherwise(checkout):
            raise GitError("; ".join(refused))
        try:
            _build(checkout, part, branch, repo.prefix, tips, objects, made_for)
        except (GitError, OSError):
            shutil.rmtree(part, ignore_errors=True)
            raise
        part.rename(root)
    base = git("rev-parse", "--verify", "HEAD^{commit}", cwd=root).strip()
    path = root / repo.prefix
    repository = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root).strip()
    host = socket.gethostname()
    return Workspace(
        mode="snapshot", path=str(path), host=host, branch=branch, base=base, repository=repository, objects=objects
    )


def _build(
    checkout: Path, part: Path, branch: str, prefix: str, tips: Sequence[str], objects: str, made_for: str
) -> None:
    """Build a snapshot in `part`: its repository, borrowing `objects`, with what your checkout's git resolves for who
    commits and how files are read and written, and your local excludes and attributes; then the capture, made in your
    checkout under its own config, into a copy of its index, written whole, and into the part's own store, which must
    hold the session's subfolder `prefix`; then its own pack of what the capture reaches that `tips` do not, and the
    fill."""
    part.parent.mkdir(parents=True, exist_ok=True)
    git("init", "-q", str(part), cwd=part.parent)
    store = Path(git("rev-parse", "--path-format=absolute", "--git-path", "objects", cwd=part).strip())
    (store / "info" / "alternates").write_text(f"{objects}\n")
    for key in _CARRIED:
        if value := git("config", "--get", key, cwd=checkout, ok=(0, 1)).strip():
            git("config", key, value, cwd=part)
    for name in ("info/exclude", "info/attributes", "index"):
        yours = Path(git("rev-parse", "--path-format=absolute", "--git-path", name, cwd=checkout).strip())
        mine = Path(git("rev-parse", "--path-format=absolute", "--git-path", name, cwd=part).strip())
        if yours.exists():
            mine.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(yours, mine)
    index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=part).strip())
    captured = {
        "GIT_INDEX_FILE": str(index),
        "GIT_OBJECT_DIRECTORY": str(store),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": objects,
        **_WHOLE,
    }
    git("add", "-A", cwd=checkout, env=captured)
    tree = git("write-tree", cwd=checkout, env=captured).strip()
    base = head = git("rev-parse", "--verify", "HEAD^{commit}", cwd=checkout).strip()
    if tree != git("rev-parse", f"{head}^{{tree}}", cwd=checkout).strip():
        message = (
            f"platoon-harness: {made_for} starts from your tree\n\nThe tree of {checkout} as your git saw it when this "
            "snapshot was made, its uncommitted and untracked work included."
        )
        base = git("commit-tree", tree, "-p", head, "-m", message, cwd=checkout, env={**captured, **_RUNTIME}).strip()
    if git("cat-file", "-t", f"{base}:{prefix}", cwd=part, ok=(0, 128)).strip() != "tree":
        raise GitError(f"{prefix} holds nothing tracked or unignored at {base[:12]}, so its agent has nowhere to work")
    given = f"{base}\n" + "".join(f"^{tip}\n" for tip in tips)
    if listed := git("rev-list", "--objects", "--ignore-missing", "--stdin", cwd=part, input=given):
        git("pack-objects", "-q", str(store / "pack" / "pack"), cwd=part, input=listed)
    git("update-ref", f"refs/heads/{branch}", base, cwd=part)
    git("symbolic-ref", "HEAD", f"refs/heads/{branch}", cwd=part)
    git("reset", "--hard", "-q", cwd=part)


# Ending a worktree.


def end_worktree(workspace: Workspace, folder: Path, checkout: Path, left: Sequence[str]) -> dict[str, Any]:
    """Remove an ended agent's worktree only when nothing would go with it, as git says: its processes gone, which
    `left` says were not, no path in its status, ignored ones included, no operation under way, no index entry hidden
    from status while its file is there, and no commit its own HEAD, reflog or refs hold that is not its base or
    reachable from a ref of your repository. Otherwise it stays, locked, and is named with why. Its branch always
    stays. Each step is safe to repeat, so a stop retried after a crash finishes what the last one began."""
    root = (folder / "workspace").resolve()
    entry = _worktrees(checkout).get(str(root))
    ignored: list[str] = []
    if not root.exists():
        if entry is None:
            return {"removed": True, "kept": None}  # An earlier stop removed it.
        why = ["its folder has gone, and git still holds its reflog: `git worktree prune` forgets it once unlocked"]
    else:
        try:
            lost, ignored = _losses(root, ())
            alone = _only_in_worktree(root, checkout, workspace.base)
            why = [*(["a process of its may still run"] if left else []), *lost, *alone]
        except GitError as error:
            why = [f"could not be read: {error}"]
    if not why and not ignored:
        if entry is not None and "locked" in entry:  # A stop cut after its unlock finds it unlocked.
            git("worktree", "unlock", str(root), cwd=checkout)
        try:
            git("worktree", "remove", str(root), cwd=checkout)
            return {"removed": True, "kept": None}
        except GitError as error:
            git("worktree", "lock", "--reason", _reason(root), str(root), cwd=checkout)
            why = [f"git would not remove it: {error}"]
    me = ("git", "-C", str(checkout), "worktree")
    release = () if why else (_command(*me, "unlock", str(root)), _command(*me, "remove", str(root)))
    return _kept(workspace, root, [*why, *ignored], release)


def _kept(workspace: Workspace, root: Path, why: Sequence[str], release: Sequence[str]) -> dict[str, Any]:
    """What a stop says of a workspace it left in place."""
    size = _bytes(root) if root.exists() else None
    host = socket.gethostname()
    kept = Kept(path=str(root), host=host, branch=workspace.branch, bytes=size, why=tuple(why), release=tuple(release))
    return {"removed": False, "kept": kept.model_dump(mode="json")}


def end_snapshot(
    workspace: Workspace, folder: Path, checkout: Path, left: Sequence[str], *, retried: bool, wrap: Sequence[str] = ()
) -> dict[str, Any]:
    """Remove an ended agent's snapshot only when nothing would go with it, as git says, by the rule a worktree's end
    follows, where the commits it alone holds are those of all its refs, its stash and its reflogs: it is renamed aside
    first, so a crash part of the way leaves it whole or going, and its folder gone is taken as removed only where
    that began or this stop is `retried`, since only a stop removes it. Otherwise it stays, made whole, so that your
    repository's pruning cannot take what it borrowed. Git runs in it under `wrap`."""
    root, gone = folder / "workspace", folder / "workspace.gone"
    began = gone.exists()
    if began:
        shutil.rmtree(gone)
    if not root.exists():
        if began or retried:
            return {"removed": True, "kept": None}  # An earlier attempt of this stop removed it.
        return _kept(workspace, root, ["its folder has gone, which only its stop removes"], ())
    ignored: list[str] = []
    carried: list[str] = []
    try:
        lost, ignored = _losses(root, wrap)
        carried, elsewhere = _only_in_snapshot(root, wrap, checkout, workspace.base, workspace.branch)
        why = [*(["a process of its may still run"] if left else []), *lost, *elsewhere]
    except GitError as error:
        why = [f"could not be read: {error}"]
    if not why and not carried and not ignored:
        root.rename(gone)
        shutil.rmtree(gone)
        return {"removed": True, "kept": None}
    alternates = Path(
        git("rev-parse", "--path-format=absolute", "--git-path", "objects/info/alternates", cwd=root, wrap=wrap).strip()
    )
    if alternates.exists():
        git("repack", "-a", "-d", "-q", cwd=root, wrap=wrap)
        alternates.unlink()
    branch = workspace.branch or ""
    fetch = [_command("git", "-C", str(checkout), "fetch", str(root), f"{branch}:{branch}")] if carried else []
    release = () if why else (*fetch, _command("rm", "-rf", str(root)))
    return _kept(workspace, root, [*why, *carried, *ignored], release)


def _only_in_snapshot(
    root: Path, wrap: Sequence[str], checkout: Path, base: str | None, branch: str | None
) -> tuple[list[str], list[str]]:
    """The commits a snapshot's refs, stash and reflogs hold that are neither its base nor reachable from a ref of your
    repository, in words: those its branch holds, which a fetch of it makes yours, and the rest, named. They are read
    in the snapshot, which sees your commits through its alternates."""
    refs = ("for-each-ref", "--format=%(objecttype) %(objectname)")
    yours = [line.split()[1] for line in git(*refs, cwd=checkout).splitlines() if line.split()[0] in ("commit", "tag")]
    mine = git(*refs, cwd=root, wrap=wrap).splitlines()
    held = {
        *git("log", "-g", "--all", "--format=%H", cwd=root, wrap=wrap).split(),
        *(line.split()[1] for line in mine if line.split()[0] in ("commit", "tag")),
        git("rev-parse", "--verify", "HEAD", cwd=root, wrap=wrap).strip(),
    }
    known = [*filter(None, (base,)), *yours]
    alone = _beyond(root, wrap, held, known)
    on = f"refs/heads/{branch}^{{commit}}"
    tip = git("rev-parse", "-q", "--verify", on, cwd=root, ok=(0, 1), wrap=wrap).strip()
    elsewhere = _beyond(root, wrap, held, [*known, tip]) if alone and tip else alone
    carried = len(alone) - len(elsewhere)
    on_branch = [f"{_some(carried, 'commit')} only its branch holds"] if carried else []
    rest = f"{_some(len(elsewhere), 'commit')} only it holds, in its other refs, stash or reflogs: {_shas(elsewhere)}"
    return on_branch, [rest] if elsewhere else []


def _beyond(root: Path, wrap: Sequence[str], held: Iterable[str], known: Iterable[str]) -> list[str]:
    """The commits `held` reach and `known` do not, newest first, and a child before its parent however close their
    times. A commit this repository lacks excludes nothing."""
    given = "".join(f"{sha}\n" for sha in held) + "".join(f"^{sha}\n" for sha in known)
    return git("rev-list", "--topo-order", "--ignore-missing", "--stdin", cwd=root, input=given, wrap=wrap).split()


def _shas(commits: Sequence[str]) -> str:
    return _listed([sha[:12] for sha in commits])


def _losses(root: Path, wrap: Sequence[str]) -> tuple[list[str], list[str]]:
    """What removing a workspace would lose that is not committed, each in words: what may be work, then its ignored
    files, apart, which a release may drop since they are named."""
    found = []
    entries = status_of(git(*STATUS, "--ignored", cwd=root, wrap=wrap))
    if uncommitted := [path for kind, _, path in entries if kind != "!"]:
        found.append(f"{_some(len(uncommitted), 'uncommitted path')}: {_listed(uncommitted)}")
    kinds = {UNDER_WAY[name] for name in operations(root, wrap)}
    found += sorted(f"a {'sequence of picks' if kind == 'sequence' else kind} under way" for kind in kinds)
    flagged = [(entry[0], entry[2:]) for entry in _lines(git("ls-files", "-v", "-z", cwd=root, wrap=wrap))]
    if hidden := [path for flag, path in flagged if (flag.islower() or flag == "S") and os.path.lexists(root / path)]:
        found.append(f"{_some(len(hidden), 'path')} hidden from status: {_listed(hidden)}")
    ignored = [path for kind, _, path in entries if kind == "!"]
    return found, [f"ignored: {_listed(ignored)}"] if ignored else []


def _only_in_worktree(root: Path, checkout: Path, base: str | None) -> list[str]:
    """The commits a worktree's own HEAD, reflog and refs hold that are neither its base nor reachable from a ref of
    your repository, named, if any."""
    held = {
        *git("log", "-g", "--format=%H", "HEAD", cwd=root).split(),
        *git("for-each-ref", "--format=%(objectname)", "refs/worktree", "refs/bisect", cwd=root).split(),
        git("rev-parse", "--verify", "HEAD", cwd=root).strip(),
    }
    given = "".join(f"{sha}\n" for sha in held) + (f"^{base}\n" if base else "")
    listed = ("rev-list", "--topo-order", "--ignore-missing", "--stdin", "--not", "--glob=refs/*")
    alone = git(*listed, cwd=checkout, input=given).split()
    if not alone:
        return []
    return [f"{_some(len(alone), 'commit')} only it holds, in its HEAD, reflog or own refs: {_shas(alone)}"]


def operations(root: Path, wrap: Sequence[str] = ()) -> dict[str, Path]:
    """What git keeps of each operation under way in a work tree, by its name in `UNDER_WAY`, in that table's order, as
    git run under `wrap` says."""
    names = list(UNDER_WAY)
    asked = (part for name in names for part in ("--git-path", name))
    paths = git("rev-parse", "--path-format=absolute", *asked, cwd=root, wrap=wrap).splitlines()
    return {name: Path(path) for name, path in zip(names, paths, strict=True) if Path(path).exists()}


def status_of(text: str) -> list[tuple[str, str, str]]:
    """Each path `git status --porcelain=v2 -z` names, as the kind of its entry, its index and work tree letters where
    it has them, and the path: a rename's other path and the headers are passed over."""
    found, entries = [], iter(_lines(text))
    for entry in entries:
        kind = entry[0]
        if kind in _FIELDS:
            found.append((kind, entry[2:4], entry.split(" ", _FIELDS[kind])[-1]))
        elif kind != "#":
            found.append((kind, "", entry[2:]))
        if kind == "2":
            next(entries)  # A rename's other path.
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


def write_bundle(
    folder: Path, repo: Repo, commits: Sequence[str], repositories: Mapping[str, Sequence[str]]
) -> dict[str, Any]:
    """Keep every commit the journal recorded, past the session's starting HEAD, in one bundle in the session folder,
    so that a commit an agent rewrote outlives git's pruning. It replaces the last one, and holds what that held, and
    it is built in a repository of its own beside it that borrows the objects of `repositories`, each named with the
    wrap git runs under there, so nothing is written into yours."""
    scratch = Path(tempfile.mkdtemp(dir=folder, prefix=".bundle-"))
    bundle, part = folder / BUNDLE, folder / f"{BUNDLE}.part"
    try:
        git("init", "-q", "--bare", str(scratch), cwd=folder)
        objects = [
            git("rev-parse", "--path-format=absolute", "--git-path", "objects", cwd=Path(repository), wrap=wrap).strip()
            for repository, wrap in {repo.repository: (), **repositories}.items()
            if Path(repository).is_dir()  # A snapshot its stop removed held nothing that yours does not.
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


# Testing a commit.


def checkout(sha: str, root: Path, repositories: Sequence[str]) -> None:
    """Check `sha` out at `root`, clean and detached, in a repository of its own that borrows the objects of those of
    `repositories` still there, so nothing is written into any of them and none of their own config applies. A commit
    none of them holds fails, saying so."""
    git("init", "-q", str(root), cwd=root.parent)
    store = Path(git("rev-parse", "--path-format=absolute", "--git-path", "objects", cwd=root).strip())
    objects = [
        git("rev-parse", "--path-format=absolute", "--git-path", "objects", cwd=Path(repository)).strip()
        for repository in repositories
        if Path(repository).is_dir()
    ]
    (store / "info" / "alternates").write_text("".join(f"{path}\n" for path in objects))
    if not git("rev-parse", "-q", "--verify", f"{sha}^{{commit}}", cwd=root, ok=(0, 1)).strip():
        raise GitError(f"no repository a test may read from holds {sha[:12]}")
    git("checkout", "-q", "--detach", sha, cwd=root)
