"""What every primitive shares: names, gists, the address grammar and how an agent's read is recorded."""

import json
import re
from collections.abc import Iterable
from hashlib import sha256
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from platoon_harness.kernel import GIST_LIMIT, NAME, Refused, Tombstones, Txn

Name = Annotated[str, Field(pattern=f"^{NAME}$", max_length=128)]
Gist = Annotated[str, Field(max_length=GIST_LIMIT)]
BodyRef = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Delivery = Literal["pull", "next-turn", "wake", "steer"]

DIGEST_ITEMS = 32
RESULT_LIMIT = (
    12 * 1024
)  # The kernel refuses a command's result past 16 KiB; this leaves room for what frames the rows.

_ADDRESS = re.compile(rf"([@#+])({NAME})")
_STREAMS = {"@": "inbox/", "#": "channel/", "+": "channel/+"}


def stream_of(address: str) -> str:
    """The stream an address names: `@agent`, `#channel` or `+group`."""
    match = _ADDRESS.fullmatch(address)
    if match is None:
        raise Refused("invalid", f"an address is @agent, #channel or +group, not {address[:64]!r}")
    return _STREAMS[match[1]] + match[2]


def size_of(value: Any) -> int:
    """How many bytes a value takes in the journal."""
    return len(json.dumps(value, ensure_ascii=False).encode())


def fitted[T](rows: Iterable[T], *, show: Any = lambda row: row) -> list[T]:
    """As many rows as a command's result can carry."""
    kept, size = [], 0
    for row in rows:
        size += size_of(show(row))
        if size > RESULT_LIMIT:
            break
        kept.append(row)
    return kept


def inline_body(txn: Txn, ref: str) -> bytes | None:
    """A body's bytes, or nothing if they were redacted or sit in `blobs/`, which an op may not read."""
    try:
        return txn.view(Tombstones).inline(ref.removeprefix("sha256:"))
    except Refused:
        return None


def decoded(data: bytes) -> str | None:
    """A body as text, if it is text."""
    try:
        return data.decode()
    except UnicodeDecodeError:
        return None


class Exposed(BaseModel, frozen=True):
    """One thing offered to an agent. `form` is `gist` or `body`, recorded apart, and `digest` hashes what it saw."""

    ref: str
    form: Literal["gist", "body"]
    digest: str

    @classmethod
    def of(cls, ref: str, form: Literal["gist", "body"], content: str | bytes) -> "Exposed":
        text = content if isinstance(content, bytes) else content.encode()
        return cls(ref=ref, form=form, digest=sha256(text).hexdigest())


def expose(
    txn: Txn,
    agent: str,
    items: list[Exposed],
    *,
    how: str,
    boundary: str,
    positions: dict[str, int] | None = None,
    hops: int = 0,
    monitored: bool = False,
) -> int:
    """Record what an agent was offered on `context/<agent>` and return the offer's seq, which names its input."""
    event = txn.emit(
        "context.offered",
        f"context/{agent}",
        gist=f"{len(items)} offered by {how}",
        agent=agent,
        refs=[item.ref for item in items],
        data={
            "items": items,
            "boundary": boundary,
            "how": how,
            "positions": positions or {},
            "hops": hops,
            "monitored": monitored,
        },
    )
    return event.seq


def expose_read(txn: Txn, items: list[Exposed], *, positions: dict[str, int] | None = None, **chain: Any) -> None:
    """An agent's read is evidence and anyone else's is nothing, so only an agent's read writes this."""
    if txn.me.kind == "agent" and (items or positions):
        expose(txn, txn.me.name, items, how="read", boundary="tool", positions=positions, **chain)
