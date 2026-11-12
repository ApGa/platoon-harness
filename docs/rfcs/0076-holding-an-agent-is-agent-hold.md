# RFC 0076: Holding an agent is `agent hold`, and a takeover drives its terminal

| | |
|---|---|
| Status | Accepted, 2026-11-08 |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`primitives/lifecycle.py`](../../packages/sdk/src/platoon_harness/primitives/lifecycle.py), [`primitives/reports.py`](../../packages/sdk/src/platoon_harness/primitives/reports.py), [`tui/keymap.py`](../../packages/cli/src/platoon_harness_cli/tui/keymap.py), [architecture sections 7](../architecture.md#lifecycle) and [11](../architecture.md#11-provenance), [RFC 0037](0037-an-offer-is-confirmed-only-by-its-harness.md) and [RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md) |
| Discussion | Decided by the maintainers on 2026-11-08 |
| Implementation | `refactor!: Rename agent takeover to agent hold, as it only holds deliveries` |

## Summary

The op that holds an agent's deliveries until `agent.release` returns it is `agent.hold`, where it was `agent.takeover`, with
its command `platoon-harness agent hold`, its method `Session.hold` and its gap `hold`. What it does is unchanged. The word
takeover is left to what it promised: a person driving an agent's own terminal, the terminal UI's `/takeover`, which stays
planned. No alias is kept, so a journal recorded before the rename keeps the old names, and the code reads them as they stand.

## Motivation

`agent.takeover` holds an agent's deliveries, already requested ones too, until `agent.release` returns it, interrupting a turn
under way and recording a gap where the hold begins. Its name promised a person driving the agent's native session, which is
planned and not built ([STATUS](../STATUS.md#terminal-ui-platoon_harness_clitui)). So its help said that driving was not built,
and the terminal UI's `/takeover`, the feature the name promised, said that `agent takeover` held deliveries and no more: two
things called takeover, one built and one not, each saying it was not the other. Everything else the op writes already says
hold: its event is `agent.held`, the state it leaves is `held`, and the roster's `held_by` names who holds the agent.

## Proposal

### 1. The names

| Was | Is |
|---|---|
| `agent.takeover`, and `lifecycle.takeover` | `agent.hold`, and `lifecycle.hold` |
| `platoon-harness agent takeover` | `platoon-harness agent hold` |
| `Session.takeover(agent)` | `Session.hold(agent)` |
| The gap `takeover` in `Gap` and `GAPS` | The gap `hold`, of the same plane, writer and mark: control, the runtime, and content could come through |

`agent.release`, `agent.held`, `agent.released`, the state `held`, `held_by` and every refusal's code stay. The op's help says
what it does and no longer that driving the native session is not built, as its name no longer promises it. The terminal's
Alt+T and `/takeover` stay planned, saying that `agent hold` holds deliveries and no more. Nothing is released, and AGENTS.md
forbids compatibility shims, so no old name is kept beside the new one.

### 2. A journal recorded before

A journal names the op in the outcome each of its commands carries and in an `op.refused`, and names the gap in the data and
gist of its `gap.recorded`. A journal is append-only, so these keep the old names, and the code reads them as they stand:

- The session opens, by `session resume`, `Session.resume` or a guest's attach, and its views fold as before: no view changes
  shape, and `Gaps` keeps a gap's kind as text.
- An agent held then stays held, as `agent.held` is unchanged, until `agent.release`.
- Its gap reads `takeover` wherever a gap's kind is said: in `exposure`'s incidents, in `session.ending` and `session.metrics`,
  in the terminal's transcript and inspector, and in the provenance lines the command line and the page share. `GAPS` holds no
  `takeover`, and provenance takes a kind outside the closed set as one content could come through, which `hold` is, so every
  answer is the one it was.
- A new `agent.takeover` is refused `not_found`, and `agent takeover` is an unknown command, exit 64. A command the journal
  answered retried under its key, with its op and arguments, is answered from the journal, as any retry is, since the kernel
  looks a key up before the op.

`WIRE_PROTOCOL` stays 2. `GAPS` names the runtime alone as this gap's writer, and a wire program's report of the gap
`takeover` is now answered `INVALID_PARAMS`, as any report outside the vocabulary is.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep `agent takeover`, its help saying driving is not built | Two things named takeover, each saying it is not the other, and the terminal-driving feature would need another name once built |
| `agent pause` | The record already says hold: `agent.held`, `held` and `held_by`. A pause reads as stopping a turn, which `agent.interrupt` does |
| Keep `agent.takeover` as an alias | A compatibility shim, which AGENTS.md forbids, for a project nothing has released |
| Rewrite an old journal's `takeover`, or fold it as `hold` | The journal is the only truth, and a fold that renames what it holds says it held what it did not. Read as it stands, it gives the same answers |
| Keep `takeover` in `GAPS` beside `hold` | A member nothing writes, kept for old journals, which provenance already reads as a gap content could come through |

## Consequences

- A script that calls `Session.takeover`, `agent.takeover` or `agent takeover` breaks, loudly: an `AttributeError`, `not_found`,
  or exit 64 naming `hold` among the commands.
- A count of gaps by kind across sessions finds `takeover` in a journal from before and `hold` after: one kind under two names.
- `hold` also names `wait`'s `hold`, which keeps an agent's own call open. Their places keep them apart: an op of the `agent`
  namespace, and an argument of `wait`.
- Takeover is free for driving an agent's own terminal, which stays planned.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 The rename | Section 1's names, the command line's reference, the terminal's keymap, architecture and STATUS | `tests/unit/primitives/test_lifecycle.py::test_hold_holds_deliveries_until_release_and_records_a_gap`, `tests/unit/primitives/test_gaps.py::test_a_hold_records_its_gap_where_it_begins` and `::test_a_journal_from_before_the_rename_keeps_its_gap_named_takeover`, `tests/unit/runtime/test_host.py::test_deliveries_wait_while_an_agent_is_held`, and the reference and keymap tests | |

## Open questions

1. Open: what a takeover does once it is built, and whether it holds an agent first, is for the RFC that builds it.

## Evidence

- `git grep -n -i takeover` at 1f72a37: outside history, the op's name, its function, its method, the gap's name, the
  terminal's planned key and the docs and tests that name them, while its event, state and roster field said held.
- `tests/unit/primitives/test_gaps.py::test_a_journal_from_before_the_rename_keeps_its_gap_named_takeover` shows section 2 on a
  journal whose hold was recorded as `agent.takeover` recorded it.
- `_incident` in [`primitives/provenance.py`](../../packages/sdk/src/platoon_harness/primitives/provenance.py) takes a kind outside
  `GAPS` as one content could come through, and `Kernel._execute` in
  [`kernel/kernel.py`](../../packages/sdk/src/platoon_harness/kernel/kernel.py) answers a retried key before it looks up the op.
