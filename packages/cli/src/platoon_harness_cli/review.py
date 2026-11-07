"""What changed, which the terminal and the browser say alike: each workspace's commits and uncommitted paths, from the
`changes` view, each line in parts that each client draws by its tone."""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

Tone = Literal["", "strong", "faint", "good", "bad", "warn"]
"""How a part of a line is drawn: plainly, as a heading, quieter, or as what passed, failed or needs a look."""
Part = tuple[str, Tone]

NOBODY = "nobody's"
"""Where the commits go that no agent's workspace made: in your checkout, or in no workspace or in two."""
TESTS: dict[str, Tone] = {"passed": "good", "failed": "bad", "error": "warn"}


@dataclass(frozen=True)
class Change:
    """One line of what changed: a workspace's `heading`, a `commit`, an uncommitted `path`, how many `more` paths a
    workspace holds than its reading lists, or `nothing` measured yet. Its words, in parts each with its tone; the
    `key` of its row in the `changes` view, which a person chooses, or None; whether it is `new`, past the person's
    mark; and for a commit the acts the view offers on it, the one that tests it."""

    kind: Literal["heading", "commit", "path", "more", "nothing"]
    parts: tuple[Part, ...]
    key: str | None = None
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
        found.append(Change("heading", (title, *apart, *under_way)))
        for commit in (commit for commit in commits if _owner(commit) == group):
            parts: tuple[Part, ...] = (
                (commit["gist"], ""),
                (f"  {_lines(commit['added'], commit['removed'])}", "faint"),
                *_tests(commit),
                *(((" dropped", "bad"),) if commit["dropped"] else ()),
            )
            found.append(Change("commit", parts, commit["id"], new(commit), tuple(commit.get("actions") or ())))
        held = [path for path in paths if path["workspace"] == group]
        for path in held:
            parts = (
                (f"{path['state']:<13}", "warn" if path["state"] == "conflicted" else ""),
                (path["path"], ""),
                (f"  {_lines(path['added'], path['removed'])}", "faint"),
            )
            found.append(Change("path", parts, path["id"], new(path)))
        if reading and (more := (reading["total"] or 0) - len(held)) > 0:
            found.append(Change("more", ((f"{more} more", "faint"),)))
    if not found:
        return [Change("nothing", (("Nothing measured yet: a look runs at the end of each agent's turn.", "faint"),))]
    return found
