"""A topology: who may reach whom, as grants over relations. It holds no control flow."""

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    JsonValue,
    PlainSerializer,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
    model_validator,
)

from platoon_harness.kernel import NAME, Grant
from platoon_harness.primitives import Injection
from platoon_harness.schema import ConfigError, Duration, Model, Name, Positive, Problem, Sorted, nearest

RELATIONS = ("self", "parent", "children", "siblings", "ancestors", "descendants", "next", "prev")
SELECTORS = (*RELATIONS, "human", "program", "all")


def _selector(text: str) -> str:
    kind, colon, name = text.partition(":")
    if text in SELECTORS or (colon and kind in ("role", "group") and name):
        return text
    raise ValueError(f"unknown selector `{text}`.{nearest(text, SELECTORS)} A role is `role:x` and a group `group:x`")


def _as_list(value: Any) -> Any:
    return [value] if isinstance(value, str) else value


def _unique(selectors: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(selectors)))


def _one_or_many(selectors: tuple[str, ...]) -> str | list[str]:
    return selectors[0] if len(selectors) == 1 else list(selectors)


def _normal_edges(edges: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    return {role: _unique(selectors) for role, selectors in sorted(edges.items()) if selectors}


def _normal_grants(grants: tuple[Grant, ...]) -> tuple[Grant, ...]:
    return tuple(sorted(set(grants), key=lambda grant: (grant.who, grant.ops, grant.on)))


Selector = Annotated[str, AfterValidator(_selector)]
Until = Annotated[str, StringConstraints(pattern=f"^(settled|program|role:{NAME})$")]
Member = Annotated[str, StringConstraints(pattern=f"^(agent|human|program|judge):{NAME}$")]
Selectors = Annotated[
    tuple[Selector, ...],
    BeforeValidator(_as_list),
    Field(min_length=1),
    AfterValidator(_unique),
    PlainSerializer(_one_or_many),
]
"""One selector or several: a lone one prints as a string, and order never matters."""


class _Channel(Model):
    kind: str
    writers: Selectors
    readers: Selectors

    @model_serializer(mode="wrap")
    def _keep_kind(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return {"kind": self.kind, **handler(self)}


class Topic(_Channel):
    """A log every reader follows by cursor."""

    kind: Literal["topic"] = "topic"
    delivery: Injection = "next-turn"
    history: Literal["from-join", "full"] = "from-join"
    coalesce: Duration | None = None


class Queue(_Channel):
    """Tasks leased to one claimant at a time. Unless `pull`, `delivery` announces work; it never assigns it."""

    kind: Literal["queue"] = "queue"
    delivery: Injection = "pull"
    lease: Duration | None = None
    lease_max: Duration | None = None
    max_attempts: Positive = 3
    max_inflight: Positive = 1


class Board(_Channel):
    """Named objects with immutable versions."""

    kind: Literal["board"] = "board"
    delivery: Injection = "pull"


Channel = Annotated[Topic | Queue | Board, Field(discriminator="kind")]


class Group(Model):
    """A named membership rule: some roles, some principals, or roles in an order that `next` and `prev` walk."""

    roles: tuple[Name, ...] = ()
    members: tuple[Member, ...] = ()
    order: tuple[Name, ...] = ()

    @model_validator(mode="after")
    def _one_rule(self) -> Self:
        if sum(map(bool, (self.roles, self.members, self.order))) != 1:
            raise ValueError("a group is exactly one of `roles`, `members` or `order`")
        return self


class Limits(Model):
    """Bounds on the live graph, and on how far a chain of messages may run."""

    max_depth: Positive | None = None
    max_children: Positive | None = None
    max_live: Positive | None = None
    max_hops: Positive | None = None


class Program(Model):
    """A named episode program with arguments. One with no arguments is just its name."""

    name: Name
    params: Annotated[Mapping[str, JsonValue], Field(min_length=1)]


class Unexpanded(Model):
    """A preset table no known definition could expand yet, because an extension must supply one."""

    preset: str
    params: Mapping[str, JsonValue] = {}


class Topology(Model):
    """What may happen: a set of fragments merged by union. Presets make fragments; `a | b` mixes them."""

    until: Until | None = None
    program: Name | Program | None = None
    edges: Annotated[
        Mapping[Name, Annotated[tuple[Selector, ...], BeforeValidator(_as_list)]], AfterValidator(_normal_edges)
    ] = {}
    groups: Annotated[Mapping[Name, Group], Sorted] = {}
    channels: Annotated[Mapping[Name, Channel], Sorted] = {}
    limits: Limits = Limits()
    grants: Annotated[tuple[Grant, ...], AfterValidator(_normal_grants)] = ()
    unexpanded: tuple[Unexpanded, ...] = ()

    def __or__(self, other: "Topology") -> "Topology":
        return union([("the left side", self), ("the right side", other)])

    @property
    def hash(self) -> str:
        """The sha256 of the resolved form, which no order of mixing can change."""
        if self.unexpanded:
            raise ConfigError([Problem("topology", "unexpanded presets have no hash yet")])
        return sha256(json.dumps(self.canonical(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def union(parts: Iterable[tuple[str, Topology]]) -> Topology:
    """Merge named fragments. Edges and grants add up; anything defined twice must be defined alike."""
    tables: defaultdict[str, dict[str, Any]] = defaultdict(dict)
    sources: dict[tuple[str, str], str] = {}
    problems: list[Problem] = []

    def define(table: str, key: str, value: Any, source: str) -> None:
        if value is None:
            return
        first = sources.setdefault((table, key), source)
        if tables[table].setdefault(key, value) != value:
            where = ".".join(filter(None, ("topology", table, key)))
            problems.append(Problem(where, f"defined differently by {first} and {source}"))

    edges: defaultdict[str, set[str]] = defaultdict(set)
    grants: set[Grant] = set()
    unexpanded: dict[str, Unexpanded] = {}
    for source, part in parts:
        for role, selectors in part.edges.items():
            edges[role].update(selectors)
        grants.update(part.grants)
        unexpanded.update((json.dumps(item.canonical(), sort_keys=True), item) for item in part.unexpanded)
        for name, channel in part.channels.items():
            define("channels", name, channel, source)
        for name, group in part.groups.items():
            define("groups", name, group, source)
        for name, value in part.limits:
            define("limits", name, value, source)
        define("", "until", part.until, source)
        define("", "program", part.program, source)
    if problems:
        raise ConfigError(problems)
    return Topology(
        **tables[""],
        edges={role: tuple(selectors) for role, selectors in edges.items()},
        groups=tables["groups"],
        channels=tables["channels"],
        limits=Limits(**tables["limits"]),
        grants=tuple(grants),
        unexpanded=tuple(item for _, item in sorted(unexpanded.items())),
    )
