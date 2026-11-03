"""A team in plain English: what `team show` prints. It reads the resolved form, so a preset and its expansion agree."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from .compile import reach
from .spec import Board, Group, Queue, Topic

if TYPE_CHECKING:
    from platoon_harness.team import Team

_WORDS = {
    "human": "you",
    "program": "the program",
    "all": "everyone",
    "next": "the next role",
    "prev": "the previous role",
}


_DELIVERY = {
    "pull": "Readers fetch it when they choose.",
    "next-turn": "Readers see it on their next turn.",
    "wake": "Each entry wakes its readers.",
    "steer": "Each entry steers its readers.",
}


def _join(items: Sequence[str]) -> str:
    return " and ".join(filter(None, (", ".join(items[:-1]), items[-1])))


def _plural(name: str) -> str:
    """A role in the plural. A name that is no plain word stays an identifier."""
    if not name.isalpha():
        return f"every {name}"
    if name.endswith("y") and name[-2:-1] not in "aeiou":
        return f"{name[:-1]}ies"
    return f"{name}es" if name.endswith(("s", "x", "ch", "sh")) else f"{name}s"


def _group(name: str, group: Group) -> str:
    if group.order:
        return f"+{name} runs {', then '.join(group.order)}."
    return f"+{name} is {_join([*(f'every {role}' for role in group.roles), *group.members])}."


class _Prose:
    def __init__(self, team: Team) -> None:
        self.team = team

    def many(self, role: str) -> bool:
        """Whether a role can have several agents, so that its name reads as a plural."""
        return role in self.team.roles and (bool(self.team.spawners(role)) or len(self.team.starts(role)) > 1)

    def noun(self, selector: str, subject: str = "") -> str:
        kind, _, name = selector.partition(":")
        its = "their" if self.many(subject) else "its"
        if kind == "role":
            return _plural(name) if self.many(name) else name
        if kind == "group":
            return f"+{name}"
        if selector == "self":
            return "themselves" if self.many(subject) else "itself"
        if selector == "parent":
            parents = sorted(reach(self.team, subject, "parent"))
            return " or ".join(parents) if parents and not any(map(self.many, parents)) else f"{its} parent"
        if selector == "children" and (children := sorted(reach(self.team, subject, "children") - {subject})):
            return f"{its} {_join([_plural(child) for child in children])}"
        return _WORDS.get(selector, f"{its} {selector}")

    def nouns(self, selectors: Iterable[str], subject: str = "") -> str:
        return _join([self.noun(selector, subject) for selector in selectors])

    def plural(self, selectors: tuple[str, ...]) -> bool:
        """Whether selectors take a plural verb."""
        first = selectors[0]
        return (
            len(selectors) > 1 or first == "human" or first.startswith("group:") or self.many(first.partition(":")[2])
        )

    def subject(self, selectors: tuple[str, ...]) -> str:
        """Selectors opening a sentence. A lone role name is an identifier, so it keeps its case."""
        text = self.nouns(selectors)
        lone = selectors[0].startswith("role:") and not self.many(selectors[0].partition(":")[2])
        return text if lone else text[0].upper() + text[1:]

    def closing(self, until: str) -> str:
        if until == "program":
            return "Closes when the program finishes."
        if until == "settled":
            return "Closes when the session settles."
        role = until.partition(":")[2]
        return f"Closes when every {role} has finished." if self.many(role) else f"Closes when {role} finishes."

    def role(self, name: str) -> str:
        role = self.team.roles[name]
        details = [role.harness if isinstance(role.harness, str) else role.harness.command[0]]
        if role.workspace != "shared":
            details.append(f"own {role.workspace}s" if self.many(name) else f"own {role.workspace}")
        edges = self.team.topology.edges
        selectors = sorted(
            {*edges.get(name, ()), *edges.get("all", ())}, key=lambda selector: (selector == "human", selector)
        )
        objects = self.nouns(selectors, name) if selectors else "no one"
        return f"{self.subject((f'role:{name}',))} ({', '.join(details)}) may message {objects}."

    def channel(self, name: str, channel: Topic | Queue | Board) -> str:
        writers = self.subject(channel.writers)
        readers = self.nouns(channel.readers)
        s = "" if self.plural(channel.writers) else "s"
        reader_s = "" if self.plural(channel.readers) else "s"
        if channel.writers == channel.readers:
            sentence = f"{writers} share{s} {channel.kind} `{name}`."
        elif channel.kind == "queue":
            sentence = f"{writers} add{s} to queue `{name}`; {readers} claim{reader_s} from it."
        elif channel.kind == "topic":
            sentence = f"{writers} post{s} to topic `{name}`; {readers} read{reader_s} it."
        else:
            sentence = f"{writers} write{s} board `{name}`; {readers} read{reader_s} it."
        if channel.delivery != type(channel).model_fields["delivery"].default:
            sentence += f" {_DELIVERY[channel.delivery]}"
        return sentence


def describe(team: Team) -> str:
    """One line on who may message whom, and one on everything shared."""
    topology = team.topology
    prose = _Prose(team)
    shared = [_group(name, group) for name, group in topology.groups.items()]
    shared += [
        prose.channel(name, channel)
        for kind in ("queue", "topic", "board")
        for name, channel in topology.channels.items()
        if channel.kind == kind
    ]
    limits = [f"{name.removeprefix('max_')} {value}" for name, value in topology.limits if value is not None]
    if limits:
        shared.append(f"Limits: {', '.join(limits)}.")
    shared += [f"{grant.who} may {grant.ops} on {grant.on}." for grant in topology.grants]
    if topology.program is not None:
        program = topology.program if isinstance(topology.program, str) else topology.program.name
        shared.append(f"Program `{program}` runs it.")
    shared.append(prose.closing(topology.until or "settled"))
    return f"{' '.join(map(prose.role, team.roles))}\n{' '.join(shared)}"
