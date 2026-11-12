# The terminal UI

`platoon-harness` on a terminal opens the terminal UI, where you start, watch and steer sessions. It is a client like any
other: it submits ops and draws the views, holds no timer that decides anything, and computes no status.
[Run headless](headless.md) runs the same sessions with no terminal.

**Goal:** open a session in a terminal, see who is working and what needs you, answer it, steer an agent with a message,
and see what changed and where a line came from.

**Prerequisites:**

- platoon-harness installed as [Install](../getting-started/install.md) says;
- the harnesses you use on your PATH, signed in as you usually are, or a session to open, such as
  [your first session](../getting-started/first-session.md)'s.

## Open a session, and detach

```console
$ platoon-harness                 # the sessions screen
$ platoon-harness attach fix-auth # one session
```

A session started here gets a detached runtime of its own, the way tmux starts its server, and the UI is its guest:
`/detach`, or Ctrl+D, detaches and the session runs on, and `attach` comes back to it. With no terminal, `platoon-harness`
prints its help and `attach` exits 64, naming `events --follow`.

![The sessions screen: Platoon's agents beside the wordmark, and the mixed team's session, closed, as its history](../assets/tui-sessions.svg)

*The sessions screen on the mixed team's session as a live run on DeepSeek V4.1 Flash recorded it, at 100 columns by 28
rows.*

The sessions screen lists every session under the root, whether a runtime holds it and its state, and works with none.
Enter opens one: live, as a guest, or as read-only history when no runtime holds it, with `/resume` offered to resume it.
`n` starts a session from the project's `platoon-harness.toml` or a team file, asking once, where several agents would run
on your own plan login, whether this is your own work. `r` resumes a session whose runtime has gone, which can spend
money, and `s` stops one as its owner would, keeping it resumable, each after a question. `R` replays one, and `e` edits
the project's team, as [Edit a team](edit-a-team.md) shows. Where the folder you started in has no
`platoon-harness.toml`, it offers once to write one as `init` does, which only `y` takes, writing over nothing. An agent
whose harness cannot start fails, and the UI says what `doctor` finds of that harness: not on PATH, or its version, the
kind of its login and what its checks found.

## Every act from any terminal

A chord is a shortcut and never the only way: every act also takes keys every terminal delivers. In the composer, a line
that is exactly `/` and an act's name runs that act and goes to no agent, as `/next-place`, `/interrupt` or `/detach`;
`/` alone, or `/help`, lists them, and anything else that begins with `/` is asked about before it goes as a message.
Tab and Shift+Tab go round the parts in the order they are on screen: the navigator, the transcript, the dock and the
composer. Esc in the composer interrupts the agent in view, and from any other part goes back to the composer. No chord
decides, stops or spends anything: a terminal sends Alt and a letter as Esc then that letter, so Esc then a word typed at
once would run one, and so `/yes`, `/no`, `/stop-below` and `/resume` have no key.

## The workspace

![The workspace on the mixed team's closed session: the pi lead and the OpenHands worker it spawned in the navigator, the lead's transcript beside them, and the composer below](../assets/tui-wide.svg)

*The workspace on the mixed team's session as a live run on DeepSeek V4.1 Flash recorded it, at 120 columns by 32 rows: a pi lead
that spawned an OpenHands worker, read back as history.*

| Part | What it answers |
|---|---|
| Header | The session's name and how it stands, who is working, how many places need you, what is blocked or failed, what changed, and each limit with what is spent against it, `?` where nobody could say |
| Navigator | The agents grouped by what you must do, needs you, working, blocked, idle, done and failed, as a tree by parent, each with its glyph, state and harness and what it is on or waits for; then the channels, with your unread lines and mentions |
| Focus pane | One agent, one channel or one thread at a time, so live text is never merged |
| Inspector, `/inspector` | Why an agent waits, its harness, model, login kind and levels, its workspace and branch, what it spent, its gaps, and what the runtime refused you |
| Dock | Each place you must act, with its actions, such as Allow and Deny, Write to it, Reply, or Add it again |
| Composer | What you write, and above it whom it goes to and what waits for that agent |

Each agent's state has a glyph as well as a colour, so neither alone says it:

| Glyph | State |
|---|---|
| `◉` | needs you |
| `●` | working, which stirs while motion is on |
| `◌` | blocked |
| `○` | idle, which breathes while motion is on |
| `✓` | done |
| `✗` | failed |
| `⊘` | lost: the runtime lost it |
| `?` | unknown: a state this terminal does not know |

Your unread counts and the mentions you have read come from your marks in `marks.sqlite`, the one file the terminal writes
reading a session: moving them is no event, and acknowledges nothing an agent was handed.

| Size | Layout |
|---|---|
| 120 columns or more | Navigator, focus pane, and the inspector beside them |
| 80 to 119 | Navigator and focus pane, and the inspector over the focus pane |
| 60 to 79 | The focus pane, with the team as tabs at its top, the one in view filled with the accent, and the navigator over the focus pane on `/navigator`, until Esc or a row chosen in it closes it |
| under 60 | As 60 to 79, with the header shortened to the name and counts and the footer to `/ commands` and keys |
| under 16 rows | The dock, the banner, the tabs, the logo and the panels' borders give way, the composer keeps three rows, and while the transcript does not follow, a line under it says what came since and how to follow again |

A resize changes which parts show, and never the scroll position or the composer's target. The recorded session at
[120 by 32](../assets/tui-wide.svg), [90 by 28](../assets/tui-medium.svg), [70 by 24](../assets/tui-narrow.svg),
[52 by 20](../assets/tui-slim.svg) and [100 by 14](../assets/tui-short.svg), in columns by rows, shows each.

## Read the transcript

An agent's transcript shows what it said, and folds the rest away, in levels you open as you need them:

1. **A turn.** What the agent said, its messages and its report, stands whole, and all else it did in the turn is one
   quiet line that counts it, `▸ 5 tool calls · ✗ 1 failed · 3 thoughts · 1 spawn`.
2. **What it did.** That line opens on each step in its place: a call as its tool's name and its input in short, with
   `✗` where it failed and `? ended unknown` where nothing says how it ended, a thought, a patch, and each spawn under the
   call that made it.
3. **The whole of one.** A step opens on all of it: a call on its whole input and what it gave back, a thought on its
   text, an approval on what it asks.

Ended turns rest folded, and a turn under way shows its latest step, `running` where it has no end yet. Nothing a fold
holds is out of reach, and a fold never hides that something failed, waits on you or is unknown. That ended turns rest
folded, that a turn under way shows its latest step, that a turn's ordinary end draws no line, and these keys, are the
defaults pending the owner's ruling. Enter, Right and Left open and close the chosen line, and Ctrl+O, or `/folds`,
opens every fold.

Below the lines is what the agent in view is saying now, live, until the journal holds it. Reading up stops following,
and `/follow` follows again; `/oldest` reads from the journal's first line. Each ref a line's words name is underlined,
and a click on it shows that ref's provenance, as [See where a line came from](#see-where-a-line-came-from) says.

`/find`, or Ctrl+F, opens a form for words, and sending it chooses the line before the chosen one whose words hold
yours, whatever their case, opening folds and reading back a page at a time. A ref is opened through `/provenance`'s form,
not found. That `/find` finds words alone, with Ctrl+F its shortcut, is the default pending the owner's ruling.

A drag with the mouse selects text, and Ctrl+C, or `/copy`, copies it as plain text, without borders or glyphs from the
transcript; with nothing selected, it copies the chosen line. It is sent to the terminal as OSC 52, which a terminal may
put on its clipboard, or not, or not past a length of its own: no real terminal has been measured, nor tmux or SSH
between. Shift held as you drag selects as the terminal itself does. That `/copy` copies the chosen line, with nothing
selected, is the default pending the owner's ruling.

## Steer an agent

Enter sends what you wrote to the target shown above the composer, and a person's message steers: it reaches the agent
at the earliest point its harness takes input. `@agent` or `#channel` and a space at the start retargets it, and the
target follows the focus pane while the draft is empty; a message that would go elsewhere than the target shown is asked
about first. `/file` attaches a file as the message's body, and Up and Down recall what you sent.

`/thread` shows the thread of the chosen line's message, with every message sent in it, on any inbox or channel, and the
composer then replies to that message, as the chip above it says. The page shows a reply under what it answers only in
the same chat, so a reply that went to another chat is in the terminal's thread and not under its message on the page.

## Answer approvals and act

Approvals never take focus, and the dock's `y` and `n` act only on a place you chose there, so typing never answers one.
When an agent comes to need you while another is in view, a toast names it and why it waits, and Alt+A, or
`/next-place`, goes to each place you must act, in turn. That order, and the toast, are the defaults pending the owner's
ruling. `/yes` and `/no` take a place's first and second action, Allow and Deny for an approval, and `/ask` reads what an
approval asks, as whole as the record holds it, before you answer it. An ask the record cut at 64 KiB says how many bytes
more it asks, which Allow allows too, and one whose record holds no body says that what it asks beyond its gist is
unknown. An answer another client gave as you pressed shows as theirs, and an act the runtime refused shows disabled,
saying why.

Esc in the composer interrupts the agent in view, and `/stop-below` stops the turns of it and of every agent below it.
Every other op you hold that writes is in the palette, `/palette`, an extension's among them, each through a form worded
as the command line words its command. The ones that end an agent or the session, erase a body, or run a commit's code as
you ask once first.

On a queue's focus, `/tasks` or Ctrl+T lists its tasks, as `task list` gives them, with what you may do to each, and on a
board's focus its entries, as `board query --history` gives them. The list is read again whenever the journal moves one
of them, and at no other time.

## Review what changed

`/review`, or Alt+D, lists what changed, grouped by workspace: the commits made in each agent's workspace, with what their
latest runtime test came to, then its uncommitted paths, conflicted first; your checkout's paths when a role works there;
and last the commits that are nobody's. A look after each agent's turn finds them. [A screenshot](../assets/tui-review.svg)
shows the list on the recorded session.

Enter on a commit opens its patch, and on a workspace what it holds uncommitted, read where the workspace lives, as
[Read a diff](workspaces.md#read-a-diff) says; [a screenshot](../assets/tui-patch.svg) shows a patch on a scripted session.
`t` on a commit tests it, once you say yes, as it runs that commit's code as you, unconfined
([Test a commit](workspaces.md#test-a-commit)). In a patch, Space chooses lines and `c` writes a comment on them, a
message to the agent whose workspace made the change. A conflict an agent's merge stopped on waits in the dock, saying to
tell the agent or to resolve it in your own checkout, never in its workspace
([workspaces](workspaces.md#resolve-an-agents-conflict)).

## See where a line came from

`p` with the transcript in focus shows where the chosen line came from, and `/provenance` opens a form for any ref, as
`stream@version`: what it rests on, what came of it, whose work it reaches, and what estimators said of it, in the
parts [Provenance](provenance.md#follow-it-in-the-terminal-and-the-browser) describes, each link opening its event's
provenance and Esc going back one hop. That a ref is opened by hand, rather than found by searching, is the default
pending the owner's ruling. [A screenshot](../assets/tui-provenance.svg) shows the provenance of the mixed team's lead's
answer on the recorded session.

`/reached` shows who reached whom in the session in the same panel: each pair of makers, each kind of edge apart with how
it is known, never summed, and each agent's unknowns, so an agent no pair names is not shown to be reached by nobody. It
walks the journal each time it is read, so it slows as the session grows. [A screenshot](../assets/tui-who-reached-whom.svg)
shows it on a scripted session. That it is listed in provenance, and not on the page's Map, counting these kinds, is the
default pending the owner's ruling.

## Replay a session

`platoon-harness attach fix-auth --replay`, or `R` on the sessions screen, opens a read-only copy of a session's record,
drawn as the session is and moving as it plays, under a banner that always says it is a replay. Every act says why it
does nothing; [Replay a session](replay.md) is its guide.

## Reconnecting

A runtime that stops, is resumed or is killed while you are attached shows as what it is, as a banner over its history.
When a runtime takes the session up again, the UI attaches again and goes on from the last event it drew, so nothing is
shown twice or lost.

## Themes and motion

The workspace is drawn on a dark ink background with one accent colour, the logo's sky blue: the theme `platoon-ink`.
Warnings, history and what needs you are a muted amber, each told apart by its glyph and words as well. `/theme`, or `t`
on the sessions screen, chooses another of Textual's themes for this run, `ansi-dark` among them, which draws in your
terminal's own colours, and says the line that keeps it, such as `theme = "nord"`, in `tui.toml`, in
`$XDG_CONFIG_HOME/platoon-harness`, or `~/.config/platoon-harness` where that is not set. `tui.toml` takes two keys,
`theme` and `motion`, which `false` turns off, and a file it cannot take is not taken at all, saying why.

Platoon's agents stand beside the wordmark, sprites drawn from Platoon's icon, which [the README](../../README.md#license)
credits, and move a little, at four frames a second at most, from the session's state as its record says it and from
nothing else: they step while agents work, blink while every agent rests, and hop when one comes to need you. A session
that is history never moves, and an agent whose state is unknown shows no motion that would say it works or rests.
Textual's animation level below full, as `TEXTUAL_ANIMATIONS=basic` or `none` sets it, turns motion off too.

The mouse does what a key does, and each key still does it: a click chooses a row or a line, the wheel scrolls, and a
drag of the navigator's edge widens or narrows it.

## Text from outside

Agent, tool, branch and file names, messages and tool output reach the screen through one boundary, `SafeText`, which
shows each control a terminal would act on as its escape, and nothing from outside is read as markup. Links are followed
only to `http` and `https`.

## Terminals that keep keys

Some terminals keep keys for themselves. The terminal inside VS Code, and inside editors built on it such as Cursor, hands
a key bound to an editor command to the editor, and there F1 opens the editor's own command palette:
`"terminal.integrated.sendKeybindingsToShell": true` sends most keys to the program instead. On macOS, Option types a
character unless the terminal sends it as Meta: `"terminal.integrated.macOptionIsMeta": true` in VS Code and Cursor,
"Use Option as Meta key" in Terminal.app and "Left Option key: Esc+" in iTerm2. Nothing here was measured on a Mac. None
of these settings is needed, since every act has a typed command and a plain-key path.

## Keys

F1 shows every key and typed command, and so do `?` on the sessions screen and `/` typed in a session. A part that has
focus takes its own keys before the session's. `^` is Ctrl.

<!-- keymap: made from the keymap table by `uv run python -m platoon_harness_cli.tui.keymap docs/how-to/tui.md` -->

### Everywhere

| Keys | Typed | Does |
|---|---|---|
| `F1` | `/help` | Show every key and typed command |
| `^P` | `/palette` | Find a command, an op among them |
| `^Q` | `/quit` | Quit: a session you are in runs on |
| `^C` | `/copy` | Copy the text selected with the mouse, or else the chosen line, as OSC 52, which a terminal may put on the clipboard |

### The sessions screen

| Keys | Does |
|---|---|
| `Enter` | Open the session, live or as its history |
| `n` | Start a session from the project's team or a team file |
| `e` | Edit the project's team: its roles, harnesses, models, topology, budget, labels, auth profiles and test |
| `r` | Resume a session whose runtime has gone, which can spend money |
| `s` | Stop a session's runtime as its owner would, keeping it resumable |
| `R` | Replay a session from its start: a copy of its record, which acts on nothing |
| `l` | Look again for sessions and how each stands |
| `t` | Choose a colour theme for this run |
| `c` | Copy the text selected with the mouse, as OSC 52 |
| `?` | Show every key and typed command |
| `p` | Find a command, an op among them |
| `q` | Quit: a session you are in runs on |

### The team editor

| Keys | Does |
|---|---|
| `Enter` | Change the chosen field, or add or remove the chosen entry |
| `s` | Save the draft as its diff shows, asking first where it writes what would run as you |
| `n` | Start a session from the project's team, saving changes first |
| `r` | Read the team file and this machine's harnesses again, asking first where that drops your changes |
| `?` | Show every key and typed command |
| `Esc` | Go back to the sessions screen, asking first where that drops your changes |

### A session, unless the part that has focus takes the key

| Keys | Typed | Does |
|---|---|---|
| `Esc` | `/interrupt` | Interrupt the agent in view: its turn stops, and it lives on |
|  | `/stop-below` | Stop the turns of the agent in view and of every agent below it |
| `Alt+A` | `/next-place` | Go to the next place you must act |
|  | `/yes` | Take the first action of where you are, such as Allow |
|  | `/no` | Take the second action of where you are, such as Deny |
|  | `/ask` | Read the whole of what the approval you are at asks, before you answer it |
| `Alt+↓` | `/next` | Show the next agent or channel |
| `Alt+↑` | `/previous` | Show the previous agent or channel |
| `^B` | `/navigator` | Show or hide the agents and channels |
| `Alt+→` | `/wider` | Widen the agents and channels, as dragging their edge does |
| `Alt+←` | `/narrower` | Narrow the agents and channels, as dragging their edge does |
| `F2` | `/inspector` | Show or hide why the agent in view waits, and what it runs on |
|  | `/open-line` | Open or close the chosen line of the transcript |
| `^O` | `/folds` | Open every fold of the transcript, each turn's calls, thoughts and spawns, or close them all |
| `PgUp` | `/page-up` | Scroll the transcript up |
| `PgDn` | `/page-down` | Scroll the transcript down |
| `^Home` | `/oldest` | Go to the start of the transcript, read back from the journal |
| `^End` | `/follow` | Go to the newest line and follow what comes |
| `^F` | `/find` | Find the line before the chosen one whose words hold those you give, reading back a page at a time |
| `Alt+F` | `/file` | Attach a file to the message, as its body |
|  | `/resume` | Resume this session when it is history, which can spend money |
|  | `/theme` | Choose a colour theme for this run |
| `^T` | `/tasks` | Show the tasks of the queue in view, or the entries of the board in view, each act opening its op's form |
| `Alt+D` | `/review` | List what changed: each workspace's commits and uncommitted paths, each opening its diff |
|  | `/provenance` | Show an event's provenance, by the ref you give, the chosen line's unless you give another: what it rests on, what came of it and whose work it reaches |
|  | `/thread` | Show the thread of the chosen line's message, where the composer replies to it |
|  | `/reached` | Show who reached whom in the session: each pair of makers, each kind of edge apart with how it is known, and each agent's unknowns, each link opening its event's provenance |
| `Alt+M` | `/model` | Switch the model of the agent in view. Not built yet: the driver contract cannot switch a running agent's model; switching it is planned |
| `Alt+T` | `/takeover` | Drive the agent in view in its own terminal. Not built yet: the driver contract carries no agent's terminal, and `agent hold` holds its deliveries and no more; driving it is planned |
| `^D` | `/detach` | Detach on an empty composer: the session runs on |

### A replay, once the transcript, the dock or the navigator has focus

| Keys | Typed | Does |
|---|---|---|
| `Space` | `/play` | Play the replay from where it stands, at its speed, or pause it |
| `s` | `/speed` | Play at the next speed: 1x, 4x, 16x, idle skipped, then 1x again |
| `.` | `/step` | Step one event on |
| `,` | `/back` | Step one event back |
| `]` | `/turn` | Go on to where the next turn ends, of any agent |
| `[` | `/turn-back` | Go back to where the turn before ended, of any agent |
| `j` | `/jump` | Jump to an event, by its number, or to a time into the session, as m:ss or h:mm:ss |

### Between a session's parts

| Keys | Does |
|---|---|
| `Tab` | Go to the next part: the navigator, the transcript, the dock, the composer, and round |
| `Shift+Tab` | Go to the part before |

### The transcript, the dock or the navigator, once one has focus

| Keys | Does |
|---|---|
| `Esc` | Go back to the composer, interrupting nothing |
| `/` | Go back to the composer and begin a typed command there |

### The transcript, once it has focus

| Keys | Does |
|---|---|
| `↑` | Choose the line above |
| `↓` | Choose the line below |
| `Enter` | Open or close the chosen line |
| `→` | Open the chosen line one level, or go into the fold it opened |
| `←` | Close the chosen line one level, or go out to the fold it stands in |
| `Esc` | Close the chosen line one level, as Left does, or with nothing open there go back to the composer |
| `End` | Go to the newest line and follow what comes |
| `p` | Show the chosen line's provenance |

### The dock, once it has focus

| Keys | Does |
|---|---|
| `y` | Take the first action of the chosen place, such as Allow |
| `n` | Take the second action of the chosen place, such as Deny |
| `a` | Read the whole of what the chosen approval asks |

### The composer

| Keys | Does |
|---|---|
| `Enter` | Send to the target shown above it, which steers an agent at its next boundary, or run a typed command |
| `Shift+Enter` or `Alt+Enter` or `^J` | Start a new line |
| `↑` | On the first line, what you sent or ran before |
| `↓` | On the last line, what you sent or ran after |

### A list: sessions, agents, places, help, provenance, changes, tasks, asks

| Keys | Does |
|---|---|
| `↑` | Choose the row above, or scroll up the help |
| `↓` | Choose the row below, or scroll down the help |
| `Enter` | Open the chosen row, or show the chosen place |

### What changed

| Keys | Does |
|---|---|
| `t` | Test the chosen commit, once you say yes, as that runs its code as you |

### A diff

| Keys | Does |
|---|---|
| `Space` | Choose the line under the cursor; on another, every line from the first to it; again, none |
| `c` | Comment on the chosen lines, or with none on the commit, as a message to its maker |

### The provenance panel

| Keys | Does |
|---|---|
| `Esc` | Go back one hop, and from the first, leave |

### A question

| Keys | Does |
|---|---|
| `y` | Say yes |
| `n` or `Esc` | Say no |

### A form, the help, an approval's ask, or tasks or entries

| Keys | Does |
|---|---|
| `Esc` | Leave it, and a form sends nothing |

<!-- end of keymap -->

## Not built yet

Disabled where a control for it would be, or absent from the palette: image input, harness slash commands, model and
permission switching, taking over an agent's native terminal, notifications outside the terminal, such as its bell or
the desktop's, and in provenance credit drawn beside who contributed. [STATUS.md](../STATUS.md) says what each is. A
session does not fork, since native sessions, worktrees, leases and credentials do not, so no control will offer it.
