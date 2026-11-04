# The browser

`platoon-harness web SESSION` serves [SwarmChat](https://swarmchat.io)'s page over one session's journal. It is a client
like any other: it reads what the journal holds, decides nothing, and computes no status. [tui.md](tui.md) is the terminal's
guide and [cli.md](cli.md) the command line's reference. In this stage the page reads: acting from it, by message, reply,
approval or lifecycle, comes in the next, and each act is on the page now, disabled, saying so.

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
itself as it was. It serves one session on one port, as the page keeps one session in the browser per address.

## The two links

| Link | What it opens |
|---|---|
| View | The session, to read. It reaches only what the page reads, can never act or make a link, and nothing turns it into the other kind |
| Control | The session, as you: what you do through it is your op, through the same path as the terminal's, and your grants decide what you may do |

A link opens once, within ten minutes, and is spent for a session in that browser of the same kind, which lasts twelve
hours. Its secret is after `#`, so it never reaches a server log or a referrer. `web` keeps only hashes of what it gave
out, in its own memory, so stopping it ends every browser's session: open a new link. A page that acts can make more links
of either kind, through `/x/link`; the page has no button for it yet. Your own credential never reaches a browser.

A control link acts as you, on your login. Never hand one to somebody else: on a plan login that would be your login
serving another person, which its terms do not allow. Give them a view link.

## What the page shows

- **Chats.** A channel's chat for each topic, group, queue and board, and direct chats. Every agent has a direct chat with
  you from its start, and a direct chat between two agents merges both their inboxes, in the order the journal has them.
  A queue's or board's chat holds what it announced, as the terminal's channel lines do.
- **Messages.** A message shows its gist, or its body when the body is text that holds the gist, as a message the terminal
  sent with a long text does. A body longer than 20,000 characters, what a SwarmChat message shows, is cut there, saying
  so, and a body a message does not show whole comes as a file, which SwarmChat's own viewer opens whole. A reply, or a
  message in a thread, shows under what it answers when that is in the same chat.
- **What an agent says.** What its harness says in a turn is its message to you, in its chat with you. Thoughts, tool
  calls and their output, token counts and live text never enter a chat. Live text, as it streams, is not shown in this
  stage.
- **Agents and people.** A person's picture is round and an agent's square, and the top bar counts agents and people
  apart. Each agent's status is the roster's, the same words the terminal uses: its group, then what it waits on or what
  it is doing. An agent's end is one line in its chat with you.
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

Disabled where its control is, with the reason: sending, replying, a file as a message's body, approving, and an agent's
interrupt, stop below, retire and cancel, which come next; the board layout, the tasks and board views, the map, tool
activity, diff review and provenance. Pictures in a body are offered as a download and not drawn. [STATUS.md](STATUS.md)
says what each is.

## Security

- **Where it listens.** Loopback, unless `--host` names another address, which needs TLS, `--certificate` and `--key`, and
  is refused without them. A wildcard such as `0.0.0.0` is refused, since a browser's requests must name the host served.
- **What it believes.** Every request is bounded before it is believed, by the same code as the SDK's tool server: a head
  of at most 16 KiB, then `Host`, which must name the authority served, which defeats DNS rebinding, then on a POST
  `Origin`, which must be the page's own, then the bearer, and only then a body of a stated length, on a deadline, with a
  cap on connections and on the requests the feed holds at once.
- **What it runs.** SwarmChat's five page files are read from the installed package, `swarmchat==0.1.0`, and each is held to
  its SHA-256: a file that differs stops `web` before anything is served, saying which. Its own server never runs. The page
  runs under SwarmChat's own policy, scripts by hash alone, with the hashes made for what is served, and every answer says
  `Cache-Control: no-store`.
- **What it keeps.** The page's projection of the session is `swarmchat.sqlite` in the session folder, readable by you
  alone, which nothing reads back into the journal. Dropping it is harmless: `web` folds it again from the journal, and a
  new version of it does that by itself. A body erased in the journal is erased from it too.
