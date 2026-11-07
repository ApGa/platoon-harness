"""A diff: what git shows of a recorded commit's patch, or of a workspace's uncommitted work, for `repo.keep`, read
without changing any ref, index or file, with no external diff, textconv or hook, and each object as it is stored. See
architecture section 13."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from platoon_harness.primitives.repo import PATCH_LIMIT

from .git import git, head_at

_PLAIN = ("--no-ext-diff", "--no-textconv", "--no-color", "--src-prefix=a/", "--dst-prefix=b/")
"""What every diff passes, so that no external diff or textconv a repository's config names runs to show it, and its
colours and prefixes are git's own. A filter still runs for an uncommitted diff, as at a look."""
_STORED = MappingProxyType({"GIT_NO_REPLACE_OBJECTS": "1"})
"""What every git of a diff sets, so that no replace ref stands in for the object a SHA names."""

__all__ = ["Diff", "patch", "uncommitted"]


@dataclass(frozen=True)
class Diff:
    """A diff as its record keeps it: its patch as `text`, to the end of the last line within `PATCH_LIMIT` bytes where
    it was longer, which `cut` says, and how many `untracked_repositories` in the work tree it shows no file of."""

    text: bytes
    cut: bool
    untracked_repositories: int = 0


def patch(root: Path, sha: str, *, wrap: Sequence[str] = ()) -> Diff:
    """A commit's patch, from the tree of the first parent its own object names, or from no tree for a root, to its own,
    as git run under `wrap` shows it in the repository whose work tree is at `root`. Its parent is read from the object,
    so no graft or shallow list changes it, and no porcelain reads it, so no signature is verified."""
    stored = _git(root, wrap, "cat-file", "commit", sha).partition("\n\n")[0]
    parent = next((line.removeprefix("parent ") for line in stored.splitlines() if line.startswith("parent ")), None)
    against = parent or _git(root, wrap, "hash-object", "-t", "tree", "--stdin", input="").strip()
    return _kept(_printed(root, wrap, PATCH_LIMIT, "diff-tree", "-p", "-M", *_PLAIN, against, sha))


def uncommitted(root: Path, *, wrap: Sequence[str] = ()) -> tuple[str | None, Diff]:
    """The HEAD the work tree at `root` holds, None before its first commit, and what it holds uncommitted against that,
    as git run under `wrap` shows it: its tracked files, staged or not, then each untracked file git does not ignore, as
    a new one, until the patch passes its bound. An untracked repository in the tree is passed over, as git shows no
    file of it, and counted. It is read only where git finds the work tree's own repository at `root`."""
    head = head_at(root, wrap=wrap)
    against = head or _git(root, wrap, "hash-object", "-t", "tree", "--stdin", input="").strip()
    printed = _printed(root, wrap, PATCH_LIMIT, "diff-index", "-p", "-M", *_PLAIN, against, "--")
    listed = [path for path in _git(root, wrap, "ls-files", "-z", "--others", "--exclude-standard").split("\0") if path]
    for path in listed:
        if len(printed) > PATCH_LIMIT:
            break
        if not path.endswith("/"):
            asked = ("diff", "--no-index", *_PLAIN, "--", "/dev/null", path)
            printed += _printed(root, wrap, PATCH_LIMIT - len(printed), *asked, ok=(0, 1))
    return head, _kept(printed, sum(path.endswith("/") for path in listed))


def _git(root: Path, wrap: Sequence[str], *args: str, input: str | None = None) -> str:
    """What git printed, run as every git of a diff is."""
    return git(*args, cwd=root, input=input, env=_STORED, wrap=wrap)


def _printed(root: Path, wrap: Sequence[str], limit: int, *args: str, ok: Sequence[int] = (0,)) -> bytes:
    """What git printed, as the bytes it printed, up to `limit` and one more."""
    return git(*args, cwd=root, ok=ok, env=_STORED, wrap=wrap, limit=limit).encode(errors="surrogateescape")


def _kept(printed: bytes, untracked_repositories: int = 0) -> Diff:
    """A patch as its record keeps it, cut at a line's end, which splits no character and leaves every line whole."""
    if len(printed) <= PATCH_LIMIT:
        return Diff(printed, False, untracked_repositories)
    return Diff(printed[: printed.rfind(b"\n", 0, PATCH_LIMIT) + 1], True, untracked_repositories)
