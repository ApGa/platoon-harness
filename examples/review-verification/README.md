# A review and verification team

**Goal:** run a team in which an author commits a change, a reviewer reads it, and a verifier that cannot write checks it
with your test of it as evidence, and read back what the verdict rests on, with no keys first.

A Codex author in a worktree of its own, a Claude Code reviewer, and a Codex verifier in Codex's read-only sandbox: the
pipeline [the topologies guide](../../docs/how-to/topologies.md#pipeline) writes out, with each role's instructions saying
its part. The author commits the job on its branch and hands the commit to the reviewer through the queue `to-reviewer`.
The reviewer reads it with `git show` and through `repo.commit`, which gives the ref its review cites, and hands it on
with its review through the queue `to-verifier`. No agent can have the runtime run a commit's code, as
[RFC 0056](../../docs/rfcs/0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md) decided, so the
verifier asks you to test the commit and waits for your answer. It finishes with its verdict, citing the commit, its task
and your answer, which cites the record of your test.

**Prerequisites:**

- a checkout of this repository with its packages installed, as [the README](../../README.md#install) says, and its
  environment active, as [your first session](../../docs/getting-started/first-session.md#5-set-up-your-own-team) has
  it;
- a git repository with a commit, from which you start the session: the author's branch is made there, so a scratch one
  does;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the author
  commits as you;
- `python3` on your PATH, which the team's test runs;
- for a run on real models, `claude` and `codex` on your PATH and signed in as you usually are. The run with no keys
  needs neither.

The example has three files:

| File | What it is |
|---|---|
| [`team.toml`](team.toml) | The team: the `pipeline` preset for the three roles, with the queues `to-reviewer` and `to-verifier` it makes, each role's instructions, the team's `test`, Python's `unittest` run at a commit, an edge that lets the verifier ask you, and a budget of 20 turns and 30 minutes, so a runaway stops itself. The session closes when the verifier finishes |
| [`job.md`](job.md) | What you ask of the author: a function and its test, committed |
| [`stand_ins.py`](stand_ins.py) | Scripted stand-ins for the three harnesses, for the run with no keys |

## 1. Check it

From your repository, with the checkout's environment active:

```console
$ source path/to/platoon-harness/.venv/bin/activate
$ platoon-harness team check path/to/platoon-harness/examples/review-verification/team.toml --plan-login --trust
$ platoon-harness team show path/to/platoon-harness/examples/review-verification/team.toml --trust
```

`team check` says `no problems`, before any cost. `--trust` says you trust the team file's `test`, a command the runtime
runs as you, unconfined, at a commit you ask it to test: without it, each command that reads the file refuses it, with
exit 78. `team show` says in sentences what the team allows:

```text
author (codex, own worktree) may message no one. reviewer (claude) may message no one. verifier (codex) may message you.
author adds to queue `to-reviewer`; reviewer claims from it. Each entry wakes its readers. reviewer adds to queue `to-verifier`; verifier claims from it. Each entry wakes its readers. Closes when verifier finishes.
```

Codex keeps `.git` read-only under its sandbox, so the author's commit waits on an approval, which nobody is there to
answer in a headless run, and the team file gives the author `approvals = "allow"`: it runs git as you, unasked. A
worktree is not a sandbox: what runs there can reach anything you can. The reviewer and the verifier only read, so they
deny their approvals: what of theirs would ask is refused, and nobody is asked. The verifier's `sandbox = "read-only"` is
Codex's own, under which its shell writes nothing. The reviewer works in your checkout, the session's `shared`
workspace, and Claude Code asks nothing of a command it takes for read-only, while a `permissions.allow` rule in your
own Claude Code settings answers before the runtime hears, so `deny` holds the reviewer only to what would ask.

## 2. Run it with no keys

Scripted stand-ins, in [stand_ins.py](stand_ins.py), do what the job and each role's instructions ask with git and no
model at all:

```console
$ PYTHONPATH=path/to/platoon-harness/examples/review-verification platoon-harness run \
    --team path/to/platoon-harness/examples/review-verification/team.toml \
    --prompt-file path/to/platoon-harness/examples/review-verification/job.md --to @author --trust --name review \
    --set 'roles.author.harness = "stand_ins:author"' \
    --set 'roles.reviewer.harness = "stand_ins:reviewer"' \
    --set 'roles.verifier.harness = "stand_ins:verifier"'
```

`PYTHONPATH` lets the runtime import the stand-ins, and each `--set` puts a role on one of them in place of its harness.
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
$ platoon-harness message send review --to @verifier --reply-to inbox/you@1 --gist passed --based-on TESTED
```

`session show` names the verifier's ask under needs you, as `needs you: mention inbox/you@1, Please test 4dde84429173
with ...`: its ref, `inbox/you@1` here, which your answer replies to, and the commit, SHA here. `repo test` has the runtime run the team's test at that
commit, as you, in a clean checkout of it, and record what it came to: the one step of the flow that no agent can take,
which [Test a commit](../../docs/how-to/workspaces.md#test-a-commit) describes. `view watch` gives the changes view. Once
the test has run, the commit's row says what it came to as `tests`, `passed` here, and the ref of its record as `tested`,
TESTED here, such as `repo/<name>@4`, `<name>` being your repository's folder. Your message answers the ask, says what
the test came to and cites its record, so the verdict, which cites your answer, rests on your test. The run then
settles, and ends with how the session ended and each agent's last words:

```text
settled, exit 0
  @author          finished  Committed slug.py and its test, and handed the commit to the reviewer.
  @reviewer        finished  It adds slug.py and its test, as the job asks, and changes nothing else.
  @verifier        finished  Reviewed, and tested by you: passed
```

`tests/integration/test_examples.py` runs the `platoon-harness` commands on this page as shown, in a repository of its
own, the run in one process and your steps beside it. A session's name is taken once, so a second run needs another
`--name`.

## 4. Read it back

```console
$ platoon-harness task list review --queue to-verifier
$ platoon-harness contributors review --ref task/to-verifier/1@3
```

`task list` prints the verifier's task with its verdict as its `result`, and `task/to-verifier/1@3` is the verdict's ref:
the task was added, claimed, then completed. `contributors` says whose work the record ties to the verdict, in the order
reached: the verifier's own; the author, whose commit the look recorded as made in its worktree; the reviewer, who handed
the commit on; you, whose answer the verdict cites; and the runtime, whose record of your test your answer cites. It is
reachability in the record and never credit: it weighs and ranks nobody, and a citation is its agent's claim.
[docs/how-to/provenance.md](../../docs/how-to/provenance.md) says how to read each answer.

## 5. What a run with no keys cannot show

The stand-ins show the flow: a commit, a review that cites it, your test of it and a verdict that cites your answer.
They run in the runtime's own process, so a run with no keys cannot show what each role's harness holds it to: that the
verifier, in Codex's read-only sandbox, cannot write, that the reviewer's denied approvals keep it from changing your
checkout, or that the author's commit escalates past Codex's sandbox once allowed. Nor can it show that real models
follow their instructions, or how often a reviewer asks for a commit before it is recorded. The stand-in verifier says
what you answered, and judges nothing. Only a run on the real harnesses shows those.

## 6. Run it on your harnesses

The same command with neither `PYTHONPATH` nor the three `--set` lines, and with `--plan-login` and a new `--name`, runs
the team on `claude` and `codex`. `--plan-login` says you mean to run several agents on plan logins at once, which a
headless run refuses otherwise, with exit 78. The run says the session's name on stderr at once, owns the session in the
foreground until it settles, and exits 0 once it has, after your answer, as in step 3. This team has not run on real
models yet: [docs/STATUS.md](../../docs/STATUS.md) says what has run live.
