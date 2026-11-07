"""A diff: what git shows of a recorded commit's patch, or of a workspace's uncommitted work, for `repo.keep`, read
without changing any ref, index or file, and with no external diff, textconv or hook. See architecture section 13."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from platoon_harness.primitives.repo import PATCH_LIMIT

from .git import git

_PLAIN = ("--no-ext-diff", "--no-textconv", "--no-color", "--src-prefix=a/", "--dst-prefix=b/")
"""What every diff passes, so that no program a repository's config names runs to show it, and its colours and prefixes
are git's own."""

__all__ = ["Diff", "patch", "uncommitted"]


@dataclass(frozen=True)
class Diff:
    """A diff as its record keeps it: its patch as `text`, to the end of the last line within `PATCH_LIMIT` bytes where
    it was longer, which `cut` says."""

    text: bytes
    cut: bool


def patch(root: Path, sha: str, *, wrap: Sequence[str] = ()) -> Diff:
    """A commit's patch against its first parent, as git run under `wrap` shows it in the repository whose work tree is
    at `root`. No porcelain reads it, so no signature is verified."""
    asked = ("diff-tree", "-p", "--root", "--diff-merges=first-parent", "--no-commit-id", "-M", *_PLAIN, sha)
    return _kept(_printed(root, wrap, PATCH_LIMIT, *asked))


def uncommitted(root: Path, *, wrap: Sequence[str] = ()) -> tuple[str | None, Diff]:
    """The HEAD the work tree at `root` holds, None before its first commit, and what it holds uncommitted against that,
    as git run under `wrap` shows it: its tracked files, staged or not, then each untracked file git does not ignore, as
    a new one, until the patch passes its bound. An untracked repository in the tree is passed over, as git shows no
    file of it."""
    head = git("rev-parse", "-q", "--verify", "HEAD^{commit}", cwd=root, ok=(0, 1), wrap=wrap).strip() or None
    against = head or git("hash-object", "-t", "tree", "--stdin", cwd=root, input="", wrap=wrap).strip()
    printed = _printed(root, wrap, PATCH_LIMIT, "diff-index", "-p", "-M", *_PLAIN, against, "--")
    for path in git("ls-files", "-z", "--others", "--exclude-standard", cwd=root, wrap=wrap).split("\0"):
        if len(printed) > PATCH_LIMIT:
            break
        if path and not path.endswith("/"):
            asked = ("diff", "--no-index", *_PLAIN, "--", "/dev/null", path)
            printed += _printed(root, wrap, PATCH_LIMIT - len(printed), *asked, ok=(0, 1))
    return head, _kept(printed)


def _printed(root: Path, wrap: Sequence[str], limit: int, *args: str, ok: Sequence[int] = (0,)) -> bytes:
    """What git printed, as the bytes it printed, up to `limit` and one more."""
    return git(*args, cwd=root, ok=ok, wrap=wrap, limit=limit).encode(errors="surrogateescape")


def _kept(printed: bytes) -> Diff:
    """A patch as its record keeps it, cut at a line's end, which splits no character and leaves every line whole."""
    if len(printed) <= PATCH_LIMIT:
        return Diff(printed, cut=False)
    return Diff(printed[: printed.rfind(b"\n", 0, PATCH_LIMIT) + 1], cut=True)
