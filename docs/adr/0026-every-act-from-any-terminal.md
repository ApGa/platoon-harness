# 0026. Every act from any terminal

**Status:** Accepted, 2026-11-04

## Context

The owner, on a Mac in a Cursor window, found the TUI did not get its Ctrl keys: the editor took them. The terminal inside VS Code and
editors built on it hands a key bound to an editor command to the editor, and F1 opens the editor's own palette. On a Mac, Option
types a character unless the terminal sends it as Meta, so every Alt key in the keymap arrived as a letter such as `å`. Several acts
had a chord as their only key: going to the next place you must act, answering it, stopping the turns below an agent, opening the
palette, detaching and quitting. What every terminal delivers is printable characters, Enter, Esc, Tab, Shift+Tab, the arrows and
Backspace.

## Decision

- **A chord is a shortcut and never the only way.** Every act also takes only keys every terminal delivers.
- **Typed commands.** In the composer, a line that is exactly `/` and an act's name runs that act and goes to no agent. Each act of a
  session has one name, kept in the keymap table beside any key, so the table makes the typed commands as it makes the bindings, the
  help, the footer, the palette and the guide's keymap. `/` alone lists them, `/` from any other part begins one in the composer, and
  the footer always begins `/ commands`. Anything else that begins with `/` is still asked about before it goes as a message.
- **No chord decides, stops or spends.** A terminal sends Alt and a letter as Esc then that letter, and Textual reads the two as the
  chord when they come within its escape delay, so Esc then a word typed at once ran Alt+Y, Alt+N or Alt+S, and Esc then "ry" on
  history opened the question that resumes, which can spend money, for the y to answer. `/yes`, `/no`, `/stop-below` and `/resume`
  have no key.
- **Plain-key focus.** Tab and Shift+Tab go round the parts in the order they are on screen. In the dock the arrows choose a place,
  Enter goes to it, and `y` and `n` take its two actions with the version they were drawn from.
- **The dock takes focus only from Tab or Shift+Tab, with no place chosen**, and a character it does not take lets go of the place
  chosen, so its letters act only on a place chosen there with the arrows, and nothing typed for the composer answers one, Esc then a
  word at once included. A click chooses a place and gives no focus. A part hidden while it has focus, by a resize, `/navigator` or a
  dock left empty, gives focus back to the composer.
- **Esc in the composer interrupts the agent in view, and from any other part goes back to the composer**, interrupting nothing. The
  footer names Esc by what it does from the part with focus, and that part is marked.
- **Where nothing is typed, every act has a plain key**: on the sessions screen `?` is the help, `p` the palette, `l` looks again and
  `q` quits.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Other chords | No chord is known to reach the program in every terminal and editor, and Option is a character on a Mac by default |
| A leader key, as OpenCode's Ctrl+X | It is a chord too |
| Documenting terminal settings alone | A person on the defaults stays stuck. The guide names the settings as well |
| Bare letters in the workspace while the composer is empty | A letter would act or type depending on a state the person may not see |
| Aliases, such as `/allow` beside `/yes` | One name per act. The first and second actions are Allow and Deny for an approval but other words for other places |
| Keeping Alt+Y, Alt+N, Alt+S and Alt+R as shortcuts | A terminal cannot tell them from Esc then a letter, so leaving a part and typing at once would answer a place, stop turns or ask to resume |
| A Tab order that keeps the dock two keys from the composer | It held only while the navigator showed, and a second stray Tab still reached the dock. A dock that takes focus with no place chosen is safe from any order |
| A click focusing the dock | The next message typed would answer the place clicked to look at |
| Enter taking the dock's first action | A confirmation takes only `y`, so a key pressed for something else never says yes, and Enter in a list opens the row |
| Esc interrupting from every part | A person pressing Esc to leave a panel would interrupt an agent by surprise |
| `/` as search from the parts | The footer offers `/` for commands from every part, so it would do something else where focus is not on the composer |

## Consequences

- ADR 0015's "approvals never take focus" now reads: never on their own.
- `/` begins a typed command from every part of a session, and search in a transcript has no key until it is built.
- A resize moves focus only by hiding the part that has it.
- The dock reads its own letters, as the composer does, so a word typed at once is read in the order it came. As bindings, the
  App ran them as they arrived, before the dock had read the keys ahead of them.
- A typed command is kept in the composer's history beside what was sent.
- A new line in the composer still takes Shift+Enter, Alt+Enter, Ctrl+J or a paste. It edits a message and runs no act.
- Nothing was measured on a Mac or in Cursor. The tests drive the whole flow with plain keys through Pilot, and quit through a real
  terminal by typing `/quit`.

## Evidence

- The owner's report, and [tui-expectations.md](../research/tui-expectations.md) section 2 on terminal limits.
- [tui.md](../tui.md), "Every act from any terminal" and "Terminals that keep keys". [Architecture section 12](../architecture.md).
