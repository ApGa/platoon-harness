# RFC NNNN: A short title in sentence case

<!--
How to use this template (see README.md in this directory for the whole process):

1. Copy it to docs/rfcs/NNNN-short-title.md, where NNNN is the next free number and short-title is a few
   lower-case words joined by hyphens.
2. Replace every placeholder, keep the section order, and delete these comments and any optional section you
   do not use.
3. Add a row for the RFC to the index in docs/rfcs/README.md, with the status Draft.
-->

| | |
|---|---|
| Status | Draft |
| Created | YYYY-MM-DD |
| Authors | Your name and GitHub handle |
| Builds on | What this extends, with links: modules (`packages/sdk/src/platoon_harness/kernel/`), docs ([architecture](../architecture.md)) and earlier RFCs |
| Discussion | The issue or pull request where the proposal is discussed |
| Implementation | The pull requests that implement it, added as they merge (none yet) |

<!--
When the RFC is Rejected or Deferred, add a short "Decision" paragraph here: why, and for a deferred RFC, what
would bring it back. When its status carries a note, such as superseded by another RFC, the full note goes here.
-->

## Summary

One paragraph: what changes, for whom, and what it makes possible. A reader who stops here should know what is
proposed and roughly how.

## Motivation

What platoon-harness cannot do today, shown with concrete cases: a team that cannot be written, a harness that
cannot be driven, a question the record cannot answer. Say who needs it and point at the code that limits it today
(`packages/...`). Keep it to the problem; the design goes in the next section.

## Proposal

The design, split into numbered subsections, one per mechanism. Show each new or changed interface as a typed
sketch:

```python
class Example(Protocol):
    def act(self, name: str, *, timeout: float) -> Result: ...
```

Typed sketches show shape, not final names; the code that lands is authoritative. Mark an estimate with EST
and a claim nobody has checked yet with UNVERIFIED.

Say what changes for users (the team file, the `platoon-harness` command line, the ops agents call as tools, the
journal's events) and what stays as it is. Renames ship without aliases, so list every public name this removes or
renames. If it changes a law of [architecture section 3](../architecture.md#3-laws), say which, and why the law
was wrong.

### 1. The first mechanism

### 2. The second mechanism

## The hard parts

Optional. The problems you expect to be hardest, and how the design handles them or why it might not.

## Alternatives

| Alternative | Why not |
|---|---|
| The first alternative | What it is, and why not |
| Doing nothing | Include it when it is a real option: what users do today instead, and what that costs |

## Consequences

What becomes true once it lands: what gets easier, what gets harder, what is now refused, and what it costs. What
is not known yet is written as unknown.

## Rollout plan

Optional for a decision written down after its code; an RFC written before its code has one. Milestones that can
each merge on their own, in order. Each has an exit check: a test, a command or a measured number that shows the
milestone works. List each milestone's pull requests in the last column as they merge.

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 a short name | What lands | How we know it works | |
| M2 a short name | What lands | How we know it works | |

## Open questions

Optional, as the rollout plan is.

1. A question that needs a decision, who can make it, and by when (at the latest, before the milestone that
   depends on it).

## Evidence

The research, spikes, measurements and tests the design rests on, each cited by repo-relative link. A decision with no
evidence says so.
