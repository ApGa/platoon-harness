"""What a driver says of a harness: its capabilities, and one closed vocabulary of reports, in Python or on the wire."""

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal, NamedTuple

from pydantic import Field, TypeAdapter

from platoon_harness.kernel import Args, Effects, Stamps, Txn
from platoon_harness.schema import Model

from .budgets import Label
from .common import BodyRef, Gist, Name

RAW_LIMIT = 2048
SHORT_LIMIT = 256
OWNER_STOP = "stopped by its owner"
CUT_OFF = {"lost": "a crash", OWNER_STOP: "the owner stopping the session"}
"""The reasons only the runtime can give a turn, each with what cut that turn off, as a notice says it."""

Short = Annotated[str, Field(max_length=SHORT_LIMIT)]
Boundary = Literal["turn", "tool", "model_call"]
Plane = Literal["control", "tool", "model"]
Surface = Literal["prompt", "tool_results", "shell_reads", "files", "native_children", "compaction", "external"]
Gap = Literal[
    "stream_lost",
    "compaction_opaque",
    "native_child_unattributed",
    "usage_lower_bound",
    "unknown_update",
    "hidden_call",
    "crash_window",
    "takeover",
    "workspace_unobserved",
]


class Kind(NamedTuple):
    """What a gap of the closed set is: the plane it lies on, who records it, and whether content could reach an agent
    through it unseen, which is what makes it a reason that what an agent saw is unknown."""

    plane: Plane
    writers: tuple[Literal["driver", "runtime"], ...]
    carries: bool


GAPS: Mapping[Gap, Kind] = {
    "stream_lost": Kind("control", ("driver",), carries=True),
    "compaction_opaque": Kind("control", ("runtime",), carries=False),
    "native_child_unattributed": Kind("model", ("driver",), carries=True),
    "usage_lower_bound": Kind("model", ("driver",), carries=False),
    "unknown_update": Kind("control", ("driver", "runtime"), carries=True),
    "hidden_call": Kind("model", ("driver",), carries=True),
    "crash_window": Kind("control", ("driver", "runtime"), carries=True),
    "takeover": Kind("control", ("runtime",), carries=True),
    "workspace_unobserved": Kind("control", ("runtime",), carries=True),
}
"""Every gap a `gap.recorded` can name, and what each is."""


def record_gap(
    txn: Txn, agent: str, what: Gap, *, gist: str | None = None, cause: Sequence[int] = (), **more: Any
) -> None:
    """Record one incident gap on its agent's stream, on its own plane. A `crash_window`, the one recorded after the
    fact, names in `since` where the work it could not prove began: the start of the agent's turn it cut, or else the
    request of the agent's oldest uncertain effect, and with neither it stands where it is."""
    since = _unproven(txn, agent) if what == "crash_window" else None
    data = {"plane": GAPS[what].plane, "what": what, "since": since, **more}
    txn.emit("gap.recorded", f"agent/{agent}", gist=gist or f"gap: {what}", agent=agent, cause=cause, data=data, v=2)


def _unproven(txn: Txn, agent: str) -> int | None:
    if (began := txn.view(Stamps).began(agent)) is not None:
        return began
    return min((effect.id for effect in txn.view(Effects).in_state("uncertain") if effect.agent == agent), default=None)


class Capabilities(Model):
    """What a driver declares of a harness. Absence means unsupported, and `levels` believes only what was verified."""

    persistent: bool = False
    resume: bool = False
    boundaries: frozenset[Boundary] = frozenset()
    tool_paths: frozenset[Literal["mcp-http", "mcp-stdio", "shell"]] = frozenset()
    tool_names: Literal["namespaced", "bare"] = "namespaced"
    tool_timeout_s: float | None = None
    interrupt: bool = False
    approvals: Literal["none", "gated", "native"] = "none"
    native_children: Literal["none", "observed", "opaque"] = "none"
    call_ids: Literal["none", "agent", "call"] = "none"
    dialects: frozenset[Literal["chat", "responses", "messages"]] = frozenset()
    coverage: Mapping[Surface, Literal["observed", "partial", "none"]] = {}
    measures: frozenset[Literal["tokens", "usd"]] = frozenset()
    sandboxes: frozenset[str] = frozenset()


class Ready(Args):
    """A harness is up. `tools_visible` is a list only when it comes from an observed source."""

    type: Literal["ready"] = "ready"
    native: str | None = None
    version: str | None = None
    effective_model: str | None = None
    tools_visible: tuple[str, ...] | None = None


class TurnStarted(Args):
    type: Literal["turn.started"] = "turn.started"
    turn: Short


class TurnEnded(Args):
    """`stopped` if it stopped on its own, `interrupted` if someone stopped it, and otherwise what went wrong. A driver
    cannot say a reason in `CUT_OFF`, which are the runtime's own."""

    type: Literal["turn.ended"] = "turn.ended"
    reason: Short = "stopped"


class Delta(Args):
    """Live text. It is lossy and never journaled: the `item` that follows is authoritative."""

    type: Literal["delta"] = "delta"
    text: str


class Item(Args):
    """One thing a harness did or began. A tool or a patch is `started` while under way, so `activity` can say what is
    running, then `completed`, and a message or a thought has no `phase`. `approval` names the approval an outcome
    answers. `call_id` names the model call that made it, when the harness says so. `body` is its whole text until the
    host stores it and journals the hash."""

    type: Literal["item"] = "item"
    kind: Literal["message", "thought", "tool", "patch"]
    gist: Gist
    phase: Literal["started", "completed"] | None = None
    native_id: Short | None = None
    call_id: Short | None = None
    body: str | None = None
    approval: Name | None = None
    outcome: str | None = None


class InputDelivered(Args):
    """A delivery reached the harness. `evidence` names what showed it, which is what makes this observed exposure, and
    `native_id` is the harness's own id for what landed."""

    type: Literal["input.delivered"] = "input.delivered"
    input: Short
    boundary: Boundary
    evidence: str | None = None
    native_id: Short | None = None


class ApprovalRequested(Args):
    type: Literal["approval.requested"] = "approval.requested"
    id: Name
    gist: Gist


class ModelCall(Args):
    """A model call the harness made. `call_id` is present only when it is real, and `purpose` only when the harness
    said why, in its own word, such as `compaction`."""

    type: Literal["model.call"] = "model.call"
    call_id: Short | None = None
    model: str | None = None
    purpose: Short | None = None


class Usage(Args):
    """What was spent, once: `scope` says what the amounts cover, one `call`, this agent's `turn`, or its whole `tree`
    with native children. A driver reports each spend at one scope. `tokens` counts input and output, cached input
    included. `call_id` names the model call, when the harness says so."""

    type: Literal["usage"] = "usage"
    tokens: int | None = None
    usd: float | None = None
    label: Label
    scope: Literal["call", "turn", "tree"] = "turn"
    call_id: Short | None = None


class Compacted(Args):
    """A harness compacted its context. `forgotten` holds the native ids of what left it, None if nobody can say, and
    `summary` the text that took its place. Each is that until the host stores it and journals the hash."""

    type: Literal["compacted"] = "compacted"
    forgotten: tuple[str, ...] | BodyRef | None = None
    summary: str | None = None


class ChildSeen(Args):
    """A native child the harness made on its own, which stays on its parent's credential: its native id, and the tool
    call of its parent's that started it. How well a call is tied to an agent is the record's to say, so no driver
    claims it."""

    type: Literal["child.seen"] = "child.seen"
    native: str
    parent: str | None = None


class GapReport(Args):
    """A gap a driver saw. Its plane is the gap's own."""

    type: Literal["gap"] = "gap"
    what: Gap


class Native(Args):
    """A frame nobody's vocabulary covers, as it came, up to 2 KiB. `cut` says how many characters did not fit."""

    type: Literal["native"] = "native"
    kind: Short
    raw: Annotated[str, Field(max_length=RAW_LIMIT)]
    cut: int = 0


class Exited(Args):
    type: Literal["exited"] = "exited"
    reason: str = "the harness exited"


type Report = Annotated[
    Ready
    | TurnStarted
    | TurnEnded
    | Delta
    | Item
    | InputDelivered
    | ApprovalRequested
    | ModelCall
    | Usage
    | Compacted
    | ChildSeen
    | GapReport
    | Native
    | Exited,
    Field(discriminator="type"),
]

REPORTS: TypeAdapter[Report] = TypeAdapter(Report)
"""The vocabulary as a parser: `REPORTS.validate_json(text)`. Anything it refuses is an unknown frame."""
