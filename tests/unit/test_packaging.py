"""What the packages publish: one version, set in one place, and the command line requiring the SDK of its own minor
release; the project's one sentence, after what each package is; the license in each wheel; and classifiers that claim
no system STATUS has not seen run and no Python CI does not test."""

import re
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

import platoon_harness
import platoon_harness_cli

ROOT = Path(__file__).parents[2]
VERSION = ROOT / "packages" / "sdk" / "src" / "platoon_harness" / "version.py"
"""The file that sets the version of both packages."""
SETS = re.compile(r'^__version__ = "(.+)"$', re.M)
PACKAGES = {
    "packages/sdk": "The Python SDK of platoon-harness",
    "packages/cli": "The terminal UI and command line of platoon-harness",
}
"""Each package's folder, and what its description says it is before the project's sentence."""


def project(folder: Path) -> dict[str, Any]:
    return tomllib.loads((folder / "pyproject.toml").read_text())["project"]


def tool(folder: Path) -> dict[str, Any]:
    return tomllib.loads((folder / "pyproject.toml").read_text())["tool"]


def test_each_version_is_set_once_and_the_sdk_and_cli_share_it():
    """Each package reads its version from the SDK's version file, and uv makes its metadata again when that file
    changes, so what a checkout's metadata says is what the file sets. The workspace's root is never built."""
    for folder in (ROOT, *(ROOT / folder for folder in PACKAGES)):
        assert "version" not in project(folder) and project(folder)["dynamic"] == ["version"]
    for folder in PACKAGES:
        path = tool(ROOT / folder)["hatch"]["version"]["path"]
        assert (ROOT / folder / path).resolve() == VERSION
        assert tool(ROOT / folder)["uv"]["cache-keys"] == [{"file": "pyproject.toml"}, {"file": path}]
    setters = {path: SETS.findall(path.read_text()) for path in (ROOT / "packages").rglob("*.py")}
    version = platoon_harness.__version__

    assert {path: found for path, found in setters.items() if found} == {VERSION: [version]}
    assert platoon_harness_cli.__version__ == version
    assert metadata.version("platoon-harness-cli") == metadata.version("platoon-harness-sdk") == version


def test_the_cli_requires_the_sdk_s_own_minor_release():
    """Below 1.0 a minor release may change the SDK's API, as CHANGELOG says, so the command line takes any patch of its
    own minor release and no other."""
    release = Version(platoon_harness.__version__)
    requirements = [Requirement(line) for line in project(ROOT / "packages" / "cli")["dependencies"]]
    [sdk] = [requirement for requirement in requirements if requirement.name == "platoon-harness-sdk"]

    assert release.major == 0
    assert sdk.specifier == SpecifierSet(f">={release.major}.{release.minor},<{release.major}.{release.minor + 1}")


def test_each_package_is_described_by_what_it_is_and_the_projects_sentence():
    sentence = project(ROOT)["description"]

    assert sentence.startswith("Run the agent harnesses you already use")
    for folder, what in PACKAGES.items():
        assert project(ROOT / folder)["description"] == f"{what}: {sentence[0].lower()}{sentence[1:]}"


def test_each_wheel_ships_a_copy_of_the_license():
    """A package's license files must be inside its own folder, so each holds a copy."""
    for folder in PACKAGES:
        assert project(ROOT / folder)["license-files"] == ["LICENSE"]
        assert (ROOT / folder / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()


def test_no_package_names_macos_while_nothing_has_run_there():
    assert "Nothing has run on macOS" in (ROOT / "docs" / "STATUS.md").read_text()
    for folder in PACKAGES:
        assert [kind for kind in project(ROOT / folder)["classifiers"] if "MacOS" in kind] == []


def test_the_packages_name_the_pythons_ci_tests_and_nothing_else():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    tested = workflow["jobs"]["test"]["strategy"]["matrix"]["python"]
    sdk, cli = (project(ROOT / folder)["classifiers"] for folder in PACKAGES)

    assert cli == sdk
    assert [kind.removeprefix("Programming Language :: Python :: ") for kind in sdk if "Python ::" in kind] == tested
