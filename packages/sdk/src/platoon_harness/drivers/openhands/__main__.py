"""The worker, as `python -P -m platoon_harness.drivers.openhands` runs it: one OpenHands agent served on stdio."""

import os

from ..wire import serve
from .worker import Worker


def main() -> None:
    """Serve one agent on stdio. The SDK's banner would reach stdout, which is the protocol's, and litellm reaches for a
    price list on the network unless told to use its own. The folder its driver gave tmux is made again where this
    worker's `/tmp` is its own, as in an isolation."""
    os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    if tmux := os.environ.get("TMUX_TMPDIR"):
        os.makedirs(tmux, mode=0o700, exist_ok=True)
    serve(Worker())


if __name__ == "__main__":
    main()
