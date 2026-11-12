# RFC 0032: The runtime looks and never moves a branch

| | |
|---|---|
| Status | Accepted, 2026-11-04; superseded in part by [RFC 0038](0038-provenance-is-answered-from-the-record.md), extended by [RFC 0041](0041-a-commit-cites-what-informed-it-by-its-ref.md), and amended by [RFC 0077](0077-a-look-waits-only-for-looks-of-its-own-workspace.md) |

**Superseded in part by [RFC 0038](0038-provenance-is-answered-from-the-record.md)**: a commit's and a
rewrite's record name no `cause`, as the turn end that prompted a look did not cause what git holds. Extended by
[RFC 0041](0041-a-commit-cites-what-informed-it-by-its-ref.md): an `Informed-By` value can cite an event of the session.

**Its looks one at a time in a session are amended by [RFC 0077](0077-a-look-waits-only-for-looks-of-its-own-workspace.md)**:
a look waits only for looks of its own workspace, and each probe still looks at the shared workspace first.

## Summary

A look after each turn, one at a time, recording on `repo/<name>` with no agent in the envelope; a commit is its maker's by the HEAD reflog entry at its committer time; `Informed-By` resolved from hex alone; conflicts surfaced and never resolved

## Motivation

With workspaces of their own, agents commit, rewrite, merge and leave work uncommitted where only git can see it. A driver cannot
report this: most harnesses say nothing of the files a shell changed, and an opaque one says nothing at all, so the `changes` report
no driver ever sent was a second source for one fact. A person needs to know what changed, whose each commit is, and where a merge
stopped on conflicts, without the runtime ever deciding a merge for them. Credit for a commit must not depend on the order in which
agents' turns happen to end, and a look must never claim the turn or the context of the agent it looks at.

## Proposal

- **The look is the host's, asked for by the lifecycle.** A turn's end, through `_turn_ended`, and a resumed `agent.start` each request a
  `probe` effect owned by the agent, retried after a crash, with the event that prompted it as its `cause`. Per-agent effect order
  starts it before anything handed over after that point, and as a requested effect it keeps the session from settling. An agent that
  ends is looked at by its stop instead, after its processes are reaped and before its workspace's end. A resume's look is the one that
  sees a turn a crash or the owner's stop cut off.
- **Looks run one at a time in a session.** Each takes the shared workspace's commits first and then the agent's own workspace, so a
  worker whose base holds the shared workspace's new commits finds them recorded. It reads HEAD once and uses that commit in every later
  step, and a status naming another HEAD is the gap `workspace_unobserved`, never a mixed state.
- **A commit is the agent's whose workspace's HEAD reflog records making it:** an entry that moved HEAD onto it at its own committer
  time. Git writes that when the commit is made, by commit, amend, merge, cherry-pick, revert or a rebase's pick, and not when a
  fast-forward, a reset or a rebase's start moves HEAD onto a commit that exists, so a worker that builds on another's commit never takes
  it, whatever order the looks run in. A commit made in the shared workspace is nobody's, as is one no workspace records making, or two.
  Every workspace still on disk is read, so that two which made the same commit are both seen.
- **What a look records names no agent in its envelope.** `repo.committed`, `repo.rewritten` and `workspace.changed` go on `repo/<name>`
  with `agent` None, so none claims a turn or a context, and their data names the workspace, `@ada` or `shared`, in the address grammar.
  `cause` names what prompted the look, so it says when a commit was seen, never when it was made.
- **A look records what is new, and only what is new.** Each commit its workspace's HEAD reaches, and each commit those name in an
  `Informed-By` trailer, that the session did not start with, the workspace did not start from and the journal does not hold, parents
  first and each after what it cites, in pages of 64. A rewrite is recorded only when a branch no longer reaches commits the journal
  holds. A workspace's head, branch and uncommitted state are recorded whenever they differ from its last look, which moves only with
  a look's last page, so a crash between pages repeats the whole look. Your checkout's uncommitted state is recorded only when a role
  works in it, since your own edits there are not the session's.
- **`Informed-By` is the one declaration of a commit's semantic parents.** A value of 4 to 40 hex digits naming one commit in the
  commit's own repository is resolved to its full SHA once, at the commit's first record. Anything else is kept as written, a ref among
  them, since a ref names whatever it points at when asked. `based_on` holds the refs of the cited commits the journal holds.
- **Unknown stays unknown.** A line count of an untracked or binary file is None, a list cut to fit says how many paths there were,
  with the whole list as a body, and the Ending names every agent whose last look never finished as `unobserved`.
- **What an agent wrote is cut to fit.** A commit's author and each `Informed-By` value are kept to 256 characters, ending in `…` where
  cut, and a commit's first 16 values with how many it had, so one long trailer cannot make a look's page invalid. The design bounded
  a value only where the op checked it, which refused the page, so every later look of that workspace failed the same way and none of
  its commits was ever recorded.
- **The runtime never merges, rebases or resolves.** A merge is a commit an agent or a person made, a conflict is what a look found, and
  a `conflict` attention row is open while its agent rests on it: it comes at the end of each look of the agent's that still finds
  conflicted paths, goes at the next turn's start, and is moot once the agent ends, when the Ending names the kept workspace. Its gist
  says what stopped, on which files, and where to resolve it, from the work tree's `path` each reading names, so the terminal and the
  browser show the same words and neither repeats the agent.
- **`changes` leaves the driver's vocabulary,** with `Changed` and `change.recorded`. A wire program that sends one gets `native` plus a
  gap, and the wire protocol stays 1, since no program ever sent it.

These details differ from the design, each the smallest change that keeps its rules:

- Attribution reads every workspace's reflog rather than reading the others only for a commit neither its own nor the shared one made,
  since that order called a commit two worktrees made the first one's.
- The `changes` view has a `workspace` row for each workspace's last reading, with its head, any operation under way and its true
  `total`, in place of a `more` row, which says how many paths a cut list left out and tells "not measured" from "nothing changed".
- `workspace.changed` records head and branch beside the uncommitted state, as the event that moves a workspace's last look; the shared
  workspace's, with no role in it, holds no state, and the `changes` view shows nothing of it.
- `conflicted` is a count, and the paths come conflicted first; `informed_by` entries are `{written, sha}`, `repo.rewritten` names `was`
  and `now`, and the probe's prompt is its `cause`, as `as`, `from` and `after` are taken words.
- `under_way` names a `sequence` too, a cherry-pick or revert of several commits between its picks, which a stop already kept for.
- A conflict row comes at the end of each probe that finds conflicts, the first among them, and never from a stop's look.
- The view of each workspace's last look is `Looks`, as `Repo` names the repository a session opens on, and `repo.looks`, a runtime
  query, gives the host each workspace's last head and branch from it, since a daemon keeps nothing of its own.
- `session.status` names the repository observed as `repo`, None when there is none, and a client says "not observed" from that.
- A commit row has no `tests` until runtime tests exist, and has the seq that `recorded` it beside the `seq` that last moved it, so
  `/review` lists commits newest recorded first, where a rewrite that dropped one would otherwise lift it above the newer ones.
- A look and a stop read status through one form, `--untracked-files=normal --ignore-submodules=none`, so no config makes them
  disagree on what a workspace holds.

## Alternatives

| Alternative | Why not |
|---|---|
| Driver-reported `changes` | An opaque harness reports nothing, and a fact would have two sources |
| A commit is its first observer's | Its owner would depend on whose turn ends first |
| The only workspace whose HEAD reaches it | Turns the maker's commit into nobody's whenever another worker builds on it before the maker's look |
| Classifying reflog messages (`commit`, `cherry-pick`, `rebase`) | That wording is no interface git documents, and `GIT_REFLOG_ACTION` renames it |
| The author field, or a per-agent committer identity | The first is data anyone writes; the second would write our names into your history, through every harness |
| The agent as the envelope's `agent` | `emit` would stamp the turn and context open when the look runs, which is wrong whenever a turn began without a delivery |
| Concurrent looks deduplicated by the op | They would race on the shared workspace's last look, which every look takes |
| Excluding every journaled commit at every look | One commit another snapshot holds fails `rev-list` there, and the list grows with the session |
| A runtime merge through `merge-tree` and a compare-and-swap `update-ref` | Sound, but nothing needs the runtime to move a branch: an agent merges in its own worktree, and you in yours |
| Raising a conflict at `turn.ended` | That fires before the turn's look has run |
| Resolving a trailer with `rev-parse` as written | `HEAD`, `main` and `main@{1.year.ago}` resolve too, so a ref would become a parent at whatever it pointed at then |

## Consequences

- A one-turn agent's work shows nothing until its turn ends, and a commit on a branch no workspace has at HEAD is unobserved.
- A worktree an agent makes with git is outside every look ([RFC 0033](0033-a-harness-s-own-worktrees-are-off.md)).
- Attribution reads what the agent's own git wrote, so it is evidence at the workspace's assurance, never proof: a commit made by a
  command that never moves HEAD, such as `commit-tree` with `update-ref`, is nobody's, and so is one two workspaces made in one second.
- Each look blocks only its own agent's next handover, and looks run one at a time, so a burst of turn ends queues looks.
- An agent's read of a commit, its tests and the GitSwarm rework come in a later stage, with records of their own.

## Evidence

- `tests/unit/runtime/test_looks.py`, on real git under a test's own folder: whose each commit is, whatever order looks run in, after
  a fast-forward, a merge from your checkout, two makers and none; cited commits first and trailers resolved from hex alone; an author
  and trailers cut to fit, and a long trailer that blinds no later look; rewrites
  and a moved untouched branch; merges and rebases under way; untracked and binary counts; a list cut to fit; HEAD moving mid-look; a
  look that changes no ref, index or file; and through a session: a look after a turn, at a stop, on a resume after the owner's stop,
  one at a time, of a one-shot program, and one that failed.
- `tests/unit/primitives/test_repo.py`: the probe at each turn end and resume, before a handover and keeping a session unsettled, the
  Ending's unobserved agents, envelopes with no agent, records once and only when they differ, the `changes` view and `seq`, and a
  conflict that needs you while its agent rests on it and again after the next look.
- `tests/live/test_worktrees.py`, live: a real agent's commit in its worktree recorded as its own, with no agent in the envelope,
  across a `kill -9` of its runtime and a resume, on `claude-haiku-5-5` in 5 calls and on `gpt-6-luna` in 4.
- Git 2.47.3 is the only version run.
