# A review and verification team

**Goal:** run a team on a model you name in which an author fixes a bug of the sample project and commits it, a
reviewer reads the commit, and a verifier that can run nothing checks it with your test of it as evidence, and read back
what the verdict rests on.

An OpenHands author in a worktree of its own, a pi reviewer in a snapshot of its own, and a pi verifier whose every
command and edit is refused, in your copy of [the sample project](../sample-project/README.md): the pipeline
[the topologies guide](../../docs/how-to/topologies.md#pipeline) writes out, with each role's instructions saying its
part. The author fixes issue 2 of its `ISSUES.md` with a test, commits both on its branch, and hands the commit to the
reviewer through the queue `to-reviewer`. The reviewer reads it with `git show` and through `repo.commit`, which gives
the ref its review cites, and hands it on with its review through the queue `to-verifier`. No agent can have the runtime
run a commit's code, as [RFC 0056](../../docs/rfcs/0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md)
decided, so the verifier asks you to test the commit and waits for your answer. Its instructions have it finish with its
verdict, citing the commit, its task and your answer, which cites the record of your test. A citation is its model's to
make, and step 4 shows which it made.

**Prerequisites:**

- a checkout of this repository with its packages installed by `uv sync`, as [the README](../../README.md#install) says,
  which brings the SDK's `openhands` extra, and its environment active, as
  [your first session](../../docs/getting-started/first-session.md#1-run-a-team-on-your-model) has it;
- `pi` on your PATH, which needs no login here;
- a model at an endpoint that speaks OpenAI's Chat Completions, and a key for it, in `OPENAI_BASE_URL` and
  `OPENAI_API_KEY`, as [the mixed team](../mixed-team/README.md#1-check-it) names them;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the author
  commits as you, and `python3` 3.9 or later on your PATH, which the author and the team's test run.

The example has two files:

| File | What it is |
|---|---|
| [`team.toml`](team.toml) | The team: the `pipeline` preset for the three roles, with the queues `to-reviewer` and `to-verifier` it makes, each role's instructions, the team's `test`, Python's `unittest` run at a commit, an edge that lets the verifier ask you, an auth profile, `provider`, that hands each harness your endpoint and key, and a budget of 24 turns and 40 minutes, so a runaway stops itself. The session closes when the verifier finishes |
| [`job.md`](job.md) | What you ask of the author: the fix of issue 2 and its test, committed |

## 1. Check it

In a new, empty folder, make a copy of the sample project, as a repository of its own, and work there:

```console
$ cp -r path/to/platoon-harness/examples/sample-project tally
$ cd tally
$ git init -q && git add -A && git commit -qm "Start from the sample project"
```

Check the team with a `--set` line for each role that names your model, MODEL as your endpoint names it:

```console
$ platoon-harness team check path/to/platoon-harness/examples/review-verification/team.toml --trust \
    --set 'roles.author.model = "MODEL"' --set 'roles.reviewer.model = "MODEL"' --set 'roles.verifier.model = "MODEL"'
$ platoon-harness team show path/to/platoon-harness/examples/review-verification/team.toml --trust
```

`--trust` says you trust the team file's auth profile, which hands your key to each harness, and its `test`, a command
the runtime runs as you, unconfined, at a commit you ask it to test: without it, each command that reads the file
refuses it, with exit 78. `team check` says `no problems`, before any cost, and `team show` says in sentences what the
team allows:

```text
author (openhands, own worktree) may message no one. reviewer (pi, own snapshot) may message no one. verifier (pi) may message you.
author adds to queue `to-reviewer`; reviewer claims from it. Each entry wakes its readers. reviewer adds to queue `to-verifier`; verifier claims from it. Each entry wakes its readers. Closes when verifier finishes.
```

Nobody is there to answer an approval in a headless run. The author edits, runs the tests and commits, so its approvals
allow: it runs commands as you, unasked, and a worktree is not a sandbox, as what runs there can reach anything you can.
The reviewer reads the commit with git, so its approvals allow too, in a snapshot of its own: a repository of its own,
which reads your objects, the author's commit among them, so git there writes only its own repository, while what runs
there can still reach anything you can. The verifier only reads, so its approvals deny: pi's `read`, `grep`, `find` and
`ls` ask nothing, and every command or edit it tries is refused, nobody asked.

## 2. Run it

```console
$ platoon-harness run --team path/to/platoon-harness/examples/review-verification/team.toml \
    --prompt-file path/to/platoon-harness/examples/review-verification/job.md --to @author --trust --name review \
    --set 'roles.author.model = "MODEL"' --set 'roles.reviewer.model = "MODEL"' --set 'roles.verifier.model = "MODEL"'
```

`--to @author` gives the job to the author alone: the reviewer and the verifier start idle, and a task on their queue
wakes each. The run prints a line per event as the session journals it. The author commits on the branch
`platoon-harness/review/author`, in a worktree in the session's folder, made at your HEAD: nothing of it is in your
checkout. A commit is recorded at the look after the turn that made it, so a reviewer that asks `repo.commit` for it
sooner is refused `not_found`, saying it is not recorded yet, and asks again a moment later, as its instructions say;
the run may print that refusal. The verifier then asks you to test the commit and waits up to 20 minutes for your
answer, and the run waits with it.

## 3. Test it, and answer the verifier

From another shell, in the same repository:

```console
$ platoon-harness session show review
$ platoon-harness repo test review --commit SHA
$ platoon-harness view watch review --name changes
$ platoon-harness message send review --to @verifier --reply-to ASK --gist passed --based-on TESTED
```

`session show` names the verifier's ask under needs you, with its ref, ASK here, which your answer replies to, and its
words, which are the model's own and name the commit, SHA here, as in `needs you: mention inbox/you@1, Please test
4dde84429173 ...` from a run on FakeModel. `repo test` has the runtime run the team's test at that commit, as you, in a
clean checkout of it, and record what it came to: the one step of the flow that no agent can take, which [Test a
commit](../../docs/how-to/workspaces.md#test-a-commit) describes. It answers at once, with the `effect` it started, and
the test runs after. `view watch` gives the changes view, in which the commit's row says what the test came to as
`tests`, null until it has run and `passed` here, and the ref of its record as `tested`, TESTED here, such as
`repo/<name>@4`, `<name>` being your repository's folder: while `tests` is null, run `view watch` again. Your message
answers the ask, says what the test came to and cites its record, so the verdict, which cites your answer, rests on your
test. The run then settles, and ends with `settled, exit 0` and a line for each agent, each finished with its last
words, which are the model's own: the verifier's is its verdict.

A real model chooses its own steps, so a run can go otherwise: the reviewer may ask `repo.commit` again more often, and
the verifier may word its ask differently, so read the SHA from what it says. The team's budget of 24 turns and 40
minutes is what stops a runaway: no budget counts model calls, and one turn can make many.
`tests/live/test_examples.py` fails a live run of this example that took more than 70 model calls, counted once the run
has ended, or 40 minutes, your answer included, about one and a half times what live runs on DeepSeek V4.1 Flash took on 2026-11-08, 42 model calls:
[docs/STATUS.md](../../docs/STATUS.md) says what has run live. `tests/integration/test_examples.py` runs the
`platoon-harness` commands on this page as shown, with `fake-model` for MODEL, and the run with one more `--set` line,
which hands pi its switch for no network, the run in one process and your steps beside it, on the real `pi` and
OpenHands against FakeModel, a loopback model that replies from a script, so the harnesses, the tools, git, the
approvals and the team file are real and only the model is scripted. A session's name is taken once, so a second run
needs another `--name`.

## 4. Read it back

```console
$ platoon-harness task list review --queue to-verifier
$ platoon-harness contributors review --ref VERDICT
```

`task list` prints the verifier's task with its verdict as its `result`, and the verdict's ref as its `result_ref`,
VERDICT here, such as `task/to-verifier/1@3` when the task was added, claimed, then completed. `contributors` says whose
work the record ties to the verdict, in the order reached, when each agent cites as its instructions ask: the verifier's
own; the author, whose commit the look recorded as made in its worktree; the reviewer, who handed the commit on; you,
whose answer the verdict cites; and the runtime, whose record of your test your answer cites. It is reachability in the
record and never credit: it weighs and ranks nobody, and a citation is its agent's claim.
[docs/how-to/provenance.md](../../docs/how-to/provenance.md) says how to read each answer.