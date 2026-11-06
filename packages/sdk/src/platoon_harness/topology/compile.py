"""Compilation: a team to its one `(who, ops, on)` table, which is all `authorize` reads."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import TYPE_CHECKING

from platoon_harness.kernel import Grant
from platoon_harness.primitives import WAKING, channel_grants
from platoon_harness.schema import ConfigError, Problem, nearest

from .spec import RELATIONS, Group, Topology

if TYPE_CHECKING:
    from platoon_harness.team import Role, Team

_RELATION = re.compile(r"\{([^{}]+)\}")
_TREE = ("parent", "children", "ancestors", "descendants")
_BASE = (
    Grant(who="all", ops="ops.list"),
    Grant(who="human", ops="*"),
    Grant(who="program", ops="*"),
    Grant(who="agent", ops="agent.finish"),
    Grant(who="agent", ops="blob.*"),
    Grant(who="agent", ops="channel.list"),
    Grant(who="agent", ops="message.read", on="inbox/{self}"),
    Grant(who="agent", ops="repo.commit"),
    Grant(who="agent", ops="session.status"),
    Grant(who="agent", ops="wait", on="inbox/{self}"),
    Grant(who="agent", ops="wait.*"),
)


def _neighbors(groups: Mapping[str, Group], role: str, step: int) -> Iterator[str]:
    for group in groups.values():
        for index, name in enumerate(group.order):
            if name == role and 0 <= index + step < len(group.order):
                yield group.order[index + step]


def _for_kernel(topology: Topology, role: str, selector: str) -> tuple[str, ...]:
    """What `authorize` can evaluate in place of `selector`: groups and orders become their roles."""
    kind, _, name = selector.partition(":")
    if kind == "group":
        group = topology.groups[name]
        return (*(f"role:{member}" for member in (*group.roles, *group.order)), *group.members)
    if selector in ("next", "prev"):
        return tuple(f"role:{name}" for name in _neighbors(topology.groups, role, 1 if selector == "next" else -1))
    return (selector,)


def _inbox(target: str) -> str:
    """A selector as an inbox pattern, or one principal's inbox when `target` names it outright."""
    kind, colon, name = target.partition(":")
    return f"inbox/{name}" if colon and kind != "role" else f"inbox/{{{target}}}"


def compile(team: Team) -> tuple[Grant, ...]:
    """The grant table of a resolved team, sorted. Humans and programs hold every op; an agent holds what is listed."""
    if problems := structure(team):
        raise ConfigError(problems)
    topology = team.topology
    grants = {*_BASE, *topology.grants}

    for role, selectors in topology.edges.items():
        who = "all" if role == "all" else f"role:{role}"
        grants |= {Grant(who=who, ops="peers"), Grant(who=who, ops="channel.create")}
        for selector in selectors:
            for target in _for_kernel(topology, role, selector):
                grants.add(Grant(who=who, ops="message.send", on=_inbox(target)))
            if selector.startswith("group:"):
                grants.add(Grant(who=who, ops="message.send", on=f"channel/+{selector.partition(':')[2]}"))

    for name in topology.groups:
        for who in _for_kernel(topology, "", f"group:{name}"):
            grants |= {
                Grant(who=who, ops="message.send", on=f"channel/+{name}"),
                Grant(who=who, ops="message.read", on=f"channel/+{name}"),
                Grant(who=who, ops="wait", on=f"channel/+{name}"),
                Grant(who=who, ops="wait", on=f"group/{name}"),
            }

    for name, channel in topology.channels.items():
        for selectors, write in ((channel.writers, True), (channel.readers, False)):
            for who in (who for selector in selectors for who in _for_kernel(topology, "", selector)):
                grants |= {
                    Grant(who=who, ops=ops, on=on) for ops, on in channel_grants(channel.kind, name, write=write)
                }

    for name, role in team.roles.items():
        who = f"role:{name}"
        grants |= {Grant(who=who, ops="agent.spawn", on=f"role/{child}") for child in role.may_spawn}
        if role.may_spawn:
            grants |= {
                Grant(who=who, ops=ops, on="agent/{descendants}")
                for ops in ("agent.interrupt", "agent.cancel", "agent.retire", "agent.status", "wait")
            }

    return tuple(sorted(grants, key=lambda grant: (grant.who, grant.ops, grant.on)))


def scopes(role: Role) -> tuple[str, ...]:
    """A token's scopes: the role's op globs, always with `ops.list`, which every surface derives from."""
    return tuple(sorted({*role.tools, "ops.list"}))


def reach(team: Team, role: str, selector: str) -> set[str]:
    """What `selector` can name from `role`, as far as config alone can tell: roles, `human` and `program`."""

    def children(name: str) -> set[str]:
        return {*team.roles[name].may_spawn} if name in team.roles else set()

    def closure(step: Callable[[str], set[str]]) -> set[str]:
        found: set[str] = set()
        frontier = step(role)
        while frontier - found:
            found |= frontier
            frontier = {name for member in frontier for name in step(member)}
        return found

    kind, _, name = selector.partition(":")
    match selector:
        case "self":
            return {role}
        case "parent":
            return team.spawners(role)
        case "children":
            return children(role)
        case "siblings":
            return {sibling for parent in team.spawners(role) for sibling in children(parent)}
        case "ancestors":
            return closure(team.spawners)
        case "descendants":
            return closure(children)
        case "human" | "program":
            return {selector}
        case "all":
            return {*team.roles, "human", "program"}
        case "next" | "prev":
            return set(_neighbors(team.topology.groups, role, 1 if selector == "next" else -1))
    if kind == "role":
        return {name}
    if kind == "group" and name in team.topology.groups:
        group = team.topology.groups[name]
        return {*group.roles, *group.order}
    return set()


def arcs(team: Team, *, wakes: bool = False) -> dict[str, list[str]]:
    """Who can pass anything to whom, by role. With `wakes`, only what starts a turn and is no reply up a tree."""
    found: dict[str, set[str]] = {name: set() for name in team.roles}

    def link(senders: Iterable[str], targets: set[str]) -> None:
        for sender in found.keys() & set(senders):
            found[sender] |= targets

    def wakes_on_message(name: str) -> bool:
        return name in team.roles and team.roles[name].delivery in WAKING

    for role, selectors in team.topology.edges.items():
        for sender in team.roles if role == "all" else (role,):
            for selector in selectors:
                if not wakes:
                    link((sender,), reach(team, sender, selector))
                elif selector not in _TREE:
                    link((sender,), set(filter(wakes_on_message, reach(team, sender, selector))))
    for channel in team.topology.channels.values():
        if not wakes or channel.delivery in WAKING:
            readers = {name for selector in channel.readers for name in reach(team, "", selector)}
            link({name for selector in channel.writers for name in reach(team, "", selector)}, readers)
    if not wakes:
        for name, role in team.roles.items():
            link((name,), {*role.may_spawn})
            link(role.may_spawn, {name})
    return {name: sorted(targets) for name, targets in found.items()}


def structure(team: Team) -> list[Problem]:
    """What stops a team compiling: names that resolve to nothing, and selectors with nothing to be relative to."""
    topology = team.topology
    roles = set(team.roles)
    problems: list[Problem] = []

    def role_exists(where: str, name: str) -> None:
        if name not in roles:
            problems.append(Problem(where, f"unknown role `{name}`.{nearest(name, roles)}"))

    def selector_resolves(where: str, selector: str, *, relative: bool) -> None:
        kind, _, name = selector.partition(":")
        if kind == "role":
            role_exists(where, name)
        elif kind == "group" and name not in topology.groups:
            problems.append(Problem(where, f"unknown group `{name}`.{nearest(name, topology.groups.keys())}"))
        elif selector in RELATIONS and not relative:
            what = f"`{selector}` needs an agent to be relative to, and a channel in a team has none"
            problems.append(Problem(where, what))

    for item in topology.unexpanded:
        problems.append(Problem(f"topology.{item.preset}", "not resolved: this preset waits for an extension"))
    for name, role in team.roles.items():
        for child in role.may_spawn:
            role_exists(f"roles.{name}.may_spawn", child)
    for name, group in topology.groups.items():
        for role in (*group.roles, *group.order):
            role_exists(f"topology.groups.{name}", role)
    for role, selectors in topology.edges.items():
        where = f"topology.edges.{role}"
        if role != "all":
            role_exists("topology.edges", role)
        for selector in selectors:
            selector_resolves(where, selector, relative=True)
            if selector in ("next", "prev") and not any(role in group.order for group in topology.groups.values()):
                problems.append(Problem(where, f"`{selector}` needs a group with `order` holding `{role}`"))
    for name, channel in topology.channels.items():
        for field in ("writers", "readers"):
            for selector in getattr(channel, field):
                selector_resolves(f"topology.channels.{name}.{field}", selector, relative=False)
    for grant in topology.grants:
        for relation in _RELATION.findall(grant.on):
            if relation in ("next", "prev") or relation.startswith("group:"):
                what = f"`{relation}` in a written grant has no evaluator: use `edges`, or name the roles"
                problems.append(Problem("topology.grants", what))
    if topology.until and topology.until.startswith("role:"):
        role_exists("topology.until", topology.until.partition(":")[2])
    if topology.until == "program" and topology.program is None:
        problems.append(Problem("topology.until", "`program` needs a `program` to wait for"))
    return problems
