"""A team: roles plus a topology, as a file or a Python object."""

import graphlib
import math
import tomllib
from collections.abc import Iterable, Mapping
from fnmatch import fnmatchcase
from typing import Annotated, Any, Literal, Self

from pydantic import Field, StrictFloat, StrictInt, StringConstraints, ValidationError, field_validator, model_validator

from platoon_harness.kernel import Extension
from platoon_harness.primitives import WAKING, Capabilities, Injection, Policy
from platoon_harness.schema import (
    ConfigError,
    Duration,
    Model,
    Name,
    Positive,
    Problem,
    Sorted,
    dumps,
    nearest,
    problems_in,
)
from platoon_harness.topology.compile import arcs, reach, structure
from platoon_harness.topology.presets import PRESETS, Preset, expand, finish, preset_name
from platoon_harness.topology.show import describe
from platoon_harness.topology.spec import RELATIONS, Topology

_FAN_OUT = 8
_MEASURED = ("tokens", "usd")
_UNENFORCED = frozenset({"digest", "entry", "keys", "requires", "validator"})

EnvName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]

__all__ = [
    "AuthProfile",
    "Budget",
    "Capabilities",
    "Command",
    "Role",
    "Team",
    "team_check",
]


class Budget(Model):
    """Limits on a session or a role. `fallback` says what stands in for a unit a harness cannot measure."""

    tokens: Positive | None = None
    usd: Annotated[StrictInt | StrictFloat, Field(gt=0, allow_inf_nan=False)] | None = None
    turns: Positive | None = None
    agents: Positive | None = None
    wall: Duration | None = None
    fallback: Literal["turns"] | None = None


class AuthProfile(Model):
    """Which environment variables a harness receives. Names only: a value never enters configuration."""

    env: tuple[EnvName, ...]


class Command(Model):
    """A harness given as a command line: a `oneshot` CLI run by the `exec` driver, or a `wire` driver program."""

    command: Annotated[tuple[str, ...], Field(min_length=1)]
    mode: Literal["oneshot", "wire"] = "oneshot"


class Role(Model):
    """A template for agents. `tools` lists op globs, and only ever narrows what the topology grants.

    `count` is how many start with the session: left out, one, or none if another role spawns this one. `delivery` is
    how a message reaches this role's inboxes, and `inbox_depth` how many entries one holds before refusing more.
    """

    harness: str | Command
    model: str | None = None
    instructions: str | None = None
    auth: str | None = None
    workspace: Literal["shared", "worktree", "snapshot", "isolated"] = "shared"
    sandbox: str | None = None
    tools: tuple[str, ...] = ("*",)
    delivery: Injection = "wake"
    inbox_depth: Positive = 1024
    may_spawn: tuple[str, ...] = ()
    count: Annotated[StrictInt, Field(ge=0)] | None = None
    on_parent_exit: Literal["cancel-subtree", "adopt"] = "cancel-subtree"
    approvals: Policy = "ask"
    budget: Budget = Budget()

    @property
    def driver(self) -> str:
        """The name this role's harness goes by among drivers."""
        if isinstance(self.harness, str):
            return self.harness
        return "exec" if self.harness.mode == "oneshot" else "wire"


class Team(Model):
    """Roles plus a topology. It says what may happen, never what happens next."""

    extensions: tuple[str, ...] = ()
    roles: Annotated[Mapping[Name, Role], Field(min_length=1), Sorted]
    auth: Annotated[Mapping[Name, AuthProfile], Sorted] = {}
    budget: Budget = Budget()
    topology: Topology = Topology()

    @field_validator("topology", mode="before")
    @classmethod
    def _expand_presets(cls, value: Any) -> Any:
        return expand(value) if isinstance(value, Mapping) else value

    @model_validator(mode="after")
    def _knows_every_preset(self) -> Self:
        """With no extension to supply one, a preset nobody knows is a mistake now, and no wait."""
        if not self.extensions and (problems := finish(self.topology, {})[1]):
            raise ConfigError(problems)
        return self

    @classmethod
    def loads(cls, text: str) -> Self:
        """A team from TOML text alone. `load_team` layers one over the user's and project's config."""
        try:
            return cls.model_validate(tomllib.loads(text))
        except tomllib.TOMLDecodeError as error:
            raise ConfigError([Problem("team", f"not TOML: {error}")]) from error
        except ValidationError as error:
            raise ConfigError(problems_in(error, cls)) from None

    def spawners(self, role: str) -> set[str]:
        """The roles that may spawn `role`."""
        return {name for name, other in self.roles.items() if role in other.may_spawn}

    def starts(self, role: str) -> int:
        """How many agents of `role` start with the session."""
        count = self.roles[role].count
        if count is not None:
            return count
        return 0 if self.spawners(role) - {role} else 1

    def resolved(self, extensions: Mapping[str, Extension] | None = None) -> Self:
        """This team with every preset expanded, using the extensions it names from `extensions`."""
        presets, problems = _presets_of(self, {} if extensions is None else extensions)
        topology, more = finish(self.topology, presets)
        if problems + more:
            raise ConfigError(problems + more)
        return self.model_copy(update={"topology": topology})

    def show(self, *, resolved: bool = False) -> str:
        """English sentences, or with `resolved` the TOML expansion, which is valid input."""
        if self.topology.unexpanded:
            names = ", ".join(item.preset for item in self.topology.unexpanded)
            raise ConfigError([Problem("topology", f"not resolved: {names} waits for an extension")])
        return dumps(self.canonical()) if resolved else describe(self)


def _presets_of(team: Team, extensions: Mapping[str, Extension]) -> tuple[dict[str, Preset], list[Problem]]:
    """The presets of the extensions `team` names. Installing activates nothing."""
    presets: dict[str, Preset] = {}
    problems: list[Problem] = []
    for reference in team.extensions:
        try:
            extension = extensions[reference]
        except ConfigError as error:
            problems.extend(error.problems)
            continue
        except KeyError:
            problems.append(
                Problem("extensions", f"unknown extension `{reference}`.{nearest(reference, [*extensions])}")
            )
            continue
        for preset in extension.presets:
            name = preset_name(preset)
            if name in presets or name in PRESETS or name in Topology.model_fields:
                problems.append(Problem(f"extensions.{extension.name}", f"preset `{name}` is defined twice"))
            presets[name] = preset
    return presets, problems


def _cycle(arcs: Mapping[str, Iterable[str]]) -> list[str] | None:
    try:
        graphlib.TopologicalSorter(arcs).prepare()
    except graphlib.CycleError as error:
        return error.args[1]
    return None


def _budget_problems(budget: Budget, where: str, role: Role, capabilities: Capabilities) -> Iterable[Problem]:
    for unit in _MEASURED:
        if getattr(budget, unit) is None or unit in capabilities.measures:
            continue
        if budget.fallback is None:
            what = f'`{role.driver}` cannot measure {unit}. Remove the limit, or set `fallback = "turns"`'
            yield Problem(f"{where}.{unit}", what)
        elif budget.turns is None:
            yield Problem(f"{where}.{unit}", "falls back to turns, but this budget has no `turns` limit")


def _population(team: Team, role: str) -> float:
    """The most agents a role can have at once, which is infinite when nothing bounds it."""
    return (team.topology.limits.max_live or math.inf) if team.spawners(role) else team.starts(role)


def _spawning(team: Team) -> dict[str, set[str]]:
    """Who may spawn whom, by role: `may_spawn`, and any written grant of `agent.spawn`, which is the same thing."""
    found = {name: {*role.may_spawn} for name, role in team.roles.items()}
    for grant in team.topology.grants:
        if fnmatchcase("agent.spawn", grant.ops):
            spawners = (
                found.keys() if grant.who in ("agent", "all") else found.keys() & {grant.who.removeprefix("role:")}
            )
            for name in spawners:
                found[name] |= {role for role in team.roles if fnmatchcase(f"role/{role}", grant.on)}
    return found


def _warnings(team: Team) -> Iterable[Problem]:
    starting = {name for name in team.roles if team.starts(name)}
    started = starting.union(*(reach(team, name, "descendants") for name in starting))
    for name in sorted(team.roles.keys() - started):
        yield Problem(f"roles.{name}", "never starts: its count is 0 and nothing that starts can spawn it", "warning")

    if len(team.roles) > 1:
        for name, targets in arcs(team).items():
            if not set(targets) - {name}:
                yield Problem(f"roles.{name}", "has no path to anyone", "warning")

    for role, selectors in team.topology.edges.items():
        for name in team.roles if role == "all" else (role,):
            for selector in selectors:
                if selector in RELATIONS and not reach(team, name, selector):
                    what = f"`{selector}` reaches nobody: relations come from `may_spawn`, and none makes this one true"
                    yield Problem(f"topology.edges.{role}", what, "warning")

    if (program := team.topology.program) is not None:
        name = program if isinstance(program, str) else program.name
        yield Problem("topology.program", f"`{name}` cannot run yet: no program can be resolved", "warning")

    for name, channel in team.topology.channels.items():
        if channel.delivery in WAKING:
            readers = {role for selector in channel.readers for role in reach(team, "", selector)}
            fan_out = sum(_population(team, role) for role in readers & team.roles.keys())
            if fan_out > _FAN_OUT:
                how_many = "an unbounded number of" if fan_out == math.inf else fan_out
                what = f"each entry can wake {how_many} agents. Prefer `next-turn`, or `coalesce` the wakes"
                yield Problem(f"topology.channels.{name}.delivery", what, "warning")
        for field in sorted(_UNENFORCED & channel.canonical().keys()):
            yield Problem(f"topology.channels.{name}.{field}", "recorded, but nothing enforces it yet", "warning")


def team_check(
    team: Team, *, capabilities: Mapping[str, Capabilities], extensions: Mapping[str, Extension] | None = None
) -> tuple[Problem, ...]:
    """Every problem with a team, at once, before any cost. Pure: all it knows arrives as arguments.

    `capabilities` maps harness names, or a role's own name where its command decides, to what is known of them, and
    `extensions` maps the references a team may name to their extensions. Errors stop a team from running; warnings do
    not.
    """
    presets, problems = _presets_of(team, {} if extensions is None else extensions)
    topology, more = finish(team.topology, presets)
    problems += more
    team = team.model_copy(update={"topology": topology})
    limits = topology.limits
    problems += structure(team)

    for name, role in team.roles.items():
        known = capabilities.get(name) or capabilities.get(role.driver)
        if known is None:
            what = f"unknown harness `{role.driver}`.{nearest(role.driver, capabilities.keys())}"
            problems.append(Problem(f"roles.{name}.harness", what))
        else:
            if role.sandbox is not None and role.sandbox not in known.sandboxes:
                what = f"`{role.driver}` has no sandbox `{role.sandbox}`.{nearest(role.sandbox, known.sandboxes)}"
                problems.append(Problem(f"roles.{name}.sandbox", what))
            problems += _budget_problems(team.budget, "budget", role, known)
            problems += _budget_problems(role.budget, f"roles.{name}.budget", role, known)
        if role.auth is not None and role.auth not in team.auth:
            problems.append(Problem(f"roles.{name}.auth", f"unknown profile.{nearest(role.auth, team.auth.keys())}"))

    if limits.max_depth is None and (cycle := _cycle(_spawning(team))):
        what = f"recursive may_spawn with no limit: {' -> '.join(cycle)}"
        problems.append(Problem("topology.limits.max_depth", what))
    if limits.max_hops is None and (cycle := _cycle(arcs(team, wakes=True))):
        problems.append(Problem("topology.limits.max_hops", f"a wake cycle with no limit: {' -> '.join(cycle)}"))

    problems += _warnings(team)
    return tuple(problems)
