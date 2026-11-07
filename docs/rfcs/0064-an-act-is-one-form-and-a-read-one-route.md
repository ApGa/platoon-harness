# RFC 0064: A person's act is an op completed by one form, and a pane's read is one route

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`ops.py`](../../packages/cli/src/platoon_harness_cli/ops.py), [`tui/workspace.py`](../../packages/cli/src/platoon_harness_cli/tui/workspace.py), [`web/server.py`](../../packages/cli/src/platoon_harness_cli/web/server.py), [`web/overlay.js`](../../packages/cli/src/platoon_harness_cli/web/overlay.js), [architecture sections 6, 12 and 17](../architecture.md#6-operations), [RFC 0026](0026-every-act-from-any-terminal.md), [RFC 0028](0028-acting-from-the-page.md) and [RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md) |
| Discussion | Milestone 4's plan and the audits and critiques behind it, kept outside the repository |
| Implementation | `refactor: Build the palette from the write ops a person holds, by one rule both clients share`; `refactor: Read every pane of the page through one route, which x_provenance becomes`; `feat: Run every write op a person holds from the page through one generated form`; `test: Show an extension's op in the palette and the page with no core edit` |

## Summary

The terminal's palette and a new palette in the page each offer every write op that `ops.list` says the person holds, made by
one function of the command line's package, by one rule: every op but `wait` and the ops on a wait, as a wait parks a turn and a
person has none, and but a query, which a pane draws. Each is worded as its command's help, and runs through one form made from
its schema, which asks once before each op the terminal asks about. Every pane of the page reads through one route, `/v1/x_read`,
which answers in the command line package's words from the session's query ops, which a view link reaches, and through which
nothing can be written. `x_provenance` becomes its `provenance` pane, and Needs you reads its `attention` pane. This is step 1 of 2:
step 2 lets an attention action fix only the arguments it knows and leave the rest to its op's form.

## Motivation

The page acts through a few buttons ([RFC 0028](0028-acting-from-the-page.md)): a message, a reply, an approval, the actions Needs
you offers, an agent's interrupt, retire and cancel, and closing or cancelling the session. Spawning an agent, erasing a body,
budgets, channels, tasks, boards, episodes and every other op a person may run are the terminal's and the command line's alone, as
[web.md](../how-to/web.md) says under Not built yet, though `/x/command` already runs any op the grants hold.

The terminal's palette is made from `person_ops()`, the ops of the SDK's own registry, so an op that a team's extension adds, which
`ops.list` holds, is never offered there, where architecture section 17 says the generic client renders one with no core edit.

The rule that keeps an op from a person lives in `person_ops` alone ([`ops.py`](../../packages/cli/src/platoon_harness_cli/ops.py)),
and `ops.list` carries no flag for it: a person holds `wait` and `wait.cancel`, as every op is a person's, and holds the reads, a
stream and `ops.list` itself among them. Two clients that each filtered `ops.list` in their own way would drift.

The page reads provenance through `x_provenance`, a route of its own, and what needs the person through `/x/command`, as a query,
which a view link cannot reach, so its Needs you is disabled. Each pane milestone 4 adds, review, tasks and boards, spans, who
reached whom and tool activity, would add a route of its own, with nothing saying which credential reaches it.

## Proposal

### 1. One rule, which the command line's package states for both clients

```python
def forms(held: Iterable[Mapping[str, Any]]) -> list[Form]: ...  # `held` is what ops.list answers the person

@dataclass(frozen=True)
class Form:
    op: str
    said: str                 # the op's description, as its command's help says it
    fields: tuple[Flag, ...]  # a field per flag of its command, but `via`
    via: bool                 # whether the op takes `via`, which the client says
```

Of what `ops.list` says the person holds, every op but `wait` and the ops on a wait, as the command line leaves them out already,
since a wait parks a turn and a person has none, and but a query, one marked `query` or `exposes`, which a pane draws and the
command line prints. `ops.list` already leaves out what no grant gives a person, the runtime's ops and an agent's own. No field is
added to the op table: an extension's op is offered when the person holds its grant, as every op is, and no extension needs a field
yet. `agent.takeover` is offered and runs, as it does at the command line, holding an agent's deliveries until `agent.release`,
and its own words say that driving the agent's native session is not built, as `/takeover` says.

### 2. One form, made from the schema

A form asks for each flag of the op's command, by its flag and in its help's words, and takes what the flag's type takes: text, yes
or no, one of its choices, a whole number, a number, several separated by commas, JSON, or a body, whose text is stored as a body
for the op to cite. A JSON field takes only JSON, and says why before anything is sent. A field left empty is left out, so the op's
own default stands, and the kernel refuses a required one left out, saying which. `via`, what an act was decided through, is no
field: each client says it, `tui` or `browser`, as each says it for an approval today.

Before an op in `CONFIRMED`, the form asks once. `CONFIRMED` is the command line package's list, the ops that end an agent or the
session, erase a body, or run a commit's code as you, so an extension's op is never asked about: none needs it yet, and the
extension guide says so.

### 3. In the terminal

The palette lists the session's acts by their typed commands, then a form for each write op the person holds, read from `ops.list`
once as the workspace attaches, named as the op is with a space for its dot, and worded as the first sentence of its command's
help. Choosing one opens its form.

### 4. In the page

`view_info` gives the page each form, on any link. Commands, in the top bar, opens a palette of them, found by typing as Search
finds, and choosing one opens its form in the pane, which the address names, `act=`, so the browser's Back and a reload keep it,
and Esc or × closes it. A form says under it what came of its act: done, with the op's result as text, or the refusal. Each act
keeps its key until it is answered ([RFC 0028](0028-acting-from-the-page.md)). On a view link and on history every field and its
Run button are disabled, saying why, as the composer is.

### 5. One read route

```text
POST /v1/x_read {"pane": "provenance", "ref": "agent/w1@1"} -> {"ref", "at", "lines"}
POST /v1/x_read {"pane": "attention"}                       -> {"rows"}
```

Each pane answers in the command line package's words, from the session's query ops, which the kernel's grants decide:
`provenance` what `x_provenance` answered ([RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md)), and `attention`
every row of the runtime's `attention` view but a mention, which is a message to read in its chat. A view link reaches it as it
reaches `view_*`. It runs queries alone, so nothing can be written through it. `/x/command` stays the one route that writes, and the
page sends it no read.

This amends [RFC 0028](0028-acting-from-the-page.md), whose Needs you read through `/x/command` and whose page acted on a few ops,
[RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md)'s route, and the TUI and Web rows of architecture section 6.
`x_provenance` goes with no alias, as nothing is released.

## The hard parts

- **The page's form is JavaScript.** The fields' widgets and the checks that each takes what its kind takes are the page's script.
  Python gives the page every word, flag and kind, so the script decides only how a widget takes them.
- **One form's question replaces nothing.** Asking first opens a popover beside Run, and the form stays in the pane under it, so a
  person who answers no keeps what they typed.

## Alternatives

| Alternative | Why not |
|---|---|
| A field of the op table saying whether a person may run an op, or is asked first | No extension needs one yet. `wait` and the ops on a wait are told apart by name, a query by what `ops.list` gives, and asking first is the command line's list. A field comes with the first extension that needs one |
| Queries in the palette and the form | A query's answer is a pane's to word. A form would show it as raw JSON, a second wording beside the pane's |
| Raw op answers from `x_read`, worded by the page | Wording in JavaScript as well as Python drifts, as [RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md) found |
| A route per pane | Each pane would add a route, and a question of which credential reaches it |
| Refusing a query at `/x/command` | It would read the op table for each command. The kernel answers a person's read as a query, which writes nothing, and the page sends it none |
| The form in a popover, as Needs you is | The question asked before an op opens a popover, which would replace the form and what was typed in it |
| A form filled in from where it was opened | Step 2, where an attention action fixes the arguments it knows |

## Consequences

- An extension's op is offered in both palettes and run through the form with no core edit, and never asked about.
- A view link sees what needs the person, each action disabled saying why, and on history Needs you shows what the journal holds,
  where both were disabled.
- `agent takeover` runs from both palettes, where the terminal's said it was not built, and its words, at the command line too,
  say that driving the agent's native session is not built, where they said it held deliveries so that a human could drive it.
- The page's form takes the pane, so opening a thread or provenance closes it, as each closes the other.
- `view_info` reads `ops.list` on every link and every load, where it read it on a live control link alone.
- Every pane milestone 4 adds reads through `x_read`, and words its answer in Python.

## Rollout plan

Each milestone lands beside this draft. Once the owner accepts it and they are all on main, a last change sets its status to
`Implemented`; step 2, an attention action that fixes only the arguments it knows, then amends it.

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 The rule | `forms` in the command line's package, and the terminal's palette made of it from `ops.list` | `test_the_palette_offers_each_write_op_the_person_holds_as_ops_list_gives_it`, `test_the_palette_offers_no_wait_and_no_query` | `refactor: Build the palette from the write ops a person holds, by one rule both clients share` |
| M2 One read route | `/v1/x_read`, its `provenance` and `attention` panes, and `x_provenance` gone | `test_every_pane_reads_through_x_read_and_a_view_credential_reaches_it_and_never_x_command`, and `tests/e2e/test_provenance.py` through it | `refactor: Read every pane of the page through one route, which x_provenance becomes` |
| M3 The page's form | Each form in `view_info`, Commands, and the form in the pane | `test_the_page_is_given_each_write_op_s_form_worded_as_the_command_line_s_help`, `test_the_page_runs_every_write_op_the_person_holds_through_one_form`, `test_an_op_that_ends_an_agent_or_erases_a_body_is_asked_about_once_in_the_page`, `test_a_json_field_takes_only_json_and_shows_it_as_text`, `test_on_a_view_link_or_on_history_every_form_is_disabled_saying_why` | `feat: Run every write op a person holds from the page through one generated form` |
| M4 An extension's op | An extension's op offered in both palettes, and its event drawn | `test_the_palette_offers_an_extension_s_op_with_no_core_edit_and_never_asks_about_it`, `test_an_extension_s_event_is_drawn_by_its_gist`, `test_the_page_is_given_an_extension_s_op_s_form_with_no_core_edit` and `test_the_page_runs_an_extension_s_op_through_its_form_and_never_asks_about_it` | `test: Show an extension's op in the palette and the page with no core edit` |

## Open questions

1. Whether the browser may list, start, resume or stop sessions is the owner's, as [RFC 0027](0027-the-browser-on-our-backend.md)
   says it may not. The default, pending the owner's ruling, is that it may not: the page's palette offers the ops of the one
   session it serves, and starts or resumes nothing. A ruling the other way would add to the palette, and tear nothing out.
2. Whether both palettes run `agent takeover` is the owner's to confirm: the terminal's palette kept it out until now, as an
   earlier fix said a hold for a terminal not built was a defect. The default, pending the owner's ruling, is that every write op
   a person holds runs from both, as the plan's definition of done asks, with the op's words saying what it does and that driving
   the agent's native session is not built, which the owner's question on the terminal's features defers by default. A ruling
   the other way would leave it out of both palettes, and tear nothing else out.

## Evidence

- `ops.list` returns each op a principal holds with its schema and its `query` and `exposes` flags
  ([`kernel/core.py`](../../packages/sdk/src/platoon_harness/kernel/core.py)), and `web` already read it for `view_info`.
- `person_ops` leaves out `wait` and the ops on a wait ([`ops.py`](../../packages/cli/src/platoon_harness_cli/ops.py)), and
  `primitives/waits.py` keeps neither to an agent, so a person holds both.
- [`tests/unit/runtime/test_session.py`](../../tests/unit/runtime/test_session.py),
  `test_an_op_a_team_s_extension_adds_works_with_no_core_edit`: an extension's op run by `Session.submit`, which a person holds.
