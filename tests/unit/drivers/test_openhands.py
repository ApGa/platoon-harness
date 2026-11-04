"""The `openhands` harness: its worker, found on PATH, as a wire program. The worker itself, on the real OpenHands SDK,
is in `tests/integration/test_openhands.py`."""

import sys

import pytest

from platoon_harness.drivers import Driver, DriverError
from platoon_harness.drivers.openhands import WORKER, OpenHandsDriver
from platoon_harness.extensions import DRIVERS, load

pytestmark = pytest.mark.timeout(30)

STAND_IN = f"""#!{sys.executable}
from platoon_harness.drivers import DriverInfo
from platoon_harness.drivers.wire import serve


class StandIn:
    def describe(self):
        return DriverInfo(name="openhands")


serve(StandIn())
"""


def test_the_openhands_harness_is_its_worker_run_from_path(tmp_path, monkeypatch):
    (tmp_path / WORKER).write_text(STAND_IN)
    (tmp_path / WORKER).chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    driver = load(DRIVERS, "openhands")()

    assert isinstance(driver, OpenHandsDriver) and isinstance(driver, Driver)
    assert driver.command == (WORKER,)
    assert driver.describe().name == "openhands"


def test_with_no_worker_on_path_it_says_how_to_install_one(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(DriverError, match=f"uv tool install {WORKER}"):
        OpenHandsDriver().describe()
