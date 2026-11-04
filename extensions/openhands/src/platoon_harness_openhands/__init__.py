"""OpenHands as a harness: `platoon-harness-openhands` is a wire worker per agent, on the OpenHands SDK."""

import os
import sys
from importlib.metadata import version

from platoon_harness.drivers.wire import serve

from .worker import SDK, Worker

__all__ = ["main"]


def main() -> None:
    """Serve one agent on stdio, or say the version of the OpenHands SDK with `--version`. The SDK's banner would reach
    stdout, which is the protocol's, and litellm reaches for a price list on the network unless told to use its own."""
    os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    if sys.argv[1:] == ["--version"]:
        print(version(SDK))
        return
    serve(Worker())
