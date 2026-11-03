"""The sessions screen: every session under the root and how each stands, and opening, starting, resuming or stopping
one."""

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

from ..sessions import ask_to_stop
from ..teams import Source
from .dialogs import Confirm, Form
from .keymap import bindings, keys
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
        yield Static(id="header")
        yield Rows(id="sessions")
        yield Static(id="said")
        yield Static(id="footer")

    def on_mount(self) -> None:
        self.query_one(Rows).focus()
        footer = [part for key in keys("sessions") if key.footer for part in ((key.shown, "bold"), f" {key.name}  ")]
        self.query_one("#footer", Static).update(Content.assemble(*footer))
        self.action_look()

    def on_screen_resume(self) -> None:
        self.action_look()

    @work(exclusive=True, group="look")
    async def action_look(self) -> None:
        root = find_root()
        self.query_one("#header", Static).update(
            Content.assemble(("Sessions", "bold"), SafeText(f" under {root}", "dim"))
        )
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
                    ("live " if row["live"] else "—    ", "green" if row["live"] else "dim"),
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

    def _chosen(self) -> str | None:
        return self.query_one(Rows).cursor

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        self.app.push_screen(Workspace(chosen.key))

    def action_open(self) -> None:
        if (name := self._chosen()) is not None:
            self.app.push_screen(Workspace(name))

    @work(group="act")
    async def action_new(self) -> None:
        """Start a session as the TUI does: a detached runtime, which outlives the TUI, with the TUI as its guest."""
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
