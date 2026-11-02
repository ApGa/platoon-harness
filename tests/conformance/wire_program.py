"""A wire driver for the conformance suite: a scripted harness in its own process, which can also garble its stdout."""

import os

from platoon_harness.drivers import Delivery, Receipt
from platoon_harness.drivers.wire import serve
from platoon_harness.testing import ScriptedDriver, every_turn_asks_the_model

GARBLE = "garble"


class Garbling(ScriptedDriver):
    async def deliver(self, delivery: Delivery) -> Receipt:
        if delivery.input == GARBLE:
            os.write(1, b"this is no frame\n")
            return Receipt()
        return await super().deliver(delivery)


serve(Garbling(every_turn_asks_the_model(), name="wire-scripted"))
