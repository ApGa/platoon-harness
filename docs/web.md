# The browser

`platoon-harness web SESSION` serves [SwarmChat](https://swarmchat.io)'s page over one session's journal. It is a client
like any other: it reads what the journal holds, decides nothing, and computes no status, and what a person does there is an
op, through the same path as the terminal's. [tui.md](tui.md) is the terminal's guide and [cli.md](cli.md) the command line's
reference.

## Opening it

```console
$ platoon-harness web fix-auth
platoon-harness: web: session fix-auth on 127.0.0.1:43117. Each link opens once, within ten minutes
platoon-harness: web: view link, which shows the session and acts on nothing: http://127.0.0.1:43117/view#link=9f1c…
platoon-harness: web: control link, which acts as you: http://127.0.0.1:43117/view#link=4b07…
```

Open a link in a browser. `web` is a guest of the session's runtime, on your own control credential, as the terminal is.
It starts and resumes nothing, since resuming can spend money: on a session no runtime holds, the page shows its history,
says so at the top right, and names `platoon-harness session resume`. When a runtime takes the session up again, from any
shell, the page follows it. Ctrl+C or `SIGTERM` stops `web`, which ends every browser's session and leaves the session
itself as it was. It serves one session on one port, as the page keeps one session in the browser per address, and one
`web` serves a session at a time, as one folds its projection: a second is refused, saying where the first serves, so
stop that one for new links.

## The two links

| Link | What it opens |
|---|---|
| View | The session, to read. It reaches only what the page reads, can never act or make a link, and nothing turns it into the other kind |
| Control | The session, as you: what you do through it is your op, through the same path as the terminal's, and your grants decide what you may do |

A link opens once, within ten minutes, and is spent for a session in that browser of the same kind, which lasts twelve
hours. Its secret is after `#`, so it never reaches a server log or a referrer. A link opened a second time says it was
used already. `web` keeps only hashes of what it gave out, in its own memory, so stopping it ends every browser's session:
open a new link. A page that acts can make more links of either kind, through `/x/link`; the page has no button for it
yet. Your own credential never reaches a browser, and who sends from a page is the credential's, never anything the page
says.

A control link acts as you, on your login. Never hand one to somebody else: on a plan login that would be your login
serving another person, which its terms do not allow. Give them a view link.

## What the page shows

- **Chats.** A channel's chat for each topic, group, queue and board, and direct chats. Every agent has a direct chat with
  you from its start, and a direct chat between two agents merges both their inboxes, in the order the journal has them.
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
  it is doing. An agent's end is one line in its chat with you, saying what the terminal says of it: its report when it
  finished with one, and otherwise how it ended and why.
- **Approvals.** An approval left for you is a card in the agent's chat with you, which says who decided it and through
  what, or that it went moot with the turn that asked.
- **Delivered to.** Where SwarmChat says "Read by", the page says "Delivered to": the agents a message was for that a
  handover landed it in, or a tool's result showed it to, which is evidence, and when. It never says one understood it. A
  person's reading leaves no evidence, so a person is in neither list. "What had reached" an agent, beside a message it
  sent, says how much of each of its chats had been delivered to it then.
- **As an agent.** Seeing the session as an agent shows its chats, how far each was delivered to it, and what waits to
  reach it, oldest first. Nothing is marked. A person cannot be seen as, for the same reason.

Browsing writes nothing to the journal, moves no agent's cursor, and moves no mark of yours: the terminal's unread counts
are yours alone.

## Acting

On a control link, each act is one op, sent to `/x/command` and run by `Session.submit`, as the terminal runs it, so your
grants decide what you may do here as anywhere. Every control you cannot use now is drawn disabled, and its title says why:
on a view link, on a session no runtime holds, which names `platoon-harness session resume`, in a chat between two agents,
which you are not in, in a queue's or a board's chat, while you see the session as an agent, and for an op your grants do
not hold.

| Act | Where | What it sends |
|---|---|---|
| A message | The composer at the foot of a chat, which names its target, `@agent`, `#topic` or `+group`. Enter sends and Shift+Enter starts a new line | `message.send`. A text too long for a gist is cut as the terminal cuts one: its first 279 characters and an ellipsis are the gist, and the whole is the body, which the message shows |
| A reply | Reply on a message opens its thread, with a composer at the foot that answers that message | `message.send` with `reply_to`, the entry the message is in the journal. What an agent said in its turn, and an approval, are no entry a reply can cite, so their Reply is disabled, saying so |
| A file | Attach, beside Send, whose title says the most a body may be. A file larger is refused before it is sent, saying both sizes | The file to `/x/body`, saying how much has gone, then `message.send` with it as the body and your text, or `file NAME`, as the gist. A long text and a file are two bodies, refused together, as in the terminal |
| An approval | A card in the agent's chat with you, Allow and Deny | `approval.resolve` with the card's version and `via` `browser` |
| Needs you | The first row under All activity, with how many places there are. It opens a list of each, with its actions | Each action as the runtime's `attention` view offers it, with the version it was drawn from. A mention is a message to read in its chat, and the page keeps no marks, so the list holds none |
| An agent's acts | Its page: Interrupt, Stop below, Retire and Cancel | `agent.interrupt`, with `below` for Stop below, `agent.retire` and `agent.cancel`. What came of each is said under them |
| The session's | Your own page: Close the session and Cancel the session | `session.close`, which drains, and `session.cancel`, which stops now |

**Asked first.** Retire, Cancel, and closing or cancelling the session ask you once, beside the button, before they run:
these are the ops the terminal asks about too, one set both read, and nothing takes them back.

**Once.** The page makes a key for each draft sent or button pressed, 128 random bits, and keeps it until the act is
answered. Until then it sends the act again, after a lost connection, after a reload of the page, and from a new link opened
in the same tab, since it keeps unanswered acts in the tab's own storage, and `web` answers a key it has seen with its first
answer, whichever link sends it. So a retry is one operation: one message, one decision. An act whose page's session ended
before it was answered, as when `web` stops, says it was not answered, and goes again from the next link you open in that
tab. `web` puts the key under `web/`, so no other client's meets it.

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
| `view_posts` | Not built: the board layout, with the tasks and board views, is disabled, saying so |
| `view_activity` | Not built: the map is disabled, saying so |

## Not built yet

Disabled where its control is, with the reason: the board layout, the tasks and board views, and the map. Tool activity,
diff review, provenance and a button to make a link have no control yet. Live text, what an agent is saying before its turn
commits it, is not shown in the page: an agent's words appear once they are in the journal. Pictures in a body are offered
as a download and not drawn. [STATUS.md](STATUS.md) says what each is.

## Security

- **Where it listens.** Loopback, unless `--host` names another address, which needs TLS, `--certificate` and `--key`, and
  is refused without them. A wildcard such as `0.0.0.0` is refused, since a browser's requests must name the host served.
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
