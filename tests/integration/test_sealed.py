"""A sealed launch is earned where it runs: `doctor --check`'s checks of a real harness, on FakeModel acting as a
gateway, keep a result whose sealed checks passed, which makes an agent on a gateway login trainable."""

import shutil

import pytest

from platoon_harness.drivers.levels import Profile, implementation, levels
from platoon_harness.drivers.openhands import OpenHandsDriver
from platoon_harness.drivers.pi import PiDriver
from platoon_harness.runtime.paths import read_conformance, write_conformance
from platoon_harness.testing import check_harness

pytestmark = [pytest.mark.slow, pytest.mark.timeout(1500)]

SEALED = ("sealed_first_request_holds_only_ours", "environment_tools_in_first_request")
DRIVERS = {"pi": PiDriver, "openhands": OpenHandsDriver}


@pytest.mark.parametrize("name", ["pi", "openhands"])
async def test_sealed_conformance_earns_trainable(tmp_path, name):
    if name == "pi" and shutil.which(name) is None:
        pytest.skip("pi is not installed, so this driver met no real harness here")
    write_conformance(tmp_path, await check_harness(name, tmp_path / "check"))
    kept = read_conformance(tmp_path, name)
    assert kept is not None

    driver = DRIVERS[name]()
    on = {"driver": name, "implementation": implementation(driver), "version": kept.version}
    profile = Profile(**on, login="gateway", tools="visible")
    earned = levels(driver.describe().capabilities, profile, kept)

    assert [(check.name, check.state) for check in kept.checks if check.name in SEALED] == [
        (n, "passed") for n in SEALED
    ]
    assert earned.trainable.state == "met", earned.trainable.reasons
