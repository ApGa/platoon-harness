"""Mixing is a union: commutative, associative, with no order to get wrong and no way to deny."""

from functools import reduce
from itertools import permutations
from operator import or_

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from platoon_harness.kernel import Grant
from platoon_harness.schema import ConfigError
from platoon_harness.team import Team
from platoon_harness.topology import Board, Group, Limits, Queue, Topic, Topology, blackboard, star, tree, union

MIX = (
    tree("agent", max_depth=6, max_children=4),
    blackboard("agent", board="notes"),
    star("agent", "scout", topic="announcements"),
    Topology(edges={"agent": ["human"]}),
    Topology(channels={"alerts": Topic(writers="human", readers="all", delivery="steer")}),
)


def outcome(parts):
    """A union's hash, or the fact that it conflicts."""
    try:
        return reduce(or_, parts).hash
    except ConfigError:
        return "conflict"


def test_any_permutation_gives_the_same_hash():
    assert len({reduce(or_, order).hash for order in permutations(MIX)}) == 1


def test_grouping_does_not_change_the_hash():
    a, b, c, *_ = MIX
    assert ((a | b) | c).hash == (a | (b | c)).hash


def test_a_union_with_itself_changes_nothing():
    for part in MIX:
        assert (part | part) == part


def test_a_table_and_its_fragments_agree_however_it_was_written():
    keys_first = """
        [roles.agent]
        harness = "pi"
        [topology]
        edges = { agent = ["human"] }
        [topology.blackboard]
        role = "agent"
        [topology.tree]
        role = "agent"
        max_depth = 6
        max_children = 4
    """
    presets_first = """
        [roles.agent]
        harness = "pi"
        [topology.tree]
        max_children = 4
        max_depth = 6
        role = "agent"
        [topology.blackboard]
        role = "agent"
        [topology]
        edges = { agent = ["human"] }
    """
    python = tree("agent", max_depth=6, max_children=4) | blackboard("agent") | Topology(edges={"agent": ["human"]})
    assert Team.loads(keys_first).topology == Team.loads(presets_first).topology == python


names = st.sampled_from(["a", "b", "c"])
selectors = st.lists(st.sampled_from(["parent", "children", "human", "all", "role:a"]), max_size=3)
channels = st.one_of(
    st.builds(Queue, writers=st.just("role:a"), readers=st.just("role:b"), lease=st.sampled_from(["30m", "1h"])),
    st.builds(Topic, writers=st.just("all"), readers=st.just("all")),
    st.builds(Board, writers=st.just("all"), readers=st.just("all")),
)
fragments = st.builds(
    Topology,
    edges=st.dictionaries(names, selectors, max_size=2),
    channels=st.dictionaries(names, channels, max_size=2),
    groups=st.dictionaries(names, st.builds(Group, roles=st.lists(names, min_size=1, max_size=2)), max_size=2),
    limits=st.builds(Limits, max_hops=st.sampled_from([None, 4, 8]), max_depth=st.sampled_from([None, 2])),
    until=st.sampled_from([None, "settled", "program"]),
    grants=st.lists(st.builds(Grant, who=st.just("all"), ops=st.sampled_from(["x.*", "y.*"])), max_size=2),
)


@settings(deadline=None)
@given(st.lists(fragments, min_size=1, max_size=3))
def test_any_order_of_any_fragments_gives_one_outcome(parts):
    assert len({outcome(order) for order in permutations(parts)}) == 1


@settings(deadline=None)
@given(fragments, fragments, fragments)
def test_the_union_is_associative(a, b, c):
    def outcome_of(build):
        try:
            return build().hash
        except ConfigError:
            return "conflict"

    assert outcome_of(lambda: (a | b) | c) == outcome_of(lambda: a | (b | c))


def test_two_sources_defining_one_channel_differently_is_a_load_error():
    with pytest.raises(ConfigError) as caught:
        Team.loads(
            """
            [roles.lead]
            harness = "pi"
            [roles.worker]
            harness = "pi"
            [topology.manager-worker]
            manager = "lead"
            workers = "worker"
            [topology.blackboard]
            role = "worker"
            """
        )
    assert "topology.channels.notes" in str(caught.value)
    assert "manager-worker" in str(caught.value)
    assert "blackboard" in str(caught.value)


def test_two_sources_defining_one_channel_alike_is_no_conflict():
    channel = Queue(writers="role:a", readers="role:b")
    assert Topology(channels={"q": channel}) | Topology(channels={"q": channel}) == Topology(channels={"q": channel})


@pytest.mark.parametrize(
    ("left", "right", "where"),
    [
        (Topology(groups={"g": Group(roles=("a",))}), Topology(groups={"g": Group(roles=("b",))}), "topology.groups.g"),
        (Topology(limits=Limits(max_hops=4)), Topology(limits=Limits(max_hops=8)), "topology.limits.max_hops"),
        (Topology(until="program"), Topology(until="settled"), "topology.until"),
    ],
)
def test_anything_else_defined_twice_must_also_agree(left, right, where):
    with pytest.raises(ConfigError, match=where):
        left | right


def test_every_conflict_is_reported_at_once():
    left = Topology(limits=Limits(max_hops=4), until="program")
    right = Topology(limits=Limits(max_hops=8), until="settled")
    with pytest.raises(ConfigError) as caught:
        union([("one", left), ("two", right)])
    assert {problem.where for problem in caught.value.problems} == {"topology.limits.max_hops", "topology.until"}


def test_edges_and_grants_only_add_up():
    a = Topology(edges={"x": ["parent"]}, grants=[Grant(who="all", ops="a.*")])
    b = Topology(edges={"x": ["children"]}, grants=[Grant(who="all", ops="b.*")])
    assert (a | b).edges == {"x": ("children", "parent")}
    assert len((a | b).grants) == 2


def test_there_is_no_deny():
    with pytest.raises(ValidationError, match="deny"):
        Topology(deny={"worker": ["human"]})
    with pytest.raises(ConfigError, match="not a key of"):
        Team.loads('[roles.a]\nharness = "pi"\n[topology]\ndeny = ["human"]')


def test_a_hash_ignores_how_a_value_was_spelled():
    assert Topology(edges={"a": ["human", "parent", "parent"]}).hash == Topology(edges={"a": ("parent", "human")}).hash
    assert Queue(writers="all", readers="all", lease="60m") == Queue(writers=["all"], readers=("all",), lease="1h")


def test_a_hash_does_not_drift():
    fragment = Topology(edges={"a": ["parent"]}, channels={"q": Queue(writers="role:a", readers="role:b", lease="30m")})
    assert fragment.hash == "f9672f9d631dab3b8cb1b74083cdc86b7143dbe7df513643398b54ec151f144a"


def test_an_empty_edge_list_is_no_edge():
    assert Topology(edges={"a": []}) == Topology()
