"""The `openhands` harness: its worker, found on PATH, as a wire program. The worker itself, on the real OpenHands SDK,
is in `tests/integration/test_openhands.py`."""

import json
import os
import signal
import stat
import sys
from pathlib import Path

import pytest

from platoon_harness.drivers import Driver, DriverError, Exited
from platoon_harness.drivers.openhands import WORKER, OpenHandsDriver
from platoon_harness.drivers.process import Record
from platoon_harness.extensions import DRIVERS, load

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

STAND_IN = f"""#!{sys.executable}
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
    """A worker on PATH that says what environment it started in."""
    (tmp_path / WORKER).write_text(STAND_IN)
    (tmp_path / WORKER).chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    return tmp_path / f"{WORKER}.env"


def test_the_openhands_harness_is_its_worker_run_from_path(stand_in):
    driver = load(DRIVERS, "openhands")()

    assert isinstance(driver, OpenHandsDriver) and isinstance(driver, Driver)
    assert driver.command == (WORKER,)
    assert driver.describe().name == "openhands"


def test_with_no_worker_on_path_it_says_how_to_build_one_from_a_checkout(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(DriverError, match=f"uv sync --package {WORKER} --frozen"):
        OpenHandsDriver().describe()


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
