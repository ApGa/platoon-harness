"""The session record: what was resolved at open, journaled, and the state the session is in."""

import json
from typing import Annotated, Any, Literal

from pydantic import Field, JsonValue

from platoon_harness.kernel import Args, Event, Refused, Stamps, Txn, View, fold, op

from .common import BodyRef, Delivery, Name


class Role(Args):
    """What a spawn reads from a role. `approvals` is the policy for this role's requests."""

    harness: JsonValue = None
    model: str | None = None
    workspace: str = "shared"
    tools: tuple[str, ...] = ("*",)
    on_parent_exit: Literal["cancel-subtree", "adopt"] = "cancel-subtree"
    approvals: Literal["ask", "deny", "allow"] = "ask"
    delivery: Delivery = "wake"
    inbox_depth: Annotated[int, Field(ge=1)] = 1024


class Limits(Args):
    """Bounds on the live graph and on how far a chain of messages may run."""

    max_depth: int | None = None
    max_children: int | None = None
    max_live: int | None = None
    max_hops: int | None = None


class Settings(Args):
    """What a session states at open. `manifest` is a stored body."""

    roles: dict[Name, Role] = {}
    limits: Limits = Limits()
    until: Annotated[str, Field(pattern=r"^(settled|program|role:[\w.-]+)$")] = "settled"
    manifest: BodyRef | None = None


class Session(View):
    """One row, once the session is open."""

    schema = """
    CREATE TABLE v_session(id INTEGER PRIMARY KEY CHECK (id = 1), state TEXT NOT NULL, settings TEXT NOT NULL) STRICT;
    """

    @fold("session.opened")
    def opened(self, event: Event) -> None:
        self.db.execute("INSERT INTO v_session VALUES (1, 'open', ?)", (json.dumps(event.data),))

    @fold("session.closed", "session.cancelled", "session.stopped")
    def moved(self, event: Event) -> None:
        state = event.type.removeprefix("session.")
        self.db.execute("UPDATE v_session SET state = ?", ({"closed": "closing"}.get(state, state),))

    def state(self) -> str:
        row = self.db.execute("SELECT state FROM v_session").fetchone()
        return "unopened" if row is None else row["state"]

    def settings(self) -> Settings:
        row = self.db.execute("SELECT settings FROM v_session").fetchone()
        return Settings() if row is None else Settings.model_validate_json(row["settings"])

    def accepting(self) -> bool:
        """Whether new work may start. A session that is closing only drains."""
        return self.state() in ("unopened", "open")


@op("session.open", runtime=True)
def open_session(txn: Txn, a: Settings) -> None:
    """Journal what this session runs under, before its first turn."""
    if txn.view(Session).state() != "unopened":
        raise Refused("conflict", "this session is open")
    txn.emit("session.opened", "session", gist="session opened", data=a, refs=[a.manifest] if a.manifest else ())


@op("session.manifest", query=True)
def show_manifest(txn: Txn, a: Args) -> dict[str, Any]:
    """Name the stored manifest of this session, which holds no secrets."""
    return {"manifest": txn.view(Session).settings().manifest}


class OpenEpisode(Args):
    episode: Name


class CloseEpisode(Args):
    outcome: dict[str, JsonValue] = {}


@op("episode.open", on=lambda a: f"episode/{a.episode}")
def open_episode(txn: Txn, a: OpenEpisode) -> None:
    """Open a span of this session with one outcome. Only events inside one can become training data."""
    txn.emit("episode.opened", f"episode/{a.episode}", gist=f"episode {a.episode} opened", data=a)


@op("episode.close")
def close_episode(txn: Txn, a: CloseEpisode) -> None:
    """Close the open episode, or refuse `conflict` when none is open."""
    episode = txn.view(Stamps).episode()
    if episode is None:
        raise Refused("conflict", "no episode is open")
    data = {"episode": episode, "outcome": a.outcome}
    txn.emit("episode.closed", f"episode/{episode}", gist=f"episode {episode} closed", data=data)
