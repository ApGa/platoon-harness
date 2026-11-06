"""A team: roles plus a topology, as a file or a Python object."""

import graphlib
import math
import tomllib
from collections.abc import Iterable, Mapping
from fnmatch import fnmatchcase
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from platoon_harness.kernel import Extension
from platoon_harness.primitives import PRIMITIVES, WAKING, Capabilities, Injection, Policy
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
from platoon_harness.tools import PREAMBLE, slots
from platoon_harness.tools.surface import OP_NAMED
from platoon_harness.topology.compile import arcs, compile, reach, scopes, structure
from platoon_harness.topology.presets import PRESETS, Preset, expand, finish, preset_name
from platoon_harness.topology.show import describe
from platoon_harness.topology.spec import RELATIONS, Topology

_FAN_OUT = 8
_MEASURED = ("tokens", "usd")

EnvName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]


def _template(text: str) -> str:
    slots(text)
    return text


Template = Annotated[str, AfterValidator(_template)]
"""A preamble template, whose every slot is one the runtime fills."""

__all__ = [
    "AuthProfile",
    "Budget",
    "Capabilities",
    "Command",
    "Role",
    "Team",
    "Test",
    "team_check",
    "trainable_problems",
]


Amount = Annotated[StrictInt | StrictFloat, Field(gt=0, allow_inf_nan=False)]


class Budget(Model):
    """Limits on a session or a role. `estimate` is what one turn is reserved in `tokens` or `usd` before it is
    measured, and charged on top of what was measured when nobody measured it whole, so a limit in either needs one."""

    tokens: Positive | None = None
    usd: Amount | None = None
    turns: Positive | None = None
    agents: Positive | None = None
    wall: Duration | None = None
    estimate: Annotated[Mapping[Literal["tokens", "usd"], Amount], Sorted] = {}


class AuthProfile(Model):
    """Which environment variables a harness receives. Names only: a value never enters configuration."""

    env: tuple[EnvName, ...]


class Command(Model):
    """A harness given as a command line: a `oneshot` CLI run by the `exec` driver, or a `wire` driver program."""

    command: Annotated[tuple[str, ...], Field(min_length=1)]
    mode: Literal["oneshot", "wire"] = "oneshot"


class Test(Model):
    """What the runtime runs at a recorded commit when a person or a program asks: `command`, in a clean detached
    checkout of that commit, as you and unconfined, ended at `timeout`, which is then an error and not a failure."""

    command: Annotated[tuple[str, ...], Field(min_length=1)]
    timeout: Duration


class Role(Model):
    """A template for agents. `tools` lists op globs, and only ever narrows what the topology grants.

    `count` is how many start with the session: left out, one, or none if another role spawns this one. `delivery` is
    how a message reaches this role's inboxes, and `inbox_depth` how many entries one holds before refusing more.
    `effort` goes to the harness as it stands, and a harness that cannot honor it fails the spawn. `stays` says whether
    an agent is told to stay after its task for the next message, rather than to finish, which one that does not stay
    does with a turn that leaves nothing more to come for it: left out, one the session started stays and one spawned
    does not, and a spawn may say otherwise either way. `on_parent_exit` says what becomes
    of an agent whose parent ends: `cancel-subtree` ends it too, `cancelled` if a turn of its was cut off and `retired`
    otherwise, and `adopt` gives it to the session. `allow_native_children` lets its harness start agents of its own,
    beside ours. `preamble` is the template of what its agents are told before `instructions`, its own words, in place
    of the team's.
    """

    harness: str | Command
    model: str | None = None
    effort: str | None = None
    preamble: Template | None = None
    instructions: str | None = None
    auth: str | None = None
    workspace: Literal["shared", "worktree", "snapshot", "isolated"] = "shared"
    sandbox: str | None = None
    allow_native_children: StrictBool = False
    tools: tuple[str, ...] = ("*",)
    delivery: Injection = "wake"
    inbox_depth: Positive = 1024
    may_spawn: tuple[str, ...] = ()
    count: Annotated[StrictInt, Field(ge=0)] | None = None
    stays: StrictBool | None = None
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
    """Roles plus a topology. It says what may happen, never what happens next. `preamble` is the template of what every
    agent is told before its role's words, unless its role gives its own. `test` is what a runtime test of a commit
    runs, if the team names one."""

    extensions: tuple[str, ...] = ()
    preamble: Template = PREAMBLE
    roles: Annotated[Mapping[Name, Role], Field(min_length=1), Sorted]
    auth: Annotated[Mapping[Name, AuthProfile], Sorted] = {}
    budget: Budget = Budget()
    topology: Topology = Topology()
    test: Test | None = None

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
        """The roles that may spawn `role`, by `may_spawn` or by a written grant, which is the same thing."""
        return {name for name, children in _spawning(self).items() if role in children}

    def starts(self, role: str) -> list[str]:
        """The agents of `role` that start with the session: one by the role's name, or a numbered one for each of
        its `count`."""
        count = self.roles[role].count
        if count is None:
            count = 0 if self.spawners(role) - {role} else 1
        return [role] if count == 1 else [f"{role}-{number}" for number in range(1, count + 1)]

    def recipients(self, to: str | None = None) -> tuple[str, ...]:
        """Whom a session's prompt goes to, as `@agent`: the agent `to` names, which the session must start, or else
        every agent it starts."""
        started = tuple(f"@{agent}" for role in self.roles for agent in self.starts(role))
        if to is None:
            return started
        if to not in started:
            what = f"{to} is no agent this session starts: it starts {', '.join(started) or 'none'}"
            raise ConfigError([Problem("to", what)])
        return (to,)

    def preamble_of(self, role: str) -> str:
        """The template of what `role`'s agents are told before its words: its own, else the team's."""
        own = self.roles[role].preamble
        return self.preamble if own is None else own

    def resolved(self, extensions: Mapping[str, Extension] | None = None) -> Self:
        """This team with every preset expanded, using the extensions it names from `extensions`."""
        loaded, problems = _extensions_of(self, {} if extensions is None else extensions)
        presets, named = _presets_of(loaded)
        topology, more = finish(self.topology, presets)
        if problems + named + more:
            raise ConfigError(problems + named + more)
        return self.model_copy(update={"topology": topology})

    def show(self, *, resolved: bool = False) -> str:
        """English sentences, or with `resolved` the TOML expansion, which is valid input."""
        if self.topology.unexpanded:
            names = ", ".join(item.preset for item in self.topology.unexpanded)
            raise ConfigError([Problem("topology", f"not resolved: {names} waits for an extension")])
        return dumps(self.canonical()) if resolved else describe(self)


def _extensions_of(team: Team, extensions: Mapping[str, Extension]) -> tuple[list[Extension], list[Problem]]:
    """The extensions `team` names. Installing activates nothing."""
    loaded: list[Extension] = []
    problems: list[Problem] = []
    for reference in team.extensions:
        try:
            loaded.append(extensions[reference])
        except ConfigError as error:
            problems.extend(error.problems)
        except KeyError:
            problems.append(
                Problem("extensions", f"unknown extension `{reference}`.{nearest(reference, [*extensions])}")
            )
    return loaded, problems


def _presets_of(loaded: Iterable[Extension]) -> tuple[dict[str, Preset], list[Problem]]:
    presets: dict[str, Preset] = {}
    problems: list[Problem] = []
    for extension in loaded:
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


def _unestimated(budget: Budget, where: str, shared: Budget | None = None) -> Iterable[Problem]:
    """A limit in a unit a turn can go unmeasured in needs an amount to charge such a turn, or it could hold on none. A
    role's limit takes the shared estimate where the role has none, as a reservation does."""
    estimate = {**(shared.estimate if shared else {}), **budget.estimate}
    for unit in _MEASURED:
        if getattr(budget, unit) is not None and unit not in estimate:
            what = f"a {unit} limit needs `estimate.{unit}`: what a turn nobody measured whole is charged on top"
            yield Problem(f"{where}.estimate", what)


def _unmeasured(budget: Budget, where: str, role: Role, capabilities: Capabilities) -> Iterable[Problem]:
    for unit in _MEASURED:
        if getattr(budget, unit) is not None and unit not in capabilities.measures:
            what = f"`{role.driver}` cannot measure {unit}, so each of its turns is charged its estimate"
            yield Problem(f"{where}.{unit}", what, "warning")


def _population(team: Team, role: str) -> float:
    """The most agents a role can have at once, which is infinite when nothing bounds it."""
    return (team.topology.limits.max_live or math.inf) if team.spawners(role) else len(team.starts(role))


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


def _staying(team: Team, capabilities: Mapping[str, Capabilities]) -> dict[str, list[str]]:
    """The wake arcs, and a parent and a child that can stay waking each other: a message from the parent wakes the
    child, and the child's answer wakes the parent. Any child on a persistent harness can stay, as a spawn may ask."""
    found = {name: set(targets) for name, targets in arcs(team, wakes=True).items()}
    for parent, children in _spawning(team).items():
        edges = (*team.topology.edges.get(parent, ()), *team.topology.edges.get("all", ()))
        reached = {role for selector in edges for role in reach(team, parent, selector)}
        for child in sorted(children & reached & team.roles.keys()):
            known = capabilities.get(child) or capabilities.get(team.roles[child].driver)
            woken = {team.roles[parent].delivery, team.roles[child].delivery} <= set(WAKING)
            if known is not None and known.persistent and woken:
                found[parent].add(child)
                found[child].add(parent)
    return {name: sorted(targets) for name, targets in found.items()}


def _native(role: Role, known: Capabilities) -> str:
    """What an opt-in to a harness's own agents gives up."""
    if known.native_children == "none":
        return f"`{role.driver}` starts no agents of its own, so this allows nothing"
    return (
        "its harness's own agents are none of ours: their calls reach us only in their parent's total, no topology "
        "binds them, and their calls to our tools go out on their parent's token"
    )


def _template_problems(team: Team, tools: set[str], capabilities: Mapping[str, Capabilities]) -> Iterable[Problem]:
    """What a template leaves out, a template a role's harness is never told, and the tools a user's words name that a
    role cannot hold. Words a user wrote are never dropped, so these are said here. A grant to a named agent may be this
    role's, since agents' names are chosen as a session runs, so it counts as held."""
    grants = compile(team)
    yield from _left_out(team.preamble, "preamble")
    for name, role in team.roles.items():
        known = capabilities.get(name) or capabilities.get(role.driver)
        where = "preamble" if role.preamble is None else f"roles.{name}.preamble"
        if known is not None and not known.tool_paths:
            unreached = f"`{role.driver}` reaches none of our tools, so its agents are told `instructions` alone"
            if role.preamble is not None:
                yield Problem(where, f"{unreached}: say it there")
            elif team.preamble != PREAMBLE:
                yield Problem(where, f"`{name}` is told none of this: {unreached}", "warning")
            continue
        if role.preamble is not None:
            yield from _left_out(role.preamble, where)
        whos = ("agent", "all", f"role:{name}")
        held = {
            tool
            for tool in tools
            if any(fnmatchcase(tool, scope) for scope in scopes(role))
            and any(
                (grant.who in whos or grant.who.startswith("agent:")) and fnmatchcase(tool, grant.ops)
                for grant in grants
            )
        }
        for at, words in ((where, team.preamble_of(name)), (f"roles.{name}.instructions", role.instructions)):
            for tool in sorted(set(OP_NAMED.findall(words or "")) & tools - held):
                what = f"names `{tool}`, which `{name}` cannot hold: its agents are told of a tool they cannot call"
                yield Problem(at, what, "warning")


def _left_out(template: str, where: str) -> Iterable[Problem]:
    filled = slots(template)
    if "tools" not in filled:
        what = "leaves out `{tools}`: a harness can keep a server's tools from a model that knows none of their names"
        yield Problem(where, what, "warning")
    if "ending" not in filled:
        what = "leaves out `{ending}`: an agent never told how to end can leave its parent waiting for ever"
        yield Problem(where, what, "warning")


def _taken_down(team: Team, name: str) -> Iterable[Problem]:
    """A one-shot role's turn is its end, and no refusal can stand in the way of that."""
    for child in sorted(_spawning(team)[name] & team.roles.keys()):
        if team.roles[child].on_parent_exit == "cancel-subtree":
            what = (
                f"a one-shot harness ends with its turn, and that cancels `{child}` however far along it is: "
                'wait for it within the turn, or set `on_parent_exit = "adopt"` on that role'
            )
            yield Problem(f"roles.{name}.may_spawn", what, "warning")


def _warnings(team: Team) -> Iterable[Problem]:
    starting = {name for name in team.roles if team.starts(name)}
    started = starting.union(*(reach(team, name, "descendants") for name in starting))
    for name in sorted(team.roles.keys() - started):
        if team.roles[name].count != 0:  # Zero was said on purpose: a human or a program can spawn any role.
            yield Problem(f"roles.{name}", "never starts: nothing that starts can spawn it", "warning")

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

    for name, channel in team.topology.channels.items():
        if channel.delivery in WAKING:
            readers = {role for selector in channel.readers for role in reach(team, "", selector)}
            fan_out = sum(_population(team, role) for role in readers & team.roles.keys())
            if fan_out > _FAN_OUT:
                how_many = "an unbounded number of" if fan_out == math.inf else fan_out
                what = f"each entry can wake {how_many} agents. Prefer `next-turn`, or `coalesce` the wakes"
                yield Problem(f"topology.channels.{name}.delivery", what, "warning")


def team_check(
    team: Team, *, capabilities: Mapping[str, Capabilities], extensions: Mapping[str, Extension] | None = None
) -> tuple[Problem, ...]:
    """Every problem with a team, at once, before any cost. Pure: all it knows arrives as arguments.

    `capabilities` maps harness names, or a role's own name where its command decides, to what is known of them, and
    `extensions` maps the references a team may name to their extensions. Errors stop a team from running; warnings do
    not.
    """
    loaded, problems = _extensions_of(team, {} if extensions is None else extensions)
    presets, named = _presets_of(loaded)
    topology, more = finish(team.topology, presets)
    problems += named + more
    team = team.model_copy(update={"topology": topology})
    limits = topology.limits
    unsound = structure(team)
    problems += unsound

    for name, role in team.roles.items():
        known = capabilities.get(name) or capabilities.get(role.driver)
        if known is None:
            what = f"unknown harness `{role.driver}`.{nearest(role.driver, capabilities.keys())}"
            problems.append(Problem(f"roles.{name}.harness", what))
        else:
            if role.sandbox is not None and role.sandbox not in known.sandboxes:
                what = f"`{role.driver}` has no sandbox `{role.sandbox}`.{nearest(role.sandbox, known.sandboxes)}"
                problems.append(Problem(f"roles.{name}.sandbox", what))
            if not known.persistent and team.starts(name):
                what = (
                    "a one-shot harness needs a goal, and agents that start with the session have none: "
                    "set `count = 0` and spawn it with one"
                )
                problems.append(Problem(f"roles.{name}.count", what))
            if not known.persistent:
                problems += _taken_down(team, name)
            if role.stays and not known.persistent:
                what = "a one-shot harness ends with its turn, so it cannot stay"
                problems.append(Problem(f"roles.{name}.stays", what))
            if role.allow_native_children:
                problems.append(Problem(f"roles.{name}.allow_native_children", _native(role, known), "warning"))
            problems += _unmeasured(team.budget, "budget", role, known)
            problems += _unmeasured(role.budget, f"roles.{name}.budget", role, known)
        problems += _unestimated(role.budget, f"roles.{name}.budget", team.budget)
        if role.auth is not None and role.auth not in team.auth:
            problems.append(Problem(f"roles.{name}.auth", f"unknown profile.{nearest(role.auth, team.auth.keys())}"))

    if limits.max_depth is None and (cycle := _cycle(_spawning(team))):
        what = f"recursive may_spawn with no limit: {' -> '.join(cycle)}"
        problems.append(Problem("topology.limits.max_depth", what))
    if limits.max_hops is None:
        if cycle := _cycle(arcs(team, wakes=True)):
            problems.append(Problem("topology.limits.max_hops", f"a wake cycle with no limit: {' -> '.join(cycle)}"))
        elif cycle := _cycle(_staying(team, capabilities)):
            what = (
                f"a wake cycle with no limit, through a child that can stay: {' -> '.join(cycle)}. Each message from a "
                "parent wakes its child, and each answer wakes the parent: set `max_hops` to bound them"
            )
            problems.append(Problem("topology.limits.max_hops", what, "warning"))
    if (program := topology.program) is not None:
        name = program if isinstance(program, str) else program.name
        instead = "use a topology that names none, such as `manager-worker`, or drive the session from Python"
        problems.append(Problem("topology.program", f"`{name}` cannot run, as no program runs yet: {instead}"))

    problems += _unestimated(team.budget, "budget")
    problems += _warnings(team)
    if not unsound:
        ops = (operation for extension in (*PRIMITIVES, *loaded) for operation in extension.ops)
        problems += _template_problems(team, {operation.name for operation in ops if operation.tool}, capabilities)
    return tuple(problems)


def _reached_alone(team: Team) -> str | None:
    """Why only a person brings a session of this team to its `until`, or None when something else does: no program
    runs, a role's agents that stay end only when told to finish, and a role nothing starts a person must start."""
    until = team.topology.until or "settled"
    if until == "program":
        return "`program` is left to a program, and none runs, so only someone closing the session ends it"
    role = until.removeprefix("role:")
    if until == "settled" or role not in team.roles:
        return None
    stays = team.roles[role].stays
    if stays or (stays is None and team.starts(role)):
        return f"`{role}`'s agents stay until told to finish, and no person is there to tell them: set `stays = false`"
    if not team.starts(role) and not team.spawners(role):
        return f"nothing starts `{role}`, so only a person could"
    return None


def trainable_problems(team: Team, *, approvals: Policy | None = None) -> tuple[Problem, ...]:
    """What keeps a team from training, read from the team alone, with no driver to ask: a model or an auth profile a
    role names, as a training system's gateway gives both; approvals left to `ask`, which nobody answers in a rollout,
    by `approvals`, a session's policy over every role's own, or else by a role's; a harness's own agents allowed, whose
    calls go on their parent's key; a workspace other than `shared` or `isolated`; and an `until` only a person
    reaches."""
    asking = "approvals left to `ask` wait for a person, and nobody answers in a rollout: say `allow` or `deny`"
    problems = [Problem("approvals", asking)] if approvals == "ask" else []
    for name, role in team.roles.items():
        where = f"roles.{name}"
        if role.model is not None:
            problems.append(Problem(f"{where}.model", "a trainable team names no model: its gateway serves one"))
        if role.auth is not None:
            what = "a trainable team names no auth profile: its gateway is its access"
            problems.append(Problem(f"{where}.auth", what))
        if approvals is None and role.approvals == "ask":
            problems.append(Problem(f"{where}.approvals", asking))
        if role.allow_native_children:
            what = "a harness's own agents call on their parent's key, so no call of theirs is tied to an agent"
            problems.append(Problem(f"{where}.allow_native_children", what))
        if role.workspace not in ("shared", "isolated"):
            what = f"a trainable team works in `shared` or `isolated`, not `{role.workspace}`"
            problems.append(Problem(f"{where}.workspace", what))
    if (why := _reached_alone(team)) is not None:
        problems.append(Problem("topology.until", why))
    return tuple(problems)
