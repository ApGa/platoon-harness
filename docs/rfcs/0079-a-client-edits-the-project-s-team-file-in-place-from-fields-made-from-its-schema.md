# RFC 0079: A client edits the project's team file in place, from fields made from its schema

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-09 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`config.py`](../../packages/sdk/src/platoon_harness/config.py), [`team.py`](../../packages/sdk/src/platoon_harness/team.py), [`team_file.py`](../../packages/cli/src/platoon_harness_cli/team_file.py), [`machine.py`](../../packages/cli/src/platoon_harness_cli/machine.py), [`teams.py`](../../packages/cli/src/platoon_harness_cli/teams.py), [`web/sessions.py`](../../packages/cli/src/platoon_harness_cli/web/sessions.py), [architecture sections 12 and 17](../architecture.md#12-clients), [RFC 0017](0017-config-and-entry-points.md), [RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md), [RFC 0074](0074-the-browser-lists-starts-resumes-and-stops-sessions.md) and [RFC 0078](0078-a-span-carries-the-labels-of-the-work-it-was-done-for.md) |
| Discussion | The owner's request of 2026-11-09: "it'd be great if we can configure the team from within the team, harnesses, topology, models, efforts, etc. from within the tui/web ui instead of forcing us to write a config file a priori". The owner's rulings of the same day: the editor reads and writes the project's team file, `platoon-harness.toml`, so the command line, the terminal and the browser always agree, starting from the editor saves first, and the session's record keeps the exact team it ran; and changing a running session's settings is later, a stage of its own. The request accepts no design: this one waits for the owner's acceptance |
| Implementation | `docs: Add RFC 0079 on editing the project's team from a client`; `feat: Edit the project's team file in place from fields made from its schema`; `feat: Edit the project's team from the browser's sessions page` |

## Summary

A person sets a team's roles, topology, budget, labels and test command from a client, and the client writes them into the
project's team file, `platoon-harness.toml`, which `run`, `team check`, the terminal and the browser all read. The keys a
person sets map one to one onto the file's schema, and the rest are the file's alone, kept as written. One module of the
command line's makes the editor's fields from the `Team` schema itself, as the clients' op forms are made from `ops.list`
([RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md)): each field's kind, choices, default and words come from the
schema and the reference made from it, a harness is chosen from the drivers this machine has, with what `doctor` finds of
each, and a model is free text. A draft is the file as read with a person's edits, written as the file's own text by a
format-preserving TOML library, so comments, order and layout survive; it is loaded by the same loader `run` uses and
checked by `team check`, every problem shown at its field, with `team show`'s sentences of it and the diff a save makes. A
save writes the whole file through a file beside it, never through a link, over nothing changed since it was read, and asks
once before it writes what would run as the person or a credential to pass on. The browser's sessions page
([RFC 0074](0074-the-browser-lists-starts-resumes-and-stops-sessions.md)) gains the editor first; the terminal's, on the same
module, follows the terminal's redesign.

## Motivation

Today a team starts as a file written by hand, or by `init`, which writes one starter and never edits it
([`machine.py`](../../packages/cli/src/platoon_harness_cli/machine.py) `Starter`). Changing a role's model, a lead's effort
or a topology's limits means opening the file in an editor, knowing its keys from [the reference](../reference/team-file.md),
and running `team check` to learn what is wrong. Agent terminals and browsers people already use let them choose a model or a
setting in the interface, and the owner asked for that here. What the existing pieces do not settle:

- **Which file.** A team comes from layers: the user's config, the project file, a team file, the environment and `--set`
  lines ([architecture section 17](../architecture.md#17-extensions-and-configuration)). A client that kept settings of its
  own would be a sixth layer that `run` and `team check` never read.
- **Which keys.** The schema has keys that run code as the person, a command harness, a `module:attr`, a test command, and
  keys that pass on a credential, an auth profile, which an untrusted load refuses
  ([`config.py`](../../packages/sdk/src/platoon_harness/config.py) `_needing_trust`). A form that set them freely would
  run code nobody looked at.
- **The person's file.** A person's file holds comments and an order of their own. `schema.dumps` writes a resolved team
  from data, so a client that rewrote the file through it would drop both.
- **What is checked.** A client that checked a draft by rules of its own would drift from what `run` refuses.

## Proposal

### 1. What a person sets from a client, one to one onto the file

Each field is one key of the project's team file, at the place the file has it, and a client writes nothing else.

| Section | Keys | Taken as |
|---|---|---|
| Roles, each `[roles.<name>]`, added by name and removed whole | `harness` | One of the drivers this machine has that names a harness, as `machine.harnesses()` finds them, each with what `doctor` says of it: its version, its login's kind and what its checks found, or why it is not here. A harness the file names that is no such driver, a command or a `module:attr`, is shown as the file has it and kept unless another is chosen |
| | `model`, `effort` | Free text. No driver lists the models its harness takes, so none is offered; no driver declares whether it takes an effort, so the field is on every role, and a harness that cannot honor one fails the spawn, as the schema says |
| | `approvals`, `workspace` | The literal's values |
| | `sandbox` | One of the sandboxes its harness's driver declares, and none can be set, saying why, where it declares none |
| | `instructions` | Text of several lines |
| | `auth` | One of the file's auth profiles |
| | `count`, `stays`, `may_spawn` | A whole number, yes or no, and role names separated by commas |
| Topology | `until` | `settled`, `program` or `role:<name>` of each role |
| | A preset of the SDK's, `[topology.<preset>]`, used once, added from those not used and removed whole | Each of its arguments, from its signature |
| | `[topology.channels.<name>]`, added with its kind and removed whole | Each key of its kind's model; the kind is chosen as it is added |
| | `[topology.edges]` | Selectors for each role and `all` |
| | `[topology.limits]` | Each limit |
| Budget | `[budget]` | Each limit, and `estimate.tokens` and `estimate.usd` |
| Labels | `[labels]`, each added by name | Its values ([RFC 0078](0078-a-span-carries-the-labels-of-the-work-it-was-done-for.md)) |
| Auth profiles | `[auth.<name>]`, added by name and removed whole | `env`, variable names alone |
| Test | `[test]`, removed whole | `command`, as a shell splits it, and `timeout` |

Left to the file alone, and shown in the editor as kept as the file has it: `extensions`, the team's and each role's
`preamble`, a role's `tools`, `delivery`, `inbox_depth`, `on_parent_exit`, `allow_native_children` and `budget`, a
harness given as a command or a `module:attr`, `topology.groups` and `topology.grants`, a preset an extension gives or one
used more than once, and any key the schema does not declare, which the loader names. Renaming an entry is removing it and
adding it again.

### 2. Fields made from the schema

`team_editor.py`, in the command line's package, makes each field from the `Team` schema: its kind from the type, as an op's
form takes its kind from its argument's ([RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md)), `text`, `lines`,
`command`, `list`, `integer`, `number`, `yes-no` or `choice`; a literal's values as its choices; and its words from the
sentences of its model's docstring that name it, then its type and default in the words of
[the reference](../reference/team-file.md), which the same functions write. A preset's fields come from its signature, as
the reference's do. A client draws the fields; it computes none of them.

```python
@dataclass(frozen=True)
class Field:
    path: tuple[str, ...]           # its place in the file
    kind: str                       # what it takes
    help: str                       # the docstring's sentences, its type and default
    text: str                       # its value in the draft, as text
    empty: str                      # what stands left empty
    choices: tuple[Choice, ...] = ()
    trust: bool = False             # a value of it from a project file needs trust
    fixed: str | None = None        # why it cannot be changed here
    problems: tuple[Problem, ...] = ()


def harnesses() -> tuple[Harness, ...]: ...  # what `doctor` finds, which blocks
def draft(folder: Path, edits: Sequence[Edit], harnesses: Sequence[Harness]) -> Draft: ...
def save(folder: Path, base: str | None, edits: Sequence[Edit], harnesses: Sequence[Harness], trust: str | None) -> Asked | Draft: ...
```

### 3. A draft is the file and a person's edits

A client keeps a person's edits and sends them whole with each check, so no server keeps a draft. An edit is one of three:
`set` a field's place to text, where empty text leaves its key out; `add` an entry, given its first field, such as a role
and its harness or a channel and its kind; and `remove` an entry. Each is made on the file as read, in order, only where the
draft offers it: a place that is no field, a name that is no name, a value a field does not take, each is refused with
a problem at its place and leaves the draft as it was. A field left empty leaves its key out, and a table it leaves empty
goes with it, but an entry a person named, which stays until it is removed.

The file is parsed by a format-preserving TOML library, and each edit is written into that document: a changed value keeps
its line's comment, a new key goes after its table's last key and before the comments that end the table, which are about
what follows, a new table goes after the last of its kind with those comments after it, and a removed table goes with the
comments right above its header and leaves those about what follows. A table a removal leaves empty goes too, as
`[topology]` does with its only preset, and edits that together change nothing the file means leave it as it was, byte
for byte. Beside the text, the editor keeps the data the edits
mean; after each edit the text is read back with `tomllib`, the loader's own parser, and an edit whose text does not mean
that data is refused, saying to make the change in the file. A file that is not TOML or not UTF-8 is left to the file.

### 4. Checked as `run` loads it and as `team check` checks it

A draft is loaded by `load_trusted` as `run` would load the project there: the user's config beneath it, the environment
over it, with the draft in a folder of its own in the project file's place, so no rule of the editor's stands in for the
loader. A team that loads is checked by `runtime.opening.check`, which `team check` runs, in the folder `web` runs in, and
shown as `team show` shows it. Every problem is placed at the field it names, or the deepest table that holds its place, or
else at the top, so none is left out; a tagged table, a channel, is named in a problem with its tag after it, which is no
key, and is placed at its field. A draft that the loader refuses, or that holds an edit that could not be made, cannot be
saved, saying so; what `team check` finds is said and does not stop a save, as a team may name a harness this machine lacks.

### 5. Written in place

A save sends the edits and `base`, the digest of the file's bytes the person's last check read, or none where there was no
file. The server makes the draft again from the file as it is: a file that changed is refused, writing nothing, and the
next check shows the edits on what it holds now. The draft is written whole to a file beside the project's, created over
nothing and never following a link, synced, and renamed over it, keeping its mode; a new project file is linked into place,
which fails if a file came to be. A project file that is a link, or anything but a file, is refused when it is read, so the
person learns before editing that the editor writes through none. A save is shown first as the diff it makes, which the
client shows beside the fields.

### 6. Trust

A save that writes a value only trust may take, which the file did not hold as it would, asks once first, naming each by its
place and as the team would hold it, in the words a start's trust question uses, and its answer is the digest of that
question: a save with any other answer asks again, and a draft changed since is asked about again. Nothing is trusted by a
save: a start from the saved team asks for trust as any start does ([RFC 0074](0074-the-browser-lists-starts-resumes-and-stops-sessions.md)),
and `run` still needs `--trust`.

### 7. The browser's sessions page

The sessions page's server, loopback alone with its one link, serves three more acts, on the token its link was spent for:

```text
POST /x/team {}                            -> a draft of no edits, with what `doctor` finds read again | {"refused"}
POST /x/check {"edits"}                    -> {"file", "here", "base", "sections", "kept", "problems", "shown", "diff", "blocked", "unmade"} | {"refused"}
POST /x/save {"base", "edits", "trust"}    -> {"said"} | {"ask": {"question", "yes", "answer"}} | {"refused"}
```

The page gains a team editor, opened by Edit: a fieldset of fields for each table, by section, each problem under its field
as its accessible description, the entries to add, `team show`'s sentences, the diff, Save and Read again. A change is
checked once focus leaves its field, and only the newest answer is drawn. Save is disabled, saying why, while a check is
waited for, while there is nothing to save, and while the draft cannot be saved. Start, from the project's team, saves the
editor's changes first, and is disabled, saying why, where Team file names another file while the editor holds changes.
Everything the server says is put in as text.

### 8. The terminal next

The terminal's editor is the next stage, after its redesign lands, on the same module: its fields, its words, its placing
of problems and its save are this module's, so the terminal draws them as the page does, and the two cannot disagree.

## The hard parts

- **Comments that belong to what follows.** A TOML parser keeps a comment above a table's header in the table before it. A
  key appended to that table would land under a comment about the next one, and removing a table would drop the comments
  about the one after. The editor places each new key and table itself, and moves such comments, and the read back with
  `tomllib` holds every edit to what it means, so a layout it cannot place is refused, never written wrong.
- **A file written another way.** Dotted keys, inline tables and a table written in parts, its keys under two headers, are
  edited in their own form, and a test holds one of each; a form the placement does not foresee is caught by the read back.
  Its spacing is not: a role added to a table written in parts takes `tomlkit`'s own placement, which may leave no blank
  line before the next header, and the diff shows it before a save.
- **A rename that loses the race.** A rename cannot compare what it replaces, so a file changed between the last look and
  the rename is overwritten. The window is the time it takes to write and sync a file of a few kilobytes, after the check of
  the person's base and a second look just before it.
- **A slow check.** `team check` asks each role's driver what it is, which runs its harness's status command, a second or two
  for some harnesses. The page checks as a field is left, not as a key is pressed, and draws only the newest answer.

## Alternatives

| Alternative | Why not |
|---|---|
| Settings kept by each client, beside the file | A sixth layer `run` and `team check` never read, and a team the terminal and the browser could hold differently: the owner ruled for the file |
| The whole file rewritten through `schema.dumps` | Loses every comment and the person's order |
| A format-preserving writer of our own, by line | TOML's dotted keys, inline tables, arrays of tables and strings over several lines make that a parser of our own |
| `tomlkit`'s own placement | It puts a new key after the comments that end a table, which are about what follows, as the evidence shows |
| Edits sent as the file's text, typed by the person | A text editor in the page, which the person has already; the schema's forms are what the owner asked for |
| A draft kept on the server between checks | State a reload or a second tab would contend for, where the edits are small enough to send whole |
| Checks of the editor's own, in Python or in JavaScript | A second set of rules beside the loader and `team check`, which would drift from what `run` refuses |
| Every key of the schema a field | Keys that run code as the person would be set unseen in a form; the owner named the keys a person sets, and the rest stay the file's |
| A model chosen from a list | No driver lists the models its harness takes: a list made here would be invented |
| Saving without asking about trust, as writing runs nothing | The page acts as the person, and what it writes runs at the next start: never trusting silently means asking where it writes such a value |

### The new dependency

`tomlkit` is a required dependency of the command line, not of the SDK: MIT, pure Python, with no dependencies of its own,
a wheel of 52 KB, maintained by the Poetry project, which reads and writes its own `pyproject.toml` through it. It is pinned
to `>=0.15,<0.16`, as the editor's placement reads its document's bodies, which a minor release below 1.0 may change. The
SDK keeps reading TOML with `tomllib` alone, and the read back with `tomllib` checks every edit `tomlkit` writes.

## Consequences

- A person sets a team's roles, topology, budget, labels and test command in the browser, and what they set is the project
  file, which the command line and the terminal read as they read any.
- The session's record keeps the exact team it ran, as the manifest already does: a start from the editor saves first, then
  loads the file, so the manifest's sanitized resolved team is what was saved.
- The command line's package depends on `tomlkit`.
- A team file of another name, `--team`, is not edited from a client, and keys left to the file are kept, shown and not
  editable.
- Changing a running session's settings, such as an agent's model mid-session, is not here: the terminal's Alt+M stays as it
  is, and a later stage takes it up.
- Nothing here has run in WebKit, on macOS or on a real model.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 The shared part and the browser's editor | `team_editor.py`; `/x/team`, `/x/check` and `/x/save` on the sessions page; the page's team editor | `tests/unit/cli/test_team_editor.py`; `tests/unit/web/test_sessions.py`, `test_the_team_editor_reads_checks_and_saves_the_project_s_team_and_a_start_runs_what_it_saved`, `test_a_save_of_a_file_changed_since_it_was_read_is_refused_and_one_that_writes_a_test_command_asks_once`; `tests/e2e/test_team_editor.py`, in Chromium and Firefox | `feat: Edit the project's team file in place from fields made from its schema`; `feat: Edit the project's team from the browser's sessions page` |
| M2 The terminal's editor | The same module drawn by the terminal, after its redesign | Tests named for the same promises in the terminal | |

## Open questions

1. Whether a save that writes a value only trust may take, and the start after it, each ask, or the save's yes covers the
   start too, is the owner's. The default, pending the owner's ruling, is that each asks, as a save writes and a start runs;
   the other answer drops one question and tears nothing out.
2. Whether more keys become fields, such as `allow_native_children`, which a role on an ACP harness must set and which the
   editor now leaves to the file, saying what `team check` says, is the owner's. The default is the owner's list alone.
3. Whether the driver contract gains an optional list of the models a harness takes, which the model field would offer, is
   the owner's, and an RFC of its own. The default is none, and a model is free text.

## Evidence

- `tomlkit` 0.15.2 appends a key to a table after the comments that end it: with `[roles.worker]`, a blank line,
  `# about the lead` and `[roles.lead]`, setting `model` on the worker writes it under `# about the lead`, and removing a
  table drops the comment above the next header. Both were tried against that release, and
  `test_an_edit_keeps_the_file_s_comments_order_and_layout` holds the editor's placement.
- `load_trusted` ([`config.py`](../../packages/sdk/src/platoon_harness/config.py)) reads the layers as `run` does, from a
  `cwd`, so a draft in a folder of its own is loaded by the loader itself, which
  `test_a_draft_is_loaded_as_run_loads_it_with_the_user_s_config_beneath` holds.
- `doctor`'s finding of a harness took 0.5 s for `claude` and 1.8 s for `codex` on our hosts, as each runs its own status
  command: the editor reads it as it opens and as Read again asks, and keeps it between checks.
- The tests the rollout plan names.
