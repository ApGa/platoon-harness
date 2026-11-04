# 0040. Pi names what landed and which call made a tool call

**Status:** Accepted, 2026-11-05

## Context

[ADR 0037](0037-an-offer-is-confirmed-only-by-its-harness.md) left pi with two holes in what its reports could say. An input pi took
was reported with no `native_id`, so a compaction, whose `forgotten` pi names by entry ids, could never mark a handover `forgot` or
`kept`. And our tools reach pi through the stdio shim, which sent a fresh `platoon-harness/callId` with each call, an id no item
holds: a read through pi stayed unconfirmed, and a pi tool call joined no model call, so every answer about a pi agent's event was
bounded at its commit, which can count a read the same model call chose as below it.

Pi 1.5.0 names neither in any frame. Its MCP client puts only `progressToken` in a call's `_meta`, and a user message's entry is
made after pi has said `message_end`, so neither `message_start` nor `message_end` holds its id. Pi does say both when asked or
let: `get_entries` with `since` lists the entries after one, and the `tool_call` hook of an extension sees `toolCallId` after pi
has checked a call's arguments and before the tool runs, with the arguments mutable and a copy of what the transcript holds.

## Decision

- **A landed input names its entry.** Pi writes a user message down as an entry once that message has ended, before it reads
  another command. At that `message_end` the driver asks `get_entries` for what came after the last entry it saw, and reports the
  input under the id of the entry holding its text, as `InputDelivered.native_id`, the id a compaction would name it by. Where pi
  names none, as when it refuses the ask or exits first, the input is reported with no id, as before.
- **Pi's order is kept.** A fast model can answer before pi answers the ask, so whatever pi says after an input waits behind it,
  at its place, until the input is named. One ask is out at a time: pi answers after what it said before, so an answer holds every
  entry whose message ended before it. What is still waiting when pi stops goes on with no id, before the exit.
- **A tool call goes under pi's own id.** Our extension puts `{"pi/toolCallId": toolCallId}` among the arguments of a call of ours,
  as `_meta`, and the shim moves a `_meta` it finds among a call's arguments to where MCP keeps it, beside what the client put
  there. The server takes `pi/toolCallId` as a harness's anchor, beside Claude Code's `claudecode/toolUseId` and Codex's `callId`,
  so the op's anchor is the `native_id` of pi's tool item, whose `call_id` is the `responseId` of the call that chose it.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Asking for the entry at `message_start` | Pi writes the entry down only after `message_end`, and an extension's handler between the two can let a command in first |
| Reporting the input at once and its id later | One confirmation per offer: a second report would be a second way to confirm |
| Reporting the input once named, wherever that falls | It would say the harness took the input after a model call that already held it, an order pi never said |
| Mapping `forgotten` entries back to our inputs by their text at compaction | `forgotten` holds the harness's ids verbatim; an input's id is what it is said to land under |
| Reading pi's session file | A read loop that waits on a file no longer only drains the pipe |
| Our own tools registered by the extension, over HTTP with `_meta` | A second tool path for one harness, beside the shim the OpenHands worker shares |
| The shim taking only `pi/toolCallId` from the arguments | `_meta` is MCP's own name for what a call carries beside its arguments, so the rule is one sentence for any harness. No `_meta` a model writes gets through: OpenHands refuses an argument our schemas do not declare, and on pi our extension writes `_meta` on every call of ours after pi's own check |

## Consequences

- A read through pi is confirmed by the tool item that holds its result, and a pi tool call joins the model call that chose it,
  so an answer about a pi agent's event is bounded at that call, `call`. Pi's bound rests on `message_end` coming before that
  call's tool items, which it did on FakeModel.
- A compaction marks a handover pi took `forgot` or `kept`. A read is still `unsaid`, as for every harness.
- Each input costs one `get_entries` round trip, of what is new since the last entry seen, and what pi says after it is held for
  that long.
- With a client id, two identical calls in one turn are two calls, as through the shim's own ids before. Two calls under one id
  are one, as for Claude Code: FakeModel gives every call the id `call_1` unless told otherwise.
- OpenHands' calls still go under the shim's own id, and its inputs still carry none: its worker would have to report both.

## Evidence

- On pi 1.5.0 against FakeModel, in `tests/integration/test_pi.py`: each input's `native_id` was the id `get_entries` holds it
  under, and the one a compaction named forgotten, the goal's and a handover's
  (`test_a_compaction_reports_its_call_what_it_forgot_and_its_summary`); a handover a compaction forgot was marked `forgot` and still
  seen (`test_a_handover_a_compaction_forgot_is_marked_forgot_by_the_entry_it_landed_as`); `tool_item_carries_its_anchor` passed,
  where it had skipped; a read was confirmed by its tool item, and a spawn's anchor was its call's tool item's id.
- On the stand-in, `tests/unit/drivers/test_pi.py`: a turn said whole before the driver's ask was answered kept pi's order, and an
  ask refused, or a pi that exited, left the input with no id in its place.
- Pi's source, read and not copied: `AgentSession._handleAgentEvent` emits `message_end` and then appends the entry with no await
  between; `validateToolArguments` clones what a tool is handed; the MCP client's `callTool` sends `_meta` with `progressToken` alone.
- [compatibility.md](../compatibility.md), pi and Provenance per harness. [Architecture sections 6 and 9.5](../architecture.md).
