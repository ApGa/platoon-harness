# RFC 0047: An empty read names what was already handed over

| | |
|---|---|
| Status | Accepted, 2026-11-05 |

## Summary

An agent's read that finds nothing past its cursor names, in `next`, what the offer that last moved that cursor handed over there and the `after` that reads it again, so an empty page is never taken for an empty channel

## Motivation

A wake hands an agent what woke it and moves its cursor past that, as section 7 of the architecture says a handover does, so a
`message_read` right after it finds nothing new and answered `{entries: [], cursor, behind: 0}`. Codex models open a woken turn with
such a read: in 4 of 6 woken helper turns in live runs 34 to 39, and once, woken by a memo, a worker read `#memo`, got nothing, and
said there were none ([the real-harness spike](../research/spikes/real-harness.md), section 16 and its lessons). The page was empty;
the channel was not. Claude Code did this in none of 17 woken turns.

## Proposal

- **A read of an agent's own that finds nothing past its cursor names what was already handed over there.** Its result gains `next`:
  the refs of the entries the offer that last moved that cursor handed over on that stream, by the refs the agent was shown them by,
  which its filter would have shown, and the `after` that reads them again, in the words of its surface. One that a read of its own
  moved names nothing, as that read showed what it gave. So does a read with `after`, which asked for what it got, and a person's,
  who holds no cursor. A read whose filter passed over a new entry found something past its cursor, so it is told nothing of the
  kind, and `behind` counts what it passed over.
- **A cursor keeps the offer that last moved it on,** a column of `Deliveries`, at view version 12, and loses it when a failed
  handover steps the cursor back, as that queues the entries again and the next read shows them.
- **Nothing else changes.** The handover's text, the preamble and every description stay as they were: the preamble and the tool
  list are in every request under a ceiling, and the place a wrong conclusion is drawn is the empty page.

## Alternatives

| Alternative | Why not |
|---|---|
| A read right after a wake starting from before the wake | It would show the entries twice, ack what the harness may not have landed, and make a cursor mean two things |
| A sentence in the handover, or in the preamble, saying not to read | Every request pays for it, a model that reads anyway still meets an empty page, and the description of a read already says where it starts |
| Naming every entry a handover gave and no result showed | An agent that never reads would be told of every entry since its start, and `after` would read them all again |
| Finding the offer from `context/<agent>` or by scanning offers | Unbounded in a long session, inside a write; one column answers it at once |
| A description of `next` in `message.read`'s own words | About 120 bytes in every request of every agent holding the tool, for a field that says what it is when it comes |

## Consequences

- An agent can tell an empty page from an empty channel, and read again what it was handed, from the page itself.
- `Deliveries` refolds once, at version 12, on a session from before.
- Whether a model reads less, or reads the empty page right, is a matter for live runs, not of this rule.

## Evidence

- `tests/unit/primitives/test_messages.py`, `test_a_read_right_after_a_wake_names_what_the_wake_handed_over` and
  `test_an_empty_read_names_only_what_a_handover_gave_and_the_read_would_show`, which a filtered read that passed over a new entry
  is among.
- `tests/unit/tools/test_mcp.py`, `test_an_empty_read_after_a_wake_names_what_it_handed_over_as_its_surface_does`, on the `mcp`,
  `mcp__<ns>` and `ph` surfaces.
- `tests/live/test_reads.py`, live, run 79, on `gpt-6-luna` at low effort, 7 calls: woken by a memo and asked to read `#memo`,
  the model read, was told `Nothing is new here past what was already handed to you: channel/memo@1`, read again with `after` 0
  as told, and answered with the memo's code word; in its next two woken turns it read with `after` 0 at once. One run.
