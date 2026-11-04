"""Who a browser is to `web`: a credential of one of two classes, fixed when it is minted. A view credential reaches
only what the page reads, and can never act or mint, and nothing turns it into a control credential.

A link is minted for one class and opens once: it is spent for a session token of that class, and a link nobody
spent expires after `LINK_SECONDS`. A session token expires after `SESSION_SECONDS`. Each is lowercase hex, long enough
for the page to take, and only its hash is kept, in this process's memory, so stopping `web` revokes every browser.
Time comes from the clock, never from the browser.
"""

import hashlib
import secrets
from typing import Literal, NamedTuple

from platoon_harness.kernel import Clock

Class = Literal["view", "control"]
LINK_SECONDS = 600.0
SESSION_SECONDS = 12 * 3600.0
_BYTES = 32


class Held(NamedTuple):
    """A credential, by the hash of its token: its class, and when it stops opening anything."""

    kind: Class
    expires: float


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Credentials:
    """The links and session tokens this process has minted."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._links: dict[str, Held] = {}
        self._sessions: dict[str, Held] = {}

    def mint(self, kind: Class) -> str:
        """A link of `kind`, which opens once, within `LINK_SECONDS`."""
        self._forget()
        link = secrets.token_hex(_BYTES)
        self._links[_hash(link)] = Held(kind, self._clock.now() + LINK_SECONDS)
        return link

    def exchange(self, link: str) -> tuple[str, Held] | None:
        """Spend a link for a session token of its class, or None for a link that is spent, expired or never was."""
        held = self._links.pop(_hash(link), None)
        if held is None or held.expires <= self._clock.now():
            return None
        token = secrets.token_hex(_BYTES)
        session = Held(held.kind, self._clock.now() + SESSION_SECONDS)
        self._sessions[_hash(token)] = session
        return token, session

    def check(self, token: str) -> Held | None:
        """What a session token holds, or None for one that expired or never was."""
        held = self._sessions.get(_hash(token))
        return held if held is not None and held.expires > self._clock.now() else None

    def _forget(self) -> None:
        """Drop what has expired, so what is held grows only with what is live."""
        now = self._clock.now()
        for held in (self._links, self._sessions):
            for key in [key for key, found in held.items() if found.expires <= now]:
                del held[key]
