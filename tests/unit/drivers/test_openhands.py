"""The `openhands` harness: its worker, a wire program on the runtime's own interpreter, and its start where the SDK's
`openhands` extra is missing. The worker on the real OpenHands SDK is in `tests/integration/test_openhands.py`."""

import json
import os
import re
import signal
import stat
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from platoon_harness.config import Secret
from platoon_harness.drivers import Driver, DriverError, Exited, openhands
from platoon_harness.drivers.env import PYTHON
from platoon_harness.drivers.openhands import OpenHandsDriver, worker
from platoon_harness.drivers.process import Record
from platoon_harness.extensions import DRIVERS, load

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

KEYLESS = "openhands signs in with a key alone"
"""How the worker refuses a start with no key, which it can say only once it has loaded."""

ON_PYTHONPATH = """
import asyncio
import sys
from pathlib import Path

from platoon_harness.drivers import AgentSpec, DriverError
from platoon_harness.drivers.openhands import OpenHandsDriver


async def heard(report):
    pass


async def main(work):
    driver = OpenHandsDriver()
    print(driver.describe().name)
    try:
        await driver.start(AgentSpec(agent="ada", role="worker", cwd=work, folder=work / "ada"), heard)
    except DriverError as error:
        print(error)
    finally:
        await driver.stop(2.0)


asyncio.run(main(Path(sys.argv[1])))
"""
"""A runtime's program: it describes the worker, and starts it with no key."""

STAND_IN = """
import json
import os
import sys

from platoon_harness.drivers import DriverInfo
from platoon_harness.drivers.wire import serve


class StandIn:
    def describe(self):
        return DriverInfo(name="openhands")

    async def start(self, spec, report):
        with open(sys.argv[0] + ".env", "w") as file:
            json.dump(dict(os.environ), file)

    async def stop(self, grace):
        pass


serve(StandIn())
"""


@pytest.fixture
def stand_in(tmp_path, monkeypatch):
    """A worker that says what environment it started in, in place of the real one."""
    program = tmp_path / "worker.py"
    program.write_text(STAND_IN)
    monkeypatch.setattr(openhands, "_WORKER", (sys.executable, str(program)))
    return tmp_path / "worker.py.env"


async def test_the_openhands_harness_is_its_worker_as_a_module_on_the_runtime_s_own_interpreter(tmp_path):
    driver = load(DRIVERS, "openhands")()
    spec = make_spec(tmp_path, goal="")

    try:
        with pytest.raises(DriverError, match=KEYLESS):
            await driver.start(spec, Heard())
        record = Record.read(spec.folder)
        assert record is not None
        ran = Path(f"/proc/{record.pid}/cmdline").read_bytes().split(b"\0")[:-1]
    finally:
        await driver.stop(2.0)

    assert isinstance(driver, OpenHandsDriver) and isinstance(driver, Driver)
    assert driver.describe().name == "openhands"
    assert ran == [os.fsencode(part) for part in (sys.executable, "-P", "-m", "platoon_harness.drivers.openhands")]


def test_it_declares_the_python_its_worker_runs_on():
    assert OpenHandsDriver().describe().installed == PYTHON


def test_it_names_no_credential_file_as_openhands_keeps_none_in_its_folder():
    """Its key reaches the worker's environment alone, which reads it and lets it go, and the SDK keeps it in no file:
    `tests/integration/test_openhands.py` shows no file of the session's holds it after a run on the real SDK."""
    assert OpenHandsDriver().describe().credentials == ()


async def test_no_module_of_the_workspace_it_runs_in_stands_in_for_one_of_the_worker_s(tmp_path):
    """The worker runs in the agent's workspace, whose files are the user's to name as they like."""
    (tmp_path / "platoon_harness").mkdir()
    (tmp_path / "platoon_harness" / "__init__.py").write_text("raise SystemExit('the workspace ran')")
    driver = OpenHandsDriver()

    try:
        with pytest.raises(DriverError, match=KEYLESS):
            await driver.start(make_spec(tmp_path, goal=""), Heard())
    finally:
        await driver.stop(2.0)


@pytest.mark.timeout(150)
def test_a_runtime_that_finds_the_sdk_on_pythonpath_runs_a_worker_that_finds_it_there_too(tmp_path):
    """As a module system, an install to a prefix or a checkout would have it, on an interpreter that finds none of the
    SDK alone. The runtime's environment is the shell's, as a detached one's is."""
    base = sys._base_executable
    shell = {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}
    found = {**shell, "PYTHONPATH": os.pathsep.join(filter(None, sys.path))}

    def run(*command: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, env=env, cwd=tmp_path, timeout=60, check=False)

    alone = run(base, "-P", "-c", "import platoon_harness", env=shell)
    done = run(base, "-P", "-c", ON_PYTHONPATH, str(tmp_path), env=found)

    assert alone.returncode != 0
    assert done.stdout.splitlines()[:1] == ["openhands"], done.stderr
    assert done.stdout.splitlines()[1].startswith(KEYLESS), done.stdout


@pytest.mark.parametrize("missing", ["openhands-sdk", "openhands-tools"])
async def test_without_the_extra_the_worker_refuses_to_start_naming_the_interpreter_to_install_it_for(
    tmp_path, monkeypatch, missing
):
    found = worker.version

    def version(name: str) -> str:
        if name == missing:
            raise PackageNotFoundError(name)
        return found(name)

    monkeypatch.setattr(worker, "version", version)
    spec = make_spec(tmp_path, model="m", access={"OPENAI_API_KEY": Secret("k")})
    said = (
        f"{missing} is not installed for {sys.executable}: install platoon-harness's `openhands` extra for it, "
        "beside any other extras it has, "
    )

    with pytest.raises(DriverError, match=f"^{re.escape(said)}`platoon-harness\\[openhands\\]`$"):
        await worker.Worker().start(spec, Heard())


async def test_it_takes_the_shell_s_proxy_and_ca_file_and_no_key_of_the_shell_s(tmp_path, stand_in, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy")
    monkeypatch.setenv("SSL_CERT_FILE", "/their/ca.pem")
    monkeypatch.setenv("OPENAI_API_KEY", "a-key-in-the-shell")
    driver = OpenHandsDriver()

    await driver.start(make_spec(tmp_path, goal=""), Heard())
    await driver.stop(2.0)

    env = json.loads(stand_in.read_text())
    assert (env["HTTPS_PROXY"], env["SSL_CERT_FILE"]) == ("http://proxy", "/their/ca.pem")
    assert "OPENAI_API_KEY" not in env


async def test_its_tmux_directory_is_its_own_and_outlasts_no_stop_even_of_a_worker_killed_outright(tmp_path, stand_in):
    spec = make_spec(tmp_path, goal="")
    driver, heard = OpenHandsDriver(), Heard()
    await driver.start(spec, heard)
    tmux = Path(json.loads(stand_in.read_text())["TMUX_TMPDIR"])
    private = stat.S_IMODE(tmux.stat().st_mode) == 0o700
    record = Record.read(spec.folder)
    assert record is not None
    os.killpg(record.pid, signal.SIGKILL)
    await heard.until(Exited)

    await driver.stop(2.0)

    assert private and not tmux.exists()
