# 0058. A merge queue is a queue and a merger, written out

**Status:** Accepted, 2026-11-06

## Context

The landscape survey proposed a merge-queue role, workers handing branches to one merger rather than merging themselves, after Gas
Town's bisecting Refinery and Overstory's merge queue, and placed it in the `git-swarm` preset. GitSwarm never merges: it integrates
by synthesis commits, each declaring what it rests on. The runtime never merges either (ADR 0032): a merge is a commit an agent or a
person made, and a conflict is what a look found. A queue's `task.fail` returns the task to the queue's readers until `max_attempts`,
which here is the merger itself, so a merger that failed a conflicting task would claim it again and its worker would never hear.

## Decision

- **No preset.** A merge queue for worktree teams is written out in topologies.md: a `merges` queue that workers write and a `merger`
  role reads, the merger in a worktree of its own. It is one queue and one role, a few lines of TOML, with nothing a preset would add.
- **The merger merges with git, and the look records it.** It merges each branch a task names into its own branch; the look after its
  turn records the merge commit as the merger's, or the merge under way and its conflicted paths, which put the merger under Needs you
  while it rests on them.
- **A conflict goes back through the task.** On a conflict the merger completes the task with a result naming the paths, and the
  worker reads it from its task, by `task.list` or a `wait` on `task/merges/<id>`, which whoever adds to a queue may do.
- **landscape.md is corrected** to put the merge-queue role with worktree teams, written out, and not in `git-swarm`.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A `merge-queue` preset | A macro over six lines, and a second way to say what the lines say |
| The merge queue in `git-swarm` | GitSwarm never merges; it integrates by synthesis commits |
| `task.fail` back to the author | It returns the task to the queue's readers, the merger, until it dies |
| A runtime merge act | The runtime never merges; one would have to earn its place, which nobody has asked for |
| Batch bisection, as Gas Town's Refinery does | Out until someone asks |

## Consequences

- A team that wants a merge queue copies the written-out form, and `team show` says what it does like any other team.
- That a merger completes a conflicting task naming its paths is for its instructions to say; nothing enforces it, as nothing
  enforces what any agent writes in a result.

## Evidence

- `tests/unit/runtime/test_merge_queue.py`, `test_the_written_out_merge_queue_tells_the_worker_of_a_conflict`, on real git with
  scripted harnesses: two workers' branches through one merger, a merge commit recorded as the merger's, a conflict recorded with its
  path and raised under Needs you, and the conflicting worker reading its task's result.
- `tests/unit/topology/test_docs.py`, which builds the written-out form from topologies.md's TOML and Python alike and holds it to the
  `team show` text the page prints.
