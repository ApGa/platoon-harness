"""The command line made from the op registry and its schemas: a command for each op a person may run, by the name and
with the arguments an agent's `ph` uses, and none for any other. An installed extension's ops are commands too, made
from that extension alone, which fake distributions on `sys.path` stand in for."""

import asyncio
import inspect
import io
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, get_args

import pytest
from cyclopts import App, CycloptsError
from rich.console import Console

from platoon_harness import Session, Team
from platoon_harness.annotations import Annotate
from platoon_harness.extensions import EXTENSIONS
from platoon_harness.kernel import GIST_LIMIT, Event, registry
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.session import Reason
from platoon_harness.tools.surface import body_fields
from platoon_harness_cli.exits import CONFIGURATION, ENDINGS, REFUSED, SHARED
from platoon_harness_cli.main import build, extended, main
from platoon_harness_cli.ops import _PURPOSES, command_line, cut, person_ops
from platoon_harness_cli.output import event_line, safe
from platoon_harness_cli.reference import reference

from ..conftest import Site
from ..runtime.support import scripted

APP = build()
OPS = registry(PRIMITIVES)
REFERENCE = Path(__file__).parents[3] / "docs" / "reference" / "cli.md"


def parsed(words: list[str]) -> tuple[Any, dict[str, Any]]:
    command, bound, _ = APP.parse_args(words, exit_on_error=False, print_error=False)
    return command, bound.arguments


def needed(name: str) -> list[str]:
    """The flags an op cannot go without, each with a value its schema takes."""
    schema = OPS[name].input.model_json_schema()
    samples = {"integer": "1", "boolean": None, "string": "x"}
    words = []
    for field in schema.get("required", ()):
        kind = schema["properties"][field].get("type", "string")
        flag = f"--{field.replace('_', '-')}"
        sample = schema["properties"][field].get("enum", [samples.get(kind, "x")])[0]
        words += [flag] if kind == "boolean" else [flag, sample]
    return words


def helped(words: list[str], app: App = APP) -> str:
    """What `--help` says for a command, as a wide terminal shows it."""
    shown = io.StringIO()
    app([*words, "--help"], console=Console(file=shown, width=200), exit_on_error=False, result_action="return_value")
    return shown.getvalue()


@pytest.mark.parametrize("name", sorted(person_ops()))
def test_every_op_a_person_may_run_has_a_command_of_its_name(name: str):
    command, arguments = parsed([*name.split("."), "fix-auth", *needed(name)])

    assert arguments["session"] == "fix-auth"
    assert (command.__doc__ or "").split()[0] == (OPS[name].fn.__doc__ or "").split()[0]


@pytest.mark.parametrize("name", sorted(name for name, op in OPS.items() if op.runtime or op.agent or "wait" in name))
def test_no_op_kept_to_the_runtime_or_to_agents_and_no_wait_has_a_command(name: str):
    """A wait parks a turn, and a person has none."""
    words = [*name.split("."), "fix-auth"]
    try:
        command, _ = parsed(words)
    except CycloptsError:
        return
    assert command.__module__ != "platoon_harness_cli.ops", f"{name} has a command"


@pytest.mark.parametrize("name", sorted(person_ops()))
def test_a_command_takes_exactly_its_op_s_arguments_as_flags(name: str):
    command, _ = parsed([*name.split("."), "fix-auth", *needed(name)])
    operation = OPS[name]
    schema = operation.input.model_json_schema()
    fields = {*schema.get("properties", {})}
    bodies = set(body_fields(schema))

    flags = {parameter.name.rstrip("_") for parameter in inspect.signature(command).parameters.values()}

    reads = operation.query or operation.exposes
    assert flags == {"session", *fields, *(f"{body}_file" for body in bodies), *(() if reads else ("key",))}


def test_a_repeated_flag_is_a_list():
    _, arguments = parsed(
        ["message", "send", "s", "--to", "@a", "--gist", "g", "--based-on", "x@1", "--based-on", "y@2"]
    )

    assert arguments == {"session": "s", "to": "@a", "gist": "g", "based_on": ("x@1", "y@2")}


@pytest.mark.parametrize("name", sorted(person_ops()))
def test_every_flag_of_every_command_has_help(name: str):
    command, _ = parsed([*name.split("."), "fix-auth", *needed(name)])

    for parameter in inspect.signature(command).parameters.values():
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            assert parameter.annotation.__metadata__[0].help, f"{name} --{parameter.name}"


def test_each_command_group_says_what_it_is_for():
    """In a sentence of its own, as one sentence every group shared said nothing of any."""
    namespaces = {name.partition(".")[0] for name in person_ops() if "." in name} - {"session"}

    assert {namespace: APP[namespace].help for namespace in namespaces} == _PURPOSES
    assert len(set(_PURPOSES.values())) == len(_PURPOSES)


def test_a_command_s_help_names_commands_and_flags_where_its_op_names_ops_and_arguments():
    """As each surface names a tool as its own, and a sentence naming one with no command goes, as an agent's would."""
    send = " ".join(helped(["message", "send"]).split())
    claim = " ".join(helped(["task", "claim"]).split())

    assert "set --to to the entry's sender and --reply-to to its ref" in send
    assert "platoon-harness channel list for channels" in send and "channel.list" not in send
    assert "end your turn" not in claim and "wait" not in claim


@pytest.mark.parametrize("name", sorted(person_ops()))
def test_a_persons_surface_shows_no_sentence_written_to_an_agent(name: str):
    """A person has no turn, no place a read leaves off, no harness to keep a lease at work, and nothing to finish."""
    command, _ = parsed([*name.split("."), "fix-auth", *needed(name)])
    parameters = inspect.signature(command).parameters.values()
    flags = [
        parameter.annotation.__metadata__[0].help for parameter in parameters if parameter.kind.name == "KEYWORD_ONLY"
    ]

    said = " ".join([command.__doc__ or "", *flags]).lower()

    assert not re.search(r"\b(your (own )?(open )?turn|you left off|you are active|you have finished)\b", said)


def test_the_reference_names_only_flags_the_command_line_takes():
    """Command by command, the flags the reference lists are the ones `--help` shows, which the parser takes."""
    sections = re.split(r"^#{2,4} platoon-harness", REFERENCE.read_text(), flags=re.MULTILINE)[2:]
    for section in sections:
        words = section.partition("\n")[0].split()
        listed = set(re.findall(r"^\* `(--[a-z-]+(?:, --[a-z-]+)*)`", section, flags=re.MULTILINE))
        flags = {flag for names in listed for flag in names.split(", ")}
        assert flags <= set(re.findall(r"--[a-z][a-z-]*", helped(words))), words


def test_an_action_is_shown_as_the_command_that_runs_it():
    action = {"op": "approval.resolve", "args": {"id": "a7", "verdict": "allow", "expected_version": 3}}

    line = command_line("fix-auth", action["op"], action["args"])
    _, arguments = parsed(shlex.split(line)[1:])

    assert line == "platoon-harness approval resolve fix-auth --id a7 --verdict allow --expected-version 3"
    assert arguments == {"session": "fix-auth", **action["args"]}
    assert parsed(shlex.split(command_line("s", "effect.settle", {"id": 4, "happened": False}))[1:])[1] == {
        "session": "s",
        "id": 4,
        "happened": False,
    }


def test_an_action_that_leaves_flags_to_you_is_shown_with_them_still_to_give():
    """`budget set` with only its scope would set no limits, so the line that shows such an action does not run as it
    stands."""
    line = command_line("fix-auth", "budget.set", {"scope": "shared"}, form=True)

    assert line == "platoon-harness budget set fix-auth --scope shared ..."
    with pytest.raises(CycloptsError):
        parsed(shlex.split(line)[1:])


def test_every_way_a_session_ends_has_an_exit_code():
    assert set(ENDINGS) == set(get_args(Reason))
    assert ENDINGS["settled"] == 0 and ENDINGS["cancelled"] == 130


def test_a_code_every_command_shares_means_one_thing_and_no_ending_s_but_an_interrupt():
    assert set(SHARED) & set(ENDINGS.values()) == {1, 130}
    assert "other than `run` and `session resume`" in SHARED[1]


def test_a_jsonl_line_is_an_event_s_envelope_with_its_format():
    fields = {"v": 2, "seq": 7, "stream": "inbox/lead", "version": 1, "type": "message.sent", "actor": "human:you"}
    stamps = {"agent": None, "turn": None, "context_version": None, "episode": None, "topology_rev": 0}
    more = {"correlation": None, "cause": (), "based_on": (), "native": {}, "model": None, "outcome": None}
    event = Event(**fields, **stamps, **more, wall_time=1.0, gist="é \x1b[2J", data={"sender": "@you"})

    line = event_line(event)

    assert line.isascii()
    assert json.loads(line) == {"format": 1, **event.model_dump(mode="json")}


def test_text_a_terminal_shows_escapes_what_could_take_it_over():
    assert safe("ok\x1b]0;owned\x07 and‮back\nnext") == "ok\\x1b]0;owned\\x07 and\\u202eback\nnext"


@pytest.mark.parametrize(
    "name", ["exposure", "lineage", "uses", "contributors", "eligibility", "spans", "interactions"]
)
def test_the_provenance_commands_derive_from_the_registry(name: str):
    """Each query is a command of its own name, reading on a view credential, with its op's flags and help."""
    command, arguments = parsed([name, "fix-auth", *needed(name)])

    assert name in person_ops() and arguments["session"] == "fix-auth"
    assert "key" not in inspect.signature(command).parameters
    assert (command.__doc__ or "").split()[:4] == (OPS[name].fn.__doc__ or "").split()[:4]


def test_annotate_is_made_from_the_schema_session_annotate_checks():
    credit = ["--target", "agent/a@1", "--kind", "credit", "--producer", "p", "--producer-version", "1"]
    said = ["--scope", "team", "--status", "timeout", "--head-seq", "9"]
    _, arguments = parsed(["annotate", "fix-auth", *credit, *said])

    flags = {name.replace("_", "-") for name in Annotate.model_fields}
    assert {f"--{flag}" for flag in flags} <= set(re.findall(r"--[a-z-]+", helped(["annotate"])))
    assert (arguments["session"], arguments["kind"]) == ("fix-auth", "credit")


def test_the_reference_is_made_from_the_definitions():
    """On a failure, run `uv run python -m platoon_harness_cli.reference > docs/reference/cli.md`."""
    assert (Path(__file__).parents[3] / "docs" / "reference" / "cli.md").read_text() == reference()


def test_a_person_s_text_is_cut_into_a_gist_and_a_body_one_way():
    fits, long = "x" * GIST_LIMIT, "y" * (GIST_LIMIT + 1)

    assert cut(fits) == (fits, None)
    assert cut(long) == ("y" * (GIST_LIMIT - 1) + "…", long)


def test_a_file_sent_as_a_body_is_named_in_the_gist_since_a_body_keeps_no_name():
    words = "x" * (GIST_LIMIT - len(" (file notes.txt)"))

    assert cut("here they are", file="notes.txt") == ("here they are (file notes.txt)", None)
    assert cut("", file="notes.txt") == ("file notes.txt", None)
    assert cut(words, file="notes.txt") == (f"{words} (file notes.txt)", None)
    for text, name in ((words + "x", "notes.txt"), ("", "n" * (GIST_LIMIT - len("file ") + 1))):
        with pytest.raises(ValueError, match=f"of at most {GIST_LIMIT} characters, and these make {GIST_LIMIT + 1}"):
            cut(text, file=name)


# An installed extension's ops.

BALLOT = """
from typing import Annotated, Literal

from pydantic import Field

from platoon_harness.kernel import Args, Extension, Txn, op


class Vote(Args):
    choice: Annotated[Literal["yes", "no"], Field(description="Yes or no.")]


@op("ballot.cast", on=lambda a: "ballot/votes")
def cast(txn: Txn, a: Vote) -> dict[str, str]:
    \"\"\"Cast a vote, kept on the ballot's own stream. Refused by nothing of its own.\"\"\"
    txn.emit("ballot.voted", "ballot/votes", gist=f"a vote for {a.choice}", data=a)
    return {"choice": a.choice}


extension = Extension("ballot", ops=[cast])
"""
"""An extension of one op, a vote, as a third party's package would give it."""
NEVER = "raise RuntimeError('imported')"
"""A module that says so when anything imports it."""


def installed(site: Site, module: str, *never: str) -> None:
    """The ballot extension, from the distribution `voting` 2.0.0, in `module`, and an extension of each name in
    `never`, from a distribution of its own, whose module is never to be imported."""
    site.module(module, BALLOT)
    site.install("voting", "2.0.0", entry_points={EXTENSIONS: {"ballot": f"{module}:extension"}})
    for name in never:
        site.module(f"never_{name}", NEVER)
        site.install(f"{name}-maker", entry_points={EXTENSIONS: {name: f"never_{name}:extension"}})


def line(words: list[str]) -> tuple[Any, dict[str, Any]]:
    """What `words` parse to on the command line `main` runs them on, with what is installed."""
    command, bound, _ = extended(build(), words).parse_args(words, exit_on_error=False, print_error=False)
    return command, bound.arguments


def test_an_installed_extension_s_group_loads_only_that_extension(site: Site, capsys: pytest.CaptureFixture[str]):
    """Named first on a command line, its group imports it, and nothing else installed: its op is a command made as an
    op of the SDK's own is. A name two distributions define loads neither, saying both, and an entry point whose
    extension has another name is refused, as no command of its name would name that extension's ops."""
    installed(site, "ballot_alone", "other")
    site.module("never_twice", NEVER)
    for maker in ("one", "two"):
        site.install(maker, entry_points={EXTENSIONS: {"twice": "never_twice:extension"}})
    site.install("renamed", entry_points={EXTENSIONS: {"vote": "ballot_alone:extension"}})

    command, arguments = line(["ballot", "cast", "fix-auth", "--choice", "yes"])
    refused = [main([name, "--help"]) for name in ("twice", "vote")]

    assert arguments == {"session": "fix-auth", "choice": "yes"}
    assert (command.__doc__ or "").startswith("Cast a vote, kept on the ballot's own stream.")
    assert "platoon-harness ballot cast SESSION --choice CHOICE" in (command.__doc__ or "")
    assert "--key" in helped(["ballot", "cast"], extended(build(), ["ballot"]))
    assert "ballot_alone" in sys.modules
    assert refused == [CONFIGURATION, CONFIGURATION]
    assert capsys.readouterr().err == (
        "platoon-harness: extensions.twice: defined by more than one distribution: one 1.0.0, two 1.0.0, so this loads "
        "neither: uninstall one\n"
        "platoon-harness: extensions.vote: `ballot_alone:extension` is the extension ballot, whose ops no command of "
        "vote would name\n"
    )
    assert not {"never_other", "never_twice"} & set(sys.modules)


async def test_an_extension_s_command_on_a_session_whose_team_does_not_name_it_is_refused_saying_why(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """Installing activates nothing, so a session whose team does not name the extension holds none of its ops, and its
    command is refused before anything is asked of the session. On one whose team names it, it runs. A team that names
    an extension by `module:attr` records only that reference, which says nothing of its name until imported, so there
    the session's runtime answers: it runs the op where the reference is the extension, and refuses it where not."""
    installed(site, "ballot_named")
    site.module("other_extension", "from platoon_harness.kernel import Extension\n\nextension = Extension('other')\n")
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    roles = {"bob": {"harness": scripted()}}
    vote = ["ballot", "cast", "--choice", "yes"]

    def team(*extensions: str) -> Team:
        return Team.model_validate({"roles": roles, "extensions": extensions})

    async with (
        Session.start(team(), name="plain") as plain,
        Session.start(team("ballot"), name="named") as named,
        Session.start(team("ballot_named:extension"), name="byref") as byref,
        Session.start(team("other_extension:extension"), name="other"),
    ):
        refused = await asyncio.to_thread(main, [*vote[:2], "plain", *vote[2:]])
        said = capsys.readouterr()
        ran = [
            (await asyncio.to_thread(main, [*vote[:2], name, *vote[2:]]), json.loads(capsys.readouterr().out))
            for name in ("named", "byref")
        ]
        answered = await asyncio.to_thread(main, [*vote[:2], "other", *vote[2:]])
        votes = [[event.gist async for event in one.events() if event.type == "ballot.voted"] for one in (named, byref)]
        held = [entry["name"] for entry in await plain.ops() if entry["name"].startswith("ballot.")]

    assert refused == REFUSED and said.out == ""
    assert said.err == (
        "platoon-harness: refused not_found: session plain's team does not name the extension ballot, so it holds none "
        "of its ops: a team names its extensions in `extensions`, and this one names none\n"
    )
    assert ran == [(0, {"choice": "yes"})] * 2
    assert votes == [["a vote for yes"]] * 2 and held == []
    assert answered == REFUSED and capsys.readouterr().err == "platoon-harness: refused not_found: no such op\n"


def test_an_extension_named_as_a_built_in_command_group_is_refused_at_discovery_before_any_import(
    site: Site, capsys: pytest.CaptureFixture[str]
):
    """`run` and `task` are the command line's own, so an extension of either name gets no group: discovery refuses it
    from metadata, saying why on stderr, and each word still names the command line's own command."""
    for name in ("run", "task"):
        site.module(f"never_{name}", NEVER)
        site.install(f"{name}-maker", entry_points={EXTENSIONS: {name: f"never_{name}:extension"}})

    listed = " ".join(helped([], extended(build(), [])).split())
    said = capsys.readouterr().err
    command, arguments = line(["task", "claim", "fix-auth", "--queue", "tasks"])

    assert said == "".join(
        f"platoon-harness: extensions.{name}: {name}-maker 1.0.0's extension `{name}` has no commands, as `{name}` is "
        f"a command of the command line's own: its ops run through the SDK, MCP, `ph` and the clients' palettes\n"
        for name in ("run", "task")
    )
    assert "-maker" not in listed
    assert "run Start a session, give it a prompt, and own it in the foreground until it settles." in listed
    assert (command.__doc__ or "").split()[:4] == (OPS["task.claim"].fn.__doc__ or "").split()[:4]
    assert arguments == {"session": "fix-auth", "queue": "tasks"}
    assert not {"never_run", "never_task"} & set(sys.modules)


def test_help_lists_installed_extensions_from_metadata_without_importing_them(site: Site):
    """Each by its distribution and version, which metadata gives, under Installed extensions, with none imported."""
    site.module("never_ballot", NEVER)
    site.install("voting", "2.0.0", entry_points={EXTENSIONS: {"ballot": "never_ballot:extension"}})

    said = " ".join(helped([], extended(build(), [])).split())

    assert "Installed extensions" in said
    assert "ballot The ops of the extension ballot, from voting 2.0.0, on a session whose team names it." in said
    assert "never_ballot" not in sys.modules
