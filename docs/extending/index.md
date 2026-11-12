# Extending platoon-harness

platoon-harness is extended from code of your own, with no change to platoon-harness: a driver that presents a harness,
an extension that adds ops, views, daemons, presets or an isolation, a program that owns a session, or a training system
that admits each agent and says what its work was worth. Installing a package activates nothing: a role names its
harness, and a team names its extensions. This page names every way in, how platoon-harness finds your code and the
rules your code keeps, and links the guide to each.

## Ways in

| You add | You write | It is found through | It is chosen by | Guide |
|---|---|---|---|---|
| A harness that takes a task and exits | Nothing but its command line | The `exec` driver | A role's `harness = { command = [...], mode = "oneshot" }` | [A one-shot CLI](drivers.md#a-one-shot-cli-exec) |
| A harness driven from any language | A program that speaks JSON-RPC on stdio | The `wire` driver | A role's `harness = { command = [...], mode = "wire" }` | [A program: the wire](drivers.md#a-program-the-wire) |
| A driver in Python | A class with the seven methods of `Driver` | The `platoon_harness.drivers` entry-point group, or `module:attr` | A role's `harness`, by the driver's name | [A Python package](drivers.md#a-python-package) |
| A driver of an agent that speaks ACP | A subclass of the SDK's experimental `AcpDriver` that names the agent's command | The `platoon_harness.drivers` entry-point group, or `module:attr` | A role's `harness`, by the driver's name | [ACP agents](drivers.md#acp-agents) |
| An extension | An `Extension`, of [the parts below](#an-extensions-parts) | The `platoon_harness.extensions` entry-point group, or `module:attr` | A team's `extensions = [...]` | [Write an extension](extensions.md) |
| A topology preset | A function that returns a `Topology` | An extension's `presets` | A team's `[topology.<name>]` table | [Write your own preset](../how-to/topologies.md#write-your-own-preset) |
| An isolation | An object with `refusal()` and `wrap(writable, readable, hidden)` | An extension's `isolation` | A team that names the extension, and a role's `workspace = "isolated"`, which is [experimental](../reference/python.md#platoon_harnessruntimeisolation) | [Where an isolated agent runs](../how-to/workspaces.md#where-an-isolated-agent-runs) |
| A program | A Python script that starts its session as `program:<name>` and drives it through the session's ops | Nothing: you run it | `until = "program"`, which leaves the session to the program | [Programs](#programs) |
| A training system | An `Authority` that admits each agent through a gateway of yours, and what trains | Nothing: your program passes it to `Session.start` | `authority=` and `trainable=True` | [The training contract](#the-training-contract) |
| An estimator | Code that reads the record and writes rewards or credit beside the journal through `Session.annotate` | Nothing: you run it | The producer and version each statement names | [Write credit](../how-to/provenance.md#write-credit) |

## An extension's parts

An extension is an `Extension` from `platoon_harness.kernel`: a name, and any of the other fields
([architecture §17](../architecture.md#17-extensions-and-configuration)).

| Field | What it holds | What it becomes |
|---|---|---|
| `name` | The extension's name, which is its ops' namespace | What a team names in `extensions`, and, once it is installed, the command line's group of its ops' commands |
| `ops` | Ops, each a plain function under `@op("<name>.<verb>")` that takes a `Txn` and its `Args` | An op `Session.submit` runs, a command of the command line, a form in the terminal's palette and the page's, and, with `tool=True`, a tool on MCP and a command of `ph` for an agent whose grants reach it |
| `views` | `View` classes, each a schema and the `@fold` methods that keep its tables from the journal | Tables an op reads through `txn.view`, which a rebuild from the journal makes again row for row |
| `daemons` | `Daemon`s, each a named task that reads views, does in the world what an op asked for, and reports through ops | A task the runtime runs beside the session, started again when it fails |
| `presets` | Functions that each return a `Topology` fragment | A team's `[topology.<name>]` table, named after the function with dashes for underscores, its keys the function's arguments |
| `isolation` | What confines an isolated agent: `refusal()`, why it cannot here, and `wrap(writable, readable, hidden)`, the argv a command runs under | The confinement of each isolated agent of a team that names the extension, as a team names at most one extension that gives one. An isolated agent is [experimental](../reference/python.md#platoon_harnessruntimeisolation) |

An op is usable through the SDK, MCP, `ph`, the command line and both clients' palettes with no core edit, as each
derives from the op table, and any client draws its events by their `gist`. The SDK's own primitives are extensions of
the same kind, which every session holds, and `bwrap`, the SDK's isolation, which is
[experimental](../reference/python.md#platoon_harnessbwrap), is one that only a team that names it loads.

## How platoon-harness finds your code

A role's `harness` and a team's `extensions` name your code in one of two ways:

| Way | Looks like | Imports it | Use it when |
|---|---|---|---|
| An entry point | `ballot = "ballot:extension"` under `[project.entry-points."platoon_harness.extensions"]` in your package's `pyproject.toml` | Only when a role or a team names it, and nothing else installed | You ship a package |
| `module:attr` | `harness = "my_drivers:MyDriver"`, `extensions = ["ballot:extension"]` | When the team is loaded, from a layer you trust | You try something out, or your code is in no package |

There are two entry-point groups: `platoon_harness.drivers`, whose names are drivers' names and whose values are driver
classes, and `platoon_harness.extensions`, whose names are extensions' names and whose values are `Extension`s. A kind
of code gets a group when a second independent user needs a short name for it. Discovery reads installed metadata and
imports nothing, so before any code loads or any cost is spent it refuses a name that two distributions both register,
unless the team pins one as `name@version` by a version the other does not have, and a distribution whose requirement on
`platoon-harness` excludes the release that runs. `platoon-harness extension list` shows what each group holds, from
metadata alone.

`module:attr` imports, so it is taken only from a layer you trust: Python, your user config, `--set` and the
environment. A project or team file that names one is refused without `--trust`, as
[troubleshooting](../how-to/troubleshooting.md#a-team-file-needs-trust) says.

## What a driver says of itself

A driver's `describe` returns a `DriverInfo` before anything starts, as [the contract](drivers.md#the-contract) says. Two
of its fields concern a driver of yours in particular:

- **`check`** names the check that ships with a driver outside the SDK, as `module:function`, which
  `platoon-harness doctor --check` runs against FakeModel and keeps, and which is imported only to run it. The SDK's own
  drivers, `opencode` among them, name none, as `levels.CHECKED` holds theirs.
- **`credentials`** names where, beneath the agent's folder, its harness keeps a credential, as relative paths that
  cannot leave that folder. When the agent ends, its stop removes them with the harness's `TMPDIR`, and a rest removes
  nothing, as the harness comes back
  ([RFC 0075](../rfcs/0075-an-ended-agent-s-folder-keeps-its-record-and-no-credential.md), a draft).

## Programs

A program is a Python script that starts its session as `program:<name>`, as any script may, and drives it through the
session's ops, so control flow stays out of the team file. It keeps nothing that must survive a restart: after a crash it
is run again on the session, reads what the record holds, and sends each command under a key it makes the same way on
every run, so a command the journal answered before acts once. A team leaves its session to its program with
`until = "program"`, and a person's start or resume of such a team is refused, naming the script way.
`platoon_harness.patterns` holds a program's building blocks, `population` among them
([RFC 0068](../rfcs/0068-a-program-is-a-script-that-owns-its-session.md),
[run a program from Python](../how-to/topologies.md#run-a-program-from-python)).

## The training contract

A training system runs a session per rollout, from a program of its own, and admits each agent through its `Authority`,
which gives the agent model access through a gateway and hears how it ended. It asks the record what can train, and
writes rewards and credit beside the journal, each an estimate by a named producer at a version. The SDK names no
training system: [Training on sessions](training.md) is the contract, what the SDK owns and what the training system
owns, and [architecture §14](../architecture.md#14-training) is its design.

## Rules your code keeps

- **Public names alone.** Code outside the kernel reaches the SDK by its public API alone: each name
  `tests/public_api.txt` lists, and each attribute and method without a leading underscore that a class it lists
  defines, which [the Python API reference](../reference/python.md) shows, and which 0.1.0 promises by default, pending
  the owner's ruling. An extension reaches the kernel by its `__all__`, as the SDK's own primitives do. If an extension
  needs a private name, the kernel is wrong.
- **An op waits on nothing.** An op is synchronous, does no I/O and runs inside one transaction. Work in the world is an
  effect: an op asks for it with `txn.effect`, and a daemon does it and reports
  ([architecture §5.4](../architecture.md#54-effects)).
- **A fold is pure.** It sees its own tables and one event, so its view, made again from the journal, holds what it held.
- **Identity comes from a credential.** No op's arguments say who calls it: `txn.me` does.
- **Unknown is not zero.** A driver reports what its harness shows and no more, and an estimate that has no value says
  why in its status.
- **Unsupported is loud.** A driver method that cannot be honored raises `DriverError` with the reason, and an op
  refuses with `Refused` and a code its docstring explains.
- **Names follow the law.** Ops are imperative, `<extension>.<verb>`, events are past tense, and a driver's name is the
  command you type ([the naming law](../architecture.md#naming-law)).
- **Prove it.** `check_driver` and `check_extension`, from `platoon_harness.testing`, hold a driver and an extension to
  what the SDK's own keep, and report every failure their checks find at once, and a check that could not run as a
  skip, saying why ([conformance](drivers.md#conformance), [check it](extensions.md#11-check-it)). A skip is never a
  pass.

[Architecture §3](../architecture.md#3-laws) states each law, with the test of its name.

## What is not an extension point

The kernel, the journal's format, the SDK's own ops, the wire protocol, the command line's own commands and the clients'
panes are not extended from outside. A change to any of them starts as an RFC:
[when to write one](../rfcs/README.md#when-to-write-an-rfc).
