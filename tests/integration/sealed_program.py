"""A sealed harness in a process of its own, which an isolation can confine: a scripted one on the wire that says where
it is installed, our Python and this file. Each turn calls the environment's tool, asks the model and compacts. Run with
`checked`, each turn asks the model, as the checks that earn it trainable expect."""

import itertools
import sys
from pathlib import Path

from platoon_harness.drivers import DriverInfo
from platoon_harness.drivers.env import PYTHON
from platoon_harness.drivers.wire import serve
from platoon_harness.testing import ENVIRONMENT_TOOL, AskModel, Call, Compact, ScriptedDriver, every_turn_asks_the_model

TURN = (Call(ENVIRONMENT_TOOL, {"note": "looked"}), AskModel(), Compact())


class Installed(ScriptedDriver):
    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"installed": (*PYTHON, Path(__file__))})


turns = every_turn_asks_the_model() if sys.argv[1:] == ["checked"] else itertools.repeat(TURN)
serve(Installed(turns, name="wire-sealed"))
