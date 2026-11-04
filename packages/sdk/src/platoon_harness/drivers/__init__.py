"""The driver contract: how one harness session is presented to the runtime, whoever wrote the driver."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from platoon_harness.config import Secret
from platoon_harness.primitives import (
    RAW_LIMIT,
    SHORT_LIMIT,
    ApprovalRequested,
    Boundary,
    Capabilities,
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

Login = Literal["plan", "key", "gateway"]
Reconciled = Literal["landed", "not_landed", "unknown"]
Reporter = Callable[[Report], Awaitable[None]]

UNREADABLE = (AttributeError, KeyError, TypeError, ValueError, RecursionError)
"""What reading a harness's frame raises, whichever part of it would not read."""

__all__ = [
    "RAW_LIMIT",
    "SHORT_LIMIT",
    "UNREADABLE",
    "AgentSpec",
    "ApprovalRequested",
    "Boundary",
    "Capabilities",
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
    "Reconciled",
    "Report",
    "Reporter",
    "ToolBinding",
    "TurnEnded",
    "TurnStarted",
    "Usage",
    "Verdict",
    "refuse_other_effort",
    "refuse_unset_model",
    "text_of",
    "unknown_frame",
]


class DriverError(Exception):
    """A driver cannot do what was asked, and says why."""


class DriverInfo(Model):
    """What a driver says of itself before anything starts. `login` is None when it cannot tell without reading one."""

    name: str
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
    access, URLs included, and reaches only the harness's environment. `effort` goes to the harness as it stands, and
    `sandbox` is one of the values the driver declared. `allow_native_children` lets the harness start agents of its
    own.
    """

    agent: str
    role: str
    goal: str
    cwd: Path
    folder: Path
    model: str | None = None
    effort: str | None = None
    sandbox: str | None = None
    allow_native_children: bool = False
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


@runtime_checkable
class Driver(Protocol):
    """One harness session, one instance per agent. A method it cannot honor raises `DriverError`."""

    def describe(self) -> DriverInfo: ...

    async def start(self, spec: AgentSpec, report: Reporter) -> None: ...

    async def deliver(self, delivery: Delivery) -> None: ...

    async def interrupt(self) -> None: ...

    async def answer(self, approval: str, verdict: Verdict) -> None: ...

    async def reconcile(self, input_id: str) -> Reconciled: ...

    async def stop(self, grace: float) -> None: ...


def refuse_unset_model(spec: AgentSpec) -> None:
    """On a harness's own login its default is the user's. Where access was given, it may go somewhere nobody chose."""
    if spec.model is None and spec.access:
        raise DriverError("set a model: with access given, this harness's default may go somewhere nobody chose")


def refuse_other_effort(spec: AgentSpec, effort: str | None) -> None:
    """A harness warns of an effort it cannot honor and runs on, so hold what it says it runs at to what was asked."""
    if spec.effort not in (None, effort):
        raise DriverError(f"it runs at effort {effort}, and {spec.effort} was asked for")


def text_of(content: str | Sequence[Mapping[str, Any]]) -> str:
    """What a message or a tool's result says, in either of its shapes."""
    if isinstance(content, str):
        return content
    return "\n".join(block["text"] for block in content if "text" in block)


def unknown_frame(
    kind: str, raw: str, plane: Literal["control", "tool", "model"] = "control"
) -> tuple[Native, GapReport]:
    """What a frame nobody's vocabulary covers becomes: the frame, as far as it fits, and the gap it leaves."""
    return Native(kind=kind, raw=raw[:RAW_LIMIT], cut=max(len(raw) - RAW_LIMIT, 0)), GapReport(
        plane=plane, what="unknown_update"
    )
