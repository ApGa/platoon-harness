"""OpenCode through the ACP driver, on the real binary against FakeModel. Free: a dummy key, a home of the check's own,
and loopback only.

It needs `opencode` on `PATH`, which nothing here installs, and skips, saying so, where it is not. Where it is, it fails
today, for the reasons STATUS gives (RFC 0072).
"""

import shutil

import pytest

from platoon_harness.drivers.levels import Profile, implementation, levels
from platoon_harness.drivers.opencode import OpenCodeDriver
from platoon_harness.testing import check_harness

pytestmark = [pytest.mark.slow, pytest.mark.timeout(1800)]


@pytest.fixture(autouse=True)
def opencode_is_here() -> None:
    if shutil.which("opencode") is None:
        pytest.skip("opencode is not on PATH, so OpenCode's check against FakeModel did not run here")


async def test_opencode_through_acp_passes_check_driver_against_fake_model(tmp_path):
    """The SDK's own check of it, which `doctor --check` runs, through `check_harness` as `doctor` reaches it: nothing
    fails, and it earns operational and observable, and never trainable."""
    result = await check_harness("opencode", tmp_path)

    print(result)
    assert result.failed == (), str(result)
    assert result.driver == "opencode" and result.implementation == implementation(OpenCodeDriver())
    profile = Profile(driver="opencode", implementation=result.implementation, version=result.version, login="gateway")
    earned = levels(OpenCodeDriver().describe().capabilities, profile, result)
    assert (earned.operational.state, earned.observable.state, earned.trainable.state) == ("met", "met", "unmet")
