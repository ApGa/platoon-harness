"""Blobs: the body an event carries, read by the event's ref. A surface stores the bytes first, as for any body."""

from typing import Annotated, Any

from pydantic import Field

from platoon_harness.kernel import Args, Event, Refused, Tombstones, Txn, op

from .common import (
    REF,
    RESULT_LIMIT,
    Exposed,
    Name,
    body_of,
    decoded,
    event_at,
    expose,
    expose_read,
    lines_of,
    size_of,
)
from .exposures import readable


class Blob(Args):
    ref: Annotated[str, Field(pattern=REF, description="A `ref` or `rest` from a result.")]


def _carrier(txn: Txn, ref: str) -> tuple[Event, str]:
    """The event `ref` names and its body, if the caller may read it: an agent one it was handed or made, and anyone
    else any. A miss and a denial answer alike, so a ref is no oracle."""
    event = event_at(txn, ref)
    body = None if event is None else body_of(event)
    me = txn.me
    if event is None or body is None or (me.kind == "agent" and not readable(txn, me.name, event)):
        raise Refused("not_found", f"no body you were handed is at {ref}")
    return event, body


@op("blob.get", on=lambda a: None, exposes=True, tool=True)
def get(txn: Txn, a: Blob) -> dict[str, Any]:
    """Read the body an event carries: pass its `ref`, or a `rest`, from any result. An agent reads what it was handed
    or wrote. A long body comes back cut: `lines` says how many exist and `rest` is the ref to read on with. `text` is
    null for a binary body. Refused `not_found` when there is no such body to read, or it was redacted. `invalid`, with
    `lines`, for a range past the end."""
    ref, _, span = a.ref.partition("#")
    _, body = _carrier(txn, ref)
    data = txn.view(Tombstones).inline(body.removeprefix("sha256:"))
    text = None if data is None else decoded(data)
    if text is None:
        return {"ref": a.ref, "text": None}  # A surface fetches what an op may not read.
    cut = lines_of(ref, text, span or None, RESULT_LIMIT - size_of(a.ref))
    if cut.text is None:
        return {"ref": a.ref, **cut.shown()}
    shown = f"{ref}{cut.span}"
    expose_read(txn, [Exposed.of(shown, "body", cut.text)])
    return {"ref": shown, **cut.shown()}


@op("blob.hash", query=True, runtime=True)
def hash_of(txn: Txn, a: Blob) -> str:
    """The hash of the body an event carries, for a surface to read one in `blobs/`, which no op may, without a model
    ever being shown it."""
    return _carrier(txn, a.ref.partition("#")[0])[1]


class Offered(Args):
    agent: Name
    ref: Annotated[str, Field(pattern=REF)]
    digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


@op("blob.offer", on=lambda a: f"agent/{a.agent}", runtime=True)
def offer(txn: Txn, a: Offered) -> None:
    """Record what a surface showed an agent of a body no op could read, by the ref of the event that carries it and
    the lines shown, before the agent gets it."""
    expose(txn, a.agent, [Exposed(ref=a.ref, form="body", digest=a.digest)], how="read", boundary="tool")
