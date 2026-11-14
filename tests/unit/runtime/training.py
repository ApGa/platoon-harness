"""What a test of a training authority's sessions shares: a scripted harness that launches sealed, an authority that
admits through a gateway, in the environment or not, and a result kept for that harness that proves trainable."""

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
UNSEALED = SEALED.model_copy(update={"sealed": False})
IN_ENVIRONMENT = SEALED.model_copy(update={"in_environment": True})
"""What a driver with a launch in the environment declares."""
ORIGIN = "http://127.0.0.1:9"


class Sealed(ScriptedDriver):
    """A scripted harness that says it launches sealed, and has a launch in the environment where `capabilities` say
    so, and that its own login is a plan, and that runs what it is given: it reads nothing of its access until a step
    asks the model. Each message a step says comes from a model call it reports, by an id of the message's own, as one
    the model says comes from the call that asked it."""

    def __init__(self, turns: Iterable[Sequence[Step]] = (), capabilities: Capabilities = SEALED) -> None:
        super().__init__(turns, capabilities=capabilities)

    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"login": "plan"})

    async def _say(self, text: str, call_id: str | None = None) -> None:
        if call_id is None:
            call_id = f"call-{text}"
            await self._report(ModelCall(call_id=call_id, model=self._spec.model))
        await super()._say(text, call_id)


class Gating(LocalAuthority):
    """Admits each agent through a gateway of its own, by a bearer and a backend id of its own, which says the session
    runs in the environment where `in_environment` does, and keeps what it was asked and told."""

    def __init__(self, team: Team, model: str = "m", *, in_environment: bool = False) -> None:
        super().__init__(team)
        self.model = model
        self.in_environment = in_environment
        self.asked: list[SpawnRequest] = []
        self.told: list[tuple[AgentRef, AgentOutcome]] = []

    async def admit(self, spawn: SpawnRequest) -> Admission:
        self.asked.append(spawn)
        bearer = Secret(f"bearer-of-{spawn.agent}")
        gateway = Gateway(origin=ORIGIN, bearer=bearer, model=self.model, in_environment=self.in_environment)
        token = Secret(f"token-{len(self.asked)}")
        return Admission(token=token, access=gateway, backend={"agent_id": f"id-of-{spawn.agent}"})

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        self.told.append((agent, outcome))


TRAINABLE = (
    "ready_with_pinned_model",
    "tool_in_first_request",
    "call_ids_reported",
    "sealed_first_request_holds_only_ours",
    "environment_tools_in_first_request",
    "own_tools_in_first_request_in_the_environment",
)
"""Every check `trainable` needs passed, at a launch in the environment too."""


def kept(root: Path, *failed: str, version: str = "1") -> Path:
    """Keep a result for the sealed harness under `root`, as `write_conformance` keeps one, in which each check that
    `failed` names failed and every other check trainable needs passed."""
    named = dict.fromkeys((*TRAINABLE, *failed))
    checks = tuple(Check(name=name, state="failed" if name in failed else "passed", reason="") for name in named)
    pinned = {"implementation": implementation(Sealed()), "sdk": __version__, "host": socket.gethostname()}
    return write_conformance(root, Conformance(driver="scripted", version=version, checks=checks, **pinned))
