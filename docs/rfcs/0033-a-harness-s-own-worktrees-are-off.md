# RFC 0033: A harness's own worktrees are off

| | |
|---|---|
| Status | Accepted, 2026-11-04 |

## Summary

Claude Code's `EnterWorktree` and `ExitWorktree` off on every launch, and a Codex thread held to `spec.cwd`

## Motivation

Claude Code 2.1.316 offers `EnterWorktree` and `ExitWorktree` in its first request's tool listing, and `--worktree` on its command
line. Either moves the agent into a worktree Claude Code makes for itself: outside the folder its workspace effect made and the journal
records, outside the lock and the branch the runtime keeps, and outside what its stop reads before it removes anything. RFC 0024 set
the precedent of turning off a harness's own way to do what the runtime does.

## Proposal

- **The Claude driver disallows `EnterWorktree` and `ExitWorktree` on every launch,** beside `AskUserQuestion`, whatever a role allows,
  and nothing passes `--worktree`.
- **A worktree an agent makes with git from a shell is outside every look,** and workspaces.md says so. Nothing stops it, as nothing
  stops any command an agent runs as you.
- **Codex, pi and OpenHands have no such tool.** The Codex driver refuses a thread whose `thread/start` or `thread/resume` names a `cwd`
  other than `spec.cwd`, a field of 0.164.0's stable schema, so a user's config cannot move its tools elsewhere unseen.

## Alternatives

| Alternative | Why not |
|---|---|
| Leave them on | A second way to make a worktree, with no record, no lock and no lossless end |
| Off unless a role allows them, as native children are | Nobody has asked for them, and allowing them would mean watching a folder nothing records |
| Refuse a Claude start whose init frame names another cwd | Where 2.1.316 reports it, and when, is not yet checked; `runs_in_its_workspace` holds the harness to `spec.cwd` meanwhile |

## Consequences

- An agent that wants another tree makes one with git, as a person would, and that tree is its own affair.

## Evidence

- `tests/unit/drivers/test_claude.py`, `test_claude_never_offers_its_own_worktree_tools`, and `test_codex.py`,
  `test_codex_refuses_a_thread_running_outside_its_workspace`.
- `runs_in_its_workspace` in `check_driver`, on each real binary against FakeModel.
