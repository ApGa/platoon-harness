"""What the packages publish: one version, set in one place, and the command line requiring the SDK of its own minor
release; the project's one sentence, after what each package is; the license in each wheel, and every license of what
installing them brings on the allowlist, but those the `openhands` extra brings that the owner has yet to rule on; and
classifiers that claim no system STATUS has not seen run and no Python CI does not test."""

import re
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
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
ALLOWED = {
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC0-1.0",
    "CNRI-Python",
    "ISC",
    "MIT",
    "MIT-0",
    "MIT-CMU",
    "MPL-2.0",
    "PSF-2.0",
    "Unlicense",
    "License :: OSI Approved :: Apache Software License",
    "License :: OSI Approved :: BSD License",
    "License :: OSI Approved :: MIT License",
    "3-Clause BSD License",
    "BSD 3-Clause OR Apache-2.0",
    "MIT License",
}
"""Each license a runtime dependency may state, as `stated` reads it: an SPDX identifier, a trove classifier, or the
words of a `License` field that name one. Each is permissive, but MPL-2.0, whose copyleft reaches only changes to its
own files."""
UNSETTLED = {
    "agent-client-protocol": (),
    "func-timeout": ("License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)",),
    "lupa": ("MIT style",),
    "openhands-sdk": (),
    "openhands-tools": (),
}
"""What each distribution the `openhands` extra brings whose license is not on the allowlist states: no license, the
LGPL, or words that name none. Whether a published extra may bring them is the owner's to rule on."""
IDENTIFIER = re.compile(r"[^\s()]+")


def project(folder: Path) -> dict[str, Any]:
    return tomllib.loads((folder / "pyproject.toml").read_text())["project"]


def tool(folder: Path) -> dict[str, Any]:
    return tomllib.loads((folder / "pyproject.toml").read_text())["tool"]


def required(*roots: tuple[str, tuple[str, ...]]) -> tuple[set[str], set[str]]:
    """The distributions installed here that `roots`, each a distribution and its extras, require on this platform and
    Python, `roots` among them, and those they require that are not installed."""
    found: dict[str, set[str]] = {}
    missing: set[str] = set()
    walk = [(name, set(extras)) for name, extras in roots]
    while walk:
        named, extras = walk.pop()
        name = canonicalize_name(named)
        if name in found and extras <= found[name]:
            continue
        try:
            requires = metadata.requires(name) or []
        except metadata.PackageNotFoundError:
            missing.add(name)
            continue
        found[name] = found.get(name, set()) | extras
        for requirement in map(Requirement, requires):
            marker = requirement.marker
            if marker is None or any(marker.evaluate({"extra": extra}) for extra in {"", *found[name]}):
                walk.append((requirement.name, set(requirement.extras)))
    return set(found), missing


def stated(name: str) -> tuple[str, ...]:
    """The license the installed distribution `name` states: the identifiers of its SPDX expression, from
    `License-Expression` or a `License` field that is one; else its license classifiers; else the first line of its
    `License` field; else none."""
    core = metadata.metadata(name)
    for field in ("License-Expression", "License"):
        try:
            expression = canonicalize_license_expression(core.get(field) or "")
        except InvalidLicenseExpression:
            continue
        return tuple(sorted(set(IDENTIFIER.findall(expression)) - {"AND", "OR", "WITH"}))
    if classifiers := [kind for kind in core.get_all("Classifier") or [] if kind.startswith("License ::")]:
        return tuple(sorted(classifiers))
    return tuple((core.get("License") or "").strip().splitlines()[:1])


def unlisted(names: set[str]) -> dict[str, tuple[str, ...]]:
    """Each of `names` that states no license on the allowlist, or none, with what it states."""
    said = {name: stated(name) for name in sorted(names)}
    return {name: terms for name, terms in said.items() if not terms or not set(terms) <= ALLOWED}


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


def test_every_runtime_dependency_s_license_is_on_the_allowlist():
    """What installing the two packages brings states a license on the allowlist, every one. The `openhands` extra
    brings besides only what `UNSETTLED` names, and the proxy the workspace excludes, whose license nothing here can
    read, as it is not installed."""
    plain, missing = required(("platoon-harness-sdk", ()), ("platoon-harness-cli", ()))
    extra, excluded = required(("platoon-harness-sdk", ("openhands",)), ("platoon-harness-cli", ()))

    assert missing == set() and excluded == set(tool(ROOT)["uv"]["exclude-dependencies"])
    assert {"platoon-harness-sdk", "platoon-harness-cli", "pydantic", "swarmchat", "textual"} <= plain < extra
    assert unlisted(plain) == {}
    assert unlisted(extra) == UNSETTLED


def test_the_workspace_excludes_the_proprietary_dependency_and_install_md_says_a_published_install_brings_it():
    """OpenHands' SDK requires `lmnr`, which requires Laminar's proxy. The workspace's lock leaves it out, so no
    checkout installs it, and the install guide says so, and that the extra installed from a wheel brings it."""
    excluded = tool(ROOT)["uv"]["exclude-dependencies"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    guide = " ".join((ROOT / "docs" / "getting-started" / "install.md").read_text().split())

    assert excluded == ["lmnr-claude-code-proxy"] and lock["manifest"]["excludes"] == excluded
    assert "lmnr" in {Requirement(line).name for line in metadata.requires("openhands-sdk") or []}
    assert "lmnr-claude-code-proxy" in {Requirement(line).name for line in metadata.requires("lmnr") or []}
    with pytest.raises(metadata.PackageNotFoundError):
        metadata.distribution("lmnr-claude-code-proxy")
    assert "`openhands-sdk` requires `lmnr`, which requires `lmnr-claude-code-proxy`" in guide
    assert "The checkout's lock leaves it out with `exclude-dependencies`, so a checkout never installs it" in guide
    assert "the extra installed from the SDK's wheel, as a published install would be, brings" in guide
