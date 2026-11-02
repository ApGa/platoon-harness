"""Blobs: a stored body read by its hash. A surface stores the bytes first, as for any body."""

from typing import Annotated, Any

from pydantic import Field

from platoon_harness.kernel import Args, Tombstones, Txn, op

from .common import RESULT_LIMIT, Exposed, decoded, expose_read, size_of


class Blob(Args):
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", description="The hash from a `body`, without `sha256:`.")]


@op("blob.get", on=lambda a: f"blob/{a.sha256}", exposes=True, tool=True)
def get(txn: Txn, a: Blob) -> dict[str, Any]:
    """Read a stored body's text. A body too long for one result comes back without text. Refused `not_found` when it
    does not exist or was redacted."""
    ref = f"sha256:{a.sha256}"
    data = txn.view(Tombstones).inline(a.sha256)
    text = None if data is None else decoded(data)
    if data is None or text is None or size_of(text) > RESULT_LIMIT:
        return {"ref": ref, "text": None}
    expose_read(txn, [Exposed.of(ref, "body", data)])
    return {"ref": ref, "text": text}
