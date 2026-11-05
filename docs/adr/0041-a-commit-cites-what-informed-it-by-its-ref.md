# 0041. A commit cites what informed it by its ref

**Status:** Accepted, 2026-11-05

## Context

A commit declares what it rests on through `Informed-By` trailers ([ADR 0032](0032-the-runtime-looks-and-never-moves-a-branch.md)),
and until now only a value naming a commit resolved: a commit's record cited the record of each commit its hex values named, and
kept anything else as written and unresolved. So the walk back from code stopped at code. The board entry a commit implements, the
message that asked for it, or the task it closes could be named in a trailer and reach nothing, and the owner wants credit for an
outcome to reach the messages that informed it.

The design's owner question 7 asked whether a trailer should also take an event's ref, through the same check as `based_on`. The
owner approved the stage's recommendations, which state the decision as: a trailer also takes an event ref, "checked as based_on is
(it exists, and the commit's maker could read it)", recorded on `repo.committed` as a declared citation beside the resolved commits,
and a value that is neither stays unresolved.

A trailer is not written through our ops. It is text in a commit, which git carries between clones, sessions and years: a commit
fetched from another clone may cite `agent/ada@1` of the session it was made in, and this session has an `agent/ada@1` of its own.
An event's ref means something only in the session that wrote it.

## Decision

- **A value that is an event's ref is cited when the commit's maker could read it.** At the commit's first record, a look's
  `repo.report` checks each `Informed-By` value that names no commit as `based_on` is, through `cited`: it must name an existing
  event, and a range lines of that event's text body. And the commit's maker must be an agent of the session, by the workspace whose
  reflog records making it, that made the event or was handed it by the look, as `blob.get` decides what an agent may read. One that
  passes joins the commit's `based_on`, beside the records of the commits its hex values named, in the order written.
- **Anything else stays as written, saying why.** A value is never refused, since git already holds it: it stays in `informed_by`,
  and the record keeps why it cites nothing, `unrecorded`, `no_event`, `no_lines` or `unread`, which lineage gives with each
  unresolved value. `repo.committed` is at payload 2 for this; a record from before cited no event, and lineage says so of what it
  could not tie to a commit, `unchecked`.
- **What the maker was handed is still exposure's to say.** Being handed an event is what lets a trailer cite it, and lineage gives
  each citation with the maker's exposure to it, bounded at the look that recorded the commit, as for every citation: an event
  handed over and never confirmed is cited, and its exposure says `unknown`.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Citing any existing event, and leaving whether the maker could read it to exposure, as `based_on` does | The first build did this. A commit made in another clone, or a year before the session, then cited this session's unrelated event of the same ref, and contributors credited its maker; and the owner's decision names the check. `based_on` is written by its citer in the session, and a trailer may come from anywhere |
| Resolving only a commit whose committer time is not before the session opened | It needs a time the record does not keep, and a cherry-pick or a rebase takes a new committer time, so it would still let an old trailer in. A commit an agent's workspace made, of an event that agent could read, is the condition the record can state |
| A gate on the maker's grants for the cited stream | A per-stream table of reader ops, which the design rejected for `based_on` |
| A trailer of its own name for event refs | Two ways to declare what a commit rests on |
| Resolving event refs at query time from `informed_by` | Every query would repeat a check the record can make once, and a view could not fold it |
| Reasons worked out at query time | Two places would decide one thing: the record keeps the reason the look decided by |

## Consequences

- `contributors` from a commit walks to whoever wrote the entry, message or task it cites, so code credit reaches what informed it.
- A commit nobody's workspace made alone, your checkout's among them, cites no event: nobody the record names can be shown to have
  read one. Its hex values still cite the commits they name.
- A commit an agent of the session made by replaying another's, as a cherry-pick or a rebase does, is its own, and a trailer it kept
  is read as its claim in this session, of what it could read here.
- Git made the commit at a time the record does not hold, so an event a trailer names may have come after the commit and before
  its look. Law 7 still holds, as the record comes after both, and the maker's being handed it and its exposure are both counted
  below the look, which the bound says.
- `repo.committed` is at payload 2: each `informed_by` value is `{written, sha, why}`, `why` None where it cites.

## Evidence

- `tests/unit/primitives/test_provenance.py`: `test_an_informed_by_event_ref_is_a_declared_citation_checked_as_based_on_is`, a ref and
  a range of a board entry its maker was handed cited, and a missing event, lines past the body and a body's hash unresolved with
  why; `test_an_informed_by_event_ref_cites_only_what_the_commit_s_maker_could_read`, an event its maker made cited, one it was
  never handed `unread`, and a commit made in the shared workspace or by no single workspace citing no event;
  `test_a_look_before_payload_2_looked_for_commits_alone`.
- `tests/unit/runtime/test_looks.py`, on real git: `test_an_informed_by_value_naming_an_event_is_cited_by_the_commit_s_record`, a
  worker citing the goal it was handed, and `test_a_commit_made_elsewhere_cites_no_event_of_this_session`, a commit fetched from
  another clone, made a year before, citing the `agent/ada@1` of its own session, which cites nothing here, though ada was handed
  this session's.
- [Architecture sections 7, 11 and 13](../architecture.md). [workspaces.md](../workspaces.md).
