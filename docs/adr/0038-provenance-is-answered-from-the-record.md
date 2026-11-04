# 0038. Provenance is answered from the record, one hop at a time, and never as credit

**Status:** Accepted, 2026-11-05

## Context

[ADR 0036](0036-one-ref-names-what-a-model-is-shown.md) and [ADR 0037](0037-an-offer-is-confirmed-only-by-its-harness.md) made the
record able to say what reached an agent and what an agent claimed: one ref per act, citations checked and kept as claims, offers
confirmed only by a harness's own report, makers stamped, and gaps placed where they began. Nothing could ask it yet. Provenance is
to be a selling point of the harness, and credit research wants to know which agents contributed to an outcome, so the record has to
answer for people and programs, live and on a closed copy, without ever presenting a claim as evidence, an estimate as a fact or
unknown as zero. [ADR 0010](0010-provenance.md) sketched `lineage` returning whole paths and a `why` command; neither was built.

## Decision

- **Three views index the references events already hold.** `Exposures` holds each item an offer named, by the event it names, each
  offer with how it was made and the tool call it came under, each confirmation, each compaction and each start's declared coverage,
  levels and assurance. `References` holds what cites an event, what follows from one, which commits name one a parent, and which of
  an agent's events came under one tool call's id. `Calls` holds each model call by its harness's id, each tool item by its own, and
  where each turn began and who drove it. `Gaps` becomes an index of every incident gap by where it began. The graph is still not
  stored: backward edges are read from each event, and the views serve forward, per-agent and join lookups.
- **Four queries, for people and programs and no agent's tool.** Each is a query op with `tool=False`, a `Session` method returning a
  typed answer, and a derived command:
  - `exposure(agent, ref, before)` answers `Seen`, with each confirmed offer, what it showed, its evidence and each compaction since
    marked `forgot`, `kept` or `unsaid`; `NotSeen`; or `Unknown`, with the offers never confirmed, the surfaces no result proves
    observed and the gaps content could have come through. Never a boolean.
  - `lineage(ref)` is one hop back: the maker, its turn, the model call that chose the event, each citation with its citer's
    exposure, each cause, the previous version or a commit's parents, and a page of the maker's offers and gaps, newest first, with
    true totals.
  - `uses(ref)` is one hop forward: what cites it, what follows from it, its next version or child commits, and who was offered it.
  - `contributors(ref)` walks back from an outcome along citations, causes and ancestry, at most 4096 events, and names each maker it
    reaches in the order it reached them, with the kinds that reached each, and apart from them each maker whose events were only
    offered to a walked maker. It weighs and ranks nobody.
- **The bound is on the agent's own report stream.** An answer about an event an agent made counts what its harness reported taking
  before the model call that chose that event, joined through the op's anchor, the tool item that holds it and that item's call id.
  With no call joined it counts what was reported before the event's commit, and says `commit`. A question about an event made by
  someone else is bounded at its commit, as two report streams have no order between them.
- **Nothing answers `NotSeen` yet.** `NotSeen` needs every surface proved observed by a stored conformance result, and no check proves
  one, so the queries pass none: every negative answer is `Unknown`, and an agent with a shell never answers `NotSeen`. The rule is one
  pure function, `decide`, which a test drives with proved coverage given directly.
- **Every answer says its `head` and whether it is `open`**, the turn its event was made in not yet ended, since a later report can
  still confirm an offer or join a call.
- **A closed copy answers alike, or refuses naming its fix.** A read-only kernel folds nothing, so a query on a copy whose views are
  behind its journal is refused `unavailable`, naming the views and saying that a writer refolds them as it opens and writes no event.
- **Git ancestry is `ancestry`, and a commit is its workspace's.** A commit's parents are ancestry, its `Informed-By` trailers that
  resolved are its declaration, and the two never merge. A commit's maker is the agent whose workspace's reflog made it, and nobody,
  `None`, when that was the shared one or no single workspace did.

Where the design was wrong in a detail, this keeps its rules and changes the least:

- The design named the forward index `Uses`, after the query, and the answer type `Uses` too. One name cannot be both, so the view is
  `References`, for what it holds.
- The design kept each offered event's maker in `Exposures`. A fold sees one event (law 2), so an answer finds an offered event's
  maker by its ref, which the journal's unique index serves.
- The design kept running ordinals so that "handed" and "confirmed" below a bound were one lookup. They cost the writer a read per
  offer and per confirmation, so the counts are index ranges read when asked.
- Turn starts live in `Calls`, beside the calls and items whose turn they open, so that "who drove this turn" needs no stream scan.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Whole paths from `lineage`, or a depth parameter | Unbounded. A walk is asking again, one hop at a time, and `contributors` is the one bounded walk |
| `platoon-harness why` | A second way to ask what `lineage` answers |
| Contributors as a walk each client makes over `lineage` | Clients compute nothing (section 12), and three clients would walk three ways |
| Walking through observed edges | Being handed something is not using it, and that walk would be unbounded. Those makers are listed apart |
| Shares, weights or ranks in `contributors` | Estimates, which are annotations by a named producer (ADR 0011) |
| `NotSeen` from declared coverage, or from isolated assurance | A driver's word is no proof, and an isolated harness keeps a shell |
| A test-only coverage check that makes `NotSeen` reachable | Speculation: the pure function is tested with proved coverage given directly |
| Folding stale views into a temporary schema on each read-only open | A kernel feature with one user, costing a whole-journal pass per open |
| Comparing a read's offer, committed over HTTP, with a model call reported on stdout | Two streams with no order between them: it can count a sibling read as below the write its call chose |

## Consequences

- At M2 a negative answer about Claude Code, Codex, pi, OpenHands or `exec` is always `Unknown`, and says why.
- Claude Code's tool calls join their model calls, so its answers are bounded at the call. Codex's reach their script's item and no
  call, and pi's, OpenHands' and `exec`'s reach nothing, so theirs are bounded at the commit, which can count a read the same model call
  chose as below, and says `commit`.
- A compaction is `unsaid` for every read, and for every handover on a harness that names nothing it forgot, which is Claude Code and
  Codex today.
- Credit stays an annotation: `contributors` says who the record ties to an outcome and how, and an estimator writes beside it.
- The writer pays one row per offered item, offer, confirmation, citation, cause, anchored agent event, tool item, model call and turn.
  In the reference closed loop of a trivial op the views cost nothing measurable. In a loop made only of reads and citations, where
  every command writes provenance, they cost about 6% (see the evidence), against a proposed budget of 5%.

## Evidence

- `tests/unit/primitives/test_provenance.py`: `test_the_provenance_scenario`, the acceptance case;
  `test_exposure_agrees_with_a_brute_force_reading_of_the_journal`, a hypothesis property that also passed at 600 examples;
  `test_provenance_answers_alike_after_a_rebuild_and_on_a_closed_copy`; `test_a_closed_copy_with_stale_views_is_refused_naming_the_fix`;
  `test_not_seen_needs_proved_coverage_and_no_gap_below_the_bound`; `test_no_agent_answers_not_seen_at_m2`; and the rest named in
  STATUS. `tests/integration/test_cli.py`, `test_provenance_of_a_closed_session_from_the_command_line`.
- Writer throughput, measured on the shared login node at load 27 to 64, each run 5 s, alternated. A trivial op with 256 in flight:
  10,290, 10,327 and 10,454 commands/s with the views against 10,382, 10,578 and 10,304 without. A loop of 32 workers, each a citing
  send, a read under a tool call's id and that tool item's completion: 2,524, 2,630, 2,621 and 2,630 commands/s with the views against
  2,760, 2,719, 2,777 and 2,769 without, after `Exposures` dropped its ordinals, which had cost about 8% of that loop.
- [Architecture section 11](../architecture.md).
