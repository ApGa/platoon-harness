"""The host: what the journal asks of the world, one task per effect, and each harness heard in order."""

import asyncio
import contextlib
import logging
import shutil
from collections.abc import Awaitable, Callable, Mapping
from functools import partial
from pathlib import Path
from typing import Any

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
    Delivery,
    Delta,
    Driver,
    DriverError,
    DriverInfo,
    Exited,
    Item,
    Offered,
    Ready,
    Report,
    Started,
    ToolBinding,
)
from platoon_harness.drivers.env import Redactor, secrets_of
from platoon_harness.drivers.levels import Profile, levels, tool_visibility
from platoon_harness.drivers.process import reap
from platoon_harness.kernel import Effect, Kernel, Outcome, first, hash_token
from platoon_harness.schema import ConfigError
from platoon_harness.team import Team
from platoon_harness.tools import PH, ToolServer, delivery_text, harness_name, list_tools, preamble, shell_name

from .authority import Admission, AgentOutcome, AgentRef, Authority, SpawnRequest
from .opening import make_driver
from .paths import agent_folder

NAMESPACE = "ph"
GRACE = 5.0

_READY_SECONDS = 60.0
_RETRY_SECONDS = 1.0
_RENEW_EVERY = 5.0
_GOAL_BODY_LIMIT = 16 * 1024 * 1024
_MCP = frozenset({"mcp-http", "mcp-stdio"})

log = logging.getLogger("platoon_harness.runtime")

__all__ = ["GRACE", "NAMESPACE", "DriverLink", "Host"]


class DriverLink:
    """One harness as the host holds it. Links live on the `Host` and not in the daemon, so a restarted daemon loses
    none. `leaving` means its end is our doing, and `ready` is set once `agent.start` commits or nobody needs it to."""

    def __init__(self, agent: str, role: str, driver: Driver, info: DriverInfo, *, resumed: bool) -> None:
        self.agent = agent
        self.role = role
        self.driver = driver
        self.info = info
        self.resumed = resumed
        self.leaving = False
        self.ready = asyncio.Event()
        self.redact = Redactor(())
        self.ours: tuple[str, ...] = ()
        self.order = asyncio.Lock()
        self.renewal = 0.0


class Host:
    """Performs effects from `v_effects`, level-triggered, so it holds no position that must survive a restart. One
    agent's effects start in the order `effect.ready` allows, and `interrupt`, `stop` and `answer` go around that order
    by their priority, each in its own task, so Esc works while a delivery hangs."""

    def __init__(
        self, kernel: Kernel, tools: ToolServer, team: Team, authority: Authority, folder: Path, cwd: Path
    ) -> None:
        self._kernel = kernel
        self._tools = tools
        self._team = team
        self._authority = authority
        self._folder = folder
        self._cwd = cwd
        self._links: dict[str, DriverLink] = {}
        self._acting: dict[int, asyncio.Task[None]] = {}
        self._admitted: dict[str, Admission] = {}
        self._described: dict[str, DriverInfo] = {}
        self._closing = False
        self._acts: dict[str, Callable[[Effect], Awaitable[Any]]] = {
            "admit": self._admit,
            "workspace": self._workspace,
            "launch": self._launch,
            "deliver": self._deliver,
            "interrupt": self._interrupt,
            "stop": self._stop,
            "answer": self._answer,
        }

    def link(self, agent: str | None) -> DriverLink | None:
        return self._links.get(agent) if agent else None

    async def run(self) -> None:
        """The daemon: notice what is ready, start it, and sleep until the journal moves."""
        kernel = self._kernel
        while not kernel.closed:
            head = kernel.head
            self._dispatch()
            await kernel.changed(head)

    def _dispatch(self) -> None:
        kernel = self._kernel
        for kind in ("interrupt",) if self._closing else self._acts:
            for row in kernel.query(kernel.runtime, "effect.ready", {"kind": kind}).result or ():
                effect = Effect.model_validate(row)
                if effect.id not in self._acting and not (kind == "deliver" and self._held(effect.agent)):
                    self._begin(effect)

    def _held(self, agent: str | None) -> bool:
        """Whether a takeover holds this agent's deliveries. A release moves the journal, so this looks again."""
        kernel = self._kernel
        return kernel.query(kernel.runtime, "agent.status", {"agent": agent}).result["state"] == "held"

    def _begin(self, effect: Effect) -> None:
        task = asyncio.create_task(self._perform(effect))
        self._acting[effect.id] = task
        task.add_done_callback(lambda _: self._acting.pop(effect.id))

    async def _perform(self, effect: Effect) -> None:
        """Start, act, report. A driver that raises anything but `DriverError` is broken, so its harness is lost."""
        started = await self.insist("effect.start", {"id": effect.id})
        if started.refusal is not None:
            return  # It moved on before it started, which is no failure of ours.
        attempt = {"id": effect.id, "attempt": started.result}
        try:
            result = await self._acts[effect.kind](effect)
        except (DriverError, ConfigError) as error:
            await self.insist("effect.fail", {**attempt, "error": self._masked(effect, str(error))})
        except Exception as error:
            log.exception("%s failed for %s", effect.kind, effect.agent)
            said = self._masked(effect, f"{type(error).__name__}: {error}")
            await self.insist("effect.fail", {**attempt, "error": said})
            await self._lose(effect.agent, f"its {effect.kind} failed: {type(error).__name__}")
        else:
            await self.insist("effect.finish", {**attempt, "result": result})

    def _masked(self, effect: Effect, text: str) -> str:
        """What a harness said is journaled with any credential it held masked."""
        link = self.link(effect.agent)
        return text if link is None else link.redact(text)

    async def insist(self, op: str, args: Mapping[str, Any]) -> Outcome:
        """Submit as the runtime. What left no event may be tried again, so it is, until the kernel closes."""
        kernel = self._kernel
        while True:
            outcome = await kernel.submit(kernel.runtime, op, args)
            refusal = outcome.refusal
            if refusal is None or outcome.seq is not None or refusal.code not in ("busy", "unavailable"):
                return outcome
            if kernel.closed:
                return outcome
            await kernel.clock.sleep(refusal.retry_after or _RETRY_SECONDS)

    # Effects.

    async def _admit(self, effect: Effect) -> None:
        agent = effect.data["agent"]
        self._admitted[agent] = await self.admit(SpawnRequest(agent=agent, role=effect.data["role"]))

    async def admit(self, spawn: SpawnRequest) -> Admission:
        """Admit an agent and give it its credential: the raw token stays in memory, and only its hash is journaled."""
        admission = await self._authority.admit(spawn)
        token_hash = hash_token(admission.token.reveal())
        issued = await self.insist("principal.issue", {"id": f"agent:{spawn.agent}", "token_hash": token_hash})
        if issued.refusal is not None:
            raise DriverError(f"{spawn.agent} has no credential: {issued.refusal.detail}")
        return admission

    async def _workspace(self, effect: Effect) -> dict[str, str]:
        mode = effect.data["workspace"]
        if mode != "shared":
            raise DriverError(f"workspace `{mode}` is not available yet: use `shared`")
        return {"path": str(self._cwd)}

    def _goal(self, data: Mapping[str, Any]) -> str:
        body = data["body"]
        if body is None:
            return data["goal"]
        text = self._kernel.get_body(body.removeprefix("sha256:"), limit=_GOAL_BODY_LIMIT)
        return "\n\n".join(filter(None, (data["goal"], text.decode(errors="replace"))))

    async def _launch(self, effect: Effect) -> dict[str, str | None]:
        data = effect.data
        agent, role = data["agent"], data["role"]
        admission = self._admitted.pop(agent, None)
        if admission is None:  # It finished in a runtime that has gone, and what it gave went too.
            admission = await self.admit(SpawnRequest(agent=agent, role=role, resumed=True))
        return {"native": await self.connect(agent, role, admission, goal=self._goal(data))}

    async def connect(
        self, agent: str, role: str, admission: Admission, *, goal: str = "", resume: str | None = None
    ) -> str | None:
        """Bring a harness up on its own binding, and return the native id `start` gave. A harness that never says it is
        ready is a failure, not a hang."""
        info = await self.describe(role)
        driver = await asyncio.to_thread(make_driver, self._team.roles[role])
        link = DriverLink(agent, role, driver, info, resumed=resume is not None)
        self._links[agent] = link
        spec = self._spec(link, admission, goal, resume)
        link.redact = Redactor(secrets_of(spec))

        async def up() -> Started:
            started = await driver.start(spec, partial(self._heard, link))
            await link.ready.wait()
            return started

        coming = asyncio.ensure_future(up())
        try:
            await first(asyncio.shield(coming), self._kernel.clock.sleep(_READY_SECONDS))
            if not coming.done():
                raise DriverError(f"{agent}'s harness never said it was ready")
            return coming.result().native
        except BaseException as error:
            coming.cancel()
            await self._discard(link)
            if isinstance(error, DriverError):
                raise DriverError(link.redact(str(error))) from error
            raise

    async def _discard(self, link: DriverLink) -> None:
        link.leaving = True
        self._links.pop(link.agent, None)
        with contextlib.suppress(Exception):
            await link.driver.stop(GRACE)

    async def describe(self, role: str) -> DriverInfo:
        """What a role's driver says of itself, kept, because a wire program says it by running."""
        if role not in self._described:
            make = partial(make_driver, self._team.roles[role])
            self._described[role] = await asyncio.to_thread(lambda: make().describe())
        return self._described[role]

    def _spec(self, link: DriverLink, admission: Admission, goal: str, resume: str | None) -> AgentSpec:
        role = self._team.roles[link.role]
        folder = agent_folder(self._folder, link.agent)
        teaching, binding = None, None
        if paths := link.info.capabilities.tool_paths:
            surface = harness_name(NAMESPACE) if paths & _MCP else shell_name
            principal = self._kernel.authenticate(admission.token.reveal())
            teaching = preamble(self._kernel, principal, surface)
            link.ours = tuple(tool["name"] for tool in list_tools(self._kernel, principal))
            binding = self._binding(folder, admission.token, surface=f"mcp__{NAMESPACE}" if paths & _MCP else "ph")
        return AgentSpec(
            agent=link.agent,
            role=link.role,
            goal=goal,
            cwd=self._cwd,
            folder=folder,
            model=role.model,
            tools=binding,
            access=admission.access,
            instructions="\n\n".join(filter(None, (role.instructions, teaching))) or None,
            resume=resume,
        )

    def _binding(self, folder: Path, token: Secret, *, surface: str) -> ToolBinding:
        bin = folder / "bin"
        bin.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(PH, bin / "ph")
        (bin / "ph").chmod(0o700)
        return ToolBinding(url=f"{self._tools.url}?surface={surface}", token=token, namespace=NAMESPACE, bin=bin)

    def _required(self, effect: Effect) -> DriverLink:
        link = self.link(effect.agent)
        if link is None:
            raise DriverError(f"{effect.agent} has no harness")
        return link

    async def _deliver(self, effect: Effect) -> dict[str, Any]:
        link, data = self._required(effect), effect.data
        surface = harness_name(NAMESPACE) if link.info.capabilities.tool_paths & _MCP else shell_name
        delivery = Delivery(
            input=str(data["input"]),
            boundary=data["boundary"],
            text=delivery_text(data, surface, self._kernel.ops),
            items=tuple(Offered(**item) for item in data["items"]),
            behind=data["behind"],
        )
        return (await link.driver.deliver(delivery)).model_dump(mode="json")

    async def _interrupt(self, effect: Effect) -> dict[str, Any] | None:
        link = self.link(effect.agent)
        return None if link is None else (await link.driver.interrupt()).model_dump(mode="json")

    async def _answer(self, effect: Effect) -> None:
        await self._required(effect).driver.answer(effect.data["approval"], effect.data["verdict"])

    async def _stop(self, effect: Effect) -> None:
        """End what an ended agent left. With no link, a crash may have left it, and `reap` proves what is ours."""
        name = effect.data["agent"]
        link = self._links.pop(name, None)
        if link is None:
            await reap(agent_folder(self._folder, name), GRACE)
        else:
            link.leaving = True
            link.ready.set()
            await link.driver.stop(GRACE)
        status = self._kernel.query(self._kernel.runtime, "agent.status", {"agent": name})
        role = link.role if link else status.result["role"]
        await self._authority.finish(AgentRef(agent=name, role=role), AgentOutcome(status=status.result["status"]))

    # Reports.

    async def _heard(self, link: DriverLink, report: Report) -> None:
        """Take one report, in the order its harness said it: a driver waits here, and its own queue keeps a pipe
        draining. Nothing it cannot hear goes unsaid: a report that cannot be taken ends the harness, not the host."""
        kernel = self._kernel
        try:
            if isinstance(report, Delta):
                kernel.push_delta(link.agent, report.text)
            else:
                async with link.order:
                    await self._commit(link, report)
            await self._renew(link)
        except Exception:
            log.exception("a report from %s could not be taken", link.agent)
            await self._lose(link.agent, "its reports could not be taken")

    async def _commit(self, link: DriverLink, report: Report) -> None:
        match report:
            case Ready():
                await self._ready(link, report)
                return
            case Exited() if link.leaving:
                return
            case Item(body=str(text)):
                sha256 = await self._kernel.put_body(text.encode(errors="replace"))
                report = report.model_copy(update={"body": f"sha256:{sha256}"})
        outcome = await self.insist("agent.report", {"agent": link.agent, "report": report})
        if isinstance(report, ApprovalRequested) and outcome.refusal is not None:
            await link.driver.answer(report.id, "deny")  # It is blocked on an answer the journal will not hold.

    async def _ready(self, link: DriverLink, ready: Ready) -> None:
        """Commit what was declared with what was verified, so no driver can claim a level."""
        info = link.info
        profile = Profile(
            driver=info.name,
            version=ready.version or info.version,
            login=info.login,
            tools=tool_visibility(ready.tools_visible, link.ours),
        )
        args = {
            "agent": link.agent,
            "ready": ready,
            "declared": info.capabilities,
            "verified": profile.model_dump(mode="json"),
            "levels": levels(info.capabilities, profile, None).model_dump(mode="json"),
            "resumed": link.resumed,
        }
        await self.insist("agent.start", args)
        link.ready.set()

    async def _renew(self, link: DriverLink) -> None:
        """Observed activity keeps an agent's leases, up to `lease_max`. Asking first journals nothing idle."""
        kernel = self._kernel
        now = kernel.clock.now()
        if now >= link.renewal:
            link.renewal = now + _RENEW_EVERY
            for lease in kernel.query(kernel.runtime, "lease.due", {"agent": link.agent}).result or ():
                await kernel.submit(kernel.runtime, "task.renew", lease)

    async def _lose(self, agent: str | None, reason: str) -> None:
        """A harness nothing can hear any more has exited, as far as anyone can tell: no silent hang."""
        link = self.link(agent)
        if link is not None and not link.leaving:
            await self.insist("agent.report", {"agent": link.agent, "report": Exited(reason=reason)})

    # Shutdown.

    def closing(self) -> None:
        """Start nothing new but interrupts, and take no harness's end from here on as an agent's."""
        self._closing = True
        for link in self._links.values():
            link.leaving = True

    async def close(self, grace: float) -> None:
        """End every process tree, and drop whatever was still in flight. A dropped effect stays `started`, so the next
        runtime marks it uncertain, which is the truth."""
        links = tuple(self._links.values())
        self._links.clear()

        async def ended(link: DriverLink) -> None:
            link.leaving = True
            link.ready.set()
            try:
                async with asyncio.timeout(2 * grace + _RETRY_SECONDS):
                    await link.driver.stop(grace)
            except (DriverError, TimeoutError):
                log.exception("%s did not stop", link.agent)

        await asyncio.gather(*map(ended, links))
        acting = tuple(self._acting.values())
        for task in acting:
            task.cancel()
        await asyncio.gather(*acting, return_exceptions=True)
