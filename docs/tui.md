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
its guest: `/detach`, or Ctrl+D, detaches and the session runs on, and `attach` comes back to it.

## Every act from any terminal

A chord is a shortcut and never the only way: every act also takes only keys every terminal delivers, which are
printable characters, Enter, Esc, Tab, Shift+Tab, the arrows and Backspace.

- In the composer, a line that is exactly `/` and an act's name runs that act and goes to no agent: `/next-place`, `/yes`,
  `/interrupt`, `/detach`, `/quit`. Each act has one name, kept in the keymap table beside any key, and the help, the
  palette and the keymap below show it there.
- `/` alone, or `/help`, lists them, and the footer always begins `/ commands`. `/` from any other part goes back to the
  composer and begins one there.
- Anything else that begins with `/` is asked about before it goes as a message, since a harness's own commands are not
  built yet.
- A typed command not built yet says why, as its key does.
- No chord decides, stops or spends anything: a terminal sends Alt and a letter as Esc then that letter, so Esc then a word
  typed at once would run one. `/yes`, `/no`, `/stop-below` and `/resume` have no key.
- Tab and Shift+Tab go round the parts in the order they are on screen: the navigator, the transcript, the dock and the
  composer.
- Only Tab or Shift+Tab moves focus to the dock, and its `y` and `n` act only on a place chosen there with the arrows: it
  takes focus with no place chosen, and a character it does not take lets go of the one chosen, in the order the keys
  come, so a stray Tab from a draft, then the draft going on, answers nothing. A click chooses a place and gives no focus.
- A part hidden while it has focus, by a resize, `/navigator` or a dock left empty, gives focus back to the composer.
- Esc in the composer interrupts the agent in view, and from any other part goes back to the composer, interrupting
  nothing. The footer names Esc by what it does from the part with focus, and that part is marked: the navigator by its
  edge, the transcript by its title and the dock by its band.
- Where nothing is typed, on the sessions screen, in a question, a form or the help, every act has a plain key, quitting
  included.

## The sessions screen

Every session under the root, whether a runtime holds it and its state, and it works with none. `n` starts one from the
project's `platoon-harness.toml` or a team file. When several agents would run on your own plan login it asks once whether
this is your own work, which is the SDK's `plan_login`. `r` resumes a session whose runtime has gone, after saying that it
can spend money. `s` stops one as its owner would, after one confirmation, and it stays resumable. Enter opens one: live
as a guest, or as read-only history when no runtime holds it, with `/resume` offered to resume it. `/detach` comes back
here from a session opened here, which runs on. `l` looks again, `?` shows every key, `p` opens the palette and `q`
quits. In a form, Enter goes to the next field, and from the last sends it.

## The workspace

| Part | What it answers |
|---|---|
| Header | Who is working, how many places need you, what is blocked or failed, what changed, as commits and paths uncommitted, `not measured` until the first look and `not observed` when the session's cwd is in no git repository, and each limit with what is spent against it, `?` where nobody could say, and how many turns nobody measured whole |
| Navigator | Agents grouped by what you must do, Needs you, Working, Blocked, Idle, Done and Failed, as a tree by parent, with what each is on or waits for. Channels below, with how many lines you did not write lie past your mark, and a mark for a mention you have not read |
| Focus pane | One agent or one channel at a time, so live text is never merged |
| Inspector, `/inspector` | Why an agent waits, its harness, model and levels, its workspace, with its branch, the commit it started from and why its stop kept it, what it spent with labels, its gaps, and what the runtime refused you |
| Dock | Each place you must act, from the `attention` view, with its actions. A conflict has none, and says where to resolve it |
| Composer | What you write, and above it whom it goes to and what waits for that agent |

The groups come from the roster's `group`, so every client says the same. Your unread counts and the mentions you have
read come from your marks in `marks.sqlite`: reading a channel to its newest line moves them, and moving them is no event
and acknowledges nothing an agent was handed. It is the one file the terminal writes reading a session, history too. One that cannot be
read or written loses only badges, which is said once.

### The transcript

Each event is one line, and a line opens on demand, with Enter on the chosen line, `/open-line` from anywhere, or a click: its
body as Markdown and code, or its gist whole, then where it came from. Links are followed only to `http` and `https`. The
transcript holds a window of at most 10,000 lines, read from the journal a page at a time as you scroll either way, and what
was on screen stays where it was. `/oldest` reads it from the journal's first line. An agent's transcript shows how each
child it spawned began and ended, where the journal has it, inside the turn that spawned it. Below the lines is what the
agent in view is saying now, live, until the journal holds it as an item, and it goes with a runtime that goes. Reading up
stops following, and the line under the transcript counts what came since; `/follow` follows again. A page the journal
would not give is named as lines missed.

### The composer

Enter sends to the target shown above it, and a person's message steers: it lands at the earliest boundary the harness
has, unless the line is a typed command, which runs. `@agent` or `#channel` and a space at the start retargets it, and the
target follows the focus pane while the draft is empty. Something that would go elsewhere than the target shown, such as a
message that still begins with another address, is asked about first, and so is one that begins with `/` and is none of
ours. `/file` attaches a file as the message's body, and since a body keeps no name, the file's name follows your words
in the gist. Up and Down on the first and last lines recall what you sent or ran, over an empty draft and never over one
being written, which a recalled message is once you edit it. Ctrl+D on an empty composer detaches, and with a draft it
says why it does not.

### Acting

Approvals never take focus, so a key meant for the composer never answers one. `/next-place`, or Alt+A, goes to the next
place you must act, and `/yes` and `/no` take its first and second action, Allow and Deny for an approval, each carrying
the version it was drawn from. With the dock reached by Shift+Tab, the arrows choose a place, Enter goes to it, and `y`
and `n` take the same two actions. Only you move where you are: a place that goes, answered here or by another client,
takes it with it, so a key never acts on a place you did not choose. An answer another client gave as you pressed shows
as theirs. Esc in the composer interrupts the agent in view, and `/stop-below` stops the turns of it and of every agent
below it: both stop turns, not waits. When the runtime refuses one, the refusal is kept: the key shows disabled,
pressing it again says the runtime's reason and sends nothing, and it comes back once that agent's row moves. Retiring
or cancelling an agent, closing or cancelling the session, and every other command a person may run are in the palette,
`/palette`, worded as the command line words them, after the acts by their typed commands, and the ones that end an
agent or the session, or erase a body, ask once. A read is what the screen draws, so the palette offers none: the
command line prints any. A takeover says it is not built yet, as `/takeover` does.

### What changed

`/review`, or Alt+D, lists what changed, read-only, grouped by workspace: the commits made in an agent's workspace under that agent,
newest recorded first, with their short SHA, subject and lines added and removed, a dropped one marked where it stands; then that
workspace's uncommitted paths, conflicted first, with their state and lines, `?` where nobody measured them, and how many more there
are than the list holds; your checkout's paths when a role works there; and last the commits that are nobody's, made in your checkout
or in no workspace the session knows. A snapshot's group says its commits are in its own repository, until you fetch them. A look
after each agent's turn finds them, so a one-turn agent's work shows once its turn has ended. A row past your mark on `repo/<name>` is
marked `●`, and reading the list to its end moves the mark. Diffs are drawn disabled: they come with review, which is planned. A
conflict an agent's merge stopped on waits in the dock with no action, saying where to resolve it, since the runtime never resolves
one. The inspector says why a workspace was kept only once its agent's stop has kept it.

### Provenance

`/provenance`, or `p` with the transcript in focus, shows where the chosen line came from: the newest line while the transcript
follows, or the one you chose with the arrows. Every line is an event, and a line of a message that carries another event's words,
a write it announces or a child's report, opens on that event. The panel has four parts, read from the session's provenance queries
when it opens, in the words the browser's pane uses ([provenance.md](provenance.md) says what each answer means):

| Part | What it says |
|---|---|
| Sources | Who made it, in which turn, and the model call that chose it, through the tool item that joins them, or why no call is joined. Each citation, with its maker and what its citer had been handed of it, `seen` with each offer its harness said it took and each compaction since, `unknown` with its reasons, and for a range whether its lines were shown; each cause; its previous version or a commit's parents; and what its maker was handed below where the answer stops counting, with the gaps in its record |
| Uses | What cites it, what follows from it, its next version or the commits it is a parent of, and each agent it was handed to, with whether its harness said it took it |
| Contributors | Each maker a walk back along citations, causes and ancestry reaches, with the kinds that reached it and its gaps, and apart from them each maker whose work was only handed to one of them. It weighs and ranks nobody |
| Credit and rewards | What estimators said of it, each by its producer and version, with its scope and status and a value only when scored, beside any other and never summed |

Each link is labelled by how it is known, `declared`, `observed`, `cause`, `ancestry` or `gap`, and Enter on it shows that event's
provenance; Esc goes back one hop, and from the first leaves. A line that opens nothing, a commit git holds and the journal does
not, or an `Informed-By` value naming nothing the session holds, says why in its place. Each part says the head it was read at;
Sources says where it stops counting, below the model call that chose the event or its commit; and an answer whose turn had not
ended says a later report can still confirm an offer or join a call. Yellow marks what is unknown, missing or cut, and a part an
answer cut names the command line command that reads on. With no line chosen, it says so: what an agent is saying now is no event
until the journal holds it.

### Size

| Size | Layout |
|---|---|
| 120 columns or more | Navigator, focus pane, and the inspector beside them |
| 80 to 119 | Navigator and focus pane, and the inspector over the focus pane |
| 60 to 79 | The focus pane, a line of the team above the composer, and the navigator over the focus pane on `/navigator`, until Esc or a row chosen in it closes it |
| under 60 | As 60 to 79, with the header shortened to counts and the footer to `/ commands` and keys |
| under 16 rows | The dock, the banner and the team line give way, and the composer keeps three rows |

A resize changes which parts show, and never the scroll position or the composer's target. It moves focus only by hiding
the part that has it, which gives focus back to the composer.

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

## Terminals that keep keys

Some terminals keep keys for themselves. The terminal inside VS Code, and inside editors built on it such as Cursor, hands
a key bound to an editor command to the editor, by the list in `terminal.integrated.commandsToSkipShell`, and there F1
opens the editor's own command palette. `"terminal.integrated.sendKeybindingsToShell": true` sends most keys to the program
instead. On macOS, Option types a character, `å` for Option+A, unless the terminal is set to send it as Meta: in VS Code
and Cursor `"terminal.integrated.macOptionIsMeta": true`, in Terminal.app's profile "Use Option as Meta key", and in
iTerm2's "Left Option key: Esc+". Until then every Alt key here arrives as a character instead. Nothing here was measured
on a Mac. None of these settings is needed, since every act has a typed command and a plain-key path.

## Keys

The keymap is one table, from which the bindings, the typed commands, the help (`/` typed in a session, `?` on the
sessions screen, or F1), the footer, the palette and this keymap are made. A part that has focus takes its own keys
before the session's. `^` is Ctrl.

<!-- keymap: made from the keymap table by `uv run python -m platoon_harness_cli.tui.keymap docs/tui.md` -->

### Everywhere

| Keys | Typed | Does |
|---|---|---|
| `F1` | `/help` | Show every key and typed command |
| `^P` | `/palette` | Find a command, an op among them |
| `^Q` | `/quit` | Quit: a session you are in runs on |

### The sessions screen

| Keys | Does |
|---|---|
| `Enter` | Open the session, live or as its history |
| `n` | Start a session from the project's team or a team file |
| `r` | Resume a session whose runtime has gone, which can spend money |
| `s` | Stop a session's runtime as its owner would, keeping it resumable |
| `l` | Look again for sessions and how each stands |
| `?` | Show every key and typed command |
| `p` | Find a command, an op among them |
| `q` | Quit: a session you are in runs on |

### A session, unless the part that has focus takes the key

| Keys | Typed | Does |
|---|---|---|
| `Esc` | `/interrupt` | Interrupt the agent in view: its turn stops, and it lives on |
|  | `/stop-below` | Stop the turns of the agent in view and of every agent below it |
| `Alt+A` | `/next-place` | Go to the next place you must act |
|  | `/yes` | Take the first action of where you are, such as Allow |
|  | `/no` | Take the second action of where you are, such as Deny |
| `Alt+↓` | `/next` | Show the next agent or channel |
| `Alt+↑` | `/previous` | Show the previous agent or channel |
| `^B` | `/navigator` | Show or hide the agents and channels |
| `F2` | `/inspector` | Show or hide why the agent in view waits, and what it runs on |
| `^O` | `/open-line` | Open or close the chosen line of the transcript |
| `PgUp` | `/page-up` | Scroll the transcript up |
| `PgDn` | `/page-down` | Scroll the transcript down |
| `^Home` | `/oldest` | Go to the start of the transcript, read back from the journal |
| `^End` | `/follow` | Go to the newest line and follow what comes |
| `Alt+F` | `/file` | Attach a file to the message, as its body |
|  | `/resume` | Resume this session when it is history, which can spend money |
| `^T` | `/tasks` | Show the tasks and the board. Not built yet: the tasks and board views are planned: a queue's or a board's channel shows its lines |
| `Alt+D` | `/review` | List what changed: each workspace's commits and uncommitted paths |
|  | `/provenance` | Show the chosen line's provenance: what it rests on, what came of it and whose work it reaches |
| `Alt+M` | `/model` | Switch the model of the agent in view. Not built yet: switching an agent's model is planned |
| `Alt+T` | `/takeover` | Drive the agent in view in its own terminal. Not built yet: driving an agent's own terminal is planned: `agent takeover` holds its deliveries and no more |
| `^D` | `/detach` | Detach on an empty composer: the session runs on |

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
| `End` | Go to the newest line and follow what comes |
| `p` | Show the chosen line's provenance |

### The dock, once it has focus

| Keys | Does |
|---|---|
| `y` | Take the first action of the chosen place, such as Allow |
| `n` | Take the second action of the chosen place, such as Deny |

### The composer

| Keys | Does |
|---|---|
| `Enter` | Send to the target shown above it, which steers an agent at its next boundary, or run a typed command |
| `Shift+Enter` or `Alt+Enter` or `^J` | Start a new line |
| `↑` | On the first line, what you sent or ran before |
| `↓` | On the last line, what you sent or ran after |

### A list: the sessions, the navigator, the dock, the help, provenance

| Keys | Does |
|---|---|
| `↑` | Choose the row above, or scroll up the help |
| `↓` | Choose the row below, or scroll down the help |
| `Enter` | Open the chosen row, or show the chosen place |

### The provenance panel

| Keys | Does |
|---|---|
| `Esc` | Go back one hop, and from the first, leave |

### A question

| Keys | Does |
|---|---|
| `y` | Say yes |
| `n` or `Esc` | Say no |

### A form or the help

| Keys | Does |
|---|---|
| `Esc` | Leave it, and a form sends nothing |

<!-- end of keymap -->

## Not built yet

Disabled where a control for it would be, or absent from the palette: diffs and review comments, search in a transcript,
threads, the tasks and board views beyond their channel's lines, image input, harness slash commands, model and permission
switching, taking over an agent's native terminal, an approval and who answered it in the transcript, forking a session, copying
a selection from the transcript, themes and notifications, and in provenance the interaction graph, credit drawn beside who
contributed, and refs in a message's text followed. [STATUS.md](STATUS.md) says what each is.
