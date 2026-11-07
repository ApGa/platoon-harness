"""What the runtime finds in the session's repository, on `repo/<name>`: each commit, each rewrite of what the journal
holds, and each workspace's head and uncommitted state, as its looks find them, what each runtime test of a commit came
to, and each diff a person or a program asked for. The runtime's finding is not an act of an agent's, so none of these
events names an agent in its envelope, and none claims a turn or a context."""

import json
import sqlite3
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from platoon_harness.kernel import GIST_LIMIT, NAME, Args, Effects, Event, Refused, Stamps, Txn, View, fold, op

from .agents import Agents
from .common import BodyRef, Exposed, Name, cited, event_at, expose_read, inline_body, parts_of
from .exposures import readable
from .reports import record_gap
from .sessions import SessionRecord

Sha = Annotated[str, Field(pattern=r"^([0-9a-f]{40}|[0-9a-f]{64})$")]
Given = Annotated[
    str, Field(pattern=r"^[0-9a-f]{4,64}$", description="A commit's SHA, or its first 4 or more hex digits.")
]
"""A recorded commit as a person or an agent names it: its SHA, or the first 4 or more of its hex digits, naming one."""
Where = Annotated[str, Field(pattern=rf"^(shared|@{NAME})$")]
"""A workspace in the address grammar: `@ada` for an agent's own, and `shared` for the session's checkout."""
UnderWay = Literal["merge", "rebase", "cherry-pick", "revert", "bisect", "sequence"]
Uncited = Literal["unrecorded", "no_event", "no_lines", "unread"]
"""Why an `Informed-By` value cites nothing: it names a commit the journal holds no record of, no event, no lines of
its event's body, or an event its commit's maker had neither made nor been handed."""
PathState = Literal["modified", "added", "deleted", "renamed", "copied", "type_changed", "untracked", "conflicted"]
TestOutcome = Literal["passed", "failed", "error"]
"""What a runtime test came to: its command exited 0, exited otherwise or was ended by a signal of its own, or it could
not run to its end, as when its timeout came first."""

NOT_RECORDED = "not recorded yet: a commit is recorded at the look after the turn that made it"

DROPPED_LIMIT = 64
TEXT_LIMIT = 256
"""How many characters a look keeps of a commit's author and of each `Informed-By` value, which an agent wrote."""
CITED_LIMIT = 16
"""How many `Informed-By` values of one commit a look keeps."""
PATCH_LIMIT = 64 * 1024
"""How many bytes of a patch its record keeps: as much as the journal holds in an event's own body, so that `blob.get`
reads it and a citation's lines are checked."""
_WHY_LIMIT = 512
_NAMED = 3


class Cited(Args):
    """One `Informed-By` value of a commit as it was `written`, cut to fit, and the commit it names, or None when it
    names no one commit: only 4 to 40 hex digits naming one commit in the commit's own repository do. A value that is an
    event's ref names no commit."""

    written: Annotated[str, Field(max_length=TEXT_LIMIT)]
    sha: Sha | None


class Commit(Args):
    """A commit a look found: its `parents`, the `branch` its workspace's HEAD was on, or None for one found only as
    cited, the workspace whose HEAD reflog records making it as `made_in`, or None when none or two do, its `author`,
    its lines `added` and `removed` against its first parent, None when a file's were not measured, as a binary file's
    are not, how many `files` it touched, and what it says it was `informed_by`, the first of its `informed_by_total`
    values, which its record keeps each with `why` it cites nothing, or None where it cites. What an agent wrote is cut
    to fit, so one long value cannot keep a commit from being recorded."""

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
    """Each workspace's last look, which the next one starts from, every isolated workspace, the ref of each commit the
    journal holds, with the workspace it was `found_in` and the isolated workspace that confines its code: that one
    where it was found, or an isolated commit the journal holds that it is built on, and each commit's diff: the
    `effect` asked to read it, then the `ref` of its patch once kept."""

    version = 4
    schema = """
    CREATE TABLE v_looks(workspace TEXT PRIMARY KEY, reading TEXT NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_looks_commits(
        sha TEXT PRIMARY KEY, ref TEXT NOT NULL, isolated TEXT, found_in TEXT
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_looks_isolated(workspace TEXT PRIMARY KEY) WITHOUT ROWID, STRICT;
    CREATE TABLE v_looks_diffs(sha TEXT PRIMARY KEY, effect INTEGER NOT NULL, ref TEXT) WITHOUT ROWID, STRICT;
    """

    @fold("effect.requested")
    def asked(self, event: Event) -> None:
        effect, data = event.data["id"], event.data["data"]
        if event.data["kind"] == "diff" and "sha" in data:
            self.db.execute("INSERT OR REPLACE INTO v_looks_diffs VALUES (?, ?, NULL)", (data["sha"], effect))

    @fold("repo.diffed")
    def diffed(self, event: Event) -> None:
        """A record that says why it could not be read holds no patch, so the next ask reads again."""
        if event.data["sha"] is not None and event.data["body"] is not None:
            self.db.execute(
                "UPDATE v_looks_diffs SET ref = ? WHERE sha = ? AND effect = ?",
                (f"{event.stream}@{event.version}", event.data["sha"], event.data["effect"]),
            )

    @fold("effect.finished")
    def made(self, event: Event) -> None:
        result = event.data["result"]
        if event.data["kind"] == "workspace" and isinstance(result, dict) and result.get("mode") == "isolated":
            self.db.execute("INSERT OR IGNORE INTO v_looks_isolated VALUES (?)", (f"@{event.agent}",))

    @fold("repo.committed")
    def committed(self, event: Event) -> None:
        """A commit's code runs only in an isolation when the look that found it was of an isolated workspace, which is
        where its code is, or when a parent the journal holds is confined. Attribution does not decide this, since an
        isolated agent writes its own reflog. A commit's parents the journal holds are recorded before it."""
        sha, parents, found_in = event.data["sha"], event.data["parents"], event.data.get("found_in")
        row = self.db.execute("SELECT workspace FROM v_looks_isolated WHERE workspace = ?", (found_in,)).fetchone()
        isolated = found_in if row is not None else None
        if isolated is None and parents:
            marks = ", ".join("?" * len(parents))
            parent = self.db.execute(
                f"SELECT isolated FROM v_looks_commits WHERE sha IN ({marks}) AND isolated IS NOT NULL LIMIT 1",
                parents,
            ).fetchone()
            isolated = None if parent is None else parent["isolated"]
        self.db.execute(
            "INSERT OR IGNORE INTO v_looks_commits VALUES (?, ?, ?, ?)",
            (sha, f"{event.stream}@{event.version}", isolated, found_in),
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

    def named(self, given: str) -> list[sqlite3.Row]:
        """The recorded commits whose SHA begins with `given`, two at most, as one is all a name may name."""
        return self.db.execute(
            "SELECT * FROM v_looks_commits WHERE substr(sha, 1, ?) = ? ORDER BY sha LIMIT 2", (len(given), given)
        ).fetchall()

    def isolated(self, sha: str) -> sqlite3.Row | None:
        """A recorded commit's `isolated` workspace, the one that confines its code, and the workspace it was
        `found_in`, or None for a commit the journal does not hold. `isolated` is None for one whose code may leave
        every isolation, equals `found_in` for one found in an isolated workspace, and names an ancestor's for one
        built on an isolated commit."""
        return self.db.execute("SELECT isolated, found_in FROM v_looks_commits WHERE sha = ?", (sha,)).fetchone()

    def diff(self, sha: str) -> sqlite3.Row | None:
        """A commit's diff: the `effect` last asked to read it and the `ref` of its patch once kept, or None while
        nobody asked."""
        return self.db.execute("SELECT effect, ref FROM v_looks_diffs WHERE sha = ?", (sha,)).fetchone()

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


def _citation(txn: Txn, looks: Looks, value: Cited, made_in: str | None) -> tuple[str | None, Uncited | None]:
    """The ref an `Informed-By` value cites, or why it cites none. One git resolved cites that commit's record. An
    event's ref cites the event once it is checked as `based_on` is and the commit's maker could read it, having made it
    or been handed it, as `blob.get` reads: a trailer is text git carries between clones and sessions, so a ref names
    this session's event only in a commit an agent of this session made. None is refused, since git already holds it."""
    if value.sha is not None:
        ref = looks.ref(value.sha)
        return (None, "unrecorded") if ref is None else (ref, None)
    parts = parts_of(value.written)
    event = None if parts is None else txn.view(Stamps).at(parts[0], parts[1])
    if event is None:
        return None, "no_event"
    try:
        cited(txn, [value.written])
    except Refused:
        return None, "no_lines"
    agent = made_in[1:] if made_in is not None and made_in.startswith("@") else None
    if agent is None or not readable(txn, agent, event):
        return None, "unread"
    return value.written, None


@op("repo.report", runtime=True)
def report(txn: Txn, a: Report) -> None:
    """Record one page of a look, on `repo/<name>` with no agent in the envelope. A commit the journal holds is passed
    over, so a look repeated after a crash records nothing twice, a rewrite names only what the journal holds, and a
    reading is recorded only when it differs from the workspace's last. A commit's `based_on` is what its `Informed-By`
    values cite, and the rest stay in `informed_by` alone, each saying why."""
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
            cites = [_citation(txn, looks, value, commit.made_in) for value in commit.informed_by]
            data = commit.model_dump(mode="json", exclude={"subject"})
            data["found_in"] = a.workspace
            for value, (_, why) in zip(data["informed_by"], cites, strict=True):
                value["why"] = why
            based_on = list(dict.fromkeys(ref for ref, _ in cites if ref is not None))
            gist = f"{commit.sha[:12]} {commit.subject}"[:GIST_LIMIT]
            txn.emit("repo.committed", stream, gist=gist, based_on=based_on, data=data, v=2)
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


def confined(looks: Looks, sha: str) -> str | None:
    """Why a recorded commit's code runs only in an isolation, in words, or None when nothing keeps it there: it was
    found in an isolated workspace, or it is built on a commit the journal holds that was."""
    row = looks.isolated(sha)
    if row is None or row["isolated"] is None:
        return None
    isolated, found_in = row["isolated"], row["found_in"]
    if isolated == found_in:
        return f"{isolated}'s commit was made in an isolated workspace, so its code runs only there"
    return f"it is built on a commit {isolated} made in an isolated workspace, so its code runs only there"


def _recorded(txn: Txn, given: str) -> Event:
    """The `repo.committed` of the one recorded commit `given` names. Refused `unsupported` when the session observes
    no repository, `not_found` while the journal holds no such commit, and `invalid` when `given` names several."""
    if txn.view(SessionRecord).settings().repo is None:
        raise Refused("unsupported", "this session observes no repository")
    named = txn.view(Looks).named(given)
    if not named:
        raise Refused("not_found", NOT_RECORDED)
    if len(named) > 1:
        raise Refused("invalid", f"{given} names more than one recorded commit: give more of its hex digits")
    event = event_at(txn, named[0]["ref"])
    assert event is not None
    return event


class Which(Args):
    sha: Given


def commit_fields(event: Event) -> dict[str, Any]:
    """What an offer shows beside a recorded commit's gist: its `sha` and the workspace it was `made_in`."""
    return {"sha": event.data["sha"], "made_in": event.data["made_in"]}


@op("repo.commit", exposes=True, tool=True)
def commit(txn: Txn, a: Which) -> dict[str, Any]:
    """Give a commit's `ref`, which `based_on` cites, its `sha`, `gist`, and the workspace it was `made_in`. Refused
    `not_found` until the look after the turn that made it records it, and `invalid` when `sha` names several."""
    event = _recorded(txn, a.sha)
    ref, fields = f"{event.stream}@{event.version}", commit_fields(event)
    expose_read(txn, [Exposed.gist(ref, event.gist, fields)])
    return {"ref": ref, "gist": event.gist, **fields}


class Testing(Args):
    commit: Given


@op("repo.test")
def test(txn: Txn, a: Testing) -> dict[str, int]:
    """Run a recorded commit's maker's code as you, unconfined: the team's `test` command, in a clean detached checkout
    of that commit. What it came to is recorded on `repo/<name>` as `repo.tested`, naming the `effect` this gives back.
    A person or a program asks for this, never an agent, as what the commit holds, a `conftest.py` among it, runs with
    all you can reach. Refused `not_permitted` to an agent, and for a commit made in an isolated workspace or built on
    one, whose code runs only there; `not_found` while the commit is not recorded yet; `invalid` when what you gave
    names several; `unsupported` when the team names no `test` or the session observes no repository; and `conflict`
    once the session is closing."""
    if txn.me.kind == "agent":
        raise Refused("not_permitted", "an agent cannot have the runtime run its code: a person or a program asks")
    session = txn.view(SessionRecord)
    if not session.accepting():
        raise Refused("conflict", f"the session is {session.state()}")
    if session.settings().test is None:
        raise Refused("unsupported", "the team names no `test` command")
    event = _recorded(txn, a.commit)
    sha = event.data["sha"]
    if (why := confined(txn.view(Looks), sha)) is not None:
        raise Refused("not_permitted", why)
    return {"effect": txn.effect("test", {"sha": sha}, on_uncertain="retry")}


class Tested(Args):
    """What a runtime test at `sha`, which `effect` ran, came to: the `command` it ran, its `exit`, None when it never
    exited on its own, the `seconds` it took, None when it never started, its `outcome`, `why` it failed or erred where
    its exit does not say, and as its `body` the last of what it printed, of `printed` bytes in all, which `blob.get`
    reads by the record's ref."""

    effect: int
    sha: Sha
    command: tuple[str, ...]
    exit: int | None
    seconds: float | None
    outcome: TestOutcome
    why: str | None = None
    body: BodyRef | None = None
    printed: int | None = None


@op("repo.record", runtime=True)
def record(txn: Txn, a: Tested) -> str:
    """Record what a runtime test of a commit came to, on `repo/<name>` with no agent in the envelope, its `why` cut to
    fit, and give its ref."""
    repo = txn.view(SessionRecord).settings().repo
    if repo is None:
        raise Refused("unsupported", "this session observes no repository")
    why = None if a.why is None else a.why[:_WHY_LIMIT]
    said = f"{a.outcome}: {why}" if why else f"failed, exit {a.exit}" if a.outcome == "failed" else a.outcome
    took = "" if a.seconds is None else f" in {a.seconds:.1f} s"
    gist = f"{a.sha[:12]} tests {said}{took}"[:GIST_LIMIT]
    refs = [a.body] if a.body else ()
    data = a.model_copy(update={"why": why})
    event = txn.emit("repo.tested", f"repo/{repo.name}", gist=gist, refs=refs, data=data)
    return f"{event.stream}@{event.version}"


class Diffing(Args):
    of: Annotated[
        str,
        Field(
            pattern=rf"^([0-9a-f]{{4,64}}|shared|@{NAME})$",
            description="A recorded commit's SHA, or its first 4 or more hex digits, for its patch; or a workspace, "
            "`@ada` for an agent's own or `shared` for the session's checkout, for what it holds uncommitted.",
        ),
    ]


def _held(txn: Txn, where: str) -> str:
    """`where`, a workspace the session holds: an agent's own once it is made and until its stop removes it, and your
    checkout while a role works there, as a look records its state only then. Refused `not_found` otherwise."""
    if where == "shared":
        if not any(role.workspace == "shared" for role in txn.view(SessionRecord).settings().roles.values()):
            raise Refused("not_found", "no role works in your checkout, so what it holds uncommitted is yours alone")
        return where
    agent = txn.view(Agents).get(where[1:])
    if agent is None:
        raise Refused("not_found", f"no agent is {where[1:]}")
    if agent.workspace is None:
        raise Refused("not_found", f"{where}'s workspace is not made yet")
    if agent.workspace.mode == "shared":
        raise Refused("not_found", f"{where[1:]} works in your checkout, which is `shared`")
    if agent.removed:
        raise Refused("not_found", f"{where}'s workspace went at its stop")
    return where


@op("repo.diff")
def diff(txn: Txn, a: Diffing) -> dict[str, int | str]:
    """Read the patch of a recorded commit against its first parent, or what a workspace holds uncommitted against its
    HEAD, as `of` names, where that workspace lives, and keep it on `repo/<name>` as `repo.diffed`, whose body is the
    patch, cut at a line's end past 64 KiB, naming the `effect` this gives back. A commit's patch never changes, so it
    is read once: asked again while it is read, this gives the same `effect`, and once it is kept, its `ref`. What a
    workspace holds uncommitted is read at each ask, and its record says when. A person or a program asks for this,
    never an agent. Refused `not_permitted` to an agent, which reads a commit through `repo.commit` or its own git;
    `not_found` while the commit is not recorded yet, and for a workspace the session holds none of; `invalid` when what
    you gave names several commits; `unsupported` when the session observes no repository; and `conflict` once the
    session is closing."""
    if txn.me.kind == "agent":
        raise Refused("not_permitted", "an agent reads a commit through `repo.commit` or its own git, not as a diff")
    session = txn.view(SessionRecord)
    if session.settings().repo is None:
        raise Refused("unsupported", "this session observes no repository")
    if not session.accepting():
        raise Refused("conflict", f"the session is {session.state()}")
    if a.of == "shared" or a.of.startswith("@"):
        asked = {"workspace": _held(txn, a.of)}
    else:
        event = _recorded(txn, a.of)
        asked = {"sha": event.data["sha"], "found_in": event.data.get("found_in")}
        if (kept := txn.view(Looks).diff(asked["sha"])) is not None:
            if kept["ref"] is not None:
                return {"ref": kept["ref"]}
            effect = txn.view(Effects).get(kept["effect"])
            if effect is not None and effect.state in ("requested", "started", "uncertain"):
                return {"effect": effect.id}
    return {"effect": txn.effect("diff", asked, on_uncertain="retry")}


class Diffed(Args):
    """What a diff `effect` read: a recorded commit's patch against its first parent, by its `sha`, or a `workspace`'s
    uncommitted diff against `head`, None before its first commit, as it was when its reading began, `read_at`, on the
    session's clock; as its `body` the patch, which `cut` says ends at the end of the last line within `PATCH_LIMIT`
    bytes, as it was longer; or `why` it could not be read."""

    effect: int
    sha: Sha | None = None
    workspace: Where | None = None
    head: Sha | None = None
    read_at: float | None = None
    body: BodyRef | None = None
    cut: bool = False
    why: str | None = None


def _diffed(a: Diffed, lines: int | None) -> str:
    """A diff's record in a line: what it is of, and how many lines its patch has and where it was cut, or why it could
    not be read."""
    what = f"{a.sha[:12]} patch" if a.sha is not None else f"{a.workspace} uncommitted"
    if lines is None:
        return f"{what} could not be read: {a.why}"
    if a.sha is None:
        what += f" against {'no commit' if a.head is None else a.head[:12]}"
    cut = f"cut after {_some(lines, 'line')} at {PATCH_LIMIT // 1024} KiB" if a.cut else _some(lines, "line")
    return f"{what}, {cut}"


@op("repo.keep", runtime=True)
def keep(txn: Txn, a: Diffed) -> str:
    """Keep what a diff read, on `repo/<name>` with no agent in the envelope, its `why` cut to fit, and give its ref.
    Its body must be one the journal holds, which its gist counts the lines of."""
    repo = txn.view(SessionRecord).settings().repo
    if repo is None:
        raise Refused("unsupported", "this session observes no repository")
    patch = None if a.body is None else inline_body(txn, a.body)
    if a.body is not None and patch is None:
        raise Refused("invalid", "a patch is kept in a body the journal holds")
    why = None if a.why is None else a.why[:_WHY_LIMIT]
    data = a.model_copy(update={"why": why})
    gist = _diffed(data, None if patch is None else patch.count(b"\n"))[:GIST_LIMIT]
    event = txn.emit("repo.diffed", f"repo/{repo.name}", gist=gist, refs=[a.body] if a.body else (), data=data)
    return f"{event.stream}@{event.version}"


@op("repo.looks", query=True, runtime=True)
def looks(txn: Txn, a: Args) -> dict[str, dict[str, Any]]:
    """The head and branch each workspace's last look read, by workspace, which the next look starts from."""
    return {
        where: {"head": read["head"], "branch": read["branch"]} for where, read in txn.view(Looks).readings().items()
    }
