"""The sessions screen: every session under the root and how each stands, and opening, starting, resuming, stopping or
replaying one, and with no team here, writing one, and editing the project's team."""

import asyncio
from functools import partial
from pathlib import Path
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.content import Content
from textual.screen import Screen
from textual.widgets import Static

from platoon_harness import ConfigError, Refused, Session
from platoon_harness.config import PROJECT_FILE
from platoon_harness.runtime.paths import find_root, listing
from platoon_harness.version import __version__

from ..machine import Starter, finding
from ..sessions import ask_to_stop
from ..teams import Source
from . import logo
from .dialogs import Confirm, Form, Keys
from .editor import TeamEditor, shortened
from .keymap import bindings, footer, keys
from .rows import Row, Rows
from .safe import SafeText, note
from .workspace import Workspace


class Sessions(Screen[None]):
    """Every session, from its folder: whether a runtime holds it and its state. It works with none. Nothing is typed
    here, so each act has a plain key."""

    BINDINGS = bindings("sessions")

    def __init__(self) -> None:
        super().__init__()
        self.found: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Static(id="brand")
        yield Rows(id="sessions")
        yield Static(id="said")
        yield Keys(id="footer")

    def on_mount(self) -> None:
        self.query_one(Rows).focus()
        self.query_one(Rows).border_title = Content("sessions")
        self.query_one("#footer", Static).update(footer("sessions"))
        self.app.theme_changed_signal.subscribe(self, lambda _: self._brand())
        self.action_look()
        if not Path(PROJECT_FILE).exists(follow_symlinks=False):
            self.offer_team()

    def on_resize(self) -> None:
        self._brand()

    def _brand(self) -> None:
        """The logo's agents beside the wordmark and where the sessions are, each line cut at the edge rather than
        wrapped, so that the logo is never torn. It stands still, as this screen reads no agent's state."""
        shown = shortened(find_root())
        said = [
            Content.assemble(("platoon-harness", "bold"), (f" {__version__}", "dim")),
            Content.styled("the agent harnesses you already use, as one team", "dim"),
            Content(""),
            SafeText(f"sessions under {shown}", "dim"),
        ]
        art = logo.sprite(logo.SMALL, logo.ANSI if self.app.current_theme.ansi else logo.TRUECOLOUR)
        lines = [Content.assemble(cells, "   ", words) for cells, words in zip(art, said, strict=True)]
        width = self.size.width - 4
        self.query_one("#brand", Static).update(Content("\n").join(line.truncate(width) for line in lines))

    def on_screen_resume(self) -> None:
        self.action_look()

    @work(exclusive=True, group="look")
    async def action_look(self) -> None:
        root = find_root()
        self._brand()
        found: dict[str, dict[str, Any]] = {}
        for listed in await asyncio.to_thread(listing, root):
            state = None
            try:
                async with Session.attach(listed.name, view=True) as attached:
                    state = (await attached.status())["state"]
            except Refused as refused:
                state = f"unknown: {refused}"
            found[listed.name] = {"live": listed.live, "state": state}
        self.found = found
        rows = [
            Row(
                Content.assemble(
                    SafeText(f"{name:<32} ", "bold"),
                    ("● live    " if row["live"] else "○ history ", "$success" if row["live"] else "dim"),
                    SafeText(row["state"] or "unknown"),
                ),
                name,
            )
            for name, row in found.items()
        ]
        self.query_one(Rows).show(rows)
        team = PROJECT_FILE if Path(PROJECT_FILE).exists() else "a team file"
        empty = Content.styled(f"No sessions yet. n starts one from {team}.", "dim")
        self.query_one("#said", Static).update(Content("") if rows else empty)

    @work(group="act")
    async def offer_team(self) -> None:
        """Offer once, as the screen opens with nothing where the project's team goes, to write one from the harnesses
        on PATH, as `init` does, over nothing and through no link. With none on PATH, say so."""
        here = Path.cwd()
        try:
            starter = await asyncio.to_thread(Starter.on_path)
        except ConfigError as error:
            what = "; ".join(problem.what for problem in error.problems)
            note(self, f"No team is in {here}, and none can be written there: {what}", severity="warning")
            return
        question = f"No team is in {here}. Write {PROJECT_FILE} there from the harnesses on PATH: {starter.said}?"
        if not await self.app.push_screen_wait(Confirm(SafeText(question))):
            return
        try:
            await asyncio.to_thread(starter.write)
        except FileExistsError:
            said = f"Nothing was written, as something is at {PROJECT_FILE} now: a team is written over nothing, "
            note(self, said + "nor through a link", severity="warning")
            return
        note(self, f"Wrote {PROJECT_FILE}: {starter.said}. n starts a session from it.")
        self.action_look()

    def _chosen(self) -> str | None:
        return self.query_one(Rows).cursor

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        self.app.push_screen(Workspace(chosen.key))

    def action_open(self) -> None:
        if (name := self._chosen()) is not None:
            self.app.push_screen(Workspace(name))

    @work(group="act")
    async def action_edit(self) -> None:
        """Edit the project's team where the terminal runs, and start a session as `n` does once the editor says to,
        having saved its changes."""
        if await self.app.push_screen_wait(TeamEditor()):
            self.action_new()

    @work(group="act")
    async def action_new(self) -> None:
        """Start a session as the TUI does: a detached runtime, which outlives the TUI, with the TUI as its guest. A
        harness that cannot start then says what `doctor` finds of it."""
        team = PROJECT_FILE if Path(PROJECT_FILE).exists() else ""
        fields = [
            ("team", SafeText("A team file. Left empty, the project's own."), team),
            ("name", SafeText("A name. Left empty, one is made from the time."), ""),
            (
                "trust",
                SafeText("yes, to run what the team file names to run: a command, a module or an auth profile."),
                "",
            ),
        ]
        given = await self.app.push_screen_wait(Form(Content.styled("Start a session", "bold"), fields))
        if given is None:
            return
        plan_login = False
        while True:
            try:
                source = Source(trust=given.get("trust", "").lower() in ("y", "yes"))
                loaded = await asyncio.to_thread(source.load, Path(given["team"]) if "team" in given else None)
                session = await Session.start(
                    loaded, name=given.get("name"), detach=True, cwd=Path.cwd(), plan_login=plan_login
                )
            except ConfigError as error:
                if not plan_login and [problem.where for problem in error.problems] == ["plan_login"]:
                    question = SafeText(f"{error.problems[0].what.partition(':')[0]}. Is this your own work?")
                    if await self.app.push_screen_wait(Confirm(question)):
                        plan_login = True
                        continue
                    return
                note(self, "\n".join(map(str, error.problems)), severity="error")
                return
            except Refused as refused:
                note(self, str(refused), severity="error")
                return
            break
        self.app.push_screen(Workspace(session.name, session))
        await self._say_what_doctor_finds(session.name)

    async def _say_what_doctor_finds(self, name: str) -> None:
        """Follow a session just started until each agent it started with has launched or failed to, and say what
        `doctor` finds of the harness of each that failed, where doctor looks for a harness of that name."""
        harnesses: dict[str | None, Any] = {}
        launching: set[str | None] = set()
        try:
            async with Session.attach(name, view=True) as attached:
                head = await attached.head()
                async for event in attached.events(0, follow=True):
                    match event.type, event.data.get("kind"):
                        case "agent.spawned", _:
                            harnesses[event.data["name"]] = event.data["harness"]
                        case "effect.requested", "launch":
                            launching.add(event.agent)
                        case "effect.failed", "launch":
                            launching.discard(event.agent)
                            await self._say_what_doctor_finds_of(event.agent, harnesses.get(event.agent))
                        case "effect.finished" | "effect.cancelled", "launch":
                            launching.discard(event.agent)
                    if event.seq >= head and not launching:
                        return
        except Refused:
            return  # Its runtime went, which the workspace says.

    async def _say_what_doctor_finds_of(self, agent: str | None, harness: Any) -> None:
        """Say what `doctor` finds of an agent's harness that could not start, run in this terminal, whose environment
        the runtime it started has, so on the PATH the harness was looked for on. A harness a command names is none it
        looks for."""
        found = await asyncio.to_thread(finding, harness) if isinstance(harness, str) else None
        if found is not None:
            note(self, f"@{agent} could not start, and doctor, run here, finds {harness} {found}", severity="error")

    @work(group="act")
    async def action_resume(self) -> None:
        name = self._chosen()
        if name is None:
            return
        if self.found.get(name, {}).get("live"):
            note(self, f"A runtime holds {name} already: Enter opens it.")
            return
        question = SafeText(f"Resume {name}? Its harnesses come back, which can spend money.")
        if not await self.app.push_screen_wait(Confirm(question)):
            return
        try:
            session = await Session.resume(name, detach=True)
        except Refused as refused:
            note(self, str(refused), severity="error")
            return
        self.app.push_screen(Workspace(name, session))

    def action_replay(self) -> None:
        if (name := self._chosen()) is not None:
            self.app.push_screen(Workspace(name, replay=True))

    @work(group="act")
    async def action_stop(self) -> None:
        name = self._chosen()
        if name is None:
            return
        question = SafeText(f"Stop {name}? Its turns are interrupted and its harnesses end; it stays resumable.")
        if not await self.app.push_screen_wait(Confirm(question)):
            return
        try:
            async with Session.attach(name, view=True) as attached:
                await ask_to_stop(attached)
                async for _ in attached.events(await attached.head(), follow=True):
                    pass
        except Refused as refused:
            note(self, str(refused), severity="warning")
        else:
            note(self, f"Stopped {name}. r resumes it.")
        self.action_look()

    def commands(self) -> list[tuple[str, str, Any]]:
        return [(key.name.capitalize(), key.does, partial(self.run_action, key.runs)) for key in keys("sessions")]
