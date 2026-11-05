"""The driver contract: how one harness session is presented to the runtime, whoever wrote the driver."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, Self, runtime_checkable
from urllib.parse import quote, urlsplit

from pydantic import PlainSerializer, field_validator, model_validator

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

BEARER_VARIABLE = "PLATOON_HARNESS_BEARER"
"""Where a sealed launch puts its gateway's bearer: the harness's environment is the one place the bearer goes, and a
file the launch writes names this variable, never its value."""

ENVIRONMENT = "environment"
"""The name a sealed launch gives the environment's own MCP server, which a harness reaches beside ours."""

__all__ = [
    "BEARER_VARIABLE",
    "ENVIRONMENT",
    "RAW_LIMIT",
    "SHORT_LIMIT",
    "UNREADABLE",
    "Access",
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
    "Gateway",
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
    "keys_of",
    "refuse_other_effort",
    "refuse_unset_model",
    "text_of",
    "unknown_frame",
]


class DriverError(Exception):
    """A driver cannot do what was asked, and says why."""


class DriverInfo(Model):
    """What a driver says of itself before anything starts. `login` is None when it cannot tell without reading one, and
    `version` is the harness version it would run, None when it cannot tell without starting one: `ready` says the
    version that runs."""

    name: str
    login: Login | None = None
    version: str | None = None
    capabilities: Capabilities = Capabilities()


class ToolBinding(Model):
    """Our tools as one agent reaches them. `namespace` prefixes their names in the harness, and `bin` holds `ph`."""

    url: str
    token: Secret
    namespace: str
    bin: Path


def _url(text: str, *, path: bool) -> str:
    """A URL a gateway names. A credential goes by the bearer alone, so it has no user, query or fragment, which can
    carry one, and an origin has no path either."""
    found = urlsplit(text)
    if found.scheme not in ("http", "https") or not found.hostname:
        raise ValueError("a gateway's URL is http or https, with a host")
    if found.username is not None or found.query or found.fragment or (found.path and not path):
        raise ValueError(
            "a credential goes by the bearer alone: a gateway's URL has no user, query or fragment, and an origin no "
            "path"
        )
    return text


class Gateway(Model):
    """Model access through a training system's gateway: its models at `origin`, a scheme and a host with nothing more,
    under `bearer`, serving `model`. `tools` is the URL of the environment's own MCP server under the same bearer, when
    there is one, and `compaction_headers` go with each call a harness makes to compact its context, so that the gateway
    tells that call apart as it is made."""

    origin: str
    bearer: Secret
    model: str
    tools: str | None = None
    compaction_headers: Mapping[str, str] = {}

    @field_validator("origin")
    @classmethod
    def _an_origin(cls, origin: str) -> str:
        return _url(origin, path=False)

    @field_validator("tools")
    @classmethod
    def _a_server(cls, tools: str | None) -> str | None:
        return None if tools is None else _url(tools, path=True)

    @model_validator(mode="after")
    def _bearer_alone(self) -> Self:
        bearer = self.bearer.reveal()
        if self.tools is not None and (bearer in self.tools or quote(bearer, safe="") in self.tools):
            raise ValueError("a credential goes by the bearer alone, and the tools' URL holds it")
        return self


def _refused(access: Any) -> dict[str, Any]:
    if access:
        raise TypeError("model access refuses serialization, as the Secret it holds does")
    return {}


Access = Annotated[Mapping[str, Secret] | Gateway, PlainSerializer(_refused)]
"""Model access: variable names to values, URLs included, or a gateway. Either holds a `Secret`, so it refuses
serialization whole, as none would be left to the union's guesses."""


class Offered(Model):
    """One entry handed over: its ref, who sent it, what a reader sees first, and whether it has a body, which
    `blob.get` reads by its ref."""

    ref: str
    gist: str
    sender: str | None = None
    body: bool = False


class Delivery(Model):
    """One handover. `input` is the id `input.delivered` echoes, `boundary` is one the driver declared, `text` is the
    handover as a harness's prompt reads it, in the words of its surface, and `behind` counts entries left for the
    next."""

    input: str
    boundary: Boundary
    text: str
    items: tuple[Offered, ...]
    behind: int = 0


class AgentSpec(Model):
    """One agent to start, or to resume from the native id in `resume`. `goal` is the first delivery of a fresh start,
    under the id of the offer that launched it, so its harness says it landed as it says any input did, and None when
    there is none, as on a resume. `folder` is the agent's own directory, for its record, log and native home. `access`
    is model access: variable names to values, URLs included, that reach only the harness's environment, or a gateway,
    which only a driver that declares `sealed` is given. `effort` goes to the harness as it stands, and `sandbox` is one
    of the values the driver declared. `allow_native_children` lets the harness start agents of its own."""

    agent: str
    role: str
    goal: Delivery | None = None
    cwd: Path
    folder: Path
    model: str | None = None
    effort: str | None = None
    sandbox: str | None = None
    allow_native_children: bool = False
    tools: ToolBinding | None = None
    access: Access = {}
    env: Mapping[str, str] = {}
    instructions: str | None = None
    resume: str | None = None


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


def keys_of(spec: AgentSpec) -> Mapping[str, Secret]:
    """A spec's model access as variables by name, which is all a driver with no sealed launch reads, so it refuses a
    gateway."""
    if isinstance(spec.access, Gateway):
        raise DriverError("this harness has no sealed launch, which a gateway needs")
    return spec.access


def refuse_other_effort(spec: AgentSpec, effort: str | None) -> None:
    """A harness warns of an effort it cannot honor and runs on, so hold what it says it runs at to what was asked."""
    if spec.effort not in (None, effort):
        raise DriverError(f"it runs at effort {effort}, and {spec.effort} was asked for")


def text_of(content: str | Sequence[Mapping[str, Any]]) -> str:
    """What a message or a tool's result says, in either of its shapes."""
    if isinstance(content, str):
        return content
    return "\n".join(block["text"] for block in content if "text" in block)


def unknown_frame(kind: str, raw: str) -> tuple[Native, GapReport]:
    """What a frame nobody's vocabulary covers becomes: the frame, as far as it fits, and the gap it leaves."""
    return Native(kind=kind, raw=raw[:RAW_LIMIT], cut=max(len(raw) - RAW_LIMIT, 0)), GapReport(what="unknown_update")
