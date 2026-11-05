"""`team_check`: a pure function that reports every problem at once, before any cost."""

import pytest

from platoon_harness.kernel import Extension, Grant
from platoon_harness.schema import ConfigError, Problem
from platoon_harness.team import Budget, Capabilities, Command, Role, Team, team_check
from platoon_harness.tools import PREAMBLE
from platoon_harness.topology import (
    Group,
    Limits,
    Queue,
    Topic,
    Topology,
    Unexpanded,
    manager_worker,
    mesh,
    pipeline,
    star,
    tree,
)

from .support import CAPABILITIES, MEASURING, PRESET_TEAMS

BLIND = Capabilities(persistent=True)


def check(team, capabilities=CAPABILITIES, extensions=None):
    return team_check(team, capabilities=capabilities, extensions=extensions)


def errors(team, **kwargs):
    return [str(problem) for problem in check(team, **kwargs) if problem.level == "error"]


def warnings(team, **kwargs):
    return [str(problem) for problem in check(team, **kwargs) if problem.level == "warning"]


def text(problems):
    return "\n".join(problems)


def lead_and_worker(**limits: int) -> Team:
    """A lead that may spawn a worker on a persistent harness and message it, written out by hand."""
    roles = {"lead": Role(harness="claude", may_spawn=["worker"]), "worker": Role(harness="codex")}
    edges = {"lead": ["children", "human"], "worker": ["parent"]}
    return Team(roles=roles, topology={"edges": edges, "limits": limits})


def test_a_sound_team_has_no_problems():
    assert check(PRESET_TEAMS["manager-worker"]) == ()


@pytest.mark.parametrize("preset", PRESET_TEAMS)
def test_no_shipped_preset_sets_off_a_warning_of_a_wake_cycle(preset):
    assert "wake cycle" not in text(warnings(PRESET_TEAMS[preset]))


def test_recursive_may_spawn_with_no_max_depth_is_refused():
    team = Team(roles={"agent": Role(harness="pi", may_spawn=["agent"])})
    assert "recursive may_spawn" in text(errors(team))


def test_mutually_recursive_may_spawn_is_refused():
    team = Team(roles={"a": Role(harness="pi", may_spawn=["b"]), "b": Role(harness="pi", may_spawn=["a"])})
    assert "a -> b -> a" in text(errors(team)) or "b -> a -> b" in text(errors(team))


def test_max_depth_answers_recursion():
    assert (
        errors(
            Team(
                roles={"agent": Role(harness="pi", may_spawn=["agent"])},
                topology=tree("agent", max_depth=2, max_children=2),
            )
        )
        == []
    )


def test_a_wake_cycle_with_no_max_hops_is_refused():
    team = Team(
        roles={"a": Role(harness="pi"), "b": Role(harness="pi")},
        topology=pipeline(["a", "b"], back=True),
    )
    assert "wake cycle" in text(errors(team))


def test_a_self_waking_topic_is_a_cycle():
    channel = Topic(writers="role:a", readers="role:a", delivery="wake")
    team = Team(roles={"a": Role(harness="pi")}, topology=Topology(channels={"chatter": channel}))
    assert "wake cycle" in text(errors(team))


def test_a_cycle_that_wakes_no_one_is_no_cycle():
    team = Team(
        roles={"a": Role(harness="pi"), "b": Role(harness="pi")},
        topology=Topology(
            channels={
                "one": Queue(writers="role:a", readers="role:b"),
                "two": Queue(writers="role:b", readers="role:a"),
            }
        ),
    )
    assert errors(team) == []


def test_peer_messages_in_a_loop_are_a_cycle():
    team = Team(
        roles={"a": Role(harness="pi"), "b": Role(harness="pi")},
        topology=Topology(edges={"a": ["role:b"], "b": ["role:a"]}),
    )
    assert "wake cycle" in text(errors(team))


def test_a_loop_into_inboxes_that_do_not_wake_is_no_cycle():
    team = Team(
        roles={"a": Role(harness="pi", delivery="next-turn"), "b": Role(harness="pi")},
        topology=Topology(edges={"a": ["role:b"], "b": ["role:a"]}),
    )
    assert errors(team) == []


def test_a_reply_up_a_tree_is_no_cycle():
    assert errors(PRESET_TEAMS["manager-worker"]) == []


def test_max_hops_answers_a_cycle():
    team = Team(
        roles={"a": Role(harness="pi"), "b": Role(harness="pi")},
        topology=pipeline(["a", "b"], back=True, max_hops=4),
    )
    assert errors(team) == []


def test_a_parent_and_a_child_that_can_stay_are_a_wake_cycle_to_warn_of():
    team = lead_and_worker()

    assert errors(team) == []
    found = text(warnings(team))
    assert "a wake cycle with no limit, through a child that can stay:" in found
    assert "lead -> worker -> lead" in found or "worker -> lead -> worker" in found
    assert "set `max_hops`" in found


def test_max_hops_bounds_a_parent_and_a_child_that_can_stay():
    assert warnings(lead_and_worker(max_hops=8)) == []


@pytest.mark.parametrize("why", ["one-shot", "quiet", "out of reach"])
def test_a_child_that_cannot_stay_or_be_woken_by_its_parent_closes_no_such_cycle(why):
    worker = Role(harness="exec" if why == "one-shot" else "codex", delivery="pull" if why == "quiet" else "wake")
    edges = {"lead": ["human"]} if why == "out of reach" else {"lead": ["children", "human"]}
    team = Team(
        roles={"lead": Role(harness="claude", may_spawn=["worker"]), "worker": worker}, topology={"edges": edges}
    )
    capabilities = {**CAPABILITIES, "exec": Capabilities(persistent=False)}

    assert "through a child that can stay" not in text(warnings(team, capabilities=capabilities))


def test_a_role_that_stays_on_a_harness_that_cannot_is_refused():
    team = Team(
        roles={"lead": Role(harness="claude", may_spawn=["worker"]), "worker": Role(harness="exec", stays=True)},
        topology={"limits": {"max_hops": 4}},
    )

    found = errors(team, capabilities={**CAPABILITIES, "exec": Capabilities(persistent=False)})

    assert found == ["roles.worker.stays: a one-shot harness ends with its turn, so it cannot stay"]


def test_a_role_that_allows_its_harness_s_own_agents_is_told_what_is_lost():
    team = Team(roles={"lead": Role(harness="claude", allow_native_children=True)})
    capabilities = {"claude": Capabilities(persistent=True, native_children="observed")}

    assert warnings(team, capabilities=capabilities) == [
        "roles.lead.allow_native_children: its harness's own agents are none of ours: their calls reach us only in "
        "their parent's total, no topology binds them, and their calls to our tools go out on their parent's token"
    ]


def test_a_role_that_allows_agents_its_harness_never_starts_is_told_so():
    team = Team(roles={"lead": Role(harness="pi", allow_native_children=True)})

    assert warnings(team, capabilities={"pi": BLIND}) == [
        "roles.lead.allow_native_children: `pi` starts no agents of its own, so this allows nothing"
    ]


def test_a_template_that_leaves_out_how_to_reach_tools_or_how_to_end_is_told_what_breaks():
    team = Team(preamble="You are @{name}.", roles={"lead": Role(harness="claude", preamble="{tools}")})

    tools = "leaves out `{tools}`: a harness can keep a server's tools from a model that knows none of their names"
    ending = "leaves out `{ending}`: an agent never told how to end can leave its parent waiting for ever"

    assert warnings(team) == [f"preamble: {tools}", f"preamble: {ending}", f"roles.lead.preamble: {ending}"]


def test_an_empty_template_is_checked_as_the_one_its_agents_are_told():
    team = Team(preamble="Team words.\n{tools}\n{ending}", roles={"lead": Role(harness="claude", preamble="")})

    assert warnings(team) == [
        "roles.lead.preamble: leaves out `{tools}`: a harness can keep a server's tools from a model that knows none "
        "of their names",
        "roles.lead.preamble: leaves out `{ending}`: an agent never told how to end can leave its parent waiting for "
        "ever",
    ]


def test_words_that_name_a_tool_a_role_does_not_hold_are_warned_of():
    lead = Role(harness="claude", instructions="Post with `board.post`, then `agent.finish`.")
    team = Team(preamble=f"{PREAMBLE}\nClaim with `task.claim`.", roles={"lead": lead})

    assert warnings(team) == [
        "preamble: names `task.claim`, which `lead` cannot hold: its agents are told of a tool they cannot call",
        "roles.lead.instructions: names `board.post`, which `lead` cannot hold: its agents are told of a tool they "
        "cannot call",
    ]


def test_a_tool_held_through_a_grant_to_a_named_agent_is_no_tool_a_role_cannot_hold():
    """A group's members, and so a channel's writers, can name an agent, whose name a session chooses as it runs."""
    topology = {
        "groups": {"g": {"members": ["agent:lead"]}},
        "channels": {"notes": {"kind": "board", "writers": "group:g", "readers": "all"}},
    }
    team = Team(
        preamble=f"{PREAMBLE}\nPost notes with `board.post`.", roles={"lead": Role(harness="claude")}, topology=topology
    )

    assert warnings(team) == []


def test_a_template_a_harness_that_reaches_none_of_our_tools_is_never_told_is_said():
    """Its agents are told `instructions` alone, so a role's own template there is refused, and its team's is a
    warning, with nothing said of what either leaves out or names."""
    capabilities = {**CAPABILITIES, "pi": BLIND}
    own = Team(roles={"bob": Role(harness="pi", preamble="Say OK. You are @{name}.")})
    inherited = Team(
        preamble="Say OK.\n{tools}\n{ending}", roles={"bob": Role(harness="pi", instructions="Use `wait`.")}
    )

    assert check(own, capabilities=capabilities) == (
        Problem(
            "roles.bob.preamble",
            "`pi` reaches none of our tools, so its agents are told `instructions` alone: say it there",
        ),
    )
    assert warnings(inherited, capabilities=capabilities) == [
        "preamble: `bob` is told none of this: `pi` reaches none of our tools, so its agents are told `instructions` "
        "alone"
    ]


def test_a_template_with_a_slot_nobody_fills_is_refused_when_the_team_loads():
    with pytest.raises(ConfigError, match=r"roles\.lead\.preamble: no slot `\{nam\}`\. Did you mean `name`\?"):
        Team.loads('[roles.lead]\nharness = "claude"\npreamble = "You are @{nam}."\n')


def test_a_tokens_or_usd_limit_with_no_estimate_is_refused_naming_what_to_give():
    team = Team(
        roles={"a": Role(harness="claude", budget=Budget(tokens=5))},
        budget=Budget(tokens=1000, estimate={"usd": 1}),
    )
    found = errors(team, capabilities={"claude": MEASURING})
    tail = "what a turn nobody measured whole is charged on top"
    assert found == [
        f"roles.a.budget.estimate: a tokens limit needs `estimate.tokens`: {tail}",
        f"budget.estimate: a tokens limit needs `estimate.tokens`: {tail}",
    ]


def test_a_role_s_limit_holds_on_the_team_s_estimate_where_the_role_has_none():
    """As a reservation does: a role's own estimate goes over the team's, unit by unit."""
    team = Team(
        roles={"a": Role(harness="claude", budget=Budget(usd=5, estimate={"tokens": 10}))},
        budget=Budget(estimate={"usd": 1}),
    )

    assert errors(team, capabilities={"claude": MEASURING}) == []


def test_a_limit_in_a_unit_a_harness_cannot_measure_holds_on_its_estimates_and_says_so():
    capabilities = {"pi": BLIND, "claude": MEASURING}
    team = Team(
        roles={
            "a": Role(harness="claude", budget=Budget(tokens=1000, estimate={"tokens": 100})),
            "b": Role(harness="pi", budget=Budget(tokens=10, estimate={"tokens": 5})),
        }
    )
    assert errors(team, capabilities=capabilities) == []
    assert (
        "roles.b.budget.tokens: `pi` cannot measure tokens, so each of its turns is charged its estimate"
        in warnings(team, capabilities=capabilities)
    )
    assert "roles.a.budget.tokens" not in text(warnings(team, capabilities=capabilities))


def test_the_runtime_measures_turns_agents_and_wall_for_everyone():
    team = Team(roles={"a": Role(harness="pi")}, budget=Budget(turns=5, agents=2, wall="2h"))
    assert errors(team, capabilities={"pi": BLIND}) == []


def test_an_unknown_harness_gets_a_did_you_mean():
    assert "unknown harness `cluade`. Did you mean `claude`?" in text(errors(Team(roles={"a": Role(harness="cluade")})))


def test_a_command_harness_runs_under_exec():
    role = Role(harness=Command(command=["my-agent", "{goal}"]))
    assert errors(Team(roles={"a": role})) == []
    assert "unknown harness `exec`" in text(errors(Team(roles={"a": role}), capabilities={}))


def test_an_unsupported_sandbox_fails():
    team = Team(roles={"a": Role(harness="pi", sandbox="read-onyl")})
    assert "no sandbox `read-onyl`. Did you mean `read-only`?" in text(errors(team))


def test_an_unknown_preset_gets_a_did_you_mean_at_load():
    with pytest.raises(ConfigError, match=r"unknown preset `blackbord`\. Did you mean `blackboard`\?"):
        Team.loads('[roles.a]\nharness = "pi"\n[topology.blackbord]\nrole = "a"')


def test_a_preset_can_wait_only_for_an_extension_the_team_names():
    team = Team.loads('extensions = ["hubs"]\n[roles.a]\nharness = "pi"\n[topology.hub]\ncenter = "a"')
    assert [item.preset for item in team.topology.unexpanded] == ["hub"]


def test_unexpanded_is_no_key_of_a_topology():
    with pytest.raises(ConfigError, match="not a key"):
        Team.loads('[roles.a]\nharness = "pi"\n[topology]\nunexpanded = "x"')


def test_an_unknown_extension_gets_a_did_you_mean():
    team = Team(roles={"a": Role(harness="pi")}, extensions=["balot"])
    assert "unknown extension `balot`. Did you mean `ballot`?" in text(
        errors(team, extensions={"ballot": Extension("ballot")})
    )


def test_an_unknown_role_in_may_spawn_gets_a_did_you_mean():
    team = Team(roles={"worker": Role(harness="pi", may_spawn=["wroker"])})
    assert "unknown role `wroker`. Did you mean `worker`?" in text(errors(team))


def test_an_unknown_role_in_a_selector_gets_a_did_you_mean():
    team = Team(
        roles={"worker": Role(harness="pi")},
        topology=Topology(
            edges={"worker": ["role:wroker"]}, channels={"q": Queue(writers="role:worke", readers="all")}
        ),
    )
    found = text(errors(team))
    assert "topology.edges.worker: unknown role `wroker`" in found
    assert "topology.channels.q.writers: unknown role `worke`" in found


def test_an_unknown_role_in_until_is_refused():
    assert "unknown role `boss`" in text(
        errors(Team(roles={"a": Role(harness="pi")}, topology=Topology(until="role:boss")))
    )


def test_until_program_needs_a_program():
    assert "needs a `program`" in text(
        errors(Team(roles={"a": Role(harness="pi")}, topology=Topology(until="program")))
    )


def test_an_unknown_auth_profile_gets_a_did_you_mean():
    team = Team(roles={"a": Role(harness="pi", auth="wrok")}, auth={"work": {"env": ["WORK_KEY"]}})
    assert "unknown profile. Did you mean `work`?" in text(errors(team))


def test_a_key_pasted_as_a_profile_is_not_repeated():
    team = Team(roles={"a": Role(harness="pi", auth="sk-hunter2")})
    assert "hunter2" not in text(errors(team))


def test_a_relation_that_no_may_spawn_makes_true_is_warned():
    team = Team(
        roles={"lead": Role(harness="pi"), "worker": Role(harness="pi", count=3)},
        topology=manager_worker("lead", "worker"),
    )
    found = warnings(team)
    assert any("`children` reaches nobody" in line for line in found)
    assert any("`parent` reaches nobody" in line for line in found)


def test_team_check_refuses_a_program_it_cannot_run():
    """No program runs yet, so a team left to one would never get what it waits for: refused, naming it."""
    team = Team(roles={"a": Role(harness="pi")}, topology=Topology(program="nope", until="program"))
    assert errors(team) == ["topology.program: `nope` cannot run: no program runs yet, so nothing it does happens"]


def test_recursion_through_a_written_grant_is_seen():
    written = Grant(who="role:a", ops="agent.spawn", on="role/a")
    team = Team(roles={"a": Role(harness="pi")}, topology=Topology(grants=[written]))
    assert "recursive may_spawn with no limit" in text(errors(team))


def test_recursion_through_a_glob_is_seen():
    written = Grant(who="all", ops="agent.*", on="role/*")
    team = Team(roles={"a": Role(harness="pi")}, topology=Topology(grants=[written]))
    assert "recursive may_spawn with no limit" in text(errors(team))


def test_a_written_grant_of_spawning_makes_a_spawner_as_may_spawn_does():
    written = Grant(who="role:a", ops="agent.spawn", on="role/b")
    team = Team(roles={"a": Role(harness="pi"), "b": Role(harness="pi")}, topology=Topology(grants=[written]))

    assert (team.spawners("b"), team.starts("b")) == ({"a"}, [])


def test_a_grant_of_another_op_is_no_spawning():
    written = Grant(who="role:a", ops="board.*", on="role/a")
    team = Team(roles={"a": Role(harness="pi")}, topology=Topology(grants=[written]))
    assert errors(team) == []


def test_a_channel_cannot_use_a_relation():
    team = Team(
        roles={"a": Role(harness="pi")}, topology=Topology(channels={"q": Queue(writers="parent", readers="all")})
    )
    assert "`parent` needs an agent" in text(errors(team))


def test_every_problem_is_reported_at_once():
    team = Team.loads(
        """
        extensions = ["balot"]

        [roles.agent]
        harness = "cluade"
        may_spawn = ["agent", "ghost"]
        sandbox = "nope"
        auth = "missing"

        [roles.quiet]
        harness = "pi"
        count = 0

        [budget]
        usd = 1

        [topology.blackbord]
        role = "agent"

        [topology.channels.storm]
        kind = "topic"
        writers = "role:agent"
        readers = "role:agent"
        delivery = "wake"
        """
    )
    report = team_check(team, capabilities={"pi": BLIND}, extensions={"ballot": Extension("ballot")})
    wheres = {problem.where for problem in report}
    assert wheres >= {
        "extensions",
        "topology.blackbord",
        "roles.agent.harness",
        "roles.agent.may_spawn",
        "roles.agent.auth",
        "budget.usd",
        "topology.limits.max_depth",
        "topology.limits.max_hops",
        "roles.quiet",
        "topology.channels.storm.delivery",
    }


def test_team_check_is_pure():
    team = PRESET_TEAMS["mesh"]
    assert check(team) == check(team)
    assert team == PRESET_TEAMS["mesh"]


def test_a_count_of_zero_was_said_on_purpose_and_is_no_warning():
    team = Team(roles={"lead": Role(harness="pi"), "later": Role(harness="pi", count=0)})

    assert "never starts" not in text(warnings(team))


def test_a_one_shot_role_that_starts_with_the_session_has_no_goal_and_is_refused():
    one_shot = Capabilities()
    team = Team(roles={"lead": Role(harness="pi")})

    assert "set `count = 0`" in text(errors(team, capabilities={"pi": one_shot}))


def test_a_one_shot_role_that_is_spawned_is_sound():
    team = Team(roles={"lead": Role(harness="claude"), "worker": Role(harness="pi", count=0)})

    assert errors(team, capabilities={"claude": MEASURING, "pi": Capabilities()}) == []


def test_a_one_shot_role_only_another_role_spawns_is_sound():
    team = Team(roles={"lead": Role(harness="claude", may_spawn=["worker"]), "worker": Role(harness="pi")})

    assert errors(team, capabilities={"claude": MEASURING, "pi": Capabilities()}) == []


def test_a_one_shot_parent_is_warned_that_its_children_end_with_its_turn():
    team = Team(
        roles={
            "lead": Role(harness="pi", may_spawn=["brief"]),
            "brief": Role(harness="brief", count=0, may_spawn=["worker", "helper"]),
            "worker": Role(harness="pi"),
            "helper": Role(harness="pi", on_parent_exit="adopt"),
        },
        topology=Topology(limits=Limits(max_depth=3)),
    )

    capabilities = {"pi": MEASURING, "brief": Capabilities()}
    found = [problem for problem in warnings(team, capabilities=capabilities) if "one-shot" in problem]

    assert found == [
        "roles.brief.may_spawn: a one-shot harness ends with its turn, and that cancels `worker` however far along it "
        'is: wait for it within the turn, or set `on_parent_exit = "adopt"` on that role'
    ]


def test_a_role_only_a_never_started_role_spawns_never_starts():
    team = Team(
        roles={
            "root": Role(harness="pi", count=0, may_spawn=["leaf"]),
            "leaf": Role(harness="pi"),
        }
    )
    assert [w for w in warnings(team) if "never starts" in w] == [
        "roles.leaf: never starts: nothing that starts can spawn it"
    ]


def test_a_role_with_no_path_to_anyone_is_a_warning():
    team = Team(roles={"lead": Role(harness="pi"), "worker": Role(harness="pi")})
    found = warnings(team)
    assert "roles.lead: has no path to anyone" in found
    assert "roles.worker: has no path to anyone" in found


def test_a_lone_role_is_not_cut_off_from_anyone():
    assert warnings(Team(roles={"solo": Role(harness="pi")})) == []


def test_a_spawned_role_reaches_its_parent_through_the_monitor():
    team = Team(roles={"lead": Role(harness="pi", may_spawn=["worker"]), "worker": Role(harness="pi")})
    assert warnings(team) == []


def test_a_wake_topic_with_large_fan_out_is_a_warning():
    channel = Topic(writers="human", readers="role:peer", delivery="wake")
    team = Team(roles={"peer": Role(harness="pi", count=32)}, topology=Topology(channels={"alerts": channel}))
    assert "can wake 32 agents" in text(warnings(team))


def test_a_wake_topic_over_an_unbounded_role_is_a_warning():
    channel = Topic(writers="human", readers="all", delivery="steer")
    team = Team(
        roles={"lead": Role(harness="pi", may_spawn=["peer"]), "peer": Role(harness="pi")},
        topology=Topology(channels={"alerts": channel}),
    )
    assert "an unbounded number of agents" in text(warnings(team))


def test_max_live_bounds_a_spawned_fan_out():
    channel = Topic(writers="human", readers="role:peer", delivery="wake")
    team = Team(
        roles={"lead": Role(harness="pi", may_spawn=["peer"]), "peer": Role(harness="pi")},
        topology=Topology(channels={"alerts": channel}, limits=Limits(max_live=4)),
    )
    assert warnings(team) == []


def test_a_quiet_topic_never_warns_of_fan_out():
    team = Team(roles={"peer": Role(harness="pi", count=64)}, topology=mesh("peer"))
    assert not any("wake" in warning for warning in warnings(team))


@pytest.mark.parametrize(
    ("kind", "setting"),
    [("topic", "digest"), ("topic", "entry"), ("topic", "requires"), ("topic", "validator"), ("board", "keys")],
)
def test_a_channel_setting_nothing_enforces_is_no_setting(kind, setting):
    """A setting nothing would enforce is refused where it is written, as any unknown key is."""
    written = f"[roles.a]\nharness = 'pi'\n[topology.channels.c]\nkind = '{kind}'\nreaders = 'all'\nwriters = 'all'\n"
    with pytest.raises(ConfigError) as refused:
        Team.loads(f"{written}{setting} = 'x'\n")
    found = [str(problem) for problem in refused.value.problems]
    assert found == [f"topology.channels.c.{kind}.{setting}: `{setting}` is not a key here."]


def test_a_member_is_a_principal_id_and_never_a_glob():
    with pytest.raises(ValueError, match="pattern"):
        Group(members=("agent:*",))
    with pytest.raises(ValueError, match="pattern"):
        Group(members=("ada",))


def test_a_name_cannot_smuggle_a_glob_into_a_grant():
    with pytest.raises(ConfigError, match="pattern"):
        Team.loads('[roles."*"]\nharness = "pi"')
    with pytest.raises(ConfigError, match="pattern"):
        Team.loads('[roles.a]\nharness = "pi"\n[topology.blackboard]\nrole = "a"\nboard = "*"')


def test_an_extensions_preset_has_the_same_power_as_a_builtin():
    def hub(center: str, rim: str, *, max_hops: int = 8) -> Topology:
        return star(center, rim, max_hops=max_hops)

    extension = Extension("hubs", presets=[hub])
    text_form = """
    extensions = ["hubs"]
    [roles.c]
    harness = "pi"
    [roles.r]
    harness = "pi"
    [topology.hub]
    center = "c"
    rim = "r"
    """
    team = Team.loads(text_form)
    assert errors(team, extensions={"hubs": extension}) == []
    resolved = team.resolved({"hubs": extension})
    assert resolved.topology == star("c", "r")
    assert Team.loads(resolved.show(resolved=True)) == resolved


def test_a_builtin_written_as_unexpanded_still_expands():
    team = Team(
        roles={"a": Role(harness="pi", may_spawn=["a"])},
        topology=Topology(
            unexpanded=[Unexpanded(preset="tree", params={"role": "a", "max_depth": 2, "max_children": 2})]
        ),
    )
    assert team.resolved().topology == tree("a", max_depth=2, max_children=2)


def test_a_preset_is_active_only_if_its_extension_is_named():
    def hub(center: str) -> Topology:
        return Topology(edges={center: ["human"]})

    team = Team.loads('extensions = ["other"]\n[roles.c]\nharness = "pi"\n[topology.hub]\ncenter = "c"')
    known = {"other": Extension("other"), "hubs": Extension("hubs", presets=[hub])}
    assert "unknown preset `hub`" in text(errors(team, extensions=known))


def test_an_extension_cannot_shadow_a_builtin_preset():
    def tree(role: str) -> Topology:
        return Topology()

    team = Team(roles={"a": Role(harness="pi")}, extensions=["evil"])
    assert "preset `tree` is defined twice" in text(
        errors(team, extensions={"evil": Extension("evil", presets=[tree])})
    )


def test_a_conflict_with_an_extensions_preset_is_a_problem_too():
    def notes(role: str) -> Topology:
        return Topology(limits=Limits(max_hops=2))

    team = Team.loads(
        """
        extensions = ["x"]
        [roles.a]
        harness = "pi"
        [topology]
        limits = { max_hops = 3 }
        [topology.notes]
        role = "a"
        """
    )
    assert "defined differently" in text(errors(team, extensions={"x": Extension("x", presets=[notes])}))


def test_resolving_reports_what_cannot_be_expanded():
    team = Team.loads('extensions = ["x"]\n[roles.a]\nharness = "pi"\n[topology.ballot]\nvoters = "a"')
    with pytest.raises(ConfigError, match="unknown preset `ballot`"):
        team.resolved({"x": Extension("x")})


def test_a_broken_extension_preset_is_a_problem_not_a_crash():
    def needs_a_table(role: str) -> Topology:
        raise ValueError("this preset is unhappy")

    team = Team.loads('extensions = ["x"]\n[roles.a]\nharness = "pi"\n[topology.needs-a-table]\nrole = "a"')
    assert "this preset is unhappy" in text(errors(team, extensions={"x": Extension("x", presets=[needs_a_table])}))


def test_a_preset_must_return_a_topology():
    def wrong(role: str) -> dict:
        return {}

    team = Team.loads('extensions = ["x"]\n[roles.a]\nharness = "pi"\n[topology.wrong]\nrole = "a"')
    assert "must return a Topology" in text(errors(team, extensions={"x": Extension("x", presets=[wrong])}))


def test_problems_print_as_place_and_reason():
    assert str(Problem("roles.a", "broken")) == "roles.a: broken"


def test_groups_and_selectors_are_validated_at_load():
    with pytest.raises(ConfigError) as caught:
        Team.loads(
            """
            [roles.a]
            harness = "pi"
            [topology]
            edges = { a = ["chidlren", "lead"] }
            [topology.groups.g]
            roles = ["a"]
            order = ["a"]
            """
        )
    found = str(caught.value)
    assert "unknown selector `chidlren`. Did you mean `children`?" in found
    assert "unknown selector `lead`" in found
    assert "A role is `role:x`" in found
    assert "exactly one of" in found


def test_a_star_and_a_mesh_bound_their_own_hops():
    assert (
        errors(Team(roles={"hub": Role(harness="pi"), "spoke": Role(harness="pi")}, topology=star("hub", "spoke")))
        == []
    )
    assert errors(Team(roles={"peer": Role(harness="pi")}, topology=mesh("peer"))) == []


def test_groups_and_orders_resolve_in_cycles():
    team = Team(
        roles={"a": Role(harness="pi"), "b": Role(harness="pi")},
        topology=Topology(groups={"ring": Group(order=("a", "b"))}, edges={"a": ["next"], "b": ["prev"]}),
    )
    assert "wake cycle" in text(errors(team))


def test_a_manager_worker_mix_with_a_tree_agrees_on_when_to_close():
    team = Team(
        roles={
            "lead": Role(harness="pi", may_spawn=["worker"]),
            "worker": Role(harness="pi", may_spawn=["worker"]),
        },
        topology=manager_worker("lead", "worker") | tree("worker", max_depth=3, max_children=2, until="role:lead"),
    )
    assert errors(team) == []
