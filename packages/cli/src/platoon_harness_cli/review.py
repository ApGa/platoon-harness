"""What changed, which the terminal and the browser say alike: each workspace's commits and uncommitted paths, from the
`changes` view, and a commit's patch or a workspace's uncommitted diff, read a page at a time, each line in parts or a
tone that each client draws its own way."""

import re
import time
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from platoon_harness import Refused, Session
from platoon_harness.kernel import Event
from platoon_harness.primitives.repo import PATCH_LIMIT

from .ops import cut

Tone = Literal["", "strong", "faint", "good", "bad", "warn"]
"""How a part of a line is drawn: plainly, as a heading, quieter, or as what passed, failed or needs a look."""
Part = tuple[str, Tone]

NOBODY = "nobody's"
"""Where the commits go that no agent's workspace made: in your checkout, or in no workspace or in two."""
TESTS: dict[str, Tone] = {"passed": "good", "failed": "bad", "error": "warn"}
SIGNS: dict[str, Tone] = {"+": "good", "-": "bad"}
"""How a line of a hunk is drawn by its first character: added, removed, or neither."""


@dataclass(frozen=True)
class Change:
    """One line of what changed: a workspace's `heading`, a `commit`, an uncommitted `path`, how many `more` paths a
    workspace holds than its reading lists, or `nothing` measured yet. Its words, in parts each with its tone; the
    `key` of its row in the `changes` view, which a person chooses, or None; what `repo.diff` reads for it, `of`: a
    commit's SHA for its patch, or a workspace for what it holds uncommitted; whether it is `new`, past the person's
    mark; and for a commit the acts the view offers on it, the one that tests it."""

    kind: Literal["heading", "commit", "path", "more", "nothing"]
    parts: tuple[Part, ...]
    key: str | None = None
    of: str | None = None
    new: bool = False
    actions: tuple[Mapping[str, Any], ...] = ()


def _lines(added: int | None, removed: int | None) -> str:
    """Lines added and removed, `?` for what nobody measured."""
    return f"+{'?' if added is None else added} -{'?' if removed is None else removed}"


def _owner(commit: Mapping[str, Any]) -> str:
    made_in = commit["made_in"] or ""
    return made_in if made_in.startswith("@") else NOBODY


def snapshots_of(roster: Iterable[Mapping[str, Any]]) -> set[str]:
    """The workspaces whose commits are in a repository of their own: each snapshot's, an isolated one's among them."""
    return {f"@{row['agent']}" for row in roster if (row["workspace"] or {}).get("mode") in ("snapshot", "isolated")}


def _tests(commit: Mapping[str, Any]) -> tuple[Part, ...]:
    """What a commit's latest runtime test came to, with why it failed or erred, or that none ran where one could."""
    outcome = commit["tests"]
    if outcome is None:
        return (("  untested", "faint"),) if commit.get("actions") else ()
    detail = commit.get("tests_why") or (
        f"exit {commit['tests_exit']}" if commit.get("tests_exit") is not None else None
    )
    said = f"  tests {outcome}: {detail}" if detail and outcome != "passed" else f"  tests {outcome}"
    return ((said, TESTS[outcome]),)


def changes_of(
    changes: Mapping[str, Mapping[str, Any]], mark: int | None, snapshots: Collection[str] = ()
) -> list[Change]:
    """The changes as lines, grouped by workspace: each agent's commits under it, newest recorded first, with what its
    latest runtime test came to, then its uncommitted paths, conflicted first, and how many more there are than the
    list holds; your checkout's paths; and last the commits that are nobody's. A group of one of `snapshots` says its
    commits are in its own repository. A line past `mark` is new, and with no mark none is."""
    commits = sorted((row for row in changes.values() if row["kind"] == "commit"), key=lambda row: -row["recorded"])
    readings = {row["workspace"]: row for row in changes.values() if row["kind"] == "workspace"}
    paths = sorted(
        (row for row in changes.values() if row["kind"] == "path"),
        key=lambda row: (row["state"] != "conflicted", row["path"]),
    )
    agents = sorted(({_owner(commit) for commit in commits} | set(readings)) - {NOBODY, "shared"})
    nobody = any(_owner(commit) == NOBODY for commit in commits)
    groups = [*agents, *(["shared"] if "shared" in readings else []), *([NOBODY] if nobody else [])]

    def new(row: Mapping[str, Any]) -> bool:
        return mark is not None and row["seq"] > mark

    found: list[Change] = []
    for group in groups:
        reading = readings.get(group)
        title: Part = ("your checkout" if group == "shared" else group, "strong")
        apart: tuple[Part, ...] = (
            ((", a snapshot, whose commits are in its own repository", "faint"),) if group in snapshots else ()
        )
        under_way = ((f", a {reading['under_way']} under way", "warn"),) if reading and reading["under_way"] else ()
        heading = (title, *apart, *under_way)
        found.append(Change("heading", heading, reading["id"], group) if reading else Change("heading", heading))
        for commit in (commit for commit in commits if _owner(commit) == group):
            parts: tuple[Part, ...] = (
                (commit["gist"], ""),
                (f"  {_lines(commit['added'], commit['removed'])}", "faint"),
                *_tests(commit),
                *(((" dropped", "bad"),) if commit["dropped"] else ()),
            )
            acts = tuple(commit.get("actions") or ())
            found.append(Change("commit", parts, commit["id"], commit["commit"], new(commit), acts))
        held = [path for path in paths if path["workspace"] == group]
        for path in held:
            parts = (
                (f"{path['state']:<13}", "warn" if path["state"] == "conflicted" else ""),
                (path["path"], ""),
                (f"  {_lines(path['added'], path['removed'])}", "faint"),
            )
            found.append(Change("path", parts, path["id"], group, new(path)))
        if reading and (more := (reading["total"] or 0) - len(held)) > 0:
            found.append(Change("more", ((f"{more} more", "faint"),)))
    if not found:
        return [Change("nothing", (("Nothing measured yet: a look runs at the end of each agent's turn.", "faint"),))]
    return found


@dataclass(frozen=True)
class Line:
    """One line of a patch: its `number`, which a citation of its lines names, its `text`, and its `tone`: a file's
    first line strong, what heads a file or a hunk faint, an added line good and a removed one bad, and a file git
    takes for binary, which it names and never shows, warn."""

    number: int
    text: str
    tone: Tone


@dataclass(frozen=True)
class Page:
    """Lines of a patch as `blob.get` reads them, a page at a time: these, how many lines the patch has in all, and the
    ref of the lines after these, or None at its end."""

    lines: tuple[Line, ...]
    total: int
    rest: str | None


@dataclass(frozen=True)
class Diff:
    """A diff as a person reads it: the `ref` of its record, which `blob.get` reads and a citation names lines of; the
    words `above` its patch, what it is of and how long, then where it was read and, for what a workspace holds
    uncommitted, when; its `first` page, or None where it has no text to draw; and the words `below` its last line,
    where it was cut or why it is not drawn. `of` says what it is of. A comment on it goes `to` the change's maker, the
    agent whose workspace made the commit or holds what is uncommitted, or where none did, `unsendable` says why it has
    nobody to go to; and a comment on no lines cites `whole`, the commit, or an uncommitted diff's record, which
    `about` says."""

    ref: str
    above: tuple[str, ...]
    first: Page | None
    below: str | None
    of: str
    to: str | None
    unsendable: str | None
    whole: str
    about: str


async def kept(session: Session, effect: int) -> Event:
    """The record of what the diff `effect` read, once the journal holds it: its `repo.diffed`, past its request.
    Refused `unavailable` when the effect failed, saying why, or when nothing more can come."""
    async for event in session.events(effect, match="repo/*", streams=[f"effect/{effect}"], follow=True):
        if event.type == "repo.diffed" and event.data["effect"] == effect:
            return event
        if event.type == "effect.failed" and event.stream == f"effect/{effect}":
            raise Refused("unavailable", f"the diff was not read: {event.data['error']}")
    raise Refused("unavailable", "the session's runtime went before the diff was read")


async def read(session: Session, effect: int) -> Diff:
    """The diff the effect `effect` read, as `repo.diff` gave it, once it is recorded, with its first page."""
    record = await kept(session, effect)
    data, ref = record.data, f"{record.stream}@{record.version}"
    above = [record.gist]
    if data["body"] is not None:
        read_in = data["read_in"]
        mode = None if read_in == "shared" else ((await session.status(read_in))["workspace"] or {}).get("mode")
        where = place(read_in, mode, commit=data["sha"] is not None)
        when = data["read_at"]
        above.append(f"Read in {where}." if when is None else f"What it held at {_clock(when)}, read in {where}.")
    if data["sha"] is not None:
        commit = await session.repo_commit(data["sha"])
        maker, whole = commit["made_in"] or "", commit["ref"]
        of, about, nobody = f"{data['sha'][:12]}'s patch", f"the commit {data['sha'][:12]}", "this commit"
    else:
        maker, whole = data["workspace"], ref
        of = about = f"{'your checkout' if maker == 'shared' else maker}'s uncommitted diff"
        nobody = "your checkout"
    to = maker if maker.startswith("@") else None
    unsendable = None if to else f"A comment goes to whoever made the change, and no agent's workspace made {nobody}."
    first = None if data["body"] is None else await page(session, ref)
    below = None
    if data["body"] is not None and first is None:
        below = "It is not UTF-8, so it is not drawn, and no line of it can be cited."
    elif data["cut"]:
        rest = f"in git, at {data['sha'][:12]}" if data["sha"] else f"uncommitted in {_whose(data['workspace'])}"
        below = f"Cut here, at the end of the last line within {PATCH_LIMIT // 1024} KiB: the rest is {rest}."
    return Diff(ref, tuple(above), first, below, of, to, unsendable, whole, about)


def on(diff: Diff, lines: tuple[int, int] | None) -> str:
    """What a comment on `lines` of a diff, its first and last, is on, in words, or with none chosen, on the diff's
    `whole`."""
    if lines is None:
        return diff.about
    first, last = lines
    return f"line {first} of {diff.of}" if first == last else f"lines {first} to {last} of {diff.of}"


def cites(diff: Diff, lines: tuple[int, int] | None) -> str:
    """What a comment on `lines` of a diff cites: those lines, by its record's ref, or with none chosen its `whole`."""
    return diff.whole if lines is None else f"{diff.ref}#L{lines[0]}-{lines[1]}"


async def comment(session: Session, diff: Diff, lines: tuple[int, int] | None, text: str) -> str:
    """Send a comment on `lines` of a diff, a person's message to the change's maker whose `based_on` cites what it is
    on, its text made its gist and body as the composer's is, and give what it cites. Refused `not_found` where no
    agent made the change."""
    if diff.to is None:
        raise Refused("not_found", diff.unsendable or "no agent made this change")
    gist, body = cut(text)
    cited = cites(diff, lines)
    await session.send(diff.to, gist, body=body, based_on=[cited])
    return cited


async def page(session: Session, ref: str) -> Page | None:
    """The lines of a patch that `blob.get` gives by `ref`, its record's or a page's `rest`, or None for a patch that
    is no text."""
    got = await session.blob(ref)
    if got["text"] is None:
        return None
    first = int(found[1]) if (found := re.search(r"#L(\d+)-", got["ref"])) else 1
    return Page(lines_of(first, got["text"]), got["lines"], got["rest"])


def lines_of(first: int, text: str) -> tuple[Line, ...]:
    """The lines of a page of a patch from line `first`, each with its tone. A page that begins past the patch's first
    line is taken to begin in a hunk, until a file's first line says otherwise."""
    found = []
    hunk = first > 1
    for number, said in enumerate(text.splitlines(), first):
        if said.startswith("diff --git "):
            hunk, tone = False, "strong"
        elif said.startswith("@@"):
            hunk, tone = True, "faint"
        elif not hunk:
            tone = "warn" if said.startswith("Binary files ") else "faint"
        else:
            tone = SIGNS.get(said[:1], "")
        found.append(Line(number, said, tone))
    return tuple(found)


def place(read_in: str, mode: str | None, *, commit: bool) -> str:
    """Where a diff was read, in words: your checkout, or for a commit your repository, or an agent's workspace,
    `read_in`, by its `mode`."""
    if read_in == "shared":
        return "your repository" if commit else "your checkout"
    return {
        "worktree": f"{read_in}'s worktree",
        "snapshot": f"{read_in}'s own repository, a snapshot",
        "isolated": f"{read_in}'s own repository, inside its isolation",
    }.get(mode, f"{read_in}'s workspace")


def _whose(workspace: str) -> str:
    return "your checkout" if workspace == "shared" else f"{workspace}'s workspace"


def _clock(at: float) -> str:
    """A time on the session's clock as the transcript says one."""
    return time.strftime("%H:%M:%S", time.localtime(at))
