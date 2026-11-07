"""The runtime: one live session's kernel, daemons, tool plane and control socket. Nothing here is global, so several
can share a process, and `Session` is how anyone uses one."""

import asyncio
import logging
import os
import secrets
from pathlib import Path
from typing import Any

from platoon_harness.config import Manifest
from platoon_harness.drivers import TurnEnded
from platoon_harness.extensions import Installed
from platoon_harness.kernel import Clock, Daemon, Extension, Kernel, Principal, Refused, first, hash_token
from platoon_harness.primitives import OWNER_STOP, PRIMITIVES
from platoon_harness.team import Team
from platoon_harness.tools import ToolServer

from .authority import Admission, AgentOutcome, AgentRef, Authority, Gateway, LocalAuthority, SpawnRequest
from .control import Control
from .host import GRACE, Host
from .isolation import isolation_of
from .opening import open_session, repository, told
from .paths import MANIFEST, OWNER_TOKEN, RUNNING, VIEW_TOKEN, Running, write_private
from .recovery import recover_agents

log = logging.getLogger("platoon_harness.runtime")

_SUBMIT_SECONDS = 1.0

__all__ = [
    "GRACE",
    "Admission",
    "AgentOutcome",
    "AgentRef",
    "Authority",
    "Gateway",
    "LocalAuthority",
    "Runtime",
    "SpawnRequest",
    "told",
]


class Runtime:
    """One live session. `start` is one path for a new session and a resumed one: recover, open under keys that answer
    from the journal, then per agent reap, resume and reconcile.

    `stop` is the owner's shutdown: interrupt turns, wait `grace`, end the process trees, hand back what will not
    happen, append `session.stopped`, and keep the folder resumable, holding no credential. A journal that stops
    answering holds up none of it past `grace`, and nothing a driver does keeps it from letting go.
    """

    def __init__(self, folder: Path, *, authority: Authority | None = None, clock: Clock | None = None) -> None:
        self.folder = folder
        self._authority = authority
        self._clock = clock
        self._stop_asked = asyncio.Event()
        self._stopped = False
        self._supervising: asyncio.Task[None] | None = None

    async def start(self) -> None:
        text = (self.folder / MANIFEST).read_text()
        manifest = Manifest.model_validate_json(text)
        team = Team.loads(manifest.team)
        extensions = [Installed()[name] for name in team.extensions]
        host_daemon = Daemon("host", lambda _: self.host.run())
        loaded = [*PRIMITIVES, *extensions, Extension("host", daemons=[host_daemon])]
        self.kernel = Kernel.open(self.folder, clock=self._clock, extensions=loaded)
        self.principal = Principal(id=manifest.principal)
        self.tools = ToolServer(self.kernel)
        authority = self._authority or LocalAuthority(team)
        cwd = Path(manifest.cwd)
        self.host = Host(
            self.kernel,
            self.tools,
            team,
            authority,
            self.folder,
            cwd,
            plan_login=manifest.plan_login,
            isolation=isolation_of(extensions),
        )
        self.control = Control(self.kernel, self.principal, self.folder)
        incarnation = None
        try:
            self._refuse_a_managed_session(manifest)
            await self.host.check_plan_login()
            incarnation = (await self.kernel.recover(*manifest.drift())).result
            capabilities, repo = await self.host.capabilities(), await repository(self.kernel, cwd)
            await open_session(self.kernel, team, manifest, text, capabilities, repo)
            await self.tools.start()
            await self._issue_credentials()
            await first(recover_agents(self.kernel, self.host, self.folder), self._stop_asked.wait())
            self._supervising = asyncio.create_task(self.kernel.supervise())
            await self.control.start()
            running = Running(
                pid=os.getpid(), started=self.kernel.clock.now(), socket=str(self.control.path), incarnation=incarnation
            )
            write_private(self.folder / RUNNING, running.model_dump_json())
        except BaseException as error:
            failure = self.kernel.failure
            if incarnation is None:
                self.host.closing()
                await self.host.close(GRACE)
                await self._close()
            else:  # This incarnation has begun in the journal, so it ends there as an owner's does.
                await self.stop()
            if failure is not None and failure is not error:
                raise failure from error
            raise

    def _refuse_a_managed_session(self, manifest: Manifest) -> None:
        """A session that has run never runs again once it was started trainable or its agents' admit results name the
        backend's ids: their keys went with the authority that gave them, no other can admit them as the same agents,
        and an admit a stop cut short named ids nobody knows."""
        if not self.kernel.head:
            return
        if admitted := [record["name"] for record in self._records() if record["backend"]]:
            why = f"an authority that has gone admitted {', '.join(admitted)}"
        elif manifest.trainable:
            why = "it was started trainable, and its authority has gone"
        else:
            return
        raise Refused(
            "unsupported",
            f"session {self.folder.name} is never resumed: {why}, so it is history, which `Session.attach` reads",
        )

    async def _issue_credentials(self) -> None:
        """Fresh credentials each incarnation, so the last one's stop working. The owner's hash is in the journal, and a
        session a program started issues none, as whoever held it would act as that program. A view token is nobody's
        identity, so it lives only in the runtime and its file."""
        if self.principal.kind == "human":
            owner = secrets.token_urlsafe(32)
            issue = {"id": self.principal.id, "token_hash": hash_token(owner)}
            issued = await self.kernel.submit(self.kernel.runtime, "principal.issue", issue)
            if issued.refusal is not None:
                raise Refused(issued.refusal.code, issued.refusal.detail)
            write_private(self.folder / OWNER_TOKEN, owner)
        write_private(self.folder / VIEW_TOKEN, self.control.view_token)

    def ask_to_stop(self) -> None:
        """Ask `run` to return. A signal handler may call this."""
        self._stop_asked.set()

    async def run(self) -> None:
        """Serve until asked to stop, or until the session has drained: nothing is left for a detached runtime to do. A
        commit that fails ends it with `JournalError`, as nothing more can be recorded."""
        kernel = self.kernel
        while not self._stop_asked.is_set():
            if kernel.failure is not None:
                raise kernel.failure
            head = kernel.head
            status = kernel.query(kernel.runtime, "session.status", {}).result
            if status["state"] != "open" and status["settled"]:
                return
            await first(kernel.changed(head), self._stop_asked.wait())

    def _records(self) -> list[dict[str, Any]]:
        """Every agent's record, or none once the kernel has closed, as a failed commit closes it."""
        return self.kernel.query(self.kernel.runtime, "agent.records", {}).result or []

    async def stop(self, grace: float = GRACE) -> None:
        """The owner's shutdown. After a failed commit only the process trees end, and nothing is recorded, as after a
        kill: the next runtime finds the turns that were open and tells their agents they were cut off."""
        if self._stopped:
            return
        self._stopped = True
        kernel, host = self.kernel, self.host
        limit = grace + _SUBMIT_SECONDS
        host.closing()
        try:
            if not kernel.closed:
                await first(self._interrupt_turns(grace), kernel.clock.sleep(limit))
        finally:
            try:
                await self._end_daemons()
                await host.close(grace)
                if not kernel.closed:
                    bundle = await host.bundle()
                    await first(self._hand_back(bundle), kernel.clock.sleep(limit))
            finally:
                await self._close()
        log.info("session %s stopped", self.folder.name)

    async def _interrupt_turns(self, grace: float) -> None:
        kernel, host = self.kernel, self.host
        for record in self._records():
            if record["turn"] is not None:
                await host.insist("agent.interrupt", {"agent": record["name"]})
        deadline = kernel.clock.now() + grace
        while any(record["turn"] is not None for record in self._records()):
            head = kernel.head
            remaining = deadline - kernel.clock.now()
            if remaining <= 0:
                return
            await first(kernel.changed(head), kernel.clock.sleep(remaining))

    async def _hand_back(self, bundle: dict[str, Any] | None) -> None:
        """Release what will not happen now. A turn still open ends, which reconciles its reservation, and its agent is
        told on resume. `session.stop` records the `bundle` of the commits the journal recorded, and cancels a handover
        that never started, which queues its entries again and returns a wake's reservation. A spawn still to come keeps
        its own, since the next runtime goes on with it."""
        host = self.host
        for record in self._records():
            if record["turn"] is not None:
                report = TurnEnded(reason=OWNER_STOP)
                await host.insist("agent.report", {"agent": record["name"], "report": report})
        await host.insist("session.stop", {"bundle": bundle})

    async def _end_daemons(self) -> None:
        if self._supervising is not None:
            self._supervising.cancel()
            await asyncio.gather(self._supervising, return_exceptions=True)

    async def _close(self) -> None:
        """Let go of everything, in the order that leaves nobody hanging on what has gone. The credential files go once
        the socket that took them has closed and before the lock does, so no other runtime's are among them, and a
        killed runtime's, which are dead, go at the next stop."""
        await self._end_daemons()
        await self.tools.stop()
        await self.control.stop()
        for name in (OWNER_TOKEN, VIEW_TOKEN, RUNNING):
            (self.folder / name).unlink(missing_ok=True)
        self.kernel.close()
