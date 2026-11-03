"""What every primitive shares: names, gists, the address grammar and how an agent's read is recorded."""

import json
import re
from collections.abc import Iterable
from hashlib import sha256
from typing import Annotated, Any, Literal, NamedTuple

from pydantic import AfterValidator, BaseModel, Field

from platoon_harness.kernel import GIST_LIMIT, NAME, Args, Refused, Stamps, Tombstones, Txn


def _bare(name: str) -> str:
    return name.removeprefix("@").removeprefix("agent:")


Name = Annotated[str, Field(pattern=f"^{NAME}$", max_length=128)]
AgentName = Annotated[str, Field(pattern=f"^(@|agent:)?{NAME}$", max_length=134), AfterValidator(_bare)]
Gist = Annotated[str, Field(max_length=GIST_LIMIT, description="What readers see first, at most 280 characters.")]
BODY_REF = r"^sha256:[0-9a-f]{64}$"
BodyRef = Annotated[str, Field(pattern=BODY_REF)]
Body = Annotated[BodyRef | None, Field(description="Anything longer than the gist.")]
Seq = Annotated[int, Field(ge=0, lt=2**63)]
BasedOn = Annotated[tuple[str, ...], Field(description="Refs this rests on, such as a `ref` you read.")]
Injection = Literal["pull", "next-turn", "wake", "steer"]
Policy = Literal["ask", "deny", "allow"]

WAKING: tuple[Injection, ...] = ("wake", "steer")
IN_A_RESULT = ("read", "notice")  # How an offer reaches a tool's result, which shows it at once.

DIGEST_ITEMS = 32
RESULT_LIMIT = (
    12 * 1024
)  # The kernel refuses a command's result past 16 KiB; this leaves room for what frames the rows.

LINE_RANGE = r"L([1-9]\d*)-([1-9]\d*)"

_ADDRESS = re.compile(rf"([@#+])({NAME})")
_STREAMS = {"@": "inbox/", "#": "channel/", "+": "channel/+"}


def stream_of(address: str) -> str:
    """The stream an address names: `@agent`, `#channel` or `+group`."""
    match = _ADDRESS.fullmatch(address)
    if match is None:
        raise Refused("invalid", f"an address is @agent, #channel or +group, not {address[:64]!r}")
    return _STREAMS[match[1]] + match[2]


def address(principal: str) -> str:
    """A principal id as an address: `agent:alice` is `@alice`, and the runtime has none."""
    kind, colon, name = principal.partition(":")
    return f"@{name}" if colon else kind


def name_of(principal: str) -> str:
    """A principal id as a row names it: `agent:alice` is `alice`, as a name is unique across kinds."""
    return principal.partition(":")[2]


def checked_after(txn: Txn, after: int | None) -> int | None:
    """`after` as given. Past the head it is no cursor, and reading from it would hide what is unread."""
    if after is not None and after > txn.view(Stamps).head():
        raise Refused("invalid", f"`after` {after} is past every event: leave it out")
    return after


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


class Paging(Args):
    after: Annotated[str | None, Field(description="A `cursor` from an earlier call.")] = None


def paged(rows: Iterable[dict[str, Any]], name: str, key: str, after: str | None) -> dict[str, Any]:
    """One page of a list as long as a team, in order of `key`, with the true `total`. `cursor` goes on from there, and
    is None at the end. A query has no other way past what one tool result holds."""
    ordered = sorted(rows, key=lambda row: row[key])
    rest = [row for row in ordered if after is None or row[key] > after]
    kept = fitted(rest)
    return {name: kept, "total": len(ordered), "cursor": kept[-1][key] if len(kept) < len(rest) else None}


class Lines(NamedTuple):
    """What a result can show of a text body. `text` is None if one line alone will not fit, `total` counts every line,
    `span` is `#L<first>-<last>` unless this is the whole body, and `rest` is the ref of the lines after these."""

    text: str | None
    total: int
    span: str = ""
    rest: str | None = None

    def shown(self) -> dict[str, Any]:
        return {"text": self.text, "lines": self.total, "rest": self.rest}


def lines_of(body: str, text: str, wanted: str | None, room: int) -> Lines:
    """The lines of `wanted` that fit in `room`, from the text of the body whose ref is `body`. A range no line stands
    in is refused with how many there are."""
    lines = text.splitlines(keepends=True)
    match = re.fullmatch(LINE_RANGE, wanted) if wanted else None
    first = int(match[1]) if match else 1
    last = min(int(match[2]) if match else len(lines), len(lines))
    if first > max(last, 1):
        raise Refused("invalid", {"lines": len(lines), "detail": f"no lines {wanted}"})
    if not lines:
        return Lines("", 0)
    size = 0
    kept = first - 1
    for line in lines[first - 1 : last]:
        size += size_of(line)
        if size > room:
            break
        kept += 1
    if kept < first:
        return Lines(None, len(lines))
    whole = first == 1 and kept == len(lines) and match is None
    rest = None if kept == len(lines) else f"{body}#L{kept + 1}-{len(lines)}"
    return Lines("".join(lines[first - 1 : kept]), len(lines), "" if whole else f"#L{first}-{kept}", rest)


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
    asked: bool = False,
) -> int:
    """Record what an agent was offered on `context/<agent>` and return the offer's seq, which names its input.
    `asked` says a message from its parent, never offered to it before, is among what was offered."""
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
            "asked": asked,
        },
        v=2,
    )
    return event.seq


def expose_read(txn: Txn, items: list[Exposed], *, positions: dict[str, int] | None = None, **chain: Any) -> None:
    """An agent's read is evidence and anyone else's is nothing, so only an agent's read writes this."""
    if txn.me.kind == "agent" and (items or positions):
        expose(txn, txn.me.name, items, how="read", boundary="tool", positions=positions, **chain)
