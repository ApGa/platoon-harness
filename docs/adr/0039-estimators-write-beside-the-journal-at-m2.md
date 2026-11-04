# 0039. Estimators write rewards and credit beside the journal from M2

**Status:** Accepted, 2026-11-05

## Context

[ADR 0011](0011-annotations-beside-the-journal.md) put rewards, judgments and credit in `annotations.sqlite`, beside the journal,
and planned it for M3 with the Platoon bridge. The owner wants research estimators to write credit on M2 sessions before that bridge
exists, now that `contributors` and `lineage` say who the record ties to an outcome (ADR 0038). An estimate written there must never
read as a fact, and a reward nobody could score must never read as zero.

## Decision

- **The store.** `annotations.sqlite` in the session folder holds architecture section 11's table, `id`, `target`, `kind`,
  `producer`, `producer_version`, `params_hash`, `value`, `status`, `evidence`, `head_seq` and `wall_time`, with `scope`, unique on
  producer, version, params, target and kind. It is written with no runtime and no lock but the file's own, on a live session or a
  closed one, and no op, view or tool opens it, so nothing an agent can reach reads it.
- **Rewards and credit, and only those.** `kind` is `reward` or `credit`, and `scope` is `local` or `team`. `status` is required:
  `scored`, `invalid`, `error`, `cancelled` or `unscored`, and `value` is given when the status is `scored` and only then, so nothing
  unscored is zero.
- **About the trace it read.** `target` and each ref of `evidence` must name an event at or below `head_seq`, which may not pass the
  head, so a statement names the exact trace it is about. A range or a body's hash is refused, as the queries refuse them.
- **One way to write and read.** `Session.annotate` and `Session.annotations`, and the commands `platoon-harness annotate`, whose
  flags are made from the schema `Session.annotate` checks, as an op's are from its arguments, and `platoon-harness annotations`.
- **A second estimate goes beside the first.** The same statement again is answered with the first, and another under the same
  producer, version, params, target and kind is refused `conflict`, as a reused key is: a new version or other params write beside it.
- **No estimator ships.** Credit is an annotation by a named producer at a version. The SDK writes and reads statements and makes none.

## Alternatives considered

| Alternative | Why not |
|---|---|
| An op that writes an annotation | An op runs in the journal's writer, which a closed session has none of, and does no I/O |
| Annotations as events | ADR 0011: keeping them from agents would rest on a grant, and a closed journal would need a writer |
| Judged attribution and validated intervention as kinds now | Nobody asked for them yet, and folding them into `credit` would merge evidence types. They stay planned |
| Replacing a statement under the same key | It silently changes what an estimator said. A new version writes beside it |
| An estimator of our own, such as an even split over contributors | A heuristic with no reader, and an estimate presented by the harness itself reads as a fact |

## Consequences

- An estimator reads a closed copy with the four queries, carries the `head` they answered at as its `head_seq`, and writes beside
  any other estimator's rows. A client shows a value only with its producer and version.
- The second file travels with an export, as ADR 0011 said. Losing it loses statements about the record, never the record.
- Each statement checks its target and evidence through `lineage`, one query a ref, which a closed copy with stale views refuses
  until a writer has refolded them.
- Eligibility, attribution, the export and judged or validated evidence stay M3.

## Evidence

- `tests/unit/runtime/test_annotations.py`; `tests/unit/primitives/test_provenance.py`, `test_provenance_reads_no_annotation`;
  `tests/unit/cli/test_commands.py`, `test_annotate_is_made_from_the_schema_session_annotate_checks`;
  `tests/integration/test_cli.py`, `test_provenance_of_a_closed_session_from_the_command_line_and_credit_beside_it`.
- [Architecture sections 4 and 11](../architecture.md).
