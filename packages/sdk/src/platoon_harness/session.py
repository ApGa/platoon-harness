"""The Session: one durable thing you start, attach to and resume, through one link, in-process or over a socket.

    async with Session.start(team, name="fix-auth") as session:
        await session.send("@lead", "Fix the flaky test")
        ending = await session.settled(timeout="30m")
    print(ending.agents[0]["report"]["gist"])

The owner's leaving stops the agents and keeps the folder. A guest's leaving only disconnects. `submit` returns the
kernel's `Outcome` and never raises a refusal; every typed method returns the result and raises `Refused`. A commit that
fails ends an owner's runtime, as a kill would, and from then on every call raises `JournalError`: `Session.resume` goes
on from what the journal holds.
"""

import asyncio
import contextlib
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Generator, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter, ValidationError

from platoon_harness.annotations import ANNOTATIONS, Annotate, Annotation, Status
from platoon_harness.config import Manifest
from platoon_harness.kernel import Clock, Delta, Event, Kernel, Outcome, Page, Principal, Refused, first, is_held
from platoon_harness.primitives import (
    BODY_REF,
    PRIMITIVES,
    Condition,
    Contributors,
    Eligibility,
    Exposure,
    Lineage,
    NotSeen,
    Policy,
    Seen,
    Unknown,
    Uses,
    Verdict,
)
from platoon_harness.rpc import Closed
from platoon_harness.runtime import GRACE, Authority, Runtime
from platoon_harness.runtime.control import History, Link, Local, Remote
from platoon_harness.runtime.opening import prepare
from platoon_harness.runtime.paths import LOG, MANIFEST, MARKS, find_root, open_log, read_running, session_folder
from platoon_harness.schema import seconds
from platoon_harness.team import Team

_ATTACH_SECONDS = 60.0
_START_SECONDS = 60.0
_FIRST_PAUSE = 0.005
_LONGEST_PAUSE = 0.5
_ATTEMPTS = 8
_LOG_TAIL = 2048
_CLIENT_SECONDS = 1.0
_WAITED_OUT = ("not_permitted", "unavailable")
_STREAM_LENGTH = 512
_MARKS_TABLE = """
CREATE TABLE IF NOT EXISTS marks(
    person TEXT NOT NULL, stream TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (person, stream)
) WITHOUT ROWID, STRICT
"""
_ANNOTATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS annotations(
    id INTEGER PRIMARY KEY,
    target TEXT NOT NULL,
    kind TEXT NOT NULL,
    producer TEXT NOT NULL,
    producer_version TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    scope TEXT NOT NULL,
    status TEXT NOT NULL,
    value REAL,
    evidence TEXT NOT NULL,
    head_seq INTEGER NOT NULL,
    wall_time REAL NOT NULL,
    UNIQUE (producer, producer_version, params_hash, target, kind)
) STRICT
"""
_ANNOTATIONS_INDEX = "CREATE INDEX IF NOT EXISTS annotations_target ON annotations(target, id)"

Reason = Literal["settled", "agent_failed", "budget_exhausted", "timed_out", "needs_human", "cancelled"]
Span = str | float
_EXPOSURE: TypeAdapter[Seen | NotSeen | Unknown] = TypeAdapter(Exposure)

__all__ = ["Ending", "Reason", "Session"]


class Ending(BaseModel, frozen=True):
    """What a session came to. `reason` is what an exit code is made from. Each of `agents` has its last `report`, a
    `gist` and the ref of any `body`, or None if it said nothing. `usage` keeps its labels: a unit nobody measured has
    no amount, which is not zero. Each of `workspaces` is one an agent's end did not take, with where it is, what it
    takes on disk, why it stayed and, where some lose nothing it stayed for, the commands that let it go. `unobserved`
    names the agents whose last look never finished, so what they last changed was not recorded."""

    state: str
    reason: Reason
    agents: tuple[dict[str, Any], ...]
    usage: dict[str, dict[str, Any]]
    gaps: tuple[dict[str, Any], ...]
    workspaces: tuple[dict[str, Any], ...] = ()
    unobserved: tuple[str, ...] = ()


def _result(outcome: Outcome) -> Any:
    if outcome.refusal is not None:
        raise Refused.of(outcome.refusal)
    return outcome.result


def _optional_seconds(span: Span | None) -> float | None:
    return None if span is None else seconds(span)


async def _pauses(total: float) -> AsyncIterator[None]:
    """Yield, then sleep a little longer each time, until `total` seconds have gone."""
    deadline = time.monotonic() + total
    pause = _FIRST_PAUSE
    while time.monotonic() < deadline:
        yield
        await asyncio.sleep(pause)
        pause = min(pause * 2, _LONGEST_PAUSE)


def _spawn_runtime(folder: Path) -> subprocess.Popen[bytes]:
    """A runtime that outlives us. It runs from its folder with `-P`, so that nothing in our working directory can stand
    in for a module it imports. A thread reaps it, whenever it ends."""
    folder = folder.resolve()
    command = [sys.executable, "-P", "-m", "platoon_harness.runtime", str(folder)]
    log = open_log(folder)
    process = subprocess.Popen(
        command, cwd=folder, start_new_session=True, stdin=subprocess.DEVNULL, stdout=log, stderr=log
    )
    os.close(log)
    threading.Thread(target=process.wait, daemon=True).start()
    return process


async def _start_detached(folder: Path) -> None:
    """Start a runtime of its own, and wait until it says it is up."""
    process = await asyncio.to_thread(_spawn_runtime, folder)
    async for _ in _pauses(_START_SECONDS):
        running = read_running(folder)
        if running is not None and running.pid == process.pid:
            return
        if process.poll() is not None:
            break
    tail = (folder / LOG).read_text(errors="replace")[-_LOG_TAIL:]
    raise Refused("unavailable", f"the runtime for {folder.name} did not start: {tail}")


class Session:
    """A session, as its owner or as a guest. `Session.start`, `Session.attach` and `Session.resume` give one, to
    `await` or to use in `async with`. The class holds one link, so everything below is written once."""

    def __init__(self, enter: Callable[["Session"], Awaitable[None]]) -> None:
        self._enter: Callable[[Session], Awaitable[None]] | None = enter
        self._link: Link | None = None
        self._runtime: Runtime | None = None
        self._view = False
        self._attaching = asyncio.Lock()
        self.folder = Path()

    @classmethod
    def start(
        cls,
        team: Team,
        *,
        name: str | None = None,
        principal: str = "human:you",
        approvals: Policy | None = None,
        authority: Authority | None = None,
        detach: bool = False,
        cwd: str | Path | None = None,
        root: str | Path | None = None,
        clock: Clock | None = None,
        plan_login: bool = False,
        trainable: bool = False,
    ) -> Self:
        """Start a team. You own it, unless `detach` starts a runtime of its own and gives you a guest.

        `principal` is who you are in the journal, a name and not a claim, as identity comes from the credential: a
        person, `human:<name>`, or a program, `program:<name>`. A program's session issues no owner credential, as
        whoever held it would act as that program, so a guest of it holds a view credential, and it cannot detach.
        `approvals` states a policy over every role's own, which is durable, so it is said here and not when you wait.
        `plan_login` says several agents may run headless on one plan login, which is refused otherwise. `trainable`
        checks the team as a training system starts it, which an `authority` admits through its gateway, before any
        harness launches.
        """
        _refuse_across_processes(detach, authority, clock)
        if trainable and authority is None:
            raise Refused("invalid", "a trainable session's agents reach their model through an authority's gateway")
        _refuse_a_program_detached(detach, principal)

        async def enter(self: Session) -> None:
            options: dict[str, Any] = {"name": name, "root": root, "principal": principal, "approvals": approvals}
            options |= {"cwd": cwd, "plan_login": plan_login, "trainable": trainable}
            preparing = asyncio.ensure_future(asyncio.to_thread(prepare, team, **options))
            try:
                folder = await asyncio.shield(preparing)
            except asyncio.CancelledError:  # A thread runs on, so what it makes is taken back once it has.
                with contextlib.suppress(Exception):
                    _unclaim(await preparing)
                raise
            await self._take_up(folder, detach, authority, clock)

        return cls(enter)

    @classmethod
    def resume(
        cls, name: str, *, detach: bool = False, root: str | Path | None = None, clock: Clock | None = None
    ) -> Self:
        """Restart a session whose runtime has gone. This is its own verb because restarting can spend money. Harnesses
        come back on fresh credentials, which the session issues, or their agents are lost, with a gap. A session
        started trainable, or whose agents an authority admitted with the backend's ids, is refused: their keys went
        with it. A program's session cannot detach, as at its start."""
        _refuse_across_processes(detach, None, clock)

        async def enter(self: Session) -> None:
            folder = session_folder(find_root(root, writing=True), name)
            with contextlib.suppress(ValidationError):  # A manifest that does not read is the runtime's to report.
                _refuse_a_program_detached(detach, _principal_of(folder))
            await self._take_up(folder, detach, None, clock)

        return cls(enter)

    @classmethod
    def attach(cls, name: str, *, view: bool = False, root: str | Path | None = None) -> Self:
        """Join a session as a guest. It has no side effects: with no live runtime it gives read-only history, and a
        write is refused `unavailable`, naming the command that restarts it. `view` holds a view credential, which reads
        and never writes."""

        async def enter(self: Session) -> None:
            await self._join(session_folder(find_root(root), name), view=view)

        return cls(enter)

    def __await__(self) -> Generator[Any, None, Self]:
        return self._entered().__await__()

    async def _entered(self) -> Self:
        """Enter, once: restarting something left is what `resume` is for, as it can spend money."""
        enter, self._enter = self._enter, None
        if enter is not None:
            await enter(self)
        return self

    async def __aenter__(self) -> Self:
        return await self._entered()

    async def __aexit__(self, *_: object) -> None:
        await self.leave()

    async def _join(self, folder: Path, *, view: bool = False) -> None:
        self.folder, self._view = folder, view
        self._link = await self._attached()

    async def _take_up(self, folder: Path, detach: bool, authority: Authority | None, clock: Clock | None) -> None:
        if detach:
            await _start_detached(folder)
            await self._join(folder)
        else:
            self.folder = folder
            runtime = Runtime(folder, authority=authority, clock=clock)
            await runtime.start()
            self._runtime = runtime
            self._link = Local(runtime.kernel, runtime.principal, others=runtime.control.clients)

    def _history(self) -> History:
        folder = self.folder
        if not (folder / "journal.sqlite").exists():
            raise Refused("unavailable", f"session {self.name} never opened: {_resume_command(folder)} opens it")
        kernel = Kernel.open(folder, read_only=True, extensions=PRIMITIVES)
        return History(kernel, Principal(id=_principal_of(folder)), _resume_command(folder))

    async def _attached(self) -> Link:
        """What attaching gives now. A lock held with nothing answering is a runtime on its way up or down. A runtime of
        a program's session issued no owner credential, so its guests hold a view credential."""
        async for _ in _pauses(_ATTACH_SECONDS):
            if not is_held(self.folder):
                return self._history()
            self._view = self._view or _principal_of(self.folder).startswith("program:")
            try:
                return await Remote.connect(self.folder, view=self._view)
            except Closed:
                pass
            except Refused as refused:
                if refused.refusal.code not in _WAITED_OUT:  # A runtime on its way has last time's credential.
                    raise
        raise Refused("unavailable", f"a runtime holds session {self.name} and does not answer")

    async def _reattach(self, stale: Link) -> Link:
        """Replace a link that went. Several calls can find that out at once, and only the first does the work."""
        async with self._attaching:
            if self._link is stale:
                await stale.close()
                self._link = await self._attached()
            return self._current()

    def _failed(self) -> None:
        """An owner whose runtime a failed commit ended has nothing worth asking, and says why."""
        if self._runtime is not None and (failure := self._runtime.kernel.failure) is not None:
            raise failure

    def _current(self) -> Link:
        self._failed()
        if self._link is None:
            detail = "not started: `await` it or use `async with`" if self._enter else "this session was left"
            raise Refused("unavailable", detail)
        return self._link

    async def _over_link[T](self, call: Callable[[Link], Awaitable[T]]) -> T:
        """Run one call on the link. A runtime that went gives way to what attaching gives now, and the call goes again,
        so a command keeps its key and stays one operation. A guest on history looks for a runtime each time. A failed
        commit is said however the call ended: one under way when another's commit failed is refused by the writer."""
        link = self._current()
        if isinstance(link, History) and (is_held(self.folder) or link.stale()):
            link = await self._reattach(link)
        for _ in range(_ATTEMPTS):
            try:
                answered = await call(link)
            except Closed:
                link = await self._reattach(link)
            except Refused:
                self._failed()
                raise
            else:
                self._failed()
                return answered
        raise Refused("unavailable", f"the runtime of session {self.name} keeps going away")

    @property
    def name(self) -> str:
        return self.folder.name

    @property
    def owner(self) -> bool:
        """Whether leaving stops the agents."""
        return self._runtime is not None

    async def leave(self, grace: Span = GRACE) -> None:
        """Go. An owner interrupts turns, waits `grace` and ends the process trees, keeping the folder resumable. A
        guest only disconnects, and changes nothing."""
        grace = seconds(grace)
        link, self._link = self._link, None
        if self._runtime is not None:
            await self._runtime.stop(grace)
            self._runtime = None
        elif link is not None:
            await link.close()

    # The one way in.

    async def submit(self, op: str, /, *, key: str | None = None, **args: Any) -> Outcome:
        """Run an op by name and return the kernel's `Outcome`, refusal and all. A retry under one `key` is one
        operation, and the link retries under this one on its own when a runtime goes."""
        chosen = key or uuid4().hex
        try:
            return await self._over_link(lambda link: link.submit(op, args, key=chosen))
        except Refused as refused:  # No link would take it, which is a refusal like any other.
            return Outcome(op=op, key=chosen, args_hash="", refusal=refused.refusal)

    async def _do(self, op: str, **args: Any) -> Any:
        return _result(await self.submit(op, **args))

    async def _ask(self, op: str, **args: Any) -> Any:
        return _result(await self._over_link(lambda link: link.query(op, args)))

    async def _stored(self, body: str | bytes | None) -> str | None:
        """A body as a ref: stored first if it is content, and as it stands if it is a ref already."""
        if body is None or (isinstance(body, str) and re.fullmatch(BODY_REF, body)):
            return body
        return await self.put_body(body.encode() if isinstance(body, str) else body)

    async def _changed(self, after: int) -> int | None:
        return await self._over_link(lambda link: link.changed(after))

    async def _moves(self) -> AsyncIterator[int]:
        """Yield the head now, and again each time the journal moves, until nothing more can come."""
        head: int | None = 0
        while (head := await self._changed(head)) is not None:
            yield head

    # Lifecycle.

    async def spawn(
        self,
        name: str,
        role: str,
        goal: str = "",
        *,
        body: str | bytes | None = None,
        stays: bool | None = None,
        based_on: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Start an agent in a role, and give its `ref`. With no `goal` and no `body` it starts idle until a message
        wakes it. `stays` says whether it is told to stay after its task for the next message, rather than to finish:
        left out, its role decides, else it does not."""
        stored = await self._stored(body)
        return await self._do(
            "agent.spawn", name=name, child_role=role, goal=goal, body=stored, stays=stays, based_on=based_on
        )

    async def status(self, agent: str | None = None) -> dict[str, Any]:
        """How this session stands, or one agent."""
        return await (self._ask("session.status") if agent is None else self._ask("agent.status", agent=agent))

    async def agents(self) -> list[dict[str, Any]]:
        return await self._ask("agent.list")

    async def unread(self, agent: str) -> dict[str, Any]:
        """What waits for an agent's next handover, oldest first, which the roster's `unread` counts: each entry with
        the `delivery` it would land by now, and the true `total`."""
        return await self._ask("agent.unread", agent=agent)

    async def interrupt(self, agent: str, *, below: bool = False) -> dict[str, Any]:
        """Stop an agent's turn, and with `below` the turns of every agent below it, and say whose. It stops turns, not
        waits, and every agent lives on."""
        return await self._do("agent.interrupt", agent=agent, below=below)

    async def cancel_agent(self, agent: str) -> None:
        """End one agent now."""
        await self._do("agent.cancel", agent=agent)

    async def retire(self, agent: str) -> None:
        """Take an agent that has stopped working out of the team. Its history stays."""
        await self._do("agent.retire", agent=agent)

    async def takeover(self, agent: str) -> None:
        """Hold an agent's deliveries."""
        await self._do("agent.takeover", agent=agent)

    async def release(self, agent: str) -> None:
        """Hand a held agent back, which records the gap."""
        await self._do("agent.release", agent=agent)

    async def close(self) -> None:
        """Drain: nothing new starts, and what is in flight finishes."""
        await self._do("session.close")

    async def cancel(self) -> None:
        """Stop now: every live agent ends."""
        await self._do("session.cancel")

    async def open_episode(self, episode: str) -> None:
        await self._do("episode.open", episode=episode)

    async def close_episode(self, *, based_on: Sequence[str] = ()) -> None:
        """Close the open episode on the refs of what it came to. What it is worth is an annotation's to say."""
        await self._do("episode.close", based_on=based_on)

    # Waiting.

    async def wait(
        self,
        *,
        on: Sequence[Condition] = (),
        agents: Sequence[str] = (),
        senders: Sequence[str] = (),
        tasks: Sequence[str] = (),
        board: Sequence[str] = (),
        channels: Sequence[str] = (),
        queue: Sequence[str] = (),
        mode: Literal["all", "any"] = "all",
        after: int | None = None,
        timeout: Span | None = None,  # noqa: ASYNC109  The service keeps this, not this call.
    ) -> dict[str, Any]:
        """Wait until the condition holds or `timeout` passes, and say how it closed. The wait lives in the service, so
        losing this client loses nothing."""
        placed = await self._do(
            "wait",
            on=[condition.model_dump(mode="json") for condition in on],
            agents=agents,
            tasks=tasks,
            board=board,
            channels=channels,
            queue=queue,
            mode=mode,
            after=after,
            timeout=_optional_seconds(timeout),
            **{"from": senders},
        )
        async for _ in self._moves():
            shown = await self._ask("wait.progress", id=placed["id"])
            if shown["state"] != "open":
                return shown
        raise Refused("unavailable", f"the runtime of session {self.name} went before the wait closed")

    async def cancel_wait(self, id: int | None = None) -> None:
        await self._do("wait.cancel", id=id)

    async def wait_progress(self, id: int | None = None) -> dict[str, Any] | None:
        return await self._ask("wait.progress", id=id)

    async def ending(self) -> Ending:
        """What this session has come to so far."""
        return Ending.model_validate(await self._ask("session.ending"))

    async def _alone(self) -> None:
        """Return once nobody else could act. A client can go without moving the journal, so this has to look."""
        while await self._over_link(lambda link: link.others()):
            await self._current().clock.sleep(_CLIENT_SECONDS)

    async def _settling(self) -> Reason | None:
        """Close at `until`, and return once the session has drained. What only a person could move ends this with
        `needs_human`, once nobody else could be that person."""
        async for head in self._moves():
            status = await self.status()
            if status["state"] != "open" and status["settled"]:
                return None
            if status["asking"] or status["stalled"]:
                if await first(self._alone(), self._changed(head)):
                    return "needs_human"
            elif status["state"] == "open" and status["done"]:
                with contextlib.suppress(Refused):  # A message got in first, or a guest closed it.
                    await self._do("session.close", if_done=True)
        raise Refused("unavailable", f"the runtime of session {self.name} went before it settled")

    async def settled(self, timeout: Span | None = None) -> Ending:  # noqa: ASYNC109  It is part of what this reports.
        """Wait for `session.status` to say done, close at `until`, and say what the session came to. Past `timeout` it
        says `timed_out`, and with something only a person can move it says `needs_human`. Both leave it as it is."""
        clock = self._current().clock
        settling = asyncio.ensure_future(self._settling())
        rivals = () if timeout is None else (clock.sleep(seconds(timeout)),)
        reason = settling.result() if await first(settling, *rivals) else "timed_out"
        ending = await self.ending()
        return ending if reason is None else ending.model_copy(update={"reason": reason})

    # Messages.

    async def send(
        self,
        to: str,
        gist: str,
        *,
        body: str | bytes | None = None,
        thread: str | None = None,
        reply_to: str | None = None,
        based_on: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Send to `@agent`, `#channel` or `+group`. `gist` is what readers see first, and `body` anything longer."""
        stored = await self._stored(body)
        return await self._do(
            "message.send", to=to, gist=gist, body=stored, thread=thread, reply_to=reply_to, based_on=based_on
        )

    async def reply(self, entry: Mapping[str, Any], gist: str, *, body: str | bytes | None = None) -> dict[str, Any]:
        """Answer an entry from `read`."""
        return await self.send(entry["sender"], gist, body=body, reply_to=entry["ref"])

    async def read(
        self,
        channel: str | None = None,
        *,
        after: int | None = None,
        limit: int = 32,
        sender: str | None = None,
        thread: str | None = None,
        bodies: bool = False,
    ) -> dict[str, Any]:
        """Read your inbox, `#channel` or `+group`. A human's read writes nothing and moves no cursor."""
        return await self._ask(
            "message.read", channel=channel, after=after, limit=limit, sender=sender, thread=thread, bodies=bodies
        )

    async def channels(self, *, after: str | None = None) -> dict[str, Any]:
        return await self._ask("channel.list", after=after)

    async def peers(self, *, after: str | None = None) -> dict[str, Any]:
        return await self._ask("peers", after=after)

    async def create_channel(
        self,
        name: str,
        kind: Literal["topic", "queue", "board"],
        *,
        readers: Sequence[str] = (),
        writers: Sequence[str] = (),
        delivery: str | None = None,
    ) -> dict[str, Any]:
        return await self._do(
            "channel.create", name=name, kind=kind, readers=readers, writers=writers, delivery=delivery
        )

    # Boards.

    async def board_post(
        self,
        board: str,
        name: str,
        gist: str,
        *,
        body: str | bytes | None = None,
        fields: Mapping[str, Any] | None = None,
        based_on: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Create an object on a board, at version 1."""
        stored = await self._stored(body)
        args = {"board": board, "name": name, "gist": gist, "body": stored, "fields": fields or {}}
        return await self._do("board.post", **args, based_on=based_on)

    async def board_revise(
        self,
        board: str,
        name: str,
        gist: str,
        expected_version: int,
        *,
        body: str | bytes | None = None,
        fields: Mapping[str, Any] | None = None,
        based_on: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Add a version, if `expected_version` is still the latest. Nothing is ever overwritten."""
        stored = await self._stored(body)
        args = {"board": board, "name": name, "gist": gist, "body": stored, "fields": fields or {}}
        return await self._do("board.revise", **args, expected_version=expected_version, based_on=based_on)

    async def board_get(
        self, board: str, name: str, *, version: int | None = None, range: str | None = None
    ) -> dict[str, Any]:
        return await self._ask("board.get", board=board, name=name, version=version, range=range)

    async def board_query(
        self,
        board: str,
        *,
        prefix: str | None = None,
        author: str | None = None,
        where: Mapping[str, Any] | None = None,
        text: str | None = None,
        history: bool = False,
        after: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Find objects on a board. Results carry exact refs and the true total."""
        filters = {"prefix": prefix, "author": author, "where": where or {}, "text": text, "history": history}
        return await self._ask("board.query", board=board, **filters, after=after, limit=limit)

    # Queues.

    async def task_add(
        self, queue: str, gist: str, *, body: str | bytes | None = None, based_on: Sequence[str] = ()
    ) -> dict[str, Any]:
        """Add a task to a queue."""
        return await self._do("task.add", queue=queue, gist=gist, body=await self._stored(body), based_on=based_on)

    async def task_claim(self, queue: str, *, task: str | None = None) -> dict[str, Any]:
        return await self._do("task.claim", queue=queue, task=task)

    async def task_renew(self, queue: str, *, task: str | None = None, fence: int | None = None) -> dict[str, Any]:
        return await self._do("task.renew", queue=queue, task=task, fence=fence)

    async def task_release(self, queue: str, *, task: str | None = None, fence: int | None = None) -> None:
        """Give a task back, which spends no attempt."""
        await self._do("task.release", queue=queue, task=task, fence=fence)

    async def task_complete(
        self,
        queue: str,
        *,
        task: str | None = None,
        fence: int | None = None,
        gist: str = "",
        body: str | bytes | None = None,
        based_on: Sequence[str] = (),
    ) -> None:
        stored = await self._stored(body)
        await self._do("task.complete", queue=queue, task=task, fence=fence, gist=gist, body=stored, based_on=based_on)

    async def task_fail(
        self,
        queue: str,
        *,
        task: str | None = None,
        fence: int | None = None,
        gist: str = "",
        body: str | bytes | None = None,
        based_on: Sequence[str] = (),
    ) -> None:
        stored = await self._stored(body)
        await self._do("task.fail", queue=queue, task=task, fence=fence, gist=gist, body=stored, based_on=based_on)

    async def task_list(
        self, queue: str, *, state: str | None = None, after: int = 0, limit: int = 32
    ) -> dict[str, Any]:
        return await self._ask("task.list", queue=queue, state=state, after=after, limit=limit)

    # Humans.

    async def attention(self) -> list[dict[str, Any]]:
        """Where a human must act now, each with the actions that would settle it."""
        return await self._ask("attention.list")

    async def approvals(self) -> list[dict[str, Any]]:
        """What waits on a decision. `id` and `version` are what `resolve` takes."""
        rows = await self.attention()
        return [{**row, "id": row["id"].removeprefix("approval/")} for row in rows if row["kind"] == "approval"]

    async def resolve(
        self, id: str, verdict: Verdict, *, expected_version: int, via: str | None = None
    ) -> dict[str, Any]:
        """Decide an approval. The first commit wins, and the loser is refused `conflict`, told who won."""
        return await self._do("approval.resolve", id=id, verdict=verdict, expected_version=expected_version, via=via)

    async def settle_effect(self, id: int, happened: bool) -> None:
        """Say whether an uncertain effect happened, which is what an `uncertain` row of `attention` asks."""
        await self._do("effect.settle", id=id, happened=happened)

    async def budgets(self) -> list[dict[str, Any]]:
        return await self._ask("budget.status")

    async def set_budget(
        self,
        scope: str = "shared",
        *,
        limits: Mapping[str, float] | None = None,
        estimate: Mapping[str, float] | None = None,
    ) -> None:
        """Set a scope's limits and what a turn is estimated at, which a `tokens` or `usd` limit needs."""
        await self._do("budget.set", scope=scope, limits=limits or {}, estimate=estimate or {})

    async def manifest(self) -> dict[str, Any]:
        return await self._ask("session.manifest")

    async def ops(self) -> list[dict[str, Any]]:
        return await self._ask("ops.list")

    # Reading.

    async def events(
        self,
        after: int = 0,
        match: str | None = None,
        *,
        streams: Sequence[str] | None = None,
        follow: bool = False,
    ) -> AsyncIterator[Event]:
        """Each event past `after` whose stream `match` globs, or `streams` names. Resume from any event's `seq`. With
        `follow` this goes on as the journal grows, until nothing more can come. It is a read plus a long-poll,
        in-process or not."""
        async for _ in self._moves():
            while True:
                page = await self.page(after=after, match=match, streams=streams)
                for event in page.events:
                    yield event
                after = page.cursor
                if after >= page.head:
                    break
            if not follow:
                return

    async def page(
        self,
        *,
        after: int = 0,
        before: int | None = None,
        match: str | None = None,
        streams: Sequence[str] | None = None,
        limit: int = 256,
    ) -> Page:
        """A page of events past `after`, or with `before` the newest below it, in order, so a transcript pages back
        without reading the journal whole. A filtered page scans at most 4,096 events, so it can be empty with more to
        come: pass `cursor` as the next `after`, or as the next `before`, which is `after` once nothing is left."""
        return await self._over_link(
            lambda link: link.read(after, before=before, match=match, streams=streams, limit=limit)
        )

    async def head(self) -> int:
        """The `seq` of the newest event now, after which a follower of only what comes next starts."""
        return await self._changed(-1) or 0

    async def deltas(self, agent: str) -> AsyncIterator[Delta]:
        """An agent's live text as it comes. It is lossy: `lag` counts what was lost, and the item that follows is the
        truth."""
        agent = agent.removeprefix("@")
        frame = await self._frame(agent, None)
        while frame is not None:
            yield frame
            frame = await self._frame(agent, frame.frame)

    async def _frame(self, agent: str, after: int | None) -> Delta | None:
        return await self._over_link(lambda link: link.delta(agent, after))

    async def watch(self, view: Literal["roster", "attention", "changes"]) -> AsyncIterator[dict[str, Any]]:
        """A snapshot of a view, then its keyed changes, until nothing more can come."""
        after = None
        async for _ in self._moves():
            state = await self._ask("view.watch", name=view, after=after)
            after = state["cursor"]
            if state["snapshot"] or state["rows"] or state["removed"]:
                yield state

    async def marks(self) -> dict[str, int]:
        """How far you have read each stream, as you marked it, by stream: where a badge counts from. A mark is neither
        evidence nor a view, and an agent's cursor is no mark, so losing `marks.sqlite` loses only these."""
        return await asyncio.to_thread(_marks_of, self.folder, self._current().principal)

    async def mark(self, stream: str, seq: int) -> None:
        """Mark that you have read `stream` through `seq`. A mark only moves forward. It writes no event and
        acknowledges nothing an agent was handed, with a runtime or without one, and a view credential moves none."""
        principal = self._current().principal
        if self._view:
            raise Refused("not_permitted", "a view credential reads and never writes, a mark among it")
        await asyncio.to_thread(_mark, self.folder, principal, stream, seq)

    async def put_body(self, body: bytes) -> str:
        """Store a body and return its ref, which `body=` takes. An orphan is harmless."""
        return f"sha256:{await self._over_link(lambda link: link.put_body(body))}"

    async def get_body(self, ref: str, *, limit: int | None = None) -> bytes:
        """A stored body's bytes, by a `body` from any result."""
        return await self._over_link(lambda link: link.get_body(ref.removeprefix("sha256:"), limit))

    async def blob(self, ref: str) -> dict[str, Any]:
        """The text of the body an event carries, by the event's ref or a `rest` from any result."""
        return await self._ask("blob.get", ref=ref)

    async def tombstone(self, ref: str) -> None:
        """Redact a body: reads stop now, and its bytes follow. Events citing its hash stay whole."""
        await self._do("body.tombstone", sha256=ref.removeprefix("sha256:"))

    # Provenance.

    async def exposure(self, agent: str, ref: str, *, before: str | None = None) -> Seen | NotSeen | Unknown:
        """Whether the event `ref` reached `agent` through us before the event `before`, or by now: `Seen`, `NotSeen` or
        `Unknown`, each with why, and never a boolean."""
        return _EXPOSURE.validate_python(await self._ask("exposure", agent=agent, ref=ref, before=before))

    async def lineage(self, ref: str, *, after: str | None = None) -> Lineage:
        """One hop back from an event: who made it, what it cites with its citer's exposure, what it followed from, its
        ancestry, and a page of what its maker was offered and the gaps in its record. Pass `cursor` as `after`."""
        return Lineage.model_validate(await self._ask("lineage", ref=ref, after=after))

    async def uses(self, ref: str, *, after: str | None = None) -> Uses:
        """One hop forward from an event: what cites it, what follows from it, its next version or the commits it is a
        parent of, and each agent it was offered to. Pass `cursor` as `after`."""
        return Uses.model_validate(await self._ask("uses", ref=ref, after=after))

    async def contributors(self, ref: str, *, after: str | None = None) -> Contributors:
        """Each maker a walk back from an outcome reaches, and apart from them each maker whose work was only handed to
        one of them: reachability in the record, never credit. Pass `cursor` as `after`."""
        return Contributors.model_validate(await self._ask("contributors", ref=ref, after=after))

    async def eligibility(self, agent: str, episode: str, *, after: str | None = None) -> Eligibility:
        """Whether an agent's work in one episode can train, from the record alone: its attribution, `exact`, `forked`
        or None, and its verdict with every bar, and the same for a page of its model calls. It reads the levels its
        starts recorded, never a result kept since. Pass `cursor` as `after` for the next page."""
        return Eligibility.model_validate(await self._ask("eligibility", agent=agent, episode=episode, after=after))

    async def annotate(
        self,
        target: str,
        *,
        kind: Literal["reward", "credit"],
        producer: str,
        producer_version: str,
        scope: Literal["local", "team"],
        status: Status,
        head_seq: int,
        value: float | None = None,
        params: Mapping[str, Any] | None = None,
        evidence: Sequence[str] = (),
    ) -> Annotation:
        """Say what an estimator found of an event, a `reward` or a `credit`, in `annotations.sqlite` beside the journal
        and never in it, on a live session or a closed one, with no runtime. It is `producer`'s at `producer_version`,
        run with `params`, of the trace up to `head_seq`, at or below which the target and each ref of `evidence` lie:
        an estimate, never a fact. `status` is `scored`, `invalid`, `error`, `timeout` or `cancelled`, and `value` is
        given when it is `scored` alone, so no other is ever zero; with no statement a target is unscored. The same
        statement again is answered with the first, and another under the same producer, version, params, target and
        kind is refused `conflict`."""
        if self._view:
            raise Refused("not_permitted", "a view credential reads and never writes, an annotation among it")
        given: dict[str, Any] = {"target": target, "kind": kind, "producer": producer, "scope": scope}
        given |= {"producer_version": producer_version, "params": dict(params or {}), "status": status, "value": value}
        try:
            statement = Annotate.model_validate({**given, "evidence": tuple(evidence), "head_seq": head_seq})
        except ValidationError as error:
            faults = (f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors(include_url=False))
            raise Refused("invalid", "; ".join(faults)) from None
        if head_seq > (head := await self.head()):
            raise Refused("invalid", f"head_seq {head_seq} is past the head, {head}")
        for ref in dict.fromkeys((statement.target, *statement.evidence)):
            if (seq := (await self.lineage(ref)).event.seq) > head_seq:
                raise Refused("invalid", f"{ref} is at {seq}, past head_seq {head_seq}, so it is no part of that trace")
        return await asyncio.to_thread(_annotate, self.folder, statement, self._current().clock.now())

    async def annotations(self, target: str | None = None) -> list[Annotation]:
        """What estimators said of one event, or of every one, oldest first, each with its producer and version and
        never summed. Nothing an agent can reach reads these."""
        return await asyncio.to_thread(_annotations_of, self.folder, target)


def _marks_of(folder: Path, person: str) -> dict[str, int]:
    """A person's marks. Reading writes nothing, so a folder nobody marked stays as it was, and a file that holds no
    marks yet has none."""
    if not (folder / MARKS).exists():
        return {}
    try:
        with contextlib.closing(sqlite3.connect(f"{(folder / MARKS).as_uri()}?mode=ro", uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name = 'marks'").fetchone() is None:
                return {}
            return dict(db.execute("SELECT stream, seq FROM marks WHERE person = ?", (person,)).fetchall())
    except sqlite3.Error as error:
        raise Refused("unavailable", f"marks cannot be read: {error}") from None


def _mark(folder: Path, person: str, stream: str, seq: int) -> None:
    if not (stream.isprintable() and 0 < len(stream) <= _STREAM_LENGTH) or isinstance(seq, bool) or seq < 0:
        raise Refused("invalid", f"a mark is a stream name of at most {_STREAM_LENGTH} characters and a seq")
    try:
        with contextlib.closing(sqlite3.connect(folder / MARKS, timeout=_CLIENT_SECONDS * 5)) as db, db:
            db.execute(_MARKS_TABLE)
            db.execute(
                "INSERT INTO marks VALUES (?, ?, ?) ON CONFLICT DO UPDATE SET seq = max(seq, excluded.seq)",
                (person, stream, seq),
            )
    except sqlite3.Error as error:
        raise Refused("unavailable", f"marks cannot be written: {error}") from None


def _annotation(row: sqlite3.Row) -> Annotation:
    return Annotation.model_validate({**dict(row), "evidence": json.loads(row["evidence"])})


def _annotate(folder: Path, statement: Annotate, wall_time: float) -> Annotation:
    """Write one statement beside a session's journal, with no runtime and no lock but the file's own, which it holds
    from its look for the key to its write. The file keeps a write-ahead log, so a reader never holds a writer up. The
    same statement again is answered with the first, and another under the same producer, version, params, target and
    kind is refused `conflict`, naming the one there, as a key reused is."""
    said = {
        **statement.model_dump(include={"scope", "status", "value", "head_seq"}),
        "evidence": json.dumps(statement.evidence),
    }
    params = json.dumps(statement.params, sort_keys=True, separators=(",", ":")).encode()
    row = {**statement.model_dump(include={"target", "kind", "producer", "producer_version"}), **said}
    row |= {"params_hash": hashlib.sha256(params).hexdigest(), "wall_time": wall_time}
    try:
        with contextlib.closing(sqlite3.connect(folder / ANNOTATIONS, timeout=_CLIENT_SECONDS * 5)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            db.execute(_ANNOTATIONS_TABLE)
            db.execute(_ANNOTATIONS_INDEX)
            found = db.execute(
                """
                SELECT * FROM annotations WHERE producer = :producer AND producer_version = :producer_version
                    AND params_hash = :params_hash AND target = :target AND kind = :kind
                """,
                row,
            ).fetchone()
            if found is None:
                columns = ", ".join(row)
                found = db.execute(
                    f"INSERT INTO annotations ({columns}) VALUES ({', '.join(f':{key}' for key in row)}) RETURNING *",
                    row,
                ).fetchone()
            elif any(found[key] != value for key, value in said.items()):
                raise Refused("conflict", f"annotation {found['id']} says otherwise under this producer and version")
            return _annotation(found)
    except sqlite3.Error as error:
        raise Refused("unavailable", f"annotations cannot be written: {error}") from None


def _annotations_of(folder: Path, target: str | None) -> list[Annotation]:
    """The statements about one event, found by its index, or every one, oldest first. Reading writes nothing, so a
    folder with none stays as it was."""
    if not (folder / ANNOTATIONS).exists():
        return []
    try:
        uri = f"{(folder / ANNOTATIONS).as_uri()}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=_CLIENT_SECONDS * 5)) as db:
            db.row_factory = sqlite3.Row
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name = 'annotations'").fetchone() is None:
                return []
            if target is None:
                rows = db.execute("SELECT * FROM annotations ORDER BY id")
            else:
                rows = db.execute("SELECT * FROM annotations WHERE target = ? ORDER BY id", (target,))
            return [_annotation(row) for row in rows]
    except sqlite3.Error as error:
        raise Refused("unavailable", f"annotations cannot be read: {error}") from None


def _principal_of(folder: Path) -> str:
    """Who started a session, as its manifest says."""
    return Manifest.model_validate_json((folder / MANIFEST).read_bytes()).principal


def _unclaim(folder: Path) -> None:
    """Free the name of a session no runtime has opened, whose folder holds its manifest and nothing else."""
    (folder / MANIFEST).unlink()
    folder.rmdir()


def _resume_command(folder: Path) -> str:
    return f'`platoon-harness session resume {folder.name}`, or `Session.resume("{folder.name}")`,'


def _refuse_a_program_detached(detach: bool, principal: str) -> None:
    """A program's session issues no owner credential, so a detached runtime of one would give back a guest that could
    only read, and leave a runtime nothing could stop."""
    if detach and principal.startswith("program:"):
        raise Refused("unsupported", "a program's session issues no owner credential, so only its own process acts")


def _refuse_across_processes(detach: bool, authority: Authority | None, clock: Clock | None) -> None:
    if detach and (authority is not None or clock is not None):
        raise Refused("unsupported", "a detached runtime is another process, and takes no authority or clock from here")
