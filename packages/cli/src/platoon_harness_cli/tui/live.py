"""Live: a session as the TUI follows it, through one coalescer between the journal and the widgets."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Literal

from textual.worker import Worker

from platoon_harness import Ending, Refused, Session
from platoon_harness.kernel import Event, is_held

from .transcript import Tail

FRAME = 1 / 15
"""The shortest time between two frames: at most 15 a second."""
PENDING = 1024
"""How many events wait for a frame before the reader waits for one too."""
LOOK = 1.0
"""How often a session that is history is looked at for a runtime that took it up again."""


class Live:
    """A session as the TUI follows it: one reader of its journal, one of the live text of the agent in view, kept in
    `tail`, and what the views say, each frame. Frames come at most 15 a second, and one that would come sooner is
    dropped; an event never is: a reader with too many waiting waits for the next frame, so a slow screen holds up only
    its own reading. It decides nothing: what it shows comes from the views, and `runtime` says only whether a runtime
    holds the session, which is the kernel's own check, or that it is a `replay`, a copy whose record grows as it plays
    and which no runtime holds or says anything of. Its two timers decide nothing either: one paces frames, and one
    looks for a runtime to attach to. Each loop runs as a worker of the screen, so one that fails ends the app loudly,
    rather than leaving a screen that no longer moves."""

    def __init__(
        self,
        session: Session,
        draw: Callable[[list[Event], bool], Awaitable[None]],
        run: Callable[[Coroutine[Any, Any, None]], Worker[None]],
        *,
        replay: bool = False,
    ) -> None:
        self.session = session
        self.roster: list[dict[str, Any]] = []
        self.attention: dict[str, dict[str, Any]] = {}
        self.status: dict[str, Any] = {}
        self.budgets: list[dict[str, Any]] = []
        self.changes: dict[str, dict[str, Any]] = {}
        self.ending: Ending | None = None
        self.channels: list[dict[str, Any]] = []
        self.runtime: Literal["live", "history", "replay"] = "replay" if replay else "live"
        self.tail = Tail()
        self.frames = 0
        self._draw = draw
        self._run = run
        self._read_through = 0
        self._said = False
        self._pending: list[Event] = []
        self._dirty = asyncio.Event()
        self._room = asyncio.Event()
        self._drawn = asyncio.Condition()
        self._cursors: dict[str, int | None] = {"roster": None, "attention": None, "changes": None}
        self._channels_moved = True
        self._workers: list[Worker[None]] = []
        self._tail: Worker[None] | None = None
        self._tail_of: str | None = None

    def start(self, through: int) -> None:
        """Follow from `through`, which the screen has drawn already."""
        self._read_through = through
        if self.runtime != "replay":
            self.runtime = "live" if is_held(self.session.folder) else "history"
        self._workers = [self._run(self._read()), self._run(self._frames())]
        self._dirty.set()

    def stop(self) -> None:
        for worker in [*self._workers, *([self._tail] if self._tail else [])]:
            worker.cancel()

    def follow_tail(self, agent: str | None) -> None:
        """Read the live text of `agent` alone, the one in view, or of nobody. A new reader starts a new `tail`, as it
        is told all that is said now and not yet committed."""
        if agent == self._tail_of and self._tail is not None and not self._tail.is_finished:
            return
        if self._tail is not None:
            self._tail.cancel()
        self._tail_of, self._tail, self.tail = agent, None, Tail()
        if agent is not None and self.runtime == "live":
            self._tail = self._run(self._read_tail(agent, self.tail))

    async def next_frame(self, after: int) -> None:
        """Wait until a frame past the `after`th has been drawn."""
        async with self._drawn:
            await self._drawn.wait_for(lambda: self.frames > after)

    async def _read(self) -> None:
        while True:
            with contextlib.suppress(Refused):
                async for event in self.session.events(self._read_through, follow=True):
                    self._read_through = event.seq
                    self._pending.append(event)
                    self._dirty.set()
                    if len(self._pending) >= PENDING:
                        self._room.clear()
                        await self._room.wait()
            if self.runtime == "replay":
                return
            if not is_held(self.session.folder):
                await self._gone()
            while not is_held(self.session.folder):  # noqa: ASYNC110  Nothing says when a runtime takes it up.
                await asyncio.sleep(LOOK)
            self.runtime = "live"
            self.follow_tail(self._tail_of)

    async def _gone(self) -> None:
        """No runtime holds the session now: what one was saying is said no more, and its state says how it ended."""
        if self._tail is not None:
            self._tail.cancel()
        self.runtime, self._tail, self.tail = "history", None, Tail()
        with contextlib.suppress(Refused):
            self.status = await self.session.status()
        self._dirty.set()

    async def _read_tail(self, agent: str, tail: Tail) -> None:
        with contextlib.suppress(Refused):
            async for delta in self.session.deltas(agent):
                tail.take(delta)
                self._said = True
                self._dirty.set()

    async def _frames(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            events, self._pending = self._pending, []
            said, self._said = self._said, False
            self._room.set()
            self._channels_moved = self._channels_moved or any(event.type == "channel.created" for event in events)
            with contextlib.suppress(Refused):
                await self._look(bool(events) or self.frames == 0)
            await self._draw(events, said)
            async with self._drawn:
                self.frames += 1
                self._drawn.notify_all()
            await asyncio.sleep(FRAME)

    async def _look(self, moved: bool) -> None:
        """Read what the views say now, once a frame, and only when the journal has moved."""
        if not moved:
            return
        session = self.session
        roster = await self._watch("roster")
        if roster["snapshot"] or roster["rows"]:
            self.roster = roster["rows"]
        attention = await self._watch("attention")
        if attention["snapshot"]:
            self.attention = {}
        self.attention |= {row["id"]: row for row in attention["rows"]}
        for gone in attention["removed"]:
            self.attention.pop(gone, None)
        changes = await self._watch("changes")
        if changes["snapshot"]:
            self.changes = {}
        self.changes |= {row["id"]: row for row in changes["rows"]}
        for gone in changes["removed"]:
            self.changes.pop(gone, None)
        self.status = await session.status()
        self.budgets = await session.budgets()
        self.ending = await session.ending()
        if self._channels_moved:
            self._channels_moved = False
            self.channels = await self._listed()

    async def _watch(self, view: str) -> dict[str, Any]:
        outcome = await self.session.submit("view.watch", name=view, after=self._cursors[view])
        if outcome.refusal is not None:
            raise Refused.of(outcome.refusal)
        self._cursors[view] = outcome.result["cursor"]
        return outcome.result

    async def _listed(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        after = None
        while True:
            page = await self.session.channels(after=after)
            found += page["channels"]
            if (after := page.get("cursor")) is None:
                return found
