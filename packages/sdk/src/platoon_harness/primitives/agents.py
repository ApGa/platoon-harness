"""The agent record: one row per agent, kept for good, because retiring leaves the team and never the journal."""

import json
from typing import Any, Literal

from pydantic import BaseModel

from platoon_harness.kernel import Event, View, fold

from .common import IN_A_RESULT

AgentState = Literal["spawning", "idle", "waking", "running", "waiting", "held", "ended"]
Mode = Literal["shared", "worktree", "snapshot", "isolated"]


class Workspace(BaseModel, frozen=True):
    """Where an agent works, as its `workspace` effect made it: in `mode`, its harness runs in the folder `path` on
    `host`, on `branch` made at the commit `base`, with the git directory `repository` holding its refs, and `objects`
    the object directory a snapshot reads. `assurance` is how well what runs there is tied to its credential. What a
    mode does not have is None."""

    mode: Mode
    path: str
    host: str | None = None
    branch: str | None = None
    base: str | None = None
    repository: str | None = None
    objects: str | None = None
    assurance: Literal["cooperative", "isolated"] = "cooperative"


class Kept(BaseModel, frozen=True):
    """A workspace its agent's stop left in place, on `host` at `path`, on `branch`, taking `bytes` on disk, and `why`:
    what removing it would lose, or why that could not be told. `release` is the commands that let it go and lose
    nothing it was kept for but the ignored files `why` names, and is empty when no commands would: then `why` says
    what to save first."""

    path: str
    host: str | None
    branch: str | None
    bytes: int | None
    why: tuple[str, ...]
    release: tuple[str, ...] = ()


class Agent(BaseModel, frozen=True):
    """One agent. `parent` is the spawner's principal id, and `None` once adopted by the session. `stays` says it is
    told to stay after its task for the next message. `asked` says its parent is owed an answer: the spawn asks, and so
    does each new message from the parent once it lands in a turn, until a report answers. `native` is the id its
    harness resumes by, when it gave one. `unbegun` says it was given a goal and no turn has begun on it. `final_ref` is
    the ref of what said its last words: its turn's last message, or a finished agent's end. `finishing` says it called
    `agent.finish` in a turn that has not ended, and `finish_ref` is that call's `agent.finished`. `stopped` says why
    its last turn did not stop on its own, until the next begins. `failure` is what the last effect to fail for it said,
    `failures` counts handovers failed in a row, and the next waits until `retry_at`. `quieted` is the seq of the last
    interrupt of it or owner's stop, and a handover asked for before it is no failure of its harness's. `instructions`
    is the body of what its harness was told last, or None for nothing. `workspace` is where it works, once made, and
    `removed` or `kept` say what its stop did with it."""

    name: str
    role: str
    parent: str | None
    depth: int
    stays: bool
    asked: bool
    state: AgentState
    status: str | None
    reason: str | None
    harness: Any
    model: str | None
    on_parent_exit: str
    persistent: bool | None
    resume: bool | None
    native: str | None
    tool_timeout_s: float | None
    boundaries: tuple[str, ...]
    held_by: str | None
    goal: str
    goal_body: str | None
    unbegun: bool
    activity: str | None
    final_gist: str | None
    final_body: str | None
    final_ref: str | None
    finishing: bool
    finish_gist: str | None
    finish_body: str | None
    finish_ref: str | None
    stopped: str | None
    failure: str | None
    failures: int
    retry_at: float
    quieted: int
    levels: dict[str, Any]
    instructions: str | None
    workspace: Workspace | None
    removed: bool
    kept: Kept | None

    @property
    def id(self) -> str:
        return f"agent:{self.name}"

    @property
    def ended(self) -> bool:
        return self.state == "ended"

    @property
    def starting(self) -> bool:
        """Whether a turn is on its way to this agent."""
        return self.state in ("spawning", "waking") or self.unbegun


class Agents(View):
    """Everyone ever spawned, live or not."""

    version = 11
    schema = """
    CREATE TABLE v_agents(
        name TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        parent TEXT,
        depth INTEGER NOT NULL,
        stays INTEGER NOT NULL,
        asked INTEGER NOT NULL,
        state TEXT NOT NULL,
        status TEXT,
        reason TEXT,
        harness TEXT NOT NULL,
        model TEXT,
        on_parent_exit TEXT NOT NULL,
        persistent INTEGER,
        resume INTEGER,
        native TEXT,
        tool_timeout_s REAL,
        boundaries TEXT NOT NULL,
        held_by TEXT,
        goal TEXT NOT NULL,
        goal_body TEXT,
        unbegun INTEGER NOT NULL,
        activity TEXT,
        final_gist TEXT,
        final_body TEXT,
        final_ref TEXT,
        finishing INTEGER NOT NULL DEFAULT 0,
        finish_gist TEXT,
        finish_body TEXT,
        finish_ref TEXT,
        stopped TEXT,
        failure TEXT,
        failures INTEGER NOT NULL DEFAULT 0,
        retry_at REAL NOT NULL DEFAULT 0,
        quieted INTEGER NOT NULL DEFAULT 0,
        levels TEXT NOT NULL DEFAULT '{}',
        instructions TEXT,
        workspace TEXT,
        removed INTEGER NOT NULL DEFAULT 0,
        kept TEXT
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_agents_parent ON v_agents(parent);
    CREATE INDEX v_agents_state ON v_agents(state);
    """

    @fold("agent.spawned")
    def spawned(self, event: Event) -> None:
        """The spawn asks, so a child's first report answers it. One the session started has no parent to ask. A v1
        spawn said nothing of `stays`, and then a root was told to stay and a child to finish."""
        data = {"stays": event.data["parent"] is None, **event.data}
        self.db.execute(
            """
            INSERT INTO v_agents(
                name, role, parent, depth, stays, asked, state, harness, model, on_parent_exit, boundaries, goal,
                goal_body, unbegun
            ) VALUES (
                :name, :role, :parent, :depth, :stays, :asked, 'spawning', :harness, :model, :on_parent_exit, '[]',
                :goal, :body, :unbegun
            )
            """,
            {
                **data,
                "asked": data["parent"] is not None,
                "harness": json.dumps(data["harness"]),
                "unbegun": bool(data["goal"] or data["body"]),
            },
        )

    @fold("agent.started", "agent.resumed")
    def harness_up(self, event: Event) -> None:
        data, declared = event.data, event.data["declared"]
        self.db.execute(
            """
            UPDATE v_agents SET persistent = :persistent, resume = :resume, tool_timeout_s = :tool_timeout_s,
                boundaries = :boundaries, levels = :levels, model = coalesce(:effective_model, model),
                native = coalesce(:native, native)
            WHERE name = :agent
            """,
            {
                **declared,
                "effective_model": data["effective_model"],
                "native": data["native"],
                "boundaries": json.dumps(sorted(declared["boundaries"])),
                "levels": json.dumps(data["levels"]),
                "agent": event.agent,
            },
        )
        if event.type == "agent.started":
            self._move(event, "idle", "spawning")

    @fold("agent.instructed")
    def instructed(self, event: Event) -> None:
        """A v1 record named its text `instructions`."""
        told = event.data["body"] if event.v >= 2 else event.data["instructions"]
        self.db.execute("UPDATE v_agents SET instructions = ? WHERE name = ?", (told, event.agent))

    def _move(self, event: Event, state: str, *only: str) -> None:
        marks = ", ".join("?" * len(only))
        self.db.execute(
            f"UPDATE v_agents SET state = ? WHERE name = ? AND state IN ({marks})", (state, event.agent, *only)
        )

    def _reachable(self, event: Event) -> None:
        self.db.execute("UPDATE v_agents SET failures = 0, retry_at = 0 WHERE name = ?", (event.agent,))

    @fold("turn.started")
    def working(self, event: Event) -> None:
        self._move(event, "running", "idle", "waking", "waiting")
        self._reachable(event)
        self.db.execute(
            "UPDATE v_agents SET unbegun = 0, final_gist = NULL, final_body = NULL, final_ref = NULL, stopped = NULL "
            "WHERE name = ?",
            (event.agent,),
        )

    @fold("turn.ended", "turn.lost")
    def turn_over(self, event: Event) -> None:
        self._move(event, "idle", "running", "waking")
        self._reachable(event)
        reason = "lost" if event.type == "turn.lost" else event.data["reason"]
        self.db.execute(
            "UPDATE v_agents SET stopped = ? WHERE name = ?", (None if reason == "stopped" else reason, event.agent)
        )

    @fold("agent.woken")
    def woken(self, event: Event) -> None:
        self._move(event, "waking", "idle", "waiting")

    @fold("context.offered", "context.delivered")
    def handed(self, event: Event) -> None:
        """A parent's message asks once it lands in a turn: at once in a tool's result, and by a handover once the
        harness says it landed, which for a steer can be in the turn after the one it was offered in. A v1 offer or
        landing asked nothing."""
        lands = event.type == "context.delivered" or event.data["how"] in IN_A_RESULT
        if lands and event.data.get("asked", False):
            self.db.execute("UPDATE v_agents SET asked = 1 WHERE name = ?", (event.agent,))

    @fold("message.sent")
    def answered(self, event: Event) -> None:
        """A report answers what its parent asked, unless an interrupt or the owner's stop cut its turn. A v1 report
        answered whatever it said."""
        if event.data["subject"] is not None and event.data.get("answers", True):
            self.db.execute("UPDATE v_agents SET asked = 0 WHERE name = ?", (event.data["subject"],))

    @fold("effect.failed")
    def failed(self, event: Event) -> None:
        """A failed handover gives back its wake, and the next waits twice as long as the last. One an interrupt or the
        owner's stop cut, asked for before it, is no failure of its harness's, so what comes after wakes as usual."""
        self.db.execute("UPDATE v_agents SET failure = ? WHERE name = ?", (event.data["error"], event.agent))
        if event.data["kind"] == "deliver":
            self._move(event, "idle", "waking")
            self.db.execute(
                """
                UPDATE v_agents SET failures = failures + 1, retry_at = ? + (1 << failures)
                WHERE name = ? AND quieted < ?
                """,
                (event.wall_time, event.agent, event.data["id"]),
            )

    @fold("effect.finished")
    def made(self, event: Event) -> None:
        """Where an agent works, and what its stop did with that. A workspace from before modes was the session's cwd,
        and a stop from before kept nothing it made."""
        result = event.data["result"]
        if event.data["kind"] == "workspace" and result is not None:
            workspace = Workspace.model_validate({"mode": "shared", **result})
            self.db.execute(
                "UPDATE v_agents SET workspace = ? WHERE name = ?", (workspace.model_dump_json(), event.agent)
            )
        elif event.data["kind"] == "stop" and result is not None:
            kept = None if result["kept"] is None else json.dumps(result["kept"])
            self.db.execute(
                "UPDATE v_agents SET removed = ?, kept = ? WHERE name = ?", (result["removed"], kept, event.agent)
            )

    @fold("effect.cancelled")
    def handed_back(self, event: Event) -> None:
        """A handover cancelled before it started, as the owner's stop does, gives back its wake and is no failure."""
        if event.data["kind"] == "deliver":
            self._move(event, "idle", "waking")

    @fold("wake.quieted")
    def quiet(self, event: Event) -> None:
        self.db.execute("UPDATE v_agents SET quieted = ? WHERE name = ?", (event.seq, event.agent))

    @fold("session.stopped")
    def stopped(self, event: Event) -> None:
        """A handover under way when the owner stopped is the next runtime's to fail, and that is no failure either."""
        self.db.execute("UPDATE v_agents SET quieted = ?", (event.seq,))

    @fold("agent.parked")
    def parked(self, event: Event) -> None:
        self._move(event, "waiting", "idle", "running")

    @fold("agent.held")
    def held(self, event: Event) -> None:
        self.db.execute(
            "UPDATE v_agents SET state = 'held', held_by = ? WHERE name = ?", (event.data["by"], event.agent)
        )

    @fold("agent.released")
    def released(self, event: Event) -> None:
        self.db.execute(
            "UPDATE v_agents SET state = ?, held_by = NULL WHERE name = ?", (event.data["state"], event.agent)
        )

    @fold("agent.adopted")
    def adopted(self, event: Event) -> None:
        self.db.execute("UPDATE v_agents SET parent = NULL WHERE name = ?", (event.agent,))

    @fold("agent.finished")
    def finishing(self, event: Event) -> None:
        self.db.execute(
            "UPDATE v_agents SET finishing = 1, finish_gist = ?, finish_body = ?, finish_ref = ? WHERE name = ?",
            (event.data["gist"], event.data["body"], f"{event.stream}@{event.version}", event.agent),
        )

    @fold("agent.ended")
    def ended(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            """
            UPDATE v_agents SET state = 'ended', status = ?, reason = ?, held_by = NULL, unbegun = 0, finishing = 0
            WHERE name = ?
            """,
            (data["status"], data["reason"], event.agent),
        )
        if data["status"] == "finished":
            self.db.execute(
                "UPDATE v_agents SET final_gist = ?, final_body = ?, final_ref = ? WHERE name = ?",
                (data["report"], data["body"], f"{event.stream}@{event.version}", event.agent),
            )

    @fold("item.recorded")
    def item(self, event: Event) -> None:
        self.db.execute("UPDATE v_agents SET activity = ? WHERE name = ?", (event.gist, event.agent))
        if event.data["kind"] == "message":
            self.db.execute(
                "UPDATE v_agents SET final_gist = ?, final_body = ?, final_ref = ? WHERE name = ?",
                (event.gist, event.data["body"], f"{event.stream}@{event.version}", event.agent),
            )

    def _load(self, row: Any) -> Agent:
        fields = dict(row)
        fields |= {
            "harness": json.loads(row["harness"]),
            "boundaries": tuple(json.loads(row["boundaries"])),
            "levels": json.loads(row["levels"]),
            "workspace": row["workspace"] and Workspace.model_validate_json(row["workspace"]),
            "kept": row["kept"] and Kept.model_validate_json(row["kept"]),
        }
        return Agent(**fields)

    def get(self, name: str) -> Agent | None:
        row = self.db.execute("SELECT * FROM v_agents WHERE name = ?", (name,)).fetchone()
        return None if row is None else self._load(row)

    def listed(self) -> list[Agent]:
        return [self._load(row) for row in self.db.execute("SELECT * FROM v_agents ORDER BY name")]

    def live(self) -> list[Agent]:
        rows = self.db.execute("SELECT * FROM v_agents WHERE state != 'ended' ORDER BY name")
        return [self._load(row) for row in rows]

    def children(self, parent: str) -> list[Agent]:
        rows = self.db.execute("SELECT * FROM v_agents WHERE parent = ? AND state != 'ended' ORDER BY name", (parent,))
        return [self._load(row) for row in rows]

    def failing(self, handovers: int) -> list[Agent]:
        """Agents still spawning that an effect failed for, and those out of a turn past `handovers` failed in a row."""
        rows = self.db.execute(
            """
            SELECT * FROM v_agents
            WHERE (state = 'spawning' AND failure IS NOT NULL) OR (state IN ('idle', 'waiting') AND failures >= ?)
            ORDER BY name
            """,
            (handovers,),
        )
        return [self._load(row) for row in rows]

    def count_live(self) -> int:
        return self.db.execute("SELECT count(*) AS n FROM v_agents WHERE state != 'ended'").fetchone()["n"]
