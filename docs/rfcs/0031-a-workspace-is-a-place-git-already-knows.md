# RFC 0031: A workspace is a place git already knows

| | |
|---|---|
| Status | Accepted, 2026-11-04 |

## Summary

Modes as a ladder; every name a branch part; a worktree locked in the session folder, made in steps a retry adopts, refused before any cost where it would fail, and removed only when git says nothing would go with it; recorded commits kept in a bundle

## Motivation

Every agent ran in the session's cwd, and a role naming any other workspace failed its spawn. Agents that write code in parallel
need trees of their own, and a person needs to find, after the session, everything they made. A workspace is made by a crash-prone
runtime in a repository that is the person's, which an agent's own git also writes, and which may sit on a filesystem other hosts
share. A design was reviewed twice, for taste and for safety; the safety review found three ways the first draft lost work.

## Proposal

- **A ladder of modes, each promising one thing more.** `shared` is the session's checkout. `worktree` is a linked git worktree, locked,
  on a branch of its own. `snapshot` is a repository of its own holding your tree as your git sees it, and `isolated` is a snapshot
  whose harness an extension confines. This stage builds the first three. `isolated` is refused before any cost, naming why.
- **Every name is a path part and a git branch part.** The one name grammar has no `..` and ends in neither `.` nor `.lock`, for every
  principal and session, so no rule depends on the mode. A tool's schema shows a name's letters, as before, and the op holds it to the
  whole grammar, since the exact pattern, which has no lookaround to say it shortly, would cost every request of every agent 3.7 KB.
- **The core uses git and the filesystem alone.** No privilege, no container, no reflink, hardlink or overlay.
- **A worktree lives in the session folder,** at `agents/<agent>/workspace`, on `platoon-harness/<session>/<agent>`, made at your
  checkout's HEAD when the workspace is made. It is locked with the reason `platoon-harness: <host>:<path>`, so a `git worktree prune`
  run where its folder cannot be seen leaves it alone.
- **A snapshot is a repository of its own,** at the same place and on the same branch, holding your tree as your git sees it,
  uncommitted and untracked work included, as HEAD or one runtime commit over it, authored `platoon-harness
  <runtime@platoon-harness.invalid>`. It is captured in your checkout, under your repository's own config, into a copy of your index
  and into the snapshot's own object store, so your filters, attributes and excludes apply as for your own `git add`, and nothing of
  yours is written. It reads your objects through alternates, packs into its own store every object the capture reaches that your
  refs at open did not, and has no remote. It takes what your checkout's git resolves for `user.name`, `user.email`,
  `core.autocrlf`, `core.eol`, `core.fileMode`, `core.symlinks` and `core.ignoreCase`, and copies of `info/exclude` and
  `info/attributes`. It is built aside at `workspace.part` and renamed into place last, so it is whole or absent: a retry adopts a
  whole one, takes a part back, and fails on a folder whose HEAD is not on its branch. One refused when it is made, or whose build
  fails, takes its part back, so it leaves nothing. Where the design named a `capture.index`, the capture uses the snapshot's own
  index, a copy of yours, which the fill then makes its own, and writes it whole, with `core.splitIndex=false` in the capture's
  environment, since a split copy put a shared index into your git directory and left the copy unreadable; an untracked repository
  is found by `ls-files --others`, which names it where `status` names only its parent folder; and the uncommitted changes warning
  holds for worktree roles alone, since a snapshot carries them. Each keeps the design's rules.
- **What would fail late is refused before any cost.** A git mode needs a work tree, a repository that is not bare and has a commit, git
  2.36 or newer, an LFS filter for LFS files, the session's subfolder in what the workspace would hold, and no branch at
  `platoon-harness`, at `platoon-harness/<session>` or under it. A reused session name meets its own old branches, so that refusal
  says to give the session another name first, then names the release of any kept worktree holding one and `git branch -d`, which
  refuses unmerged work, where the design named `-D`. A session folder inside the work tree and not ignored there is refused in every
  mode, since a shared agent's `git add -A` would commit the owner's token. Submodules and uncommitted changes, named, are warned of.
  So is a Codex role in a worktree or a snapshot under a sandbox that keeps `.git` read-only with approvals left to ask, naming the
  three postures the owner chose to keep configurable: no sandbox, the sandbox with its escalations allowed, or asking each time; and
  one under `approvals = "deny"`, whose commits would each be refused. A snapshot is refused where its git would see your tree
  otherwise: a tracked file with any `filter` attribute, LFS and git-crypt among them, a sparse checkout, which it would hold whole, an
  untracked repository inside the tree, which a capture leaves out, and a merge, rebase, cherry-pick, revert or bisect under way or a
  conflicted path in your checkout, which `git add -A` on a copy of your index would mark resolved, each named. A snapshot's refusals
  are read again when each one is made, since your checkout may have changed since open.
- **A make in three steps git keeps a fact of.** The branch is made with `update-ref`, create-only, whose one reflog entry names the
  effect. The registration is `worktree add --no-checkout --lock --reason`, so the reason is there from its first write. The fill is
  `reset --hard`. The `workspace` effect is retried after a crash, and an attempt adopts what an earlier one of the same effect made:
  a branch with only our entry and checked out nowhere, a registration locked with our reason, a tree half filled. A registration
  git left half written is taken back by git itself, with `add -f -f` once its folder holds only the `.git` file git wrote there, and
  one git never wrote a folder into, which no git command can see, by its lock's reason. Anything else in the way fails, naming it.
  The branch is made only where the session's subfolder is committed at the HEAD it starts from, and a fill that fails takes its
  registration back with `remove -f -f`, since no agent has run there, so a spawn that cannot run leaves at most its branch, which
  the error names. The design checked the subfolder after the fill, which left a locked worktree nothing named.
- **The runtime's own git goes through one runner,** with no hook, no fsmonitor and no gc, `core.logAllRefUpdates` on, optional locks
  off, `LC_ALL=C`, no terminal prompt, a timeout per call, and none of another repository's variables inherited. Paths come from
  `rev-parse`. Agents' git is untouched.
- **The host runs a harness where the journal says its agent works.** The Agents view folds the workspace effect's result, a launch and
  a resume take `spec.cwd` from it, an agent works in the same subfolder of its workspace as the session's cwd is of its repository,
  and a resume whose folder has gone, or is no longer a work tree of its repository, ends its agent `lost`, naming the fix. A relative
  program in a `command` harness resolves against the session's cwd, wherever its agent works and wherever it is described.
- **An ended agent's worktree goes only when nothing would go with it, as git says:** its processes proved gone, no path in its status,
  ignored ones included, no operation under way, no index entry hidden from status while its file is in the tree, and no commit its
  HEAD, reflog or own refs hold that is not its base or reachable from a ref of your repository. Its status names
  `--untracked-files=normal` and `--ignore-submodules=none`, as a look's does, since under `status.showUntrackedFiles=no` the design's
  status, and git's own `worktree remove`, saw a clean tree where the look had just recorded an untracked file; and an entry a sparse
  checkout leaves out of the tree, which the design counted as hidden, holds nothing to lose. Then it is unlocked, unless a stop a
  crash cut already did, and removed with plain `git worktree remove`. Otherwise it stays, locked, named on its agent's record and in
  the Ending with its host, path, branch, size and why, each reason naming the paths or commits it found. No branch is ever removed,
  and closing a session ends no agent, so it keeps their workspaces. A snapshot goes by the same rule, its own refs being all its refs,
  its stash and its reflogs, read in the snapshot, where your commits are seen through its alternates: it is renamed aside, then
  deleted, and its folder gone counts as removed only where that began or its stop is a repeat. A kept one is made whole, with
  `repack -a -d` and its alternates removed, so your repository's pruning cannot take what it borrowed. The authority hears how the
  agent ended even when ending its workspace fails.
- **A kept workspace's release loses nothing it was kept for.** The Ending gave every kept workspace the same commands, and following
  a snapshot's, a fetch of its branch then `rm -rf`, deleted the stash, the uncommitted paths and the other refs it was kept for, while
  a worktree's `remove` succeeded on a clean tree and dropped a commit only its reflog held. So the stop that keeps one names the
  commands that let it go, quoted, only when they lose nothing but the ignored files its `why` names: a worktree's unlock and
  remove, or a snapshot's fetch of its branch, when its branch is what holds its own commits, and the removal of its folder.
  Otherwise there are none, and `why` says what to save first. An agent that has not ended, or whose stop has not finished, is named
  with no commands, since nothing has looked at what letting it go would lose.
- **What the journal recorded outlives git's pruning.** When a session stops or closes, the runtime writes one bundle into the session
  folder of every commit the journal recorded past the session's starting HEAD, replacing the last and holding what that held, and
  records it on `session.stopped`. It is built in a repository of its own that borrows the objects, so nothing is written into yours.

## Alternatives

| Alternative | Why not |
|---|---|
| `git worktree add -b` in one step | It makes the branch in a child before it registers anything, so a crash leaves a branch a redo refuses, and a single command cannot be resumed between its steps |
| `git branch <name>` for the first step, as the design said | Its reflog reads `branch: Created from`, as anyone's does, so a retry could not tell our branch from one an agent made mid-session; `update-ref -m` names the effect, which only we write |
| `git worktree remove -f -f` for a half-written registration, as the design said | Verified to fail there, since git cannot validate a registration missing `commondir` or `HEAD`; `add -f -f` is git's own way to take one back |
| No lock | A prune where the folder cannot be seen cuts a live worktree off from git, and session roots and repositories often sit on different filesystems |
| Workspaces beside or inside your checkout | Inside, Claude Code reads untracked notes through ancestry; beside, nothing owns their removal |
| Removing on an empty status | Detached commits, an amended commit's original, a stopped rebase and a skip-worktree edit were each lost so in the safety review |
| Refs in your repository for each recorded commit | They write into your repository, and the owner's question was answered with a bundle in the session folder |
| A snapshot captured with `GIT_DIR` set to it | It skipped your clean filters and `info/attributes`, so it held a tree your git would not |
| A snapshot borrowing your objects alone, with no pack of its own | A blob only ever staged in your checkout was lost from it once you unstaged it and git pruned |
| Copying your filter commands into a snapshot's config | It would run commands from a repository whose config an agent writes |
| A reflink, hardlink, overlay or whole-tree copy, or `git clone --shared` | A reflink silently becomes a full copy across filesystems; a hardlink lets a write in place reach yours; an overlay needs a mount namespace; a whole copy brings a `.venv` that points back at yours; a clone leaves a remote to push to |
| A pattern with the whole grammar in each tool's schema | Some 3.7 KB in every request of every agent |
| A name rule that depends on the mode | Two rules for one thing |

## Consequences

- A role says `workspace = "worktree"` and nothing else: there is no branch, path, base, lock or removal option.
- Most Python agents' worktrees are kept, for their ignored `.venv` and `__pycache__`, and a person removes them with git's own
  commands, which the Ending names. One kept for anything else gets no commands until a person has saved or dropped what it holds.
- Your hooks run for agents' commits in a worktree, while `post-checkout` does not run when the runtime makes one. Your repository's
  `.git/hooks` do not run in a snapshot, which is a repository of its own, while a `core.hooksPath` your global or system config sets
  does.
- A snapshot holds no ignored file, so a `.venv` must be made again there, and its commits stay in it until you fetch them with
  `git fetch <path> <branch>:<branch>`, which makes it removable too. Repositories with filtered files, a sparse checkout or a nested
  repository use `worktree`.
- Making a kept snapshot whole costs a full pack of what it reaches; a capture's own pack grows with your uncommitted changes.
- A recorded commit an agent rewrote can be fetched back from `commits.bundle` in the session folder, once a look has recorded it
  ([RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md)).

## Evidence

- `tests/unit/runtime/test_workspaces.py` and `test_ending_workspaces.py`, on real git under a test's own folder: each refusal before
  any cost, each crash state of a make, the runner's flags read from its own argv with hooks and an fsmonitor that never ran, each way
  removal would lose work, under `status.showUntrackedFiles=no` and `diff.ignoreSubmodules=all` too, release commands run through a
  shell's quoting from a folder with a space in its name, none given where they would lose work, a fill that fails taken back, and
  the bundle holding a commit after its rewrite and a prune.
- `tests/unit/runtime/test_snapshots.py`, on real git under a test's own folder: what a snapshot holds, its capture under your
  config, a blob only ever staged and then pruned from yours still held, identity and file-reading values carried, no remote, nothing
  of yours changed under a split index too, each refusal, a checkout mid-merge among them, adoption after a rename and of a part, and
  its end: removed when clean or fetched, kept for a commit, a ref, a stash or uncommitted work, made whole, and surviving your
  repository's prune.
- `tests/integration/test_worktree_crashes.py`: `SIGKILL` before and after each git step of a worktree's make, and after each step of
  a snapshot's, then a resume; and at each step of ending one, after the unlock, around the removal, before the stop's finish and
  while a kept snapshot is made whole.
- `tests/integration/test_claude.py`, `test_codex.py` and `test_pi.py`: a commit in a worktree, a killed runtime and a resume in the
  same folder, on each real binary against FakeModel; `runs_in_its_workspace` in `check_driver`.
- `tests/live/test_worktrees.py`, live: a commit in a worktree, a `kill -9` of the runtime and a resume there, then an end that kept
  the worktree for the file left uncommitted, in run 60 on `claude-haiku-5-5` in 4 calls and run 61 on `gpt-6-luna` in 4. In run
  59 the model ended its agent after the commit, so the kill cut its stop, which the next runtime retried and finished, removing
  the clean worktree and keeping its branch. In run 68 on `gpt-6-luna`, in 5 calls, the end named the uncommitted file and gave no
  release.
- `tests/live/test_worktrees.py`, live, in a snapshot of a tree with uncommitted work: a real agent's commit there, recorded as its
  own, and an end that kept the snapshot whole, in run 64 on `claude-haiku-5-5` in 2 calls and run 65 on `gpt-6-luna` in 2; and its
  release commands run after it, which left the commit on its branch in your repository and the snapshot gone, in run 66 on
  `claude-haiku-5-5` in 2 calls and run 67 on `gpt-6-luna` in 2.
- Git 2.47.3 is the only version run. [compatibility.md](../reference/compatibility.md) has what each harness sees in a worktree.
