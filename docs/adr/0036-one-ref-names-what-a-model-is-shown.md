# 0036. One ref names what a model is shown, and a citation is checked and kept as a claim

**Status:** Accepted, 2026-11-04. Extended by [0042](0042-agents-are-asked-to-cite-by-their-template.md): the `{citing}` slot
asks agents to cite, and by [0041](0041-a-commit-cites-what-informed-it-by-its-ref.md): a commit cites an event by its ref.

## Context

Provenance is to be a selling point of the harness: which agents contributed to an outcome is to be read from the record. A
citation is the cheapest edge an agent can give, and models copy what they are shown. Before this, what they were shown named one
act several ways. A body was a 71-character hash, which names bytes and no act, so a citation of one named no maker, and two
events could carry one body. A board write reached its readers as an announce on the channel's own stream, so a wake handed over
`board/notes@1` while the write was `board/notes/spec@1`, and exposure keyed by event missed every woken reader. A child's report
and a goal told again after a crash were the runtime's copies under refs of their own. A task's result, a spawn and a finish
returned no ref at all, and `based_on` was checked only to exist: `agent/bob@1#L999-1000`, `#L5-3` and `#banana` were taken.

## Decision

- **One ref form.** A ref is `stream@version`, with `#La-b` for lines of that event's body, and it is the one form a citation
  takes. An event's body is the body its data names `body`, so `agent.instructed` names its text `body` at payload version 2.
  Every result, handover, notice and refusal a model sees names what it shows by a ref, and none holds a body's hash: message
  rows say `body: true|false`, `rest` is an event ref with a range, and `blob.get` takes an event ref.
- **A carried message is shown by what it carries.** An announce of a board or queue write, the monitor's report of a child (its
  `agent.finished`, its turn's last message, or else the `turn.ended` or `agent.ended`) and a goal told again (`agent/<x>@1`) name
  the event whose words they carry as their `cause`, and are shown and handed over by its ref. `reply_to` finds an entry by the ref
  it was shown by.
- **Refs come back from every write of content**, and `task.claim` and `task.list` name a task by its `task.added` ref and a
  result by `result_ref`.
- **`based_on` on all eight writes of content**: `message.send`, `board.post`, `board.revise`, `task.add`, `task.complete`,
  `task.fail`, `agent.spawn` and `agent.finish`. A citation must name an existing event, and a range lines of that event's text
  body, or the whole write is refused naming the ref: `not_found` for a missing event, `invalid` for a body's hash, a malformed
  range, lines that do not exist, or a range on an event with no body. A body in `blobs/`, which an op cannot read, keeps its range
  as given. A citation of something its citer was never handed is kept as its claim: whether it was handed is exposure's answer.
  So a citation says whether the event it names exists, even on a stream its citer may not read, and never what that event holds.
  The check reads each ref, each event and each body once, and refuses a `based_on` too long for an event before it reads any.
- **A spawn is its spawner's.** `agent.spawned`, payload version 3, carries the spawner as its envelope agent, so its turn and
  context version are the spawner's and a citation on it is judged against what the spawner was handed. The child's own events
  stay the child's.
- **`blob.get` reads what its caller was handed or made.** An agent reads on in the body of an event offered to it or of its own
  making, and any other is `not_found`, as a miss is, so a ref is no oracle. A person or a program reads any. The tool plane reads
  a body in `blobs/` through `blob.hash`, a runtime-only query, so the hash never reaches a model.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keeping hashes in what models see | Two forms, and a citation of a hash names bytes and no maker |
| A query-time rule that an offer of an announce is an offer of the write it announces | Two refs for one act, and models would cite the announce |
| No data field for what a message carries, its `cause` alone | A fold sees one event (law 2), and cannot turn a cause's seq into the ref it must show. `carries` holds that ref, and `cause` names the same event for whoever walks the graph |
| Refusing a citation of what its citer was never handed | It makes declared a subset of observed, and loses the claim that credit research wants to compare with exposure |
| Keeping a write and dropping a citation that fails | It silently loses a claim |
| Grants on an event's stream deciding `blob.get` | A group member would read on in an entry never addressed to it, and carried events live on streams no read op grants |
| Refusing a citation of an event on a stream its citer may not read, in a denial's words, so existence never shows | It refuses the claim declared exposure exists to compare, and a citation discloses a version, never content |

## Consequences

- One act has one ref, so exposure, uses and contributors key on events with no inference.
- Every wake reads differently, and a journal from before message payload 3 and offer payload 3 names announces and bodies its old
  way, which exposure cannot tie to an event and says so.
- A bad citation costs a refused write and a retry. The refusal says to cite a `ref` that was given, or to leave it out.
- Asking agents to cite is the next stage's `{citing}` slot, so tool descriptions describe and never ask.

## Evidence

- The design's probes: a wake handed over `board/notes@1` for the write `board/notes/spec@1`, and `agent.spawned` was stamped with
  the child. [Architecture section 7](../architecture.md), Citations.
- `tests/unit/primitives/test_citations.py`, `test_every_ref_a_model_is_shown_is_an_event_ref` in `tests/unit/tools/test_mcp.py`.
