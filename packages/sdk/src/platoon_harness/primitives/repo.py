"""What the runtime's looks find in the session's repository, on `repo/<name>`: each commit, each rewrite of what the
journal holds, and each workspace's head and uncommitted state. A look is the runtime's observation, not an act of an
agent's, so none of its events names an agent in its envelope, and none claims a turn or a context."""

import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from platoon_harness.kernel import GIST_LIMIT, NAME, Args, Event, Refused, Txn, View, fold, op

from .common import BodyRef, Name, cited
from .reports import record_gap
from .sessions import SessionRecord

Sha = Annotated[str, Field(pattern=r"^([0-9a-f]{40}|[0-9a-f]{64})$")]
Where = Annotated[str, Field(pattern=rf"^(shared|@{NAME})$")]
"""A workspace in the address grammar: `@ada` for an agent's own, and `shared` for the session's checkout."""
UnderWay = Literal["merge", "rebase", "cherry-pick", "revert", "bisect", "sequence"]
PathState = Literal["modified", "added", "deleted", "renamed", "copied", "type_changed", "untracked", "conflicted"]

DROPPED_LIMIT = 64
TEXT_LIMIT = 256
"""How many characters a look keeps of a commit's author and of each `Informed-By` value, which an agent wrote."""
CITED_LIMIT = 16
"""How many `Informed-By` values of one commit a look keeps."""
_WHY_LIMIT = 512
_NAMED = 3


class Cited(Args):
    """One `Informed-By` value of a commit as it was `written`, cut to fit, and the commit it names, or None when it
    names no one commit: only 4 to 40 hex digits naming one commit in the commit's own repository do. A value that is an
    event's ref names no commit, and its commit cites that event as any write of content cites one."""

    written: Annotated[str, Field(max_length=TEXT_LIMIT)]
    sha: Sha | None


class Commit(Args):
    """A commit a look found: its `parents`, the `branch` its workspace's HEAD was on, or None for one found only as
    cited, the workspace whose HEAD reflog records making it as `made_in`, or None when none or two do, its `author`,
    its lines `added` and `removed` against its first parent, None when a file's were not measured, as a binary file's
    are not, how many `files` it touched, and what it says it was `informed_by`, the first of its `informed_by_total`
    values. What an agent wrote is cut to fit, so one long value cannot keep a commit from being recorded."""

    sha: Sha
    parents: tuple[Sha, ...]
    subject: str
    author: Annotated[str, Field(max_length=TEXT_LIMIT)]
    branch: str | None
    made_in: Where | None
    added: int | None
    removed: int | None
    files: int
    informed_by: Annotated[tuple[Cited, ...], Field(max_length=CITED_LIMIT)] = ()
    informed_by_total: int = 0


class Uncommitted(Args):
    """A path a workspace holds uncommitted, in `state`, with its lines against HEAD, None when nobody measured them,
    as for an untracked or a binary file."""

    path: str
    state: PathState
    added: int | None
    removed: int | None


class Reading(Args):
    """What a look read of a workspace, which is its last look from then on: the `path` of its work tree, its `head`
    and `branch`, any operation `under_way` and the branch a rebase is `rebasing`, and its uncommitted `paths`,
    conflicted first and cut to fit, with the true `total`, how many are `conflicted`, and the whole list as a `body`
    when it was cut. Its state is None for the shared workspace when no role works in it, since your own edits there
    are not the session's."""

    path: str
    head: Sha | None
    branch: str | None
    under_way: UnderWay | None = None
    rebasing: str | None = None
    paths: tuple[Uncommitted, ...] | None = None
    total: int | None = None
    conflicted: int | None = None
    body: BodyRef | None = None


class Rewrite(Args):
    """A branch that `was` at the last look's tip and is `now` at another, or gone, with what that tip reached and it
    no longer does as `dropped`."""

    branch: str | None
    was: Sha
    now: Sha | None
    dropped: tuple[Sha, ...]


class Report(Args):
    """One page of a look at `workspace`, which `agent`'s probe or stop asked for and the event `cause` prompted. Its
    `commits` come parents first, and the page with a `reading` is its last, which moves the workspace's last look.
    `unobserved` says why the look could not read the workspace, which records the gap and nothing else. A reading and
    a gap follow from what prompted the look, so they name it as their cause; a commit or a rewrite the look found was
    someone's act in git, which that did not cause, so it names none."""

    agent: Name
    workspace: Where
    cause: int | None = None
    commits: tuple[Commit, ...] = ()
    rewrite: Rewrite | None = None
    reading: Reading | None = None
    unobserved: str | None = None


class Looks(View):
    """Each workspace's last look, which the next one starts from, and the ref of each commit the journal holds."""

    schema = """
    CREATE TABLE v_looks(workspace TEXT PRIMARY KEY, reading TEXT NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_looks_commits(sha TEXT PRIMARY KEY, ref TEXT NOT NULL) WITHOUT ROWID, STRICT;
    """

    @fold("repo.committed")
    def committed(self, event: Event) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO v_looks_commits VALUES (?, ?)",
            (event.data["sha"], f"{event.stream}@{event.version}"),
        )

    @fold("workspace.changed")
    def changed(self, event: Event) -> None:
        reading = {key: value for key, value in event.data.items() if key != "workspace"}
        self.db.execute(
            "INSERT OR REPLACE INTO v_looks VALUES (?, ?)",
            (event.data["workspace"], json.dumps(reading, sort_keys=True)),
        )

    def ref(self, sha: str) -> str | None:
        """The ref of the event that recorded a commit, or None while the journal holds none."""
        row = self.db.execute("SELECT ref FROM v_looks_commits WHERE sha = ?", (sha,)).fetchone()
        return None if row is None else row["ref"]

    def reading(self, workspace: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT reading FROM v_looks WHERE workspace = ?", (workspace,)).fetchone()
        return None if row is None else json.loads(row["reading"])

    def readings(self) -> dict[str, dict[str, Any]]:
        return {row["workspace"]: json.loads(row["reading"]) for row in self.db.execute("SELECT * FROM v_looks")}


def _some(count: int, what: str) -> str:
    return f"{count} {what}{'' if count == 1 else 's'}"


def unsettled(reading: Mapping[str, Any]) -> str:
    """A conflict a reading found, in a line: what stopped on it, in which files, and where to resolve it."""
    named = [path["path"] for path in reading["paths"] or () if path["state"] == "conflicted"][:_NAMED]
    more = f" and {reading['conflicted'] - len(named)} more" if reading["conflicted"] > len(named) else ""
    files = f"{_some(reading['conflicted'], 'file')}, {', '.join(named)}{more}"
    return f"{reading['under_way'] or 'work'} stopped on conflicts in {files}: resolve it in {reading['path']}"


def _said(where: str, reading: Reading) -> str:
    """A reading in a line: its conflicts, else how much it holds uncommitted, else where it stands."""
    if reading.conflicted:
        return f"{where}: {unsettled(reading.model_dump(mode='json'))}"
    if reading.total:
        under_way = f", a {reading.under_way} under way" if reading.under_way else ""
        return f"{where}: {_some(reading.total, 'path')} uncommitted{under_way}"
    at = "no commit" if reading.head is None else reading.head[:12]
    return f"{where} at {at}" + (f" on {reading.branch}" if reading.branch else "")


def _citation(txn: Txn, looks: Looks, value: Cited) -> str | None:
    """The ref an `Informed-By` value cites: a recorded commit's, by the commit git resolved it to, or an event's, by
    its ref, checked as `based_on` is. Anything else cites nothing, and is never refused, since git already holds it."""
    if value.sha is not None:
        return looks.ref(value.sha)
    try:
        return cited(txn, [value.written])[0]
    except Refused:
        return None


@op("repo.report", runtime=True)
def report(txn: Txn, a: Report) -> None:
    """Record one page of a look, on `repo/<name>` with no agent in the envelope. A commit the journal holds is passed
    over, so a look repeated after a crash records nothing twice, a rewrite names only what the journal holds, and a
    reading is recorded only when it differs from the workspace's last. A commit's `based_on` is what its `Informed-By`
    values cite, and the rest stay in `informed_by` alone."""
    repo = txn.view(SessionRecord).settings().repo
    if repo is None:
        raise Refused("unsupported", "this session observes no repository")
    stream, looks, cause = f"repo/{repo.name}", txn.view(Looks), () if a.cause is None else (a.cause,)
    if a.unobserved is not None:
        gist = f"gap: workspace_unobserved, {a.workspace}"
        record_gap(txn, a.agent, "workspace_unobserved", gist=gist, cause=cause, why=a.unobserved[:_WHY_LIMIT])
        return
    for commit in a.commits:
        if looks.ref(commit.sha) is None:
            citing = [ref for found in commit.informed_by if (ref := _citation(txn, looks, found))]
            gist = f"{commit.sha[:12]} {commit.subject}"[:GIST_LIMIT]
            data = commit.model_dump(mode="json", exclude={"subject"})
            txn.emit("repo.committed", stream, gist=gist, based_on=list(dict.fromkeys(citing)), data=data)
    if a.rewrite is not None and (dropped := [sha for sha in a.rewrite.dropped if looks.ref(sha)]):
        rewrite = a.rewrite.model_dump(mode="json", exclude={"dropped"})
        data = {"workspace": a.workspace, **rewrite, "dropped": dropped[:DROPPED_LIMIT], "dropped_total": len(dropped)}
        gist = f"{a.workspace}: {a.rewrite.branch or 'HEAD'} no longer reaches {_some(len(dropped), 'recorded commit')}"
        txn.emit("repo.rewritten", stream, gist=gist[:GIST_LIMIT], data=data)
    if a.reading is not None and looks.reading(a.workspace) != (reading := a.reading.model_dump(mode="json")):
        refs = [a.reading.body] if a.reading.body else ()
        gist = _said(a.workspace, a.reading)[:GIST_LIMIT]
        txn.emit(
            "workspace.changed", stream, gist=gist, cause=cause, refs=refs, data={"workspace": a.workspace, **reading}
        )


@op("repo.looks", query=True, runtime=True)
def looks(txn: Txn, a: Args) -> dict[str, dict[str, Any]]:
    """The head and branch each workspace's last look read, by workspace, which the next look starts from."""
    return {
        where: {"head": read["head"], "branch": read["branch"]} for where, read in txn.view(Looks).readings().items()
    }
