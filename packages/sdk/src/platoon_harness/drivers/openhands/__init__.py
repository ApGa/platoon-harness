"""The `openhands` driver: a wire worker per agent, which the runtime runs on its own interpreter as this package.

Only the worker loads OpenHands, which comes with the SDK's `openhands` extra, so importing this loads none of it.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from .. import AgentSpec, Reporter
from ..wire import WireDriver

WORKER = (sys.executable, "-P", "-m", __name__)
"""The worker's command: the runtime's own interpreter, with nothing of the workspace it runs in on its path."""
_SIGN_IN = (
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
)

__all__ = ["WORKER", "OpenHandsDriver"]


class OpenHandsDriver(WireDriver):
    """One OpenHands agent, through the worker that drives its conversation. Its key comes from the role's auth profile,
    and its way out to the network from the shell, as it would there."""

    def __init__(self) -> None:
        super().__init__(WORKER, _SIGN_IN)
        self._tmux: Path | None = None

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        """Start the worker with a directory of its own for the sockets of the tmux its agents start, short enough for
        one, as OpenHands falls back to the one every tmux of the user's shares past that."""
        self._tmux = Path(tempfile.mkdtemp(prefix="platoon-harness-tmux-"))
        await super().start(spec.model_copy(update={"env": {**spec.env, "TMUX_TMPDIR": str(self._tmux)}}), report)

    async def stop(self, grace: float) -> None:
        """Stop the worker, then take its tmux directory back, which a worker killed outright cannot."""
        await super().stop(grace)
        if self._tmux is not None:
            shutil.rmtree(self._tmux, ignore_errors=True)
