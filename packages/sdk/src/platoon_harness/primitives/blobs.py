"""Blobs: a stored body read by its hash. A surface stores the bytes first, as for any body."""

from typing import Annotated, Any

from pydantic import Field

from platoon_harness.kernel import Args, Tombstones, Txn, op

from .common import LINE_RANGE, RESULT_LIMIT, Exposed, Name, decoded, expose, expose_read, lines_of, size_of

_REF = rf"^sha256:[0-9a-f]{{64}}(#{LINE_RANGE})?$"


class Blob(Args):
    ref: Annotated[str, Field(pattern=_REF, description="A `body` or `rest` from a result.")]

    @property
    def sha256(self) -> str:
        return self.ref[len("sha256:") :].partition("#")[0]


@op("blob.get", on=lambda a: f"blob/{a.sha256}", exposes=True, tool=True)
def get(txn: Txn, a: Blob) -> dict[str, Any]:
    """Read a stored body's text: pass a `body` or `rest` from any result as `ref`. A long body comes back cut: `lines`
    says how many exist and `rest` is the ref to read on with. `text` is null for a binary body. Refused `not_found`
    when it does not exist or was redacted. `invalid`, with `lines`, for a range past the end."""
    body, _, span = a.ref.partition("#")
    data = txn.view(Tombstones).inline(a.sha256)
    text = None if data is None else decoded(data)
    if text is None:
        return {"ref": a.ref, "text": None}  # A surface fetches what an op may not read.
    cut = lines_of(body, text, span or None, RESULT_LIMIT - size_of(a.ref))
    if cut.text is None:
        return {"ref": a.ref, **cut.shown()}
    ref = f"{body}{cut.span}"
    expose_read(txn, [Exposed.of(ref, "body", cut.text)])
    return {"ref": ref, **cut.shown()}


class Offered(Args):
    agent: Name
    ref: Annotated[str, Field(pattern=_REF)]
    digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


@op("blob.offer", on=lambda a: f"agent/{a.agent}", runtime=True)
def offer(txn: Txn, a: Offered) -> None:
    """Record what a surface showed an agent of a body no op could read, before the agent gets it."""
    expose(txn, a.agent, [Exposed(ref=a.ref, form="body", digest=a.digest)], how="read", boundary="tool")
