"""Presets: plain functions that return topology fragments. Each is a macro with no power of its own.

A preset's TOML table is named after the function, with dashes for underscores: `manager_worker` is
`[topology.manager-worker]`, and its keys are the function's arguments.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from inspect import signature
from itertools import pairwise
from typing import Any

from pydantic import ConfigDict, ValidationError, validate_call

from platoon_harness.schema import ConfigError, Problem, nearest, problems_in

from .spec import Board, Group, Limits, Program, Queue, Topic, Topology, Unexpanded, union

type Preset = Callable[..., Topology]
type Roles = str | Sequence[str]
type Part = tuple[str, Topology]


def _names(roles: Roles) -> tuple[str, ...]:
    return (roles,) if isinstance(roles, str) else tuple(roles)


def _selectors(roles: Roles) -> list[str]:
    return [f"role:{role}" for role in _names(roles)]


def manager_worker(
    manager: str,
    workers: Roles,
    *,
    queue: str = "tasks",
    board: str = "notes",
    lease: str = "30m",
    max_hops: int = 8,
) -> Topology:
    """A manager fills a queue that workers claim from. Workers answer to their parent and share a board."""
    return Topology(
        until=f"role:{manager}",
        edges={manager: ["children", "human"], **{worker: ["parent"] for worker in _names(workers)}},
        channels={
            queue: Queue(writers=f"role:{manager}", readers=_selectors(workers), lease=lease),
            board: Board(writers="all", readers="all"),
        },
        limits=Limits(max_hops=max_hops),
    )


def tree(
    role: str, *, max_depth: int, max_children: int | None = None, until: str | None = None, max_hops: int = 8
) -> Topology:
    """Agents delegate downward and report upward. It closes when its root finishes, unless `until` says otherwise."""
    return Topology(
        until=until or f"role:{role}",
        edges={role: ["children", "parent", "human"]},
        limits=Limits(max_depth=max_depth, max_children=max_children, max_hops=max_hops),
    )


def mesh(role: Roles, *, board: str | None = None, group: str = "peers", max_hops: int = 8) -> Topology:
    """Peers message each other directly and share their group's topic, which wakes no one."""
    members = f"group:{group}"
    return Topology(
        groups={group: Group(roles=_names(role))},
        edges={name: [members, "human"] for name in _names(role)},
        channels={board: Board(writers=members, readers=members)} if board else {},
        limits=Limits(max_hops=max_hops),
    )


def star(hub: str, spokes: Roles, *, topic: str | None = None, max_hops: int = 8) -> Topology:
    """Every message goes through the hub, which may also announce on a topic. Spokes never reach each other."""
    return Topology(
        edges={hub: [*_selectors(spokes), "human"], **{spoke: [f"role:{hub}"] for spoke in _names(spokes)}},
        channels={topic: Topic(writers=f"role:{hub}", readers=_selectors(spokes))} if topic else {},
        limits=Limits(max_hops=max_hops),
    )


def blackboard(role: Roles, *, board: str = "notes", queue: str | None = None) -> Topology:
    """Agents coordinate through shared artifacts alone, and may share a queue of open work."""
    selectors = _selectors(role)
    channels: dict[str, Board | Queue] = {board: Board(writers=selectors, readers=selectors)}
    if queue:
        channels[queue] = Queue(writers=selectors, readers=selectors)
    return Topology(channels=channels)


def _stage_queues(links: Iterable[tuple[str, str]]) -> dict[str, Queue]:
    """One queue per stage, with everything that feeds it as writers, so a stage named twice loses none."""
    writers: dict[str, list[str]] = {}
    for before, after in links:
        writers.setdefault(after, []).append(before)
    if not writers:
        raise ValueError("stages must link at least two roles")
    return {
        f"to-{stage}": Queue(writers=_selectors(feeding), readers=f"role:{stage}", delivery="wake")
        for stage, feeding in writers.items()
    }


def pipeline(stages: Sequence[str], *, back: bool = False, max_hops: int | None = None) -> Topology:
    """Each stage feeds a queue for the next. `back` lets every later stage return work to the first."""
    links = [*pairwise(stages), *((stage, stages[0]) for stage in stages[1:] if back)]
    return Topology(channels=_stage_queues(links), limits=Limits(max_hops=max_hops))


def ring(stages: Sequence[str], *, laps: int) -> Topology:
    """A pipeline whose last stage feeds the first, for at most `laps` times round."""
    links = pairwise([*stages, *stages[:1]])
    return Topology(channels=_stage_queues(links), limits=Limits(max_hops=laps * len(stages)))


def map_reduce(map: str, reduce: str, *, parallel: int | None = None, lease: str = "1h") -> Topology:
    """A program shards work to mappers and folds their results through reducers. Mappers cannot read each other."""
    return Topology(
        until="program",
        program=Program(name="map_reduce", params={"parallel": parallel}) if parallel else "map_reduce",
        channels={
            "map": Queue(writers="program", readers=f"role:{map}", lease=lease, max_attempts=2),
            "reduce": Queue(writers="program", readers=f"role:{reduce}", lease=lease),
            "results": Board(writers=[f"role:{map}", f"role:{reduce}"], readers=[f"role:{reduce}", "program"]),
        },
    )


def git_swarm(role: str, *, live: int, episodes: int) -> Topology:
    """A population coordinating through a shared repository alone: no messages, only commits and nominations."""
    return Topology(
        until="program",
        program=Program(
            name="population",
            params={
                "role": role,
                "live": live,
                "episodes": episodes,
                "uncharged": ["abstained"],
                "readout": "plurality",
            },
        ),
        channels={
            "inflight": Board(writers="all", readers="all"),
            "nominations": Topic(writers=f"role:{role}", readers="all", delivery="pull", history="full"),
        },
    )


def preset_name(preset: Preset) -> str:
    """The name a preset goes by in TOML."""
    return getattr(preset, "__name__", "").replace("_", "-")


PRESETS: dict[str, Preset] = {
    preset_name(preset): preset
    for preset in (manager_worker, tree, mesh, star, blackboard, pipeline, ring, map_reduce, git_swarm)
}


def _call(preset: Preset, params: Mapping[str, Any], where: str) -> Topology:
    try:
        fragment = validate_call(config=ConfigDict(strict=True, hide_input_in_errors=True))(preset)(**params)
    except ValidationError as error:
        raise ConfigError(problems_in(error, where=where, keys=signature(preset).parameters.keys())) from None
    except ValueError as error:
        raise ConfigError([Problem(where, str(error))]) from error
    if not isinstance(fragment, Topology):
        raise ConfigError([Problem(where, "a preset must return a Topology")])
    return fragment


def _expand(
    uses: Iterable[tuple[str, Mapping[str, Any]]], presets: Mapping[str, Preset]
) -> tuple[list[Part], list[Problem]]:
    """Each use as a named fragment. One with no definition waits as `Unexpanded`."""
    parts: list[Part] = []
    problems: list[Problem] = []
    for name, params in uses:
        if name in presets:
            try:
                parts.append((name, _call(presets[name], params, f"topology.{name}")))
            except ConfigError as error:
                problems.extend(error.problems)
        else:
            parts.append((name, Topology(unexpanded=(Unexpanded(preset=name, params=params),))))
    return parts, problems


def expand(table: Mapping[str, Any], presets: Mapping[str, Preset] = PRESETS) -> Topology:
    """A `[topology]` table as one fragment: its own keys, in union with each preset table beside them."""
    own = {key: value for key, value in table.items() if key in Topology.model_fields and key != "unexpanded"}
    uses: list[tuple[str, Mapping[str, Any]]] = []
    problems: list[Problem] = []
    for name, value in table.items():
        if name in own:
            continue
        tables = value if isinstance(value, list) else [value]
        uses += [(name, params) for params in tables if isinstance(params, Mapping)]
        if not all(isinstance(params, Mapping) for params in tables):
            what = (
                f"`{name}` is not a key of [topology], and a preset is a table.{nearest(name, Topology.model_fields)}"
            )
            problems.append(Problem(f"topology.{name}", what))
    parts, failed = _expand(uses, presets)
    problems += failed
    try:
        parts.append(("[topology]", Topology.model_validate(own)))
    except ValidationError as error:
        problems += problems_in(error, Topology, where="topology")
    if problems:
        raise ConfigError(problems)
    return union(parts)


def finish(topology: Topology, presets: Mapping[str, Preset]) -> tuple[Topology, list[Problem]]:
    """Expand what waited for an extension. What remains unknown is a problem, and the rest is still returned."""
    uses = [(item.preset, item.params) for item in topology.unexpanded]
    known = {**PRESETS, **presets}
    parts, problems = _expand(uses, known)
    for name, fragment in parts:
        if fragment.unexpanded:
            hint = nearest(name, {*known, *Topology.model_fields})
            problems.append(Problem(f"topology.{name}", f"unknown preset `{name}`.{hint}"))
    rest = topology.model_copy(update={"unexpanded": ()})
    try:
        return union([("[topology]", rest), *(part for part in parts if not part[1].unexpanded)]), problems
    except ConfigError as error:
        return rest, [*problems, *error.problems]
