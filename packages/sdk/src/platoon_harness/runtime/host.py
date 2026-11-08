"""The host: what the journal asks of the world, one task per effect, and each harness heard in order."""

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import shutil
import socket
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any
from uuid import uuid4

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    Access,
    AgentSpec,
    ApprovalRequested,
    Capabilities,
    Compacted,
    Delivery,
    Delta,
    Driver,
    DriverError,
    DriverInfo,
    Exited,
    Gateway,
    Item,
    Login,
    Offered,
    Ready,
    Reconciled,
    Report,
    ToolBinding,
    TurnEnded,
    unknown_frame,
)
from platoon_harness.drivers.env import Held, Redactor, inherited, open_beneath, secrets_of, tmpdir
from platoon_harness.drivers.levels import Profile, implementation, levels, speaks_for, tool_visibility
from platoon_harness.drivers.process import exit_reason, reap, run
from platoon_harness.kernel import Effect, Event, Kernel, Outcome, Refused, first, hash_token, tool_name
from platoon_harness.primitives import CUT_OFF, OWNER_STOP, Repo, Workspace
from platoon_harness.primitives.approvals import bounded
from platoon_harness.schema import ConfigError, Problem, seconds
from platoon_harness.team import Role, Team, Test
from platoon_harness.tools import (
    NAMESPACE,
    PH,
    ToolServer,
    delivery_text,
    held_tools,
    instructions,
    shell_name,
    surface_of,
)

from .authority import Admission, AgentOutcome, AgentRef, Authority, SpawnRequest
from .diffs import patch, uncommitted
from .git import GitError
from .isolation import Isolation, hidden
from .looks import PAGE, look, tips_of
from .opening import PLAN_LOGIN_FIX, make_driver
from .paths import TESTS, agent_folder, read_conformance, root_of
from .workspaces import (
    branch_of,
    checkout,
    end_snapshot,
    end_worktree,
    make_snapshot,
    make_worktree,
    present,
    write_bundle,
)

GRACE = 5.0
_PRINTED = 64 * 1024
"""How much of what a runtime test printed its record keeps, the last of it: as much as the journal holds in an event's
own body, so that `blob.get` reads it for anyone."""

_READY_SECONDS = 60.0
_HANDOVER_SECONDS = 60.0
_RECONCILE_SECONDS = 10.0
_RETRY_SECONDS = 1.0
_RENEW_EVERY = 5.0
_GOAL_BODY_LIMIT = 16 * 1024 * 1024

log = logging.getLogger("platoon_harness.runtime")

__all__ = ["GRACE", "DriverLink", "Host"]


def _pinned(role: Role, access: Access) -> str | None:
    """The model an agent must run: its gateway's, which its role may name only as it is, or else its role's."""
    if not isinstance(access, Gateway):
        return role.model
    if role.model not in (None, access.model):
        raise DriverError(f"its role pins {role.model}, and its gateway serves {access.model}")
    return access.model


def _ends_live_text(report: Report) -> bool:
    """Whether what a harness said live is now in the journal, as an item, or gone with its turn."""
    return isinstance(report, TurnEnded) or (isinstance(report, Item) and report.kind in ("message", "thought"))


class DriverLink:
    """One harness as the host holds it. Links live on the `Host` and not in the daemon, so a restarted daemon loses
    none. `pinned` is the model it must run and `login` what it runs on, as its access says. `leaving` means its end is
    our doing. `ready` is set once `agent.start` commits, or nobody needs it to, or `refused` says why it never will.
    `handing` is set to drop a handover under way."""

    def __init__(
        self, agent: str, role: str, driver: Driver, info: DriverInfo, *, pinned: str | None, login: Login | None
    ) -> None:
        self.agent = agent
        self.role = role
        self.driver = driver
        self.info = info
        self.pinned = pinned
        self.login = login
        self.leaving = False
        self.ready = asyncio.Event()
        self.refused: str | None = None
        self.handing: asyncio.Event | None = None
        self.redact = Redactor(())
        self.live = Held(self.redact)
        self.held: set[str] = set()
        self.order = asyncio.Lock()
        self.renewal = 0.0

    def refuse(self, why: str) -> None:
        self.refused = why
        self.ready.set()


class Host:
    """Performs effects from `v_effects`, level-triggered, so it holds no position that must survive a restart. One
    agent's effects start in the order `effect.ready` allows, and `interrupt`, `stop` and `answer` go around that order
    by their priority, each in its own task, so Esc works while a delivery hangs."""

    def __init__(
        self,
        kernel: Kernel,
        tools: ToolServer,
        team: Team,
        authority: Authority,
        folder: Path,
        cwd: Path,
        *,
        plan_login: bool,
        isolation: Isolation | None = None,
    ) -> None:
        self._kernel = kernel
        self._tools = tools
        self._team = team
        self._authority = authority
        self._folder = folder
        self._cwd = cwd
        self._plan_login = plan_login
        self._isolation = isolation
        self._links: dict[str, DriverLink] = {}
        self._acting: dict[int, asyncio.Task[None]] = {}
        self._admitted: dict[str, Admission] = {}
        self._access: dict[str, Access] = {}
        self._described: dict[str, DriverInfo] = {}
        self._closing = False
        self._looking = asyncio.Lock()
        self._tips: list[str] | None = None
        self._acts: dict[str, Callable[[Effect], Awaitable[Any]]] = {
            "admit": self._admit,
            "workspace": self.workspace,
            "launch": self._launch,
            "deliver": self._deliver,
            "interrupt": self._interrupt,
            "probe": self._probe,
            "rest": self._rest,
            "stop": self._stop,
            "answer": self._answer,
            "test": self._test,
            "diff": self._diff,
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
        except (DriverError, ConfigError, GitError) as error:
            await self.insist("effect.fail", {**attempt, "error": self._masked(effect, str(error))})
        except Exception as error:
            said = self._masked(effect, f"{type(error).__name__}: {error}")
            log.error("%s failed for %s: %s", effect.kind, effect.agent, said)
            await self.insist("effect.fail", {**attempt, "error": said})
            await self._lose(effect.agent, f"its {effect.kind} failed: {type(error).__name__}")
        else:
            await self.insist("effect.finish", {**attempt, "result": result})
            if effect.kind == "launch" and not await first(
                self._owed(effect.data["agent"], lambda agent: agent["unbegun"]),
                self._kernel.clock.sleep(_READY_SECONDS),
            ):
                await self._lose(effect.agent, "it said it was ready and never began its goal")

    def _masked(self, effect: Effect, text: str) -> str:
        """What a harness said is journaled with any credential it held masked."""
        link = self.link(effect.agent)
        return text if link is None else link.redact(text)

    async def insist(self, op: str, args: Mapping[str, Any]) -> Outcome:
        """Submit as the runtime. What left no event may be tried again, so it is, until the kernel closes, under one
        key: a commit that failed may have landed all the same, and then the key answers from the journal."""
        kernel = self._kernel
        key = uuid4().hex
        while True:
            outcome = await kernel.submit(kernel.runtime, op, args, key=key)
            refusal = outcome.refusal
            if refusal is None or outcome.seq is not None or refusal.code not in ("busy", "unavailable"):
                return outcome
            if kernel.closed:
                return outcome
            await kernel.clock.sleep(refusal.retry_after or _RETRY_SECONDS)

    async def _owed(self, agent: str, owing: Callable[[Mapping[str, Any]], bool]) -> None:
        """Sleep while an agent's record says a turn is still to begin. Once it has ended, nothing is owed."""
        kernel = self._kernel
        while True:
            head = kernel.head
            found = kernel.query(kernel.runtime, "agent.records", {"agent": agent}).result
            if not found or not owing(found[0]):
                return
            await kernel.changed(head)

    # Effects.

    async def _admit(self, effect: Effect) -> dict[str, str]:
        """Admit a spawned agent, and give the backend's ids for it, which its admit records as its result."""
        agent = effect.data["agent"]
        self._admitted[agent] = admission = await self.admit(self._request(agent, effect.data["role"]))
        return dict(admission.backend)

    def _request(self, agent: str, role: str, *, resumed: bool = False) -> SpawnRequest:
        """An agent to admit, with its parent and its goal as its `agent.spawned` records them."""
        spawned = self._kernel.read(self._kernel.runtime, streams=[f"agent/{agent}"], limit=1).events[0].data
        return SpawnRequest(agent=agent, role=role, parent=spawned["parent"], goal=spawned["goal"], resumed=resumed)

    async def admit(self, spawn: SpawnRequest) -> Admission:
        """Admit an agent and give it its credential: the raw token stays in memory, and only its hash is journaled. The
        access it was admitted on is kept for this runtime's life, as a resume gives it back and no other agent shares a
        gateway's bearer. A resumed admission that would not hold its agent to what it was is refused, and the agent is
        lost, since its calls would go on an identity its record does not name."""
        admission = await self._authority.admit(spawn)
        if (why := self._unheld(spawn, admission)) is not None:
            if spawn.resumed:
                await self.insist("agent.report", {"agent": spawn.agent, "report": Exited(reason=why)})
            raise DriverError(why)
        token_hash = hash_token(admission.token.reveal())
        issued = await self.insist("principal.issue", {"id": f"agent:{spawn.agent}", "token_hash": token_hash})
        if issued.refusal is not None:
            raise DriverError(f"{spawn.agent} has no credential: {issued.refusal.detail}")
        self._access[spawn.agent] = admission.access
        return admission

    def _unheld(self, spawn: SpawnRequest, admission: Admission) -> str | None:
        """Why an admission does not hold its agent to one identity of its own: its gateway's bearer is another agent's,
        or, on a resume, the backend's ids are not those its admit recorded, or its access is not what this runtime
        admitted it on. None when it holds."""
        name, access = spawn.agent, admission.access
        bearers = {held.bearer for agent, held in self._access.items() if agent != name and isinstance(held, Gateway)}
        if isinstance(access, Gateway) and access.bearer in bearers:
            return f"{name}'s gateway bearer is another agent's, so no call on it is tied to one agent"
        if not spawn.resumed:
            return None
        record = self._kernel.query(self._kernel.runtime, "agent.records", {"agent": name}).result[0]
        if dict(admission.backend) != record["backend"]:
            return f"{name} came back under other backend ids than its admit recorded"
        if name in self._access and access != self._access[name]:
            return f"{name} came back on other model access than it was admitted on"
        return None

    def _repo(self) -> Repo | None:
        """The repository the session opened on, as the journal holds it: a resume's own reading never replaces it."""
        opened = self._kernel.read(self._kernel.runtime, streams=["session"], limit=1).events
        repo = opened[0].data.get("repo") if opened else None
        return None if repo is None else Repo.model_validate(repo)

    def _workspace_of(self, agent: str) -> Workspace:
        """Where an agent works, as its record holds it. One whose workspace nobody knows has nowhere to run."""
        record = self._kernel.query(self._kernel.runtime, "agent.records", {"agent": agent}).result[0]
        if record["workspace"] is None:
            raise DriverError(f"{agent} has no workspace that anyone knows of")
        return Workspace.model_validate(record["workspace"])

    async def workspace(self, effect: Effect) -> dict[str, Any]:
        """Make an agent's workspace, or adopt what an earlier attempt of this effect made, since no agent starts in
        one before its effect has finished. A mode that cannot be given fails loudly and never degrades: an isolated
        one is a snapshot made only where its isolation can confine it now."""
        mode, agent, repo = effect.data["workspace"], effect.data["agent"], self._repo()
        folder, branch = agent_folder(self._folder, agent), branch_of(self._folder.name, agent)
        if mode == "shared":
            host = socket.gethostname()
            repository = None if repo is None else repo.repository
            made = Workspace(mode="shared", path=str(self._cwd), host=host, repository=repository)
        elif repo is None:
            raise GitError(f"`{mode}` needs a git work tree, and {self._cwd} was in none when the session opened")
        elif mode == "worktree":
            made = await asyncio.to_thread(make_worktree, repo, folder, branch, effect.id)
        else:
            if mode == "isolated" and (why := await asyncio.to_thread(self._refusal)) is not None:
                raise DriverError(why)
            made_for = f"{self._folder.name}/{agent}"
            made = await asyncio.to_thread(make_snapshot, repo, folder, branch, self._tips_at_open(repo), made_for)
            if mode == "isolated":
                made = made.model_copy(update={"mode": "isolated", "assurance": "isolated"})
        return made.model_dump()

    def _refusal(self) -> str | None:
        """Why no isolated agent can be confined now, or None when its isolation can confine one."""
        if self._isolation is None:
            return "`isolated` needs an extension the team names whose isolation confines a harness"
        return self._isolation.refusal()

    async def _wrap(self, agent: str, role: str, workspace: Workspace) -> tuple[str, ...]:
        """The isolation an isolated agent's harness, and the runtime's own git in its tree, run in: writing only its
        folder, which holds its workspace and its harness's home, and a /tmp of its own, reading its repository's
        objects and where its harness is installed, and seeing nothing of your home, of a session under its root or of
        the runtime directory. Any other agent's is empty, as it runs unconfined."""
        if workspace.mode != "isolated":
            return ()
        if self._isolation is None:
            raise DriverError("`isolated` needs an extension the team names whose isolation confines a harness")
        objects = [Path(workspace.objects)] if workspace.objects else []
        readable = [*objects, *(await self.describe(role)).installed]
        return self._isolation.wrap(agent_folder(self._folder, agent), readable, hidden(self._folder))

    def _tips_at_open(self, repo: Repo) -> list[str]:
        """The commits every ref named when the session opened, read from the journal once."""
        if self._tips is None:
            self._tips = tips_of(self._kernel.get_body(repo.tips.removeprefix("sha256:")).decode())
        return self._tips

    def _goal(self, agent: str, data: Mapping[str, Any], offer: int) -> Delivery:
        """A spawn's goal as its harness's first delivery, its gist and then its body, under the launch offer's id."""
        body = data["body"]
        text = data["goal"]
        if body is not None:
            said = self._kernel.get_body(body.removeprefix("sha256:"), limit=_GOAL_BODY_LIMIT).decode(errors="replace")
            text = "\n\n".join(filter(None, (text, said)))
        item = Offered(ref=f"agent/{agent}@1", gist=data["goal"], body=body is not None)
        return Delivery(input=str(offer), boundary="turn", text=text, items=(item,))

    async def _launch(self, effect: Effect) -> None:
        data = effect.data
        agent, role = data["agent"], data["role"]
        admission = self._admitted.pop(agent, None)
        if admission is None:  # It finished in a runtime that has gone, and what it gave went too.
            admission = await self.admit(self._request(agent, role, resumed=True))
        if not self._plan_login and await self._on_plan(agent, role) and (others := await self._live_on_plans(agent)):
            raise DriverError(f"{agent} would join {', '.join(others)} headless on one plan login: {PLAN_LOGIN_FIX}")
        await self.connect(agent, role, admission, goal=data if data["goal"] or data["body"] else None)

    async def connect(
        self,
        agent: str,
        role: str,
        admission: Admission,
        *,
        goal: Mapping[str, Any] | None = None,
        resume: str | None = None,
    ) -> None:
        """Bring a harness up on its own binding, with `goal`, a spawn's goal and body, as its first delivery, under
        the id of the offer that launched it. A gateway goes only to a driver that declares a sealed launch. An isolated
        harness runs in its isolation, on access it was given, as a login of its own would be in your home, which it
        never sees. A harness that never says it is ready is a failure, not a hang."""
        info = await self.describe(role)
        access = admission.access
        if isinstance(access, Gateway) and not info.capabilities.sealed:
            raise DriverError(f"`{info.name}` has no sealed launch, which a gateway admission needs")
        pinned = _pinned(self._team.roles[role], access)
        login = "gateway" if isinstance(access, Gateway) else "key" if access else info.login
        workspace = self._workspace_of(agent)
        wrap = await self._wrap(agent, role, workspace)
        if wrap and not access and info.login is not None:
            raise DriverError(
                f"`isolated` gives `{info.name}` a home of its own, where its {info.login} login is not: "
                "give the role an auth profile"
            )
        await asyncio.to_thread(present, workspace, wrap)
        driver = await asyncio.to_thread(make_driver, self._team.roles[role], self._cwd)
        link = DriverLink(agent, role, driver, info, pinned=pinned, login=login)
        self._links[agent] = link
        spec = self._spec(link, admission, resume, Path(workspace.path), wrap)
        link.redact = Redactor(secrets_of(spec))
        link.live = Held(link.redact)

        async def up() -> None:
            offer = await self._instructed(agent, spec.instructions, goal=goal is not None, resumed=resume is not None)
            handed = None if goal is None or offer is None else self._goal(agent, goal, offer)
            await driver.start(spec.model_copy(update={"goal": handed}), partial(self._heard, link))
            await link.ready.wait()
            if link.refused is not None:
                raise DriverError(link.refused)

        coming = asyncio.ensure_future(up())
        try:
            if not await first(asyncio.shield(coming), self._kernel.clock.sleep(_READY_SECONDS)):
                raise DriverError(f"{agent}'s harness never said it was ready")
            coming.result()
        except BaseException as error:
            coming.cancel()
            await self._discard(link)
            if isinstance(error, DriverError):
                raise DriverError(link.redact(str(error))) from error
            raise

    async def resume(self, agent: Mapping[str, Any]) -> None:
        """Bring an agent's harness back, as its record holds it, on a fresh credential: on its native session, or anew
        when it took no turn, as it has written no session to reopen. With no native id or no resume it cannot come
        back."""
        name, role, native = agent["name"], agent["role"], agent["native"]
        if native is None or not (await self.describe(role)).capabilities.resume:
            raise DriverError("its harness cannot resume")
        admission = await self.admit(self._request(name, role, resumed=True))
        await self.connect(name, role, admission, resume=native if agent["began"] else None)

    async def _instructed(self, agent: str, text: str | None, *, goal: bool, resumed: bool) -> int | None:
        """Journal what a harness is told, as the body it is, before it hears it, and what a fresh start offers it,
        whose seq is the id its goal goes under."""
        args = {"agent": agent, "body": await self._stored(text), "goal": goal, "resumed": resumed}
        if (recorded := await self.insist("agent.instruct", args)).refusal is not None:
            raise DriverError(f"what {agent} is told could not be journaled: {recorded.refusal.detail}")
        return recorded.result

    async def _discard(self, link: DriverLink) -> None:
        self._links.pop(link.agent, None)
        with contextlib.suppress(Exception):
            await self._end(link, GRACE)

    async def _end(self, link: DriverLink, grace: float) -> tuple[str, ...]:
        """End a harness, then whatever its driver left: a wire program's own harness is a group of its own, and only
        `reap` looks for it, and says what it left alone. A driver has what `stop` promises, which is twice `grace`."""
        link.leaving = True
        try:
            async with asyncio.timeout(2 * grace + _RETRY_SECONDS):
                await link.driver.stop(grace)
        finally:
            left = await reap(agent_folder(self._folder, link.agent), grace)
        return left

    async def describe(self, role: str) -> DriverInfo:
        """What a role's driver says of itself, kept, because a wire program says it by running."""
        if role not in self._described:
            make = partial(make_driver, self._team.roles[role], self._cwd)
            self._described[role] = await asyncio.to_thread(lambda: make().describe())
        return self._described[role]

    async def capabilities(self) -> dict[str, Capabilities]:
        """What each role's driver says it can do, by role. One that cannot say is left out, as unknown."""
        found = {}
        for role in self._team.roles:
            with contextlib.suppress(ConfigError, DriverError):
                found[role] = (await self.describe(role)).capabilities
        return found

    async def check_plan_login(self) -> None:
        """Refuse to bring back several agents headless on one plan login, before anything runs, unless the session was
        started saying so, as a harness can be signed in on a plan between runs."""
        if not self._plan_login and len(crowded := await self._live_on_plans()) > 1:
            what = f"{', '.join(crowded)} would run headless on one plan login: {PLAN_LOGIN_FIX}"
            raise ConfigError([Problem("plan_login", what)])

    async def _on_plan(self, agent: str, role: str) -> bool:
        """Whether an agent runs on a plan login: its harness says so now, its role names no auth profile, and its
        authority admitted it through no gateway. A driver that cannot say runs nothing."""
        if self._team.roles[role].auth is not None or isinstance(self._access.get(agent), Gateway):
            return False
        try:
            return (await self.describe(role)).login == "plan"
        except (ConfigError, DriverError):
            return False

    async def _live_on_plans(self, besides: str | None = None) -> list[str]:
        """The live agents but `besides` whose harness runs on a plan login."""
        kernel = self._kernel
        records = kernel.query(kernel.runtime, "agent.records", {})
        if records.refusal is not None:
            raise Refused.of(records.refusal)
        return [
            record["name"]
            for record in records.result
            if record["state"] != "ended"
            and record["name"] != besides
            and await self._on_plan(record["name"], record["role"])
        ]

    def _spec(
        self, link: DriverLink, admission: Admission, resume: str | None, cwd: Path, wrap: tuple[str, ...]
    ) -> AgentSpec:
        """How an agent starts, in `cwd`, where its workspace is, under `wrap`, an isolation's, whose harness keeps its
        state in a home of its own in the agent's folder. Its instructions are the preamble and then the role's words,
        so a role has the last. A harness that reopens its own session keeps what it was told when that began, so it is
        handed that again."""
        role = self._team.roles[link.role]
        folder = agent_folder(self._folder, link.agent)
        env = {}
        if wrap:
            (folder / "home").mkdir(mode=0o700, parents=True, exist_ok=True)
            env["HOME"] = str(folder / "home")
        surface = surface_of(link.info.capabilities)
        principal = self._kernel.authenticate(admission.token.reveal())
        binding = None
        if surface is not None:
            link.held = held_tools(self._kernel, principal)
            name = "ph" if surface is shell_name else "mcp" if surface is tool_name else f"mcp__{NAMESPACE}"
            binding = self._binding(folder, admission.token, surface=name)
        if resume is None:
            told = instructions(self._kernel, principal, surface, self._team.preamble_of(link.role), role.instructions)
        else:
            told = self._told(link.agent)
        return AgentSpec(
            agent=link.agent,
            role=link.role,
            cwd=cwd,
            folder=folder,
            model=link.pinned,
            effort=role.effort,
            sandbox=role.sandbox,
            allow_native_children=role.allow_native_children,
            tools=binding,
            access=admission.access,
            env=env,
            instructions=told,
            resume=resume,
            wrap=wrap,
        )

    def _told(self, agent: str) -> str | None:
        """What an agent's harness was told last, which `agent.instruct` journaled."""
        kernel = self._kernel
        body = kernel.query(kernel.runtime, "agent.records", {"agent": agent}).result[0]["instructions"]
        return None if body is None else kernel.get_body(body.removeprefix("sha256:")).decode()

    def _binding(self, folder: Path, token: Secret, *, surface: str) -> ToolBinding:
        bin = folder / "bin"
        bin.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = open_beneath(folder, bin / "ph", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o700)
        with os.fdopen(fd, "wb") as ph:
            os.fchmod(ph.fileno(), 0o700)
            ph.write(PH.read_bytes())
        return ToolBinding(url=f"{self._tools.url}?surface={surface}", token=token, namespace=NAMESPACE, bin=bin)

    def _required(self, effect: Effect) -> DriverLink:
        link = self.link(effect.agent)
        if link is None:
            raise DriverError(f"{effect.agent} has no harness")
        return link

    async def _deliver(self, effect: Effect) -> None:
        """Hand entries over, and for a wake stay open until its turn begins, so `waking` always has an effect behind it
        and a crash cannot strand one. A resting agent's harness is brought back first. Past a time, or at an
        interrupt, the handover fails, which queues it again."""
        record = self._kernel.query(self._kernel.runtime, "agent.records", {"agent": effect.agent}).result[0]
        if record["resting"] and self.link(effect.agent) is None:
            await self.resume(record)
        link, data = self._required(effect), effect.data
        surface = surface_of(link.info.capabilities) or shell_name
        delivery = Delivery(
            input=str(data["input"]),
            boundary=data["boundary"],
            text=delivery_text(data, surface, self._kernel.ops, link.held),
            items=tuple(Offered(**item) for item in data["items"]),
            behind=data["behind"],
        )
        link.handing = asyncio.Event()
        handed = asyncio.ensure_future(self._hand_over(link, delivery))
        try:
            if not await first(handed, link.handing.wait(), self._kernel.clock.sleep(_HANDOVER_SECONDS)):
                raise DriverError(
                    "it was interrupted" if link.handing.is_set() else "its harness did not take it in time"
                )
            handed.result()
        finally:
            link.handing = None

    async def _hand_over(self, link: DriverLink, delivery: Delivery) -> None:
        await link.driver.deliver(delivery)
        if delivery.boundary == "turn":
            await self._owed(link.agent, lambda agent: agent["state"] == "waking")

    async def _interrupt(self, effect: Effect) -> None:
        link = self.link(effect.agent)
        if link is None:
            return
        if link.handing is not None:
            link.handing.set()
        await self._within(link.driver.interrupt())

    async def _answer(self, effect: Effect) -> None:
        await self._within(self._required(effect).driver.answer(effect.data["approval"], effect.data["verdict"]))

    async def _within[T](self, asked: Coroutine[Any, Any, T]) -> T:
        """A harness that has stopped reading fails what was asked of it, rather than hold it open for ever."""
        answering = asyncio.ensure_future(asked)
        if await first(answering, self._kernel.clock.sleep(_HANDOVER_SECONDS)):
            return answering.result()
        raise DriverError("its harness did not take it in time")

    async def _probe(self, effect: Effect) -> dict[str, Any]:
        """Look at what an agent's turn left: the shared workspace's commits, then its own workspace."""
        agent = effect.data["agent"]
        await self._look(agent, effect.data["cause"], self._places(agent))
        return {}

    def _places(self, agent: str) -> tuple[str, ...]:
        """The workspaces a look at an agent's takes: the shared one's commits, then its own, if it has one."""
        workspace = self._workspace_of(agent)
        return ("shared",) if workspace.mode == "shared" else ("shared", f"@{agent}")

    def _root(self, where: str) -> Path:
        """Where a workspace's work tree is: your checkout's top for the shared one, and in its agent's folder else."""
        repo = self._repo()
        assert repo is not None
        return Path(repo.top) if where == "shared" else agent_folder(self._folder, where[1:]) / "workspace"

    async def _look(self, agent: str, cause: int | None, places: Sequence[str]) -> None:
        """Look at each of `places`, one look at a time in the session, and record what is new in pages, the shared
        workspace first, so that a worker whose base holds its new commits finds them recorded. Git runs in an isolated
        workspace under its agent's wrap. A workspace a look cannot read records the gap `workspace_unobserved` and no
        change. Nothing is looked at outside a repository."""
        if (repo := self._repo()) is None:
            return
        kernel = self._kernel
        async with self._looking:
            readings = kernel.query(kernel.runtime, "repo.looks", {}).result
            makers: dict[str, tuple[Path, tuple[str, ...]]] = {"shared": (Path(repo.top), ())}
            for record in kernel.query(kernel.runtime, "agent.records", {}).result:
                if record["workspace"] and record["workspace"]["mode"] != "shared" and not record["removed"]:
                    made = Workspace.model_validate(record["workspace"])
                    wrap = await self._wrap(record["name"], record["role"], made)
                    makers[f"@{record['name']}"] = (self._root(f"@{record['name']}"), wrap)
            shared = any(role.workspace == "shared" for role in self._team.roles.values())
            for where in places:
                base = repo.head if where == "shared" else self._workspace_of(agent).base
                root, wrap = makers.get(where, (self._root(where), ()))
                try:
                    seen = await asyncio.to_thread(
                        look,
                        root,
                        base=base,
                        tips=self._tips_at_open(repo),
                        last=readings.get(where),
                        makers={name: tree for name, tree in makers.items() if tree[0].is_dir()},
                        record=shared or where != "shared",
                        wrap=wrap,
                    )
                except (GitError, OSError) as error:
                    await self._report({"agent": agent, "workspace": where, "cause": cause, "unobserved": str(error)})
                    continue
                reading = seen.reading
                if seen.whole is not None:
                    reading = {**reading, "body": await self._stored(seen.whole)}
                pages = [seen.commits[start : start + PAGE] for start in range(0, len(seen.commits), PAGE)] or [[]]
                for index, commits in enumerate(pages):
                    page: dict[str, Any] = {"agent": agent, "workspace": where, "cause": cause, "commits": commits}
                    if index == len(pages) - 1:
                        page |= {"rewrite": seen.rewrite, "reading": reading}
                    if not await self._report(page):
                        break

    async def _report(self, page: Mapping[str, Any]) -> bool:
        """Record a page of a look. One the journal refused is a look that did not land, which is said as its gap."""
        refused = (await self.insist("repo.report", page)).refusal
        if refused is not None and "unobserved" not in page:
            why = f"its look could not be recorded: {refused.code}: {refused.detail}"
            await self._report({**{key: page[key] for key in ("agent", "workspace", "cause")}, "unobserved": why})
        return refused is None

    async def _rest(self, effect: Effect) -> None:
        """End a resting agent's harness, and what it left, which its next handover brings back. With no link, a crash
        may have left it, and `reap` proves what is ours."""
        name = effect.data["agent"]
        link = self._links.pop(name, None)
        if link is None:
            await reap(agent_folder(self._folder, name), GRACE)
        else:
            await self._end(link, GRACE)

    async def _stop(self, effect: Effect) -> dict[str, Any]:
        """End what an ended agent left, look once more at what it left, then end its workspace, if nothing would go
        with it. With no link, a crash may have left it, and `reap` proves what is ours. A link stays until its harness
        has stopped, so a shutdown that cuts this short can still stop it. Each step is safe to repeat, so a repeat
        finishes what the last one began, and a workspace gone at a repeat, which an earlier attempt may have removed,
        is not looked for. The authority hears how the agent ended last, even when a step before fails."""
        name, retried = effect.data["agent"], effect.attempts > 0
        folder = agent_folder(self._folder, name)
        record = self._kernel.query(self._kernel.runtime, "agent.records", {"agent": name}).result[0]
        ended: dict[str, Any] = {"removed": False, "kept": None}
        try:
            link = self.link(name)
            if link is None:
                left = await reap(folder, GRACE)
            else:
                link.ready.set()
                left = await self._end(link, GRACE)
                self._links.pop(name, None)
            if record["workspace"] is not None:
                places = [
                    where
                    for where in self._places(name)
                    if where == "shared" or not retried or self._root(where).exists()
                ]
                await self._look(name, effect.data.get("cause"), places)
            if record["workspace"] is not None and (mode := record["workspace"]["mode"]) != "shared":
                workspace, repo = Workspace.model_validate(record["workspace"]), self._repo()
                assert repo is not None
                top = Path(repo.top)
                if mode == "worktree":
                    ended = await asyncio.to_thread(end_worktree, workspace, folder, top, left)
                else:
                    wrap = await self._wrap(name, record["role"], workspace)
                    ended = await asyncio.to_thread(
                        end_snapshot, workspace, folder, top, left, retried=retried, wrap=wrap
                    )
        finally:
            outcome = AgentOutcome(status=record["status"], report=self._report_of(effect.data.get("cause")))
            await self._authority.finish(AgentRef(agent=name, role=record["role"]), outcome)
        return ended

    async def _test(self, effect: Effect) -> dict[str, Any]:
        """Run the team's `test` command at a commit, in a clean detached checkout of it in the session's subfolder, as
        you and unconfined, on what every process inherits, and record what it came to. A test the journal recorded is
        not run again, as when a crash came between its record and its finish, and one a crash cut off runs again from
        the start, once what it left is ended. Its folder goes once it is recorded."""
        sha, repo, test = effect.data["sha"], self._repo(), self._team.test
        assert repo is not None and test is not None  # `repo.test` refuses a test without them.
        folder = self._folder / TESTS / str(effect.id)
        if effect.attempts:
            await reap(folder, GRACE)
            await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)
            if (ref := self._recorded(effect.id, "repo.tested")) is not None:
                return {"ref": ref}
        tmpdir(folder).mkdir(mode=0o700, parents=True)
        tested = {"effect": effect.id, "sha": sha, "command": test.command, "exit": None, "seconds": None}
        try:
            await asyncio.to_thread(checkout, sha, folder / "checkout", self._testable(repo))
            cwd = folder / "checkout" / repo.prefix
            if not cwd.is_dir():
                raise GitError(f"{sha[:12]} holds no {repo.prefix}, where the session's command runs")
        except GitError as error:
            tested |= {"outcome": "error", "why": str(error)}
        else:
            tested |= await self._run_test(test, cwd, folder)
        ref = (await self.insist("repo.record", tested)).result
        await asyncio.to_thread(shutil.rmtree, folder)
        return {"ref": ref}

    def _testable(self, repo: Repo) -> list[str]:
        """The repositories a test reads a commit from: yours, then each workspace's own, but an isolated one's, whose
        objects never leave its isolation."""
        records = self._kernel.query(self._kernel.runtime, "agent.records", {}).result
        own = [
            record["workspace"]["repository"]
            for record in records
            if record["workspace"] and record["workspace"]["mode"] != "isolated" and record["workspace"]["repository"]
        ]
        return list(dict.fromkeys([repo.repository, *own]))

    async def _run_test(self, test: Test, cwd: Path, folder: Path) -> dict[str, Any]:
        """Run a test's command in `cwd` until it exits or its timeout comes, and say what it came to, with the last of
        what it printed. A program it names by a relative path is the commit's own, in its checkout."""
        program, env, clock = test.command[0], {**inherited(), "TMPDIR": str(tmpdir(folder))}, self._kernel.clock
        if shutil.which(str(cwd / program) if os.sep in program else program, path=env.get("PATH")) is None:
            return {"outcome": "error", "why": f"{program} is not an executable a test can run"}
        output, began = folder / "output", clock.now()
        try:
            code = await run(
                test.command,
                cwd=cwd,
                folder=folder,
                env=env,
                output=output,
                limit=seconds(test.timeout),
                clock=clock,
                grace=GRACE,
            )
        except (DriverError, OSError) as error:
            return {"outcome": "error", "why": f"{program} could not start: {error}"}
        ran: dict[str, Any] = {"seconds": round(clock.now() - began, 3), "printed": output.stat().st_size}
        with output.open("rb") as printed:
            printed.seek(max(0, ran["printed"] - _PRINTED))
            ran["body"] = f"sha256:{await self._kernel.put_body(printed.read())}"
        if code is None:
            return {**ran, "outcome": "error", "why": f"its timeout of {test.timeout} came first"}
        if code < 0:
            return {**ran, "outcome": "failed", "why": exit_reason(code)}
        return {**ran, "exit": code, "outcome": "passed" if code == 0 else "failed"}

    async def _diff(self, effect: Effect) -> dict[str, Any]:
        """Read a recorded commit's patch, or a workspace's uncommitted diff, where that workspace lives, and record it,
        or why it could not be read, with the workspace it was read in, and an uncommitted diff with when its reading
        began. A commit is read in the repository of the workspace its look was of, or yours once that has gone, and git
        runs in an isolated workspace under its agent's wrap. A diff the journal recorded is not read again, as when a
        crash came between its record and its finish, and one a crash cut off is read again."""
        if effect.attempts and (ref := self._recorded(effect.id, "repo.diffed")) is not None:
            return {"ref": ref}
        sha, workspace, found_in = (effect.data.get(name) for name in ("sha", "workspace", "found_in"))
        where = workspace or (found_in if found_in and self._root(found_in).is_dir() else "shared")
        diffed: dict[str, Any] = {"effect": effect.id, "sha": sha, "workspace": workspace, "read_in": where}
        try:
            root, wrap = await self._place(where)
            if sha is not None:
                read = await asyncio.to_thread(patch, root, sha, wrap=wrap)
            else:
                diffed["read_at"] = self._kernel.clock.now()
                diffed["head"], read = await asyncio.to_thread(uncommitted, root, wrap=wrap)
        except (GitError, OSError) as error:
            diffed["why"] = str(error)
        else:
            body = f"sha256:{await self._kernel.put_body(read.text)}"
            diffed |= {"body": body, "cut": read.cut, "untracked_repositories": read.untracked_repositories}
        return {"ref": (await self.insist("repo.keep", diffed)).result}

    async def _place(self, where: str) -> tuple[Path, tuple[str, ...]]:
        """A workspace's work tree, and the wrap git runs under there, which only an isolated one's has."""
        if where == "shared":
            return self._root(where), ()
        record = self._kernel.query(self._kernel.runtime, "agent.records", {"agent": where[1:]}).result[0]
        workspace = Workspace.model_validate(record["workspace"])
        return self._root(where), await self._wrap(record["name"], record["role"], workspace)

    def _recorded(self, effect: int, type: str) -> str | None:
        """The ref of the record of what `effect` came to, an event of `type` on `repo/<name>` after its request, or
        None while the journal holds none."""
        kernel, repo, after = self._kernel, self._repo(), effect
        assert repo is not None  # Nothing asks for a test or a diff in a session that observes no repository.
        while True:
            page = kernel.read(kernel.runtime, after=after, streams=[f"repo/{repo.name}"])
            for event in page.events:
                if event.type == type and event.data["effect"] == effect:
                    return f"{event.stream}@{event.version}"
            if (after := page.cursor) >= page.head:
                return None

    def _report_of(self, ended: int | None) -> str | None:
        """The words an agent's end keeps, the gist and then the body, by the seq of its `agent.ended`, or None when it
        said nothing. A body a person redacted is no longer among them. A stop from before it named its cause has none
        to read."""
        if ended is None:
            return None
        event: Event = self._kernel.read(self._kernel.runtime, after=ended - 1, limit=1).events[0]
        report, body = event.data["report"], event.data["body"]
        if body is not None:
            try:
                said = self._kernel.get_body(body.removeprefix("sha256:"), limit=_GOAL_BODY_LIMIT)
            except Refused as refused:
                if refused.refusal.code != "not_found":
                    raise
                said = b""
            report = "\n\n".join(filter(None, (report, said.decode(errors="replace"))))
        return report or None

    async def bundle(self) -> dict[str, Any] | None:
        """Keep the commits the journal recorded in a bundle in the session folder, or None when it recorded none, as
        git may prune one an agent rewrote. Git runs in an isolated agent's repository under its wrap."""
        kernel, repo = self._kernel, self._repo()
        commits, after = [], 0
        while repo is not None:
            page = kernel.read(kernel.runtime, after=after, match="repo/*")
            commits += [event.data["sha"] for event in page.events if event.type == "repo.committed"]
            if (after := page.cursor) >= page.head:
                break
        if repo is None or not commits:
            return None
        repositories: dict[str, tuple[str, ...]] = {}
        for record in kernel.query(kernel.runtime, "agent.records", {}).result:
            if record["workspace"] and (made := Workspace.model_validate(record["workspace"])).repository:
                repositories[made.repository] = await self._wrap(record["name"], record["role"], made)
        return await asyncio.to_thread(write_bundle, self._folder, repo, commits, repositories)

    async def reconcile(self, agent: str | None, key: str) -> Reconciled:
        """What a harness says became of what it was sent. With no harness to ask, or none that says in time, nobody
        knows."""
        link = self.link(agent)
        if link is None:
            return "unknown"
        asked = asyncio.ensure_future(link.driver.reconcile(key))
        try:
            return asked.result() if await first(asked, self._kernel.clock.sleep(_RECONCILE_SECONDS)) else "unknown"
        except Exception as error:
            log.error("%s could not reconcile: %s", agent, link.redact(f"{type(error).__name__}: {error}"))
            return "unknown"

    # Reports.

    async def _heard(self, link: DriverLink, report: Report) -> None:
        """Take one report, in the order its harness said it, with every credential masked, whichever driver said it: a
        driver waits here, and its own queue keeps a pipe draining. Live text is one stream, since a secret can straddle
        two deltas, and any other report ends it. Nothing it cannot hear goes unsaid: a report that cannot be taken ends
        the harness, not the host."""
        try:
            if isinstance(report, Delta):
                self._live(link, link.live.feed(report.text.encode(errors="surrogatepass")))
            else:
                self._live(link, link.live.flush())
                async with link.order:
                    await self._commit(link, link.redact.masked(report))
            await self._renew(link)
        except Exception:
            log.exception("a report from %s could not be taken", link.agent)
            await self._drop(link, report, "its reports could not be taken")

    def _live(self, link: DriverLink, text: bytes) -> None:
        """Live text is the agent's until its harness is on its way out, after which it would follow the agent's end."""
        if text and not link.leaving:
            self._kernel.push_delta(link.agent, text.decode(errors="surrogatepass"))

    async def _commit(self, link: DriverLink, report: Report) -> None:
        match report:
            case Ready():
                await self._ready(link, report)
                return
            case Exited() if link.leaving:
                return
            case Exited(reason=reason) if not link.ready.is_set():
                record = self._kernel.query(self._kernel.runtime, "agent.records", {"agent": link.agent}).result[0]
                if record["resting"]:  # Brought back from rest by a handover, it ended on its own once more.
                    await self.insist("agent.rest", {"agent": link.agent, "exited": reason})
                link.refuse(reason)  # Nobody has heard of this harness, so `connect` fails, which says so.
                return
            case Exited(reason=reason):  # It ended on its own, which `agent.rest` forgives once.
                await self._taken(
                    link, report, await self.insist("agent.rest", {"agent": link.agent, "exited": reason})
                )
                return
            case TurnEnded(reason=reason) if reason in CUT_OFF:
                await self._unknown(link, report.type, f"a turn ended `{reason}`, which only the runtime can say")
                report = TurnEnded(reason="unknown")
            case TurnEnded(reason="interrupted") if self._closing:
                report = TurnEnded(reason=OWNER_STOP)
            case Item(body=body):
                report = report.model_copy(update={"body": await self._stored(body)})
            case ApprovalRequested(body=str(body), cut=cut):  # Masked, so a cut splits no secret.
                kept, left = bounded(body)
                report = report.model_copy(update={"body": await self._stored(kept), "cut": cut + left})
            case Compacted(forgotten=forgotten, summary=summary):
                listed = None if forgotten is None else json.dumps(forgotten)
                stored = {"forgotten": await self._stored(listed), "summary": await self._stored(summary)}
                report = report.model_copy(update=stored)
        outcome = await self.insist("agent.report", {"agent": link.agent, "report": report})
        if outcome.refusal is None and outcome.seq is not None and _ends_live_text(report):
            self._kernel.end_delta(link.agent, outcome.seq)
        await self._taken(link, report, outcome)

    async def _unknown(self, link: DriverLink, kind: str, why: str) -> None:
        for frame in unknown_frame(kind, why):
            await self.insist("agent.report", {"agent": link.agent, "report": frame})

    async def _stored(self, body: str | bytes | None) -> str | None:
        """A body from a report as the ref of a stored body, since a journal event holds 16 KiB. Redacted content does
        not come back, so a body a person redacted is the ref it had, which reads as redacted: an ask the journal
        refuses, and the approval is answered `deny`, and anything else is recorded with its body redacted."""
        if body is None:
            return None
        data = body if isinstance(body, bytes) else body.encode(errors="replace")
        try:
            return f"sha256:{await self._kernel.put_body(data)}"
        except Refused as refused:
            if refused.refusal.code != "conflict":
                raise
            return f"sha256:{hashlib.sha256(data).hexdigest()}"

    async def _taken(self, link: DriverLink, report: Report, outcome: Outcome) -> None:
        """What comes of a report the journal refused: it is dropped. But an approval is answered `deny`, as a harness
        is blocked on it, and an ended agent's late word is no loss."""
        kernel, refusal = self._kernel, outcome.refusal
        if refusal is None or link.leaving:
            return
        if isinstance(report, ApprovalRequested):
            await link.driver.answer(report.id, "deny")
            return
        status = kernel.query(kernel.runtime, "agent.status", {"agent": link.agent}).result
        if refusal.code == "conflict" and status["state"] == "ended":
            return
        await self._drop(link, report, f"its {report.type} report was refused: {refusal.code}: {refusal.detail}")

    async def _drop(self, link: DriverLink, report: Report, why: str) -> None:
        """The evidence is gone, so a gap says so and the harness ends."""
        if not link.leaving:
            await self._unknown(link, report.type, why)
            await self._lose(link.agent, why)

    async def _ready(self, link: DriverLink, ready: Ready) -> None:
        """Commit what was declared with what was verified, so no driver can claim a level: levels come from the
        conformance result kept under the root for the harness's driver, read at every launch and resume, which is
        recorded only where it speaks for this harness, here. A model that is not the one pinned is refused here: the
        effective model must equal the requested one, and an unknown one stays unknown. A harness for an agent that has
        started before comes back to it, whether it reopened a session or began anew."""
        pinned = link.pinned
        if pinned is not None and ready.effective_model not in (None, pinned):
            link.refuse(f"it runs {ready.effective_model}, and {pinned} is pinned")
            return
        info, role = link.info, self._team.roles[link.role]
        profile = Profile(
            driver=info.name,
            implementation=implementation(link.driver),
            version=ready.version,
            login=link.login,
            tools=tool_visibility(ready.tools_visible, tuple(map(tool_name, link.held))),
            allow_native_children=role.allow_native_children,
        )
        kept = await asyncio.to_thread(read_conformance, root_of(self._folder), info.name)
        proof = kept if speaks_for(profile, kept) else None
        args = {
            "agent": link.agent,
            "ready": ready,
            "declared": info.capabilities,
            "verified": profile.model_dump(mode="json"),
            "conformance": None if proof is None else await self._stored(proof.model_dump_json()),
            "levels": levels(info.capabilities, profile, kept).model_dump(mode="json"),
            "assurance": self._workspace_of(link.agent).assurance,
            "resumed": self._kernel.query(self._kernel.runtime, "agent.status", {"agent": link.agent}).result["state"]
            != "spawning",
        }
        await self._taken(link, ready, await self.insist("agent.start", args))
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
        if link is None or link.leaving:
            return
        if link.ready.is_set():
            await self.insist("agent.report", {"agent": link.agent, "report": Exited(reason=reason)})
        else:
            link.refuse(reason)

    # Shutdown.

    def closing(self) -> None:
        """Start nothing new but interrupts, and take no harness's end from here on as an agent's. A turn interrupted
        from here on was the owner's doing, which a resume tells its agent."""
        self._closing = True
        for link in self._links.values():
            link.leaving = True

    async def close(self, grace: float) -> None:
        """End every process tree, whatever a driver does, and drop whatever was in flight. A dropped effect stays
        `started`, so the next runtime marks it uncertain, which is the truth. A launch cut short stays so too: a
        harness that never said it was ready has not started."""
        links = tuple(self._links.values())
        self._links.clear()

        async def ended(link: DriverLink) -> None:
            try:
                await self._end(link, grace)
            except Exception as error:
                log.error("%s did not stop: %s", link.agent, link.redact(f"{type(error).__name__}: {error}"))

        await asyncio.gather(*map(ended, links))
        acting = tuple(self._acting.values())
        for task in acting:
            task.cancel()
        await asyncio.gather(*acting, return_exceptions=True)
