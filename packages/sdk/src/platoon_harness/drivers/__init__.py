"""The driver contract: how one harness session is presented to the runtime, whoever wrote the driver."""

from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from platoon_harness.config import Secret
from platoon_harness.primitives import (
    RAW_LIMIT,
    ApprovalRequested,
    Boundary,
    Capabilities,
    Changed,
    ChildSeen,
    Compacted,
    Delta,
    Exited,
    GapReport,
    InputDelivered,
    Item,
    ModelCall,
    Native,
    Ready,
    Report,
    TurnEnded,
    TurnStarted,
    Usage,
    Verdict,
)
from platoon_harness.schema import Model

Login = Literal["native", "plan", "key", "gateway"]
Reconciled = Literal["landed", "not_landed", "unknown"]
Reporter = Callable[[Report], Awaitable[None]]

__all__ = [
    "RAW_LIMIT",
    "AgentSpec",
    "ApprovalRequested",
    "Boundary",
    "Capabilities",
    "Changed",
    "ChildSeen",
    "Compacted",
    "Delivery",
    "Delta",
    "Driver",
    "DriverError",
    "DriverInfo",
    "Exited",
    "GapReport",
    "InputDelivered",
    "Item",
    "Login",
    "ModelCall",
    "Native",
    "Offered",
    "Ready",
    "Receipt",
    "Reconciled",
    "Report",
    "Reporter",
    "Started",
    "ToolBinding",
    "TurnEnded",
    "TurnStarted",
    "Usage",
    "Verdict",
    "unknown_frame",
]


class DriverError(Exception):
    """A driver cannot do what was asked, and says why."""


class DriverInfo(Model):
    """What a driver says of itself before anything starts. `login` is None when it cannot tell without reading one."""

    name: str
    version: str | None = None
    login: Login | None = None
    capabilities: Capabilities = Capabilities()


class ToolBinding(Model):
    """Our tools as one agent reaches them. `namespace` prefixes their names in the harness, and `bin` holds `ph`."""

    url: str
    token: Secret
    namespace: str
    bin: Path


class AgentSpec(Model):
    """One agent to start, or to resume from the native id in `resume`.

    `folder` is the agent's own directory, for its record, log and native home. `access` maps variable names to model
    access, URLs included, and reaches only the harness's environment. `effort` goes to the harness as it stands.
    """

    agent: str
    role: str
    goal: str
    cwd: Path
    folder: Path
    model: str | None = None
    effort: str | None = None
    tools: ToolBinding | None = None
    access: Mapping[str, Secret] = {}
    env: Mapping[str, str] = {}
    instructions: str | None = None
    resume: str | None = None


class Offered(Model):
    """One entry handed over: its ref, who sent it, what a reader sees first, and the ref of any body."""

    ref: str
    gist: str
    sender: str | None = None
    body: str | None = None


class Delivery(Model):
    """One handover. `input` is the id `input.delivered` echoes, `boundary` is one the driver declared, `text` is the
    handover as a harness's prompt reads it, in the words of its surface, and `behind` counts entries left for the
    next."""

    input: str
    boundary: Boundary
    text: str
    items: tuple[Offered, ...]
    behind: int = 0


class Started(Model):
    """A harness launched. `native` is the id to resume it by, when it has one."""

    native: str | None = None


class Receipt(Model):
    """What came of a request: the `boundary` it takes effect at, if known, and inputs `queued` inside the harness."""

    boundary: Boundary | None = None
    queued: tuple[str, ...] = ()


@runtime_checkable
class Driver(Protocol):
    """One harness session, one instance per agent. A method it cannot honor raises `DriverError`."""

    def describe(self) -> DriverInfo: ...

    async def start(self, spec: AgentSpec, report: Reporter) -> Started: ...

    async def deliver(self, delivery: Delivery) -> Receipt: ...

    async def interrupt(self) -> Receipt: ...

    async def answer(self, approval: str, verdict: Verdict) -> None: ...

    async def reconcile(self, input_id: str) -> Reconciled: ...

    async def stop(self, grace: float) -> None: ...


def unknown_frame(
    kind: str, raw: str, plane: Literal["control", "tool", "model"] = "control"
) -> tuple[Native, GapReport]:
    """What a frame nobody's vocabulary covers becomes: the frame, as far as it fits, and the gap it leaves."""
    return Native(kind=kind, raw=raw[:RAW_LIMIT], cut=max(len(raw) - RAW_LIMIT, 0)), GapReport(
        plane=plane, what="unknown_update"
    )
