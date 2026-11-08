# RFC 0070: A population gives each worker one outcome, which its program records

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`topology/presets.py`](../../packages/sdk/src/platoon_harness/topology/presets.py), [`team.py`](../../packages/sdk/src/platoon_harness/team.py), [architecture section 6](../architecture.md#library-tier), [section 8](../architecture.md#8-topology) and [section 13](../architecture.md#13-workspaces), [RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md), [RFC 0048](0048-a-setting-nothing-carries-out-is-refused.md), [RFC 0057](0057-an-agent-cites-a-commit-by-the-ref-the-journal-gives.md) and [RFC 0068](0068-a-program-is-a-script-that-owns-its-session.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository, and the owner's question on a readout, which is open |
| Implementation | `refactor!: Give git-swarm live and a board for its program's outcomes`, `feat: Run a population that gives each worker one outcome`, `feat: Build on a peer's nominated commit by its recorded SHA` and `feat: Warn when no budget bounds a population's spawns` |

## Summary

`platoon_harness.patterns.population(session, role, goal, attempts=...)` is git-swarm's program: a function that a script holding
`program:<name>` calls on the session it owns ([RFC 0068](0068-a-program-is-a-script-that-owns-its-session.md)). It starts workers
of `role` with `goal`, each in a worktree of its own, as many at once as the session's `max_live` allows, until `attempts` have
started, and gives each worker one outcome once it has ended and its stop has looked at what it left: `contribute`, commits of its
own and no nomination; `nominate`, one message on `#nominations` citing one recorded commit's ref and no commit; `abstain`,
neither; `invalid`, anything else; or `failed`, an end other than finishing. The program records each outcome as the worker's
entry on board `outcomes`, which refuses a second, citing the worker's end and what it came to, and a contribution's or a
nomination's entry gives its commit's recorded SHA. Every outcome counts against `attempts`, so a population whose every worker
abstains ends. A worker builds on a peer's commit by checking out that SHA on its own branch, which only a worktree reaches, so a
population in any other kind of workspace is refused, saying why. `git-swarm` takes `live`, which is its `max_live`, and makes
the board, and `team check` warns of a role only the program starts when no budget sets a limit. Nothing is read out as a
winner: choosing among the nominations is the person's.

## Motivation

`git-swarm` makes the channels of a population, a `nominations` topic and an `inflight` board, and leaves its session to its
program, but no program runs it: [RFC 0068](0068-a-program-is-a-script-that-owns-its-session.md) took the `program` key and the
arguments it carried, `live` and `episodes`, and asked where a population takes its `live` and its `attempts`. The rework
[STATUS](../STATUS.md) lists for milestone 4 names the rest: nominations that cite commits, a worker building on a peer's commit,
one outcome for each worker, every outcome counting against `attempts`, and a warning when no budget bounds the spawns.

GitSwarm, as its paper states it ([research section 3](../research/swarm-patterns.md#3-gitswarm)), ends each worker's episode in
one of a few typed exits, charges a budget of episodes by exit, leaves abstaining uncharged with no rule for a population whose
every worker abstains, and reads out a plurality of the nominations. The record already holds what an outcome rests on: an
agent's end, each commit with the workspace that made it ([RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md)), and a
message's citations, which name a recorded commit by the ref `repo.commit` gives
([RFC 0057](0057-an-agent-cites-a-commit-by-the-ref-the-journal-gives.md)). What is missing is the loop that starts workers, and
one place that says, once, what each came to.

## Proposal

### 1. `git-swarm` takes `live`

```python
def git_swarm(role: str, *, live: int) -> Topology: ...
```

`live` is the topology's `max_live`, a bound on the live graph that the kernel holds against every spawner. The population keeps
no count of its own beside it: it starts a worker while fewer agents are live than `max_live`, and all of them at once on a team
with none. The preset keeps `role`, the `nominations` topic, the `inflight` board and `until = "program"`, and adds board
`outcomes`, which the program writes and everyone reads. `live` is required, so a `[topology.git-swarm]` without it is refused at
load, naming it.

### 2. The population

```python
Outcome = Literal["contribute", "nominate", "abstain", "invalid", "failed"]

async def population(session: Session, role: str, goal: str, *, attempts: int) -> dict[str, Outcome]: ...
```

It reads the session's team from its manifest and refuses, before it starts anyone, a team it cannot run: no such role, a role
that starts with the session, as such agents have no goal, a workspace other than `worktree`, or no topic `nominations` or board
`outcomes`, each problem at once as `ConfigError`, and `attempts` below 1 as `invalid`. Then it reads the record from its start and
acts on what it reads, and reads again what it wrote, until each worker it started has its outcome and it can start no more. It
returns each worker's outcome by its name, in the order they started.

- **Starting.** A worker is `<role>-1`, `<role>-2` and on, the first name no agent has taken, spawned with `goal` and with a body
  that tells it how its outcome is read and how to build on a peer's commit. A spawn refused `not_permitted`, as `max_live` or
  `max_children` refuses one, is tried again once an agent has ended. Any other refusal, such as `over_budget` or a session that is
  closing, ends the starting, and the population raises it once each worker it started has its outcome.
- **Retiring.** A worker whose turn ended with nothing more to come for it, as a failed turn leaves a worker that does not stay,
  is idle for good, as nothing in a population wakes it, so the population retires it, and its outcome is `failed`. One that is
  waiting on something is left to it. A retirement refused `conflict` says the worker is at work again or has ended, and any
  other refusal would leave it idle with no outcome to come, so the population raises it.
- **Choosing.** The population chooses nothing among the nominations: that is the person's (Open questions).

### 3. One outcome for each worker

A worker's outcome is decided once it has ended and the stop that followed its end has settled, as that stop's look records the
commits its worktree made. Its outcome is:

| Outcome | When |
|---|---|
| `failed` | It ended other than finishing, or its last look did not finish, so what it left is unknown |
| `invalid` | It finished, and committed and nominated, nominated more than once, or nominated citing no recorded commit, or several |
| `nominate` | It finished having sent one message to `#nominations` whose `based_on` cites one recorded commit, and committed nothing |
| `contribute` | It finished having made recorded commits in its worktree, and nominated nothing |
| `abstain` | It finished having done neither |

A commit is a worker's when the look attributes it to the worker's workspace, as `made_in` records
([architecture section 13](../architecture.md#13-workspaces)). Each check is of structure, never of worth: a nomination is valid
when it cites one recorded commit, whatever that commit holds.

The program records the outcome as an entry of board `outcomes` named for the worker, `<outcome>: <what>`, with `outcome` in its
`fields`, and with `sha` for a contribution, its last commit's, and for a nomination, the nominated commit's. It cites the
worker's end and what it came to: its last commit, its nomination and the commit that cites, or what made it invalid. A board
refuses a second post of a name, and the population never revises one, so no worker gets a second outcome. The program alone
writes the board, so no worker can claim one.

### 4. Every outcome counts against `attempts`

`attempts` counts the workers the population starts, whatever each comes to, so abstaining and failing are charged too, and a
population whose every worker abstains ends once it has started `attempts`. GitSwarm leaves abstaining uncharged, which needs a
cap of its own to end; charging it needs none. A spawn the kernel refuses starts no worker, so it is no attempt.

### 5. Building on a peer's commit

A worker builds on a peer's commit by checking out its recorded SHA on its own branch in its worktree, `git reset --hard <sha>`,
which its body tells it, reading the SHA from the peer's entry on `outcomes`. Every worktree shares the repository's objects, so
every commit any worker made is there by its SHA. The worker moves its own branch, in its own git; the runtime moves none
([RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md)). The look after its turn records its new commit with the peer's
as its parent, which the peer's commit already recorded is not recorded again.

No other kind of workspace reaches a peer's commit, so the population refuses each, saying why: in `shared`, every worker works
in one checkout, with no branch or commits of its own; and a `snapshot` or an `isolated` workspace is a repository of its own,
which holds no peer's commits.

### 6. Run again after a crash

A population keeps nothing: run again on the session after a crash, as RFC 0068 runs any program again, it reads the record from
its start. A worker's name is taken once it is spawned, and a board refuses a second entry of a name, so a second run starts no
worker and records no outcome that the record holds, and goes on from there. Its spawns and posts carry no key of the program's:
a refusal is answered again under its key, so a spawn that `max_live` refused would be refused under that key for ever.

### 7. `team check` warns when no budget bounds the spawns

`team check` knows no program, so it cannot see `attempts`. Under `until = "program"`, it warns of each role that nothing in the
team starts, none at the session's start and no role by `may_spawn`, when neither that role's budget nor the session's sets a
limit, as then nothing in the team stops the program starting more of its agents, or what they spend. Any limit does once it is
reached, as a spawn past it is refused and the session stops, though only `agents` counts how many start: under a `wall` limit
alone, the program starts as many as it likes until then. It is a warning, as the program may bound them itself.

What changes for users:

- **The team file:** `[topology.git-swarm]` needs `live`, and makes board `outcomes`.
- **Python:** `git_swarm(role, *, live)`, and `platoon_harness.patterns`, with `population` and `Outcome`.
- **The command line:** `team check` warns of a role only the program starts with no budget to bound it. `run` still refuses a
  `git-swarm` team, as RFC 0068 says.
- **The journal:** nothing new. An outcome is a board entry, a worker a spawn, and a retirement `agent.retire`'s.

## The hard parts

- **A slot frees at an end, an outcome after the stop.** The next worker can start before the outcome of the one whose end freed
  its slot is recorded, as that worker's stop looks at its worktree after its end. A worker reads `outcomes` as it works, and
  waits for an entry it needs.
- **A commit nobody made.** A commit that two worktrees' reflogs claim is made in neither (section 13), so it counts for no
  worker, and a worker whose only commit it was abstained, as far as the record says.
- **A look that never finished.** A worker whose stop failed or was cancelled may have committed work its look never recorded, so
  its outcome is `failed`, saying so, never `abstain`.
- **What a worker is told names our ops as the kernel does.** The body beside its goal says `repo.commit` and `#nominations`, and
  a spawn's body reaches its harness as it was written, while its preamble names each tool as that harness shows it
  ([RFC 0029](0029-a-harness-names-our-tools-as-it-shows-them.md)), such as `mcp__ph__repo_commit`. Whether a real model finds
  the tool by the kernel's name is unknown, as no real model has run a population: pi has run one only against FakeModel.

## Alternatives

| Alternative | Why not |
|---|---|
| A readout of a winner: the plurality of valid nominations, a tie going to the least full SHA, and the repository's root when no nomination is valid, as GitSwarm's paper has it | The owner's question, open (Open questions). The default reads out nothing: each worker's outcome is the result, and choosing among the nominations is the person's. A readout would be one more function over the board, and would change nothing built here |
| Abstaining uncharged, with a cap of its own on uncharged attempts | A second count, with a rule of its own, for what charging every outcome already ends |
| `attempts` as an argument of `git-swarm` | A preset is a fragment of a topology, which holds no count of spawns, and a setting nothing carries out is refused ([RFC 0048](0048-a-setting-nothing-carries-out-is-refused.md)). How many workers to start is control flow, which is the program's |
| `attempts` as the role's budget `agents` | `agents` is charged when an agent starts, so a worker whose launch failed is never charged, and a population whose launches fail would start workers without end |
| `live` as an argument of the population | A second bound on the live graph beside `max_live`, which the kernel holds against every spawner already |
| An event of its own for an outcome | A new event type and an op, for what an entry on a board that only the program writes already says once |
| An outcome as an annotation ([RFC 0052](0052-a-reward-has-five-statuses-and-eligibility-is-read-from-the-record.md)) | An annotation is a producer's estimate, kept beside the journal; an outcome is what the record holds, said by the program that owns the session |
| A worker saying its own outcome | A claim the program would check against the record anyway, and one a worker could make twice |
| The runtime making a worker's worktree at a peer's commit | A spawn argument and a change to how a workspace is made, for what the worker's own git does in one command |
| Building on a peer's commit in a snapshot, by fetching it | A snapshot's repository has no remote and holds no peer's objects, and the isolated workspace's code never leaves its isolation ([RFC 0056](0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md)) |
| Keyed spawns and posts | A refusal is answered again under its key, so a spawn `max_live` refused once would stay refused. Names and the board already refuse a second |

## Consequences

- A script runs git-swarm in a few lines: start the session as a program, call `population`, close the session.
- Each worker's outcome is in the record, once, citing what it rests on, and a person reads it from board `outcomes`, as an agent
  does.
- A population ends: every worker it starts counts against `attempts`, whatever it came to.
- A population runs only in worktrees, and is refused in any other kind of workspace before it starts anyone.
- `git_swarm("worker")` with no `live`, and a `[topology.git-swarm]` with no `live`, are refused.
- A team under `until = "program"` with a role only the program starts and no budget is warned of, so the topologies guide's
  reviewers' team has one.
- On a plan login, a population's role counts as several agents before any cost, as `live` above 1 runs several at once, so its
  start is refused unless the script says `plan_login=True`. The example's workers reach their model through an auth profile,
  which is on no plan login.
- No winner is read out. Which nomination a population favours, if any, is the person's to read from the board.
- How often workers abstain, nominate or contribute on real models is unknown: no real model has run a population, and pi has
  run one only against FakeModel, in the GitSwarm example's test.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 `git-swarm`'s `live` and board | `live` as `max_live`, board `outcomes` | `tests/unit/topology/test_presets.py::test_git_swarm_coordinates_through_artifacts_alone` | |
| M2 the population | `population`, its outcomes, retiring an idle worker, a second run | `tests/unit/patterns/test_population.py`: `test_each_worker_gets_one_outcome_and_never_a_second`, `test_a_nomination_that_cites_no_recorded_commit_is_invalid`, `test_every_outcome_abstaining_included_counts_against_attempts_so_a_population_that_all_abstain_ends` and `test_a_population_run_again_after_a_crash_gives_no_worker_a_second_outcome` | |
| M3 building on a peer's commit | `sha` on an entry, the body's words, worktrees alone | `tests/unit/patterns/test_population.py`: `test_a_worker_builds_on_a_peer_s_nominated_commit_by_its_recorded_sha` and `test_a_population_outside_worktrees_is_refused_saying_why` | |
| M4 the warning | `team check` on a role only the program starts | `tests/unit/topology/test_check.py::test_team_check_warns_when_no_budget_bounds_a_population_s_spawns` | |

## Open questions

1. Should a population read out a winner: a plurality of the valid nominations, ties going to the least full SHA, and the
   repository's root when there is none? This builds the default, pending the owner's ruling: no readout, each worker's outcome
   is the result, and choosing among the nominations is the person's. A readout would read the board this builds, so a ruling
   for one adds a function and removes nothing. The GitSwarm example ships on the default, pending the ruling, so a readout
   would add a line to what it prints.

## Evidence

- [Research section 3](../research/swarm-patterns.md#3-gitswarm): GitSwarm's exits, its budget charged by exit, its uncharged
  abstaining with no rule for a population that only abstains, and its readout, all from its paper, as no code of its was run.
- [RFC 0057](0057-an-agent-cites-a-commit-by-the-ref-the-journal-gives.md)'s tests, in `tests/unit/primitives/test_repo.py`, for
  the ref a nomination cites, and `tests/unit/runtime/test_looks.py` for `made_in`.
- `tests/unit/kernel/test_commands.py::test_a_retry_of_a_refusal_gets_the_same_refusal`, for why spawns and posts carry no key.
- The tests named in the rollout plan.
