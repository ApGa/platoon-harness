"""What changed, as a list a person reads: each workspace's commits and uncommitted paths, from the `changes` view, and
on a commit the act that tests it."""

from collections.abc import Callable, Collection, Iterable, Mapping
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Static

from .keymap import bindings
from .rows import Row, Rows
from .safe import SafeText, note

PLANNED = "Diffs come with review, which is planned."
NOBODY = "nobody's"
"""Where the commits go that no agent's workspace made: in your checkout, or in no workspace or in two."""
TESTS = {"passed": "green", "failed": "red", "error": "yellow"}


def _lines(added: int | None, removed: int | None) -> str:
    """Lines added and removed, `?` for what nobody measured."""
    return f"+{'?' if added is None else added} -{'?' if removed is None else removed}"


def _owner(commit: Mapping[str, Any]) -> str:
    made_in = commit["made_in"] or ""
    return made_in if made_in.startswith("@") else NOBODY


def snapshots_of(roster: Iterable[Mapping[str, Any]]) -> set[str]:
    """The workspaces whose commits are in a repository of their own: each snapshot's, an isolated one's among them."""
    return {f"@{row['agent']}" for row in roster if (row["workspace"] or {}).get("mode") in ("snapshot", "isolated")}


def _tests(commit: Mapping[str, Any]) -> tuple[str, str] | str:
    """What a commit's latest runtime test came to, with why it failed or erred, or that none ran where one could."""
    outcome = commit["tests"]
    if outcome is None:
        return ("  untested", "dim") if commit.get("actions") else ""
    detail = commit.get("tests_why") or (
        f"exit {commit['tests_exit']}" if commit.get("tests_exit") is not None else None
    )
    said = f"  tests {outcome}: {detail}" if detail and outcome != "passed" else f"  tests {outcome}"
    return (said, TESTS[outcome])


def rows_of(changes: Mapping[str, Mapping[str, Any]], mark: int, snapshots: Collection[str] = ()) -> list[Row]:
    """The changes as rows, grouped by workspace: each agent's commits under it, newest recorded first, with what its
    latest runtime test came to, then its uncommitted paths, conflicted first, and how many more there are than the
    list holds; your checkout's paths; and last the commits that are nobody's. A group of one of `snapshots` says its
    commits are in its own repository. A row past `mark` is marked new."""
    commits = sorted((row for row in changes.values() if row["kind"] == "commit"), key=lambda row: -row["recorded"])
    readings = {row["workspace"]: row for row in changes.values() if row["kind"] == "workspace"}
    paths = sorted(
        (row for row in changes.values() if row["kind"] == "path"),
        key=lambda row: (row["state"] != "conflicted", row["path"]),
    )
    agents = sorted(({_owner(commit) for commit in commits} | set(readings)) - {NOBODY, "shared"})
    nobody = any(_owner(commit) == NOBODY for commit in commits)
    groups = [*agents, *(["shared"] if "shared" in readings else []), *([NOBODY] if nobody else [])]
    found: list[Row] = []
    for group in groups:
        reading = readings.get(group)
        under_way = f", a {reading['under_way']} under way" if reading and reading["under_way"] else ""
        title = "your checkout" if group == "shared" else group
        apart = (", a snapshot, whose commits are in its own repository", "dim") if group in snapshots else ""
        found.append(Row(Content.assemble(SafeText(title, "bold"), apart, (under_way, "yellow"))))
        for commit in (commit for commit in commits if _owner(commit) == group):
            dropped = (" dropped", "red") if commit["dropped"] else ""
            counts = (f"  {_lines(commit['added'], commit['removed'])}", "dim")
            line = Content.assemble(_new(commit, mark), SafeText(commit["gist"]), counts, _tests(commit), dropped)
            found.append(Row(line, commit["id"]))
        held = [path for path in paths if path["workspace"] == group]
        for path in held:
            style = "yellow" if path["state"] == "conflicted" else ""
            line = Content.assemble(
                _new(path, mark),
                (f"{path['state']:<13}", style),
                SafeText(path["path"]),
                (f"  {_lines(path['added'], path['removed'])}", "dim"),
            )
            found.append(Row(line, path["id"]))
        if reading and (more := (reading["total"] or 0) - len(held)) > 0:
            found.append(Row(Content.styled(f"  {more} more", "dim")))
    return found or [Row(Content.styled("Nothing measured yet: a look runs at the end of each agent's turn.", "dim"))]


def _new(row: Mapping[str, Any], mark: int) -> tuple[str, str]:
    return ("● " if row["seq"] > mark else "  ", "cyan")


class Review(ModalScreen[None]):
    """What changed, as `rows_of` lists it. Reading to its end moves the person's mark on `repo/<name>`, through
    `read`. Choosing a commit takes its act, through `act`, or says why it is disabled. Diffs are drawn disabled, saying
    why."""

    BINDINGS = bindings("dialog")

    def __init__(
        self,
        changes: Mapping[str, Mapping[str, Any]],
        mark: int,
        read: Callable[[int], object],
        act: Callable[[Mapping[str, Any]], object],
        snapshots: Collection[str] = (),
    ) -> None:
        super().__init__()
        self._changes = changes
        self._rows = rows_of(changes, mark, snapshots)
        self._mark = mark
        self._newest = max((row["seq"] for row in changes.values()), default=0)
        self._read = read
        self._act = act

    def compose(self) -> ComposeResult:
        acted = any(row.get("actions") for row in self._changes.values())
        with Vertical(classes="dialog wide"):
            yield Static(Content.styled("What changed", "bold"))
            yield Rows(id="changes")
            yield Static(Content.styled(PLANNED, "dim"), id="diffs")
            yield Static(Content.styled("Enter on a commit: test it    Esc: leave" if acted else "Esc: leave", "dim"))

    def on_mount(self) -> None:
        rows = self.query_one(Rows)
        rows.show(self._rows)
        self.watch(rows, "scroll_y", self._seen, init=False)
        self.call_after_refresh(self._seen)

    def _seen(self) -> None:
        """Move the mark through the newest row once the list's end is in view."""
        rows = self.query_one(Rows)
        if self._newest > self._mark and rows.scroll_offset.y + rows.size.height >= len(rows.rows):
            self._mark = self._newest
            self._read(self._newest)

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        actions = self._changes.get(chosen.key, {}).get("actions") or ()
        for action in actions:
            if action["disabled"]:
                note(self, f"{action['label']}: {action['disabled']}", severity="warning")
            else:
                self._act(action)

    def action_leave(self) -> None:
        self.dismiss(None)
