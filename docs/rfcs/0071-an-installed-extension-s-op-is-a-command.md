# RFC 0071: An installed extension's op is a command

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`main.py`](../../packages/cli/src/platoon_harness_cli/main.py), [`ops.py`](../../packages/cli/src/platoon_harness_cli/ops.py), [`extensions.py`](../../packages/sdk/src/platoon_harness/extensions.py), [architecture section 6](../architecture.md#6-operations) and [section 17](../architecture.md#17-extensions-and-configuration), [the brief's section 11](../spec/BRIEF.md#11-extension-and-configuration-model), [RFC 0004](0004-one-operation-table.md), [RFC 0017](0017-config-and-entry-points.md), [RFC 0026](0026-every-act-from-any-terminal.md) and [RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository |
| Implementation | `feat: Give an installed extension's op a command, loading only that extension`, `feat: Refuse an extension named as a built-in command group`, and the fixes `fix: Leave an extension's command to the runtime where a team names extensions by module:attr` and `fix: Give no command to an installed extension named as one every session holds` |

## Summary

`platoon-harness <extension> <verb> SESSION` runs an op of an installed extension, as `platoon-harness task claim SESSION`
runs one of the SDK's: `ph ballot.cast --agent @author --choice yes` is `platoon-harness ballot cast SESSION --agent @author
--choice yes`. The command line finds installed extensions from metadata, imports only the one its first word names, and
makes that extension's commands as it makes the SDK's, a command per op a person may run, with a flag per argument and the
op's description as its help. Before anything is asked of the session, the command reads the session's manifest, and a
session whose team, as the manifest records it, does not name the extension is refused, saying so, as it holds none of its
ops; where a team names an extension by `module:attr`, the manifest cannot say which it is, and the session's runtime
answers. An extension whose name is one of the command line's own commands, or that of an extension every session holds,
gets no group: discovery refuses it from metadata, before any import, and says why on stderr. `--help` lists each installed
extension under Installed extensions, from metadata, importing none. That an installed extension's op gets a command at all
is the plan's default for an owner question the owner has not ruled on.

## Motivation

[The brief's section 11](../spec/BRIEF.md#11-extension-and-configuration-model) asks that an extension's op be usable
through the SDK, the tool protocol, the CLI and the generic UI with no core edit. Every surface but the command line does
it: `Session.submit`, MCP and `ph` take it from the op table, and both palettes from `ops.list`
([RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md)).
The command line makes its commands before any session exists, from the SDK's own `registry`, in
[`ops.py`](../../packages/cli/src/platoon_harness_cli/ops.py)'s `groups`, so
[architecture section 17](../architecture.md#17-extensions-and-configuration) says an extension's op has no command yet,
and `Session.submit` is how to run one. [The sample extension package](../../examples/extension-package/README.md) casts
its vote from the SDK, from an agent through MCP and `ph`, and from both palettes, and a person at a shell or a CI script
has no way to cast it but Python.

The command line cannot simply load every installed extension to make its commands. Installing activates nothing, and a
component is imported only by exact name ([RFC 0017](0017-config-and-entry-points.md)): importing them all would run code
nobody named, and one that failed to import would break every command. And a command needs the op's schema before the
command line is parsed, so before any session is read, and `--help` has no session at all. The plan's critique added a
third problem: `platoon-harness <extension> <verb>` puts extension names beside the command line's own, such as `run`,
`session` and `task`, and nothing said which wins.

## Proposal

### 1. A group per installed extension, found from metadata

The command line reads the installed extensions from metadata with `discover()`, which imports nothing, and gives each a
group of commands under its entry point's name, which is the name a team gives in `extensions = [...]`. Placed under
Installed extensions, each group's help says what metadata says: the distribution and version that define it, that its
commands run on a session whose team names it, and that it is imported only when a command line names it.

It reads metadata only when the first word may name an extension: when it is none of the command line's own commands, as
for no word at all, `--help`, an extension's name or a mistake. A command of its own never reads metadata to run. Reading
it took about 30 ms here, for 213 distributions.

### 2. Loaded by its group's name alone

When the first word names an installed extension, the command line imports that one, by `load`, and nothing else
installed, and gives its group a command per op of the extension's that a person may run. The rule and the making are the
SDK's own ops', so nothing differs but where the op comes from: no op kept to the runtime or to an agent, and no `wait` or
op on a wait; the name split at its dot, a flag per argument from its schema, `--key` for a command, a read on a view
credential, and the op's description as its help, each op it names written as the command that runs it.

```python
def extension_groups(own: Collection[str], named: str | None) -> list[App]:
    """A group per installed extension, found from metadata. Only `named` is loaded, importing that extension alone."""
```

What cannot be loaded as one extension exits 78, with what is wrong, as a team that named it would be refused:

- A name two distributions define loads neither, naming both. A team picks one by pinning its version, `ballot@0.1.0`; the
  command line has no pin, and no user has asked for one, so the way out is to uninstall one.
- An extension whose SDK requirement this SDK does not meet, or which fails to import, is refused as `load` refuses it.
- An entry point whose `Extension` has another name is refused: its ops lie in that other name's namespace, so no command
  of the group's name would name them.

An extension that gives no op a person may run, as the SDK's `bwrap` gives none, says so in its group's help.

### 3. Refused on a session whose team does not name it

A session holds an extension's ops only when its team names that extension, so before an extension's command attaches,
stores a body or asks anything, it reads the session's `manifest.json`, whose components record each extension the team
names, as the team names it. A session whose team, by those records, does not name the group's extension is refused
`not_found`, with exit 1, as any refused command is, saying which extensions its team names:

```text
platoon-harness: refused not_found: session plain's team does not name the extension ballot, so it holds none of its ops: a
team names its extensions in `extensions`, and this one names none
```

The manifest settles it where the team names each of its extensions by its entry point's name, `ballot` or `ballot@0.1.0`,
which the manifest records as `ballot`, with the distribution that defines it. A team may also name one by `module:attr`,
from a layer it trusts, as [architecture section 17](../architecture.md#17-extensions-and-configuration) says, and the
manifest records that reference alone, which says what extension it is only once imported. So where a team names any by
`module:attr`, the command line refuses nothing itself, and the session's runtime answers, as it answers any op: it runs the
op where the reference is the extension, and where not refuses it `not_found`, `no such op`, after the command has stored
any body it takes. A session whose team names it runs the op as any command runs one, on its runtime, which checks the
arguments against the op it loaded.

### 4. Refused at discovery if its name is held

Two kinds of name are held. The command line's own commands hold theirs: as of this RFC `annotate`, `annotations`,
`attach`, `doctor`, `events`, `extension`, `init`, `run`, `serve`, `session`, `team` and `web`, the groups of the SDK's
ops, `agent`, `approval`, `attention`, `blob`, `board`, `body`, `budget`, `channel`, `context`, `contributors`, `effect`,
`eligibility`, `episode`, `exposure`, `interactions`, `lineage`, `message`, `ops`, `peers`, `repo`, `spans`, `task`, `uses`
and `view`, and the flags `--help`, `-h` and `--version`. The list is read from the command line as it is built, so a
command added later holds its name with no second list to keep. And every session holds the SDK's own extensions, the
kernel's and the primitives', so the kernel refuses an installed extension of one of their names in any session: as of
this RFC each group of the SDK's ops above, and `daemon`, `delivery`, `grant`, `group`, `lease`, `op`, `principal`,
`runtime`, `timer` and `wait`. The command line asks the kernel, which answers as it does on loading one, so that list is
kept nowhere else either.

An installed extension with a held name gets no group. Discovery refuses it from metadata, before any import, and says so
on stderr each time it looks for an extension's group, with the distribution that defines it, in one of two ways:

```text
platoon-harness: extensions.lease: shadow 2.0.0's extension `lease` has no commands, and no session can load it, as every
session holds the SDK's own extension `lease`
platoon-harness: extensions.run: runner 1.0.0's extension `run` has no commands, as `run` is a command of the command line's
own: its ops run through the SDK, MCP, `ph` and the clients' palettes, on a session whose team names it
```

The first is the kernel's refusal said before any session meets it: no team can name the extension, so no surface reaches
its ops, and a name a group of the SDK's ops holds, such as `task`, is refused this way. The second is the command line's
alone: a team may still name such an extension, and its ops work everywhere else.

### 5. Help lists installed extensions from metadata

`platoon-harness --help`, and `platoon-harness` with no terminal, list each installed extension under Installed extensions,
with what metadata says of it, and import none. So the list cannot say which ops an extension gives:
`platoon-harness <extension> --help` loads that one and lists its commands. [The command line
reference](../reference/cli.md) is made from the command line's own commands, so it lists no extension's, and stays the same
whatever is installed.

## The hard parts

**The schema before the session.** A command's flags come from its op's schema, and the command line is built before it
is parsed, so before it knows the session, and `--help` names none. The session's `ops.list` holds the schema too, but only
once the session is read. The first word is the one point where the command line knows which extension is wanted with no
session, so that is where it imports.

**What is installed now and what a session loaded.** A session's runtime imports its extensions when it starts, and the
command line imports what is installed when it runs. After an upgrade the two can differ. The command line compares no
versions, as a session survives an upgrade and a resume labels the drift rather than refusing it: the runtime checks the
arguments against the op it holds, and refuses `invalid` what does not fit.

## Alternatives

| Alternative | Why not |
|---|---|
| Import every installed extension to build the command line | Runs code nobody named, against "installing activates nothing" and import by exact name, and one extension that fails to import breaks every command |
| One generic command, `platoon-harness op SESSION ballot.cast --args JSON` | A second way to run an op, with JSON for flags and no help but the op's name; every op of the SDK's own already has a command of its name |
| Make the flags from the session's `ops.list` | The parser is built before the session is read, and `--help` has no session |
| A prefix of its own, `platoon-harness x ballot cast` | Collides with nothing, but no reader would guess it, and the command would no longer be the `ph` form split at its dot |
| Let an extension take a built-in's name, or the built-in win silently | One shadows a command the reference documents; the other leaves an installed extension with no command and nothing said |
| Ask the session, through `ops.list`, whether it holds the op | Attaches first, and a body would be stored before the refusal; the manifest says the same wherever it settles it, and asks nothing of the session |
| Doing nothing | An extension's op runs from the SDK, MCP, `ph` and both palettes, and from a shell or CI only through Python |

## Consequences

- An installed extension's op runs from the command line as the SDK's ops do, so every surface the brief names runs it with
  no core edit.
- A command line whose first word is none of the command line's own reads metadata first, about 30 ms here, and one that
  names an extension imports it. One that cannot be loaded exits 78, saying why, as a team that named it would be refused.
- An extension named as a command of the command line's own, or as an extension every session holds, has no command, and
  the command line says so whenever it looks for an extension's group, `--help` among those times. `doctor` and `extension
  list` read what the SDK finds, and do not say it.
- A runtime adds an extension of its own, `host`, which no kernel holds until a runtime loads it, so the kernel's answer
  leaves that name free: an installed extension called `host` gets a group, and a team that names it is refused when its
  runtime starts.
- A command the command line adds later takes its name from any installed extension that has it, whose commands then go,
  with the refusal said: a change to the command line, which the changelog names as it names any.
- The reference documents the command line's own commands only, and says how an extension's are made.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 the command | A group per installed extension from metadata, loaded by name alone, refused on a session whose team does not name it, and listed by `--help` | `tests/unit/cli/test_commands.py`, `test_an_installed_extension_s_group_loads_only_that_extension`, `test_an_extension_s_command_on_a_session_whose_team_does_not_name_it_is_refused_saying_why` and `test_help_lists_installed_extensions_from_metadata_without_importing_them`; `tests/integration/test_installed_extensions.py`, `test_the_sample_s_op_is_a_command_from_its_wheel` | `feat: Give an installed extension's op a command, loading only that extension`, `fix: Leave an extension's command to the runtime where a team names extensions by module:attr` |
| M2 the reserved names | An extension named as a command of the command line's own, or as an extension every session holds, refused at discovery, saying why | `test_an_extension_named_as_a_built_in_command_group_is_refused_at_discovery_before_any_import` and `test_an_extension_named_as_one_every_session_holds_is_refused_at_discovery_as_no_session_can_load_it` | `feat: Refuse an extension named as a built-in command group`, `fix: Give no command to an installed extension named as one every session holds` |

## Open questions

1. Whether an installed extension's op gets a command at all is the owner's, as milestone 4's plan asks. The default, pending
   the owner's ruling, is that it does: loaded by its group's name alone, refused on a session whose team does not name it,
   and refused at discovery if its name is a built-in group. A ruling the other way would remove the Installed extensions
   groups and the manifest check, which nothing else rests on, and leave every other surface as it is.

## Evidence

- `tests/unit/cli/test_commands.py`, on fake distributions on `sys.path`, each whose module is not to be imported raising
  as it is: `test_an_installed_extension_s_group_loads_only_that_extension`,
  `test_an_extension_s_command_on_a_session_whose_team_does_not_name_it_is_refused_saying_why`, on four live sessions with
  the command run as `main` in a thread of its own, one whose team names the extension by `module:attr` running it and one
  whose team names another by `module:attr` refused by its runtime,
  `test_an_extension_named_as_a_built_in_command_group_is_refused_at_discovery_before_any_import`,
  `test_an_extension_named_as_one_every_session_holds_is_refused_at_discovery_as_no_session_can_load_it` and
  `test_help_lists_installed_extensions_from_metadata_without_importing_them`.
- `tests/integration/test_installed_extensions.py`, slow, `test_the_sample_s_op_is_a_command_from_its_wheel`: the sample's
  wheel, beside its rival, loads neither, and the rival is never imported; alone, `--help` lists it, and the installed
  `platoon-harness ballot cast` casts a vote on a session whose team names it, is refused `conflict` the second time and is
  refused on a session whose team names no extension.
- Reading metadata took 30 to 32 ms across ten runs of `discover()` for the 213 distributions of the development
  environment, on a Lustre filesystem, on one host. Elsewhere it is UNVERIFIED.
