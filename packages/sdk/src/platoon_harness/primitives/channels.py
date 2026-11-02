"""Channels and groups: durable named places, who may use them, and who is in them."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from platoon_harness.kernel import Args, Event, Grants, Principals, Refused, Stamps, Txn, View, fold, op

from .common import WAKING, Delivery, Name

_PREFIX = {"topic": "channel", "queue": "queue", "board": "board"}
_DEFAULT_DELIVERY: dict[str, Delivery] = {"topic": "next-turn", "queue": "pull", "board": "pull"}
_WRITE = {"topic": ("message.send",), "queue": ("task.add", "task.list"), "board": ("board.post", "board.revise")}
_READ = {
    "topic": ("message.read",),
    "queue": ("task.claim", "task.renew", "task.release", "task.complete", "task.fail", "task.list"),
    "board": ("board.get", "board.query"),
}
_ON = {"topic": "channel/{}", "queue": "queue/{}", "board": "board/{}/*"}
_RULES = ("all", "human", "program")


class Channel(BaseModel, frozen=True):
    """Settings on the reader's side, so a sender cannot buy a wake. A queue's or board's objects sit under `stream`."""

    stream: str
    kind: Literal["inbox", "topic", "queue", "board"]
    delivery: Delivery = "pull"
    history: Literal["from-join", "full"] = "from-join"
    coalesce: float = 0.0
    depth: int | None = None
    lease: float = 1800.0
    lease_max: float | None = None
    max_inflight: int = 1
    max_attempts: int = 3


class Channels(View):
    """Every channel. An agent's inbox is one, made at spawn from its role."""

    schema = "CREATE TABLE v_channels(stream TEXT PRIMARY KEY, settings TEXT NOT NULL) WITHOUT ROWID, STRICT;"

    @fold("channel.created")
    def created(self, event: Event) -> None:
        self.db.execute("INSERT INTO v_channels VALUES (?, ?)", (event.data["stream"], json.dumps(event.data)))

    @fold("agent.spawned")
    def inbox(self, event: Event) -> None:
        stream = f"inbox/{event.agent}"
        settings = Channel(
            stream=stream, kind="inbox", delivery=event.data["delivery"], depth=event.data["inbox_depth"]
        )
        self.db.execute("INSERT INTO v_channels VALUES (?, ?)", (stream, settings.model_dump_json()))

    def get(self, stream: str) -> Channel | None:
        row = self.db.execute("SELECT settings FROM v_channels WHERE stream = ?", (stream,)).fetchone()
        return None if row is None else Channel.model_validate_json(row["settings"])

    def require(self, stream: str) -> Channel:
        channel = self.get(stream)
        if channel is None:
            raise Refused("not_found", f"no channel {stream}")
        return channel

    def listed(self) -> list[Channel]:
        rows = self.db.execute("SELECT settings FROM v_channels ORDER BY stream")
        return [Channel.model_validate_json(row["settings"]) for row in rows]


class Group(BaseModel, frozen=True):
    """A membership rule, by role or by named principal, and the agents it holds now, sorted."""

    name: str
    roles: tuple[str, ...]
    named: tuple[str, ...]
    members: tuple[str, ...] = ()

    def takes(self, role: str | None, agent: str) -> bool:
        return role in self.roles or f"agent:{agent}" in self.named


class Groups(View):
    """Named membership rules. A group's generation is the version of its stream."""

    schema = """
    CREATE TABLE v_groups(name TEXT PRIMARY KEY, rule TEXT NOT NULL) WITHOUT ROWID, STRICT;
    """

    @fold("group.changed")
    def changed(self, event: Event) -> None:
        self.db.execute("INSERT OR REPLACE INTO v_groups VALUES (?, ?)", (event.data["name"], json.dumps(event.data)))

    def get(self, name: str) -> Group:
        row = self.db.execute("SELECT rule FROM v_groups WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise Refused("not_found", f"no group {name}")
        return Group.model_validate_json(row["rule"])

    def listed(self) -> list[Group]:
        return [
            Group.model_validate_json(row["rule"]) for row in self.db.execute("SELECT rule FROM v_groups ORDER BY name")
        ]


def _change(txn: Txn, group: Group, members: list[str]) -> None:
    data = group.model_copy(update={"members": tuple(sorted(members))})
    txn.emit("group.changed", f"group/{group.name}", gist=f"group {group.name} changed", data=data)


def regroup(txn: Txn, agent: str, role: str, *, joined: bool) -> None:
    """Journal a membership change, which moves a group's generation. Spawn does this on success only."""
    for group in txn.view(Groups).listed():
        rest = [member for member in group.members if member != agent]
        members = [*rest, agent] if joined and group.takes(role, agent) else rest
        if sorted(members) != sorted(group.members):
            _change(txn, group, members)


class CreateChannel(Args):
    name: Name
    kind: Literal["topic", "queue", "board"]
    readers: tuple[str, ...] = ()
    writers: tuple[str, ...] = ()
    delivery: Delivery | None = None
    history: Literal["from-join", "full"] = "from-join"
    coalesce: Annotated[float, Field(ge=0)] = 0.0
    lease: Annotated[float, Field(gt=0)] = 1800.0
    lease_max: Annotated[float, Field(gt=0)] | None = None
    max_inflight: Annotated[int, Field(ge=1)] = 1
    max_attempts: Annotated[int, Field(ge=1)] = 3


def _reach(txn: Txn, selector: str) -> None:
    """A creator may name only readers and writers it could reach itself."""
    grants = txn.view(Grants)
    for principal in txn.view(Principals).select(txn.me, selector):
        if principal.id != txn.me.id and not grants.permits(txn.me, "message.send", f"inbox/{principal.name}"):
            raise Refused("not_permitted", f"{selector} covers {principal.id}, beyond your reach")


def _grantees(txn: Txn, selector: str) -> list[str]:
    """Whom a selector grants to: a rule stays one, and a relation names today's holders, as `who` has no relations."""
    if selector in _RULES or selector.startswith("role:"):
        return [selector]
    return [principal.id for principal in txn.view(Principals).select(txn.me, selector)]


def _grant(txn: Txn, name: str, kind: str, selectors: tuple[str, ...], verbs: dict[str, tuple[str, ...]]) -> None:
    for selector in selectors:
        for who in _grantees(txn, selector):
            for ops in verbs[kind]:
                data = {"who": who, "ops": ops, "on": _ON[kind].format(name)}
                txn.emit("grant.added", "topology", gist=f"{who} may {ops} on {name}", data=data)


@op("channel.create", on=lambda a: f"{_PREFIX[a.kind]}/{a.name}", tool=True)
def create(txn: Txn, a: CreateChannel) -> dict[str, Any]:
    """Create a topic, queue or board. `readers` and `writers` are selectors such as `children` or `role:x`, within
    your own reach. Refused `not_permitted` past it, and `conflict` when the name is taken: choose another."""
    stream = f"{_PREFIX[a.kind]}/{a.name}"
    if txn.view(Channels).get(stream) is not None:
        raise Refused("conflict", f"{stream} exists")
    for selector in (*a.readers, *a.writers):
        _reach(txn, selector)
    delivery = a.delivery or _DEFAULT_DELIVERY[a.kind]
    if txn.me.kind == "agent" and delivery in WAKING:
        raise Refused("not_permitted", "an agent cannot buy a wake: delivery is the reader's setting")
    settings = Channel(
        **a.model_dump(include={"kind", "history", "coalesce", "lease", "lease_max", "max_inflight", "max_attempts"}),
        stream=stream,
        delivery=delivery,
    )
    _grant(txn, a.name, a.kind, a.readers, _READ)
    _grant(txn, a.name, a.kind, a.writers, _WRITE)
    txn.emit("channel.created", "topology", gist=f"{a.kind} {a.name} created", data=settings)
    return {"stream": stream}


@op("channel.list", query=True, tool=True)
def list_channels(txn: Txn, a: Args) -> list[dict[str, Any]]:
    """List the channels you may read or write."""
    grants = txn.view(Grants)

    def usable(channel: Channel) -> bool:
        target = f"{channel.stream}/*" if channel.kind == "board" else channel.stream
        verbs = (*_READ.get(channel.kind, ("message.read",)), *_WRITE.get(channel.kind, ("message.send",)))
        return any(grants.permits(txn.me, verb, target) for verb in verbs)

    return [
        {"stream": c.stream, "kind": c.kind} for c in txn.view(Channels).listed() if c.kind != "inbox" and usable(c)
    ]


class DefineGroup(Args):
    name: Name
    roles: tuple[Name, ...] = ()
    members: tuple[str, ...] = ()
    delivery: Delivery = "next-turn"
    history: Literal["from-join", "full"] = "from-join"
    coalesce: Annotated[float, Field(ge=0)] = 0.0


@op("group.define", on=lambda a: f"group/{a.name}", runtime=True)
def define_group(txn: Txn, a: DefineGroup) -> None:
    """Define a group and its implicit topic. Its first members are the live agents the rule takes."""
    stream = f"channel/+{a.name}"
    if txn.view(Stamps).version_of(f"group/{a.name}") > 0:
        raise Refused("conflict", f"group {a.name} exists")
    settings = Channel(stream=stream, kind="topic", delivery=a.delivery, history=a.history, coalesce=a.coalesce)
    txn.emit("channel.created", "topology", gist=f"group {a.name} created", data=settings)
    group = Group(name=a.name, roles=a.roles, named=a.members)
    live = txn.view(Principals).select(txn.me, "all")
    _change(txn, group, [p.name for p in live if p.kind == "agent" and group.takes(p.role, p.name)])
