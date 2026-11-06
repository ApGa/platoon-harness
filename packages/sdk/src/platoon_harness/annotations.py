"""Annotations: what an estimator says of the record, a reward or a credit, kept in `annotations.sqlite` beside the
journal and never in it, as `git notes` attach to commits. Each is one producer's statement at one version about one
event at one head, never a fact. `Session.annotate` writes one, checked against the journal, and `Session.annotations`
reads them: the one way in and out. Nothing an agent can reach opens the file. See RFC 0011.
"""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from platoon_harness.kernel import Args
from platoon_harness.schema import Model

__all__ = ["ANNOTATIONS", "Annotate", "Annotation", "Status"]

ANNOTATIONS = "annotations.sqlite"

Status = Literal["scored", "invalid", "error", "timeout", "cancelled"]
"""How an estimate came out. Only `scored` has a value, so the other four are never zero, and with no statement at all a
target is unscored, which no status says."""

EventRef = Annotated[str, Field(pattern=r"^[^\s@#]+@[1-9]\d{0,17}$", max_length=1024)]


class Annotate(Args):
    """One statement about one event of the record, by a named estimator. It is unique on its producer, version, params,
    target and kind, so a second estimator, or a second version, writes beside the first."""

    target: Annotated[EventRef, Field(description="The event it is about, by its ref, `stream@version`.")]
    kind: Annotated[Literal["reward", "credit"], Field(description="`reward` or `credit`.")]
    producer: Annotated[str, Field(min_length=1, max_length=256, description="The estimator that made it, by name.")]
    producer_version: Annotated[str, Field(min_length=1, max_length=256, description="The estimator's version.")]
    params: Annotated[
        dict[str, JsonValue], Field(description="What the estimator was run with, kept as `params_hash`.")
    ] = {}
    scope: Annotated[
        Literal["local", "team"], Field(description="`local` for the target's own, `team` for what its team shares.")
    ]
    status: Annotated[Status, Field(description="`scored`, `invalid`, `error`, `timeout` or `cancelled`.")]
    value: Annotated[
        float | None, Field(allow_inf_nan=False, description="The estimate, given when `status` is `scored` alone.")
    ] = None
    evidence: Annotated[tuple[EventRef, ...], Field(description="The refs of the events it rests on.")] = ()
    head_seq: Annotated[
        int, Field(ge=1, lt=2**63, description="The head the estimator read at, which names the trace it is about.")
    ]

    @model_validator(mode="after")
    def _valued(self) -> "Annotate":
        if (self.value is not None) != (self.status == "scored"):
            raise ValueError("a value is given when the status is `scored`, and only then, as no other is ever zero")
        return self


class Annotation(Model):
    """A statement as `annotations.sqlite` holds it. A client shows its `value` only with its `producer` and
    `producer_version`, beside any other estimate of the same target, and never sums two into a fact."""

    id: int
    target: str
    kind: Literal["reward", "credit"]
    producer: str
    producer_version: str
    params_hash: str
    scope: Literal["local", "team"]
    status: Status
    value: float | None
    evidence: tuple[str, ...]
    head_seq: int
    wall_time: float
