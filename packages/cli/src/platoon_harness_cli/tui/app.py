"""The terminal UI: the sessions screen, or one session's workspace."""

import os
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

from textual.app import App, SystemCommand
from textual.markup import escape
from textual.screen import Screen
from textual.theme import Theme

from .dialogs import Help
from .keymap import bindings
from .safe import note
from .sessions import Sessions
from .workspace import Workspace

INK = Theme(
    name="platoon-ink",
    primary="#5cb8e6",
    secondary="#4ece60",
    accent="#5cb8e6",
    warning="#e8c35f",
    error="#f0717c",
    success="#5fcf7a",
    foreground="#d9dbe4",
    background="#14151b",
    surface="#191a22",
    panel="#262834",
    dark=True,
)
"""The default theme: dark ink with one accent, the logo's sky blue, and state colours that stay legible on it."""
THEME = "theme"
"""The key of `tui.toml` that names the theme."""

CSS = """
Screen { layers: base overlay; }
#header { height: 1; background: $panel; padding: 0 1; }
#banner { height: auto; max-height: 2; padding: 0 1; display: none; }
#banner.-shown { display: block; }
#body { height: 1fr; }
#navigator { width: 34; border: round $panel; border-title-color: $foreground; padding: 0 1; }
#navigator:focus { border: round $accent; }
#focus { width: 1fr; border: round $panel; border-title-color: $foreground; border-subtitle-color: $accent; }
#focus:focus-within { border: round $accent; }
#transcript { height: 1fr; padding: 0 1; }
#inspector { width: 42; display: none; padding: 0 1; border: round $panel; border-title-color: $foreground; }
Workspace.medium #inspector { layer: overlay; dock: right; height: 100%; background: $surface; }
#strip { height: 1; display: none; padding: 0 1; link-style: none; link-background-hover: $accent 30%; }
#dock { height: auto; max-height: 4; background: $warning 12%; border-left: outer $warning; display: none; }
#dock.-shown { display: block; }
#dock:focus { background: $warning 25%; }
#chip { height: 1; padding: 0 2; }
#composer { height: auto; min-height: 3; max-height: 10; border: round $panel; padding: 0 1; }
#composer:focus { border: round $accent; }
#footer { height: 1; background: $panel; padding: 0 1; }
#brand { height: auto; padding: 1 2; }
#sessions { height: 1fr; border: round $accent; border-title-color: $foreground; padding: 0 1; }
#said { height: auto; padding: 0 2; }
Workspace.inspector-shown #inspector { display: block; }
Workspace.narrow #navigator { display: none; }
Workspace.narrow.navigator-shown #navigator { display: block; layer: overlay; dock: left; height: 100%; }
Workspace.navigator-hidden #navigator { display: none; }
Workspace.narrow #strip { display: block; }
Workspace.short #dock, Workspace.short #banner, Workspace.short #strip { display: none; }
Workspace.short #focus, Workspace.short #navigator, Workspace.short #inspector, Workspace.short #composer {
    border: none;
}
Workspace.short #composer { max-height: 3; }
.dialog { width: 72; height: auto; max-height: 90%; border: round $accent; background: $surface; padding: 1 2; }
.dialog.wide { width: 96; max-width: 100%; height: 90%; }
.dialog .about { margin-top: 1; color: $text-muted; }
ModalScreen { align: center middle; }
#help { height: 1fr; }
#comment { height: auto; min-height: 3; max-height: 8; border: round $accent; }
"""


def settings(environ: Mapping[str, str] = os.environ) -> Path:
    """Where a person keeps the terminal UI's own settings: `tui.toml`, beside the user config a team loads."""
    return Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "platoon-harness" / "tui.toml"


class TerminalUI(App[str | None], inherit_bindings=False):
    """`platoon-harness` on a terminal. It returns the name of the session it left running, if any."""

    CSS = CSS
    BINDINGS = bindings("everywhere")
    TITLE = "platoon-harness"

    def __init__(self, session: str | None = None) -> None:
        super().__init__()
        self._session = session
        self._choosing = False
        self.register_theme(INK)
        self.theme = INK.name

    def on_mount(self) -> None:
        self.push_screen(Workspace(self._session) if self._session else Sessions())
        self._take_settings()

    def _take_settings(self) -> None:
        """Take the theme `tui.toml` names, or keep the default, saying why."""
        path = settings()
        try:
            named = tomllib.loads(path.read_text()).get(THEME)
        except FileNotFoundError:
            return
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            note(self.screen, f"{path} was not read, so the theme is {self.theme}: {error}", severity="warning")
            return
        if named is None:
            return
        if named not in self.available_themes:
            known = ", ".join(sorted(self.available_themes))
            said = f"{path} names the theme {named!r}, which is none of {known}, so the theme is {self.theme}"
            note(self.screen, said, severity="warning")
            return
        self.theme = named

    def action_theme(self) -> None:
        """Choose a theme for this run from a list of them, which says, once one is chosen, what keeps it."""
        self._choosing = True
        self.search_themes()

    def watch_theme(self, theme: str) -> None:
        if self._choosing:
            self._choosing = False
            note(self.screen, f'The theme is {theme} for this run: `{THEME} = "{theme}"` in {settings()} keeps it.')

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
