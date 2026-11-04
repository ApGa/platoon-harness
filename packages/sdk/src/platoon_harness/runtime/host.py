"""The host: what the journal asks of the world, one task per effect, and each harness heard in order."""

import asyncio
import contextlib
import json
import logging
import shutil
import socket
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any
from uuid import uuid4

from platoon_harness.config import Secret
from platoon_harness.drivers import (
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
    Item,
    Offered,
    Ready,
    Reconciled,
    Report,
    ToolBinding,
    TurnEnded,
    unknown_frame,
)
from platoon_harness.drivers.env import Held, Redactor, secrets_of
from platoon_harness.drivers.levels import Profile, levels, tool_visibility
from platoon_harness.drivers.process import reap
from platoon_harness.kernel import Effect, Kernel, Outcome, Refused, first, hash_token, tool_name
from platoon_harness.primitives import CUT_OFF, OWNER_STOP, Repo, Workspace
from platoon_harness.schema import ConfigError, Problem
from platoon_harness.team import Team
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
from .git import GitError
from .looks import PAGE, look, tips_of
from .opening import PLAN_LOGIN_FIX, make_driver
from .paths import agent_folder
from .workspaces import branch_of, end_snapshot, end_worktree, make_snapshot, make_worktree, present, write_bundle

GRACE = 5.0

_READY_SECONDS = 60.0
_HANDOVER_SECONDS = 60.0
_RECONCILE_SECONDS = 10.0
_RETRY_SECONDS = 1.0
_RENEW_EVERY = 5.0
_GOAL_BODY_LIMIT = 16 * 1024 * 1024

log = logging.getLogger("platoon_harness.runtime")

__all__ = ["GRACE", "DriverLink", "Host"]


def _ends_live_text(report: Report) -> bool:
    """Whether what a harness said live is now in the journal, as an item, or gone with its turn."""
    return isinstance(report, TurnEnded) or (isinstance(report, Item) and report.kind in ("message", "thought"))


class DriverLink:
    """One harness as the host holds it. Links live on the `Host` and not in the daemon, so a restarted daemon loses
    none. `leaving` means its end is our doing. `ready` is set once `agent.start` commits, or nobody needs it to, or
    `refused` says why it never will. `handing` is set to drop a handover under way."""

    def __init__(self, agent: str, role: str, driver: Driver, info: DriverInfo) -> None:
        self.agent = agent
        self.role = role
        self.driver = driver
        self.info = info
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
    ) -> None:
        self._kernel = kernel
        self._tools = tools
        self._team = team
        self._authority = authority
        self._folder = folder
        self._cwd = cwd
        self._plan_login = plan_login
        self._links: dict[str, DriverLink] = {}
        self._acting: dict[int, asyncio.Task[None]] = {}
        self._admitted: dict[str, Admission] = {}
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
        one before its effect has finished. A mode that cannot be given fails loudly and never degrades."""
        mode, agent, repo = effect.data["workspace"], effect.data["agent"], self._repo()
        folder, branch = agent_folder(self._folder, agent), branch_of(self._folder.name, agent)
        if mode == "shared":
            host = socket.gethostname()
            repository = None if repo is None else repo.repository
            made = Workspace(mode="shared", path=str(self._cwd), host=host, repository=repository)
        elif mode not in ("worktree", "snapshot"):
            raise DriverError(f"workspace `{mode}` is not available yet: use `shared`, `worktree` or `snapshot`")
        elif repo is None:
            raise GitError(f"`{mode}` needs a git work tree, and {self._cwd} was in none when the session opened")
        elif mode == "worktree":
            made = await asyncio.to_thread(make_worktree, repo, folder, branch, effect.id)
        else:
            made_for = f"{self._folder.name}/{agent}"
            made = await asyncio.to_thread(make_snapshot, repo, folder, branch, self._tips_at_open(repo), made_for)
        return made.model_dump()

    def _tips_at_open(self, repo: Repo) -> list[str]:
        """The commits every ref named when the session opened, read from the journal once."""
        if self._tips is None:
            self._tips = tips_of(self._kernel.get_body(repo.tips.removeprefix("sha256:")).decode())
        return self._tips

    def _goal(self, data: Mapping[str, Any]) -> str:
        body = data["body"]
        if body is None:
            return data["goal"]
        text = self._kernel.get_body(body.removeprefix("sha256:"), limit=_GOAL_BODY_LIMIT)
        return "\n\n".join(filter(None, (data["goal"], text.decode(errors="replace"))))

    async def _launch(self, effect: Effect) -> None:
        data = effect.data
        agent, role = data["agent"], data["role"]
        if not self._plan_login and await self._on_plan(role) and (others := await self._live_on_plans(agent)):
            raise DriverError(f"{agent} would join {', '.join(others)} headless on one plan login: {PLAN_LOGIN_FIX}")
        admission = self._admitted.pop(agent, None)
        if admission is None:  # It finished in a runtime that has gone, and what it gave went too.
            admission = await self.admit(SpawnRequest(agent=agent, role=role, resumed=True))
        await self.connect(agent, role, admission, goal=self._goal(data))

    async def connect(
        self, agent: str, role: str, admission: Admission, *, goal: str = "", resume: str | None = None
    ) -> None:
        """Bring a harness up on its own binding. A harness that never says it is ready is a failure, not a hang."""
        info = await self.describe(role)
        workspace = self._workspace_of(agent)
        await asyncio.to_thread(present, workspace)
        driver = await asyncio.to_thread(make_driver, self._team.roles[role], self._cwd)
        link = DriverLink(agent, role, driver, info)
        self._links[agent] = link
        spec = self._spec(link, admission, goal, resume, Path(workspace.path))
        link.redact = Redactor(secrets_of(spec))
        link.live = Held(link.redact)

        async def up() -> None:
            await self._instructed(agent, spec.instructions)
            await driver.start(spec, partial(self._heard, link))
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

    async def _instructed(self, agent: str, text: str | None) -> None:
        """Journal what a harness is told, as the body it is, before it hears it."""
        args = {"agent": agent, "instructions": await self._stored(text)}
        if (recorded := await self.insist("agent.instruct", args)).refusal is not None:
            raise DriverError(f"what {agent} is told could not be journaled: {recorded.refusal.detail}")

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

    async def _on_plan(self, role: str) -> bool:
        """Whether a role's agents run on a plan login: its harness says so now, and the role names no auth profile. A
        driver that cannot say runs nothing."""
        if self._team.roles[role].auth is not None:
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
            if record["state"] != "ended" and record["name"] != besides and await self._on_plan(record["role"])
        ]

    def _spec(self, link: DriverLink, admission: Admission, goal: str, resume: str | None, cwd: Path) -> AgentSpec:
        """How an agent starts, in `cwd`, where its workspace is. Its instructions are the preamble and then the role's
        words, so a role has the last. A harness that reopens its own session keeps what it was told when that began,
        so it is handed that again."""
        role = self._team.roles[link.role]
        folder = agent_folder(self._folder, link.agent)
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
            goal=goal,
            cwd=cwd,
            folder=folder,
            model=role.model,
            effort=role.effort,
            sandbox=role.sandbox,
            allow_native_children=role.allow_native_children,
            tools=binding,
            access=admission.access,
            instructions=told,
            resume=resume,
        )

    def _told(self, agent: str) -> str | None:
        """What an agent's harness was told last, which `agent.instruct` journaled."""
        kernel = self._kernel
        body = kernel.query(kernel.runtime, "agent.records", {"agent": agent}).result[0]["instructions"]
        return None if body is None else kernel.get_body(body.removeprefix("sha256:")).decode()

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

    async def _deliver(self, effect: Effect) -> None:
        """Hand entries over, and for a wake stay open until its turn begins, so `waking` always has an effect behind it
        and a crash cannot strand one. Past a time, or at an interrupt, the handover fails, which queues it again."""
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
        workspace first, so that a worker whose base holds its new commits finds them recorded. A workspace a look
        cannot read records the gap `workspace_unobserved` and no change. Nothing is looked at outside a repository."""
        if (repo := self._repo()) is None:
            return
        kernel = self._kernel
        async with self._looking:
            readings = kernel.query(kernel.runtime, "repo.looks", {}).result
            makers = {"shared": Path(repo.top)}
            for record in kernel.query(kernel.runtime, "agent.records", {}).result:
                workspace = record["workspace"]
                if workspace and workspace["mode"] != "shared" and not record["removed"]:
                    makers[f"@{record['name']}"] = self._root(f"@{record['name']}")
            shared = any(role.workspace == "shared" for role in self._team.roles.values())
            for where in places:
                base = repo.head if where == "shared" else self._workspace_of(agent).base
                try:
                    seen = await asyncio.to_thread(
                        look,
                        self._root(where),
                        base=base,
                        tips=self._tips_at_open(repo),
                        last=readings.get(where),
                        makers={name: root for name, root in makers.items() if root.is_dir()},
                        record=shared or where != "shared",
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

    async def _stop(self, effect: Effect) -> dict[str, Any]:
        """End what an ended agent left, look once more at what it left, then end its workspace, if nothing would go
        with it. With no link, a crash may have left it, and `reap` proves what is ours. A link stays until its harness
        has stopped, so a shutdown that cuts this short can still stop it. Each step is safe to repeat, so a repeat
        finishes what the last one began, and a workspace gone at a repeat, which an earlier attempt may have removed,
        is not looked for. The authority hears how the agent ended even when ending its workspace fails."""
        name, retried = effect.data["agent"], effect.attempts > 0
        folder = agent_folder(self._folder, name)
        link = self.link(name)
        if link is None:
            left = await reap(folder, GRACE)
        else:
            link.ready.set()
            left = await self._end(link, GRACE)
            self._links.pop(name, None)
        record = self._kernel.query(self._kernel.runtime, "agent.records", {"agent": name}).result[0]
        ended: dict[str, Any] = {"removed": False, "kept": None}
        try:
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
                    ended = await asyncio.to_thread(end_snapshot, workspace, folder, top, left, retried=retried)
        finally:
            outcome = AgentOutcome(status=record["status"])
            await self._authority.finish(AgentRef(agent=name, role=record["role"]), outcome)
        return ended

    async def bundle(self) -> dict[str, Any] | None:
        """Keep the commits the journal recorded in a bundle in the session folder, or None when it recorded none, as
        git may prune one an agent rewrote."""
        kernel, repo = self._kernel, self._repo()
        commits, after = [], 0
        while repo is not None:
            page = kernel.read(kernel.runtime, after=after, match="repo/*")
            commits += [event.data["sha"] for event in page.events if event.type == "repo.committed"]
            if (after := page.cursor) >= page.head:
                break
        if repo is None or not commits:
            return None
        records = kernel.query(kernel.runtime, "agent.records", {}).result
        repositories = {record["workspace"]["repository"] for record in records if record["workspace"]} - {None}
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
                link.refuse(reason)  # Nobody has heard of this harness, so `connect` fails, which says so.
                return
            case TurnEnded(reason=reason) if reason in CUT_OFF:
                await self._unknown(link, report.type, f"a turn ended `{reason}`, which only the runtime can say")
                report = TurnEnded(reason="unknown")
            case TurnEnded(reason="interrupted") if self._closing:
                report = TurnEnded(reason=OWNER_STOP)
            case Item(body=body):
                report = report.model_copy(update={"body": await self._stored(body)})
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

    async def _stored(self, text: str | None) -> str | None:
        """Text from a report as the ref of a stored body, since a journal event holds 16 KiB."""
        return None if text is None else f"sha256:{await self._kernel.put_body(text.encode(errors='replace'))}"

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
        """Commit what was declared with what was verified, so no driver can claim a level. A model that is not the one
        pinned is refused here: the effective model must equal the requested one, and an unknown one stays unknown. A
        harness for an agent that has started before comes back to it, whether it reopened a session or began anew."""
        pinned = self._team.roles[link.role].model
        if pinned is not None and ready.effective_model not in (None, pinned):
            link.refuse(f"it runs {ready.effective_model}, and its role pins {pinned}")
            return
        info, role = link.info, self._team.roles[link.role]
        profile = Profile(
            driver=info.name,
            version=ready.version,
            login="key" if role.auth else info.login,
            tools=tool_visibility(ready.tools_visible, tuple(map(tool_name, link.held))),
            allow_native_children=role.allow_native_children,
        )
        args = {
            "agent": link.agent,
            "ready": ready,
            "declared": info.capabilities,
            "verified": profile.model_dump(mode="json"),
            "levels": levels(info.capabilities, profile, None).model_dump(mode="json"),
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
