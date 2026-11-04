"""The one keymap table. Bindings, typed commands, help, the footer, the palette and the guide's keymap are all made
from it."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from textual.binding import Binding, BindingType

Where = Literal[
    "everywhere",
    "sessions",
    "workspace",
    "parts",
    "panel",
    "transcript",
    "dock",
    "composer",
    "list",
    "provenance",
    "question",
    "dialog",
]

WHERE: dict[Where, str] = {
    "everywhere": "Everywhere",
    "sessions": "The sessions screen",
    "workspace": "A session, unless the part that has focus takes the key",
    "parts": "Between a session's parts",
    "panel": "The transcript, the dock or the navigator, once one has focus",
    "transcript": "The transcript, once it has focus",
    "dock": "The dock, once it has focus",
    "composer": "The composer",
    "list": "A list: the sessions, the navigator, the dock, the help, provenance",
    "provenance": "The provenance panel",
    "question": "A question",
    "dialog": "A form or the help",
}

TYPED: tuple[Where, ...] = ("everywhere", "workspace")
"""Where the acts of a session are, each of which is typed in its composer as `/` and its name."""


@dataclass(frozen=True)
class Key:
    """One action: the keys that run it, where, its name and what it does, in a person's words. An act with no keys is
    reached by its typed command alone. `footer` keeps it on the footer, and `priority` runs it before the focused
    part's own keys. `planned` says why it is not built yet, which is what pressing it says. An action with no namespace
    runs on the place that binds it."""

    keys: str
    action: str
    name: str
    does: str
    where: Where
    footer: bool = False
    priority: bool = True
    planned: str = ""

    @property
    def runs(self) -> str:
        """What its binding runs: its action, or the screen saying why it is not built yet."""
        return f"screen.planned('{self.action}')" if self.planned else self.action

    @property
    def shown(self) -> str:
        """The first key, as a person reads it."""
        return _shown(self.keys.split(",")[0])

    @property
    def typed(self) -> str:
        """Its typed command, `/` and its name, or nothing for a key that is no act of a session."""
        return f"/{self.name}" if self.where in TYPED else ""

    @property
    def said(self) -> str:
        """What it does, and why it is not built yet when it is not."""
        return f"{self.does}. Not built yet: {self.planned}" if self.planned else self.does


_HELD = {"ctrl": "^", "alt": "Alt+", "shift": "Shift+"}
_NAMES = {
    "escape": "Esc",
    "pageup": "PgUp",
    "pagedown": "PgDn",
    "up": "↑",
    "down": "↓",
    "slash": "/",
    "question_mark": "?",
}


def _shown(pressed: str) -> str:
    """A key as a person reads it: `^D`, `Alt+A`, `Esc`, `PgUp`, and a character alone as it is typed, `n` or `/`."""
    *held, key = pressed.split("+")
    said = _NAMES.get(key, (key.upper() if held else key) if len(key) == 1 else key.capitalize())
    return "".join(_HELD[name] for name in held) + said


KEYMAP: tuple[Key, ...] = (
    Key("f1", "app.help", "help", "Show every key and typed command", "everywhere"),
    Key("ctrl+p", "app.command_palette", "palette", "Find a command, an op among them", "everywhere", footer=True),
    Key("ctrl+q", "app.leave", "quit", "Quit: a session you are in runs on", "everywhere"),
    Key("enter", "open", "open", "Open the session, live or as its history", "sessions", footer=True),
    Key("n", "new", "new", "Start a session from the project's team or a team file", "sessions", footer=True),
    Key(
        "r",
        "resume",
        "resume",
        "Resume a session whose runtime has gone, which can spend money",
        "sessions",
        footer=True,
    ),
    Key(
        "s",
        "stop",
        "stop",
        "Stop a session's runtime as its owner would, keeping it resumable",
        "sessions",
        footer=True,
    ),
    Key("l", "look", "look again", "Look again for sessions and how each stands", "sessions"),
    Key("question_mark", "app.help", "help", "Show every key and typed command", "sessions", footer=True),
    Key("p", "app.command_palette", "palette", "Find a command, an op among them", "sessions"),
    Key("q", "app.leave", "quit", "Quit: a session you are in runs on", "sessions", footer=True),
    Key(
        "escape",
        "interrupt",
        "interrupt",
        "Interrupt the agent in view: its turn stops, and it lives on",
        "workspace",
        footer=True,
        priority=False,
    ),
    Key("", "stop_below", "stop-below", "Stop the turns of the agent in view and of every agent below it", "workspace"),
    Key("alt+a", "next_place", "next-place", "Go to the next place you must act", "workspace", footer=True),
    Key("", "first_action", "yes", "Take the first action of where you are, such as Allow", "workspace"),
    Key("", "second_action", "no", "Take the second action of where you are, such as Deny", "workspace"),
    Key("alt+down", "next_row", "next", "Show the next agent or channel", "workspace"),
    Key("alt+up", "previous_row", "previous", "Show the previous agent or channel", "workspace"),
    Key("ctrl+b", "navigator", "navigator", "Show or hide the agents and channels", "workspace"),
    Key("f2", "inspector", "inspector", "Show or hide why the agent in view waits, and what it runs on", "workspace"),
    Key("ctrl+o", "open_line", "open-line", "Open or close the chosen line of the transcript", "workspace"),
    Key("pageup", "page_up", "page-up", "Scroll the transcript up", "workspace"),
    Key("pagedown", "page_down", "page-down", "Scroll the transcript down", "workspace"),
    Key("ctrl+home", "oldest", "oldest", "Go to the start of the transcript, read back from the journal", "workspace"),
    Key("ctrl+end", "follow", "follow", "Go to the newest line and follow what comes", "workspace"),
    Key("alt+f", "attach_file", "file", "Attach a file to the message, as its body", "workspace"),
    Key("", "resume", "resume", "Resume this session when it is history, which can spend money", "workspace"),
    Key(
        "ctrl+t",
        "tasks",
        "tasks",
        "Show the tasks and the board",
        "workspace",
        planned="the tasks and board views are planned: a queue's or a board's channel shows its lines",
    ),
    Key("alt+d", "review", "review", "List what changed: each workspace's commits and uncommitted paths", "workspace"),
    Key(
        "",
        "provenance",
        "provenance",
        "Show the chosen line's provenance: what it rests on, what came of it and whose work it reaches",
        "workspace",
    ),
    Key(
        "alt+m",
        "model",
        "model",
        "Switch the model of the agent in view",
        "workspace",
        planned="switching an agent's model is planned",
    ),
    Key(
        "alt+t",
        "take_over",
        "takeover",
        "Drive the agent in view in its own terminal",
        "workspace",
        planned="driving an agent's own terminal is planned: `agent takeover` holds its deliveries and no more",
    ),
    Key(
        "ctrl+d",
        "detach",
        "detach",
        "Detach on an empty composer: the session runs on",
        "workspace",
        footer=True,
        priority=False,
    ),
    Key(
        "tab",
        "app.focus_next",
        "next part",
        "Go to the next part: the navigator, the transcript, the dock, the composer, and round",
        "parts",
    ),
    Key("shift+tab", "app.focus_previous", "part before", "Go to the part before", "parts"),
    Key("escape", "screen.back", "back", "Go back to the composer, interrupting nothing", "panel", priority=False),
    Key("slash", "screen.command", "command", "Go back to the composer and begin a typed command there", "panel"),
    Key("up", "cursor_up", "line above", "Choose the line above", "transcript"),
    Key("down", "cursor_down", "line below", "Choose the line below", "transcript"),
    Key("enter", "open_line", "open-line", "Open or close the chosen line", "transcript"),
    Key("end", "follow", "follow", "Go to the newest line and follow what comes", "transcript"),
    Key("p", "screen.provenance", "provenance", "Show the chosen line's provenance", "transcript"),
    Key("y", "screen.first_action", "yes", "Take the first action of the chosen place, such as Allow", "dock"),
    Key("n", "screen.second_action", "no", "Take the second action of the chosen place, such as Deny", "dock"),
    Key(
        "enter",
        "send",
        "send",
        "Send to the target shown above it, which steers an agent at its next boundary, or run a typed command",
        "composer",
    ),
    Key("shift+enter,alt+enter,ctrl+j", "newline", "new line", "Start a new line", "composer"),
    Key("up", "older", "older", "On the first line, what you sent or ran before", "composer"),
    Key("down", "newer", "newer", "On the last line, what you sent or ran after", "composer"),
    Key("up", "cursor_up", "row above", "Choose the row above, or scroll up the help", "list", priority=False),
    Key("down", "cursor_down", "row below", "Choose the row below, or scroll down the help", "list", priority=False),
    Key("enter", "choose", "open", "Open the chosen row, or show the chosen place", "list", priority=False),
    Key("escape", "back", "back", "Go back one hop, and from the first, leave", "provenance", priority=False),
    Key("y", "yes", "yes", "Say yes", "question", priority=False),
    Key("n,escape", "no", "no", "Say no", "question", priority=False),
    Key("escape", "leave", "leave", "Leave it, and a form sends nothing", "dialog", priority=False),
)


def keys(where: Where) -> tuple[Key, ...]:
    return tuple(key for key in KEYMAP if key.where == where)


def bindings(where: Where) -> list[BindingType]:
    """The bindings of one place, from the table."""
    return [Binding(key.keys, key.runs, key.name, show=False, priority=key.priority) for key in keys(where) if key.keys]


def action_of(where: Where, pressed: str) -> str | None:
    """The action a key runs in one place, for a widget that reads its own keys."""
    return next((key.action for key in keys(where) if pressed in key.keys.split(",")), None)


def command(line: str) -> Key | None:
    """The act a line from the composer runs: `/` and an act's name, and `/` alone, which is the help. Anything else is
    no command."""
    said = line.strip()
    said = "/help" if said == "/" else said
    return next((key for key in KEYMAP if key.typed and key.typed == said), None)


def reach(action: str) -> str:
    """How a person reaches an act of a session, in words: any key, then its typed command, which every terminal
    delivers."""
    key = next(key for key in KEYMAP if key.action == action and key.typed)
    return f"{key.shown} or {key.typed}" if key.keys else key.typed


def reference() -> str:
    """The keymap as Markdown, for the guide: each key as the screen shows it, and each act of a session with its typed
    command beside any key."""
    sections = []
    for where, title in WHERE.items():
        typed = where in TYPED
        lines = ["| Keys | Typed | Does |\n|---|---|---|" if typed else "| Keys | Does |\n|---|---|"]
        for key in keys(where):
            pressed = " or ".join(f"`{_shown(one)}`" for one in key.keys.split(",") if one)
            cells = [pressed, f"`{key.typed}`", key.said] if typed else [pressed, key.said]
            lines.append(f"| {' | '.join(cells)} |")
        sections.append(f"### {title}\n\n" + "\n".join(lines))
    return "\n\n".join(sections)


BEGIN = "<!-- keymap: made from the keymap table by `uv run python -m platoon_harness_cli.tui.keymap docs/tui.md` -->"
END = "<!-- end of keymap -->"


def regenerate(guide: str) -> str:
    """The guide with its keymap section made again from the table."""
    before, _, rest = guide.partition(BEGIN)
    _, _, after = rest.partition(END)
    return f"{before}{BEGIN}\n\n{reference()}\n\n{END}{after}"


if __name__ == "__main__":
    path = Path(sys.argv[1])
    path.write_text(regenerate(path.read_text()))
