"""The team editor's shared part: fields made from the team's schema, of the keys a person sets from a client and no
other; a draft written as the file's own text, keeping its comments, order and layout; every problem the loader and
`team check` find, at its field; `team show`'s sentences of it and its diff; and the save, whole, over the file as it
was read, never through a link, asking first of a value only trust may take."""

import hashlib
import os
import tomllib
from pathlib import Path

import pytest

from platoon_harness import ConfigError, Team, load_team
from platoon_harness.config import PROJECT_FILE
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.codex import CodexDriver
from platoon_harness_cli import machine, team_editor
from platoon_harness_cli.team_editor import ROLE, SAVING, Asked, Draft, Edit, Field, Harness, draft, edits_of, save

CLAUDE = Harness("claude", "2.1.316 (Claude Code), login unknown, not checked: --check checks it", ())
CODEX = Harness("codex", "not on PATH", ("danger-full-access", "read-only", "workspace-write"))
HARNESSES = (CLAUDE, CODEX)
STARTER = """\
# A team for this project: a lead on claude, which starts workers on codex.
# `platoon-harness team show` says what it allows.

[roles.lead]
harness = "claude"   # the lead
may_spawn = ["worker"]

# The worker, which the lead starts.
[roles.worker]
harness = "codex"
model = "gpt-6"  # cheap

# How they reach each other.
[topology.manager-worker]
manager = "lead"
workers = "worker"
# The end.
"""


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project folder with no harness on PATH and a config and a root of its own."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("PLATOON_HARNESS_CONFIG", raising=False)
    folder = tmp_path / "project"
    folder.mkdir()
    monkeypatch.chdir(folder)
    return folder


def written(here: Path, text: str = STARTER) -> Path:
    (here / PROJECT_FILE).write_text(text)
    return here / PROJECT_FILE


def drafted(here: Path, *edits: Edit) -> Draft:
    return draft(here, edits, HARNESSES)


def fields(found: Draft) -> dict[str, Field]:
    return {field.where: field for section in found.sections for group in section.groups for field in group.fields}


def problems(found: Draft) -> dict[str, list[str]]:
    """Every problem of a draft by where it is shown: a field, a table, or `top`."""
    shown: dict[str, list[str]] = {"top": [str(problem) for problem in found.problems]}
    for section in found.sections:
        for group in section.groups:
            shown[group.where] = [str(problem) for problem in group.problems]
            for field in group.fields:
                shown[field.where] = [str(problem) for problem in field.problems]
    return {where: said for where, said in shown.items() if said}


def setting(where: str, text: str) -> Edit:
    return Edit("set", tuple(where.split(".")), text)


def test_a_role_s_fields_are_the_keys_a_person_sets_from_a_client_made_from_the_schema(here):
    """Each takes what its type takes, in the reference's words, with its default, the role's docstring's sentence that
    names it, and the choices a literal gives. The rest of a role's keys are kept as the file has them."""
    written(here, STARTER.replace('may_spawn = ["worker"]', 'may_spawn = ["worker"]\ntools = ["message.*"]'))

    found = drafted(here)
    role = found.sections[0].groups[0]
    shown = fields(found)

    assert [field.path[-1] for field in role.fields] == list(ROLE)
    assert role.kept == ("tools",) and role.removable
    assert {key: shown[f"roles.lead.{key}"].kind for key in ROLE} == {
        "harness": "choice",
        "model": "text",
        "effort": "text",
        "approvals": "choice",
        "workspace": "choice",
        "sandbox": "choice",
        "instructions": "lines",
        "auth": "choice",
        "count": "integer",
        "stays": "yes-no",
        "may_spawn": "list",
    }
    approvals = shown["roles.lead.approvals"]
    assert [choice.value for choice in approvals.choices] == ["ask", "deny", "allow"]
    assert (
        approvals.help == 'Type: `"ask"`, `"deny"` or `"allow"`. Default: `"ask"`.'
        and approvals.empty == 'left out: "ask"'
    )
    assert shown["roles.lead.effort"].help.startswith("`effort` goes to the harness as it stands")
    assert shown["roles.lead.count"].help.endswith("Type: integer, at least 0. Default: none.")
    assert shown["roles.lead.may_spawn"].text == "worker"
    assert shown["roles.lead.may_spawn"].help.endswith("Separate several with commas.")
    assert shown["roles.worker.model"].text == "gpt-6"


def test_a_harness_is_chosen_from_the_drivers_this_machine_has_with_what_doctor_finds(here, tmp_path, monkeypatch):
    """Each with what `doctor` says of it after its name, its login's kind among it, and a harness the file names that
    is no driver's, such as a `module:attr`, is shown as the file has it, which choosing again changes nothing."""
    folder = tmp_path / "bin"
    folder.mkdir()
    (folder / "claude").write_text('#!/bin/sh\n[ "$1" = --version ] && echo "2.1.316 (Claude Code)"\nexit 0\n')
    (folder / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}:/usr/bin:/bin")
    monkeypatch.setattr(machine, "harnesses", lambda: [("claude", ClaudeDriver()), ("codex", CodexDriver())])
    written(here, STARTER.replace('harness = "codex"', 'harness = "tests.integration.scripts:saying"'))

    found = team_editor.harnesses()
    again = draft(here, [setting("roles.worker.harness", "tests.integration.scripts:saying")], found)
    harness = fields(again)["roles.worker.harness"]

    assert [(item.name, item.said.partition(",")[0]) for item in found] == [
        ("claude", "2.1.316 (Claude Code)"),
        ("codex", "not on PATH"),
    ]
    assert "login unknown" in found[0].said and found[1].sandboxes == (
        "danger-full-access",
        "read-only",
        "workspace-write",
    )
    assert [choice.value for choice in harness.choices] == ["tests.integration.scripts:saying", "claude", "codex"]
    assert harness.choices[0].said == "tests.integration.scripts:saying, as the file has it"
    assert harness.choices[1].said == f"claude: {found[0].said}"
    assert again.diff == "" and again.blocked == "Nothing to save: the draft is the file as it stands."


def test_a_model_is_free_text_and_no_list_of_models_is_made_up(here):
    written(here)

    model = fields(drafted(here))["roles.lead.model"]

    assert model.kind == "text" and model.choices == ()
    assert model.help.startswith("No list of models is offered: no driver says which models its harness takes.")


def test_a_sandbox_is_one_its_harness_declares_and_fixed_saying_why_where_it_declares_none(here):
    written(here)

    shown = fields(drafted(here))

    assert [choice.value for choice in shown["roles.worker.sandbox"].choices] == list(CODEX.sandboxes)
    assert shown["roles.worker.sandbox"].fixed is None
    assert shown["roles.lead.sandbox"].fixed == "`claude` declares no sandbox, so none can be set."
    assert drafted(here, setting("roles.lead.sandbox", "read-only")).blocked == (
        "Fix each change marked first: the editor could not make it."
    )


def test_an_edit_keeps_the_file_s_comments_order_and_layout(here):
    """A value changed in place keeps its line's comment, a new key goes after its table's last and before the comments
    about what follows, a new table goes after the last of its kind with those comments after it, and a removed table
    goes with the comments right above its header, keeping those about what follows it."""
    written(here)

    found = drafted(
        here,
        setting("roles.lead.harness", "codex"),
        setting("roles.worker.model", "gpt-6-luna"),
        setting("roles.worker.effort", "low"),
        Edit("add", ("roles", "critic"), "claude"),
        setting("roles.critic.count", "0"),
        setting("topology.limits.max_hops", "4"),
        setting("budget.usd", "5"),
        setting("budget.estimate.usd", "0.5"),
        Edit("remove", ("roles", "worker")),
        setting("topology.manager-worker.workers", "critic"),
    )

    assert (
        found.text
        == """\
# A team for this project: a lead on claude, which starts workers on codex.
# `platoon-harness team show` says what it allows.

[roles.lead]
harness = "codex"   # the lead
may_spawn = ["worker"]

[roles.critic]
harness = "claude"
count = 0

# How they reach each other.
[topology.manager-worker]
manager = "lead"
workers = ["critic"]

[topology.limits]
max_hops = 4

[budget]
usd = 5

[budget.estimate]
usd = 0.5
# The end.
"""
    )
    assert found.diff.startswith(f"--- {PROJECT_FILE}\n+++ {PROJECT_FILE}\n@@ ")


def test_a_file_written_with_dotted_keys_inline_tables_or_a_table_in_parts_is_edited_in_its_own_form(here):
    """Each edit means what it says once read back, whatever form the file takes."""
    written(
        here,
        'roles.lead.harness = "claude"  # one line each\n'
        'roles.lead.model = "haiku"\n'
        'topology = { until = "role:lead" }\n',
    )
    dotted = drafted(here, setting("roles.lead.model", "sonnet"), setting("topology.limits.max_hops", "3"))
    written(
        here,
        '[roles.lead]\nharness = "claude"\n\n[budget]\nturns = 3\n\n# The critic.\n[roles.critic]\nharness = "codex"\n',
    )
    parts = drafted(here, Edit("add", ("roles", "new"), "claude"), Edit("remove", ("roles", "lead")))

    assert dotted.text == (
        'roles.lead.harness = "claude"  # one line each\n'
        'roles.lead.model = "sonnet"\n'
        'topology = { until = "role:lead", limits = {max_hops = 3}}\n'
    )
    assert tomllib.loads(parts.text) == {
        "roles": {"new": {"harness": "claude"}, "critic": {"harness": "codex"}},
        "budget": {"turns": 3},
    }
    assert "# The critic.\n[roles.critic]" in parts.text and parts.unmade == ()


def test_an_edit_the_file_would_not_mean_as_written_is_refused_and_leaves_the_draft_as_it_was(here, monkeypatch):
    """The data the edit means is kept beside the text, and what the text means once written must be it."""
    written(here)
    monkeypatch.setattr(team_editor, "_item", lambda value, inline: team_editor.tomlkit.item("not it"))

    found = drafted(here, setting("roles.lead.effort", "high"))

    assert problems(found)["roles.lead.effort"] == [
        "roles.lead.effort: the editor cannot make this change and keep this file's layout: make it in the file"
    ]
    assert found.text == STARTER and found.blocked == "Fix each change marked first: the editor could not make it."


def test_clearing_a_field_leaves_its_key_out_and_a_table_it_empties_goes_with_it(here):
    """But an entry a person named, such as a role, stays until it is removed."""
    written(here, STARTER + '\n[budget]\nusd = 5\n\n[roles.critic]\nharness = "claude"\n')

    found = drafted(here, setting("budget.usd", ""), setting("roles.critic.harness", ""))

    assert found.text == STARTER + "\n[roles.critic]\n"
    assert problems(found)["roles.critic.harness"] == ["roles.critic.harness: Field required"]


def test_every_problem_is_shown_at_its_field_or_else_its_table_or_else_at_the_top(here):
    """The loader's, a field's text that is not what it takes, a tagged table's, which names its tag, and `team
    check`'s, none left out. A draft the loader refuses cannot be saved, and has no sentences to show."""
    written(here)

    found = drafted(
        here,
        setting("roles.lead.count", "two"),
        Edit("add", ("topology", "channels", "notes"), "board"),
        setting("roles.worker.approvals", "deny"),
        setting("roles.lead.stays", "no"),
        Edit("add", ("roles", "critic"), "nobody"),
    )

    assert problems(found) == {
        "top": ["roles.critic: is `claude` or `codex`"],
        "roles.lead.count": ["roles.lead.count: is a whole number"],
        "topology.channels.notes.writers": ["topology.channels.notes.board.writers: Field required"],
        "topology.channels.notes.readers": ["topology.channels.notes.board.readers: Field required"],
    }
    assert found.shown is None and found.unmade == (0, 4)
    assert found.blocked == "Fix each change marked first: the editor could not make it."


def test_team_check_s_problems_are_shown_and_do_not_stop_a_save(here):
    """A team may name a harness this machine has no driver for, so what `team check` finds is said, and the draft
    saves."""
    written(here, STARTER + '\n[roles.critic]\nharness = "nobody"\ncount = 0\n')

    found = drafted(here, setting("roles.worker.sandbox", "read-only"))

    (said,) = problems(found).pop("roles.critic.harness")
    assert problems(found) == {"roles.critic.harness": [said]} and said.startswith("roles.critic.harness: no driver")
    assert found.shown is not None and found.blocked is None


def test_the_preview_is_team_show_s_sentences_of_the_draft(here):
    written(here)

    found = drafted(here, setting("topology.limits.max_depth", "2"))

    assert found.shown == Team.loads(found.text).resolved().show()
    assert "2" in found.shown


def test_a_draft_is_loaded_as_run_loads_it_with_the_user_s_config_beneath(here, tmp_path):
    """The user's config is a layer under the project file, as `run` reads it, so a problem it makes is shown too."""
    config = tmp_path / "config" / "platoon-harness"
    config.mkdir(parents=True)
    (config / "config.toml").write_text("[budget]\ntokens = 1000\n")
    written(here)

    found = drafted(here, setting("roles.lead.model", "sonnet"))

    assert problems(found)["budget"] == [
        "budget.estimate: a tokens limit needs `estimate.tokens`: what a turn nobody measured whole is charged on top"
    ]
    assert found.shown is not None and found.blocked is None


def test_an_edit_outside_what_a_person_sets_from_a_client_is_refused(here):
    """What runs code, and the keys left to the file, are the file's alone, and an entry's name is a name."""
    written(here)

    found = drafted(
        here,
        setting("extensions", "ballot"),
        setting("roles.lead.tools", "message.*"),
        setting("roles.lead.harness", "tests.integration.scripts:saying"),
        Edit("add", ("roles", "two words"), "claude"),
        Edit("add", ("roles", "lead"), "claude"),
        Edit("remove", ("budget",)),
    )

    assert problems(found) == {
        "top": [
            "extensions: is no key a person sets from here: edit it in the file",
            "roles.two words: is no name: letters, digits, `_` and `-`, joined by single dots",
        ],
        "roles.lead": [
            "roles.lead.tools: is no key a person sets from here: edit it in the file",
            "roles.lead: is there already",
        ],
        "roles.lead.harness": ["roles.lead.harness: is `claude` or `codex`"],
        "budget": ["budget: is nothing a person removes from here: remove it in the file"],
    }
    assert found.text == STARTER and found.unmade == (0, 1, 2, 3, 4, 5)


def test_a_file_that_is_no_toml_or_no_text_is_left_to_the_file(here):
    written(here, "[roles.lead\n")
    with pytest.raises(ConfigError, match=f"{PROJECT_FILE}: not TOML: .*: edit it in the file"):
        drafted(here)

    (here / PROJECT_FILE).write_bytes(b'[roles.lead]\nharness = "\xff"\n')
    with pytest.raises(ConfigError, match=f"{PROJECT_FILE}: is not UTF-8 text: edit it in the file"):
        drafted(here)


def test_edits_from_json_take_set_add_and_remove_alone(here):
    assert edits_of(
        [{"set": ["roles", "lead", "model"], "to": "x"}, {"add": ["roles", "b"]}, {"remove": ["test"]}]
    ) == (
        Edit("set", ("roles", "lead", "model"), "x"),
        Edit("add", ("roles", "b"), ""),
        Edit("remove", ("test",)),
    )
    for wrong in (
        {},
        [{"set": "roles.lead"}],
        [{"set": [], "to": ""}],
        [{"remove": ["x"], "to": ""}],
        [{"set": ["a"], "add": ["a"]}],
        [{"set": ["a"], "to": 1}],
        [{"set": ["a"], "x": 1}],
    ):
        with pytest.raises(ValueError):
            edits_of(wrong)


def test_saving_writes_the_draft_whole_over_the_file_as_it_was_read_keeping_its_mode(here):
    path = written(here)
    path.chmod(0o640)
    base = drafted(here).base
    edits = [setting("roles.worker.model", "gpt-6-luna")]

    saved = save(here, base, edits, HARNESSES, None)

    assert isinstance(saved, Draft) and path.read_text() == saved.text
    assert 'model = "gpt-6-luna"  # cheap' in path.read_text()
    assert oct(path.stat().st_mode & 0o777) == oct(0o640)
    assert sorted(item.name for item in here.iterdir()) == [PROJECT_FILE]
    assert load_team().roles["worker"].model == "gpt-6-luna"


def test_a_file_changed_since_it_was_read_is_refused_and_left_as_it_is(here):
    path = written(here)
    base = drafted(here).base
    path.write_text(STARTER.replace("gpt-6", "gpt-7"))

    with pytest.raises(ConfigError) as refused:
        save(here, base, [setting("roles.worker.effort", "low")], HARNESSES, None)

    assert str(refused.value).startswith(f"{PROJECT_FILE}: changed since it was read, so nothing was saved")
    assert path.read_text() == STARTER.replace("gpt-6", "gpt-7")
    assert sorted(item.name for item in here.iterdir()) == [PROJECT_FILE]


def test_the_editor_never_writes_through_a_link(here, tmp_path):
    """Nor reads one to edit: a link and what it names are left as they are."""
    elsewhere = tmp_path / "team.toml"
    elsewhere.write_text(STARTER)
    (here / PROJECT_FILE).symlink_to(elsewhere)

    with pytest.raises(ConfigError, match="is a link, and the editor writes through none: edit the file it names"):
        drafted(here)
    with pytest.raises(ConfigError, match="is a link"):
        save(here, hashlib.sha256(STARTER.encode()).hexdigest(), [setting("roles.lead.model", "x")], HARNESSES, None)

    assert (here / PROJECT_FILE).is_symlink() and elsewhere.read_text() == STARTER


def test_a_new_project_file_is_written_over_nothing(here):
    """With none, the draft starts empty and the loader asks for a role. A file that came to be since is refused."""
    empty = drafted(here)
    edits = [Edit("add", ("roles", "lead"), "claude")]
    first = drafted(here, *edits)

    saved = save(here, None, edits, HARNESSES, None)
    again = None
    try:
        save(here, None, edits, HARNESSES, None)
    except ConfigError as refused:
        again = str(refused)

    assert empty.base is None and problems(empty) == {"top": ["roles: Field required"]}
    assert first.text == '[roles.lead]\nharness = "claude"\n' and isinstance(saved, Draft)
    assert (here / PROJECT_FILE).read_text() == first.text
    assert again is not None and again.startswith(f"{PROJECT_FILE}: changed since it was read")


def test_saving_a_value_only_trust_may_take_asks_once_naming_it_and_never_trusts_silently(here):
    """The question names each value the save would write that the file did not hold, as the team would hold it, and
    only its own digest says yes. A save that writes no such value asks nothing."""
    path = written(here)
    base = drafted(here).base
    edits = [setting("test.command", "uv run pytest -q"), setting("test.timeout", "10m")]

    asked = save(here, base, edits, HARNESSES, None)
    wrong = save(here, base, edits, HARNESSES, "0" * 64)
    nothing = path.read_text()
    assert isinstance(asked, Asked)
    saved = save(here, base, edits, HARNESSES, asked.trust)
    later = save(
        here, hashlib.sha256(path.read_bytes()).hexdigest(), [setting("roles.lead.effort", "low")], HARNESSES, None
    )

    assert asked.question == f'{SAVING}\ntest.command = ["uv", "run", "pytest", "-q"]\nSave it, as shown here?'
    assert asked.yes == "Save it" and asked.trust == hashlib.sha256(asked.question.encode()).hexdigest()
    assert wrong == asked and nothing == STARTER
    assert isinstance(saved, Draft) and tomllib.loads(path.read_text())["test"]["command"] == [
        "uv",
        "run",
        "pytest",
        "-q",
    ]
    assert fields(saved)["test.command"].trust and fields(saved)["test.command"].text == "uv run pytest -q"
    assert isinstance(later, Draft)
    assert os.path.exists(path)
