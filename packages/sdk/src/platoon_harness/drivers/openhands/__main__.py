"""The worker, as `python -m platoon_harness.drivers.openhands` runs it: one OpenHands agent served on stdio."""

import os
import sys

from .. import DriverError
from ..wire import serve
from .worker import Worker, sdk_version


def main() -> None:
    """Serve one agent on stdio, or with `--version` say the version of the OpenHands SDK, or why it cannot run. The
    SDK's banner would reach stdout, which is the protocol's, and litellm reaches for a price list on the network unless
    told to use its own."""
    os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    if sys.argv[1:] == ["--version"]:
        try:
            print(sdk_version())
        except DriverError as error:
            sys.exit(str(error))
    else:
        serve(Worker())


if __name__ == "__main__":
    main()
