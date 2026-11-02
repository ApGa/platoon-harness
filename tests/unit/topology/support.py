"""Teams used across the topology tests, one per preset, each with its TOML and Python forms."""

from platoon_harness.team import Capabilities, Role, Team
from platoon_harness.topology import (
    blackboard,
    git_swarm,
    manager_worker,
    map_reduce,
    mesh,
    pipeline,
    ring,
    star,
    tree,
)

MEASURING = Capabilities(measures={"tokens", "usd"}, sandboxes={"read-only", "workspace-write"})
CAPABILITIES = {name: MEASURING for name in ("claude", "codex", "pi", "openhands", "opencode", "exec")}

MANAGER_WORKER = """
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
workspace = "worktree"

[topology.manager-worker]
manager = "lead"
workers = "worker"
"""

SECTION_8_RESOLVED = """
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
workspace = "worktree"

[topology]
until = "role:lead"
edges = { lead = ["children", "human"], worker = ["parent"] }

[topology.channels.notes]
kind = "board"
writers = "all"
readers = "all"

[topology.channels.tasks]
kind = "queue"
writers = "role:lead"
readers = "role:worker"
lease = "30m"
"""

PRESET_TEAMS = {
    "manager-worker": Team(
        roles={"lead": Role(harness="claude", may_spawn=["worker"]), "worker": Role(harness="codex")},
        topology=manager_worker("lead", "worker"),
    ),
    "tree": Team(
        roles={"agent": Role(harness="openhands", may_spawn=["agent"])},
        topology=tree("agent", max_depth=6, max_children=4),
    ),
    "mesh": Team(roles={"peer": Role(harness="opencode", count=4)}, topology=mesh("peer", board="notes")),
    "star": Team(
        roles={"hub": Role(harness="claude"), "spoke": Role(harness="codex", count=3)},
        topology=star("hub", "spoke", topic="announcements"),
    ),
    "blackboard": Team(
        roles={"agent": Role(harness="pi", count=4)},
        topology=blackboard("agent", board="notes", queue="tasks"),
    ),
    "pipeline": Team(
        roles={
            "author": Role(harness="codex"),
            "reviewer": Role(harness="claude"),
            "verifier": Role(harness="opencode"),
        },
        topology=pipeline(["author", "reviewer", "verifier"], back=True, max_hops=6),
    ),
    "ring": Team(
        roles={"a": Role(harness="codex"), "b": Role(harness="claude"), "c": Role(harness="pi")},
        topology=ring(["a", "b", "c"], laps=2),
    ),
    "map-reduce": Team(
        roles={"mapper": Role(harness="codex", count=16), "reducer": Role(harness="claude")},
        topology=map_reduce("mapper", "reducer", parallel=16),
    ),
    "git-swarm": Team(
        roles={"worker": Role(harness="codex", workspace="worktree", count=8)},
        topology=git_swarm("worker", live=8, episodes=64),
    ),
}
