"""The sample extension package as a person installs it: `examples/extension-package` built as a wheel and installed in
an environment of its own, beside the SDK's and the command line's wheels and a rival's, a distribution that registers
an extension of the same name and records each import of it. There it activates nothing until a team names it, a team
that names what both register is refused before either is imported, its op runs through the SDK, MCP and `ph`, the
command line lists it from metadata and reads its votes back, and it passes `check_extension`. Installed without the
rival, its op is a command of the command line. What the environment's Python does there is `installed_ballot.py`'s."""

import json
import re
import textwrap
from pathlib import Path
from typing import Any

import pytest

from .installing import ROOT, Installed, install, install_wheels

pytestmark = [pytest.mark.slow, pytest.mark.timeout(600)]

SAMPLE = ROOT / "examples" / "extension-package"
SCRIPT = Path(__file__).with_name("installed_ballot.py")
RECORD = "RIVAL_IMPORTED"
"""The variable naming the file each import of the rival is recorded in."""
RIVAL = {
    "pyproject.toml": """
        [project]
        name = "rival"
        version = "1.0.0"
        requires-python = ">=3.12"
        dependencies = ["platoon-harness>=0.1,<0.2"]

        [project.entry-points."platoon_harness.extensions"]
        ballot = "rival:extension"

        [build-system]
        requires = ["hatchling>=1.27"]
        build-backend = "hatchling.build"

        [tool.hatch.build.targets.wheel]
        packages = ["rival"]
    """,
    "rival/__init__.py": f"""
        import os
        from pathlib import Path

        from platoon_harness.kernel import Extension

        with Path(os.environ["{RECORD}"]).open("a") as record:
            record.write(f"{{__name__}}\\n")

        extension = Extension("ballot")
    """,
}
"""A distribution of its own that registers an extension under the sample's name, and says each time it is imported."""
BOTH = "extensions.ballot: defined by more than one distribution: ballot 0.1.0, rival 1.0.0"


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Installed:
    rival = tmp_path_factory.mktemp("rival")
    for path, text in RIVAL.items():
        (rival / path).parent.mkdir(exist_ok=True)
        (rival / path).write_text(textwrap.dedent(text).lstrip())
    return install(tmp_path_factory.mktemp("installed"), SAMPLE, rival)


@pytest.fixture(scope="module")
def alone(installed: Installed, tmp_path_factory: pytest.TempPathFactory) -> Installed:
    """The same wheels but the rival's, in an environment of their own, as no command line can name `ballot` beside
    it."""
    wheels = {name: wheel for name, wheel in installed.wheels.items() if name != "rival"}
    return install_wheels(tmp_path_factory.mktemp("alone"), wheels)


@pytest.fixture
def imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The file each import of the rival is recorded in, empty."""
    record = tmp_path / "rival-imported"
    record.touch()
    monkeypatch.setenv(RECORD, str(record))
    return record


def case(installed: Installed, name: str, folder: Path) -> Any:
    """What a case of `installed_ballot.py` found, run on the environment's Python in `folder`."""
    done = installed.run("python", "-I", str(SCRIPT), name, home=folder / "home", cwd=folder)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_installing_the_sample_activates_nothing_until_a_team_names_it(
    installed: Installed, tmp_path: Path, imports: Path
):
    """A session whose team names no extension has no op of the sample's, refuses its op as no such op, and has imported
    neither the sample nor its rival; one whose team names the sample has its op and has imported it alone."""
    found = case(installed, "unnamed", tmp_path)

    assert found == {
        "unnamed": {"ops": [], "refused": "not_found", "imported": []},
        "named": {"ops": ["ballot.cast"], "imported": ["ballot"]},
    }
    assert imports.read_text() == ""


def test_a_rival_of_the_same_name_is_refused_before_any_import(installed: Installed, tmp_path: Path, imports: Path):
    """A team that names `ballot`, which both register, is refused, saying both and how to pin one, with neither
    imported. One that pins the rival's version imports the rival alone, so the rival was there to be found."""
    found = case(installed, "rival", tmp_path)

    assert found["refused"] == f"{BOTH}. Pin one with `ballot@version`"
    assert found["imported"] == []
    assert found["pinned"] == {"ops": [], "imported": ["rival"]}
    assert imports.read_text() == "rival\n"


def test_the_sample_s_op_runs_through_the_sdk_mcp_and_ph_from_its_wheel(
    installed: Installed, tmp_path: Path, imports: Path
):
    """Your vote through the SDK, then refused a second time; the reviewer's through MCP, in its scripted turn; and the
    checker's through `ph`, in its shell, which said what `ph` printed. Each lies on the author's stream, and the
    installed command line reads each back by its gist."""
    found = case(installed, "voted", tmp_path)
    read = installed.run("platoon-harness", "events", found["session"], "--json", home=tmp_path / "home", cwd=tmp_path)
    voted = [event for line in read.stdout.splitlines() if (event := json.loads(line))["type"] == "ballot.voted"]
    votes = [
        ["agent:checker", "agent/author", "a vote on @author's work: no"],
        ["agent:reviewer", "agent/author", "a vote on @author's work: yes"],
        ["human:you", "agent/author", "a vote on @author's work: yes"],
    ]

    assert found["ending"] == "settled"
    assert found["sdk"] == [{"choice": "yes"}, "conflict"]
    assert found["votes"] == votes
    assert found["checker"] == ['{"choice": "no"}']
    assert found["imported"] == ["ballot"]
    assert imports.read_text() == ""
    assert read.returncode == 0, read.stderr
    assert sorted([event["actor"], event["stream"], event["gist"]] for event in voted) == votes


def test_extension_list_names_the_sample_from_metadata(installed: Installed, tmp_path: Path, imports: Path):
    """`extension list` names the sample and its rival by their distributions, and the name they share as a problem,
    importing neither."""
    listed = installed.run("platoon-harness", "extension", "list", "--json", home=tmp_path / "home", cwd=tmp_path)
    found = json.loads(listed.stdout)

    assert listed.returncode == 0, listed.stderr
    assert [component for component in found["components"] if component["name"] == "ballot"] == [
        {"kind": "extension", "name": "ballot", "distribution": "ballot", "version": "0.1.0"},
        {"kind": "extension", "name": "ballot", "distribution": "rival", "version": "1.0.0"},
    ]
    assert found["problems"] == [BOTH]
    assert imports.read_text() == ""


def test_the_sample_s_op_is_a_command_from_its_wheel(
    installed: Installed, alone: Installed, tmp_path: Path, imports: Path
):
    """Beside the rival, `platoon-harness ballot` loads neither, saying both. Alone, `--help` lists it from metadata,
    and `platoon-harness ballot cast` casts your vote on a session whose team names it, is refused the second time as
    the SDK refuses it, and is refused on a session whose team names no extension, saying so, each from a process of
    its own while a script owns both sessions."""
    rivalled = installed.run("platoon-harness", "ballot", "--help", home=tmp_path / "home", cwd=tmp_path)
    found = case(alone, "commanded", tmp_path)
    first, again, plain = found["commands"]

    assert rivalled.returncode == 78
    assert f"{BOTH}, so this loads neither: uninstall one" in rivalled.stderr
    assert imports.read_text() == ""
    assert "ballot The extension ballot, from ballot 0.1.0. " in " ".join(found["help"]["out"].split())
    assert (first["code"], json.loads(first["out"])) == (0, {"choice": "yes"}), first["err"]
    assert again["code"] == 1 and re.search(r"refused conflict on agent/author: you voted yes", again["err"])
    assert plain["code"] == 1 and "session plain's team does not name the extension ballot" in plain["err"]
    assert found["votes"] == [["human:you", "agent/author", "a vote on @author's work: yes"]]


def test_the_sample_passes_check_extension(installed: Installed, tmp_path: Path, imports: Path):
    """Loaded from the environment by its pinned name, with a vote on each of two agents' work as its scenario, every
    check passes, its views rebuilt to what they held, and the result names its preset, which no check runs."""
    found = case(installed, "checked", tmp_path)

    assert found == {
        "checks": dict.fromkeys(
            ("names", "naming_law", "schemas", "descriptions", "public_api_only", "rebuild_equals_live"), "passed"
        ),
        "unchecked": ["preset pair-review: no check runs it, so nothing here says the topology it returns is valid"],
        "refused": [],
    }
    assert imports.read_text() == ""
