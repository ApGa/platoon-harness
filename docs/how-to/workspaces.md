# Workspaces

Where each agent works, and what becomes of it.

**Goal:** choose where each agent of a team works, know before any cost what each mode refuses, and read, take, test or let go
of what an agent leaves behind.

**Prerequisites:**

- platoon-harness installed as [Install](../getting-started/install.md) says;
- for `worktree`, `snapshot` and `isolated`, a session started in a git work tree of a repository with a commit, and git
  2.36 or later;
- for `isolated`, which is experimental, Linux with [bubblewrap](https://github.com/containers/bubblewrap) and unprivileged
  user namespaces, and an auth profile, or a training system's gateway, for each role.

## Choose a mode

A role names one:

```toml
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
workspace = "worktree"            # "shared" (the default) | "worktree" | "snapshot" | "isolated"
```

There is no branch, path, base, lock or removal option. The mode recorded is the one that ran: a mode that cannot be given fails
loudly, before any cost where that can be seen, and never becomes another. Section 13 of [the architecture](../architecture.md) is
the design, and [compatibility.md](../reference/compatibility.md#workspaces) says what each harness sees.

### What each mode promises

| Mode | It is | State |
|---|---|---|
| `shared` | The session's checkout, its cwd. Every agent's writes land there at once, and nothing in it is private or confined | Given everywhere, with or without git |
| `worktree` | A linked git worktree of your repository, on a branch of its own, made at your checkout's HEAD when its agent's workspace is made. It shares the repository's refs, objects, config and hooks, and what runs there can reach anything you can, so it is not a sandbox | Given on git |
| `snapshot` | A repository of its own holding your tree as your git sees it, uncommitted and untracked work included, but no ignored file. It reads your objects and holds its own, has no remote, and git in it writes only its own repository, while what runs there can still reach anything you can | Given on git |
| `isolated` | A snapshot whose harness, and everything the runtime runs in its tree, one extension's isolation confines. It writes only its own folder and a private /tmp, sees none of your home, no session folder and only its own processes, and still reaches the network | Experimental, given where an extension the team names confines it, as the SDK's own `bwrap` does on Linux, [below](#where-an-isolated-agent-runs) |

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
lives in that repository and not in yours. It holds your tree as your git sees it, what `git add -A` would stage, so your ignored
files, such as a `.venv`, stay out, and it takes your `user.name` and `user.email`, so an agent commits there as in a worktree.
Your repository's own hooks do not run in a snapshot, though a `core.hooksPath` your global or system config sets does, and
nothing is written into your git directory.

## Where an isolated agent runs

An isolated workspace is a snapshot, made, looked at and ended as one, whose harness runs inside the isolation that one extension the
team names gives. The SDK ships one, `bwrap`, on Linux's bubblewrap, which needs unprivileged user namespaces:

```toml
extensions = ["bwrap"]

[auth.anthropic]
env = ["ANTHROPIC_API_KEY"]

[roles.reviewer]
harness = "claude"
auth = "anthropic"
workspace = "isolated"
```

Inside it, the harness and everything it starts:

- write only the agent's folder, which holds its workspace and its home, and a /tmp of its own;
- find these empty and read-only: your home, as `HOME` names it and as your account does; the session root, with every session
  under it, its journal and tokens among them; and the runtime directory, where sockets are made. The only exceptions are your
  repository's objects, which the snapshot borrows, and the paths its harness's driver declares it is installed at, all read-only;
- see only their own processes, all of which end when the harness does, even one that started a session of its own.

The harness ends with the runtime that started it, so a runtime killed outright takes it down, where an unconfined harness lives on
until the next runtime reaps it, and a resume starts it again as after any crash. A stop gives it the end of its input and its grace,
and then kills it outright, saying so as the gap `crash_window`, since its confiner passes no `SIGTERM` on.

What stays reachable: everything you can read outside those folders, the network, every loopback service, every abstract socket,
and every socket file outside those folders, since a read-only mount does not stop a connect to one. It runs on the same kernel, as
you. Our tools and a training system's gateway are on loopback, so they stay reachable too. It is experimental: its escape tests have
run on one Linux host ([compatibility](../reference/compatibility.md#6-supported-platforms)).

Its harness's home is `home/` in the agent's folder, so none of your harness settings, logins or memory are read or written. A role
needs an auth profile, or a training system's gateway, for model access. Neither its git nor the runtime's git in its tree reads
your global git config, so your global excludes do not apply there: a file only they would ignore shows as untracked, and the stop
keeps the workspace for it.

Every git call the runtime makes in that tree, each look and each [diff](#read-a-diff) among them, goes through the same
isolation, with `PATH` and `HOME` alone, so a filter or an fsmonitor an agent writes into its own repository's config runs inside,
never as you. Only a launch
inside the isolation records assurance `isolated`; every other agent's is `cooperative`. A [runtime test](#test-a-commit) of a
commit a look of such a workspace found, or one built on it, is refused, as its code runs only there.

Before any cost, besides wherever a snapshot is refused, `isolated` is refused when no extension the team names gives an isolation,
when two do, naming both, when the isolation cannot confine here, as `bwrap` cannot where a kernel setting, AppArmor or a container's
seccomp blocks user namespaces, when a harness declares no path it is installed at, as one in the runtime's own process cannot, and
for a role with no auth profile whose harness signs itself in, since that login is in your home. A spawn asks the isolation again
before it builds the snapshot. [compatibility.md](../reference/compatibility.md#workspaces) says what each harness declares.

## Before any cost

`team check`, `run` and `Session.start` refuse, with exit 78 on the command line, each of these, every one named:

- A git mode where the cwd is in no git work tree, the repository is bare or has no commit, or git is older than 2.36.
- A git mode where the session's folder in your repository would be missing from the workspace: for a worktree, one that holds
  nothing committed at your HEAD; for a snapshot, one that holds nothing tracked or unignored.
- LFS-tracked files with no LFS filter configured, which a worktree would hold as their pointers.
- A branch at `platoon-harness`, at `platoon-harness/<session>` or under it. Branches outlive their sessions on purpose, so a reused
  session name meets its own old ones: give the session another name, or run the commands the refusal names once nothing on them is
  wanted, the release of a kept worktree that has one checked out first, then `git branch -d`, which refuses a branch whose commits
  are merged nowhere.
- In every mode, a session folder that lies inside your repository's work tree and is not ignored there, since an agent's `git add -A`
  would commit its credentials.

A snapshot is refused besides where git in it would see your tree otherwise than your own git: a tracked file with a `filter`
attribute, LFS and git-crypt among them, since only your config runs that filter; a sparse checkout, which it would hold whole; an
untracked repository inside your tree, which a capture leaves out; and a merge, rebase, cherry-pick, revert or bisect under way in
your checkout, or a conflicted path, which a capture would take as settled. Use `worktree` for these, or finish what is under way.
These are checked again when each snapshot is made, since your checkout may have changed since the session opened, and a snapshot
refused then, or one whose build fails, leaves nothing behind.

And warn of submodules, which stay uninitialized in each workspace, of uncommitted changes in your checkout, named, which a worktree
does not carry and a snapshot does, and of a Codex role whose commits would each wait on an approval, or be refused under
`approvals = "deny"`, below.

## What each harness sees there

A worktree holds what is committed at its base and nothing else: untracked project files, such as `CLAUDE.local.md`,
`.claude/settings.local.json`, `.env` or a `.venv`, are absent, so an agent can behave otherwise than it would in your checkout. Your git
hooks run for agents' commits there, while `post-checkout` does not run when the runtime makes one. Claude Code's auto memory is keyed
on the repository and shared by every worktree of it, a channel no topology binds.

Claude Code's own worktree tools are off on every launch. A worktree an agent makes with git from a shell is its own affair, and
outside what the runtime records.

**Codex** keeps `.git` read-only under its `workspace-write` and `read-only` sandboxes, so each commit asks for an approval that runs
outside the sandbox. Choose one of three postures for a Codex role in a worktree or a snapshot:

| Posture | Says | What it means |
|---|---|---|
| No sandbox | `sandbox = "danger-full-access"` | Commits work, and its commands run with no sandbox at all |
| The sandbox, its escalations allowed | `approvals = "allow"` | The sandbox stays, and each escalation the model asks for is allowed by policy |
| Asking | `approvals = "ask"`, the default | You approve each commit, so a headless run ends `needs_human` at its first |

## When a workspace goes

At its agent's end, its stop removes the worktree only when nothing would go with it, as git says, whatever your config says of
untracked files or submodules:

- its processes are proved gone;
- its status shows no path, ignored ones included;
- no merge, rebase, cherry-pick, revert or bisect is under way;
- no index entry is hidden from status by `skip-worktree` or `assume-unchanged` while its file is in the tree, as one a sparse
  checkout leaves out is not;
- every commit its HEAD, its reflog or its own refs hold is its base, or reachable from a ref of your repository. Its branch is one, so
  committed work on its branch never keeps a worktree.

Then it is unlocked and removed with plain `git worktree remove`. Otherwise it stays, locked, and the Ending's `workspaces` names it with
its host, path, branch, size on disk and why, each reason naming what it found, such as `1 uncommitted path: notes.md`,
`ignored: .venv/, __pycache__/`, `a rebase under way` or `2 commits only it holds, in its HEAD, reflog or own refs: 2a190b2d1e6b,
99d5b8af9412`. No branch is ever removed. Each step of a stop is safe to repeat, so one a crash cut finishes when the session resumes.

Its `release` is the commands that let it go, given only when they lose nothing it was kept for but the ignored files its `why` names.
For a worktree kept for its ignored files alone, they are:

```console
$ git -C ~/src/app worktree unlock ~/.local/state/platoon-harness/sessions/fix-auth/agents/ada/workspace
$ git -C ~/src/app worktree remove ~/.local/state/platoon-harness/sessions/fix-auth/agents/ada/workspace
```

`remove` deletes the ignored files without asking. For any other reason `release` is empty, since `remove` would succeed on a clean
tree and drop a commit only the worktree's reflog holds, and `why` says what to save first: commit or discard its paths, finish or
abort what is under way, and keep a commit it names with `git branch <name> <sha>`. Then the two commands above let it go. A path with
a space in it is quoted, so each command pastes as it stands. Once a session folder is deleted, `git worktree unlock <path>` and then
`git worktree prune` forget its worktrees, and `git branch -d` deletes their branches.

Closing a session ends no agent, so it keeps the workspaces of agents that never ended, named `its agent has not ended`, and an agent
whose stop did not finish is named `its stop has not finished`. Neither has a `release`, since no stop has looked at what letting it go
would lose: end the agent, or resume the session, first.

A snapshot goes by the same rule, where the commits it alone holds are those of all its refs, its stash and its reflogs that are
neither its base nor reachable from a ref of yours. A kept one is made whole: what it borrowed from your repository is packed into
its own, and its alternates are removed, so it no longer depends on yours. When what it holds alone is commits its branch holds, and
ignored files, its `release` fetches the branch into your repository, which makes those commits yours, then deletes the folder:

```console
$ git -C ~/src/app fetch ~/.local/state/platoon-harness/sessions/fix-auth/agents/ada/workspace \
    platoon-harness/fix-auth/ada:platoon-harness/fix-auth/ada
$ rm -rf ~/.local/state/platoon-harness/sessions/fix-auth/agents/ada/workspace
```

A snapshot that holds uncommitted paths, a stash, a commit on another branch or one only its reflogs hold gets no `release`, as the
fetch would leave them behind and the removal take them: `why` names them, and `git -C <path> stash list` and `git -C <path> branch`
show them. A fetch with a branch to land on, as here, is what makes a snapshot's commits yours; a fetch with none writes only
`FETCH_HEAD`.

## What a look sees

At the end of each agent's turn, and when a resumed agent comes back, the runtime looks at what it left: first your checkout's new
commits, then the agent's own workspace. Looks of different agents' workspaces run at once, and looks of one workspace, your
checkout's among them, run one at a time.
A stopping agent's stop looks once more before it ends the workspace. A look changes no ref, index or file, and records on
`repo/<name>`, `<name>` being your repository's folder name:

- each new commit its workspace's HEAD reaches, and each commit those cite in an `Informed-By` trailer, parents first, once each;
- whose each commit is: the agent's whose workspace's HEAD reflog records making it, at the commit's own committer time, so a worker
  that builds on another's commit never takes it, and whoever ran git there, you included, as [below](#resolve-an-agents-conflict);
  a commit made in your checkout is nobody's, as is one no workspace made, or two;
- what a branch no longer reaches of the commits it had, after a reset, an amend or a rebase;
- each workspace's head, branch, any merge, rebase, cherry-pick, revert or bisect under way, and its uncommitted paths, conflicted
  first, with their lines added and removed, or `?` for an untracked or binary file, which nobody measured.

Your checkout's uncommitted state is recorded only when a role works there, since your own edits are not the session's. A commit
declares what it builds on with a trailer, a commit by its SHA or an event of the session by its ref, as
`git commit --trailer Informed-By=board/notes/spec@3`, which its record cites once checked, as
[Refs and citations](provenance.md#refs-and-citations) says.

The terminal's header counts what changed, `/review` lists it, and a merge stopped on conflicts waits in the dock, and under Needs you
in the browser, saying what settles it, as [below](#resolve-an-agents-conflict), until its agent's next turn. What an agent wrote of
a commit is cut to fit: its author and each `Informed-By` value to 256 characters, ending in `…` where cut, and a commit's first 16
values, with how many it had. What a look cannot see:

- a one-turn agent's work, until its turn has ended;
- a commit made and undone within one turn, as by an amend or a reset before the turn ended, which only the workspace's reflog
  holds, so the bundle below does not keep it, though its stop keeps the workspace for it;
- commits on a branch no workspace has at HEAD;
- a worktree an agent makes with git, which is outside every look;
- who made a commit when the agent's git did not move HEAD onto it, as `commit-tree` with `update-ref` does not, or when two
  workspaces made the same commit in one second. Attribution reads what the agent's own git wrote, so it is evidence, never proof.

A look runs the filters your repository's config names, as your own `git status` does, and in an isolated workspace those its
agent's config names, inside its isolation. One that cannot read a workspace records the gap `workspace_unobserved` and nothing
else, and the Ending names each agent whose last look never finished as `unobserved`.

## Take an agent's work

A worktree agent's commits are on its branch in your repository, so you merge, rebase or cherry-pick them as you would anyone's:

```console
$ git log main..platoon-harness/fix-auth/ada
$ git merge platoon-harness/fix-auth/ada
```

A snapshot agent's commits are in the snapshot's own repository until you fetch its branch, as its `release` does, and `/review` says
so of its group. A fetch runs your git in that repository, outside any isolation, so read an isolated agent's `<path>/.git/config`
before you fetch from it, as you would any repository you did not make. The runtime never merges, rebases or resolves a conflict,
and never moves a branch an agent has. For a team whose workers hand their branches to one merger, [topologies.md](topologies.md#merge-worktrees-through-a-queue)
writes out the merge queue: a queue and a merger in a worktree, whose look records each merge or conflict, and a conflict that goes
back to its worker through the task.

## Resolve an agent's conflict

A merge, rebase or cherry-pick an agent's git stopped on conflicts is the agent's to resolve. Tell it, as the conflict's Write to it
does in the dock and under Needs you, and its next turn takes it up. Or resolve it in your own checkout, from the agent's branch, as
you would take its work. That leaves the agent's merge stopped in its workspace, and its place stands until the agent's next turn
begins, and comes back at the look after it while the merge stays stopped, so tell the agent too, which aborts or finishes it.
Never resolve it in the agent's workspace: a commit made there is recorded as that agent's, whoever made it,
since whose a commit is reads that workspace's HEAD reflog, which says the workspace made it and not who ran git, and nothing records
who committed. That record is evidence at the workspace's assurance, never proof. The conflict's own words say so:

```text
merge stopped on conflicts in 1 file, README: tell @ada, or resolve it in your own checkout, never in its workspace, where any commit is recorded as @ada's
```

A conflict in your checkout, where a role works in it, is yours, and says to resolve it there. A commit made in your checkout is
nobody's.

## Test a commit

A person or a program can have the runtime run the team's test at a recorded commit, and record what it came to beside the commit:

```toml
test = { command = ["uv", "run", "pytest", "-q"], timeout = "10m" }
```

```console
$ platoon-harness repo test fix-auth --commit 3f9c2a1
```

This runs that commit's maker's code as you, unconfined: whatever the commit holds that the command loads, a `conftest.py` or a
`Makefile` among it, runs with everything you can reach. So an agent can never ask for it, as a tool or otherwise, whatever its grants;
a `test` from a project or team file needs the trust step, `--trust` or `trust_project`, as a `command` harness does; the terminal asks
before it runs one; and a commit a look of an isolated workspace found, or one built on it, is refused, saying why — the look that
found the code decides this, not the reflog an isolated agent writes and could clear. `timeout` is required.

It runs in a clean detached checkout of that commit, in the session's subfolder of it: a repository of its own in the session folder's
`tests/<effect>/`, which borrows the objects of your repository and of each workspace's own but an isolated one's, so nothing is written
into any of them and none of their own config applies. The command gets what every process inherits, `PATH` and `HOME`, and a
`TMPDIR` of its own. A program it names by a relative path is the commit's own. The checkout goes once the test is recorded.

`repo.tested` on `repo/<name>` says what it came to: `passed` for exit 0, `failed` for another exit or a signal of its own, and `error`
when it could not run to its end, as when its timeout came first, which ends everything it started. It names the command, its exit, the
seconds it took and the bytes it printed, and carries the last 64 KiB of that as its body, which `platoon-harness blob get <session>
--ref repo/<name>@<version>` reads, a page at a time. The `changes` view's commit row gives the latest outcome as `tests`, with why it failed or
erred and the ref of its record, and the terminal's `/review` shows the outcome and the reason and tests the chosen commit with `t`. A clean checkout lacks untracked and ignored files, so its outcome can honestly differ
from the agent's own run. A test keeps its session from settling until it ends, and one a crash or a stop cut off runs again when the
session resumes.

## Read a diff

A person or a program can have the runtime read a recorded commit's patch, or what a workspace holds uncommitted, and keep it
beside the commit:

```console
$ platoon-harness repo diff fix-auth --of 3f9c2a1
$ platoon-harness repo diff fix-auth --of @ada
```

`--of` names a recorded commit, by its SHA or its first 4 or more hex digits, for its patch against its first parent, or a
workspace, `@ada` for an agent's own or `shared` for your checkout, for what it holds uncommitted against its HEAD: its tracked
files, staged or not, then each untracked file git does not ignore, as a new one. A workspace is read once it is made, and after
its agent's stop if the stop kept it; your checkout only while a role works there, as your own edits are not the session's. An
agent never asks for a diff: it reads a commit through `repo.commit` or its own git.

The runtime reads it where the workspace lives: a commit in the repository of the workspace whose look recorded it, or in yours
once that workspace has gone, and an isolated workspace inside its isolation. Git reads the diff with no external diff,
textconv, pager, hook or remote, though a filter your config names runs for an uncommitted diff, as in your own `git status`.

`repo.diffed` on `repo/<name>` keeps it: the commit, or the workspace, the HEAD it was read against and `read_at`, when its
reading began, `read_in`, the workspace whose repository it was read in, and the patch as its body, which `platoon-harness blob get <session> --ref repo/<name>@<version>` reads, a page at
a time, and which a message cites lines of by its ref, `repo/<name>@<version>#L40-52`. A patch past 64 KiB, as much as the journal
holds in an event's own body, is cut at the end of the last line that fits; the record says `cut` and its gist where, as
`3f9c2a1b2c3d patch, cut after 1022 lines at 64 KiB`, and the rest is in git. A file git takes for binary is named,
`Binary files a/x and b/x differ`, and never shown. A patch of a file that is not UTF-8 is kept as git printed it, but `blob get`
gives it as no text and no message can cite its lines, which its gist says, as
`3f9c2a1b2c3d patch, 6 lines, not UTF-8, so no line of it can be cited`. A diff that could not be read, as of a workspace gone
from under its agent, records why. A diff keeps its session from settling until it is read, and one a crash cut off is read again
when the session resumes. A look reads no patch, so a turn's end costs what it did.

A commit's patch never changes, so it is read once: asked for again while it is read, `repo diff` gives the same effect, and once
it is kept, that effect and the ref of its record, reading nothing. What a workspace holds uncommitted is read at each ask. The
terminal's `/review` opens each commit's patch and each workspace's uncommitted diff, a page at a time
([tui.md](tui.md#review-what-changed)).

What a diff cannot show: an untracked repository inside the tree, of which git shows no file, which its record counts as
`untracked_repositories` and its gist as `2 untracked repositories not shown`, and an untracked file past the bound, which `cut`
says. Git takes a file for binary by its content or by the attributes the workspace gives it, so an agent's `-diff` or `binary`
attribute, or a diff driver its config marks `binary`, has a text change read as `Binary files a/x and b/x differ`: the line is
git's, and says nothing of which decided. A workspace whose own repository has gone is not read, since git would find the one
around it: its record says why, as a look records the gap. An uncommitted diff is a moment's reading, so one of an agent in a turn
changes as it is read, and a file removed while it is read fails the read, saying so.

## Read workspaces from a script

`platoon-harness view watch <session> --name changes` gives the `changes` view's rows: each recorded commit, with its latest runtime
test's outcome and, when the team names a test, the act that runs it, each workspace's last reading and each uncommitted path, with
the `seq` that last moved it. An agent turns a commit's SHA into the ref its `based_on` cites with `repo.commit`, which records the read
as its exposure and says 'not recorded yet' until the look after the turn that made it; a person or a program reads the same with
`platoon-harness repo commit <session> --sha <sha>`, and a commit's patch or a workspace's uncommitted diff with
`platoon-harness repo diff`, as [Read a diff](#read-a-diff) says. `platoon-harness session ending <session>` gives the Ending,
whose `workspaces` are the kept ones with their reasons and any `release`, and whose `unobserved` names the agents whose last look
never finished.

## Recover a commit the journal recorded

When a session stops or closes, the runtime writes `commits.bundle` into the session folder, holding every commit the journal recorded
past the session's starting HEAD, and replaces the last one, keeping what it held. So a commit an agent amended or rebased away after a
look recorded it, which git would prune after a while, can be fetched back:

```console
$ git bundle list-heads ~/.local/state/platoon-harness/sessions/fix-auth/commits.bundle
$ git fetch ~/.local/state/platoon-harness/sessions/fix-auth/commits.bundle 'refs/commits/*:refs/recovered/*'
```

It is built in a repository of its own beside it, so nothing is written into yours for it, and `session.stopped` records it, with how
many recorded commits git no longer had.
