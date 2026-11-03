"""Presets are macros: each worked example, and the promise that a resolved form is valid input."""

from inspect import signature

import pytest

from platoon_harness.schema import ConfigError
from platoon_harness.team import Role, Team, team_check
from platoon_harness.topology import (
    PRESETS,
    Board,
    Group,
    Limits,
    Program,
    Queue,
    Topic,
    compile,
    git_swarm,
    manager_worker,
    map_reduce,
    mesh,
    pipeline,
    ring,
    star,
    tree,
)

from .support import CAPABILITIES, MANAGER_WORKER, PRESET_TEAMS


def errors(team):
    return [problem for problem in team_check(team, capabilities=CAPABILITIES) if problem.level == "error"]


def test_every_preset_has_a_team_here():
    assert (
        PRESET_TEAMS.keys()
        == PRESETS.keys()
        == {
            "manager-worker",
            "tree",
            "mesh",
            "star",
            "blackboard",
            "pipeline",
            "ring",
            "map-reduce",
            "git-swarm",
        }
    )


@pytest.mark.parametrize("name", PRESETS)
def test_the_resolved_form_is_valid_input(name):
    team = PRESET_TEAMS[name]
    reloaded = Team.loads(team.show(resolved=True))
    assert reloaded == team
    assert reloaded.topology.hash == team.topology.hash
    assert reloaded.show(resolved=True) == team.show(resolved=True)


@pytest.mark.parametrize("name", PRESETS)
def test_a_preset_behaves_as_its_expansion(name):
    team = PRESET_TEAMS[name]
    assert compile(Team.loads(team.show(resolved=True))) == compile(team)
    assert Team.loads(team.show(resolved=True)).show() == team.show()


@pytest.mark.parametrize("name", PRESETS)
def test_every_preset_passes_team_check(name):
    assert errors(PRESET_TEAMS[name]) == []


def test_toml_and_python_build_the_same_object():
    written = Team(
        roles={
            "lead": Role(harness="claude", may_spawn=["worker"]),
            "worker": Role(harness="codex", workspace="worktree"),
        },
        topology=manager_worker("lead", "worker"),
    )
    assert Team.loads(MANAGER_WORKER) == written


def test_manager_worker_with_a_shared_board():
    topology = Team.loads(
        """
        [roles.lead]
        harness = "claude"
        may_spawn = ["worker"]
        [roles.worker]
        harness = "codex"
        workspace = "worktree"
        [topology]
        limits = { max_children = 8 }
        [topology.manager-worker]
        manager = "lead"
        workers = "worker"
        queue = "tasks"
        board = "notes"
        """
    ).topology
    assert topology.edges == {"lead": ("children", "human"), "worker": ("parent",)}
    assert topology.channels == {
        "tasks": Queue(writers="role:lead", readers="role:worker", lease="30m", max_attempts=3),
        "notes": Board(writers="all", readers="all"),
    }
    assert topology.until == "role:lead"
    assert topology.limits == Limits(max_children=8, max_hops=8)


def test_recursive_tree():
    topology = tree("agent", max_depth=6, max_children=4)
    assert topology.edges == {"agent": ("children", "human", "parent")}
    assert topology.limits == Limits(max_depth=6, max_children=4, max_hops=8)
    assert topology.until == "role:agent"
    assert topology.channels == {}


def test_full_mesh_of_peers():
    team = Team.loads(
        """
        [roles.peer]
        harness = "opencode"
        may_spawn = ["peer"]
        [topology]
        limits = { max_live = 16, max_depth = 3 }
        [topology.mesh]
        role = "peer"
        board = "notes"
        """
    )
    peers = "group:peers"
    assert team.topology.groups == {"peers": Group(roles=("peer",))}
    assert team.topology.edges == {"peer": (peers, "human")}
    assert team.topology.channels == {"notes": Board(writers=peers, readers=peers)}
    assert team.topology.until is None
    assert errors(team) == []


def test_a_mesh_shares_its_groups_topic_and_makes_no_second_one():
    assert mesh("peer").channels == {}
    assert "topic" not in signature(mesh).parameters


def test_a_person_can_reach_a_star_and_a_tree_and_be_answered():
    assert "human" in star("hub", "spoke").edges["hub"]
    assert "human" in tree("agent", max_depth=2).edges["agent"]


def test_a_tree_needs_only_a_depth():
    assert tree("agent", max_depth=6).limits == Limits(max_depth=6, max_hops=8)


def test_a_stage_named_twice_keeps_every_writer():
    assert set(pipeline(["a", "b", "c", "b"]).channels["to-b"].writers) == {"role:a", "role:c"}


def test_an_edge_may_be_one_selector_as_a_channel_may():
    team = Team.loads('[roles.a]\nharness = "pi"\n[topology]\nedges = { a = "human" }')
    assert team.topology.edges == {"a": ("human",)}


def test_review_chain():
    team = Team.loads(
        """
        [roles.author]
        harness = "codex"
        [roles.reviewer]
        harness = "claude"
        tools = ["board.get", "message.*"]
        [roles.verifier]
        harness = "opencode"
        tools = ["board.get", "message.*"]
        [topology.pipeline]
        stages = ["author", "reviewer", "verifier"]
        back = true
        max_hops = 6
        """
    )
    assert team.topology.edges == {}
    assert team.topology.limits == Limits(max_hops=6)
    assert team.topology.channels == {
        "to-reviewer": Queue(writers="role:author", readers="role:reviewer", delivery="wake"),
        "to-verifier": Queue(writers="role:reviewer", readers="role:verifier", delivery="wake"),
        "to-author": Queue(writers=["role:reviewer", "role:verifier"], readers="role:author", delivery="wake"),
    }


def test_a_verifier_shares_nothing_with_the_author_but_the_chain():
    channels = pipeline(["author", "reviewer", "verifier"], back=True, max_hops=6).channels
    assert not any(
        "role:author" in channel.writers and "role:verifier" in channel.readers for channel in channels.values()
    )


def test_a_ring_is_a_pipeline_with_a_wrap():
    channels = ring(["a", "b", "c"], laps=2).channels
    assert channels["to-a"].writers == ("role:c",)
    assert channels.keys() == {"to-a", "to-b", "to-c"}
    assert ring(["a", "b", "c"], laps=2).limits.max_hops == 6


def test_stages_must_link_two_roles():
    with pytest.raises(ValueError, match="at least two"):
        pipeline(["solo"])
    with pytest.raises(ConfigError, match="at least two"):
        Team.loads('[roles.a]\nharness = "pi"\n[topology.pipeline]\nstages = []')


def test_map_reduce_with_an_llm_reducer():
    topology = map_reduce("mapper", "reducer", parallel=16)
    assert topology.channels == {
        "map": Queue(writers="program", readers="role:mapper", lease="1h", max_attempts=2),
        "reduce": Queue(writers="program", readers="role:reducer", lease="1h"),
        "results": Board(writers=["role:mapper", "role:reducer"], readers=["role:reducer", "program"]),
    }
    assert topology.program == Program(name="map_reduce", params={"parallel": 16})
    assert topology.until == "program"
    assert map_reduce("mapper", "reducer").program == "map_reduce"


def test_git_swarm_coordinates_through_artifacts_alone():
    topology = git_swarm("worker", live=8, episodes=64)
    assert topology.edges == {}
    contributions = topology.channels["contributions"]
    assert isinstance(contributions, Topic)
    assert (contributions.writers, contributions.readers) == (("role:worker",), ("all",))
    assert (contributions.delivery, contributions.history) == ("pull", "full")
    assert contributions.requires == ("informed_by",)
    assert (contributions.entry, contributions.validator) == ("commit", "task_publication")
    assert topology.channels["inflight"] == Board(writers="all", readers="all", keys="author")
    assert topology.channels["nominations"].writers == ("role:worker",)
    assert topology.program == Program(
        name="population",
        params={"role": "worker", "live": 8, "episodes": 64, "uncharged": ["abstained"], "readout": "plurality"},
    )
    assert topology.until == "program"


def test_mixed_harnesses_work_together_in_one_preset():
    topology = mesh(["coder", "tester"])
    assert topology.groups["peers"].roles == ("coder", "tester")
    assert topology.edges.keys() == {"coder", "tester"}


def test_a_preset_table_rejects_what_its_function_would():
    with pytest.raises(ConfigError) as caught:
        Team.loads(
            """
            [roles.a]
            harness = "pi"
            [topology.tree]
            rol = "a"
            max_depth = "6"
            """
        )
    text = str(caught.value)
    assert "topology.tree.rol" in text
    assert "Did you mean `role`?" in text
    assert "topology.tree.max_depth" in text


def test_a_preset_used_twice_is_an_array_of_tables():
    topology = Team.loads(
        """
        [roles.a]
        harness = "pi"
        [roles.b]
        harness = "pi"
        [[topology.blackboard]]
        role = "a"
        board = "one"
        [[topology.blackboard]]
        role = "b"
        board = "two"
        """
    ).topology
    assert topology.channels.keys() == {"one", "two"}
