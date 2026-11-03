"""The one keymap table. Bindings, help, the footer, the palette and the guide's keymap are all made from it."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from textual.binding import Binding, BindingType

Where = Literal["everywhere", "sessions", "workspace", "transcript", "composer"]

WHERE: dict[Where, str] = {
    "everywhere": "Everywhere",
    "sessions": "The sessions screen",
    "workspace": "A session, whatever has focus",
    "transcript": "The transcript, once it has focus",
    "composer": "The composer",
}


@dataclass(frozen=True)
class Key:
    """One action: the keys that run it, where, its name and what it does, in a person's words. `footer` keeps it on
    the footer, and `priority` runs it before the focused widget's own keys. `planned` says why it is not built yet,
    which is what pressing it says."""

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
        """The first key, as a person reads it: `^D`, `Alt+A`, `Esc`, `PgUp`."""
        *held, key = self.keys.split(",")[0].split("+")
        said = _NAMES.get(key, key.upper() if len(key) == 1 else key.capitalize())
        return "".join(_HELD[name] for name in held) + said


_HELD = {"ctrl": "^", "alt": "Alt+", "shift": "Shift+"}
_NAMES = {"escape": "Esc", "pageup": "PgUp", "pagedown": "PgDn", "up": "↑", "down": "↓", "slash": "/"}

KEYMAP: tuple[Key, ...] = (
    Key("f1", "help", "help", "Show every key", "everywhere", footer=True),
    Key("ctrl+p", "command_palette", "commands", "Find a command, an op among them", "everywhere", footer=True),
    Key("ctrl+q", "leave", "leave", "Leave: a session you are in runs on", "everywhere"),
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
    Key("ctrl+r", "look", "look again", "Look again for sessions and how each stands", "sessions"),
    Key(
        "escape",
        "interrupt",
        "interrupt",
        "Interrupt the agent in view: its turn stops, and it lives on",
        "workspace",
        footer=True,
    ),
    Key(
        "alt+s",
        "stop_below",
        "stop below",
        "Stop the turns of the agent in view and of every agent below it",
        "workspace",
    ),
    Key("alt+a", "next_needing_you", "next for you", "Go to the next place you must act", "workspace", footer=True),
    Key("alt+y", "first_action", "first action", "Take the first action of where you are, such as Allow", "workspace"),
    Key(
        "alt+n", "second_action", "second action", "Take the second action of where you are, such as Deny", "workspace"
    ),
    Key("alt+down", "next_row", "next", "Show the next agent or channel", "workspace"),
    Key("alt+up", "previous_row", "previous", "Show the previous agent or channel", "workspace"),
    Key("ctrl+b", "navigator", "navigator", "Show or hide the agents and channels", "workspace"),
    Key("f2", "inspector", "inspector", "Show or hide why the agent in view waits, and what it runs on", "workspace"),
    Key("ctrl+o", "open_line", "open line", "Open or close the chosen line of the transcript", "workspace"),
    Key("pageup", "page_up", "page up", "Scroll the transcript up", "workspace"),
    Key("pagedown", "page_down", "page down", "Scroll the transcript down", "workspace"),
    Key("ctrl+home", "oldest", "oldest", "Go to the start of the transcript, read back from the journal", "workspace"),
    Key("ctrl+end", "follow", "follow", "Go to the newest line and follow what comes", "workspace"),
    Key("alt+f", "attach_file", "attach", "Attach a file to the message, as its body", "workspace"),
    Key("alt+r", "resume", "resume", "Resume this session when it is history, which can spend money", "workspace"),
    Key(
        "ctrl+t",
        "tasks",
        "tasks",
        "Show the tasks and the board",
        "workspace",
        planned="the tasks and board views are planned: a queue's or a board's channel shows its lines",
    ),
    Key(
        "alt+d",
        "review",
        "review",
        "Review what changed, as diffs",
        "workspace",
        planned="the review screen is planned: what changed is measured once workspaces land",
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
        "take over",
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
    Key("up", "cursor_up", "line above", "Choose the line above", "transcript"),
    Key("down", "cursor_down", "line below", "Choose the line below", "transcript"),
    Key("enter", "open_line", "open line", "Open or close the chosen line", "transcript"),
    Key("end", "follow", "follow", "Go to the newest line and follow what comes", "transcript"),
    Key(
        "slash", "search", "search", "Search the transcript", "transcript", planned="search in a transcript is planned"
    ),
    Key(
        "enter",
        "send",
        "send",
        "Send to the target shown above it, which steers an agent at its next boundary",
        "composer",
    ),
    Key("shift+enter,alt+enter,ctrl+j", "newline", "new line", "Start a new line", "composer"),
    Key("up", "older", "older", "On the first line, the message you sent before", "composer"),
    Key("down", "newer", "newer", "On the last line, the message you sent after", "composer"),
)


def keys(where: Where) -> tuple[Key, ...]:
    return tuple(key for key in KEYMAP if key.where == where)


def bindings(where: Where) -> list[BindingType]:
    """The bindings of one place, from the table."""
    return [Binding(key.keys, key.runs, key.name, show=False, priority=key.priority) for key in keys(where)]


def action_of(where: Where, pressed: str) -> str | None:
    """The action a key runs in one place, for a widget that reads its own keys."""
    return next((key.action for key in keys(where) if pressed in key.keys.split(",")), None)


def _said(key: Key) -> str:
    return f"{key.does}. Not built yet: {key.planned}" if key.planned else key.does


def reference() -> str:
    """The keymap as Markdown, for the guide."""
    sections = []
    for where, title in WHERE.items():
        rows = "\n".join(
            f"| {' or '.join(f'`{k}`' for k in key.keys.split(','))} | {_said(key)} |" for key in keys(where)
        )
        sections.append(f"### {title}\n\n| Keys | Does |\n|---|---|\n{rows}")
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
