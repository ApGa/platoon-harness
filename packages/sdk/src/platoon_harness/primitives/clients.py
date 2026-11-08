"""What clients render: `roster`, `attention` and `changes`, watched as a snapshot and then keyed changes."""

import json
import sqlite3
from collections.abc import Collection
from typing import Annotated, Any, Literal

from pydantic import Field

from platoon_harness.kernel import GIST_LIMIT, Args, Effect, Effects, Event, Stamps, Txn, View, fold, op

from . import why
from .agents import Agent, Agents
from .approvals import Approvals
from .budgets import Budgets
from .common import DIGEST_ITEMS, name_of
from .messages import Deliveries
from .repo import Looks, confined, unsettled
from .sessions import SessionRecord
from .tasks import Tasks
from .waits import Waits

WATCH_SPAN = 4096
_MOOT_WITH_ITS_AGENT = ("approval", "uncertain", "failed", "hops", "budget", "conflict")

Group = Literal["needs_you", "working", "blocked", "idle", "done", "failed"]
"""The navigator's groups: what a person must do about an agent, derived in the view so every client says the same."""


def _action(label: str, op: str, args: dict[str, Any], *, form: bool = False) -> dict[str, Any]:
    """An action as an op reference: its label, its op, the arguments it fixes, and `form`, whether it leaves the rest
    to its op's form, as one that knows only some of them does."""
    return {"label": label, "op": op, "args": args, "form": form}


def _resolve_actions(event: Event) -> list[dict[str, Any]]:
    """Buttons as op references, each with the version it was drawn from."""
    return [
        _action(
            verdict.capitalize(),
            "approval.resolve",
            {"id": event.data["id"], "verdict": verdict, "expected_version": event.version},
        )
        for verdict in ("allow", "deny")
    ]


def _settle_actions(event: Event) -> list[dict[str, Any]]:
    """Whether an effect happened is for a person to say, and the first to say wins."""
    return [
        _action(label, "effect.settle", {"id": event.data["id"], "happened": happened})
        for label, happened in (("It happened", True), ("It did not", False))
    ]


def _write_to(agent: str | None) -> list[dict[str, Any]]:
    """What settles a place its agent's next turn settles: a message from the person, whose words are theirs to give,
    and which is no hop, so it wakes the agent. A place of no agent's has none."""
    return [] if agent is None else [_action("Write to it", "message.send", {"to": f"@{agent}"}, form=True)]


class Attention(View):
    """Where a human must act. A row closes in place, so a watcher hears that it went away. Each workspace whose latest
    look found conflicted paths is kept, so that its row comes back after the next look that still finds them, and
    what each budget scope was last set to, which setting it again replaces whole."""

    version = 6
    schema = """
    CREATE TABLE v_attention(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        agent TEXT,
        gist TEXT NOT NULL,
        since_seq INTEGER NOT NULL,
        version INTEGER NOT NULL,
        actions TEXT NOT NULL,
        open INTEGER NOT NULL,
        seq INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_attention_open ON v_attention(open, since_seq);
    CREATE INDEX v_attention_seq ON v_attention(seq);
    CREATE TABLE v_attention_conflicts(workspace TEXT PRIMARY KEY, gist TEXT NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_attention_budgets(scope TEXT PRIMARY KEY, set_to TEXT NOT NULL) WITHOUT ROWID, STRICT;
    """

    def _raise(
        self,
        id: str,
        kind: str,
        event: Event,
        actions: list[dict[str, Any]] | None = None,
        *,
        agent: str | None = None,
        gist: str | None = None,
    ) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO v_attention VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (
                id,
                kind,
                agent or event.agent,
                gist or event.gist,
                event.seq,
                event.version,
                json.dumps(actions or []),
                event.seq,
            ),
        )

    def _lower(self, event: Event, condition: str, *values: Any) -> None:
        self.db.execute(
            f"UPDATE v_attention SET open = 0, seq = ? WHERE open = 1 AND {condition}", (event.seq, *values)
        )

    @fold("approval.requested")
    def approval_asked(self, event: Event) -> None:
        if event.data["policy"] == "ask":
            self._raise(f"approval/{event.data['id']}", "approval", event, _resolve_actions(event))

    @fold("approval.resolved")
    def approval_decided(self, event: Event) -> None:
        self._lower(event, "id = ?", f"approval/{event.data['id']}")

    @fold("agent.ended")
    def agent_gone(self, event: Event) -> None:
        """What only that agent could have settled is moot, a conflict among it, which the Ending names with the
        workspace kept for it, and its messages to the person are still theirs to read but take no reply. A final
        report nobody received waits for a human."""
        marks = ", ".join("?" * len(_MOOT_WITH_ITS_AGENT))
        self._lower(event, f"agent = ? AND kind IN ({marks})", event.agent, *_MOOT_WITH_ITS_AGENT)
        self.db.execute(
            "UPDATE v_attention SET actions = '[]', seq = ? "
            "WHERE open = 1 AND kind = 'mention' AND agent = ? AND actions != '[]'",
            (event.seq, event.agent),
        )
        self.db.execute("DELETE FROM v_attention_conflicts WHERE workspace = ?", (f"@{event.agent}",))
        if event.data["status"] == "finished" and not event.data["heard"]:
            self._raise(event.stream, "mention", event)

    @fold("message.sent")
    def mention(self, event: Event) -> None:
        """A message to a person, which a reply settles, as reading it does in the person's marks. The runtime's report
        of an agent takes no reply."""
        if event.data["mention"] is not None:
            ref, sender = f"{event.stream}@{event.version}", event.data["sender"]
            reply = _action("Reply", "message.send", {"to": sender, "reply_to": ref}, form=True)
            self._raise(ref, "mention", event, [] if sender == "runtime" else [reply])
        if event.data["reply_to"] is not None:
            self._lower(event, "id = ?", event.data["reply_to"])

    @fold("effect.uncertain")
    def uncertain(self, event: Event) -> None:
        self._raise(f"effect/{event.data['id']}", "uncertain", event, _settle_actions(event))

    @fold("effect.finished", "effect.retried")
    def certain(self, event: Event) -> None:
        self._lower(event, "id = ?", f"effect/{event.data['id']}")

    @fold("workspace.changed")
    def conflicted(self, event: Event) -> None:
        """A workspace's latest look found conflicted paths, or none. The shared workspace's row is open while its
        latest look found some, and an agent's comes at the end of each look of its agent's that still finds them, so
        it never comes for an agent that has ended, whose stop looked last."""
        where = event.data["workspace"]
        if event.data["conflicted"]:
            gist = unsettled(where, event.data)
            self.db.execute("INSERT OR REPLACE INTO v_attention_conflicts VALUES (?, ?)", (where, gist))
            if where == "shared":
                self._raise("conflict/shared", "conflict", event, gist=gist)
        else:
            self.db.execute("DELETE FROM v_attention_conflicts WHERE workspace = ?", (where,))
            self._lower(event, "id = ?", f"conflict/{where}")

    @fold("effect.finished")
    def looked(self, event: Event) -> None:
        """An agent's conflict needs you again after each look that still finds it, while it rests on it."""
        if event.data["kind"] != "probe":
            return
        where = f"@{event.agent}"
        found = self.db.execute("SELECT gist FROM v_attention_conflicts WHERE workspace = ?", (where,)).fetchone()
        if found is not None:
            self._raise(f"conflict/{where}", "conflict", event, _write_to(event.agent), gist=found["gist"])

    @fold("effect.failed")
    def failed(self, event: Event) -> None:
        """A failure is news, unless a person said so, who has nothing left to do here. An agent's next turn settles
        its own. Nothing tries one of no agent's again, which only the runtime's own error or an extension's daemon
        makes, as a test and a diff record their own failures."""
        id = f"effect/{event.data['id']}"
        if event.actor != "runtime":
            self._lower(event, "id = ?", id)
        elif event.agent is not None:
            self._raise(id, "failed", event, _write_to(event.agent))
        else:
            said = f"{event.data['kind']} failed, and nothing tries it again: {event.data['error']}"
            self._raise(id, "failed", event, gist=said[:GIST_LIMIT])

    @fold("task.died")
    def dead_task(self, event: Event) -> None:
        """A task past its attempts is added again citing it, its `task.added`, which settles it."""
        again = {"queue": event.data["queue"], "based_on": [f"{event.stream}@1"]}
        self._raise(event.stream, "dead_task", event, [_action("Add it again", "task.add", again, form=True)])

    @fold("task.added")
    def task_again(self, event: Event) -> None:
        """A task added citing a dead one takes its place."""
        for ref in event.based_on:
            self._lower(event, "id = ? AND kind = 'dead_task'", ref.partition("@")[0])

    def _set_budget(self, scope: str | None) -> list[dict[str, Any]]:
        """Setting a budget settles every place one held up. `budget.set` replaces a scope's limits and estimate whole,
        so the action fixes the scope that held it up, where the record names one, filled in with what it was set to,
        for the person to change."""
        if scope is None:
            return [_action("Set the budget", "budget.set", {}, form=True)]
        found = self.db.execute("SELECT set_to FROM v_attention_budgets WHERE scope = ?", (scope,)).fetchone()
        set_to = {} if found is None else {key: value for key, value in json.loads(found["set_to"]).items() if value}
        return [_action("Set the budget", "budget.set", {"scope": scope, **set_to}, form=True)]

    @fold("wake.refused")
    def wake_refused(self, event: Event) -> None:
        """A wake past `max_hops`, or one a budget refused, naming the scope that refused it, and for a limit no amount
        can hold, saying in its gist that it is to be removed."""
        if event.data["why"] == "hops":
            self._raise(f"wake/{event.agent}", "hops", event, _write_to(event.agent))
            return
        detail = event.data["detail"]
        scope, why = (detail.get("scope"), detail.get("detail")) if isinstance(detail, dict) else (None, None)
        gist = None if why is None else f"{event.gist}: {why}"[:GIST_LIMIT]
        self._raise(f"wake/{event.agent}", "budget", event, self._set_budget(scope), gist=gist)

    @fold("budget.lapsed")
    def budget_lapsed(self, event: Event) -> None:
        self._raise(event.stream, "budget", event, self._set_budget("shared"))

    @fold("budget.set")
    def budget_set(self, event: Event) -> None:
        set_to = {key: event.data[key] for key in ("limits", "estimate")}
        self.db.execute(
            "INSERT OR REPLACE INTO v_attention_budgets VALUES (?, ?)", (event.data["scope"], json.dumps(set_to))
        )
        self._lower(event, "kind = 'budget'")

    @fold("daemon.failed")
    def daemon_failed(self, event: Event) -> None:
        """A daemon that fails is restarted with backoff, and one that fails on every pass leaves no other trace."""
        self._raise(event.stream, "daemon", event)

    @fold("daemon.recovered")
    def daemon_recovered(self, event: Event) -> None:
        self._lower(event, "id = ?", event.stream)

    @fold("runtime.started")
    def restarted(self, event: Event) -> None:
        """A new runtime's daemons have not failed yet."""
        self._lower(event, "kind = 'daemon'")

    @fold("turn.lost")
    def turn_lost(self, event: Event) -> None:
        """Nobody knows what a lost turn did, until its agent's next turn has looked."""
        self._raise(f"turn/{event.agent}", "uncertain", event, _write_to(event.agent))

    @fold("turn.ended", "turn.lost")
    def approval_moot(self, event: Event) -> None:
        self._lower(event, "agent = ? AND kind = 'approval'", event.agent)

    @fold("turn.started")
    def turn_started(self, event: Event) -> None:
        """An agent at work on its conflict is not resting on it."""
        ids = (f"wake/{event.agent}", f"turn/{event.agent}", f"conflict/@{event.agent}")
        self._lower(event, "id IN (?, ?, ?) OR (agent = ? AND kind = 'failed')", *ids, event.agent)

    def _row(self, row: Any) -> dict[str, Any]:
        return {**dict(row), "actions": json.loads(row["actions"]), "open": bool(row["open"])}

    def rows(self) -> list[dict[str, Any]]:
        return [
            self._row(row) for row in self.db.execute("SELECT * FROM v_attention WHERE open = 1 ORDER BY since_seq")
        ]

    def since(self, after: int) -> list[dict[str, Any]]:
        return [
            self._row(row) for row in self.db.execute("SELECT * FROM v_attention WHERE seq > ? ORDER BY seq", (after,))
        ]


class Changes(View):
    """What changed, as looks found it, a row for each recorded commit, with the seq that `recorded` it, its `tests`,
    the outcome of the latest runtime test at it, or None while none ran, and that test's `tested` ref, `tests_why` and
    `tests_exit` where it has them, so a client says why it failed and can open its record; for each workspace's last
    reading; and for each path it holds uncommitted, keyed by `id`, each with the `seq` that last moved it, which a
    client compares with the person's mark on `repo/<name>`. A newer reading replaces its workspace's paths whole, and a
    row closes in place, so a watcher hears that it went away."""

    version = 3
    schema = """
    CREATE TABLE v_changes(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        workspace TEXT,
        row TEXT NOT NULL,
        open INTEGER NOT NULL,
        seq INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_changes_seq ON v_changes(seq);
    CREATE INDEX v_changes_workspace ON v_changes(workspace, kind);
    """

    def _put(self, row: dict[str, Any], workspace: str | None, event: Event) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO v_changes VALUES (?, ?, ?, ?, 1, ?)",
            (row["id"], row["kind"], workspace, json.dumps(row), event.seq),
        )

    @fold("repo.committed")
    def committed(self, event: Event) -> None:
        data = event.data
        shown = {key: data[key] for key in ("made_in", "branch", "added", "removed", "files")}
        row = {"id": f"commit/{data['sha']}", "kind": "commit", "commit": data["sha"], "gist": event.gist, **shown}
        self._put({**row, "recorded": event.seq, "tests": None, "dropped": False}, None, event)

    def _amend(self, sha: str, event: Event, **changed: Any) -> None:
        found = self.db.execute("SELECT row FROM v_changes WHERE id = ?", (f"commit/{sha}",)).fetchone()
        if found is not None:
            self._put({**json.loads(found["row"]), **changed}, None, event)

    @fold("repo.rewritten")
    def rewritten(self, event: Event) -> None:
        for sha in event.data["dropped"]:
            self._amend(sha, event, dropped=True)

    @fold("repo.tested")
    def tested(self, event: Event) -> None:
        data = event.data
        self._amend(
            data["sha"],
            event,
            tests=data["outcome"],
            tested=f"{event.stream}@{event.version}",
            tests_why=data.get("why"),
            tests_exit=data.get("exit"),
        )

    @fold("workspace.changed")
    def changed(self, event: Event) -> None:
        """A path whose row says the same as before keeps the seq that last moved it, so it is not news again. A
        reading that recorded no uncommitted state, as of your checkout when no role works in it, shows nothing."""
        data, where = event.data, event.data["workspace"]
        if data["paths"] is None:
            return
        shown = {key: data[key] for key in ("head", "branch", "under_way", "rebasing", "total", "conflicted")}
        self._put({"id": f"workspace/{where}", "kind": "workspace", "workspace": where, **shown}, where, event)
        held = {
            row["id"]: row["row"]
            for row in self.db.execute(
                "SELECT id, row FROM v_changes WHERE workspace = ? AND kind = 'path' AND open = 1", (where,)
            )
        }
        for path in data["paths"]:
            row = {"id": f"path/{where}/{path['path']}", "kind": "path", "workspace": where, **path}
            if held.pop(row["id"], None) != json.dumps(row):
                self._put(row, where, event)
        for gone in held:
            self.db.execute("UPDATE v_changes SET open = 0, seq = ? WHERE id = ?", (event.seq, gone))

    def _row(self, row: Any) -> dict[str, Any]:
        return {**json.loads(row["row"]), "seq": row["seq"]}

    def rows(self) -> list[dict[str, Any]]:
        return [self._row(row) for row in self.db.execute("SELECT * FROM v_changes WHERE open = 1 ORDER BY seq")]

    def since(self, after: int) -> tuple[list[dict[str, Any]], list[str]]:
        """The rows that moved past `after`, and the keys of those that went away."""
        rows = self.db.execute("SELECT * FROM v_changes WHERE seq > ? ORDER BY seq", (after,)).fetchall()
        return [self._row(row) for row in rows if row["open"]], [row["id"] for row in rows if not row["open"]]


class Gaps(View):
    """Every incident gap by its agent and where it `began`: where it stands, or the `since` that a gap recorded after
    the fact names. An ending counts them by agent and kind, and an answer takes those below its bound."""

    version = 2
    schema = """
    CREATE TABLE v_gaps(
        seq INTEGER PRIMARY KEY,
        agent TEXT NOT NULL,
        what TEXT NOT NULL,
        plane TEXT NOT NULL,
        began INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX v_gaps_began ON v_gaps(agent, began, seq);
    """

    def _gap(self, event: Event, what: str, plane: str, since: int | None = None) -> None:
        self.db.execute(
            "INSERT INTO v_gaps VALUES (?, ?, ?, ?, ?)",
            (event.seq, event.agent, what, plane, event.seq if since is None else since),
        )

    @fold("gap.recorded")
    def recorded(self, event: Event) -> None:
        """A v1 gap named no `since`."""
        self._gap(event, event.data["what"], event.data["plane"], event.data.get("since"))

    @fold("turn.lost")
    def turn_lost(self, event: Event) -> None:
        """A v1 lost turn named its gap itself. From v2 it is a `gap.recorded` beside it."""
        if event.v < 2:
            self._gap(event, event.data["gap"], "control")

    def rows(self) -> list[dict[str, Any]]:
        """How many gaps of each kind each agent has, as an ending states them."""
        rows = self.db.execute(
            "SELECT agent, what, min(plane) AS plane, count(*) AS count FROM v_gaps GROUP BY agent, what "
            "ORDER BY agent, what"
        )
        return [dict(row) for row in rows]

    def below(
        self, agent: str, bound: int, *, besides: Collection[str] = (), before: tuple[int, int] | None = None
    ) -> tuple[list[sqlite3.Row], int]:
        """An agent's gaps but those of the kinds `besides` that began below `bound`, newest first by where they began
        and going back past `before`, as many as a page holds and one more, and how many began below `bound` in all."""
        marks = ", ".join("?" * len(besides))
        where = f"agent = ? AND began < ? AND what NOT IN ({marks})"
        began, seq = before or (bound, 0)
        rows = self.db.execute(
            f"SELECT * FROM v_gaps WHERE {where} AND (began, seq) < (?, ?) ORDER BY began DESC, seq DESC LIMIT ?",
            (agent, bound, *besides, began, seq, DIGEST_ITEMS + 1),
        ).fetchall()
        total = self.db.execute(f"SELECT count(*) AS n FROM v_gaps WHERE {where}", (agent, bound, *besides))
        return rows, total.fetchone()["n"]

    def counted(self, agent: str, bound: int, *, besides: Collection[str] = ()) -> dict[str, int]:
        """How many of an agent's gaps but those of the kinds `besides` began below `bound`, by kind."""
        marks = ", ".join("?" * len(besides))
        rows = self.db.execute(
            f"SELECT what, count(*) AS n FROM v_gaps WHERE agent = ? AND began < ? AND what NOT IN ({marks}) "
            "GROUP BY what ORDER BY what",
            (agent, bound, *besides),
        )
        return {row["what"]: row["n"] for row in rows}

    def held(self, head: int, *, besides: Collection[str] = ()) -> dict[str, dict[str, int]]:
        """How many gaps but those of the kinds `besides` the record held of each agent at `head`, by agent and kind."""
        marks = ", ".join("?" * len(besides))
        rows = self.db.execute(
            f"SELECT agent, what, count(*) AS n FROM v_gaps WHERE seq <= ? AND what NOT IN ({marks}) "
            "GROUP BY agent, what ORDER BY agent, what",
            (head, *besides),
        )
        found: dict[str, dict[str, int]] = {}
        for row in rows:
            found.setdefault(row["agent"], {})[row["what"]] = row["n"]
        return found


def _why(txn: Txn, agent: Agent, uncertain: list[Effect], dues: dict[str, float]) -> why.Why | None:
    """The one thing most worth saying about this agent, or nothing if it needs no explaining."""
    if agent.ended:
        return why.Lost(reason=agent.reason or "unknown") if agent.status == "lost" else None
    if pending := txn.view(Approvals).pending_for(agent.name):
        return why.Approval(id=pending[0].id)
    if (blocked := txn.view(Deliveries).blocked(agent.name)) is not None:
        return why.Budget(code=blocked)
    if failing := [effect for effect in uncertain if effect.agent == agent.name]:
        return why.Infra(detail=f"{failing[0].kind} is uncertain")
    if agent.state == "waiting" and (waits := txn.view(Waits).open_for(agent.id)):
        wait = waits[0]
        missing = wait.missing
        if len(missing) == 1 and missing[0].startswith("@"):
            return why.Peer(id=missing[0].removeprefix("@"))
        return why.Wait(have=wait.have, need=wait.need, missing=missing)
    if agent.name in dues:
        return why.Timer(at=dues[agent.name])
    if agent.state == "idle" and (leases := txn.view(Tasks).owned(agent.id)):
        return why.Lease(id=leases[0].stream)
    return None


def _group(agent: Agent, said: why.Why | None, needing: set[str]) -> Group:
    """Needs you while an attention row other than a mention names it, then done or failed once it has ended, working in
    a turn, on its way to one or held, blocked while `why` names what it waits on, and idle otherwise."""
    if agent.name in needing:
        return "needs_you"
    if agent.ended:
        return "failed" if agent.status in ("failed", "lost") else "done"
    if agent.starting or agent.state in ("running", "held"):
        return "working"
    return "blocked" if said is not None else "idle"


def roster(txn: Txn) -> list[dict[str, Any]]:
    """A row per agent, live or ended, each in its group: what a person must do about it."""
    uncertain = txn.view(Effects).in_state("uncertain")
    dues = {reader: due for reader, due, _ in txn.view(Deliveries).waking() if due > txn.now}
    deliveries = txn.view(Deliveries)
    budget = txn.view(Budgets)
    needing = {row["agent"] for row in txn.view(Attention).rows() if row["kind"] != "mention"}
    rows = []
    for agent in txn.view(Agents).listed():
        said = _why(txn, agent, uncertain, dues)
        rows.append(
            {
                "agent": agent.name,
                "role": agent.role,
                "harness": agent.harness,
                "model": agent.model,
                "parent": agent.parent and name_of(agent.parent),
                "state": agent.state,
                "resting": agent.resting,
                "group": _group(agent, said, needing),
                "activity": agent.activity,
                "stopped": agent.stopped,
                "held_by": agent.held_by and name_of(agent.held_by),
                "why": said,
                "unread": deliveries.unread(agent.name),
                "levels": agent.levels,
                "login": agent.login,
                "usage": budget.usage_of(f"agent:{agent.name}"),
                "workspace": agent.workspace and agent.workspace.model_dump(include={"mode", "path", "branch"}),
            }
        )
    return rows


@op("attention.list", query=True)
def attention_list(txn: Txn, a: Args) -> list[dict[str, Any]]:
    """List what needs a human now, each with the actions that would settle it."""
    return txn.view(Attention).rows()


class Watch(Args):
    name: Annotated[Literal["roster", "attention", "changes"], Field(description="The view.")]
    after: Annotated[
        int | None, Field(ge=0, description="The `cursor` of an earlier answer, for what changed since it.")
    ] = None


def _acted(txn: Txn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Changes rows, each commit's with the act that tests it when the team names a `test`, saying whose code it runs as
    you, or disabled, saying why, for a commit whose code runs only in an isolation. Neither changes once the commit is
    recorded, so a row's `seq` still says when it last moved."""
    if txn.view(SessionRecord).settings().test is None:
        return rows
    looks = txn.view(Looks)
    acted = []
    for row in rows:
        if row["kind"] == "commit":
            made_in = row["made_in"]
            whose = f"{made_in}'s commit" if made_in and made_in.startswith("@") else "this commit"
            disabled = confined(looks, row["commit"])
            label = "Test" if disabled else f"Test: runs {whose} as you, unconfined"
            act = {"label": label, "op": "repo.test", "args": {"commit": row["commit"]}, "disabled": disabled}
            row = {**row, "actions": [act]}
        acted.append(row)
    return acted


def _snapshot(txn: Txn, name: str) -> list[dict[str, Any]]:
    if name == "roster":
        return roster(txn)
    return txn.view(Attention).rows() if name == "attention" else _acted(txn, txn.view(Changes).rows())


def _changed(txn: Txn, name: str, after: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows changed past `after`, and the keys that went away. Almost any event can move a roster row, under a name
    that is not that agent's, so a roster changes as a whole whenever the journal moves."""
    if name == "roster":
        return (roster(txn) if txn.view(Stamps).head() > after else []), []
    if name == "changes":
        rows, removed = txn.view(Changes).since(after)
        return _acted(txn, rows), removed
    rows = txn.view(Attention).since(after)
    return [row for row in rows if row["open"]], [row["id"] for row in rows if not row["open"]]


@op("view.watch", query=True)
def watch(txn: Txn, a: Watch) -> dict[str, Any]:
    """A snapshot, then keyed changes. Pass `cursor` as the next `after`; a reader too far behind gets a new snapshot.

    Snapshot and cursor come from one read, so nothing commits between them.
    """
    head = txn.view(Stamps).head()
    if a.after is None or head - a.after > WATCH_SPAN:
        return {"snapshot": True, "rows": _snapshot(txn, a.name), "removed": [], "cursor": head}
    rows, removed = _changed(txn, a.name, a.after)
    return {"snapshot": False, "rows": rows, "removed": removed, "cursor": head}
