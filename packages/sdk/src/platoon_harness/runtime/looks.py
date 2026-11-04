"""A look: what git shows of one workspace now, read without changing any ref, index or file, for `repo.report`.

A look reads HEAD once and uses that commit in every later step. A commit is the agent's whose workspace's HEAD reflog
records making it: an entry that moved HEAD onto it at its own committer time, which git writes when the commit is made,
so it does not depend on which look runs first. See architecture section 13.
"""

import heapq
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .git import GitError, git
from .workspaces import UNDER_WAY, operations, status_of

PAGE = 64
"""How many commits one `repo.report` carries."""

_CITED = re.compile(r"[0-9a-f]{4,40}")
_ROOM = 8 * 1024
"""How many bytes of paths a reading holds, which leaves room in an event for the rest of it."""
_STATES = MappingProxyType(
    {"M": "modified", "A": "added", "D": "deleted", "T": "type_changed", "R": "renamed", "C": "copied"}
)

__all__ = ["PAGE", "Seen", "look", "tips_of"]


@dataclass(frozen=True)
class Seen:
    """What a look found in one workspace: the commits it holds that are new, parents first and each after what it
    cites, what its branch no longer reaches of what it did, its reading, and its whole list of paths, as text, when
    the reading holds only part of it."""

    commits: list[dict[str, Any]]
    rewrite: dict[str, Any] | None
    reading: dict[str, Any]
    whole: str | None


def tips_of(text: str) -> list[str]:
    """The commits named in the tips a session opened on, one `<sha> <ref>` a line."""
    return list(dict.fromkeys(line.split(" ", 1)[0] for line in text.splitlines() if line))


def look(
    root: Path,
    *,
    base: str | None,
    tips: Sequence[str],
    last: Mapping[str, Any] | None,
    makers: Mapping[str, Path],
    record: bool,
) -> Seen:
    """Look at the workspace whose work tree is at `root`. Its new commits are those its HEAD reaches that
    neither the session's `tips` at open, its `base` nor its `last` look's head reach. `makers` is every workspace
    still on disk by name, whose HEAD reflogs say who made each. With `record`, its uncommitted state is read too."""
    head = git("rev-parse", "-q", "--verify", "HEAD^{commit}", cwd=root, ok=(0, 1)).strip() or None
    branch = git("symbolic-ref", "-q", "--short", "HEAD", cwd=root, ok=(0, 1)).strip() or None
    known = [*tips, *filter(None, (base,))]
    looked = None if last is None else last["head"]
    found = _found(root, head, [*known, *filter(None, (looked,))], branch)
    _attribute(found, makers)
    rewrite = None if last is None or looked is None else _rewrite(root, last, head, known)
    reading: dict[str, Any] = {"head": head, "branch": branch}
    whole = None
    if record:
        state, whole = _state(root, head)
        reading |= state
    return Seen(_ordered(found), rewrite, reading, whole)


def _listed(root: Path, tips: Sequence[str], exclusions: Sequence[str]) -> list[str]:
    """What `tips` reach and `exclusions` do not, parents first. A commit this repository lacks excludes nothing, which
    is why `--ignore-missing` comes before `--stdin`."""
    given = "".join(f"{sha}\n" for sha in tips) + "".join(f"^{sha}\n" for sha in exclusions)
    return git("rev-list", "--topo-order", "--reverse", "--ignore-missing", "--stdin", cwd=root, input=given).split()


def _found(root: Path, head: str | None, exclusions: Sequence[str], branch: str | None) -> dict[str, dict[str, Any]]:
    """The new commits HEAD reaches, then those their resolvable `Informed-By` trailers cite with what those reach,
    until none is new."""
    found: dict[str, dict[str, Any]] = {}
    tips, on = [head] if head else [], branch
    while tips:
        new = _listed(root, tips, [*exclusions, *found])
        found |= {sha: {**commit, "branch": on} for sha, commit in _described(root, new).items()}
        named = dict.fromkeys(cited["sha"] for sha in new for cited in found[sha]["informed_by"])
        tips, on = [sha for sha in named if sha and sha not in found], None
    return found


def _described(root: Path, shas: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Each commit's parents, committer time, author, subject, lines against its first parent and citations."""
    if not shas:
        return {}
    given = "".join(f"{sha}\n" for sha in shas)
    form = "--format=%H%n%P%n%ct%n%an%n%s%n%(trailers:key=Informed-By,valueonly,unfold)"
    found: dict[str, dict[str, Any]] = {}
    for record in git("log", "--no-walk=unsorted", "--stdin", "-z", form, cwd=root, input=given).split("\0"):
        if record.strip():
            sha, parents, time, author, subject, *cited = record.split("\n")
            found[sha] = {
                "sha": sha,
                "parents": parents.split(),
                "time": int(time),
                "author": author,
                "subject": subject,
                "informed_by": [value.strip() for value in cited if value.strip()],
            }
    for sha, (added, removed, files) in _counted(root, given).items():
        found[sha] |= {"added": added, "removed": removed, "files": files}
    resolved = _resolved(root, {value for commit in found.values() for value in commit["informed_by"]})
    for commit in found.values():
        commit["informed_by"] = [{"written": value, "sha": resolved.get(value)} for value in commit["informed_by"]]
    return found


def _counted(root: Path, given: str) -> dict[str, tuple[int | None, int | None, int]]:
    """Each commit's lines added and removed against its first parent, None when a file's were not measured, and how
    many files it touched. With `-z`, a renamed file's paths come as two entries of their own after its counts."""
    counted: dict[str, tuple[int | None, int | None, int]] = {}
    asked = ("--no-walk=unsorted", "--stdin", "--numstat", "-z", "--diff-merges=first-parent", "--format=%H")
    tokens = iter(git("log", *asked, cwd=root, input=given).split("\0"))
    sha = ""
    for token in (token.lstrip("\n") for token in tokens):
        if token.count("\t") < 2:
            if token:
                sha, counted[token] = token, (0, 0, 0)
            continue
        added, removed, path = token.split("\t", 2)
        if not path:
            next(tokens, None)
            next(tokens, None)
        total_added, total_removed, files = counted[sha]
        counted[sha] = (_plus(total_added, added), _plus(total_removed, removed), files + 1)
    return counted


def _plus(total: int | None, count: str) -> int | None:
    """A count added to a total, which a file nobody measured, as git says `-` of a binary one, makes unknown."""
    return None if total is None or count == "-" else total + int(count)


def _resolved(root: Path, values: set[str]) -> dict[str, str]:
    """The full SHA of each value that is 4 to 40 hex digits naming one commit here. Anything else names no commit,
    a ref among them, since a ref names whatever it points at when asked."""
    candidates = {
        value: git("rev-parse", f"--disambiguate={value}", cwd=root).split()
        for value in sorted(values)
        if _CITED.fullmatch(value)
    }
    named = sorted({sha for shas in candidates.values() for sha in shas})
    asked = "".join(f"{sha}\n" for sha in named)
    kinds = git("cat-file", "--batch-check=%(objectname) %(objecttype)", cwd=root, input=asked) if named else ""
    commits = {line.split()[0] for line in kinds.splitlines() if line.endswith(" commit")}
    return {
        value: found[0]
        for value, shas in candidates.items()
        if len(found := [sha for sha in shas if sha in commits]) == 1
    }


def _attribute(found: dict[str, dict[str, Any]], makers: Mapping[str, Path]) -> None:
    """Who made each commit: the workspace whose HEAD reflog records making it, and nobody when none or two do. Every
    workspace still on disk is read, so that two which made the same commit are both seen."""
    made: dict[str, list[str]] = {sha: [] for sha in found}
    for name, root in makers.items() if found else ():
        for sha in _made(root, found):
            made[sha].append(name)
    for sha, commit in found.items():
        commit["made_in"] = made[sha][0] if len(made[sha]) == 1 else None


def _made(root: Path, commits: Mapping[str, Mapping[str, Any]]) -> set[str]:
    """The commits whose making this work tree's HEAD reflog records: an entry onto one at its own committer time."""
    found = set()
    for line in git("log", "-g", "--date=unix", "--format=%H %gd", "HEAD", cwd=root).splitlines():
        sha, _, entry = line.partition(" ")
        when = entry[entry.rfind("{") + 1 : -1]
        if sha in commits and when.isdecimal() and int(when) == commits[sha]["time"]:
            found.add(sha)
    return found


def _rewrite(root: Path, last: Mapping[str, Any], head: str | None, known: Sequence[str]) -> dict[str, Any] | None:
    """What the branch the last look saw HEAD on, or HEAD itself when it was detached, no longer reaches of what that
    look's head did, and that the session did not start with."""
    was, branch = last["head"], last["branch"]
    ref = f"refs/heads/{branch}^{{commit}}"
    now = (git("rev-parse", "-q", "--verify", ref, cwd=root, ok=(0, 1)).strip() or None) if branch else head
    if now == was:
        return None
    dropped = _listed(root, [was], [*filter(None, (now,)), *known])
    return {"branch": branch, "was": was, "now": now, "dropped": dropped} if dropped else None


def _state(root: Path, head: str | None) -> tuple[dict[str, Any], str | None]:
    """Its uncommitted paths, conflicted first and cut to fit, any operation under way, and the whole list as text when
    it was cut. Status must name the HEAD read first, or HEAD moved between the two, and that would be a mixed state."""
    status = git("status", "--porcelain=v2", "--branch", "-z", "--untracked-files=normal", cwd=root)
    named = next((entry for entry in status.split("\0") if entry.startswith("# branch.oid ")), "")
    if named.removeprefix("# branch.oid ") != (head or "(initial)"):
        raise GitError(f"HEAD moved during the look, from {head} to {named.removeprefix('# branch.oid ')}")
    counts = _changed_lines(root, head) if head else {}
    paths = [
        {
            "path": path,
            "state": "conflicted" if kind == "u" else "untracked" if kind == "?" else _state_of(xy),
            "added": None if kind == "?" else counts.get(path, (None, None))[0],
            "removed": None if kind == "?" else counts.get(path, (None, None))[1],
        }
        for kind, xy, path in status_of(status)
    ]
    paths.sort(key=lambda found: (found["state"] != "conflicted", found["path"]))
    shown, size = [], 0
    for path in paths:
        size += len(json.dumps(path, ensure_ascii=False).encode())
        if size > _ROOM:
            break
        shown.append(path)
    under_way, rebasing = _under_way(root)
    state = {
        "under_way": under_way,
        "rebasing": rebasing,
        "paths": shown,
        "total": len(paths),
        "conflicted": sum(path["state"] == "conflicted" for path in paths),
        "body": None,
    }
    return state, json.dumps(paths, ensure_ascii=False) if len(shown) < len(paths) else None


def _ordered(found: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Parents first, and each commit after the commits it cites, otherwise in the order git listed them."""
    place = {sha: index for index, sha in enumerate(found)}
    waits = {
        sha: {*commit["parents"], *(cited["sha"] for cited in commit["informed_by"])} & found.keys() - {sha}
        for sha, commit in found.items()
    }
    then: dict[str, list[str]] = {sha: [] for sha in found}
    for sha, before in waits.items():
        for other in before:
            then[other].append(sha)
    ready = [(place[sha], sha) for sha, before in waits.items() if not before]
    heapq.heapify(ready)
    ordered: dict[str, None] = {}
    while ready:
        _, sha = heapq.heappop(ready)
        ordered[sha] = None
        for other in then[sha]:
            waits[other].discard(sha)
            if not waits[other]:
                heapq.heappush(ready, (place[other], other))
    ordered |= dict.fromkeys(found)  # What a cycle of citations would leave, which only an abbreviation could make.
    return [{key: value for key, value in found[sha].items() if key != "time"} for sha in ordered]


def _state_of(xy: str) -> str:
    """A changed entry's state, from its index and work tree letters: a deletion or an addition on either side first."""
    for letter in "DATRCM":
        if letter in xy:
            return _STATES[letter]
    return "modified"


def _changed_lines(root: Path, head: str) -> dict[str, tuple[int | None, int | None]]:
    """Each tracked path's lines against the HEAD read, None for a binary one, by its path now."""
    counts: dict[str, tuple[int | None, int | None]] = {}
    tokens = iter(git("diff", "--numstat", "-z", head, "--", cwd=root).split("\0"))
    for token in tokens:
        if token.count("\t") < 2:
            continue
        added, removed, path = token.split("\t", 2)
        if not path:
            next(tokens, None)
            path = next(tokens, "")
        counts[path] = (None if added == "-" else int(added), None if removed == "-" else int(removed))
    return counts


def _under_way(root: Path) -> tuple[str | None, str | None]:
    """The operation under way, if any, and the branch a rebase is rewriting."""
    found = operations(root)
    if not found:
        return None, None
    names = (found[name] / "head-name" for name in ("rebase-merge", "rebase-apply") if name in found)
    rebasing = next((name.read_text().strip().removeprefix("refs/heads/") for name in names if name.exists()), None)
    return UNDER_WAY[next(iter(found))], rebasing
