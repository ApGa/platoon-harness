"""A result made from a read-only installation speaks for it wherever it is mounted: each real harness, run from one
installation in two sandboxes of bwrap's, each under a host name of its own and showing everything read-only but a /tmp
of its own and the test's folder, makes its result in one and earns its levels from it in the other."""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from platoon_harness.drivers.levels import Conformance
from platoon_harness.runtime.paths import read_conformance

from ..unit.runtime import support

pytestmark = [pytest.mark.slow, pytest.mark.timeout(1500)]

PROGRAM = str(Path(__file__).with_name("from_installation.py"))


async def sandboxed(host: str, folder: Path, case: str, harness: str) -> dict[str, Any]:
    """What `from_installation.py` found of `harness`, run under the host name `host` in a sandbox of bwrap's that
    shows everything read-only but a /tmp of its own and `folder`, which holds its home."""
    home = folder / "home"
    home.mkdir(exist_ok=True)
    namespaces = ("--unshare-user", "--unshare-pid", "--unshare-uts", "--hostname", host, "--die-with-parent")
    seen = ("--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp")
    process = await asyncio.create_subprocess_exec(
        *("bwrap", *namespaces, *seen, "--bind", str(folder), str(folder), "--"),
        *(sys.executable, "-P", PROGRAM, case, harness, str(folder)),
        env={**os.environ, "HOME": str(home), "TMPDIR": "/tmp"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await process.communicate()
    assert process.returncode == 0, err.decode(errors="replace")
    return json.loads(out)


@pytest.mark.parametrize("harness", ["pi", "openhands"])
async def test_a_result_made_under_one_host_name_speaks_under_another_from_the_same_installation(tmp_path, harness):
    """A training system makes one result from its build, in a sandbox like its rollouts', and places it in each fresh
    root. Here the build is the installation this runs from, every path of it read-only in both sandboxes, and the
    rollout's sandbox goes by another host name: the result names the installation, `check` finds nothing in the way of
    a trainable session before any harness launches, and the agent's start records the same installation and a
    trainable level that says where its result was made."""
    if harness == "pi" and shutil.which("pi") is None:
        pytest.skip("pi is not installed, so this met no real harness here")
    support.bubblewrap()

    result = Conformance.model_validate(await sandboxed("builder", tmp_path, "make", harness))
    ran = await sandboxed("rollout", tmp_path, "start", harness)

    assert (result.host, result.failed, read_conformance(tmp_path / "root", harness)) == ("builder", (), result)
    assert result.installation is not None
    assert ran["problems"] == [] and "agent.started" in ran, ran
    started = ran["agent.started"]
    assert (started["verified"]["host"], started["verified"]["installation"]) == ("rollout", list(result.installation))
    assert started["levels"]["trainable"] == {
        "state": "met",
        "reasons": ["its result was made on builder, from this installation"],
    }
