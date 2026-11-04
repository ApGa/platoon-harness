# 0035. The board and the map over messages

**Status:** Accepted, 2026-11-04

## Context

[ADR 0027](0027-the-browser-on-our-backend.md) left SwarmChat's Board layout and Map disabled, since they ask `view_posts`
and `view_activity`, and it turned down a board of posts over messages because our boards are objects with versions, which
such a layout would read as. Both layouts are SwarmChat's own and need nothing but messages: a post is any message that
answers none, and the map is who is in which chat and how much each wrote, when. Two parts of them cannot be said over a
session. SwarmChat ranks hot and top by votes, which are reactions, and a session's messages take none. And a queue's or a
board's chat holds what it announced, not its tasks' state or its entries' versions.

## Decision

- **Both layouts are backed.** `view_posts` and `view_activity` answer from the projection in SwarmChat's shapes, and the
  overlay enables Board and Map. Posts come from one chat or from every channel and group, never a direct chat, and with
  `as` from that agent's chats alone, as upstream's do. Every time either gives is a message's time in the journal.
- **Unknown votes are null.** A post's `votes` is null. `view_posts` sorts new, the default, and active, and refuses hot
  and top, saying why. The page draws Hot and Top disabled, sorts an address that names one new, saying so, and draws each
  post's vote control disabled, with no count, since a 0 would say people had voted.
- **`more` says whether more follow.** It is true when a post past the page exists, where upstream's is true whenever a
  page is full. The shape is the same.
- **A queue's or a board's own view stays drawn and disabled.** Its chat, as a chat and as a board, has Tasks or Entries,
  disabled, saying that the tasks and board views, with each task's state and each entry's versions, are planned and that
  the chat holds what was announced. This answers ADR 0027's objection: the page says what the board of posts is not.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Hot and top over replies alone | It would rank by a formula that weighs votes, with every vote counted as none |
| `votes` 0, as upstream's shape has it | Unknown is not zero: a 0 says people looked and did not vote |
| The board layout off for a queue's or a board's chat | It holds real messages, the announcements, and the Tasks or Entries control already says what it is not |

## Consequences

- The tasks and board views come with the terminal's own, and replace the disabled control when they do.
- A person sees the session as an agent on the Board and the Map as everywhere else: a person and the runtime cannot be.

## Evidence

- `tests/unit/web/test_board.py`, a test per rule, and `tests/unit/web/test_conformance.py` over both replies.
- `tests/e2e/test_board.py`, in Chromium's headless shell.
