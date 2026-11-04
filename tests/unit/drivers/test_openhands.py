"""The `openhands` harness: its worker, a wire program on the runtime's own interpreter, and its start where the SDK's
`openhands` extra is missing. The worker on the real OpenHands SDK is in `tests/integration/test_openhands.py`."""

import json
import os
import re
import signal
import stat
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from platoon_harness.config import Secret
from platoon_harness.drivers import Driver, DriverError, Exited, openhands
from platoon_harness.drivers.openhands import WORKER, OpenHandsDriver, worker
from platoon_harness.drivers.process import Record
from platoon_harness.extensions import DRIVERS, load

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

INSTALL = "pip install 'platoon-harness-sdk[openhands]'"

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
    monkeypatch.setattr(openhands, "WORKER", (sys.executable, str(program)))
    return tmp_path / "worker.py.env"


def test_the_openhands_harness_is_its_worker_on_the_runtime_s_own_interpreter():
    driver = load(DRIVERS, "openhands")()

    assert isinstance(driver, OpenHandsDriver) and isinstance(driver, Driver)
    assert driver.command == WORKER == (sys.executable, "-P", "-m", "platoon_harness.drivers.openhands")
    assert driver.describe().name == "openhands"


async def test_no_module_of_the_workspace_it_runs_in_stands_in_for_one_of_the_worker_s(tmp_path):
    """The worker runs in the agent's workspace, whose files are the user's to name as they like."""
    (tmp_path / "platoon_harness").mkdir()
    (tmp_path / "platoon_harness" / "__init__.py").write_text("raise SystemExit('the workspace ran')")
    driver = OpenHandsDriver()

    try:
        with pytest.raises(DriverError, match="openhands signs in with a key alone"):
            await driver.start(make_spec(tmp_path, goal=""), Heard())
    finally:
        await driver.stop(2.0)


@pytest.mark.parametrize("missing", ["openhands-sdk", "openhands-tools"])
async def test_without_the_extra_the_worker_refuses_to_start_saying_how_to_install_it(tmp_path, monkeypatch, missing):
    found = worker.version

    def version(name: str) -> str:
        if name == missing:
            raise PackageNotFoundError(name)
        return found(name)

    monkeypatch.setattr(worker, "version", version)
    spec = make_spec(tmp_path, model="m", access={"OPENAI_API_KEY": Secret("k")})

    with pytest.raises(DriverError, match=f"^{missing} is not installed: .*{re.escape(INSTALL)}"):
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
