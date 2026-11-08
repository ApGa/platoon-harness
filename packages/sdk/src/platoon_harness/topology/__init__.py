"""Topology: who may reach whom. Presets make fragments, `|` mixes them, and `compile` gives one grant table."""

from .compile import compile, scopes
from .presets import (
    PRESETS,
    blackboard,
    expand,
    git_swarm,
    manager_worker,
    mesh,
    pipeline,
    preset_name,
    ring,
    star,
    tree,
)
from .spec import Board, Channel, Group, Limits, Queue, Topic, Topology, Unexpanded, union

__all__ = [
    "PRESETS",
    "Board",
    "Channel",
    "Group",
    "Limits",
    "Queue",
    "Topic",
    "Topology",
    "Unexpanded",
    "blackboard",
    "compile",
    "expand",
    "git_swarm",
    "manager_worker",
    "mesh",
    "pipeline",
    "preset_name",
    "ring",
    "scopes",
    "star",
    "tree",
    "union",
]
