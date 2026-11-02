"""Blobs: a stored body as a citable thing of its own. A surface stores the bytes first, as for any body."""

from typing import Annotated, Any

from pydantic import Field

from platoon_harness.kernel import Args, Tombstones, Txn, op

from .common import Exposed, decoded, expose_read

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Blob(Args):
    sha256: Sha256


@op("blob.put", on=lambda a: f"blob/{a.sha256}", tool=True)
def put(txn: Txn, a: Blob) -> dict[str, Any]:
    """Record a stored body under your name and return its ref. Refused `not_found` when no such body was stored."""
    ref = f"sha256:{a.sha256}"
    txn.emit("blob.put", f"blob/{a.sha256}", gist=f"body {a.sha256[:12]} put", refs=[ref])
    return {"ref": ref}


@op("blob.get", on=lambda a: f"blob/{a.sha256}", exposes=True, tool=True)
def get(txn: Txn, a: Blob) -> dict[str, Any]:
    """Read a stored body's text. A body too large for the journal comes back without text. Refused `not_found` when it
    does not exist or was redacted."""
    ref = f"sha256:{a.sha256}"
    data = txn.view(Tombstones).inline(a.sha256)
    text = None if data is None else decoded(data)
    if data is not None and text is not None:
        expose_read(txn, [Exposed.of(ref, "body", data)])
    return {"ref": ref, "text": text}
