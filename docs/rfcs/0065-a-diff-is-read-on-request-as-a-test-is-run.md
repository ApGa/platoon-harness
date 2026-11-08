# RFC 0065: A diff is read on request, as a test is run

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`primitives/repo.py`](../../packages/sdk/src/platoon_harness/primitives/repo.py), [`runtime/git.py`](../../packages/sdk/src/platoon_harness/runtime/git.py), [`runtime/host.py`](../../packages/sdk/src/platoon_harness/runtime/host.py), [`review.py`](../../packages/cli/src/platoon_harness_cli/review.py), [`tui/review.py`](../../packages/cli/src/platoon_harness_cli/tui/review.py), [`web/server.py`](../../packages/cli/src/platoon_harness_cli/web/server.py), [`web/overlay.js`](../../packages/cli/src/platoon_harness_cli/web/overlay.js), [architecture section 5.4](../architecture.md#54-effects) and [section 13](../architecture.md#13-workspaces), [RFC 0034](0034-isolation-is-an-extension-s-and-the-runtime-s-git-runs-inside-it.md), [RFC 0056](0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md), [RFC 0057](0057-an-agent-cites-a-commit-by-the-ref-the-journal-gives.md) and [RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository |
| Implementation | `feat: Read a commit's patch or a workspace's diff on request, as an effect`; `feat: Keep a commit's patch once and say when an uncommitted diff was read`; `refactor: Word what changed once for the terminal and the page`; `feat: Draw a commit's patch and a workspace's diff in the review, a page at a time`; `feat: Comment on a diff's lines as a message that cites them`; `feat: List what changed in the page, with each commit's test and patch` |

## Summary

`repo.diff`, a person's or a program's command that an agent is refused, as `repo.test` is, asks the runtime for a recorded
commit's patch against its first parent or a workspace's uncommitted diff against its HEAD. A `diff` effect reads it with the
runtime's one git runner where the workspace lives: in the repository of the workspace a look found the commit in, a snapshot's
own among them, inside the isolation for an isolated one, with no external diff, textconv or hook, reaching no remote, and each
object as it is stored. The runtime keeps it on
`repo/<name>` as a `repo.diffed` event of its own, whose body is the patch, cut at the end of a line within 64 KiB and saying so.
A commit's patch is kept once, and asked for again gives its ref. An uncommitted diff is a moment's reading: it names the HEAD it
is against and when it was read, and asked for again is read again. A look reads no patch. In step 2, the terminal's `/review`
and the page's Review changes list what changed in one wording, open each commit's patch and each workspace's uncommitted diff a
page at a time, test a commit after one question, and send a comment on chosen lines as a person's message to the change's
maker that cites them, or the commit.

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
def diff(txn: Txn, a: Diffing) -> dict[str, Any]: ...  # {"effect": id}, and "ref" beside it for a commit's patch kept
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

The host performs a `diff` effect with the runtime's one git runner, which runs no hook, no fsmonitor and no gc, reaches no
remote, and writes no index:

- **A commit's patch** is what `git diff-tree -p -M <parent> <sha>` shows of it, from the tree of the first parent its own
  object names, the one a look counted its lines against, or from the empty tree for a root. It is read in the repository of the
  workspace the look that recorded the commit was of, its `found_in`: a snapshot's own repository, which may be the only one
  that holds it, and an isolated one's under its isolation's wrap. Once that workspace has gone it is read in your repository,
  which a stop removes a workspace only for reaching every commit it held.
- **A workspace's uncommitted diff** is what `git diff-index -p -M` shows of its work tree against the HEAD it reads first,
  staged or not, then each untracked file git does not ignore, as a new file, as `git diff --no-index` shows it, until the patch
  passes its bound. It is read in the workspace's work tree, your checkout's top for `shared`, and under its wrap for an isolated
  one, and only where git finds the work tree's own repository at its root: one whose repository has gone, inside yours, would
  have git read yours as the agent's, so it records why instead, as a look records the gap. An untracked repository inside the
  tree is passed over, as git shows no file of it, and its record counts each one it passed over.
- **No program a repository's config names runs to show a diff, but a filter.** Every diff passes `--no-ext-diff`,
  `--no-textconv` and `--no-color` and names its prefixes `a/` and `b/`, so neither `diff.external`, nor a `diff` attribute's
  `command` or `textconv`, nor a colour or a prefix setting reaches the patch. A commit's patch is read with no porcelain, so
  `log.showSignature` starts no `gpg`. The runner allows no transport, `GIT_ALLOW_PROTOCOL` set and empty, and fetches no missing
  object, `GIT_NO_LAZY_FETCH`, so a partial clone's promisor remote, a transport program or an `ssh` command a config names is
  never reached, as it would be to fetch an object a diff needs that the store has dropped. A `filter` a config names does run for
  an uncommitted diff, as it does at a look and in your own `git status`, inside the isolation for an isolated workspace, where
  the agent's own config names it.
- **Each object is read as it is stored.** Every git of a diff sets `GIT_NO_REPLACE_OBJECTS`, so no replace ref stands in for
  the commit a SHA names or for the HEAD an uncommitted diff is against, and a commit's first parent is read from its own object,
  so no graft and no shallow list names another. Whoever writes a repository's refs and files, an agent its snapshot's, cannot
  change which patch is recorded for a SHA.
- **What git takes for binary is named and never shown,** as `Binary files a/x and b/x differ`, since no diff passes `--binary`
  or `--text`. Git takes a file for binary by its content or by the attributes the workspace's tree and repository give it, so a
  `-diff` or `binary` attribute, or a `diff` driver whose config sets `binary`, makes a text change read as binary, and a `diff`
  attribute that marks a file as text has git show it as text. The line is git's either way, and says nothing of which
  decided.

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
    read_in: Where | None = None    # read in this workspace's repository,
    head: Sha | None = None         # against this commit,
    read_at: float | None = None    # read at this time, on the session's clock
    body: BodyRef | None = None     # the patch
    cut: bool = False
    untracked_repositories: int = 0 # in the work tree, of which it shows no file
    why: str | None = None          # or why it could not be read
```

Its body is the patch: all of it, or its first 64 KiB cut at the end of the last line that fits, which `cut` says and its gist
says where, as `3f9c2a1b2c3d patch, cut after 1022 lines at 64 KiB`. A cut at a line's end splits no character, so a patch that
is text stays text, and `blob.get` reads it a page at a time by the record's ref. A citation names lines of it,
`repo/app@12#L40-52`, checked as any citation is ([section 7](../architecture.md#refs-and-citations)), so a person's message can
cite the lines it is about. Git shows as text a file with no NUL byte near its start, whatever its encoding, so a patch of a file
that is not UTF-8 is kept as git printed it, but is no text: `blob.get` gives it as none, no citation can name its lines, and its
gist says so, as `3f9c2a1b2c3d patch, 6 lines, not UTF-8, so no line of it can be cited`. An uncommitted diff's gist names the
untracked repositories it passed over, as `, 2 untracked repositories not shown`. A diff that could not be read, of a workspace
that has gone or a commit no repository it may read holds, records `why` and no body. `read_in` names the workspace whose
repository git read it in, or was to: a workspace's own for its uncommitted diff, and for a commit's patch the one its look found
it in, or yours, `shared`, once that had gone, which only the runtime knows when it reads, so a client can say where it was read.

### 4. A commit's patch is kept once, and an uncommitted diff is read each time

A recorded commit never changes, so neither does its patch. The `Looks` view keeps each commit's diff: the effect reading it, then
its record's ref. Asked for again while it is read, `repo.diff` gives the same effect, and once it is kept, that effect and the
record's ref, reading nothing, so a client finds the record past the effect's request whichever it was given. A record that says why it could not be read holds no patch, so the next ask reads again.

A workspace's uncommitted diff is what the workspace held when it was read. Its record names the `head` it is against and
`read_at`, when its reading began, and its gist names the workspace and that head, as `@ada uncommitted against 3f9c2a1b2c3d, 40
lines`. Each ask reads again.

### 5. Recovery

`diff` is an effect kind of the host's, with `on_uncertain = retry`, and its row in section 5.4 is: repeat unless recorded. A
retried attempt finishes from its effect's `repo.diffed` when the journal holds one, reading nothing, and one a crash cut off
reads again from the start. Reading changes nothing, so reading again costs only time.

### 6. A look reads no patch

A look goes on recording lines, files and paths, and no patch, so a handover costs what it did.

### 7. Reviewed in both clients (step 2)

Reviewing, in milestone 4, is a person reading diffs and commenting on them, with no noun for a review: an agent reviewer is a
role in the review example. Both clients say what changed in the words of one module of the command line's package,
`review.py`, as provenance's are ([RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md)):

- **What changed** is the `changes` view's rows as lines, grouped by workspace as `/review` grouped them, each line in parts that
  each carry a tone, plain, strong, faint, good, bad or warn, which the terminal draws in its colours and the page by class. A
  commit's line opens its patch, and a workspace's heading or one of its paths what it holds uncommitted. A line past the
  person's mark on `repo/<name>` is new, and the page, which keeps no marks, marks none.
- **A diff is asked for and awaited.** A client asks `repo.diff`, then follows the repository's streams and the effect's own past
  the effect's request until its `repo.diffed`, which it finds whether the effect reads now or read before, as `repo.diff` gives
  the effect either way. An effect that failed is said, with its error.
- **A page at a time.** A client reads the patch whole, by its record's body, which is at most 64 KiB, and draws it 500 lines at
  a time, drawing on when the person asks. Each line is numbered as a citation names it, as the kernel numbers a body's lines,
  and toned by what it is: a file's
  first line strong, what heads a file or a hunk faint, an added line good, a removed one bad, and git's `Binary files` line,
  which names a file and shows none of it, warn.
- **Above and below.** Above the patch, the record's gist, then where it was read, by `read_in` and the mode of that
  workspace: your repository or your checkout, an agent's worktree, a snapshot's own repository, or inside an isolation; and for
  an uncommitted diff when, as `What it held at 14:02:11, read in @ada's worktree.`, since it changes as its agent works. Below
  the last line of a cut patch, that it was cut at the end of the last line within 64 KiB and the rest is in git at its commit,
  or uncommitted in its workspace. A patch that is no text is not drawn, saying so.
- **Text stays text.** The terminal draws every line through `SafeText`, so a control shows as its escape and markup as
  itself, and the page puts every word through its `html` template under its hash-only policy.
- **A test, after one question.** A commit's act from the `changes` view, `repo.test`, is taken from either client after the
  person says yes to its label, which says whose code it runs as them, unconfined, or is disabled, saying why.
- **A comment is a message.** A comment is the person's `message.send` to the change's maker, the agent whose workspace made the
  commit, or the agent whose workspace an uncommitted diff is of, with `based_on` citing the lines chosen of the diff,
  `repo/app@12#L40-52`, or with none chosen, the commit's `repo.committed` or an uncommitted diff's record whole. It needs no new
  op. A change no agent's workspace made, a commit that is nobody's or your checkout's diff, has nobody to take a comment, and its
  comment is disabled, saying so. A comment's text becomes its gist and body as the composer's does.
- **The page reads through `x_read`** ([RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md)), with two panes more:
  `changes`, the lines of what changed, and `diff`, which by an `effect` holds until that effect's record is in the journal, for at
  most the 25 s the feed holds, and gives the diff with every line of its patch and how many the page draws at a time. A pane
  reads, the record by following the journal and the patch by its body, which writes nothing either. Asking for a diff, testing and commenting go
  through `/x/command`, so on a view link and on history they are disabled, saying why, as every act is.

```text
POST /v1/x_read {"pane": "changes"}                        -> {"repo", "lines"}
POST /v1/x_read {"pane": "diff", "effect": 38}             -> {"reading": true} or {"diff", "page"}
```

The terminal's `/review` lists what changed, Enter opens a diff and `t` tests the chosen commit. In the diff Space chooses the
line under the cursor, and pressed on another every line from the first to it, and `c` writes a comment in a composer at the
foot. The page's Review changes, in its top
bar and on an agent's page, opens the list in the pane, each commit with Patch and Test and each workspace with Uncommitted diff,
and the diff in the same pane, `review=` in the address naming what it shows, where a click on a line's number chooses it,
Shift and a click a range, and Comment sends what is written below.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep a patch at every look | Every turn's handover would pay for patches nobody reads: up to 64 commits' and an uncommitted diff per look, which keeps the session from settling, at a cost unmeasured past 100,000 files or on Lustre; and the patch would clash with the body `workspace.changed` already carries |
| Two arguments, `commit` and `workspace`, one of which is given | A form or a command derived from the op could give both or neither, and its example would show neither, since neither is required |
| A query that reads the diff | An op does no I/O (law 3), and a query keeps nothing, so each client would read it again and no citation could name its lines |
| A tool an agent calls | An agent's read of a patch is evidence the record would have to account for, as `blob.get` does by exposure, and milestone 4 does not take it on. An agent reads a commit through `repo.commit` and its own git. That an agent is refused is the default, pending the owner's ruling |
| Read every diff in your repository | A snapshot's commit may be only in its own repository, and an isolated agent's config, which names what git runs, is the agent's, so its git stays inside its isolation |
| `git show` for a commit's patch | It verifies a signature where `log.showSignature` is set, which starts the program `gpg.program` names. `diff-tree` shows the same patch and starts nothing |
| `git diff-tree --root --diff-merges=first-parent <sha>`, which finds the parent itself | Git takes a commit's parents from a graft or a shallow list where one names it, so whoever writes the repository's files could have another parent's patch, or the whole tree's, recorded for the SHA. Its own object names the parent, and for every commit of this repository the two print the same bytes |
| Honouring replace refs, grafts and shallow lists, as your own git does | A recorded patch is the SHA's, which a person and a citation take it for. A replace ref the agent wrote would have another commit's patch recorded under it with nothing to say so |
| Reaching a promisor remote for an object the store has dropped | Fetching runs what the config names, a transport program or an `ssh` command, as you or, for an isolated workspace, inside its isolation with the network it has. The runtime never means to fetch, so a dropped object fails the read, saying why, unless git finds its file in the work tree |
| Recording each path an uncommitted diff passed over | A path is the agent's text of any length and number. A count says the patch is not all the tree holds, and the workspace's reading at its last look names each untracked path |
| Recording the diff through `repo.record`, which records a test | An op takes one kind of `Args` and records one event, as `repo.report` records a look and `repo.record` a test, so a diff's record is an op of its own, `repo.keep`. Its name is the verb the plan and these docs give a read patch, kept beside its commit; an op may not be past tense, and `repo.diff` is the person's command |
| Keep a whole patch of any size | A body past 64 KiB is held outside the journal's row, in `blobs/`, which no op reads, so `blob.get` would give no text and a citation's lines would go unchecked |
| Cut at 64 KiB exactly | It can split a character, which leaves a text patch no text, and a line, which a citation names whole |
| Show untracked files through a scratch index, with `git add -N` | `git add -N` writes the empty blob into the workspace's object store, and the scratch index needs a place an isolated agent can write, from which the runtime would then remove it |
| Leave untracked files out | A new file an agent has not added is often most of its uncommitted work, and a diff without it would mislead |
| Read on past the bound to count a cut patch's length | A patch of gigabytes would cost the runtime the time to read it all. What a commit added and removed is on its `repo.committed`, and a workspace's paths on its `workspace.changed` |
| Read a patch a page at a time through `blob.get`, as an agent reads a body | A line longer than one result holds, 12 KiB, as a minified file's can be, comes back with no text, so it and every line after it could not be read, and how a page's first lines are toned turns on the pages before it, which a page read alone does not know. A kept patch is at most 64 KiB, so a person's client reads it whole |
| A query that gives a diff's record by its ref, for a client given a kept patch's ref alone | A concept more, for one use: the record is past its effect's request, so `repo.diff` giving the effect beside the ref lets a client follow the journal to it, whichever it was given |
| A client that says where a commit's patch was read from the workspace its look found it in | Once that workspace has gone the runtime reads it in yours, and only the runtime knows which it did, so its record says |
| A review, a noun with its own ops, states and verdicts | Nothing in milestone 4 needs a review to be more than the messages that cite what they are about, and the default pending the owner's ruling has none |
| A comment citing both the commit and the lines | A citation of lines names their record, whose gist names the commit, and the plan asks for the commit or the lines. One citation says what the comment is about |
| A comment to whoever the person names | The composer already writes to anyone. A comment on a change goes to its maker, whom the record names, so it needs no address |

## Consequences

- A person or a program reads what changed from the record, and a message cites the lines it is about.
- A diff costs only when someone asks for one, and a look and a handover cost what they did.
- In this repository's own history, about one commit in five has a patch past 64 KiB, which is cut. Its record says so, and the
  rest is in git, at the commit's SHA.
- An uncommitted diff is a moment's reading. A workspace whose agent is in a turn changes as it is read, and a file removed
  between the list of untracked files and its reading fails the read, saying so, so the next ask reads again.
- A filter a repository's config names runs for an uncommitted diff, as it does at every look.
- A workspace's own attributes decide what git takes for binary, so an agent can have a text change read as binary, and a reviewer
  reads that line as git's, not as proof of what the file holds.
- A patch of a file that is not UTF-8 is kept and read whole, but cannot be read as text or cited by its lines.
- The runtime's git reaches no remote at a look or a stop either, so a partial clone's dropped object fails them, saying why,
  where it would have been fetched.
- An agent cannot read a patch through the runtime. A message that cites lines of one hands it the message, and not the patch.
- What a diff costs on a repository past 100,000 files or on Lustre is unmeasured. It is paid only on request, and twice for a
  read a crash cut off.
- A person reads what changed, and comments on it, from either client in the same words, and a comment is a message, so its
  maker hears it as it hears any, and provenance follows it to the lines it cites.
- Asking for a diff is an act, so a view link and a session's history read none, not even a commit's patch kept, and say why.
- A comment on a change no agent's workspace made has nobody to take it, and a person writes about it in the composer instead.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 read on request | `repo.diff`, the `diff` effect and its recovery, `repo.keep` and `repo.diffed`, a commit's patch kept once and an uncommitted diff saying when it was read | `tests/unit/primitives/test_repo.py`, `tests/unit/runtime/test_diffs.py`, and `test_a_diff_left_uncertain_by_a_crash_is_read_again` in `tests/unit/runtime/test_recovery.py` | |
| M2 reviewed in both clients | `/review` and the page's Review changes draw a patch a page at a time through one shared wording, and a comment is a person's message that cites the commit or lines of its patch | `tests/unit/tui/test_review.py`: `test_a_commit_s_patch_is_asked_for_once_and_drawn_a_page_at_a_time_through_safetext`, `test_a_cut_patch_says_where_it_was_cut`, `test_a_binary_file_is_named_and_never_drawn`, `test_an_uncommitted_diff_says_when_it_was_read`, `test_a_comment_on_chosen_lines_is_a_message_to_the_commit_s_maker_citing_them`, `test_a_snapshot_or_isolated_workspace_s_diff_says_where_it_was_read`; `test_the_review_draws_a_patch` in `tests/unit/tui/test_snapshots.py`; `tests/e2e/test_review.py`: `test_review_changes_lists_each_commit_with_its_test_and_patch`, `test_a_commit_is_tested_from_the_page_after_one_question`, `test_a_hostile_patch_stays_text_under_the_page_s_policy`, `test_a_comment_from_the_page_cites_the_lines_it_is_on`; and the `changes` and `diff` panes in `tests/unit/web/test_server.py` | `refactor: Word what changed once for the terminal and the page`; `feat: Draw a commit's patch and a workspace's diff in the review, a page at a time`; `feat: Comment on a diff's lines as a message that cites them`; `feat: List what changed in the page, with each commit's test and patch` |

## Open questions

1. May an agent ask for a diff? M1 builds the default, pending the owner's ruling: no, as a diff is a person's or a program's,
   as a test is, and an agent reads a commit through `repo.commit` or its own git. A yes would make `repo.diff` a tool and record
   an agent's read of a patch as its exposure, and would remove nothing M1 builds. Needed before an agent may ask.
2. What does reviewing mean in milestone 4? The default, pending the owner's ruling, is that a person asks for and reads diffs in
   both clients and comments as a message that cites the commit or lines of its patch, with no noun for a review. M2 builds the
   default. A noun for a review would sit beside the messages that cite a change, and would remove nothing M2 builds.

## Evidence

- The bound is the most the journal holds in an event's own body, 64 KiB, as for a test's output
  ([RFC 0056](0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md)), and a measurement says how often it
  cuts. Each of the 442 commits of this repository at `04e34f1`, as git shows its patch against its first parent:

  ```console
  $ git rev-list 04e34f1 | while read sha; do
      git diff-tree -p --root --diff-merges=first-parent --no-commit-id -M --no-ext-diff --no-textconv --no-color "$sha" | wc -c
    done | sort -n
  ```

  361 of them, 81.7%, fit in 64 KiB. Half fit in 16 KiB, 91% in 128 KiB and 97% in 256 KiB; the 90th percentile is 111 KiB and
  the largest 1.4 MiB. Each took a median 21 ms to read and 157 ms at most, on a Lustre file system from a shared host with 192
  threads of Xeon Platinum 8468. These commits are larger than most an agent makes in one turn, as each holds a whole change
  with its tests and docs, so the share cut in a session is likely smaller (UNVERIFIED). M1 names the first parent the commit's
  own object holds, `git diff-tree -p -M <parent> <sha>` with the empty tree for a root, which printed the same bytes as the
  command above for all 442, the root among them, and for a merge made to check it.
- The tests named in the rollout plan's M1.
