"""`team.show()`: sentences for people, and with `resolved` the expansion, which is valid input."""

import tomllib

import pytest

from platoon_harness.schema import ConfigError
from platoon_harness.team import Command, Role, Team
from platoon_harness.topology import PRESETS, Group, Limits, Topic, Topology, pipeline, tree

from .support import MANAGER_WORKER, PRESET_TEAMS, SECTION_8_RESOLVED


def test_show_prints_what_the_architecture_shows():
    assert Team.loads(MANAGER_WORKER).show() == (
        "lead (claude) may message its workers and you. Workers (codex, own worktrees) may message lead.\n"
        "lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. "
        "Closes when lead finishes."
    )


def test_resolved_prints_what_the_architecture_shows():
    assert Team.loads(MANAGER_WORKER).show(resolved=True).strip() == SECTION_8_RESOLVED.strip()


def test_the_short_and_resolved_forms_hash_alike():
    short = Team.loads(MANAGER_WORKER)
    assert Team.loads(short.show(resolved=True)).topology.hash == short.topology.hash


@pytest.mark.parametrize("name", PRESETS)
def test_every_preset_reads_as_sentences(name):
    lines = PRESET_TEAMS[name].show().splitlines()
    assert len(lines) == 2
    assert all(line.endswith(".") for line in lines)


def test_show_describes_a_tree():
    assert PRESET_TEAMS["tree"].show() == (
        "Agents (openhands) may message their children, their parent and you.\n"
        "Limits: depth 6, children 4, hops 8. Closes when every agent has finished."
    )


def test_show_describes_a_mesh():
    assert PRESET_TEAMS["mesh"].show() == (
        "Peers (opencode) may message +peers and you.\n"
        "+peers is every peer. +peers share board `notes`. Limits: hops 8. Closes when the session settles."
    )


def test_show_describes_a_star():
    assert PRESET_TEAMS["star"].show() == (
        "hub (claude) may message spokes and you. Spokes (codex) may message hub.\n"
        "hub posts to topic `announcements`; spokes read it. Limits: hops 8. Closes when the session settles."
    )


@pytest.mark.parametrize(
    ("role", "shown"),
    [("policy", "Policies"), ("day", "Days"), ("lead_x", "Every lead_x"), ("qa-bot2", "Every qa-bot2")],
)
def test_a_role_reads_as_a_plural_only_when_it_is_a_word(role, shown):
    team = Team(roles={role: Role(harness="pi", count=2)})
    assert team.show().startswith(f"{shown} (pi)")


def test_a_close_on_a_role_of_many_says_every():
    team = Team(roles={"a": Role(harness="pi", count=2)}, topology=Topology(until="role:a"))
    assert team.show().endswith("Closes when every a has finished.")


def test_show_describes_a_pipeline():
    assert PRESET_TEAMS["pipeline"].show() == (
        "author (codex) may message no one. reviewer (claude) may message no one. "
        "verifier (opencode) may message no one.\n"
        "reviewer and verifier add to queue `to-author`; author claims from it. Each entry wakes its readers. "
        "author adds to queue `to-reviewer`; reviewer claims from it. Each entry wakes its readers. "
        "reviewer adds to queue `to-verifier`; verifier claims from it. Each entry wakes its readers. "
        "Limits: hops 6. Closes when the session settles."
    )


def test_show_describes_map_reduce():
    assert PRESET_TEAMS["map-reduce"].show() == (
        "Mappers (codex) may message no one. reducer (claude) may message no one.\n"
        "The program adds to queue `map`; mappers claim from it. "
        "The program adds to queue `reduce`; reducer claims from it. "
        "Mappers and reducer write board `results`; the program and reducer read it. "
        "Program `map_reduce` runs it. Closes when the program finishes."
    )


def test_show_describes_a_command_harness():
    team = Team(roles={"a": Role(harness=Command(command=["my-agent", "{goal}"]))})
    assert team.show().startswith("a (my-agent) may message no one.")


def test_show_uses_relations_and_kinds_in_words():
    team = Team(
        roles={"a": Role(harness="pi", count=2)},
        topology=Topology(edges={"a": ["ancestors", "self", "all", "prev"]}, groups={"o": Group(order=("a",))}),
    )
    assert "their ancestors" in team.show()
    assert "themselves" in team.show()
    assert "everyone" in team.show()
    assert "the previous role" in team.show()


def test_equal_teams_print_alike():
    one = Team.loads('[roles.a]\nharness = "pi"\n[roles.b]\nharness = "pi"')
    two = Team.loads('[roles.b]\nharness = "pi"\n[roles.a]\nharness = "pi"')
    assert one == two
    assert one.show() == two.show()
    assert one.show(resolved=True) == two.show(resolved=True)


def test_show_refuses_an_unresolved_team():
    team = Team.loads('extensions = ["x"]\n[roles.a]\nharness = "pi"\n[topology.ballot]\nvoters = "a"')
    with pytest.raises(ConfigError, match="waits for an extension"):
        team.show()
    with pytest.raises(ConfigError, match="waits for an extension"):
        team.show(resolved=True)


def test_defaults_stay_out_of_the_resolved_form():
    resolved = tomllib.loads(Team(roles={"a": Role(harness="pi")}).show(resolved=True))
    assert resolved == {"roles": {"a": {"harness": "pi"}}}


def test_the_resolved_form_prints_program_arguments():
    resolved = tomllib.loads(PRESET_TEAMS["git-swarm"].show(resolved=True))
    assert resolved["topology"]["program"]["params"]["uncharged"] == ["abstained"]


def test_several_writers_print_as_a_list_and_one_as_a_string():
    topology = pipeline(["a", "b", "c"], back=True, max_hops=3)
    resolved = tomllib.loads(Team(roles={"a": Role(harness="pi")}, topology=topology).show(resolved=True))
    channels = resolved["topology"]["channels"]
    assert channels["to-a"]["writers"] == ["role:b", "role:c"]
    assert channels["to-b"]["writers"] == "role:a"


def test_a_non_default_delivery_is_shown():
    team = Team(
        roles={"a": Role(harness="pi")},
        topology=Topology(channels={"alerts": Topic(writers="human", readers="all", delivery="steer")}),
    )
    assert "You post to topic `alerts`; everyone reads it. Each entry steers its readers." in team.show()


def test_an_edge_for_all_is_shown_for_each_role():
    team = Team(roles={"a": Role(harness="pi")}, topology=Topology(edges={"all": ["human"], "a": ["self"]}))
    assert "a (pi) may message itself and you." in team.show()


def test_groups_read_as_english():
    roles = {"a": Role(harness="pi"), "b": Role(harness="pi")}
    ordered = Team(roles=roles, topology=Topology(groups={"chain": Group(order=("a", "b"))}))
    named = Team(roles=roles, topology=Topology(groups={"owners": Group(members=("human:ada",))}))
    assert "+chain runs a, then b." in ordered.show()
    assert "+owners is human:ada." in named.show()


def test_plurals_read_as_english():
    team = Team(roles={"boss": Role(harness="pi", count=2), "coach": Role(harness="pi", count=2)})
    assert "Bosses (pi)" in team.show()
    assert "Coaches (pi)" in team.show()


def test_limits_read_in_order():
    team = Team(
        roles={"a": Role(harness="pi")},
        topology=tree("a", max_depth=2, max_children=3) | Topology(limits=Limits(max_live=4)),
    )
    assert "Limits: depth 2, children 3, live 4, hops 8." in team.show()
