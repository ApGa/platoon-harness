"""The terminal UI: the sessions screen, or one session's workspace."""

import os
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

from textual.app import App, SystemCommand
from textual.markup import escape
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Input, TextArea

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
    warning="#e0a46c",
    error="#f0717c",
    success="#5fcf7a",
    foreground="#d9dbe4",
    background="#14151b",
    surface="#191a22",
    panel="#262834",
    dark=True,
)
"""The default theme: dark ink with one accent, the logo's sky blue, state colours that stay legible on it, and for
warnings and what needs you a muted amber, which sits with the ink as a yellow does not."""
SETTINGS = {"theme": str, "motion": bool}
"""What `tui.toml` takes: `theme`, the name of a theme, and `motion`, which `false` turns off."""

CSS = """
Screen { layers: base overlay; }
#header { height: 1; background: $panel; padding: 0 1; }
#banner { height: auto; max-height: 2; padding: 0 1; display: none; }
#banner.-shown { display: block; }
#body { height: 1fr; }
#navigator { width: 34; border: round $panel; border-title-color: $foreground; padding: 0 1; }
#navigator:focus { border: round $accent; }
#edge { width: 1; pointer: ew-resize; }
#edge:hover, #edge.-dragged { background: $accent 50%; }
#focus { width: 1fr; border: round $panel; border-title-color: $foreground; border-subtitle-color: $accent; }
#focus:focus-within { border: round $accent; }
#transcript { height: 1fr; padding: 0 1 0 0; }
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
Workspace.narrow #navigator, Workspace.narrow #edge { display: none; }
Workspace.narrow.navigator-shown #navigator { display: block; layer: overlay; dock: left; height: 100%; }
Workspace.navigator-hidden #navigator, Workspace.navigator-hidden #edge { display: none; }
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
        self.motion = True
        """Whether the agents move, which `motion = false` in `tui.toml` turns off, as Textual's animation level can."""
        self.register_theme(INK)
        self.theme = INK.name

    def on_mount(self) -> None:
        self.push_screen(Workspace(self._session) if self._session else Sessions())
        self._take_settings()

    def _take_settings(self) -> None:
        """Take what `tui.toml` says, or keep the defaults, saying why: a file that cannot be read, holds a key it does
        not take or a value of another kind than its key's, or names no theme there is, is not taken."""
        path = settings()
        try:
            said = tomllib.loads(path.read_text())
        except FileNotFoundError:
            return
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            self._refuse(path, f"was not read: {error}")
            return
        for key, value in said.items():
            if key not in SETTINGS:
                self._refuse(path, f"holds {key!r}, which it does not take: it takes {' and '.join(SETTINGS)}")
                return
            if not isinstance(value, SETTINGS[key]):
                kind = "a theme's name" if key == "theme" else "true or false"
                self._refuse(path, f"gives {key} as {value!r}, which is not {kind}")
                return
        if "theme" in said and said["theme"] not in self.available_themes:
            known = ", ".join(sorted(self.available_themes))
            self._refuse(path, f"names the theme {said['theme']!r}, which is none of {known}")
            return
        self.theme = said.get("theme", self.theme)
        self.motion = said.get("motion", True)

    def _refuse(self, path: Path, why: str) -> None:
        said = f"{path} {why}, so it is not taken: the theme is {self.theme} and the agents move"
        note(self.screen, said, severity="warning")

    def action_theme(self) -> None:
        """Choose a theme for this run from a list of them, which says, once one is chosen, what keeps it."""
        self._choosing = True
        self.search_themes()

    def watch_theme(self, theme: str) -> None:
        if self._choosing:
            self._choosing = False
            note(self.screen, f'The theme is {theme} for this run: `theme = "{theme}"` in {settings()} keeps it.')

    def action_copy(self) -> None:
        """Copy, as OSC 52, which a terminal may put on the clipboard: what is selected in the field you type in, or
        else the text selected with the mouse, or with none, in a session, the chosen line of the transcript."""
        focused = self.focused
        if isinstance(focused, TextArea | Input) and focused.selected_text:
            focused.action_copy()
            return
        if selected := self.screen.get_selected_text():
            self.copy_to_clipboard(selected)
            said = f"Sent the {len(selected):,} characters selected as OSC 52: whether they reach your clipboard is "
            note(self.screen, said + "your terminal's.")
        elif isinstance(self.screen, Workspace):
            self.screen.copy_line()
        else:
            said = "Nothing is selected, so nothing is copied: drag over text with the mouse to select it."
            note(self.screen, said, severity="warning")

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
