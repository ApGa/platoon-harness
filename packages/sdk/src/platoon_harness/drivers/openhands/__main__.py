"""The worker, as `python -P -m platoon_harness.drivers.openhands` runs it: one OpenHands agent served on stdio."""

import os

from ..wire import serve
from .worker import Worker


def main() -> None:
    """Serve one agent on stdio. The SDK's banner would reach stdout, which is the protocol's, and litellm reaches for a
    price list on the network unless told to use its own."""
    os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    serve(Worker())


if __name__ == "__main__":
    main()
