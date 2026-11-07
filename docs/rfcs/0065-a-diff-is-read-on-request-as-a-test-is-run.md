# RFC 0065: A diff is read on request, as a test is run

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`primitives/repo.py`](../../packages/sdk/src/platoon_harness/primitives/repo.py), [`runtime/git.py`](../../packages/sdk/src/platoon_harness/runtime/git.py), [`runtime/host.py`](../../packages/sdk/src/platoon_harness/runtime/host.py), [architecture section 5.4](../architecture.md#54-effects) and [section 13](../architecture.md#13-workspaces), [RFC 0034](0034-isolation-is-an-extension-s-and-the-runtime-s-git-runs-inside-it.md), [RFC 0056](0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md) and [RFC 0057](0057-an-agent-cites-a-commit-by-the-ref-the-journal-gives.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository |
| Implementation | `feat: Read a commit's patch or a workspace's diff on request, as an effect` |

## Summary

`repo.diff`, a person's or a program's command that an agent is refused, as `repo.test` is, asks the runtime for a recorded
commit's patch against its first parent or a workspace's uncommitted diff against its HEAD. A `diff` effect reads it with the
runtime's one git runner where the workspace lives: in the repository of the workspace a look found the commit in, a snapshot's
own among them, inside the isolation for an isolated one, and with no external diff, textconv or hook. The runtime keeps it on
`repo/<name>` as a `repo.diffed` event of its own, whose body is the patch, cut at the end of a line within 64 KiB and saying so.
A commit's patch is kept once, and asked for again gives its ref. An uncommitted diff is a moment's reading: it names the HEAD it
is against and when it was read, and asked for again is read again. A look reads no patch.

## Motivation

What a look records of a commit is its lines added and removed against its first parent and how many files it touched, and of a
workspace its uncommitted paths with their lines ([section 13](../architecture.md#13-workspaces)). Nobody can see from the session
what changed. The terminal's `/review` draws diffs disabled, saying they are planned, and so does the page's Review changes
([STATUS](../STATUS.md)). A program that checks a worker's change before it merges it cannot read the change from the record
either.

The first draft of milestone 4's plan kept every commit's patch and every uncommitted diff at every look, on the premise that a
look is the only place a patch can be read, since an op does no I/O (law 3). The premise is false. `repo.test` already asks the
runtime to do I/O as an effect, and keeps what it came to as a body ([RFC 0056](0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md)).
A look runs at every turn's end and keeps the session from settling until it ends, so a patch at every look would make every
handover pay for up to 64 patches and an uncommitted diff, whether anyone read them or not, at a cost nobody has measured past
100,000 files or on Lustre. And an uncommitted diff as the body of `workspace.changed` would clash with the body that event
already carries, the whole list of paths when its reading is cut, so a range of lines on it would name either.

## Proposal

### 1. A command, as a test is

```python
class Diffing(Args):
    of: str  # a recorded commit, by its SHA or its first 4 or more hex digits, or a workspace, `@ada` or `shared`

@op("repo.diff")
def diff(txn: Txn, a: Diffing) -> dict[str, Any]: ...  # {"effect": id}, or {"ref": ref} for a commit's patch kept
```

`repo.diff` takes what it reads the diff `of`: a recorded commit, by the name `repo.test` takes, or a workspace in the address
grammar, `@ada` for an agent's own and `shared` for the session's checkout, which no SHA can be. One argument, which every form
and command derived from the op requires, leaves nobody a way to give both or neither. It is no tool. It refuses an agent
whatever its grants, saying that an agent reads a commit through `repo.commit` or its own git: an agent's read is evidence (law
9), and its read of a patch would be an exposure the record would have to account for, which milestone 4 does not take on. It
refuses `unsupported` when the session observes no repository, and `conflict` once the session is closing. It refuses
`not_found` for a commit not recorded yet, as `repo.test` does, `invalid` for a name several commits begin with, and `not_found`
for a workspace the session holds none of: `@ada` before its workspace is made, once its stop removed it, or when ada works in
the shared one, and `shared` when no role works there, as a look records your checkout's state only then, your own edits not
being the session's. A workspace a stop kept is still read. It gives back the `diff` effect it requested, owned by no agent and
retried after a crash, as a test's is. `Session.repo_diff` and `platoon-harness repo diff` reach it, as they reach every op a
person may run.

### 2. Read where the workspace lives

The host performs a `diff` effect with the runtime's one git runner, which runs no hook, no fsmonitor and no gc, and writes no index:

- **A commit's patch** is what `git diff-tree -p --root --diff-merges=first-parent -M` shows of it, against the first parent a
  look counted its lines against. It is read in the repository of the workspace the look that recorded the commit was of, its
  `found_in`: a snapshot's own repository, which may be the only one that holds it, and an isolated one's under its isolation's
  wrap. Once that workspace has gone it is read in your repository, which a stop removes a workspace only for reaching every
  commit it held.
- **A workspace's uncommitted diff** is what `git diff-index -p -M` shows of its work tree against the HEAD it reads first,
  staged or not, then each untracked file git does not ignore, as a new file, as `git diff --no-index` shows it, until the patch
  passes its bound. It is read in the workspace's work tree, your checkout's top for `shared`, and under its wrap for an isolated
  one. An untracked repository inside the tree is passed over, as git shows no file of it.
- **Nothing runs that a repository's config names to show a diff.** Every diff passes `--no-ext-diff`, `--no-textconv` and
  `--no-color` and names its prefixes `a/` and `b/`, so neither `diff.external`, nor a `diff` attribute's `command` or
  `textconv`, nor a colour or a prefix setting reaches the patch. A commit's patch is read with no porcelain, so
  `log.showSignature` starts no `gpg`. A `filter` a config names does run for an uncommitted diff, as it does at a look and in
  your own `git status`, inside the isolation for an isolated workspace, where the agent's own config names it.
- **What git takes for binary is named and never shown,** as `Binary files a/x and b/x differ`, since no diff passes `--binary`
  or `--text`. A file a `diff` attribute marks as text git shows as text.

Git runs with a bound on what it prints. The runner reads the bound and one byte more, then closes its end of the pipe, which
ends git, so a patch of any size costs the runtime no more memory than the bound.

### 3. Kept as `repo.diffed`

The runtime records what it read through `repo.keep`, an op only it holds, as `repo.diffed` on `repo/<name>` with no agent in the
envelope, as it records a test:

```python
class Diffed(Args):
    effect: int
    sha: Sha | None = None          # a commit's patch,
    workspace: Where | None = None  # or a workspace's uncommitted diff,
    head: Sha | None = None         # against this commit,
    read_at: float | None = None    # read at this time, on the session's clock
    body: BodyRef | None = None     # the patch
    cut: bool = False
    why: str | None = None          # or why it could not be read
```

Its body is the patch: all of it, or its first 64 KiB cut at the end of the last line that fits, which `cut` says and its gist
says where, as `3f9c2a1b2c3d patch, cut after 1022 lines at 64 KiB`. A cut at a line's end splits no character, so a patch that
is text stays text, and `blob.get` reads it a page at a time by the record's ref. A citation names lines of it,
`repo/app@12#L40-52`, checked as any citation is ([section 7](../architecture.md#refs-and-citations)), so a person's message can
cite the lines it is about. A diff that could not be read, of a workspace that has gone or a commit no repository it may read
holds, records `why` and no body.

### 4. A commit's patch is kept once, and an uncommitted diff is read each time

A recorded commit never changes, so neither does its patch. The `Looks` view keeps each commit's diff: the effect reading it, then
its record's ref. Asked for again while it is read, `repo.diff` gives the same effect, and once it is kept, its ref, reading
nothing. A record that says why it could not be read holds no patch, so the next ask reads again.

A workspace's uncommitted diff is what the workspace held when it was read. Its record names the `head` it is against and
`read_at`, when its reading began, and its gist names the workspace and that head, as `@ada uncommitted against 3f9c2a1b2c3d, 40
lines`. Each ask reads again.

### 5. Recovery

`diff` is an effect kind of the host's, with `on_uncertain = retry`, and its row in section 5.4 is: repeat unless recorded. A
retried attempt finishes from its effect's `repo.diffed` when the journal holds one, reading nothing, and one a crash cut off
reads again from the start. Reading changes nothing, so reading again costs only time.

### 6. A look reads no patch

A look goes on recording lines, files and paths, and no patch, so a handover costs what it did.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep a patch at every look | Every turn's handover would pay for patches nobody reads: up to 64 commits' and an uncommitted diff per look, which keeps the session from settling, at a cost unmeasured past 100,000 files or on Lustre; and the patch would clash with the body `workspace.changed` already carries |
| Two arguments, `commit` and `workspace`, one of which is given | A form or a command derived from the op could give both or neither, and its example would show neither, since neither is required |
| A query that reads the diff | An op does no I/O (law 3), and a query keeps nothing, so each client would read it again and no citation could name its lines |
| A tool an agent calls | An agent's read of a patch is evidence the record would have to account for, as `blob.get` does by exposure, and milestone 4 does not take it on. An agent reads a commit through `repo.commit` and its own git. That an agent is refused is the default, pending the owner's ruling |
| Read every diff in your repository | A snapshot's commit may be only in its own repository, and an isolated agent's config, which names what git runs, is the agent's, so its git stays inside its isolation |
| `git show` for a commit's patch | It verifies a signature where `log.showSignature` is set, which starts the program `gpg.program` names. `diff-tree` shows the same patch and starts nothing |
| Keep a whole patch of any size | A body past 64 KiB is held outside the journal's row, in `blobs/`, which no op reads, so `blob.get` would give no text and a citation's lines would go unchecked |
| Cut at 64 KiB exactly | It can split a character, which leaves a text patch no text, and a line, which a citation names whole |
| Show untracked files through a scratch index, with `git add -N` | `git add -N` writes the empty blob into the workspace's object store, and the scratch index needs a place an isolated agent can write, from which the runtime would then remove it |
| Leave untracked files out | A new file an agent has not added is often most of its uncommitted work, and a diff without it would mislead |
| Read on past the bound to count a cut patch's length | A patch of gigabytes would cost the runtime the time to read it all. What a commit added and removed is on its `repo.committed`, and a workspace's paths on its `workspace.changed` |

## Consequences

- A person or a program reads what changed from the record, and a message cites the lines it is about.
- A diff costs only when someone asks for one, and a look and a handover cost what they did.
- In this repository's own history, about one commit in five has a patch past 64 KiB, which is cut. Its record says so, and the
  rest is in git, at the commit's SHA.
- An uncommitted diff is a moment's reading. A workspace whose agent is in a turn changes as it is read, and a file removed
  between the list of untracked files and its reading fails the read, saying so, so the next ask reads again.
- A filter a repository's config names runs for an uncommitted diff, as it does at every look.
- An agent cannot read a patch through the runtime. A message that cites lines of one hands it the message, and not the patch.
- What a diff costs on a repository past 100,000 files or on Lustre is unmeasured. It is paid only on request, and twice for a
  read a crash cut off.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 read on request | `repo.diff`, the `diff` effect and its recovery, `repo.keep` and `repo.diffed`, a commit's patch kept once and an uncommitted diff saying when it was read | `tests/unit/primitives/test_repo.py`, `tests/unit/runtime/test_diffs.py`, and `test_a_diff_left_uncertain_by_a_crash_is_read_again` in `tests/unit/runtime/test_recovery.py` | |
| M2 reviewed in both clients | `/review` and the page's Review changes draw a patch a page at a time through one shared wording, and a comment is a person's message that cites the commit or lines of its patch | The review tests of milestone 4's stage S06 | |

## Open questions

1. May an agent ask for a diff? M1 builds the default, pending the owner's ruling: no, as a diff is a person's or a program's,
   as a test is, and an agent reads a commit through `repo.commit` or its own git. A yes would make `repo.diff` a tool and record
   an agent's read of a patch as its exposure, and would remove nothing M1 builds. Needed before an agent may ask.
2. What does reviewing mean in milestone 4? The default, pending the owner's ruling, is that a person asks for and reads diffs in
   both clients and comments as a message that cites the commit or lines of its patch, with no noun for a review. Needed before
   M2.

## Evidence

- The bound is the most the journal holds in an event's own body, 64 KiB, as for a test's output
  ([RFC 0056](0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md)), and a measurement says how often it
  cuts. Each of the 442 commits of this repository at `04e34f1`, as M1 reads it:

  ```console
  $ git rev-list 04e34f1 | while read sha; do
      git diff-tree -p --root --diff-merges=first-parent --no-commit-id -M --no-ext-diff --no-textconv --no-color "$sha" | wc -c
    done | sort -n
  ```

  361 of them, 81.7%, fit in 64 KiB. Half fit in 16 KiB, 91% in 128 KiB and 97% in 256 KiB; the 90th percentile is 111 KiB and
  the largest 1.4 MiB. Each took a median 21 ms to read and 157 ms at most, on a Lustre file system from a shared host with 192
  threads of Xeon Platinum 8468. These commits are larger than most an agent makes in one turn, as each holds a whole change
  with its tests and docs, so the share cut in a session is likely smaller (UNVERIFIED).
- The tests named in the rollout plan's M1.
