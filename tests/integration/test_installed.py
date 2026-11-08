"""The packages as a person installs them, from wheels built from this checkout, in an environment of their own: the
command line runs, a headless script's run settles on the `exec` driver and the command line reads it back, each wheel
holds the files its package tracks, and the SDK's `openhands` extra requires what the install guide says."""

import json
import re
import subprocess
from pathlib import Path

import pytest
from packaging.requirements import Requirement

import platoon_harness

from .installing import PACKAGES, ROOT, Installed, install

pytestmark = [pytest.mark.slow, pytest.mark.timeout(600)]

GUIDE = ROOT / "docs" / "getting-started" / "install.md"
SCRIPT = Path(__file__).with_name("counting.py")
BRINGS = "brings `lmnr-claude-code-proxy` unless you exclude it"
"""What the install guide and the SDK's description each say of the `openhands` extra installed from a wheel."""
WHERE = "import platoon_harness, platoon_harness_cli; print(platoon_harness.__file__, platoon_harness_cli.__file__)"
HELD = "import importlib.metadata as m; print(*(d.metadata['Name'].lower() for d in m.distributions()))"
PAGE = (
    "from importlib import resources; from platoon_harness_cli.web import page; page.load(); "
    "assert resources.files('platoon_harness.drivers').joinpath('pi_extension.js').is_file()"
)
"""The page the command line serves, put together from its own files and SwarmChat's, and the extension pi loads."""


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Installed:
    return install(tmp_path_factory.mktemp("installed"))


def test_the_installed_command_line_runs_from_wheels_in_a_fresh_environment(installed: Installed, tmp_path: Path):
    """It says the version this checkout sets, both packages come from the environment, not the checkout, and the
    environment holds the two and what they require, and nothing of the checkout's dev group."""
    version = installed.run("platoon-harness", "--version", home=tmp_path / "home", cwd=tmp_path)
    where = installed.run("python", "-I", "-c", WHERE, home=tmp_path / "home", cwd=tmp_path)
    held = installed.run("python", "-I", "-c", HELD, home=tmp_path / "home", cwd=tmp_path)
    names = set(held.stdout.split())

    assert version.stdout == f"platoon-harness {platoon_harness.__version__}, SDK {platoon_harness.__version__}\n"
    assert [Path(path).is_relative_to(installed.environment) for path in where.stdout.split()] == [True, True]
    assert {*PACKAGES, "pydantic", "swarmchat", "textual"} <= names
    assert names.isdisjoint({"hypothesis", "openhands-sdk", "playwright", "pytest"})


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
    """Each wheel holds every file git tracks in its package, the data beside the modules among them, and nothing else
    of it, with the license; installed, the command line's page and pi's extension are found where they were put."""
    for distribution, package in PACKAGES.items():
        source = ROOT / "packages" / distribution.removeprefix("platoon-harness-") / "src"
        listed = subprocess.run(
            ["git", "ls-files", "-z", package], cwd=source, capture_output=True, text=True, check=True
        )
        files = installed.files(distribution)

        assert sorted(name for name in files if not name.split("/")[0].endswith(".dist-info")) == sorted(
            name for name in listed.stdout.split("\0") if name
        )
        assert any(name.endswith(".dist-info/licenses/LICENSE") for name in files)
    found = installed.run("python", "-I", "-c", PAGE, home=tmp_path / "home", cwd=tmp_path)

    assert found.returncode == 0, found.stderr


def test_the_built_wheel_s_openhands_extra_requires_what_install_md_describes(installed: Installed):
    """The extra requires OpenHands' SDK and tools at the release the guide names, exactly, and nothing more. No wheel
    can leave out what those require, Laminar's proxy among it, so the guide and the wheel's description, the SDK's
    README, each say that the extra installed from a wheel brings it unless you exclude it."""
    guide = " ".join(GUIDE.read_text().split())
    [(sdk, tools, release)] = re.findall(r"pinning `([\w-]+)` and `([\w-]+)` at ([\d.]+) exactly", guide)
    metadata = installed.metadata("platoon-harness-sdk")
    requirements = [Requirement(line) for line in metadata.get_all("Requires-Dist", [])]
    extra = [
        requirement
        for requirement in requirements
        if requirement.marker is not None
        and requirement.marker.evaluate({"extra": "openhands"})
        and not requirement.marker.evaluate({"extra": ""})
    ]

    assert metadata.get_all("Provides-Extra") == ["openhands"]
    assert {requirement.name: str(requirement.specifier) for requirement in extra} == {
        sdk: f"=={release}",
        tools: f"=={release}",
    }
    assert BRINGS in guide
    assert BRINGS in " ".join(str(metadata.get_payload()).split())
