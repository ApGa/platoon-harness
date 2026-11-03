# The terminal UI

`platoon-harness` on a terminal opens the terminal UI. It is a client like any other: it submits ops and draws the views,
holds no timer that decides anything, and computes no status. [cli.md](cli.md) is the command line's reference and
[headless.md](headless.md) runs the same sessions with no terminal.

## Opening it

```console
$ platoon-harness                 # the sessions screen
$ platoon-harness attach fix-auth # one session
```

With no terminal, `platoon-harness` prints its help, since nothing ever prompts with none, and `attach` exits 64 and names
`events --follow`. A session started here gets a detached runtime of its own, the way tmux starts its server, and the UI is
its guest: Ctrl+D detaches and the session runs on, and `attach` comes back to it.

## The sessions screen

Every session under the root, whether a runtime holds it and its state, and it works with none. `n` starts one from the
project's `platoon-harness.toml` or a team file. When several agents would run on your own plan login it asks once whether
this is your own work, which is the SDK's `plan_login`. `r` resumes a session whose runtime has gone, after saying that it
can spend money. `s` stops one as its owner would, after one confirmation, and it stays resumable. Enter opens one: live
as a guest, or as read-only history when no runtime holds it, with Alt+R offered to resume it. Ctrl+D comes back here from
a session opened here, which runs on. In a form, Enter goes to the next field, and from the last sends it.

## The workspace

| Part | What it answers |
|---|---|
| Header | Who is working, how many places need you, what is blocked or failed, what changed, which it says is not measured until the turn-end probe lands, and each limit with what is spent against it, `?` where nobody could say, and how many turns nobody measured whole |
| Navigator | Agents grouped by what you must do, Needs you, Working, Blocked, Idle, Done and Failed, as a tree by parent, with what each is on or waits for. Channels below, with how many lines you did not write lie past your mark, and a mark for a mention you have not read |
| Focus pane | One agent or one channel at a time, so live text is never merged |
| Inspector, F2 | Why an agent waits, its harness, model and levels, what it spent with labels, its gaps, and what the runtime refused you |
| Dock | Each place you must act, from the `attention` view, with its actions |
| Composer | What you write, and above it whom it goes to and what waits for that agent |

The groups come from the roster's `group`, so every client says the same. Your unread counts and the mentions you have
read come from your marks in `marks.sqlite`: reading a channel to its newest line moves them, and moving them is no event
and acknowledges nothing an agent was handed. It is the one file reading a session writes, history too. One that cannot be
read or written loses only badges, which is said once.

### The transcript

Each event is one line, and a line opens on demand, with Enter on the chosen line, Ctrl+O from anywhere, or a click: its
body as Markdown and code, or its gist whole, then where it came from. Links are followed only to `http` and `https`. The
transcript holds a window of at most 10,000 lines, read from the journal a page at a time as you scroll either way, and what
was on screen stays where it was. Ctrl+Home reads it from the journal's first line. An agent's transcript shows how each
child it spawned began and ended, where the journal has it, inside the turn that spawned it. Below the lines is what the
agent in view is saying now, live, until the journal holds it as an item, and it goes with a runtime that goes. Reading up
stops following, and the line under the transcript counts what came since; Ctrl+End, or End with the transcript focused,
follows again. A page the journal would not give is named as lines missed.

### The composer

Enter sends to the target shown above it, and a person's message steers: it lands at the earliest boundary the harness
has. `@agent` or `#channel` and a space at the start retargets it, and the target follows the focus pane while the draft is
empty. Something that would go elsewhere than the target shown, such as a message that still begins with another address,
is asked about first, and so is one that begins with `/`, as a harness's own command would, since those are not built yet.
Alt+F attaches a file as the message's body. Up and Down on the first and last lines recall what you sent, over an empty
draft and never over one being written, which a recalled message is once you edit it. Ctrl+D on an empty composer detaches,
and with a draft it says why it does not.

### Acting

Approvals never take focus, so a key meant for the composer never answers one. Alt+A goes to the next place you must act,
and Alt+Y and Alt+N take its first and second action, Allow and Deny for an approval, each carrying the version it was
drawn from. Only you move where you are: a place that goes, answered here or by another client, takes it with it, so a key
never acts on a place you did not choose. An answer another client gave as you pressed shows as theirs. Esc interrupts the
agent in view, and Alt+S stops the turns of it and of every agent below it: both stop turns, not waits. When the runtime
refuses one, the refusal is kept: the key shows disabled, pressing it again says the runtime's reason and sends nothing,
and it comes back once that agent's row moves. Retiring or cancelling an agent, closing or cancelling the session, and every other
command a person may run are in the palette, Ctrl+P, worded as the command line words them, and the ones that end an agent
or the session, or erase a body, ask once. A read is what the screen draws, so the palette offers none: the command line
prints any. A takeover says it is not built yet, as Alt+T does.

### Size

| Size | Layout |
|---|---|
| 120 columns or more | Navigator, focus pane, and the inspector beside them |
| 80 to 119 | Navigator and focus pane, and the inspector over the focus pane |
| 60 to 79 | The focus pane, a line of the team above the composer, and the navigator on Ctrl+B |
| under 60 | As 60 to 79, with the header shortened to counts and the footer to keys |
| under 16 rows | The dock, the banner and the team line give way, and the composer keeps three rows |

A resize changes which parts show, and never the scroll position, focus or the composer's target.

### Reconnecting

A runtime that stops, is resumed or is killed while you are attached shows as what it is, as a banner over its history,
from the session's state: stopped as its owner asked, or gone without its shutdown, which a session that crashed before you
opened it says too. Leaving a session no runtime holds says nothing of one running on.
When a runtime takes the session up again, from here or from another shell, the UI attaches again and goes on from the last
event it drew, so nothing is shown twice or lost.

## Text from outside

Agent, tool, branch and file names, messages and tool output reach the screen through one boundary, `SafeText`, which
shows each control a terminal would act on as its escape: C0 but tab and newline, DEL, C1 and the bidi controls. Nothing
from outside is read as markup.

## Keys

The keymap is one table, from which the bindings, the help (F1), the footer and the palette are made.

<!-- keymap: made from the keymap table by `uv run python -m platoon_harness_cli.tui.keymap docs/tui.md` -->

### Everywhere

| Keys | Does |
|---|---|
| `f1` | Show every key |
| `ctrl+p` | Find a command, an op among them |
| `ctrl+q` | Leave: a session you are in runs on |

### The sessions screen

| Keys | Does |
|---|---|
| `enter` | Open the session, live or as its history |
| `n` | Start a session from the project's team or a team file |
| `r` | Resume a session whose runtime has gone, which can spend money |
| `s` | Stop a session's runtime as its owner would, keeping it resumable |
| `ctrl+r` | Look again for sessions and how each stands |

### A session, whatever has focus

| Keys | Does |
|---|---|
| `escape` | Interrupt the agent in view: its turn stops, and it lives on |
| `alt+s` | Stop the turns of the agent in view and of every agent below it |
| `alt+a` | Go to the next place you must act |
| `alt+y` | Take the first action of where you are, such as Allow |
| `alt+n` | Take the second action of where you are, such as Deny |
| `alt+down` | Show the next agent or channel |
| `alt+up` | Show the previous agent or channel |
| `ctrl+b` | Show or hide the agents and channels |
| `f2` | Show or hide why the agent in view waits, and what it runs on |
| `ctrl+o` | Open or close the chosen line of the transcript |
| `pageup` | Scroll the transcript up |
| `pagedown` | Scroll the transcript down |
| `ctrl+home` | Go to the start of the transcript, read back from the journal |
| `ctrl+end` | Go to the newest line and follow what comes |
| `alt+f` | Attach a file to the message, as its body |
| `alt+r` | Resume this session when it is history, which can spend money |
| `ctrl+t` | Show the tasks and the board. Not built yet: the tasks and board views are planned: a queue's or a board's channel shows its lines |
| `alt+d` | Review what changed, as diffs. Not built yet: the review screen is planned: what changed is measured once workspaces land |
| `alt+m` | Switch the model of the agent in view. Not built yet: switching an agent's model is planned |
| `alt+t` | Drive the agent in view in its own terminal. Not built yet: driving an agent's own terminal is planned: `agent takeover` holds its deliveries and no more |
| `ctrl+d` | Detach on an empty composer: the session runs on |

### The transcript, once it has focus

| Keys | Does |
|---|---|
| `up` | Choose the line above |
| `down` | Choose the line below |
| `enter` | Open or close the chosen line |
| `end` | Go to the newest line and follow what comes |
| `slash` | Search the transcript. Not built yet: search in a transcript is planned |

### The composer

| Keys | Does |
|---|---|
| `enter` | Send to the target shown above it, which steers an agent at its next boundary |
| `shift+enter` or `alt+enter` or `ctrl+j` | Start a new line |
| `up` | On the first line, the message you sent before |
| `down` | On the last line, the message you sent after |

### A list: the sessions, the agents and channels, the help

| Keys | Does |
|---|---|
| `up` | Choose the row above, or scroll up the help |
| `down` | Choose the row below, or scroll down the help |
| `enter` | Open the chosen row |

### A question

| Keys | Does |
|---|---|
| `y` | Say yes |
| `n` or `escape` | Say no |

### A form or the help

| Keys | Does |
|---|---|
| `escape` | Leave it, and a form sends nothing |

<!-- end of keymap -->

## Not built yet

Disabled where a control for it would be, or absent from the palette: a review screen of diffs, search in a transcript,
threads, the tasks and board views beyond their channel's lines, image input, harness slash commands, model and permission
switching, taking over an agent's native terminal, following a line into its provenance, an approval and who answered it in
the transcript, forking a session, copying a selection from the transcript, themes and notifications.
[STATUS.md](STATUS.md) says what each is.
