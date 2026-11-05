"""What a test of a training authority's sessions shares: a scripted harness that launches sealed, an authority that
admits through a gateway, and a result kept for that harness that proves trainable."""

import socket
from collections.abc import Iterable, Sequence
from pathlib import Path

from platoon_harness import Team, __version__
from platoon_harness.config import Secret
from platoon_harness.drivers import Capabilities, DriverInfo, Gateway, ModelCall
from platoon_harness.drivers.levels import Check, Conformance, implementation
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, LocalAuthority, SpawnRequest
from platoon_harness.runtime.paths import write_conformance
from platoon_harness.testing import ScriptedDriver
from platoon_harness.testing.scripted import Step

SEALED = Capabilities(
    persistent=True, resume=True, boundaries={"turn"}, tool_paths={"mcp-http"}, call_ids="call", sealed=True
)
ORIGIN = "http://127.0.0.1:9"


class Sealed(ScriptedDriver):
    """A scripted harness that says it launches sealed and that its own login is a plan, and that runs what it is
    given: it reads nothing of its access until a step asks the model. Each message it says comes from a model call it
    reports, by an id of the message's own."""

    def __init__(self, turns: Iterable[Sequence[Step]] = ()) -> None:
        super().__init__(turns, capabilities=SEALED)

    def describe(self) -> DriverInfo:
        return DriverInfo(name="scripted", login="plan", version="1", capabilities=SEALED)

    async def _say(self, text: str, call_id: str | None = None) -> None:
        said = call_id or f"call-{text}"
        await self._report(ModelCall(call_id=said, model=self._spec.model))
        await super()._say(text, said)


class Gating(LocalAuthority):
    """Admits each agent through a gateway of its own, by a bearer and a backend id of its own, and keeps what it was
    asked and told."""

    def __init__(self, team: Team, model: str = "m") -> None:
        super().__init__(team)
        self.model = model
        self.asked: list[SpawnRequest] = []
        self.told: list[tuple[AgentRef, AgentOutcome]] = []

    async def admit(self, spawn: SpawnRequest) -> Admission:
        self.asked.append(spawn)
        gateway = Gateway(origin=ORIGIN, bearer=Secret(f"bearer-of-{spawn.agent}"), model=self.model)
        token = Secret(f"token-{len(self.asked)}")
        return Admission(token=token, access=gateway, backend={"agent_id": f"id-of-{spawn.agent}"})

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        self.told.append((agent, outcome))


TRAINABLE = ("ready_with_pinned_model", "tool_in_first_request", "call_ids_reported")


def kept(root: Path, *failed: str, version: str = "1") -> Path:
    """Keep a result for the sealed harness under `root`, as `write_conformance` keeps one, whose checks that trainable
    stands on passed but `failed`."""
    checks = tuple(Check(name=name, state="failed" if name in failed else "passed", reason="") for name in TRAINABLE)
    pinned = {"implementation": implementation(Sealed()), "sdk": __version__, "host": socket.gethostname()}
    return write_conformance(root, Conformance(driver="scripted", version=version, checks=checks, **pinned))
