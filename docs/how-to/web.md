# The browser

This guide shows how to watch a session from a browser and act on it there. `platoon-harness web SESSION` serves
[SwarmChat](https://swarmchat.io)'s page over one session's journal. It is a client like any other: it reads what the journal
holds, decides nothing, and computes no status, and what a person does there is an op, through the same path as the
terminal's. [tui.md](tui.md) is the terminal's guide and [cli.md](../reference/cli.md) the command line's reference.

**Goal:** open a session in a browser, read its chats as yourself or as one of its agents, answer what needs you and act on
the session as you, and give someone else a link that only reads.

**Prerequisites:**

- `platoon-harness` on your PATH, from a checkout installed as [Install](../getting-started/install.md) says, with its
  environment active as [your first session](../getting-started/first-session.md#5-set-up-your-own-team) has it;
- a session: one a runtime holds, to act on, as `web` starts and resumes nothing, or one no runtime holds, to read its
  history;
- a browser on this machine, or on another that can forward a port to it. The page's tests pass in Chromium and Firefox,
  and WebKit, Safari's engine, is untested ([compatibility](../reference/compatibility.md#6-supported-platforms)).

## Open it

```console
$ platoon-harness web fix-auth
platoon-harness: web: session fix-auth on 127.0.0.1:43117. Each link opens once, within ten minutes
platoon-harness: web: view link, which shows the session and acts on nothing: http://127.0.0.1:43117/view#link=9f1c…
platoon-harness: web: control link, which acts as you: http://127.0.0.1:43117/view#link=4b07…
platoon-harness: web: from another machine, forward this port under the same number, which the page's requests must name: ssh -N -L 43117:127.0.0.1:43117 devbox
```

From another machine, forward the port as that last line says, under the same number: the page's requests must name the
port served, so through a forward to another number every one is refused. Where the browser reaches a machine that reaches
this one, as an editor's port forwarding does, run that command on the machine in between. Each link opens the page; the
address alone sends a browser there too.

Open a link in a browser. `web` is a guest of the session's runtime, on your own control credential, as the terminal is.
It starts and resumes nothing, since resuming can spend money: on a session no runtime holds, the page shows its history,
says so at the top right, and names `platoon-harness session resume`. When a runtime takes the session up again, from any
shell, the page follows it. Ctrl+C or `SIGTERM` stops `web`, which ends every browser's session and leaves the session
itself as it was. It serves one session on one port, as the page keeps one session in the browser per address, and one
`web` serves a session at a time, as one folds its projection: a second is refused, saying where the first serves, whose
page makes new links on your own page there. While it runs, `web` is a client holding your control credential, so a run
whose agent asks for an approval waits for you to answer it, from the page or anywhere, instead of ending `needs_human`
at once: stop `web` for a run that should end that way.

## Choose a link

| Link | What it opens |
|---|---|
| View | The session, to read. It reaches only what the page reads, can never act or make a link, and nothing turns it into the other kind |
| Control | The session, as you: what you do through it is your op, through the same path as the terminal's, and your grants decide what you may do |

A link opens once, within ten minutes, and is spent for a session in that browser of the same kind, which lasts twelve
hours. Its secret is after `#`, so it never reaches a server log or a referrer. A link opened a second time says it was
used already. `web` keeps only hashes of what it gave out, in its own memory, so stopping it ends every browser's session:
open a new link. A page that acts can make more links of either kind, from your own page: see Acting. Your own credential never reaches a browser, and who sends from a page is the credential's, never anything the page
says.

A control link acts as you, on your login. Never hand one to somebody else: on a plan login that would be your login
serving another person, which its terms do not allow. Give them a view link. For the same reason `web` serves a session on
a plan login on loopback alone: see [Security](#security).

## What the page shows

- **Chats.** A channel's chat for each topic, group, queue and board, and direct chats. Every agent has a direct chat with
  you from its start, which the page says the runtime made, and a direct chat between two agents merges both their inboxes,
  in the order the journal has them. An agent's goal is the first message in its chat with whoever started it.
  A queue's or board's chat holds what it announced, as the terminal's channel lines do.
- **Messages.** A message shows its gist, or its body when the body is text that begins or ends with the gist, as a
  message the terminal sent with a long text does. A body longer than 20,000 characters, what a SwarmChat message shows, is
  cut there, saying so, and a body a message does not show whole comes as a file, which SwarmChat's own viewer opens whole.
  A reply, or a message in a thread, shows under what it answers when that is in the same chat.
- **What an agent says.** What its harness says in a turn is its message to you, in its chat with you. Thoughts, tool
  calls and their output, token counts and live text never enter a chat. Live text, as it streams, is not shown in this
  stage.
- **Agents and people.** A person's picture is round and an agent's square, and the top bar counts agents and people
  apart. Each agent's status is the roster's, the same words the terminal uses: its group, then what it waits on or what
  it is doing. The people list shows it beside each agent's name, where SwarmChat shows a first field, so who is working
  and who needs you reads at a glance. An agent's end is one line in its chat with you, saying what the terminal says of it: its report when it
  finished with one, and otherwise how it ended and why.
- **Approvals.** An approval left for you is a card under its question in the agent's chat with you, which says who
  decided it and through what, or that it went moot with the turn that asked.
- **Delivered to.** Where SwarmChat says "Read by", the page says "Delivered to": the agents a message was for that a
  handover landed it in, or a tool's result showed it to, which is evidence, and when; a goal reached its agent when the
  agent's first turn began on it. It never says one understood it. A
  person's reading leaves no evidence, so a person is in neither list. "What had reached" an agent, beside a message it
  sent, says how much of each of its chats had been delivered to it then.
- **Provenance.** Provenance among a message's actions opens a pane on the event the message shows, in the words the terminal's
  `/provenance` uses ([tui.md](tui.md) has them part by part): Sources, Uses, Contributors, and Credit and rewards. It begins
  "This is what the record holds: a citation is the agent's claim, being handed something is not using it, and what reached an
  agent through a file or a shell leaves nothing here. An estimate is its producer's, never a fact." Each link is labelled by how it
  is known, and choosing it, by a click or by Tab and Enter, shows that event's provenance, and when a chat shows the event, opens
  that chat at its message too. A message's actions show while focus is in it, so Tab reaches Provenance.
  The address names the event, so Back goes back a hop and a reload keeps it, and Esc or × closes the pane. It is read when it opens,
  and again when its Provenance is pressed again. It is a read, so a view link has it, and on history it answers what the journal
  holds. Credit is only what an estimator said, by producer, version and params.
- **As an agent.** Seeing the session as an agent shows its chats, how far each was delivered to it, and what waits to
  reach it, oldest first. Nothing is marked. A person and the runtime cannot be seen as, for the same reason: the picker
  draws them disabled, saying so, and an address that names one shows everyone.
- **The Board.** Board in the top bar, or Open as a board on a chat, shows a chat's top-level messages as posts, each
  with how many messages are below it in its thread, and Front page shows every channel's and group's, never a direct
  chat's. Seen as an agent, it shows that agent's chats alone. A post opens with its replies, each under what it answers.
  New sorts by when a post was written and Active by its newest reply. A session's messages take no reactions, so Hot
  and Top, which rank by votes, are disabled, saying why, an address that names one is sorted new, saying so, and each
  post's vote control is drawn disabled with no count: a 0 would say people had voted.
- **The Map.** Map in the top bar shows everyone at once: each agent and person in a chat, and whoever wrote one, joined
  to the channels and groups they are in and to each other by their direct chats, sized by what they sent, with a
  timeline of every message below. Dragging across the timeline weighs each chat and person by the messages of that stretch alone.
  With nothing under the mouse, its pane lists who writes most, people and the runtime among them, and the busiest chats.
  Clicking an agent sees the session as it, and the timeline and the stretch then count that agent's chats alone; a person
  and the runtime cannot be seen as, and their See as says so.
- **Times.** The Board's and the Map's times are the journal's, when each message was written, and never when `web`
  read it.

Browsing writes nothing to the journal, moves no agent's cursor, and moves no mark of yours: the terminal's unread counts
are yours alone.

## Acting

On a control link, each act is one op, sent to `/x/command` and run by `Session.submit`, as the terminal runs it, so your
grants decide what you may do here as anywhere. Every control you cannot use now is drawn disabled, saying why: on a view
link, on a session no runtime holds, which names `platoon-harness session resume`, in a chat between two agents, which you
are not in, in a queue's or a board's chat, while you see the session as an agent, for an op your grants do not hold, and
while an act you took waits for its answer. Tab still reaches it, and its reason is its accessible description, which
screen readers announce with a control, though none has been run on the page. The mouse shows the reason over it, focus
or a press shows it beside it, where it stays while the control has focus, and a press does nothing else. Needs you,
each post's vote control and each name the as-picker offers are buttons Tab reaches too, and Enter or Space presses
them. Needs you takes focus as it opens, so Tab reaches its actions first, and Escape gives it back to its row, as
closing any popover gives focus back to what opened it, and its row keeps focus as the sidebar is drawn again. A request
you allow or deny keeps focus on its card, which then says what came of it. Elsewhere a list drawn again as the session
moves drops focus from a control in it.

| Act | Where | What it sends |
|---|---|---|
| A message | The composer at the foot of a chat, which names its target, `@agent`, `#topic` or `+group`. Enter sends and Shift+Enter starts a new line | `message.send`. A text too long for a gist is cut as the terminal cuts one: its first 279 characters and an ellipsis are the gist, and the whole is the body, which the message shows |
| A reply | Reply on a message opens its thread, with a composer at the foot that answers that message | `message.send` with `reply_to`, the entry the message is in the journal. What an agent said in its turn, and an approval, are no entry a reply can cite, so their Reply is disabled, saying so |
| A file | Attach, beside Send, whose title says the most a body may be. A file larger is refused before it is sent, saying both sizes | The file to `/x/body`, saying how much has gone, then `message.send` with it as the body. A body keeps no name, so the gist is your text and the file's name, `TEXT (file NAME)`, or `file NAME` alone, made by the function the terminal's composer calls, and refused when the two run past 280 characters, as there |
| An approval | A card in the agent's chat with you, Allow and Deny | `approval.resolve` with the card's version and `via` `browser` |
| Needs you | The first row under All activity, with how many places there are. It opens a list of each, with its actions, read through `x_read`, so a view link and history show it too, each action disabled, saying why | Each action as the runtime's `attention` view offers it, with the version it was drawn from. One that leaves arguments to you, as a budget's Set the budget leaves its limits, opens its op's form in the pane, as Commands does, filled in with what it fixes, which the address keeps as `args=`. A place its agent's next turn settles, a lost turn, a wake past `max_hops`, a failure or a conflict of an agent's, offers Write to it, and a dead task Add it again, each opening its op's form. A conflict an agent's merge stopped on says on which files and where to resolve it, since the runtime never resolves one, and your checkout's has no action. So has a failure of no agent's, saying that nothing tries it again, and a daemon that keeps failing, saying where its traceback is and what starts it anew. A mention is a message to read in its chat, and the page keeps no marks, so the list holds none |
| An agent's acts | Its page: Interrupt, Stop below, Retire and Cancel | `agent.interrupt`, with `below` for Stop below, `agent.retire` and `agent.cancel`. What came of each is said under them |
| The session's | Your own page: Close the session and Cancel the session | `session.close`, which drains, and `session.cancel`, which stops now |
| A link | Your own page: New view link and New control link | `/x/link`, which gives a link of that kind, opening once, within ten minutes, said under the buttons. A view link makes none |
| Any op you hold that writes | Commands, in the top bar, lists one for each op the session's `ops.list` says you hold, an extension's among them, but a query, which a pane draws, and `wait` and the ops on a wait, as the terminal's palette lists them. Typing finds one, as Search does, and choosing it opens its form in the pane, which the address names, so Back and a reload keep it, and Esc or × closes it | The op, worded as its command's help, with a field per flag in that flag's words: text, yes or no, a choice, a whole number, a number, several separated by commas, JSON, which takes JSON alone and says why before anything is sent, or a body, whose text is stored, or cited where it is a body's ref, as the command line's flag takes it. A field left empty is left out, so the op's own default, shown in it, stands, and a gist too long for one is refused, as at the command line. `via` is said as `browser`. What came of it is said under Run: done, with what the op answered as text, or the refusal |

**Asked first.** Retire, Cancel, and closing or cancelling the session ask you once, beside the button, before they run,
and so does Run on the form of any op the terminal asks about, beside Run, saying the op and what was given it: these are
the ops that end an agent or the session, erase a body, or run a commit's code as you, one set both read, and nothing takes
them back. An extension's op is never asked about. The page has no list of commits to test from, so `repo test` takes a
commit's SHA in its form, and the terminal's `/review` lists them.

**Once.** The page makes a key for each draft sent or button pressed, 128 random bits, and keeps it until the act is
answered. Until then it sends the act again, after a lost connection, after a reload of the page, and from a new control
link opened in the same tab, since it keeps unanswered acts in the tab's own storage, and `web` answers a key it has seen
with its first answer, whichever link sends it. So a retry is one operation: one message, one decision. An act whose page's
session ended before it was answered, as when `web` stops, says it was not answered, and goes again from the next control
link you open in that tab. A view link opened there sends none of it, since it acts on nothing, and says what waits. `web`
puts the key under `web/`, so no other client's meets it.

**Refusals.** A refusal is an answer and is shown with its reason, never as success: under the composer, under a person's
acts, or as a notice. An approval someone decided first says who and through what: `Already decided by you via tui.`

**Both clients at once.** The terminal and the page can be attached to one session together. What either sends is in both,
once, and an approval answered in both at the same moment takes effect once: the other is told who decided and through
what, and its card or dock updates as the journal moves.

## SwarmChat's requests, here

Each request SwarmChat's page can make gets a real answer from the session, or its control is disabled with the reason.

| Request | Here |
|---|---|
| `view_page`, `view_info`, `view_snapshot`, `view_feed` | Real: the page, the session, and what comes, held until something does or the page's own wait is up, at most 25 s |
| `view_messages`, `view_thread`, `view_receipts`, `view_text`, `view_download` | Real |
| `view_search` | Real: every message the page shows, newest first, in any case, by text, sender, chat, file, time, and who it was brought to |
| `view_as` | Real for an agent. A person is refused, saying why |
| `view_knew` | Real, from delivery evidence, for a message an agent sent |
| `view_posts` | Real: posts from one chat, or from every channel and group, sorted new or active, and with `as` an agent's chats alone. Hot and top are refused, saying why, and a post's `votes` is null, which is unknown, never 0 |
| `view_activity` | Real: messages over time across every chat, or an agent's, and with `from` and `to` how many each chat had in that stretch and from whom, by the journal's times |

The page asks one read of ours beside them, `x_read`, for each pane of ours, in the terminal's words, and a view link may ask it,
as it asks the others. It reads through the session's queries alone, which the kernel refuses for an op that writes, so nothing
is written through it. Its `provenance` pane is one event's provenance,
by its ref, and the message it is in its chat, if one shows it. Its `attention` pane is every place you must act, but a mention.

## Not built yet

Each is drawn disabled where its control is, saying why: the tasks and board views, with each task open, claimed and by
whom under what lease, or done, and each board entry with its versions, as Tasks or Entries in a queue's or a board's
chat, which holds what it announced; and Tool activity and Review changes on an agent's page, which names the terminal's `/review`
for what changed. Live text, what an agent is saying before its turn commits it, is not shown in the page: an agent's
words appear once they are in the journal. Pictures in a body are offered as a download and not drawn. A form starts
empty wherever it was opened from. The page is laid out for a wide window, and at a phone's width it is not usable yet. [STATUS.md](../STATUS.md) says what each is.

## Security

What the whole of platoon-harness protects, and what it does not, is in [security.md](../security.md). The page's part:

- **Where it listens.** Loopback, unless `--host` names another address, which needs TLS, `--certificate` and `--key`, and
  is refused without them. A wildcard such as `0.0.0.0` or `::`, or a name that resolves to one, as `0` does, is
  refused, since a browser's requests must name the host served.
  A session on a plan login is served on loopback alone, and another address exits 78, saying why: one started with
  `--plan-login`, one of whose agents' harnesses came up last on a plan login, or one with a role that names no auth
  profile and whose harness says, by its own status command, that it is signed in on one, as a control link can spawn an
  agent of any role. That is checked as `web` starts, before anything listens. While it serves another address, `web`
  stops with 78 once an agent comes up on a plan login after all, as when a harness was signed in on one since, and what
  a control link did before then stands. A harness that cannot say which login it has is not counted, as the runtime
  does not count it either. From another machine, forward the loopback port, as Open it shows.
  A name with several addresses, as `localhost` has, is served on one port at each, so no other program on the machine can
  take that port on one of them and be what a browser reaches. A port that is the scheme's own, 80 or 443, is left out of
  the address, as a browser leaves it out.
- **What it believes.** Every request is bounded before it is believed, by the same code as the SDK's tool server: a head
  of at most 16 KiB, then `Host`, which must name the authority served, which defeats DNS rebinding, then on a POST
  `Origin`, which must be the page's own, then the bearer, and only then a body of a stated length, each part of it within
  10 s of the last, so a large file crosses a slow link and a client that stops is cut, with a cap on connections and on
  the requests the feed holds at once. A page on another origin is refused before its bearer is read, and a name rebound
  to this machine is refused by its `Host`.
- **What it runs.** SwarmChat's five page files are read from the installed package, `swarmchat==0.1.0`, and each is held to
  its SHA-256: a file that differs stops `web` before anything is served, saying which. Its own server never runs. The page
  runs under SwarmChat's own policy, scripts by hash alone, with the hashes made for what is served, and every answer says
  `Cache-Control: no-store`.
- **What it keeps.** The page's projection of the session is `swarmchat.sqlite` in the session folder, readable by you
  alone, which nothing reads back into the journal. Dropping it is harmless: `web` folds it again from the journal, and a
  new version of it does that by itself. A body erased in the journal is erased from it too.
