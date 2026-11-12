# RFC 0073: An agent's page shows its tool activity and live text outside any chat

| | |
|---|---|
| Status | Accepted, 2026-11-12 |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`calls.py`](../../packages/cli/src/platoon_harness_cli/calls.py), [`web/server.py`](../../packages/cli/src/platoon_harness_cli/web/server.py), [`web/overlay.js`](../../packages/cli/src/platoon_harness_cli/web/overlay.js), [architecture sections 5.6 and 12](../architecture.md#56-readers), [RFC 0027](0027-the-browser-on-our-backend.md), [RFC 0028](0028-acting-from-the-page.md) and [RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md) |
| Discussion | Decided by the maintainers on 2026-11-12 |
| Implementation | `feat: List an agent's tool calls on its page, a page at a time`; `feat: Show an agent's live text on its page, apart from its messages` |

## Summary

Tool activity, on an agent's page in the browser, opens a pane, `tools=` and the agent, which reads two new panes of `x_read`,
each of which a view link reaches and neither of which writes. `tools` is the agent's tool calls a page at a time, in the words
of `calls.py`: whole turns, newest first, as many as 100 calls take, each a heading over its calls, each call one line from its
first item to its last, and each spawn under the call whose id its anchor holds, through the join both clients share, or saying
it joins no known call. `saying` is what the agent is saying now, which the journal does not hold yet, and says so: `web` reads it
only while a page asks for it, holds its newest 20,000 characters, and lets it go with the runtime that said it. Neither enters a
chat. This amends RFC 0027, under which tools and live text never reached the page, and RFC 0028, which drew Tool activity
disabled.

## Motivation

A person needs an accessible view of an agent's tools on the page that does not flood conversation with low-level telemetry,
and to review tool calls without meeting dozens of token streams merged into one transcript. The terminal does both: its transcript draws an agent's calls, each spawn under
the call that made it ([`calls.py`](../../packages/cli/src/platoon_harness_cli/calls.py)), and the live text of the agent in
view below them, one tail at a time. The page does neither. [RFC 0027](0027-the-browser-on-our-backend.md) keeps thoughts,
tools, usage and live text out of every chat, rightly, since a chat is messages between people and agents, and
[RFC 0028](0028-acting-from-the-page.md) draws Tool activity on an agent's page disabled, saying it is not built. So a person
at the page sees what an agent said once its turn commits it, and never what it ran, what it spawned under which call, or
what it is saying now.

Two things make this more than drawing. A page of calls must not split a call from its end, or a spawn from its call, at a
page's edge, as the terminal's window keeps a call with what it spawned. And live text is no event: it is lossy, apart from
the journal, and per runtime ([architecture section 5.6](../architecture.md#56-readers)), so the page must say it is not in the
journal yet, `web` must not hold a reader for every agent of every session it serves, and what a runtime was saying must go
with it.

## Proposal

### 1. A pane of the agent's tool activity, read through `x_read`

Tool activity, on an agent's page, opens a pane of ours, which the address names, `tools=` and the agent, so Back and a reload
keep it and Esc or × closes it. It reads through two panes of `x_read` ([RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md)):

```text
POST /v1/x_read {"pane": "tools", "agent": "w1", "before": 412}   -> {"lines", "cursor"}
POST /v1/x_read {"pane": "saying", "agent": "w1", "version": 7}   -> {"version", "text", "about", "over"}
```

Each reads through the session's reads, `Session.page`, `Session.deltas` and `agent.status`, a query, where no op that writes
runs, on the owner's credential `web` holds, so a view link reaches both, as it reaches every pane but a diff, and nothing is
written through either. A name that is no agent's is refused `not_found`.

### 2. Tool calls a page at a time, whole turns of them

```python
PAGE = 100

@dataclass(frozen=True)
class Calls:
    lines: list[Line]     # newest first, as provenance.Line, each opening its event's provenance
    cursor: int | None    # the `before` of the page before it, or None once the journal's start is read

async def page(session: Session, agent: str, *, before: int | None = None) -> Calls: ...
```

`calls.page` reads back from `before`, or from the newest, through the agent's turn stream and every agent's own stream, where
a spawn is recorded, and takes whole turns, as many as `PAGE` calls take and one at least. Where a harness reports a call, its
end and the spawns it made within the turn that made it, no page splits a call from its end or a spawn from its call, and its
words need nothing from any other page; that each harness does is unverified, as the hard parts say. The newest page is led
by the head it was read at, which says that a call or a turn that ended since reads as it stood then: the pane reads it as
it opens and on Read again, and does not follow the journal (open question 2). Each turn is a heading, its id as its harness
gave it and how it ended, or `not ended` where the journal holds no end, over its calls, newest first:

- **A call** is one line, from the first of its items to the last, joined by the id its harness gave it: its words are what its
  first item says it was called with, and its kind how its last end says it ended, `completed`, `failed` or an approval's
  `allow` or `deny`, or `started` where the journal holds no end. One that did not complete, or that its approval denied, is a
  warning. A call that came under no id, as a scripted `Call` step's does, cannot be joined to its end, so each of its items is
  a line of its own, `unjoined`, saying its own phase and that no id joins it to its call's other items, never `started`, as
  whether the journal holds the call's end is unknown. Each counts as a call toward `PAGE`.
- **A spawn** stands under the call whose id its anchor holds, through `calls.Join`, the join the terminal's transcript draws by,
  whichever of the two the journal has first. One that joins no call of its turn, as OpenHands' and an `exec` harness's do, whose
  calls come through the shim and `ph` under ids no item holds, stands where the journal has it, saying it joins no known call.

A turn of more calls than `PAGE` is listed in its newest, saying how many it leaves out and that `platoon-harness events SESSION
--after SEQ` prints them among the session's other events, and the next page is the turn before it. A journal that holds no tool
item of the agent's says so, and that this is not to say it made no call: an `exec` harness, which acts through `ph`, reports
none. Each line is a button that follows into its event's provenance, as a link of the Provenance pane does, and Back comes
back. Read again reads the newest page again, and Read on draws the page before the last one drawn, below it.

### 3. Live text, held only while a pane asks, within a bounded tail

```python
class Saying:
    text: str         # what the agent said since the journal last took what it said: its newest 20,000 characters
    lost: bool        # some before them was lost on the way, or cut
    version: int      # moves with each change, across every agent and every runtime
```

The pane shows above the calls what the agent is saying now, labelled as not yet in the journal: its next item is what it said,
and a thought never enters a chat. `web` reads an agent's live text from a page's first ask for it, through `Session.deltas`, as
the terminal reads the agent in view, and holds what the agent said since the journal last took what it said, its newest `SHOWN`
characters, 20,000, as much as a message shows, led by an ellipsis where some before them was lost or cut. A page asks with the
version it shows, and the ask is held until the version moves, or for at most 25 s, the feed's hold. The page lets go of its ask
as the pane closes, which would otherwise hold one of the few connections a browser opens to `web`, and a hold of `web`'s, until
it moved. `web` lets the reader and its text go once 25 s pass with no ask held for it, so a closed pane costs nothing past
that, and no page holds a reader for an agent it does not show. A reader that ends while the agent and a runtime go on, as one
does on a link that is not the runtime's yet, is asked anew once; one that ends again holds the ask until the journal moves, for
at most 25 s, and says the text cannot be read now, so it is asked anew no faster than that. Where the agent has ended, the
answer says it says nothing more, and `over` stops the page's asking. Where no runtime holds the session, it says so and that
what was being said went with the runtime that said it, and the ask is held until a runtime takes the session up again, or for
25 s. A runtime that goes ends the reader, so its text goes with it, and the next runtime's text stands alone.

### 4. Neither enters a chat

The projection is unchanged: a chat holds no tool, thought, usage or live text (RFC 0027). The pane is apart from the chats, and
an agent's words still reach its chat with the person once its turn commits them.

## The hard parts

- **A call that crosses a turn.** Whole turns keep a call with its end and its spawns only where its harness reports all of
  them within the turn that made the call. The kernel refuses no item outside a turn, and that each harness keeps to it is
  UNVERIFIED for every path of every harness. A page closes a turn's group at its start, reading back, so an item recorded
  after its turn ended and before the next began stays with its own turn. One recorded after the next turn began stands in
  that turn's lines, as a line of its own, and a spawn there that joins a call of the turn before says it joins no known
  call.

## Alternatives

| Alternative | Why not |
|---|---|
| A page of a fixed number of events, or of calls cut anywhere | A call would show its start on one page and its end on another, and a spawn recorded before its call's item would say it joins no known call on one page while its call is on the next. Joining across pages needs the join's state in the cursor or in the page's script, a second copy of `calls.Join` |
| Paging inside a turn of more than `PAGE` calls | The same split, at the one turn that would need it, and its heading would have no end to say. The pane says what it leaves out and the command that prints it |
| The page's script joining calls to spawns and holding live text | Two copies of one rule, the join and the tail, which would drift, as RFC 0028 found for cutting a person's text. Python says both, as every pane of ours reads in Python's words |
| `Session.deltas` taking `after`, so `web` holds nothing between asks | A parameter on the public API for one client, and the page would keep the tail in its script. A fresh reader also cannot tell a page that its text was taken by the journal until something new is said |
| A reader of every agent's live text for as long as `web` serves | Its cost would grow with the agents, read or not. Held only while asked, it grows with the panes open |
| Live text in the agent's chat with the person, below its messages | It is not a message, and the journal does not hold it: a chat is what was sent (RFC 0027) |
| Calls and live text in one pane of `x_read` | One is a page read on request, the other an ask held until it moves |

## Consequences

- A person at the page reads an agent's tool calls, each spawn under its call or said to join none, and what it is saying now,
  on a view link and on history too, where the calls are read from the journal and nothing is said.
- Each page of calls reads back through the journal to a turn's start, so a long turn in a busy session costs a scan of every
  event since it began, at most 4,096 a read. Nobody has measured it at scale yet.
- A call the journal holds no end of reads `started`, never `running`: whether it still runs is unknown.
- `web` holds at most one reader, and 20,000 characters, for each agent whose pane is open, until 25 s after no ask is held
  for it.
- Each held ask counts against the 64 requests `web` holds at once, with the feed's and a diff's.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 tool calls | `calls.page`, `x_read`'s `tools` pane, and the Tool activity pane on an agent's page | `test_an_agent_s_page_lists_its_tool_calls_a_page_at_a_time`, `test_a_spawn_is_listed_under_the_call_whose_id_its_anchor_holds_or_says_it_joins_none`, `test_activity_on_a_view_link_writes_nothing` | `feat: List an agent's tool calls on its page, a page at a time` |
| M2 live text | `x_read`'s `saying` pane, held while asked and bounded, drawn above the calls | `test_live_text_is_drawn_apart_from_messages_and_said_not_yet_in_the_journal`, `test_live_text_goes_with_the_runtime_that_said_it`, `test_live_text_is_held_only_while_its_pane_is_open_and_bounded` | `feat: Show an agent's live text on its page, apart from its messages` |

## Open questions

1. Open: should a call's line open its input and its output, the bodies its items carry? Today a line opens its event's
   provenance, and the bodies are read with `platoon-harness blob`.
2. Open: should the pane follow new calls as they come, as the feed's `x_moved` makes a queue's pane read again? Today Read again reads
   them, and the newest page says the head it was read at. Needed only if a person asks.
3. Open: what does a page of calls cost on a busy session's long turn? The scale test does not measure it yet, and could beside
   the other reads.

## Evidence

- `tests/unit/cli/test_calls.py`: `test_an_agent_s_calls_come_a_page_of_whole_turns_at_a_time_newest_first`,
  `test_the_newest_page_says_the_head_it_was_read_at_and_no_tool_item_is_not_no_call`,
  `test_a_spawn_is_listed_under_the_call_whose_id_its_anchor_holds_or_where_it_stands_joining_none` and
  `test_a_turn_of_more_calls_than_a_page_holds_is_listed_in_its_newest_saying_what_prints_the_rest`, over sessions on a scripted
  harness.
- `tests/unit/web/test_server.py`: `test_activity_on_a_view_link_writes_nothing`,
  `test_activity_on_history_lists_the_calls_the_journal_holds_and_says_nothing_is_being_said`,
  `test_live_text_is_held_only_while_its_pane_is_open_and_bounded` and
  `test_live_text_whose_reader_keeps_ending_is_asked_anew_once_and_then_held`.
- `tests/e2e/test_activity.py`, in Chromium and Firefox here, and in WebKit in CI, with
  `test_closing_tool_activity_lets_go_of_its_ask_for_live_text`, which switches between two agents eight times.
- The join and the tail it builds on: `tests/unit/cli/test_calls.py`'s join tests and `tests/unit/kernel/test_readers.py`, as
  [STATUS](../STATUS.md) cites them. No real harness's session has been drawn in the pane yet.
