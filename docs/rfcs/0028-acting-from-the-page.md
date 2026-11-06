# RFC 0028: Acting from the page

| | |
|---|---|
| Status | Accepted, 2026-11-04; amended by [RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md) |

**Amended by [RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md)**: Provenance among a
message's actions is built, and opens a pane.

## Summary

Each act keeps its key until answered, across a reload; one cut in Python for both clients; Needs you is the runtime's `attention`; asking first in the page

## Motivation

[RFC 0027](0027-the-browser-on-our-backend.md) drew every act on SwarmChat's page disabled and left `/x/command`, `/x/body`
and `/x/link` waiting for them. Acting needs four things that page does not have: a key a retry can keep, which must
outlive a lost connection and a reload; a way to cut a person's long text that cannot drift from the terminal's; somewhere
to list what waits on the person; and a way to ask before an act nothing takes back. A browser also loses answers: a
request can reach `web` and its answer never reach the page.

## Proposal

- **One key per act, kept until answered.** The page makes a key for each draft sent or button pressed, and keeps the act,
  with its key, in the tab's own storage until it is answered. Until then it sends it again, every two seconds, after a
  lost connection, and when the page loads after a reload or from a new control link in the same tab. A view link sends
  none of it and says what waits, since it acts on nothing and its refusal would read as the act's. `web` puts the key under
  `web/` and nothing else, and the kernel answers a key it has seen with its first answer, so the retry is one operation
  whichever link sends it. A refusal is an answer, and so is a failure of `web`'s, which says whether the act took effect is
  unknown; a page whose session ended was answered nothing, so its act stays kept.
- **One cut, in Python.** `cut(text)` in the CLI's `ops` module makes a person's text a gist and a body, and the terminal
  and `web` both call it: the page sends what was typed as the gist, and `web` cuts it there, before `Session.submit`. A long
  text beside a file is refused by the same function, with the terminal's words, before anything is journaled.
- **Needs you is the runtime's view.** The entry reads `attention.list`, a query, through `/x/command`, after each change the
  feed brings, at most once a second, and draws each row's actions as the view offers them, with the version each was drawn
  from. A mention is left out, as the page keeps no marks to say which were read.
- **Asked in the page.** An op in `CONFIRMED` asks once, in a popover beside its button, drawn with SwarmChat's own template.
- **A reply cites an entry.** Reply opens the message's thread with a composer that sends `reply_to`, the message's journal
  ref. What a harness said in its turn is no entry a reply can cite, so its Reply is disabled, saying so.
- **What is not built is drawn.** Tool activity and Review changes on an agent's page and Provenance among a message's
  actions are disabled, saying why, beside the layouts RFC 0027 disabled, so nothing the brief asks the page for is
  missing without a word. Links of either kind are made from the person's own page, through `/x/link`.
- **What the page draws, the page says.** Each agent's status stands beside its name in the people list, where SwarmChat
  draws someone's first field, and seeing as anyone but an agent is drawn disabled, as the person's page already did.

## Alternatives

| Alternative | Why not |
|---|---|
| A key in memory only | A reload while an answer was lost would drop the act, or send it again under a new key, which is two operations |
| The cut in the page's script, from a limit `web` says | Two copies of one rule, one in Python and one in JavaScript, whose characters differ in counting, could drift |
| A route of `web`'s own for what needs the person | It would be a second reading of `attention`; `/x/command` already answers a query from a control link |
| The browser's own confirm dialog | It blocks the page, looks like no part of it, and a test cannot see what it asked |
| A reply to an agent's words naming its turn | A turn is no entry, and `reply_to` that names none is refused, so the act would only ever fail |

## Consequences

- A view link reads attention nowhere, as it reaches no `/x/` route, so its Needs you entry is disabled, saying why.
- An act a reload left unanswered is sent again when the page loads, and its outcome is a notice, since its composer or
  button has gone.
- The page's count of places can be lower than the terminal's by its unread mentions.

## Evidence

- `tests/e2e/test_acts.py`, `test_guards.py`, `test_follow.py` and `test_harnesses.py`, in Chromium's headless shell.
- `tests/unit/web/test_server.py`, `test_a_message_too_long_for_a_gist_is_cut_as_the_terminal_cuts_it`.
- `tests/live/test_web.py`, live run 58, on a Claude Code lead and a Codex worker: see STATUS.
