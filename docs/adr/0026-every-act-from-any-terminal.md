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
  help, the footer, the palette and the guide's keymap. `/` alone lists them, and the footer always begins `/ commands`. Anything else
  that begins with `/` is still asked about before it goes as a message.
- **No chord decides or stops.** A terminal sends Alt and a letter as Esc then that letter, and Textual reads the two as the chord when
  they come within its escape delay, so Esc then a word typed at once ran Alt+Y, Alt+N or Alt+S. `/yes`, `/no` and `/stop-below` have
  no key.
- **Plain-key focus.** Tab goes from the composer to the transcript, the dock and the navigator, and Shift+Tab the other way. In the
  dock the arrows choose a place, Enter goes to it, and `y` and `n` take its two actions with the version they were drawn from.
- **The dock takes focus only from the person**, by Tab or a click, and is two keys from the composer either way. A dock with nothing
  left to act on gives focus back.
- **Esc in the composer interrupts the agent in view, and from any other part goes back to the composer**, interrupting nothing.
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
| Keeping Alt+Y, Alt+N and Alt+S as shortcuts | A terminal cannot tell them from Esc then a letter, so leaving a part and typing at once would answer a place or stop turns |
| Tab in screen order, which puts the dock next to the composer | Shift+Tab is a habit from other agent TUIs, and a stray one followed by a message beginning with `n` would deny a place |
| Enter taking the dock's first action | A confirmation takes only `y`, so a key pressed for something else never says yes, and Enter in a list opens the row |
| Esc interrupting from every part | A person pressing Esc to leave a panel would interrupt an agent by surprise |

## Consequences

- ADR 0015's "approvals never take focus" now reads: never on their own.
- `/` begins a typed command in the composer and is search, not built yet, from the other parts.
- A typed command is kept in the composer's history beside what was sent.
- A new line in the composer still takes Shift+Enter, Alt+Enter, Ctrl+J or a paste. It edits a message and runs no act.
- Nothing was measured on a Mac or in Cursor. The tests drive the whole flow with plain keys through Pilot, and quit through a real
  terminal by typing `/quit`.

## Evidence

- The owner's report, and [tui-expectations.md](../research/tui-expectations.md) section 2 on terminal limits.
- [tui.md](../tui.md), "Every act from any terminal" and "Terminals that keep keys". [Architecture section 12](../architecture.md).
