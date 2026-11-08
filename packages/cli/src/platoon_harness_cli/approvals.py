"""An approval's ask, which the terminal and the browser say alike: the whole of what its harness asks to do, read by
the ref of its request's body, and below it where it was cut, or why there is nothing more to read."""

from dataclasses import dataclass

from platoon_harness import Refused, Session
from platoon_harness.kernel import Event
from platoon_harness.primitives.approvals import ASK_LIMIT

UNKNOWN = "What it asks beyond its gist is unknown: the record holds no more of it."
"""What stands below an ask the record holds no body of: one its driver could not say, or one recorded before a request
carried it. Its harness may have said more."""


@dataclass(frozen=True)
class Ask:
    """What an approval asks, as a person reads it before answering it: the `agent` asking, its `gist`, `text`, the
    whole of it as its harness gave it, or None where there is none to read, and the words `below` it, where it was
    cut, or why there is no text."""

    agent: str
    gist: str
    text: str | None
    below: str | None


async def request(session: Session, id: str, seq: int) -> Event:
    """The request of the approval `id`, the first event of its stream, which the journal holds at `seq`."""
    page = await session.page(after=seq - 1, before=seq + 1, streams=[f"approval/{id}"])
    found = next((event for event in page.events if event.type == "approval.requested"), None)
    if found is None:
        raise Refused("not_found", f"no request of approval {id} at seq {seq}")
    return found


async def read(session: Session, request: Event) -> Ask:
    """What an approval's `request` asks: its body, read whole by its ref, as `blob.get` gives no text for a line longer
    than one result holds, which a one-line ask can be. A request of payload version 1 names no body and no cut, and
    what it asks beyond its gist is unknown, as for any request with no body."""
    agent, gist = request.agent or "", request.gist
    ref, cut = request.data.get("body"), request.data.get("cut")
    if ref is None:
        return Ask(agent, gist, None, UNKNOWN)
    try:
        text = (await session.get_body(ref, limit=ASK_LIMIT)).decode(errors="replace")
    except Refused as refused:
        return Ask(agent, gist, None, f"What it asks cannot be read: {refused}")
    below = f"Cut here: it asks {cut:,} bytes more, which the record does not keep, and Allow allows them too."
    return Ask(agent, gist, text, below if cut else None)
