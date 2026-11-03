"""Budgets: limits, reservations, and what each turn turned out to cost."""

import json
from typing import Annotated, Any, Literal, NamedTuple, get_args

from pydantic import Field

from platoon_harness.kernel import NAME, Args, Event, Refused, Stamps, Timer, Txn, View, fold, op

Unit = Literal["tokens", "usd", "turns", "agents", "wall"]
Label = Literal["provider", "estimated", "lower_bound", "unavailable"]

_FROM_BEST = ("counted", *get_args(Label))
_METERED = ("tokens", "usd")


def _weaker(one: str, other: str) -> str:
    return max(one, other, key=_FROM_BEST.index)


class _Scope(NamedTuple):
    limits: dict[str, float]
    estimate: dict[str, float]
    fallback: str | None
    since: float


class Budgets(View):
    """Limits per scope, `shared` or `role:x`. Spending is also kept per `agent:x`, for the roster."""

    schema = """
    CREATE TABLE v_budgets(
        scope TEXT PRIMARY KEY,
        limits TEXT NOT NULL,
        estimate TEXT NOT NULL,
        fallback TEXT,
        since REAL NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_budgets_spent(
        scope TEXT NOT NULL,
        unit TEXT NOT NULL,
        amount REAL NOT NULL,
        label TEXT NOT NULL,
        unmeasured INTEGER NOT NULL,
        PRIMARY KEY (scope, unit)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_budgets_reserved(
        agent TEXT NOT NULL,
        unit TEXT NOT NULL,
        role TEXT NOT NULL,
        amount REAL NOT NULL,
        waking INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (agent, unit)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_budgets_turn(
        agent TEXT NOT NULL,
        unit TEXT NOT NULL,
        amount REAL NOT NULL,
        label TEXT NOT NULL,
        PRIMARY KEY (agent, unit)
    ) WITHOUT ROWID, STRICT;
    """

    @fold("budget.set")
    def limits_set(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "INSERT OR REPLACE INTO v_budgets VALUES (?, ?, ?, ?, ?)",
            (
                data["scope"],
                json.dumps(data["limits"]),
                json.dumps(data["estimate"]),
                data["fallback"],
                event.wall_time,
            ),
        )

    @fold("budget.reserved")
    def reserved(self, event: Event) -> None:
        role = event.data["role"]
        for unit, amount in event.data["amounts"].items():
            self.db.execute(
                "INSERT INTO v_budgets_reserved(agent, unit, role, amount) VALUES (?, ?, ?, ?) "
                "ON CONFLICT DO UPDATE SET amount = max(amount, excluded.amount)",
                (event.agent, unit, role, amount),
            )

    @fold("agent.woken", "turn.started")
    def turn_coming(self, event: Event) -> None:
        """A reservation is a wake's until its turn starts, and only a wake's can come back when a handover fails."""
        waking = event.type == "agent.woken"
        self.db.execute("UPDATE v_budgets_reserved SET waking = ? WHERE agent = ?", (waking, event.agent))

    @fold("usage.reported")
    def usage(self, event: Event) -> None:
        for unit in _METERED:
            if (amount := event.data[unit]) is not None or event.data["label"] == "unavailable":
                self._seen(event.agent, unit, amount or 0.0, event.data["label"])

    def _seen(self, agent: str | None, unit: str, amount: float, label: str) -> None:
        row = self.db.execute("SELECT label FROM v_budgets_turn WHERE agent = ? AND unit = ?", (agent, unit)).fetchone()
        label = _weaker(label, row["label"]) if row else label
        self.db.execute(
            "INSERT INTO v_budgets_turn VALUES (?, ?, ?, ?) "
            "ON CONFLICT DO UPDATE SET amount = amount + excluded.amount, label = excluded.label",
            (agent, unit, amount, label),
        )

    @fold("budget.reconciled")
    def reconciled(self, event: Event) -> None:
        for charge in event.data["charges"]:
            self._charge(event.data["role"], event.agent, **charge)
        self.db.execute("DELETE FROM v_budgets_reserved WHERE agent = ? AND unit != 'agents'", (event.agent,))
        self.db.execute("DELETE FROM v_budgets_turn WHERE agent = ?", (event.agent,))

    @fold("agent.started")
    def started(self, event: Event) -> None:
        row = self.db.execute(
            "SELECT role, amount FROM v_budgets_reserved WHERE agent = ? AND unit = 'agents'", (event.agent,)
        ).fetchone()
        if row is not None:
            self._charge(row["role"], event.agent, "agents", row["amount"], "counted")
            self.db.execute("DELETE FROM v_budgets_reserved WHERE agent = ? AND unit = 'agents'", (event.agent,))

    @fold("turn.lost")
    def lost(self, event: Event) -> None:
        """A lost turn's cost is unknown, so its estimate stands, and it counts as unmeasured even with no estimate."""
        rows = self.db.execute(
            "SELECT * FROM v_budgets_reserved WHERE agent = ? AND unit != 'agents'", (event.agent,)
        ).fetchall()
        held = {row["unit"]: row["amount"] for row in rows}
        for role in {row["role"] for row in rows}:
            for unit in _METERED:
                self._charge(role, event.agent, unit, held.pop(unit, 0.0), "unavailable", 1)
            for unit, amount in held.items():
                self._charge(role, event.agent, unit, amount, "counted")
        self.db.execute("DELETE FROM v_budgets_reserved WHERE agent = ? AND unit != 'agents'", (event.agent,))
        self.db.execute("DELETE FROM v_budgets_turn WHERE agent = ?", (event.agent,))

    @fold("effect.failed")
    def wake_failed(self, event: Event) -> None:
        if event.data["kind"] == "deliver":
            self.db.execute(
                "DELETE FROM v_budgets_reserved WHERE agent = ? AND unit != 'agents' AND waking = 1", (event.agent,)
            )

    @fold("agent.ended")
    def ended(self, event: Event) -> None:
        self.db.execute("DELETE FROM v_budgets_reserved WHERE agent = ?", (event.agent,))
        self.db.execute("DELETE FROM v_budgets_turn WHERE agent = ?", (event.agent,))

    def _charge(self, role: str, agent: str | None, unit: str, amount: float, label: str, unmeasured: int = 0) -> None:
        for scope in ("shared", f"role:{role}", f"agent:{agent}"):
            row = self.db.execute(
                "SELECT label FROM v_budgets_spent WHERE scope = ? AND unit = ?", (scope, unit)
            ).fetchone()
            self.db.execute(
                "INSERT INTO v_budgets_spent VALUES (?, ?, ?, ?, ?) ON CONFLICT DO UPDATE SET "
                "amount = amount + excluded.amount, label = excluded.label, "
                "unmeasured = unmeasured + excluded.unmeasured",
                (scope, unit, amount, _weaker(label, row["label"]) if row else label, unmeasured),
            )

    def _scope(self, scope: str) -> _Scope | None:
        row = self.db.execute("SELECT * FROM v_budgets WHERE scope = ?", (scope,)).fetchone()
        if row is None:
            return None
        return _Scope(json.loads(row["limits"]), json.loads(row["estimate"]), row["fallback"], row["since"])

    def spent(self, scope: str, unit: str) -> tuple[float, str, int]:
        """The amount spent, its weakest label, and how many turns went unmeasured."""
        row = self.db.execute("SELECT * FROM v_budgets_spent WHERE scope = ? AND unit = ?", (scope, unit)).fetchone()
        return (0.0, "counted", 0) if row is None else (row["amount"], row["label"], row["unmeasured"])

    def held(self, scope: str, unit: str) -> float:
        """What is reserved in a scope and not yet reconciled."""
        role = scope.removeprefix("role:")
        row = self.db.execute(
            "SELECT coalesce(sum(amount), 0) AS held FROM v_budgets_reserved "
            "WHERE unit = ? AND (? = 'shared' OR role = ?)",
            (unit, scope, role),
        ).fetchone()
        return row["held"]

    def reservation(self, agent: str) -> dict[str, float]:
        rows = self.db.execute("SELECT unit, amount FROM v_budgets_reserved WHERE agent = ?", (agent,))
        return {row["unit"]: row["amount"] for row in rows}

    def turn_usage(self, agent: str) -> dict[str, tuple[float, str]]:
        rows = self.db.execute("SELECT * FROM v_budgets_turn WHERE agent = ?", (agent,))
        return {row["unit"]: (row["amount"], row["label"]) for row in rows}

    def estimate(self, role: str) -> dict[str, float]:
        """One turn's estimate. A role's own overrides the shared one."""
        shared, own = self._scope("shared"), self._scope(f"role:{role}")
        return {**(shared.estimate if shared else {}), **(own.estimate if own else {})}

    def _past_wall(self, found: _Scope, limit: float, now: float) -> bool:
        return now - found.since >= limit

    def _check_limit(self, scope: str, found: _Scope, unit: str, limit: float, want: float, now: float) -> None:
        if unit == "wall":
            if self._past_wall(found, limit, now):
                raise Refused("over_budget", {"scope": scope, "unit": unit, "limit": limit})
            return
        spent, _, unmeasured = self.spent(scope, unit)
        if unmeasured and found.fallback == "turns":
            return
        if unmeasured:
            raise Refused("unavailable", f"{unmeasured} turns of {unit} went unmeasured, so {scope} cannot hold")
        held = self.held(scope, unit)
        if spent >= limit or spent + held + want > limit:
            raise Refused("over_budget", {"scope": scope, "unit": unit, "limit": limit, "spent": spent, "held": held})

    def check(self, role: str, wanted: dict[str, float], now: float) -> None:
        """Refuse `over_budget` past a limit, and `unavailable` when a limit's unit cannot be measured."""
        for scope in ("shared", f"role:{role}"):
            if (found := self._scope(scope)) is not None:
                for unit, limit in found.limits.items():
                    self._check_limit(scope, found, unit, limit, wanted.get(unit, 0.0), now)

    def exhausted(self, now: float) -> bool:
        """Whether the shared budget has run out, which stops every kind of session. A reservation spends nothing."""
        found = self._scope("shared")
        if found is None:
            return False
        return any(
            self._past_wall(found, limit, now) if unit == "wall" else self.spent("shared", unit)[0] >= limit
            for unit, limit in found.limits.items()
        )

    def status(self) -> list[dict[str, Any]]:
        scopes = self.db.execute("SELECT scope FROM v_budgets ORDER BY scope").fetchall()
        rows = []
        for scope in (row["scope"] for row in scopes):
            found = self._scope(scope)
            assert found is not None
            for unit, limit in found.limits.items():
                spent, label, unmeasured = self.spent(scope, unit)
                rows.append(
                    {
                        "scope": scope,
                        "unit": unit,
                        "limit": limit,
                        "spent": spent,
                        "held": self.held(scope, unit),
                        "label": label,
                        "unmeasured": unmeasured,
                    }
                )
        return rows

    def usage_of(self, scope: str) -> dict[str, dict[str, Any]]:
        """What `shared` or one `agent:x` has spent, with labels: a unit nobody measured has no amount. The row may hold
        an estimate, which the budget charges and nobody may read as a measurement."""
        rows = self.db.execute("SELECT * FROM v_budgets_spent WHERE scope = ? AND unit != 'agents'", (scope,))
        return {
            row["unit"]: {"amount": None if row["label"] == "unavailable" else row["amount"], "label": row["label"]}
            for row in rows
        }


def reserve(txn: Txn, agent: str, role: str, *, turn: bool = True, **extra: float) -> None:
    """Hold what `extra` names, and one turn's estimate if a turn is coming, against every limit, or refuse. An agent
    holds one turn's, since it runs one at a time, so what it holds already goes toward this."""
    budget = txn.view(Budgets)
    amounts = {**(budget.estimate(role) | {"turns": 1.0} if turn else {}), **extra}
    held = budget.reservation(agent)
    budget.check(role, {unit: amount - held.get(unit, 0.0) for unit, amount in amounts.items()}, txn.now)
    data = {"role": role, "amounts": amounts}
    txn.emit("budget.reserved", f"budget/agent:{agent}", gist=f"{agent} reserved", agent=agent, data=data)


def reconcile(txn: Txn, agent: str, role: str) -> None:
    """Turn end: charge what was measured and return the rest. A unit not measured whole is charged its estimate, or
    what was measured, whichever is more, since what was measured was spent."""
    budget = txn.view(Budgets)
    held, seen = budget.reservation(agent), budget.turn_usage(agent)
    held.pop("agents", None)
    if not held and not seen:
        return
    charges = []
    for unit in _METERED:
        amount, label = seen.get(unit, (0.0, "unavailable"))
        unmeasured = label == "unavailable"
        charges.append(
            {
                "unit": unit,
                "amount": max(amount, held.get(unit, 0.0)) if unmeasured else amount,
                "label": label,
                "unmeasured": int(unmeasured),
            }
        )
    if "turns" in held:
        charges.append({"unit": "turns", "amount": 1.0, "label": "counted", "unmeasured": 0})
    data = {"role": role, "charges": charges}
    txn.emit("budget.reconciled", f"budget/agent:{agent}", gist=f"{agent} reconciled", agent=agent, data=data)


class SetBudget(Args):
    scope: Annotated[str, Field(pattern=rf"^(shared|role:{NAME})$")] = "shared"
    limits: dict[Unit, Annotated[float, Field(gt=0, strict=False)]] = {}
    estimate: dict[Literal["tokens", "usd"], Annotated[float, Field(ge=0, strict=False)]] = {}
    fallback: Literal["turns"] | None = None


@op("budget.set", on=lambda a: f"budget/{a.scope}")
def set_budget(txn: Txn, a: SetBudget) -> None:
    """Set a scope's limits and turn estimate. `fallback` lets `turns` stand in for what a role cannot measure."""
    if a.fallback == "turns" and "turns" not in a.limits:
        raise Refused("invalid", "a fallback to turns needs a turns limit, or nothing would be enforced")
    stream = f"budget/{a.scope}"
    txn.emit("budget.set", stream, gist=f"budget set for {a.scope}", data=a)
    if a.scope == "shared" and "wall" in a.limits:
        key = f"{stream}/{txn.view(Stamps).version_of(stream)}"
        timer = Timer(due=txn.now + a.limits["wall"], op="budget.lapse", args={}, key=key)
        txn.emit("timer.set", f"timer/{key}", gist=f"timer {key} set", data=timer)


@op("budget.lapse", on=lambda a: "budget/shared", runtime=True)
def lapse(txn: Txn, a: Args) -> None:
    """Fired by a timer: the shared wall clock ran out. Time passing alone exhausts a budget, and only this tells anyone
    who sleeps until the journal moves."""
    if txn.view(Budgets).exhausted(txn.now):
        txn.emit("budget.lapsed", "budget/shared", gist="the wall budget ran out")


@op("budget.status", query=True)
def budget_status(txn: Txn, a: Args) -> list[dict[str, Any]]:
    """Each limit with what is spent, held, and how well that is known."""
    return txn.view(Budgets).status()
