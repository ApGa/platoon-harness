"""From a team to a live session: checked before any cost, then journaled through ops, safe to repeat after a crash."""

import asyncio
import contextlib
import logging
import re
import tempfile
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Any

from platoon_harness.config import Manifest
from platoon_harness.drivers import Capabilities, Driver, DriverError, DriverInfo
from platoon_harness.extensions import DRIVERS, Installed, load
from platoon_harness.kernel import NAME, Kernel, Principal, Refused
from platoon_harness.primitives import PRIMITIVES, Policy
from platoon_harness.schema import ConfigError, Problem, seconds
from platoon_harness.team import Budget, Command, Role, Team, team_check
from platoon_harness.tools import instructions, surface_of
from platoon_harness.topology import Limits, Queue, Topic, compile, scopes

from .authority import Authority, LocalAuthority
from .paths import find_root, new_folder

log = logging.getLogger("platoon_harness.runtime")

__all__ = ["PLAN_LOGIN_FIX", "check", "make_driver", "open_session", "prepare", "told"]

PLAN_LOGIN_FIX = (
    "say this is your own work with `plan_login=True`, or `--plan-login` on the command line, or give each role an "
    "auth profile"
)


def make_driver(role: Role) -> Driver:
    """A new driver for a role's harness, by exact name, since a driver is one instance per agent."""
    factory = load(DRIVERS, role.driver)
    return factory(role.harness.command) if isinstance(role.harness, Command) else factory()


def _described(team: Team) -> tuple[dict[str, DriverInfo], list[Problem]]:
    """What each role's driver says of itself, by role, since a command decides that and a driver's name does not."""
    known: dict[str, DriverInfo] = {}
    problems: list[Problem] = []
    for name, role in team.roles.items():
        try:
            known[name] = make_driver(role).describe()
        except ConfigError as error:
            problems += [Problem(f"roles.{name}.harness", problem.what) for problem in error.problems]
        except DriverError as error:
            problems.append(Problem(f"roles.{name}.harness", str(error)))
    return known, problems


def _on_a_plan_login(team: Team, known: Mapping[str, DriverInfo]) -> list[Problem]:
    """Refuse many agents on one plan login. A role with an auth profile is on no login, and one agent alone is
    ordinary use, unless another role can spawn more."""
    roles = [name for name, info in known.items() if info.login == "plan" and team.roles[name].auth is None]
    if sum(len(team.starts(role)) for role in roles) < 2 and not any(map(team.spawners, roles)):
        return []
    names = ", ".join(roles)
    return [Problem("plan_login", f"{names} would run several agents headless on one plan login: {PLAN_LOGIN_FIX}")]


def check(team: Team, *, plan_login: bool = False) -> tuple[Problem, ...]:
    """Every problem a session would meet in a team, errors and warnings, at once and before any cost, asking each
    role's driver what it is. A team that cannot be resolved raises `ConfigError`.

    This blocks, because a driver may describe itself by running something.
    """
    extensions = Installed()
    resolved = team.resolved(extensions)
    known, problems = _described(resolved)
    named = {problem.where for problem in problems}
    capabilities = {role: info.capabilities for role, info in known.items()}
    checked = team_check(resolved, capabilities=capabilities, extensions=extensions)
    problems += [problem for problem in checked if problem.where not in named]
    if not plan_login:
        problems += _on_a_plan_login(resolved, known)
    return tuple(problems)


def prepare(
    team: Team,
    *,
    name: str | None = None,
    root: str | Path | None = None,
    human: str = "you",
    approvals: Policy | None = None,
    cwd: str | Path | None = None,
    plan_login: bool = False,
) -> Path:
    """Check a team and write down how it starts, before any cost. The folder is all a runtime then needs.

    This blocks, because a driver may describe itself by running something.
    """
    if re.fullmatch(NAME, human) is None:
        raise ConfigError([Problem("human", f"{human!r} cannot name a principal")])
    problems = check(team, plan_login=plan_login)
    if errors := [problem for problem in problems if problem.level == "error"]:
        raise ConfigError(errors)
    for warning in problems:
        log.warning("%s", warning)
    manifest = Manifest.of(
        team.resolved(Installed()),
        human=f"human:{human}",
        approvals=approvals,
        cwd=str(Path(cwd or ".").resolve()),
        plan_login=plan_login,
    )
    return new_folder(find_root(root, writing=True), manifest.model_dump_json(), name)


def _settings(team: Team, manifest: Manifest, body: str, capabilities: Mapping[str, Capabilities]) -> dict[str, Any]:
    roles = {
        name: {
            "harness": role.harness if isinstance(role.harness, str) else role.harness.model_dump(mode="json"),
            "model": role.model,
            "workspace": role.workspace,
            "tools": scopes(role),
            "on_parent_exit": role.on_parent_exit,
            "approvals": manifest.approvals or role.approvals,
            "delivery": role.delivery,
            "inbox_depth": role.inbox_depth,
            "stays": role.stays,
            "persistent": capabilities[name].persistent if name in capabilities else None,
        }
        for name, role in team.roles.items()
    }
    limits = team.topology.limits.model_dump()
    return {"roles": roles, "limits": limits, "until": team.topology.until or "settled", "manifest": f"sha256:{body}"}


def _channel(name: str, channel: Any) -> dict[str, Any]:
    args = {"name": name, "kind": channel.kind, "delivery": channel.delivery}
    if isinstance(channel, Topic):
        args |= {"history": channel.history, "coalesce": seconds(channel.coalesce or 0)}
    elif isinstance(channel, Queue):
        args |= {"max_attempts": channel.max_attempts, "max_inflight": channel.max_inflight}
        args |= {key: seconds(span) for key in ("lease", "lease_max") if (span := getattr(channel, key)) is not None}
    return args


def _budget(scope: str, budget: Budget, authority: Authority) -> dict[str, Any] | None:
    """The limits a session enforces itself, in seconds, or nothing if it has none."""
    units = {unit: getattr(budget, unit) for unit in ("tokens", "usd", "turns", "agents", "wall")}
    limits = {
        unit: seconds(amount) if unit == "wall" else amount
        for unit, amount in units.items()
        if amount is not None and authority.budget_owner(unit) == "session"
    }
    return {"scope": scope, "limits": limits, "estimate": dict(budget.estimate)} if limits else None


def _starting(team: Team) -> list[dict[str, str]]:
    """The agents that start with the session. They have no goal, so each waits for a message."""
    return [{"name": name, "child_role": role} for role in team.roles for name in team.starts(role)]


async def _steps(kernel: Kernel, op: str, *steps: tuple[str, Mapping[str, Any]]) -> None:
    """Run one op over several arguments, in order, as one batch of commits. A key answers a repeat from the journal,
    and a step that ran with other arguments, under an older SDK, stands as it ran."""
    outcomes = await asyncio.gather(
        *(kernel.submit(kernel.runtime, op, args, key=f"open/{key}") for key, args in steps)
    )
    for outcome in outcomes:
        if outcome.refusal is not None and outcome.refusal.code != "key_reused":
            raise Refused.of(outcome.refusal)


async def open_session(
    kernel: Kernel,
    team: Team,
    manifest: Manifest,
    authority: Authority,
    text: str,
    capabilities: Mapping[str, Capabilities],
) -> None:
    """Journal a session through ops. Each step has a fixed key, so a crash part of the way is finished by the next
    runtime, which runs this again, and a session that opened long ago is not disturbed. `capabilities` is what each
    role's driver says, by role, and a role missing from it is unknown."""
    body = await kernel.put_body(text.encode())
    await _steps(kernel, "session.open", ("session", _settings(team, manifest, body, capabilities)))
    await _steps(kernel, "principal.add", ("human", {"id": manifest.human}))
    grants = compile(team)
    await _steps(kernel, "grant.add", *((f"grant/{index}", grant.model_dump()) for index, grant in enumerate(grants)))
    channels = team.topology.channels.items()
    await _steps(kernel, "channel.create", *((f"channel/{name}", _channel(name, item)) for name, item in channels))
    groups = {
        name: {"name": name, "roles": (*group.roles, *group.order), "members": group.members}
        for name, group in team.topology.groups.items()
    }
    await _steps(kernel, "group.define", *((f"group/{name}", args) for name, args in groups.items()))
    budgets = [
        ("shared", team.budget),
        *((f"role:{name}", role.budget) for name, role in team.roles.items()),
    ]
    limits = {scope: found for scope, budget in budgets if (found := _budget(scope, budget, authority))}
    await _steps(kernel, "budget.set", *((f"budget/{scope}", args) for scope, args in limits.items()))
    await _steps(kernel, "agent.spawn", *((f"spawn/{args['name']}", args) for args in _starting(team)))


async def told(team: Team) -> dict[str, str | None]:
    """What an agent of each role would be told at launch, which is all the runtime adds to its harness. It is rendered
    on a session of its own, in a folder thrown away after, and no harness starts. A role nothing starts is shown as an
    agent of its own name, started by an agent of a role that may start it, as an agent's name is its spawner's."""
    resolved = team.resolved(Installed())
    known, problems = await asyncio.to_thread(_described, resolved)
    if problems:
        raise ConfigError(problems)
    capabilities = {name: info.capabilities for name, info in known.items()}
    async with _rehearsed(resolved, capabilities) as kernel:
        return {
            name: instructions(
                kernel,
                agent,
                surface_of(capabilities[name].tool_paths),
                resolved.preamble_of(name),
                resolved.roles[name].instructions,
            )
            async for name, agent in _one_of_each(kernel, resolved)
        }


@contextlib.asynccontextmanager
async def _rehearsed(team: Team, capabilities: Mapping[str, Capabilities]) -> AsyncGenerator[Kernel]:
    """A resolved team's session, opened as a runtime opens one, in a folder thrown away after, with no harness. Its
    limits and budgets are left out, as nothing an agent is told says them, so that an agent of every role can start."""
    roles = {name: role.model_copy(update={"budget": Budget()}) for name, role in team.roles.items()}
    topology = team.topology.model_copy(update={"limits": Limits()})
    team = team.model_copy(update={"roles": roles, "budget": Budget(), "topology": topology})
    loaded = [*PRIMITIVES, *(Installed()[name] for name in team.extensions)]
    with tempfile.TemporaryDirectory() as folder:
        kernel = Kernel.open(Path(folder), extensions=loaded)
        try:
            manifest = Manifest(team=team.show(resolved=True), topology_hash=team.topology.hash, components=())
            await open_session(kernel, team, manifest, LocalAuthority(team), manifest.model_dump_json(), capabilities)
            yield kernel
        finally:
            kernel.close()


async def _one_of_each(kernel: Kernel, team: Team) -> AsyncGenerator[tuple[str, Principal]]:
    """An agent of each role, as each comes to be: one the session started, or else one of the role's name, spawned by
    an agent of the first role that may spawn it. Where no role with an agent may, the session spawns one, of a role
    that no role left may spawn where there is one, so that a child is shown as one."""
    found: dict[str, Principal] = {}
    for record in kernel.query(kernel.runtime, "agent.records", {}).result:
        if record["role"] not in found:
            found[record["role"]] = Principal(id=f"agent:{record['name']}")
            yield record["role"], found[record["role"]]
    while missing := [name for name in team.roles if name not in found]:
        spawners = {name: [found[role] for role in sorted(team.spawners(name)) if role in found] for name in missing}
        roots = [name for name in missing if not team.spawners(name) & {*missing}] or missing[:1]
        for name in [name for name in missing if spawners[name]] or roots[:1]:
            by = next(iter(spawners[name]), kernel.runtime)
            spawned = await kernel.submit(by, "agent.spawn", {"name": name, "child_role": name})
            if spawned.refusal is not None:
                raise Refused.of(spawned.refusal)
            found[name] = Principal(id=f"agent:{name}")
            yield name, found[name]
