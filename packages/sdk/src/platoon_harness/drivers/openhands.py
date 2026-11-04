"""The `openhands` driver: a wire worker per agent, in an environment of its own, as OpenHands shares one with nobody.

The worker is `platoon-harness-openhands`, from the distribution of that name, on the runtime's `PATH`.
"""

import shutil

from . import DriverError, DriverInfo
from .wire import WireDriver

WORKER = "platoon-harness-openhands"

__all__ = ["WORKER", "OpenHandsDriver"]


class OpenHandsDriver(WireDriver):
    """One OpenHands agent, through the worker that drives its conversation."""

    def __init__(self) -> None:
        super().__init__([WORKER])

    def describe(self) -> DriverInfo:
        if shutil.which(WORKER) is None:
            raise DriverError(f"{WORKER} is not on PATH: install it with `uv tool install {WORKER}`")
        return super().describe()
