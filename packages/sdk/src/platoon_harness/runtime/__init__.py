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

from .authority import Admission, AgentOutcome, AgentRef, Authority, LocalAuthority, SpawnRequest
from .control import Control
from .host import GRACE, Host
from .opening import open_session, told
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
    "LocalAuthority",
    "Runtime",
    "SpawnRequest",
    "told",
]


class Runtime:
    """One live session. `start` is one path for a new session and a resumed one: recover, open under keys that answer
    from the journal, then per agent reap, resume and reconcile.

    `stop` is the owner's shutdown: interrupt turns, wait `grace`, end the process trees, hand back what will not
    happen, append `session.stopped`, and keep the folder resumable. A journal that stops answering holds up none of it
    past `grace`, and nothing a driver does keeps it from letting go.
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
        self.human = Principal(id=manifest.human)
        self.tools = ToolServer(self.kernel)
        authority = self._authority or LocalAuthority(team)
        cwd = Path(manifest.cwd)
        self.host = Host(self.kernel, self.tools, team, authority, self.folder, cwd, plan_login=manifest.plan_login)
        self.control = Control(self.kernel, self.human, self.folder)
        try:
            await self.host.check_plan_login()
            incarnation = (await self.kernel.recover(*manifest.drift())).result
            await open_session(self.kernel, team, manifest, authority, text, await self.host.capabilities())
            await self.tools.start()
            await self._issue_credentials()
            await first(recover_agents(self.kernel, self.host, self.folder, cwd), self._stop_asked.wait())
            self._supervising = asyncio.create_task(self.kernel.supervise())
            await self.control.start()
            running = Running(
                pid=os.getpid(), started=self.kernel.clock.now(), socket=str(self.control.path), incarnation=incarnation
            )
            write_private(self.folder / RUNNING, running.model_dump_json())
        except BaseException:
            self.host.closing()
            await self.host.close(GRACE)
            await self._close()
            raise

    async def _issue_credentials(self) -> None:
        """A fresh pair per incarnation, so the last one's stop working. The owner's hash is in the journal. A view
        token is nobody's identity, so it lives only in the runtime and its file."""
        owner = secrets.token_urlsafe(32)
        issue = {"id": self.human.id, "token_hash": hash_token(owner)}
        issued = await self.kernel.submit(self.kernel.runtime, "principal.issue", issue)
        if issued.refusal is not None:
            raise Refused(issued.refusal.code, issued.refusal.detail)
        write_private(self.folder / OWNER_TOKEN, owner)
        write_private(self.folder / VIEW_TOKEN, self.control.view_token)

    def ask_to_stop(self) -> None:
        """Ask `run` to return. A signal handler may call this."""
        self._stop_asked.set()

    async def run(self) -> None:
        """Serve until asked to stop, or until the session has drained: nothing is left for a detached runtime to do."""
        kernel = self.kernel
        while not self._stop_asked.is_set():
            head = kernel.head
            status = kernel.query(kernel.runtime, "session.status", {}).result
            if status["state"] != "open" and status["settled"]:
                return
            await first(kernel.changed(head), self._stop_asked.wait())

    def _records(self) -> list[dict[str, Any]]:
        return self.kernel.query(self.kernel.runtime, "agent.records", {}).result

    async def stop(self, grace: float = GRACE) -> None:
        if self._stopped:
            return
        self._stopped = True
        kernel, host = self.kernel, self.host
        limit = grace + _SUBMIT_SECONDS
        host.closing()
        try:
            await first(self._interrupt_turns(grace), kernel.clock.sleep(limit))
        finally:
            try:
                await self._end_daemons()
                await host.close(grace)
                await first(self._hand_back(), kernel.clock.sleep(limit))
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

    async def _hand_back(self) -> None:
        """Release what will not happen now. A turn still open ends, which reconciles its reservation, and its agent is
        told on resume. A handover that never started fails, which queues its entries again and returns a wake's
        reservation. A spawn still to come keeps its own, since the next runtime goes on with it."""
        kernel, host = self.kernel, self.host
        for record in self._records():
            if record["turn"] is not None:
                report = TurnEnded(reason=OWNER_STOP)
                await host.insist("agent.report", {"agent": record["name"], "report": report})
        requested = kernel.query(kernel.runtime, "effect.list", {"state": "requested"}).result
        for row in (row for row in requested if row["kind"] == "deliver"):
            started = await host.insist("effect.start", {"id": row["id"]})
            if started.refusal is None:
                failed = {"id": row["id"], "attempt": started.result, "error": "the owner stopped before it started"}
                await host.insist("effect.fail", failed)
        await host.insist("session.stop", {})

    async def _end_daemons(self) -> None:
        if self._supervising is not None:
            self._supervising.cancel()
            await asyncio.gather(self._supervising, return_exceptions=True)

    async def _close(self) -> None:
        """Let go of everything, in the order that leaves nobody hanging on what has gone."""
        await self._end_daemons()
        await self.tools.stop()
        await self.control.stop()
        (self.folder / RUNNING).unlink(missing_ok=True)
        self.kernel.close()
