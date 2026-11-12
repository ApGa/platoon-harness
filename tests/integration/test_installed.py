"""platoon-harness as a person installs it, from its wheel built from this checkout, in an environment of its own: with
its `cli` extra the command line runs, a headless script's run settles on the `exec` driver and the command line reads
it back, and `uv tool install` puts the command on PATH; alone, the library imports with nothing of that extra, and the
command says what to install; the wheel holds the files each layer tracks; and the `openhands` extra requires what the
install guide says."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from packaging.requirements import Requirement

import platoon_harness
from platoon_harness_cli.launcher import HINT

from .installing import PACKAGES, ROOT, SECONDS, Installed, apart, install, install_wheels, uv

pytestmark = [pytest.mark.slow, pytest.mark.timeout(600)]

GUIDE = ROOT / "docs" / "getting-started" / "install.md"
SCRIPT = Path(__file__).with_name("counting.py")
BRINGS = "brings `lmnr-claude-code-proxy` unless you exclude it"
"""What the install guide and the wheel's description each say of the `openhands` extra installed from a wheel."""
VERSION = f"platoon-harness {platoon_harness.__version__}\n"
WHERE = "import platoon_harness, platoon_harness_cli; print(platoon_harness.__file__, platoon_harness_cli.__file__)"
HELD = "import importlib.metadata as m; print(*(d.metadata['Name'].lower() for d in m.distributions()))"
PAGE = (
    "from importlib import resources; from platoon_harness_cli.web import page; page.load(); "
    "assert resources.files('platoon_harness.drivers').joinpath('pi_extension.js').is_file()"
)
"""The page the command line serves, put together from its own files and SwarmChat's, and the extension pi loads."""


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Installed:
    """The wheel with its `cli` extra, as the command line is installed."""
    return install(tmp_path_factory.mktemp("installed"))


@pytest.fixture(scope="module")
def alone(installed: Installed, tmp_path_factory: pytest.TempPathFactory) -> Installed:
    """The same wheel with no extra, as a library that builds on the SDK installs it."""
    return install_wheels(tmp_path_factory.mktemp("alone"), installed.wheels, extras=())


def required(installed: Installed, extra: str) -> set[str]:
    """Each distribution the wheel's `extra` requires, and nothing else does."""
    requirements = [Requirement(line) for line in installed.metadata("platoon-harness").get_all("Requires-Dist", [])]
    return {
        requirement.name
        for requirement in requirements
        if requirement.marker is not None
        and requirement.marker.evaluate({"extra": extra})
        and not requirement.marker.evaluate({"extra": ""})
    }


def test_the_installed_command_line_runs_from_wheels_in_a_fresh_environment(installed: Installed, tmp_path: Path):
    """It says the version this checkout sets, the SDK and the command line come from the environment, not the
    checkout, and the environment holds platoon-harness, the `cli` extra and what they require, and nothing of the
    checkout's dev group."""
    version = installed.run("platoon-harness", "--version", home=tmp_path / "home", cwd=tmp_path)
    where = installed.run("python", "-I", "-c", WHERE, home=tmp_path / "home", cwd=tmp_path)
    held = installed.run("python", "-I", "-c", HELD, home=tmp_path / "home", cwd=tmp_path)
    names = set(held.stdout.split())

    assert version.stdout == VERSION
    assert [Path(path).is_relative_to(installed.environment) for path in where.stdout.split()] == [True, True]
    assert {"platoon-harness", "pydantic", *required(installed, "cli")} <= names
    assert names.isdisjoint({"hypothesis", "openhands-sdk", "playwright", "pytest"})


def test_the_library_alone_installs_nothing_of_the_cli_extra(alone: Installed, tmp_path: Path):
    """`import platoon_harness` needs pydantic alone, as a library built on it, such as Platoon's teams bridge, would
    install it, and nothing the `cli` or `openhands` extra requires is there."""
    imported = alone.run("python", "-I", "-c", "import platoon_harness", home=tmp_path / "home", cwd=tmp_path)
    held = alone.run("python", "-I", "-c", HELD, home=tmp_path / "home", cwd=tmp_path)
    names = set(held.stdout.split())

    assert imported.returncode == 0, imported.stderr
    assert {"platoon-harness", "pydantic"} <= names
    assert names.isdisjoint(required(alone, "cli") | required(alone, "openhands"))


def test_the_library_alone_s_command_says_to_install_the_cli_extra(alone: Installed, tmp_path: Path):
    """The command names the extra and how to install it, and exits 78, as a machine that cannot be used as it is."""
    done = alone.run("platoon-harness", "--version", home=tmp_path / "home", cwd=tmp_path)

    assert (done.returncode, done.stdout, done.stderr) == (78, "", f"{HINT}\n")


def test_a_headless_run_from_the_installed_wheels_settles_on_the_exec_driver(installed: Installed, tmp_path: Path):
    """A script on the SDK alone, on the environment's Python: its two agents run on the `exec` driver, the session
    settles, and the installed command line reads back what each said."""
    home = tmp_path / "home"

    done = installed.run("python", str(SCRIPT), home=home, cwd=tmp_path)

    first, *said = done.stdout.splitlines()
    match = re.fullmatch(r"session (\S+): settled", first)
    assert done.returncode == 0 and match, done.stderr
    assert said == ["counter-1: 6 words", "counter-2: 4 words"]
    read = installed.run("platoon-harness", "events", match[1], "--json", home=home, cwd=tmp_path)
    events = [json.loads(line) for line in read.stdout.splitlines()]
    assert read.returncode == 0, read.stderr
    assert sorted(f"{event['agent']}: {event['gist']}" for event in events if event["type"] == "item.recorded") == said


def test_the_installed_wheels_hold_their_package_data(installed: Installed, tmp_path: Path):
    """The wheel holds every file git tracks in each layer's package, the data beside the modules among them, and
    nothing else but its metadata, with the license; installed, the command line's page and pi's extension are found
    where they were put."""
    files = installed.files("platoon-harness")
    for package, source in PACKAGES.items():
        listed = subprocess.run(
            ["git", "ls-files", "-z", package], cwd=source, capture_output=True, text=True, check=True
        )

        assert sorted(name for name in files if name.split("/")[0] == package) == sorted(
            name for name in listed.stdout.split("\0") if name
        )
    assert {name.split("/")[0] for name in files} == {
        *PACKAGES,
        f"platoon_harness-{platoon_harness.__version__}.dist-info",
    }
    assert any(name.endswith(".dist-info/licenses/LICENSE") for name in files)
    found = installed.run("python", "-I", "-c", PAGE, home=tmp_path / "home", cwd=tmp_path)

    assert found.returncode == 0, found.stderr


def test_uv_tool_install_puts_the_command_on_path_with_the_cli_extra(installed: Installed, tmp_path: Path):
    """As the install guide's first command does, from the wheel, offline, in a folder of tools of the test's own."""
    tools, bin = tmp_path / "tools", tmp_path / "bin"
    wheel = installed.wheels["platoon-harness"]

    command = ["tool", "install", "--python", sys.executable, f"platoon-harness[cli] @ {wheel.as_uri()}"]

    uv(*command, cwd=tmp_path, UV_TOOL_DIR=str(tools), UV_TOOL_BIN_DIR=str(bin))
    version = subprocess.run(
        [bin / "platoon-harness", "--version"],
        cwd=tmp_path,
        env=apart(PLATOON_HARNESS_HOME=str(tmp_path / "home")),
        capture_output=True,
        text=True,
        timeout=SECONDS,
        check=False,
    )

    assert version.stdout == VERSION


def test_the_built_wheel_s_openhands_extra_requires_what_install_md_describes(installed: Installed):
    """The extra requires OpenHands' SDK and tools at the release the guide names, exactly, and nothing more. No wheel
    can leave out what those require, Laminar's proxy among it, so the guide and the wheel's description each say that
    the extra installed from a wheel brings it unless you exclude it."""
    guide = " ".join(GUIDE.read_text().split())
    [(sdk, tools, release)] = re.findall(r"pinning `([\w-]+)` and `([\w-]+)` at ([\d.]+) exactly", guide)
    metadata = installed.metadata("platoon-harness")
    extra = {
        requirement.name: str(requirement.specifier)
        for requirement in map(Requirement, metadata.get_all("Requires-Dist", []))
        if requirement.name in required(installed, "openhands")
    }

    assert metadata.get_all("Provides-Extra") == ["cli", "openhands"]
    assert extra == {sdk: f"=={release}", tools: f"=={release}"}
    assert BRINGS in guide
    assert BRINGS in " ".join(str(metadata.get_payload()).split())
