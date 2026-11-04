# 0041. A commit cites what informed it by its ref

**Status:** Accepted, 2026-11-05

## Context

A commit declares what it rests on through `Informed-By` trailers ([ADR 0032](0032-the-runtime-looks-and-never-moves-a-branch.md)),
and until now only a value naming a commit resolved: a commit's record cited the record of each commit its hex values named, and
kept anything else as written and unresolved. So the walk back from code stopped at code. The board entry a commit implements, the
message that asked for it, or the task it closes could be named in a trailer and reach nothing, and the owner wants credit for an
outcome to reach the messages that informed it.

The owner decided that a trailer also takes an event's ref, "checked as `based_on` is (it exists, and the commit's maker could read
it)", recorded on `repo.committed` as a declared citation beside the resolved commits, and that a value that is neither stays
unresolved.

## Decision

- **A value that is an event's ref is cited.** At the commit's first record, a look's `repo.report` passes each `Informed-By` value
  that names no commit through `cited`, the check every write of content makes: it must name an existing event, and a range must
  name lines of that event's text body. One that passes joins the commit's `based_on`, beside the records of the commits its hex
  values named, in the order written.
- **Anything else stays as written.** A value that names nothing, no lines of its event's body, or a body's hash is never refused,
  since git already holds it: it stays in `informed_by` alone, and lineage lists it as unresolved.
- **Whether the maker could read it is exposure's to say.** The decision's words "the commit's maker could read it" are taken as
  the record can state them without making exposure a condition of a claim: lineage gives each citation with the commit maker's
  exposure to it, bounded at the look that recorded the commit and saying `look`, as for every citation. This is the one place this
  record reads the decision differently from its words, and why is below.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Citing an event only when the commit's maker made it or was handed it, as `blob.get` reads | `based_on` keeps a citation of what its citer was never handed, or may not read, as its claim, and exposure labels it beside it (architecture §7). A gate here would merge observed into declared for commits alone, and drop from the graph the signal credit research wants: a claim of something the record never showed the agent. The value would still be kept as written, so nothing is lost but the edge |
| A gate on the maker's grants for the cited stream | A per-stream table of reader ops, which the design rejected for `based_on` |
| A trailer of its own name for event refs | Two ways to declare what a commit rests on |
| Resolving event refs at query time from `informed_by` | Every query would repeat a check the record can make once, and a view could not fold it |

## Consequences

- `contributors` from a commit walks to whoever wrote the entry, message or task it cites, so code credit reaches what informed it.
- A commit in the shared workspace, which is nobody's, cites the same way, and its citations carry no exposure, as nobody's reading
  is evidence.
- Git made the commit at a time the record does not hold, so an event a trailer names may have come after the commit and before
  its look. Law 7 still holds, as the record comes after both, and the citation's exposure is bounded at the look and says so.
- No payload changes: `repo.committed` keeps `informed_by` as `{written, sha}`, and `based_on` is the envelope's.

## Evidence

- `tests/unit/primitives/test_provenance.py`, `test_an_informed_by_event_ref_is_a_declared_citation_checked_as_based_on_is`: a ref
  and a range of a board entry cited; a missing event, lines past the body and a body's hash unresolved; the commit maker's exposure
  `unknown` with nothing handed; contributors reaching the entry's writer.
- `tests/unit/runtime/test_looks.py`, `test_an_informed_by_value_naming_an_event_is_cited_by_the_commit_s_record`, on real git.
- [Architecture sections 7, 11 and 13](../architecture.md). [workspaces.md](../workspaces.md).
