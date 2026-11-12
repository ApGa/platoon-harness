"""What platoon-harness publishes: one distribution of two layers, its version set in one place; a library that needs
pydantic alone, and a command line whose imports its `cli` extra installs, run by a launcher that needs nothing more to
say so; the project's one sentence as its description; the license in its wheel, and every license of what installing
it brings on the allowlist, but those the `openhands` extra brings that the owner has yet to rule on; and classifiers
that claim no system STATUS has not seen run and no Python CI does not test."""

import ast
import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

import platoon_harness

ROOT = Path(__file__).parents[2]
VERSION = ROOT / "packages" / "sdk" / "src" / "platoon_harness" / "version.py"
"""The file that sets the version."""
SETS = re.compile(r'^__version__ = "(.+)"$', re.M)
CLI = ROOT / "packages" / "cli" / "src" / "platoon_harness_cli"
LAUNCHER = CLI / "launcher.py"
"""The module the `platoon-harness` command runs."""
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
own files: admitting it is the default, pending the owner's confirmation."""
UNSETTLED = {
    "agent-client-protocol": (),
    "func-timeout": ("License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)",),
    "lupa": ("MIT style",),
    "openhands-sdk": (),
    "openhands-tools": (),
}
"""What each distribution the `openhands` extra brings whose license is not on the allowlist states: no license, the
LGPL, or words that name none. Whether a published extra may bring them is the owner's to rule on: the owner's ruling
that it may bring `lmnr-claude-code-proxy` names that alone."""
KEPT = "Either way, platoon-harness itself stays under the MIT license."
"""What the install guide and the distribution's description say of the extra that brings Laminar's proxy."""
IDENTIFIER = re.compile(r"[^\s()]+")


def project() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


def tool() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]


def imported(path: Path) -> set[str]:
    """The top-level modules `path` imports, by absolute imports anywhere in it."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots |= {alias.name.partition(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            roots.add((node.module or "").partition(".")[0])
    return roots


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


def test_the_version_is_set_once():
    """The distribution reads its version from the SDK's version file, and uv makes its metadata again when that file
    changes, so what a checkout's metadata says is what the file sets."""
    path = tool()["hatch"]["version"]["path"]
    setters = {path: SETS.findall(path.read_text()) for path in (ROOT / "packages").rglob("*.py")}
    version = platoon_harness.__version__

    assert "version" not in project() and project()["dynamic"] == ["version"]
    assert ROOT / path == VERSION
    assert tool()["uv"]["cache-keys"] == [{"file": "pyproject.toml"}, {"file": path}]
    assert {path: found for path, found in setters.items() if found} == {VERSION: [version]}
    assert metadata.version("platoon-harness") == version


def test_the_layers_are_one_distribution():
    """The SDK and the command line are source trees of one wheel, and neither has packaging of its own."""
    held = tool()["hatch"]["build"]["targets"]

    assert held["wheel"]["packages"] == ["packages/sdk/src/platoon_harness", "packages/cli/src/platoon_harness_cli"]
    assert held["sdist"]["only-include"] == held["wheel"]["packages"]
    assert sorted(path.name for path in (ROOT / "packages").glob("*/*") if path.is_file()) == []


def test_the_library_needs_pydantic_alone_and_the_cli_extra_holds_what_the_command_line_imports():
    """`import platoon_harness` needs pydantic and nothing more, so what is built on the library brings nothing else,
    and each distribution a module of the command line imports is pydantic or one the `cli` extra requires."""
    extras = project()["optional-dependencies"]
    cli = {canonicalize_name(Requirement(line).name) for line in extras["cli"]}
    providers = metadata.packages_distributions()
    roots = {root for path in CLI.rglob("*.py") for root in imported(path)}
    outside = roots - set(sys.stdlib_module_names) - {"platoon_harness", "platoon_harness_cli"}
    needed = {canonicalize_name(name) for root in outside for name in providers.get(root, [root])}

    assert [Requirement(line).name for line in project()["dependencies"]] == ["pydantic"]
    assert sorted(extras) == ["cli", "openhands"]
    assert needed - {"pydantic"} <= cli


def test_the_command_runs_a_launcher_that_needs_only_the_standard_library():
    """Without the `cli` extra the command must still say what to install, so the module it names, and what that module
    imports before the command line, import nothing outside the standard library."""
    relative = [
        node.module
        for node in ast.parse(LAUNCHER.read_text()).body
        if isinstance(node, ast.ImportFrom) and node.level == 1
    ]
    first = [LAUNCHER, CLI / "__init__.py", *(CLI / f"{module}.py" for module in relative)]

    assert project()["scripts"] == {"platoon-harness": "platoon_harness_cli.launcher:main"}
    assert relative == ["exits"]
    assert [path.name for path in first if not imported(path) <= set(sys.stdlib_module_names)] == []


def test_the_distribution_is_described_by_the_project_s_sentence():
    """The README opens on it, and the description PyPI shows does too."""
    sentence = project()["description"]
    readme = (ROOT / "README.md").read_text().split("\n\n")[1]

    assert sentence.startswith("Run the agent harnesses you already use")
    assert " ".join(readme.split()) == sentence
    assert sentence in " ".join(project()["readme"]["text"].split())


def test_the_wheel_ships_the_license():
    assert project()["license-files"] == ["LICENSE"] and (ROOT / "LICENSE").is_file()


def test_no_classifier_names_macos_while_nothing_has_run_there():
    assert "Nothing has run on macOS" in (ROOT / "docs" / "STATUS.md").read_text()
    assert [kind for kind in project()["classifiers"] if "MacOS" in kind] == []


def test_the_classifiers_name_the_pythons_ci_tests_and_nothing_else():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    tested = workflow["jobs"]["test"]["strategy"]["matrix"]["python"]
    named = [kind.removeprefix("Programming Language :: Python :: ") for kind in project()["classifiers"]]

    assert [kind for kind in named if "::" not in kind] == tested


def test_every_runtime_dependency_s_license_is_on_the_allowlist():
    """What installing platoon-harness with its `cli` extra brings states a license on the allowlist, every one. The
    `openhands` extra brings besides only what `UNSETTLED` names, and the proxy the checkout excludes, whose license
    nothing here can read, as it is not installed."""
    plain, missing = required(("platoon-harness", ("cli",)))
    extra, excluded = required(("platoon-harness", ("cli", "openhands")))

    assert missing == set() and excluded == set(tool()["uv"]["exclude-dependencies"])
    assert {"platoon-harness", "pydantic", "swarmchat", "textual"} <= plain < extra
    assert unlisted(plain) == {}
    assert unlisted(extra) == UNSETTLED


def test_the_workspace_excludes_the_proprietary_dependency_and_install_md_says_a_published_install_brings_it():
    """OpenHands' SDK requires `lmnr`, which requires Laminar's proxy. The workspace's lock leaves it out, so no
    checkout installs it, and the install guide says so, and that the extra installed from a wheel brings it, which the
    owner has ruled a published install may. The guide and the distribution's description say that platoon-harness stays
    MIT either way."""
    excluded = tool()["uv"]["exclude-dependencies"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    guide = " ".join((ROOT / "docs" / "getting-started" / "install.md").read_text().split())

    assert excluded == ["lmnr-claude-code-proxy"] and lock["manifest"]["excludes"] == excluded
    assert "lmnr" in {Requirement(line).name for line in metadata.requires("openhands-sdk") or []}
    assert "lmnr-claude-code-proxy" in {Requirement(line).name for line in metadata.requires("lmnr") or []}
    with pytest.raises(metadata.PackageNotFoundError):
        metadata.distribution("lmnr-claude-code-proxy")
    assert "`openhands-sdk` requires `lmnr`, which requires `lmnr-claude-code-proxy`" in guide
    assert "The checkout's lock leaves it out with `exclude-dependencies`, so a checkout never installs it" in guide
    assert "the extra installed from the wheel, as an install from PyPI is, brings" in guide
    assert KEPT in guide and KEPT in " ".join(project()["readme"]["text"].split())
