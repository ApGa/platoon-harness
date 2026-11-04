# 0031. A workspace is a place git already knows

**Status:** Accepted, 2026-11-04

## Context

Every agent ran in the session's cwd, and a role naming any other workspace failed its spawn. Agents that write code in parallel
need trees of their own, and a person needs to find, after the session, everything they made. A workspace is made by a crash-prone
runtime in a repository that is the person's, which an agent's own git also writes, and which may sit on a filesystem other hosts
share. A design was reviewed twice, for taste and for safety; the safety review found three ways the first draft lost work.

## Decision

- **A ladder of modes, each promising one thing more.** `shared` is the session's checkout. `worktree` is a linked git worktree, locked,
  on a branch of its own. `snapshot` is a repository of its own holding your tree as your git sees it, and `isolated` is a snapshot
  whose harness an extension confines. This stage builds the first two. The others are refused before any cost, naming why.
- **Every name is a path part and a git branch part.** The one name grammar has no `..` and ends in neither `.` nor `.lock`, for every
  principal and session, so no rule depends on the mode. A tool's schema shows a name's letters, as before, and the op holds it to the
  whole grammar, since the exact pattern, which has no lookaround to say it shortly, would cost every request of every agent 3.7 KB.
- **The core uses git and the filesystem alone.** No privilege, no container, no reflink, hardlink or overlay.
- **A worktree lives in the session folder,** at `agents/<agent>/workspace`, on `platoon-harness/<session>/<agent>`, made at your
  checkout's HEAD when the workspace is made. It is locked with the reason `platoon-harness: <host>:<path>`, so a `git worktree prune`
  run where its folder cannot be seen leaves it alone.
- **What would fail late is refused before any cost.** A git mode needs a work tree, a repository that is not bare and has a commit, git
  2.36 or newer, an LFS filter for LFS files, and no branch at `platoon-harness`, at `platoon-harness/<session>` or under it, each named
  with the command that deletes it. A session folder inside the work tree and not ignored there is refused in every mode, since a
  shared agent's `git add -A` would commit the owner's token. Submodules and uncommitted changes are warned of. So is a Codex role in a
  worktree under a sandbox that keeps `.git` read-only with approvals left to ask, naming the three postures the owner chose to keep
  configurable: no sandbox, the sandbox with its escalations allowed, or asking each time.
- **A make in three steps git keeps a fact of.** The branch is made with `update-ref`, create-only, whose one reflog entry names the
  effect. The registration is `worktree add --no-checkout --lock --reason`, so the reason is there from its first write. The fill is
  `reset --hard`. The `workspace` effect is retried after a crash, and an attempt adopts what an earlier one of the same effect made:
  a branch with only our entry and checked out nowhere, a registration locked with our reason, a tree half filled. A registration
  git left half written is taken back by git itself, with `add -f -f` once its folder holds only the `.git` file git wrote there, and
  one git never wrote a folder into, which no git command can see, by its lock's reason. Anything else in the way fails, naming it.
- **The runtime's own git goes through one runner,** with no hook, no fsmonitor and no gc, `core.logAllRefUpdates` on, optional locks
  off, `LC_ALL=C`, no terminal prompt, a timeout per call, and none of another repository's variables inherited. Paths come from
  `rev-parse`. Agents' git is untouched.
- **The host runs a harness where the journal says its agent works.** The Agents view folds the workspace effect's result, a launch and
  a resume take `spec.cwd` from it, an agent works in the same subfolder of its workspace as the session's cwd is of its repository,
  and a resume whose folder has gone, or is no longer a work tree of its repository, ends its agent `lost`, naming the fix. A relative
  program in a `command` harness resolves against the session's cwd, wherever its agent works and wherever it is described.
- **An ended agent's worktree goes only when nothing would go with it, as git says:** its processes proved gone, no path in its status,
  ignored ones included, no operation under way, no index entry hidden from status, and no commit its HEAD, reflog or own refs hold
  that is not its base or reachable from a ref of your repository. Then it is unlocked and removed with plain `git worktree remove`.
  Otherwise it stays, locked, named on its agent's record and in the Ending with its host, path, branch, size and why, and the
  commands that let it go. No branch is ever removed, and closing a session ends no agent, so it keeps their workspaces.
- **What the journal recorded outlives git's pruning.** When a session stops or closes, the runtime writes one bundle into the session
  folder of every commit the journal recorded past the session's starting HEAD, replacing the last and holding what that held, and
  records it on `session.stopped`. It is built in a repository of its own that borrows the objects, so nothing is written into yours.

## Alternatives considered

| Alternative | Why not |
|---|---|
| `git worktree add -b` in one step | It makes the branch in a child before it registers anything, so a crash leaves a branch a redo refuses, and a single command cannot be resumed between its steps |
| `git branch <name>` for the first step, as the design said | Its reflog reads `branch: Created from`, as anyone's does, so a retry could not tell our branch from one an agent made mid-session; `update-ref -m` names the effect, which only we write |
| `git worktree remove -f -f` for a half-written registration, as the design said | Verified to fail there, since git cannot validate a registration missing `commondir` or `HEAD`; `add -f -f` is git's own way to take one back |
| No lock | A prune where the folder cannot be seen cuts a live worktree off from git, and session roots and repositories often sit on different filesystems |
| Workspaces beside or inside your checkout | Inside, Claude Code reads untracked notes through ancestry; beside, nothing owns their removal |
| Removing on an empty status | Detached commits, an amended commit's original, a stopped rebase and a skip-worktree edit were each lost so in the safety review |
| Refs in your repository for each recorded commit | They write into your repository, and the owner's question was answered with a bundle in the session folder |
| A pattern with the whole grammar in each tool's schema | Some 3.7 KB in every request of every agent |
| A name rule that depends on the mode | Two rules for one thing |

## Consequences

- A role says `workspace = "worktree"` and nothing else: there is no branch, path, base, lock or removal option.
- Most Python agents' worktrees are kept, for their ignored `.venv` and `__pycache__`, and a person removes them with git's own
  commands, which the Ending names.
- Your hooks run for agents' commits in a worktree, while `post-checkout` does not run when the runtime makes one.
- A recorded commit an agent rewrote can be fetched back from `commits.bundle` in the session folder, once a look records it; the look
  is the next stage's.

## Evidence

- `tests/unit/runtime/test_workspaces.py` and `test_ending_workspaces.py`, on real git under a test's own folder: each refusal before
  any cost, each crash state of a make, the runner's flags read from its own argv with hooks and an fsmonitor that never ran, each way
  removal would lose work, and the bundle holding a commit after its rewrite and a prune.
- `tests/integration/test_worktree_crashes.py`: `SIGKILL` before and after each git step of a make, then a resume.
- `tests/integration/test_claude.py`, `test_codex.py` and `test_pi.py`: a commit in a worktree, a killed runtime and a resume in the
  same folder, on each real binary against FakeModel; `runs_in_its_workspace` in `check_driver`.
- `tests/live/test_worktrees.py`, live: a commit in a worktree, a `kill -9` of the runtime and a resume there, then an end that kept
  the worktree for the file left uncommitted, in run 60 on `claude-haiku-5-5` in 4 calls and run 61 on `gpt-6-luna` in 4. In run
  59 the model ended its agent after the commit, so the kill cut its stop, which the next runtime retried and finished, removing
  the clean worktree and keeping its branch.
- Git 2.47.3 is the only version run. [compatibility.md](../compatibility.md) has what each harness sees in a worktree.
