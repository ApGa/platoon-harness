# Team file reference

<!-- Made from the schema by `uv run python -m platoon_harness_cli.team_file > docs/reference/team-file.md`.
Do not edit: change the schema, and make it again. A test holds it to the schema. -->

A team file is TOML, and its tables are the models below, from `Team` at the top level down. `--team` names one on the
command line, `load_team` in Python, and the project file, `platoon-harness.toml`, has the same form.
[Architecture section 17](../architecture.md#17-extensions-and-configuration) says how the layers combine: the user's
config, the project file, a team file, `PLATOON_HARNESS_CONFIG` and each `--set` line.
[Topologies](../how-to/topologies.md) has a worked team for each preset, and [Workspaces](../how-to/workspaces.md) what
each `workspace` promises.

Each section is one model: where its tables go, what its docstring says, and a row for each key, with its type and its
default, `required` where it has none. A table refuses a key its model does not declare.

## Contents

- [`Team`](#team)
- [`Role`](#role)
- [`Command`](#command)
- [`Budget`](#budget)
- [`AuthProfile`](#authprofile)
- [`Topology`](#topology)
- [`Group`](#group)
- [`Topic`](#topic)
- [`Queue`](#queue)
- [`Board`](#board)
- [`Limits`](#limits)
- [`Grant`](#grant)
- [`Test`](#test)
- [Presets](#presets)

## Team

At the top level.

Roles plus a topology. It says what may happen, never what happens next. `preamble` is the template of what every
agent is told before its role's words, unless its role gives its own. `test` is what a runtime test of a commit
runs, if the team names one.

| Key | Type | Default |
|---|---|---|
| `extensions` | list of strings | `[]` |
| `preamble` | string | the SDK's `PREAMBLE`, which `platoon-harness team told` shows filled in for each role |
| `roles` | [Role](#role) tables, by name, at least 1 | required |
| `auth` | [AuthProfile](#authprofile) tables, by name | `{}` |
| `budget` | [Budget](#budget) | `{}` |
| `topology` | [Topology](#topology) | `{}` |
| `test` | [Test](#test) | none |

## Role

At `[roles.<name>]`.

A template for agents. `tools` lists op globs, and only ever narrows what the topology grants.

`count` is how many start with the session: left out, one, or none if another role spawns this one. `delivery` is
how a message reaches this role's inboxes, and `inbox_depth` how many entries one holds before refusing more.
`effort` goes to the harness as it stands, and a harness that cannot honor it fails the spawn. `stays` says whether
an agent is told to stay after its task for the next message, rather than to finish, which one that does not stay
does with a turn that leaves nothing more to come for it: left out, one the session started stays and one spawned
does not, and a spawn may say otherwise either way. `on_parent_exit` says what becomes
of an agent whose parent ends: `cancel-subtree` ends it too, `cancelled` if a turn of its was cut off and `retired`
otherwise, and `adopt` gives it to the session. `allow_native_children` lets its harness start agents of its own,
beside ours, which a role on a harness whose driver cannot turn them off, as on ACP, must say. `preamble` is the
template of what its agents are told before `instructions`, its own words, in place of the team's.

| Key | Type | Default |
|---|---|---|
| `harness` | string or [Command](#command) | required |
| `model` | string | none |
| `effort` | string | none |
| `preamble` | string | none |
| `instructions` | string | none |
| `auth` | string | none |
| `workspace` | `"shared"`, `"worktree"`, `"snapshot"` or `"isolated"` | `"shared"` |
| `sandbox` | string | none |
| `allow_native_children` | boolean | `false` |
| `tools` | list of strings | `["*"]` |
| `delivery` | `"pull"`, `"next-turn"`, `"wake"` or `"steer"` | `"wake"` |
| `inbox_depth` | integer, above 0 | `1024` |
| `may_spawn` | list of strings | `[]` |
| `count` | integer, at least 0 | none |
| `stays` | boolean | none |
| `on_parent_exit` | `"cancel-subtree"` or `"adopt"` | `"cancel-subtree"` |
| `approvals` | `"ask"`, `"deny"` or `"allow"` | `"ask"` |
| `budget` | [Budget](#budget) | `{}` |

## Command

At `[roles.<name>.harness]`.

A harness given as a command line: a `oneshot` CLI run by the `exec` driver, or a `wire` driver program.

| Key | Type | Default |
|---|---|---|
| `command` | list of strings, at least 1 | required |
| `mode` | `"oneshot"` or `"wire"` | `"oneshot"` |

## Budget

At `[roles.<name>.budget]`, `[budget]`.

Limits on a session or a role. `estimate` is what one turn is reserved in `tokens` or `usd` before it is
measured, and charged on top of what was measured when nobody measured it whole, so a limit in either needs one.

| Key | Type | Default |
|---|---|---|
| `tokens` | integer, above 0 | none |
| `usd` | number, above 0 | none |
| `turns` | integer, above 0 | none |
| `agents` | integer, above 0 | none |
| `wall` | duration, such as `30m` | none |
| `estimate` | numbers, above 0, by `tokens` or `usd` | `{}` |

## AuthProfile

At `[auth.<name>]`.

Which environment variables a harness receives. Names only: a value never enters configuration.

| Key | Type | Default |
|---|---|---|
| `env` | list of strings matching `[A-Za-z_][A-Za-z0-9_]*` | required |

## Topology

At `[topology]`.

What may happen: a set of fragments merged by union. Presets make fragments; `a | b` mixes them.

| Key | Type | Default |
|---|---|---|
| `until` | `settled`, `program` or `role:<name>` | none |
| `edges` | lists of strings, by name | `{}` |
| `groups` | [Group](#group) tables, by name | `{}` |
| `channels` | [Topic](#topic), [Queue](#queue) or [Board](#board) tables, by name | `{}` |
| `limits` | [Limits](#limits) | `{}` |
| `grants` | list of [Grant](#grant) tables | `[]` |

## Group

At `[topology.groups.<name>]`.

A named membership rule: some roles, some principals, or roles in an order that `next` and `prev` walk.

| Key | Type | Default |
|---|---|---|
| `roles` | list of names | `[]` |
| `members` | list of `agent:<name>`, `human:<name>`, `program:<name>` or `judge:<name>` | `[]` |
| `order` | list of names | `[]` |

## Topic

At `[topology.channels.<name>]`, with `kind = "topic"`.

A log every reader follows by cursor.

| Key | Type | Default |
|---|---|---|
| `kind` | `"topic"` | required |
| `writers` | list of strings, at least 1 | required |
| `readers` | list of strings, at least 1 | required |
| `delivery` | `"pull"`, `"next-turn"`, `"wake"` or `"steer"` | `"next-turn"` |
| `history` | `"from-join"` or `"full"` | `"from-join"` |
| `coalesce` | duration, such as `30m` | none |

## Queue

At `[topology.channels.<name>]`, with `kind = "queue"`.

Tasks leased to one claimant at a time. Unless `pull`, `delivery` announces work; it never assigns it.

| Key | Type | Default |
|---|---|---|
| `kind` | `"queue"` | required |
| `writers` | list of strings, at least 1 | required |
| `readers` | list of strings, at least 1 | required |
| `delivery` | `"pull"`, `"next-turn"`, `"wake"` or `"steer"` | `"pull"` |
| `lease` | duration, such as `30m` | none |
| `lease_max` | duration, such as `30m` | none |
| `max_attempts` | integer, above 0 | `3` |
| `max_inflight` | integer, above 0 | `1` |

## Board

At `[topology.channels.<name>]`, with `kind = "board"`.

Named objects with immutable versions.

| Key | Type | Default |
|---|---|---|
| `kind` | `"board"` | required |
| `writers` | list of strings, at least 1 | required |
| `readers` | list of strings, at least 1 | required |
| `delivery` | `"pull"`, `"next-turn"`, `"wake"` or `"steer"` | `"pull"` |

## Limits

At `[topology.limits]`.

Bounds on the live graph, and on how far a chain of messages may run.

| Key | Type | Default |
|---|---|---|
| `max_depth` | integer, above 0 | none |
| `max_children` | integer, above 0 | none |
| `max_live` | integer, above 0 | none |
| `max_hops` | integer, above 0 | none |

## Grant

At `[[topology.grants]]`.

Who may run which ops on what. Absence means deny.

| Key | Type | Default |
|---|---|---|
| `who` | string | required |
| `ops` | string | required |
| `on` | string | `"*"` |

## Test

At `[test]`.

What the runtime runs at a recorded commit when a person or a program asks: `command`, in a clean detached
checkout of that commit, as you and unconfined, ended at `timeout`, which is then an error and not a failure.

| Key | Type | Default |
|---|---|---|
| `command` | list of strings, at least 1 | required |
| `timeout` | duration, such as `30m` | required |

## Presets

A preset is a table under `[topology]` named after it, whose keys are its arguments, and a list of such tables uses it
more than once. Each makes a topology fragment, merged with the rest of `[topology]` by union.

### manager-worker

At `[topology.manager-worker]`.

A manager fills a queue that workers claim from. Workers answer to their parent and share a board.

| Key | Type | Default |
|---|---|---|
| `manager` | string | required |
| `workers` | string or list of strings | required |
| `queue` | string | `"tasks"` |
| `board` | string | `"notes"` |
| `lease` | string | `"30m"` |
| `max_hops` | integer | `8` |

### tree

At `[topology.tree]`.

Agents delegate downward and report upward. It closes when its root finishes, unless `until` says otherwise.

| Key | Type | Default |
|---|---|---|
| `role` | string | required |
| `max_depth` | integer | required |
| `max_children` | integer | none |
| `until` | string | none |
| `max_hops` | integer | `8` |

### mesh

At `[topology.mesh]`.

Peers message each other directly and share their group's topic, which wakes no one.

| Key | Type | Default |
|---|---|---|
| `role` | string or list of strings | required |
| `board` | string | none |
| `group` | string | `"peers"` |
| `max_hops` | integer | `8` |

### star

At `[topology.star]`.

Every message goes through the hub, which may also announce on a topic. Spokes never reach each other.

| Key | Type | Default |
|---|---|---|
| `hub` | string | required |
| `spokes` | string or list of strings | required |
| `topic` | string | none |
| `max_hops` | integer | `8` |

### blackboard

At `[topology.blackboard]`.

Agents coordinate through shared artifacts alone, and may share a queue of open work.

| Key | Type | Default |
|---|---|---|
| `role` | string or list of strings | required |
| `board` | string | `"notes"` |
| `queue` | string | none |

### pipeline

At `[topology.pipeline]`.

Each stage feeds a queue for the next. `back` lets every later stage return work to the first.

| Key | Type | Default |
|---|---|---|
| `stages` | list of strings | required |
| `back` | boolean | `false` |
| `max_hops` | integer | none |

### ring

At `[topology.ring]`.

A pipeline whose last stage feeds the first, for at most `laps` times round.

| Key | Type | Default |
|---|---|---|
| `stages` | list of strings | required |
| `laps` | integer | required |

### git-swarm

At `[topology.git-swarm]`.

A population coordinating through a shared repository alone: no messages, only commits and nominations, with at
most `live` agents at once. Its program, a script, owns the session, writes each worker's outcome on `outcomes` and
closes it.

| Key | Type | Default |
|---|---|---|
| `role` | string | required |
| `live` | integer | required |
