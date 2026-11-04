# Workspaces

Where each agent works, and what becomes of it. A role names one:

```toml
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
workspace = "worktree"            # "shared" (the default) | "worktree" | "snapshot" | "isolated"
```

There is no branch, path, base, lock or removal option. The mode recorded is the one that ran: a mode that cannot be given fails
loudly, before any cost where that can be seen, and never becomes another. [ADR 0031](adr/0031-a-workspace-is-a-place-git-already-knows.md)
has the decisions behind this page, and [compatibility.md](compatibility.md#workspaces) what each harness sees.

## What each mode promises

| Mode | It is | State |
|---|---|---|
| `shared` | The session's checkout, its cwd. Every agent's writes land there at once, and nothing in it is private or confined | Given everywhere, with or without git |
| `worktree` | A linked git worktree of your repository, on a branch of its own, made at your checkout's HEAD when its agent's workspace is made. It shares the repository's refs, objects, config and hooks, and what runs there can reach anything you can, so it is not a sandbox | Given on git |
| `snapshot` | A repository of its own holding your tree as your git sees it, uncommitted and untracked work included, but no ignored file. It reads your objects and holds its own, has no remote, and git in it writes only its own repository, while what runs there can still reach anything you can | Given on git |
| `isolated` | A snapshot whose harness an extension's isolation confines | Planned, and refused before any cost: no extension gives an isolation yet |

An agent works in the same subfolder of its workspace as the session's cwd is of its repository: a session started in `src/` puts a
worktree agent in `src/` of its worktree. Its folder never changes while it lives, and every launch and resume runs its harness there.

## Where a worktree lives

At `agents/<agent>/workspace` in the session folder, on the branch `platoon-harness/<session>/<agent>`, locked with the reason
`platoon-harness: <host>:<path>`, so a `git worktree prune` run where its folder cannot be seen leaves it alone, and `git worktree
list` says whose it is. Nothing of it is in your checkout, and your checkout's tools never walk into it.

A session folder lives on the host whose root holds it. Where your root is node-local, as the fallback `/var/tmp/platoon-harness-$UID`
is when your home is on a network filesystem, a kept worktree is reachable only from that host, and the OS may age it away: the lock's
reason names the host. A copy of a session folder must leave `agents/*/workspace` out, since git in a copied worktree would move the
original's HEAD.

## Where a snapshot lives

At the same place, `agents/<agent>/workspace`, as a repository of its own on the branch `platoon-harness/<session>/<agent>`, which
lives in that repository and not in yours. Its first commit is your HEAD when nothing differs, and otherwise one commit over it by
`platoon-harness <runtime@platoon-harness.invalid>` holding your tree as your git saw it: what `git add -A` would stage, under your own
config, so your excludes and attributes apply and your ignored files, such as a `.venv`, stay out. It takes your `user.name` and
`user.email`, so an agent commits there as it would in a worktree, and how your git reads and writes files. Your hooks do not run
there, since it is a repository of its own. It reads your objects through alternates and holds in its own pack everything else it
needs, so your unstaging and pruning cannot take from it what it holds.

## Before any cost

`team check`, `run` and `Session.start` refuse, with exit 78 on the command line, each of these, every one named:

- A git mode where the cwd is in no git work tree, the repository is bare or has no commit, or git is older than 2.36.
- LFS-tracked files with no LFS filter configured, which a worktree would hold as their pointers.
- A branch at `platoon-harness`, at `platoon-harness/<session>` or under it, with the `git branch -D` that deletes each once nothing on
  it is wanted. Branches outlive their sessions on purpose, so a reused session name meets its own old ones.
- In every mode, a session folder that lies inside your repository's work tree and is not ignored there, since an agent's `git add -A`
  would commit its credentials.

A snapshot is refused besides where git in it would see your tree otherwise than your own git: a tracked file with a `filter`
attribute, LFS and git-crypt among them, since only your config runs that filter; a sparse checkout, which it would hold whole; and an
untracked repository inside your tree, which a capture leaves out. Use `worktree` for these.

And warn of submodules, which stay uninitialized in each workspace, of uncommitted changes in your checkout, which a worktree does not
carry, and of a Codex role whose commits would each wait on an approval, below.

## What each harness sees there

A worktree holds what is committed at its base and nothing else: untracked project files, such as `CLAUDE.local.md`,
`.claude/settings.local.json`, `.env` or a `.venv`, are absent, so an agent can behave otherwise than it would in your checkout. Your git
hooks run for agents' commits there, while `post-checkout` does not run when the runtime makes one. Claude Code's auto memory is keyed
on the repository and shared by every worktree of it, a channel no topology binds.

Claude Code's own worktree tools are off on every launch ([ADR 0033](adr/0033-a-harness-s-own-worktrees-are-off.md)). A worktree an
agent makes with git from a shell is its own affair, and outside what the runtime records.

**Codex** keeps `.git` read-only under its `workspace-write` and `read-only` sandboxes, so each commit asks for an approval that runs
outside the sandbox. Choose one of three postures for a Codex role in a worktree:

| Posture | Says | What it means |
|---|---|---|
| No sandbox | `sandbox = "danger-full-access"` | Commits work, and its commands run with no sandbox at all |
| The sandbox, its escalations allowed | `approvals = "allow"` | The sandbox stays, and each escalation the model asks for is allowed by policy |
| Asking | `approvals = "ask"`, the default | You approve each commit, so a headless run ends `needs_human` at its first |

## When a workspace goes

At its agent's end, its stop removes the worktree only when nothing would go with it, as git says:

- its processes are proved gone;
- its status shows no path, ignored ones included;
- no merge, rebase, cherry-pick, revert or bisect is under way;
- no index entry is hidden from status by `skip-worktree` or `assume-unchanged`;
- every commit its HEAD, its reflog or its own refs hold is its base, or reachable from a ref of your repository. Its branch is one, so
  committed work on its branch never keeps a worktree.

Then it is unlocked and removed with plain `git worktree remove`. Otherwise it stays, locked, and the Ending's `workspaces` names it with
its host, path, branch, size on disk and why, such as `1 uncommitted paths`, `ignored: .venv/, __pycache__/`, `a rebase under way` or
`2 commits only it holds, in its HEAD, reflog or own refs`, and the commands that let it go. No branch is ever removed. Closing a
session ends no agent, so it keeps the workspaces of agents that never ended, named `its agent has not ended`.

To let a kept worktree go, once nothing in it is wanted:

```console
$ git worktree unlock ~/.local/state/platoon-harness/sessions/fix-auth/agents/ada/workspace
$ git worktree remove ~/.local/state/platoon-harness/sessions/fix-auth/agents/ada/workspace
```

`remove` refuses one with uncommitted or untracked files until you say `--force`. Once a session folder is deleted, `git worktree
unlock <path>` and then `git worktree prune` forget its worktrees, and `git branch -D` deletes their branches.

A snapshot goes by the same rule, where the commits it alone holds are those of all its refs, its stash and its reflogs that are
neither its base nor reachable from a ref of yours. A kept one is made whole: what it borrowed from your repository is packed into
its own, and its alternates are removed, so it no longer depends on yours. To keep its work and let it go:

```console
$ git -C ~/src/app fetch ~/.local/state/platoon-harness/sessions/fix-auth/agents/ada/workspace \
    platoon-harness/fix-auth/ada:platoon-harness/fix-auth/ada
$ rm -rf ~/.local/state/platoon-harness/sessions/fix-auth/agents/ada/workspace
```

A fetch with a branch to land on, as here, is what makes a snapshot's commits yours, and so a snapshot removable; a fetch with none
writes only `FETCH_HEAD`.

## What a look sees

At the end of each agent's turn, and when a resumed agent comes back, the runtime looks at what it left, one look at a time: first
your checkout's new commits, then the agent's own workspace. A stopping agent's stop looks once more before it ends the workspace. A
look changes no ref, index or file, and records on `repo/<name>`, `<name>` being your repository's folder name:

- each new commit its workspace's HEAD reaches, and each commit those cite in an `Informed-By` trailer, parents first, once each;
- whose each commit is: the agent's whose workspace's HEAD reflog records making it, at the commit's own committer time, so a worker
  that builds on another's commit never takes it; a commit made in your checkout is nobody's, as is one no workspace made, or two;
- what a branch no longer reaches of the commits it had, after a reset, an amend or a rebase;
- each workspace's head, branch, any merge, rebase, cherry-pick, revert or bisect under way, and its uncommitted paths, conflicted
  first, with their lines added and removed, or `?` for an untracked or binary file, which nobody measured.

Your checkout's uncommitted state is recorded only when a role works there, since your own edits are not the session's. Declare what
a commit builds on with a trailer, `git commit --trailer Informed-By=<sha>`: a value of 4 to 40 hex digits naming one commit in its own
repository is resolved to its full SHA, and anything else, a branch name among them, is kept as written.

The terminal's header counts what changed, `/review` lists it, and a merge stopped on conflicts waits in the dock, and under Needs you
in the browser, until its agent's next turn. What a look cannot see:

- a one-turn agent's work, until its turn has ended;
- commits on a branch no workspace has at HEAD;
- a worktree an agent makes with git, which is outside every look;
- who made a commit when the agent's git did not move HEAD onto it, as `commit-tree` with `update-ref` does not, or when two
  workspaces made the same commit in one second. Attribution reads what the agent's own git wrote, so it is evidence, never proof.

A look runs the filters your repository's config names, as your own `git status` does. One that cannot read a workspace records the
gap `workspace_unobserved` and nothing else, and the Ending names each agent whose last look never finished as `unobserved`.

## Taking an agent's work

An agent's commits are on its branch in your repository, so you merge, rebase or cherry-pick them as you would anyone's:

```console
$ git log main..platoon-harness/fix-auth/ada
$ git merge platoon-harness/fix-auth/ada
```

The runtime never merges, rebases or resolves a conflict, and never moves a branch an agent has.

## What the journal recorded

When a session stops or closes, the runtime writes `commits.bundle` into the session folder, holding every commit the journal recorded
past the session's starting HEAD, and replaces the last one, keeping what it held. So a commit an agent amended or rebased away, which
git would prune after a while, can be fetched back:

```console
$ git bundle list-heads ~/.local/state/platoon-harness/sessions/fix-auth/commits.bundle
$ git fetch ~/.local/state/platoon-harness/sessions/fix-auth/commits.bundle 'refs/commits/*:refs/recovered/*'
```

It is built in a repository of its own beside it, so nothing is written into yours for it, and `session.stopped` records it, with how
many recorded commits git no longer had.
