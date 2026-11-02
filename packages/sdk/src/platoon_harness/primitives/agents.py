"""The agent record: one row per agent, kept for good, because retiring leaves the team and never the journal."""

import json
from typing import Any, Literal

from pydantic import BaseModel

from platoon_harness.kernel import Event, View, fold

from .reports import OWNER_STOP

AgentState = Literal["spawning", "idle", "waking", "running", "waiting", "held", "ended"]


class Agent(BaseModel, frozen=True):
    """One agent. `parent` is the spawner's principal id, and `None` once adopted by the session. `native` is the id
    its harness resumes by, when it gave one. `unbegun` says it was given a goal and no turn has begun on it.
    `finishing` says it called `agent.finish` in a turn that has not ended. `stopped` is why its last turn ended, until
    the next begins. `cut_off` is what cut its last turn short, until it has been told. `failure` is what the last
    effect to fail for it said, `failures` counts handovers failed in a row, and the next waits until `retry_at`."""

    name: str
    role: str
    parent: str | None
    depth: int
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
    finishing: bool
    finish_gist: str | None
    finish_body: str | None
    stopped: str | None
    cut_off: str | None
    failure: str | None
    failures: int
    retry_at: float
    levels: dict[str, Any]

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

    schema = """
    CREATE TABLE v_agents(
        name TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        parent TEXT,
        depth INTEGER NOT NULL,
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
        finishing INTEGER NOT NULL DEFAULT 0,
        finish_gist TEXT,
        finish_body TEXT,
        stopped TEXT,
        cut_off TEXT,
        failure TEXT,
        failures INTEGER NOT NULL DEFAULT 0,
        retry_at REAL NOT NULL DEFAULT 0,
        levels TEXT NOT NULL DEFAULT '{}'
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_agents_parent ON v_agents(parent);
    CREATE INDEX v_agents_state ON v_agents(state);
    """

    @fold("agent.spawned")
    def spawned(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            """
            INSERT INTO v_agents(
                name, role, parent, depth, state, harness, model, on_parent_exit, boundaries, goal, goal_body, unbegun
            ) VALUES (
                :name, :role, :parent, :depth, 'spawning', :harness, :model, :on_parent_exit, '[]', :goal, :body,
                :unbegun
            )
            """,
            {**data, "harness": json.dumps(data["harness"]), "unbegun": bool(data["goal"] or data["body"])},
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

    @fold("effect.finished")
    def launched(self, event: Event) -> None:
        """A driver may name its session only in what `start` returned, which reaches the journal here."""
        result = event.data["result"]
        if event.data["kind"] == "launch" and isinstance(result, dict):
            self.db.execute(
                "UPDATE v_agents SET native = coalesce(?, native) WHERE name = ?", (result.get("native"), event.agent)
            )

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
            "UPDATE v_agents SET unbegun = 0, final_gist = NULL, final_body = NULL, stopped = NULL WHERE name = ?",
            (event.agent,),
        )

    @fold("turn.ended", "turn.lost")
    def stopped(self, event: Event) -> None:
        self._move(event, "idle", "running", "waking")
        self._reachable(event)
        reason = "lost" if event.type == "turn.lost" else event.data["reason"]
        self.db.execute("UPDATE v_agents SET stopped = ? WHERE name = ?", (reason, event.agent))

    def _cut_off(self, event: Event, cause: str) -> None:
        self.db.execute("UPDATE v_agents SET cut_off = ? WHERE name = ?", (cause, event.agent))

    @fold("turn.lost")
    def crashed(self, event: Event) -> None:
        self._cut_off(event, "a crash")

    @fold("turn.ended")
    def stopped_by_its_owner(self, event: Event) -> None:
        if event.data["reason"] == OWNER_STOP:
            self._cut_off(event, "the owner stopping the session")

    @fold("agent.told")
    def told(self, event: Event) -> None:
        self.db.execute("UPDATE v_agents SET cut_off = NULL WHERE name = ?", (event.agent,))

    @fold("agent.woken")
    def woken(self, event: Event) -> None:
        self._move(event, "waking", "idle", "waiting")

    @fold("effect.failed")
    def failed(self, event: Event) -> None:
        """A failed handover gives back its wake, and the next waits twice as long as the last."""
        self.db.execute("UPDATE v_agents SET failure = ? WHERE name = ?", (event.data["error"], event.agent))
        if event.data["kind"] == "deliver":
            self._move(event, "idle", "waking")
            self.db.execute(
                "UPDATE v_agents SET failures = failures + 1, retry_at = ? + (1 << failures) WHERE name = ?",
                (event.wall_time, event.agent),
            )

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
            "UPDATE v_agents SET finishing = 1, finish_gist = ?, finish_body = ? WHERE name = ?",
            (event.data["gist"], event.data["body"], event.agent),
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
                "UPDATE v_agents SET final_gist = ?, final_body = ? WHERE name = ?",
                (data["report"], data["body"], event.agent),
            )

    @fold("item.recorded")
    def item(self, event: Event) -> None:
        self.db.execute("UPDATE v_agents SET activity = ? WHERE name = ?", (event.gist, event.agent))
        if event.data["kind"] == "message":
            self.db.execute(
                "UPDATE v_agents SET final_gist = ?, final_body = ? WHERE name = ?",
                (event.gist, event.data["body"], event.agent),
            )

    def _load(self, row: Any) -> Agent:
        fields = dict(row)
        fields |= {
            "harness": json.loads(row["harness"]),
            "boundaries": tuple(json.loads(row["boundaries"])),
            "levels": json.loads(row["levels"]),
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
