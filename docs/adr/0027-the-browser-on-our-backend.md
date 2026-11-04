# 0027. The browser on our backend

**Status:** Accepted, 2026-11-04

## Context

[ADR 0014](0014-swarmchat-compatibility-backend.md) chose SwarmChat's pinned page over a projection of our own, with an
overlay and one command route, and left how to build it open: where it lives, how a browser is let in and what it may do,
what the projection holds and how it stays the journal's, which of SwarmChat's requests to back, and how the server keeps
the bounds the SDK's tool server keeps. The page has no hook for any of this, a fixed `/v1/` path, a gate that asks for a
token before anything else, and a CSP that lets only scripts it names by hash run.

## Decision

- **Place.** The browser client is `platoon_harness_cli.web`, imported only by `platoon-harness web SESSION`, as the
  terminal UI is by its own path. `swarmchat==0.1.0` is a dependency of the CLI package, and its five page files are read
  through `importlib.resources` and nothing else: no product code imports SwarmChat, and a test holds that. Each file's
  SHA-256 is held to an allowlist when `web` starts, and one that differs stops it, saying which, with exit 78.
- **Process.** `web` is a guest on the owner's control credential, as every client of this user's is. It starts and
  resumes nothing. It follows the session as its runtime goes and comes back, and while no runtime holds it, it looks once
  a second for one or for what one wrote and left, so a runtime that came and went between two looks is still folded.
- **Projection.** A follower folds the journal one way into `swarmchat.sqlite` in the session folder, 0600, a transaction
  an event. The fold is a function of the events and of the bodies they cite, which the follower reads first, so a rebuild
  gives every row again. A chat's id is 16 hex of a hash of the session's name and what the chat is: a channel's stream, or
  the unordered pair of a direct chat's people, whose inboxes it merges in journal order. A guest cannot read the journal's
  own session id, and the name is the folder's, which the projection lives in. A line's seq is its place in its chat, the
  feed numbers what the page must hear in fold order and survives a restart of `web`, and `feed_id` hashes the session and
  the projection's version, whose change drops the file and folds again, which the page hears as a reset.
- **What a chat holds.** A person's and an agent's messages, a runtime's reports about an agent in the chat of its parent and
  that agent, an agent's goal in the chat of its spawner and itself, and what its harness says in a turn as its message in
  its chat with the person, since a harness says it to whoever runs it. Thoughts, tools, usage and live text never. A
  message shows its body in place of its gist when the body is text that holds the gist, cut at 20,000 characters, saying
  so, and a body it does not show whole comes as a file. An approval left to ask is a card, which goes moot with its turn as
  the runtime's own view has it. An agent's end is one line. A body erased in the journal is erased here: its text and file
  go, the database deletes securely, and its log is truncated at once.
- **Evidence.** A message was delivered to an agent when a handover landed it or a tool's result showed it, and the page
  says "Delivered to" from that alone. A person's reading is no evidence and is in no list. An agent's status is the
  roster's, read when the page asks, and the feed says to ask again after an event that begins, ends, parks, wakes, holds up
  or asks for its work, so the feed stays a function of the journal.
- **Credentials.** Two classes, view and control, fixed when minted. A link is `/view#link=<hex>`, opens once, and expires
  unspent after ten minutes. A script of ours, placed before SwarmChat's gate script, spends it at `/x/exchange` and hands
  the gate the session token through the address the gate watches, since the gate's first request needs the token and the
  overlay runs only after it. A session token is lowercase hex, lasts twelve hours, and only its hash is kept, in `web`'s
  memory. Time comes from the SDK's clock.
- **Network.** Loopback by default. `--host` names any other address, or a name, which `Host` must then say, and needs
  `--certificate` and `--key`; a wildcard is refused, as no browser names it. Every address a name has is bound on one
  port, so none is left for another program to take, and the scheme's own port is left out of the authority. `Host` is checked on every request and `Origin`
  on every POST. The bounds are the tool server's: its HTTP moved into `platoon_harness.http`, with public names, which both
  servers use. There `Origin`, when a request has one, must be the origin of the `Host` it names, for the tool server too,
  where before any loopback origin passed.
- **Commands.** `/x/command {op, args, key, expected_version}` runs `Session.submit`, and the kernel's grants decide.
  `expected_version` is the op's argument of that name, `via` is `browser` on an op that takes one and refused from the
  page, and the key is the page's for one draft or press, 128 random bits under `web/`, so a retry is one operation and no
  other client's key meets it. The ops asked about before they run are one set, `CONFIRMED`, which the terminal and the
  page both read.
- **SwarmChat's requests.** Every `view_*` the page reaches answers from the projection or is disabled with its reason:
  search is real, over what the page shows; seeing as an agent and what had reached an agent are real, from delivery
  evidence, and refused for a person; the board layout and the map, which ask `view_posts` and `view_activity`, are disabled.
- **Overlay.** Plain JS after SwarmChat's script, under one banner with its notice, which each of its scripts served begins
  with. It reads what the page may do from `view_info` before the page starts, says delivered where SwarmChat says read,
  tells agents and people apart, and shows every act disabled with its reason. Serve-time edits are exact-match, once
  against the pinned file or nothing is served, and are used only to put the page together as upstream's server does: the
  overlay reached every string this stage needed.

## Alternatives considered

| Alternative | Why not |
|---|---|
| The link's secret as the session token | A link left in a terminal or a history would open the page for twelve hours |
| An exact-match edit of `gate.js` for the exchange | It would put logic in an edit. A script beside it changes no byte of SwarmChat's |
| The journal's session id in the chat ids | A guest cannot read it, and the projection lives in the folder its name names |
| An agent's status folded from lifecycle events | That computes a status the roster already says, and could say it otherwise |
| A user entry in the feed for each roster read | Feed numbers would depend on when the page asked, so a rebuild could renumber them under the same `feed_id` |
| The board layout over `view_posts` | Our boards are objects with versions, and a post layout over messages would read as one. The tasks and board views are planned |
| A per-browser principal | The brief's browser acts as the person, through the terminal's op path. A second person is another credential nobody asked for |
| Copying the tool server's HTTP | Two copies of what keeps a request bounded would drift |

## Consequences

- Acting from the page is the next stage: every act is drawn, disabled, saying so, and `/x/command`, `/x/body` and
  `/x/link` already take what the page will send.
- A control link is the owner's to use: every browser on one acts as the session's person, and nothing tells a second
  person from the first. Refusing an address other than loopback on a plan-login session is not built.
- A runtime report, a goal and an agent's words each land in one chat, so a lead's chat with its child holds the reports
  about it from `runtime`, and the child's own words are in its chat with the person.
- Nothing here has run on macOS, in Firefox or in WebKit, or on a real model in the page.

## Evidence

- [swarmchat.md](../research/swarmchat.md): the wire contract, the overlay technique, the traps and the eleven implications.
- `tests/unit/web/`, `tests/integration/test_web.py`, `tests/e2e/test_web.py`. [web.md](../web.md) is the guide.
