"""What the packages publish: the project's one sentence, after what each package is; the license in each wheel; and
classifiers that claim no system STATUS has not seen run and no Python CI does not test."""

import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[2]
PACKAGES = {
    "packages/sdk": "The Python SDK of platoon-harness",
    "packages/cli": "The terminal UI and command line of platoon-harness",
}
"""Each package's folder, and what its description says it is before the project's sentence."""


def project(folder: Path) -> dict[str, Any]:
    return tomllib.loads((folder / "pyproject.toml").read_text())["project"]


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
