"""The packages as a person installs them: wheels built from this checkout, and from any other project a test installs
beside them, and an environment of their own that holds them and what their metadata requires. uv builds and installs
them offline, as tests take no network, so its cache must hold the build backend and every requirement already, as a
`uv sync` and a `uv build` with the network leave it. Where it does not, the test fails, saying so, and never skips."""

import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from dataclasses import dataclass
from email.message import Message
from email.parser import Parser
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PACKAGES = {"platoon-harness-sdk": "platoon_harness", "platoon-harness-cli": "platoon_harness_cli"}
"""Each distribution, by the import package its wheel holds."""
SECONDS = 300.0
CHECKOUT = ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT")
"""What would point uv or Python at the checkout's own environment."""


def uv(*args: str, cwd: Path) -> None:
    """uv, offline. Where it fails, the test fails with what it said."""
    if (program := shutil.which("uv")) is None:
        pytest.fail("uv is not on PATH, so nothing was built", pytrace=False)
    command = [program, *args, "--offline"]
    done = subprocess.run(command, cwd=cwd, env=apart(), capture_output=True, text=True, timeout=SECONDS, check=False)
    if done.returncode != 0:
        pytest.fail(
            f"`uv {' '.join(args)} --offline` failed, as it does where uv's cache lacks the build backend or a "
            f"requirement: run `uv sync` and `uv build --all-packages` once with the network, then this again.\n"
            f"{done.stderr}",
            pytrace=False,
        )


def apart(**variables: str) -> dict[str, str]:
    """This process's environment, without what points at the checkout's own, and with `variables`."""
    return {name: value for name, value in os.environ.items() if name not in CHECKOUT} | variables


@dataclass(frozen=True)
class Installed:
    """The wheels built from this checkout, by distribution, and the environment of their own they are installed in."""

    wheels: dict[str, Path]
    environment: Path

    def run(self, program: str, *args: str, home: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
        """`program` of the environment, with the environment's `bin` first on `PATH` and `home` the state root."""
        bin = self.environment / "bin"
        env = apart(PATH=f"{bin}{os.pathsep}{os.environ['PATH']}", PLATOON_HARNESS_HOME=str(home))
        command = [str(bin / program), *args]
        return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=SECONDS, check=False)

    def metadata(self, distribution: str) -> Message:
        """The core metadata `distribution`'s wheel holds."""
        with zipfile.ZipFile(self.wheels[distribution]) as wheel:
            [path] = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
            return Parser().parsestr(wheel.read(path).decode())

    def files(self, distribution: str) -> list[str]:
        """The paths `distribution`'s wheel holds."""
        with zipfile.ZipFile(self.wheels[distribution]) as wheel:
            return wheel.namelist()


def install(folder: Path, *projects: Path) -> Installed:
    """Every distribution of this checkout, and each of `projects`, a folder its `pyproject.toml` describes, built into
    `folder / "dist"`, each wheel from its sdist, and the wheels installed as `install_wheels` installs them."""
    dist = folder / "dist"
    uv("build", "--all-packages", "--no-sources", "--out-dir", str(dist), cwd=ROOT)
    for project in projects:
        uv("build", "--no-sources", "--out-dir", str(dist), str(project), cwd=folder)
    named = (tomllib.loads((project / "pyproject.toml").read_text())["project"]["name"] for project in projects)
    wheels: dict[str, Path] = {}
    for name in (*PACKAGES, *named):
        [wheels[name]] = dist.glob(f"{name.replace('-', '_')}-*.whl")
    return install_wheels(folder, wheels)


def install_wheels(folder: Path, wheels: dict[str, Path]) -> Installed:
    """`wheels`, by distribution, installed with what they require in `folder / "environment"`, on this interpreter's
    Python."""
    environment = folder / "environment"
    uv("venv", "--python", sys.executable, str(environment), cwd=folder)
    uv("pip", "install", "--python", str(environment / "bin" / "python"), *map(str, wheels.values()), cwd=folder)
    return Installed(wheels, environment)
