"""The kernel's plain data: what is stored, returned and refused."""

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, Field, JsonValue, TypeAdapter

NAME = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
ENROLLED_ID = rf"(agent|human|program|judge):{NAME}"
NAME_LIMIT = 256
GIST_LIMIT = 280
DATA_LIMIT = 16 * 1024
BODY_LIMIT = 64 * 1024

type RefusalCode = Literal[
    "not_permitted",
    "invalid",
    "not_found",
    "conflict",
    "stale_fence",
    "queue_full",
    "queue_empty",
    "over_budget",
    "unsupported",
    "busy",
    "unavailable",
    "key_reused",
    "undeliverable",
]

_JSON: TypeAdapter[Any] = TypeAdapter(Any)


def jsonable(value: Any) -> Any:
    """Reduce models and tuples to the JSON values they will read back as."""
    return _JSON.dump_python(value, mode="json")


def canonical(value: Any) -> str:
    """One text for one JSON value."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def args_hash(op: str, text: str) -> str:
    """Hash a command's identity for idempotency, from its canonical arguments."""
    return sha256(f"{op}\0{text}".encode(errors="surrogatepass")).hexdigest()


def hash_token(token: str) -> str:
    """The form in which a credential may be stored."""
    return sha256(token.encode()).hexdigest()


class Refusal(BaseModel, frozen=True):
    """Why a command or query did not happen. A refusal is data."""

    code: RefusalCode
    op: str | None = None
    object: str | None = None
    reachable: tuple[str, ...] | None = None
    retry_after: float | None = None
    detail: JsonValue = ""


class Refused(Exception):
    """Raised to refuse. `submit` and `query` return the refusal; `read` and `follow` raise it."""

    def __init__(
        self,
        code: RefusalCode,
        detail: JsonValue = "",
        *,
        reachable: tuple[str, ...] | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.refusal = Refusal(code=code, detail=detail, reachable=reachable, retry_after=retry_after)

    @classmethod
    def of(cls, refusal: Refusal) -> "Refused":
        """Raise what an outcome holds, for a caller that wants its refusals as exceptions."""
        refused = cls(refusal.code, refusal.detail)
        refused.refusal = refusal
        return refused


class Outcome(BaseModel, frozen=True):
    """How a command or query ended. `seq` is that of the event carrying it, if it has one."""

    op: str
    key: str | None = None
    args_hash: str
    result: Any = None
    refusal: Refusal | None = None
    seq: int | None = None


class ModelRef(BaseModel, frozen=True):
    """The model call behind an event. Present only when real."""

    policy: str | None = None
    version: str | None = None
    call_id: str | None = None
    tool_call_id: str | None = None
    token_span: tuple[int, int] | None = None


class Event(BaseModel, frozen=True):
    """One immutable fact, on exactly one stream."""

    v: int
    seq: int
    stream: str
    version: int
    type: str
    actor: str
    agent: str | None
    turn: str | None
    context_version: int | None
    episode: str | None
    topology_rev: int
    correlation: str | None
    cause: tuple[int, ...]
    based_on: tuple[str, ...]
    native: Mapping[str, str]
    model: ModelRef | None
    wall_time: float
    gist: str
    data: Any
    outcome: Outcome | None


class Page(BaseModel, frozen=True):
    """A run of events. Pass `cursor` as the next `after`."""

    events: tuple[Event, ...]
    cursor: int
    head: int


class Delta(BaseModel, frozen=True):
    """Live text an agent said past a reader's frame, joined, through `frame`. `ended` is the seq of the event that
    replaced what it said before this text, an item or an end, which the journal holds through that seq, so a reader
    drops its own copy. `lag` counts frames of this text that are no longer held."""

    agent: str
    frame: int
    text: str
    lag: int = 0
    ended: int | None = None


class Principal(BaseModel, frozen=True):
    """An authenticated actor. The id is `runtime`, or `<kind>:<name>`."""

    id: str = Field(pattern=rf"^(runtime|{ENROLLED_ID})$")
    role: str | None = None
    parent: str | None = None
    path: str = "/"
    state: Literal["live", "revoked"] = "live"
    scopes: tuple[str, ...] = ("*",)

    @property
    def kind(self) -> str:
        return self.id.partition(":")[0]

    @property
    def name(self) -> str:
        return self.id.partition(":")[2] or self.id
