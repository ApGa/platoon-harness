"""Channels and groups: durable named places, who may use them, and who is in them."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema

from platoon_harness.kernel import Args, Event, Grants, Principals, Refused, Stamps, Txn, View, fold, op

from .common import WAKING, Injection, Name, Paging, paged

_PREFIX = {"topic": "channel", "queue": "queue", "board": "board"}
_DEFAULT_DELIVERY: dict[str, Injection] = {"topic": "next-turn", "queue": "pull", "board": "pull"}
_WRITE = {"topic": ("message.send",), "queue": ("task.add", "task.list"), "board": ("board.post", "board.revise")}
_READ = {
    "topic": ("message.read",),
    "queue": ("task.claim", "task.renew", "task.release", "task.complete", "task.fail", "task.list"),
    "board": ("board.get", "board.query"),
}
_ON = {"topic": "channel/{}", "queue": "queue/{}", "board": "board/{}/*"}
_WATCHED = {"topic": "channel/{}", "queue": "task/{}/*", "board": "board/{}/*"}
_RULES = ("all", "human", "program")


def channel_grants(kind: str, name: str, *, write: bool) -> list[tuple[str, str]]:
    """The `(ops, on)` pairs that writing or reading one channel takes. Whoever reads a channel may wait on it, and
    whoever adds to a queue may wait on its tasks."""
    pairs = [(ops, _ON[kind].format(name)) for ops in (_WRITE if write else _READ)[kind]]
    return [*pairs, ("wait", _WATCHED[kind].format(name))] if not write or kind == "queue" else pairs


class Channel(BaseModel, frozen=True):
    """Settings on the reader's side, so an agent cannot buy a wake, and a person's message to an agent steers whatever
    they say. A queue's or board's objects sit under `stream`."""

    stream: str
    kind: Literal["inbox", "topic", "queue", "board"]
    delivery: Injection = "pull"
    history: Literal["from-join", "full"] = "from-join"
    coalesce: float = 0.0
    depth: int | None = None
    lease: float = 1800.0
    lease_max: float | None = None
    max_inflight: int = 1
    max_attempts: int = 3

    @property
    def object(self) -> str:
        """What grants on this channel name: a board's objects sit under its stream."""
        return f"{self.stream}/*" if self.kind == "board" else self.stream

    @property
    def reading(self) -> str:
        """The op that makes someone a reader of this channel."""
        return _READ[self.kind][0]

    @property
    def address(self) -> str:
        """What the ops that use this channel take: `#topic`, `+group`, or a queue's or board's bare name."""
        name = self.stream.partition("/")[2]
        return name if self.kind != "topic" or name.startswith("+") else f"#{name}"


class Channels(View):
    """Every channel. An agent's inbox is one, made at spawn from its role."""

    schema = "CREATE TABLE v_channels(stream TEXT PRIMARY KEY, settings TEXT NOT NULL) WITHOUT ROWID, STRICT;"

    @fold("channel.created")
    def created(self, event: Event) -> None:
        self.db.execute("INSERT INTO v_channels VALUES (?, ?)", (event.data["stream"], json.dumps(event.data)))

    @fold("agent.spawned")
    def inbox(self, event: Event) -> None:
        """A spawn is its spawner's event, so the child is the one it names."""
        stream = f"inbox/{event.data['name']}"
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
    # A surface shows what a model decides. The settings it leaves out are for a person, a program or a team file.

    name: Annotated[Name, Field(description="A name no channel of this kind has.")]
    kind: Annotated[Literal["topic", "queue", "board"], Field(description="What sort of channel this is.")]
    readers: Annotated[tuple[str, ...], Field(description="Who else may read: selectors, such as `children`.")] = ()
    writers: Annotated[tuple[str, ...], Field(description="Who else may write: selectors, such as `role:x`.")] = ()
    delivery: Annotated[Injection | None, Field(description="`pull` or `next-turn`, the most you may choose.")] = None
    history: SkipJsonSchema[Literal["from-join", "full"]] = "from-join"
    coalesce: SkipJsonSchema[Annotated[float, Field(ge=0)]] = 0.0
    lease: SkipJsonSchema[Annotated[float, Field(gt=0)]] = 1800.0
    lease_max: SkipJsonSchema[Annotated[float, Field(gt=0)] | None] = None
    max_inflight: SkipJsonSchema[Annotated[int, Field(ge=1)]] = 1
    max_attempts: SkipJsonSchema[Annotated[int, Field(ge=1)]] = 3


def _within_reach(txn: Txn, selector: str) -> None:
    """A creator may name only readers and writers it could reach itself."""
    grants = txn.view(Grants)
    covered = txn.view(Principals).select(txn.me, selector)
    if txn.me.kind == "agent" and not covered:
        raise Refused("invalid", f"`{selector}` covers nobody yet")
    for principal in covered:
        if principal.id != txn.me.id and not grants.permits(txn.me, "message.send", f"inbox/{principal.name}"):
            raise Refused("not_permitted", f"`{selector}` reaches beyond you")


def _grantees(txn: Txn, selector: str) -> list[str]:
    """Whom a selector grants to. A person's or program's rule stays one. An agent's names only those it was just found
    to reach, since a rule would go on to cover agents past its reach, and `who` has no relations."""
    if txn.me.kind != "agent" and (selector in _RULES or selector.startswith("role:")):
        return [selector]
    return [principal.id for principal in txn.view(Principals).select(txn.me, selector)]


def _grant(txn: Txn, name: str, kind: str, selectors: tuple[str, ...], *, write: bool) -> None:
    for selector in selectors:
        for who in _grantees(txn, selector):
            for ops, on in channel_grants(kind, name, write=write):
                data = {"who": who, "ops": ops, "on": on}
                txn.emit("grant.added", "topology", gist=f"{who} may {ops} on {name}", data=data)


@op("channel.create", on=lambda a: f"{_PREFIX[a.kind]}/{a.name}", tool=True)
def create(txn: Txn, a: CreateChannel) -> dict[str, Any]:
    """Create a topic, queue or board that you can read and write. `readers` and `writers` add others: each selector
    means those it covers now, so a later arrival is not among them. Refused `not_permitted` when one reaches beyond
    you, or for `wake` or `steer`, which belong to the reader: use `next-turn`. `invalid` when one covers nobody yet.
    `conflict` when the name is taken: choose another."""
    stream = f"{_PREFIX[a.kind]}/{a.name}"
    if txn.view(Channels).get(stream) is not None:
        raise Refused("conflict", f"{stream} exists")
    for selector in (*a.readers, *a.writers):
        _within_reach(txn, selector)
    delivery = a.delivery or _DEFAULT_DELIVERY[a.kind]
    if txn.me.kind == "agent" and delivery in WAKING:
        raise Refused("not_permitted", "an agent cannot buy a wake: delivery is the reader's setting")
    settings = Channel(
        **a.model_dump(include={"kind", "history", "coalesce", "lease", "lease_max", "max_inflight", "max_attempts"}),
        stream=stream,
        delivery=delivery,
    )
    mine = ("self",) if txn.me.kind == "agent" else ()
    _grant(txn, a.name, a.kind, (*mine, *a.readers), write=False)
    _grant(txn, a.name, a.kind, (*mine, *a.writers), write=True)
    txn.emit("channel.created", "topology", gist=f"{a.kind} {a.name} created", data=settings)
    return {"name": settings.address, "kind": a.kind}


@op("channel.list", query=True, tool=True)
def list_channels(txn: Txn, a: Paging) -> dict[str, Any]:
    """List the channels you may use, in `channels`, with the true `total` and a `cursor` to pass as `after`, or none at
    the end. Pass `name` as `to` or `channel` for a topic, `queue` for a queue, `board` for a board."""
    grants = txn.view(Grants)

    def usable(channel: Channel) -> bool:
        return any(
            grants.permits(txn.me, verb, channel.object) for verb in (*_READ[channel.kind], *_WRITE[channel.kind])
        )

    rows = [{"name": c.address, "kind": c.kind} for c in txn.view(Channels).listed() if c.kind != "inbox" and usable(c)]
    return paged(rows, "channels", "name", a.after)


class DefineGroup(Args):
    name: Name
    roles: tuple[Name, ...] = ()
    members: tuple[str, ...] = ()
    delivery: Injection = "next-turn"
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
