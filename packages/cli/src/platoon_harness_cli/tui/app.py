"""The terminal UI: the sessions screen, or one session's workspace."""

from collections.abc import Iterable

from textual.app import App, SystemCommand
from textual.markup import escape
from textual.screen import Screen

from .dialogs import Help
from .keymap import bindings
from .sessions import Sessions
from .workspace import Workspace

CSS = """
Screen { layers: base overlay; }
#header { height: 1; background: $panel; padding: 0 1; }
#banner { height: auto; max-height: 2; padding: 0 1; display: none; }
#banner.-shown { display: block; }
#body { height: 1fr; }
#navigator { width: 32; border-right: solid $panel; }
#focus { width: 1fr; }
#title { height: 1; padding: 0 1; background: $boost; }
#transcript { height: 1fr; }
#behind { height: 1; display: none; }
#behind.-shown { display: block; }
#inspector { width: 40; display: none; padding: 0 1; border-left: solid $panel; }
Workspace.medium #inspector { layer: overlay; dock: right; height: 100%; background: $surface; }
#strip { height: 1; display: none; padding: 0 1; }
#dock { height: auto; max-height: 4; background: $warning 10%; display: none; }
#dock.-shown { display: block; }
#navigator:focus, #dock:focus { background-tint: $foreground 6%; }
#chip { height: 1; padding: 0 1; }
#composer { height: auto; min-height: 3; max-height: 10; border-top: solid $panel; }
#footer { height: 1; background: $panel; padding: 0 1; }
#sessions { height: 1fr; }
#said { height: auto; padding: 0 1; }
Workspace.inspector-shown #inspector { display: block; }
Workspace.narrow #navigator { display: none; }
Workspace.narrow.navigator-shown #navigator { display: block; layer: overlay; dock: left; height: 100%; }
Workspace.navigator-hidden #navigator { display: none; }
Workspace.narrow #strip { display: block; }
Workspace.short #dock, Workspace.short #banner, Workspace.short #title, Workspace.short #strip { display: none; }
Workspace.short #composer { max-height: 3; }
.dialog { width: 72; height: auto; max-height: 90%; border: thick $accent; background: $surface; padding: 1 2; }
.dialog.wide { width: 96; max-width: 100%; height: 90%; }
.dialog .about { margin-top: 1; color: $text-muted; }
ModalScreen { align: center middle; }
#help { height: 1fr; }
"""


class TerminalUI(App[str | None], inherit_bindings=False):
    """`platoon-harness` on a terminal. It returns the name of the session it left running, if any."""

    CSS = CSS
    BINDINGS = bindings("everywhere")
    TITLE = "platoon-harness"

    def __init__(self, session: str | None = None) -> None:
        super().__init__()
        self._session = session

    def on_mount(self) -> None:
        self.push_screen(Workspace(self._session) if self._session else Sessions())

    def action_help(self) -> None:
        """Show every key, or leave the help when it is what shows."""
        if isinstance(self.screen, Help):
            self.screen.dismiss(None)
        else:
            self.push_screen(Help())

    def action_leave(self) -> None:
        """Leave the app, saying which session runs on, if one does."""
        workspace = next((screen for screen in reversed(self.screen_stack) if isinstance(screen, Workspace)), None)
        self.exit(workspace.left() if workspace is not None else None)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """The palette: the keys of the screen it was opened on, then, in a session, the ops a person may run."""
        if isinstance(screen, Workspace | Sessions):
            for title, help, run in screen.commands():
                yield SystemCommand(title, escape(help), run)
