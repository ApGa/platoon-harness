"""From a team to a live session: checked before any cost, then journaled through ops, safe to repeat after a crash."""

import asyncio
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from platoon_harness.config import Manifest
from platoon_harness.drivers import Capabilities, Driver, DriverError
from platoon_harness.extensions import DRIVERS, Installed, load
from platoon_harness.kernel import NAME, Kernel, Refused
from platoon_harness.schema import ConfigError, Problem, seconds
from platoon_harness.team import Budget, Command, Role, Team, team_check
from platoon_harness.topology import Queue, Topic, compile, scopes

from .authority import Authority
from .paths import MANIFEST, find_root, new_folder, write_private

log = logging.getLogger("platoon_harness.runtime")

__all__ = ["make_driver", "open_session", "prepare"]


def make_driver(role: Role) -> Driver:
    """A new driver for a role's harness, by exact name, since a driver is one instance per agent."""
    factory = load(DRIVERS, role.driver)
    return factory(role.harness.command) if isinstance(role.harness, Command) else factory()


def _capabilities_of(team: Team) -> tuple[dict[str, Capabilities], list[Problem]]:
    """What each role's driver says of itself, by role, since a command decides that and a driver's name does not."""
    known: dict[str, Capabilities] = {}
    problems: list[Problem] = []
    for name, role in team.roles.items():
        try:
            known[name] = make_driver(role).describe().capabilities
        except ConfigError as error:
            problems += [Problem(f"roles.{name}.harness", problem.what) for problem in error.problems]
        except DriverError as error:
            problems.append(Problem(f"roles.{name}.harness", str(error)))
    return known, problems


def prepare(
    team: Team,
    *,
    name: str | None = None,
    root: str | Path | None = None,
    human: str = "you",
    approvals: Literal["ask", "deny", "allow"] | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """Check a team and write down how it starts, before any cost. The folder is all a runtime then needs.

    This blocks, because a wire program describes itself by running.
    """
    if re.fullmatch(NAME, human) is None:
        raise ConfigError([Problem("human", f"{human!r} cannot name a principal")])
    extensions = Installed()
    resolved = team.resolved(extensions)
    known, problems = _capabilities_of(resolved)
    named = {problem.where for problem in problems}
    checked = team_check(resolved, capabilities=known, extensions=extensions)
    problems += [problem for problem in checked if problem.where not in named]
    if errors := [problem for problem in problems if problem.level == "error"]:
        raise ConfigError(errors)
    for warning in problems:
        log.warning("%s", warning)
    manifest = Manifest.of(resolved, human=f"human:{human}", approvals=approvals, cwd=str(Path(cwd or ".").resolve()))
    folder = new_folder(find_root(root, writing=True), name)
    write_private(folder / MANIFEST, manifest.model_dump_json())
    return folder


def _settings(team: Team, manifest: Manifest, body: str) -> dict[str, Any]:
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
    return {"scope": scope, "limits": limits, "fallback": budget.fallback} if limits else None


def _starting(team: Team) -> list[dict[str, str]]:
    """The agents that start with the session. They have no goal, so each waits for a message."""
    spawns = []
    for role in team.roles:
        count = team.starts(role)
        names = [role] if count == 1 else [f"{role}-{number}" for number in range(1, count + 1)]
        spawns += [{"name": name, "child_role": role} for name in names]
    return spawns


async def _steps(kernel: Kernel, op: str, *steps: tuple[str, Mapping[str, Any]]) -> None:
    """Run one op over several arguments, in order, as one batch of commits. A key answers a repeat from the journal,
    and a step that ran with other arguments, under an older SDK, stands as it ran."""
    outcomes = await asyncio.gather(
        *(kernel.submit(kernel.runtime, op, args, key=f"open/{key}") for key, args in steps)
    )
    for outcome in outcomes:
        if outcome.refusal is not None and outcome.refusal.code != "key_reused":
            raise Refused.of(outcome.refusal)


async def open_session(kernel: Kernel, team: Team, manifest: Manifest, authority: Authority, text: str) -> None:
    """Journal a session through ops. Each step has a fixed key, so a crash part of the way is finished by the next
    runtime, which runs this again, and a session that opened long ago is not disturbed."""
    body = await kernel.put_body(text.encode())
    await _steps(kernel, "session.open", ("session", _settings(team, manifest, body)))
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
