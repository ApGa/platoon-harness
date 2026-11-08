# RFC 0064: A person's act is an op completed by one form, and a pane's read is one route

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`ops.py`](../../packages/cli/src/platoon_harness_cli/ops.py), [`tui/workspace.py`](../../packages/cli/src/platoon_harness_cli/tui/workspace.py), [`web/server.py`](../../packages/cli/src/platoon_harness_cli/web/server.py), [`web/overlay.js`](../../packages/cli/src/platoon_harness_cli/web/overlay.js), [`primitives/clients.py`](../../packages/sdk/src/platoon_harness/primitives/clients.py), [architecture sections 6, 12, 13 and 17](../architecture.md#6-operations), [RFC 0026](0026-every-act-from-any-terminal.md), [RFC 0028](0028-acting-from-the-page.md), [RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md), [RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md) and [RFC 0046](0046-a-daemon-that-keeps-failing-needs-a-person.md) |
| Discussion | Milestone 4's plan and the audits and critiques behind it, kept outside the repository |
| Implementation | `refactor: Build the palette from the write ops a person holds, by one rule both clients share`; `refactor: Read every pane of the page through one route, which x_provenance becomes`; `feat: Run every write op a person holds from the page through one generated form`; `test: Show an extension's op in the palette and the page with no core edit`; `feat: Let an attention action fix some arguments and leave the rest to its op's form`; `feat: Give every kind of place its act, or say in its gist what settles it`; `fix: Send a person who meets a conflict to its agent or their own checkout`; `docs: Say a commit made in an agent's worktree is recorded as that agent's` |

## Summary

The terminal's palette and a new palette in the page each offer every write op that `ops.list` says the person holds, made by
one function of the command line's package, by one rule: every op but `wait` and the ops on a wait, as a wait parks a turn and a
person has none, and but a query, which a pane draws. Each is worded as its command's help, and runs through one form made from
its schema, which asks once before each op the terminal asks about. Every pane of the page reads through one route, `/v1/x_read`,
which answers in the command line package's words through the session's queries, where the kernel refuses an op that writes,
and for a diff the journal and the patch's body, which it reads and never writes, so nothing is written through it, and which a
view link reaches, but for a diff ([RFC 0065](0065-a-diff-is-read-on-request-as-a-test-is-run.md) section 7). `x_provenance` becomes its `provenance` pane, and
Needs you reads its `attention` pane. In step 2, an action of a place where a person must act fixes only the arguments it knows,
and says with `form` that it leaves the rest to its op's form, which each client opens filled in with what it fixes. Every kind of
place the `attention` view raises carries such an action or says in its gist what settles it, and a conflict never sends a person
to commit in an agent's workspace, where any commit is recorded as that agent's.

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

An action of the `attention` view is an op with every argument, so only an approval, with Allow and Deny, and an uncertain effect,
with It happened and It did not, carry one. A wake a budget refused cannot offer `budget.set`, whose limits only the person can
give, and a lost turn, a wake past `max_hops`, a failure, a dead task and a conflict carry none, nor say what settles them, so the
terminal's dock says only that nothing there takes the action, and the page's Needs you shows no button. A daemon that keeps failing
names its commands in its gist ([RFC 0046](0046-a-daemon-that-keeps-failing-needs-a-person.md)), and a conflict says to resolve it in
the agent's own worktree, where a commit the person makes is recorded as the agent's, as its HEAD reflog says the agent's workspace
made it ([RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md)).

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

A form asks for each flag of the op's command, by its flag and in its help's words, saying whether it is needed, the choices it
takes and what stands when it is left empty, and takes what the flag's type takes: text, yes or no, one of its choices, a whole
number, a number, several separated by commas, JSON, or a body, whose text is made a ref as the command line makes its flag's, by
one function of its package, `body_ref`: a body's ref as it stands, and any other text stored as a body for the op to cite. A JSON
field takes only JSON, and says why before anything is sent. A field left empty is left out, so the op's own default stands, and
the kernel refuses a required one left out, saying which, and a gist too long for one, as at the command line. `via`, what an act
was decided through, is no field: each client says it, `tui` or `browser`, as each says it for an approval today. A form says what
came of its act: done, with the op's result as text, or the refusal.

Before an op in `CONFIRMED`, the form asks once. `CONFIRMED` is the command line package's list, the ops that end an agent or the
session, erase a body, or run a commit's code as you, so an extension's op is never asked about: none needs it yet. Architecture
section 17, STATUS and the page's guide say so, and the extension guide, which milestone 4 plans and nobody has written yet, is to
say it too.

### 3. In the terminal

The palette lists the session's acts by their typed commands, then a form for each write op the person holds, read from `ops.list`
once as the workspace attaches, named as the op is with a space for its dot, and worded as the first sentence of its command's
help. Choosing one opens its form.

### 4. In the page

`view_info` gives the page each form, on any link. Commands, in the top bar, opens a palette of them, found by typing as Search
finds, and choosing one opens its form in the pane, which the address names, `act=`, so the browser's Back and a reload keep it,
and Esc or × closes it. `web` completes the args of an op the person holds a form for as the terminal completes its form's,
making each body's text a ref by `body_ref` and saying `via`, so the page sends a form's args as typed. The composer, which cuts a
long text as the terminal's composer does, says its words as `text` beside a message's args, and `web` makes them its gist, while
a form's `gist` goes as given. Each act keeps its key until it is answered ([RFC 0028](0028-acting-from-the-page.md)). On a view
link and on history every field and its Run button are disabled, saying why, as the composer is.

### 5. One read route

```text
POST /v1/x_read {"pane": "provenance", "ref": "agent/w1@1"} -> {"ref", "at", "lines"}
POST /v1/x_read {"pane": "attention"}                       -> {"rows"}
```

Each pane answers in the command line package's words: `provenance` what `x_provenance` answered
([RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md)), and `attention` every row of the runtime's `attention` view
but a mention, which is a message to read in its chat. A pane reads through the session's queries, which the kernel runs on a
read connection and refuses for any op that writes, so nothing can be written through them, whatever a pane asks. The `diff` pane
that [RFC 0065](0065-a-diff-is-read-on-request-as-a-test-is-run.md) adds also follows the journal to a diff's record and reads its patch by the record's body,
through `Session.events` and `Session.get_body`: those write nothing because no op runs in them, which is the code's to keep, not
the kernel's to refuse. A pane reads on the owner's credential that `web` holds, as every read of the page's does, and `web` lets a
view link reach it by the link's class, as it reaches `view_*`, but for a diff, which only asking for one gives: the kernel's
grants on the owner's credential, not the link's, decide what a pane may read. `/x/command` stays
the one route that writes, and the page sends it no read.

This amends [RFC 0028](0028-acting-from-the-page.md), whose Needs you read through `/x/command` and whose page acted on a few ops,
[RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md)'s route, and the TUI and Web rows of architecture section 6.
`x_provenance` goes with no alias, as nothing is released.

### 6. An action fixes what it knows, and leaves the rest to its op's form

```python
{"label": "Set the budget", "op": "budget.set", "args": {"scope": "role:worker"}, "form": True}
```

An action of the `attention` view is its `label`, its `op`, `args`, the arguments it fixes, and `form`, whether it leaves the rest
to its op's form. One without `form` runs as it stands, as Allow does. One with it fixes only what the place knows, which the record
names, and never guesses an argument: a budget the record does not name is no scope the action fixes. The terminal's dock opens the
op's form, its palette's, filled in with what the action fixes, and the page's Needs you opens the op's form in the pane, the address
holding what the action fixes as `args=`, so Back and a reload keep it. The person may change any field, as in any form, and the form
asks once first for an op in `CONFIRMED`, runs and says what came of it as the form always does. `session show` writes such an action
as its command, ending in `...`, the flags still to give, so it does not run as it stands: `budget set` with its scope alone would set
no limit. A client that holds no form for the op says that the person's grants hold none.

### 7. What settles each kind of place

| Kind | Raised by | Its action, or the words its gist uses | Closed by |
|---|---|---|---|
| `approval` | An approval left to `ask` | Allow and Deny, `approval.resolve` with `id`, `verdict` and `expected_version` | Its answer, or its turn's end |
| `uncertain` | An effect recovery could not settle | It happened and It did not, `effect.settle` with `id` and `happened` | Its settling |
| `uncertain` | A turn a crash cut off | Write to it, `message.send` with `to`, its agent, in a form | Its agent's next turn, which a message starts |
| `mention` | A message to the person | Reply, `message.send` with `to`, its sender, and `reply_to`, in a form | A reply, and reading it, which the person's marks say |
| `mention` | The runtime's report of an agent's end to the person who started it, or a final report nobody heard | None: it is the person's to read, and its agent, which has ended, takes no reply | Reading it, which the person's marks say |
| `conflict` | An agent's look | Write to it, `message.send` with `to`, in a form, and its gist: `tell @ada, or resolve it in your own checkout, never in its workspace, where any commit is recorded as @ada's` | Its agent's next turn, or a look that finds none |
| `conflict` | Your checkout's look | Its gist: `resolve it in your checkout, <path>` | A look that finds none |
| `failed` | An agent's effect | Write to it, `message.send` with `to`, in a form | Its agent's next turn |
| `failed` | An effect of no agent's | Its gist: `<kind> failed, and nothing tries it again: <error>` | Nothing: it stands as news, open question 4 |
| `dead_task` | A task past `max_attempts` | Add it again, `task.add` with `queue` and `based_on`, the dead task's ref, in a form | A task added that cites it |
| `hops` | A wake past `max_hops` | Write to it, `message.send` with `to`, in a form: a person's message is no hop, so it wakes the agent | Its agent's next turn |
| `budget` | A wake a budget refused, or the shared wall budget run out | Set the budget, `budget.set` with `scope` where the record names it, in a form | Any `budget.set` |
| `daemon` | A daemon that keeps failing | Its gist: `` `session stop` then `session resume` start it anew `` ([RFC 0046](0046-a-daemon-that-keeps-failing-needs-a-person.md)) | A run of it that lasts, or a new runtime |

Two rules are new. A dead task's place closes once a task is added that cites it, so adding it again, as its action does, settles
it. A failure of no agent's says that nothing tries it again: a test and a diff record their own failures as outcomes, so only the
runtime's own error, which `runtime.log` holds, or an extension's daemon fails one, and no op redoes an effect.

A conflict in an agent's workspace is resolved by its agent, which the person tells, or in the person's own checkout, from the
agent's branch, and never in the agent's workspace: a commit made there is recorded as the agent's, whoever made it, as whose a
commit is reads the workspace's HEAD reflog, evidence at the workspace's assurance
([RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md)). The workspace guide says so, and a test on real git shows it.

## The hard parts

- **The page's form is JavaScript.** The fields' widgets and the checks that each takes what its kind takes are the page's script.
  Python gives the page every word, flag and kind, so the script decides only how a widget takes them.
- **One form's question replaces nothing.** Asking first opens a popover beside Run, and the form stays in the pane under it, so a
  person who answers no keeps what they typed.
- **A gist is cut at 280 characters.** What settles a place goes where no cut reaches it: before what may run long, as the
  daemon's does before its error, or after a list cut to fit, as a conflict's does after its files, at most three and how many
  more, cut further with `…` where long names would push it out.

## Alternatives

| Alternative | Why not |
|---|---|
| A field of the op table saying whether a person may run an op, or is asked first | No extension needs one yet. `wait` and the ops on a wait are told apart by name, a query by what `ops.list` gives, and asking first is the command line's list. A field comes with the first extension that needs one |
| Queries in the palette and the form | A query's answer is a pane's to word. A form would show it as raw JSON, a second wording beside the pane's |
| Raw op answers from `x_read`, worded by the page | Wording in JavaScript as well as Python drifts, as [RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md) found |
| A route per pane | Each pane would add a route, and a question of which credential reaches it |
| Refusing a query at `/x/command` | It would read the op table for each command. The kernel answers a person's read as a query, which writes nothing, and the page sends it none |
| The form in a popover, as Needs you is | The question asked before an op opens a popover, which would replace the form and what was typed in it |
| An action as an op with every argument, the person's choices left to a command | A budget's limits are the person's alone, so `budget.set` could be offered nowhere |
| `form` read off the op's form, an action fixing every field running at once | An optional field an op gains would turn Allow into a form |
| Fixed arguments shown and not to be changed | Each client would draw a field it may not take, saying why, for a value the person can type in the palette's form anyway |
| A dismiss op, closing a place that is news | A new op and a new state of a place, and a person's dismissing settles nothing the record says. Open question 4 |
| A conflict resolved in the agent's workspace, recorded as the person's | Whose a commit is would need the committer's identity, which the owner has not asked for. Open question 3 |

## Consequences

- An extension's op is offered in both palettes and run through the form with no core edit, and never asked about.
- A view link sees what needs the person, each action disabled saying why, and on history Needs you shows what the journal holds,
  where both were disabled.
- `agent takeover` runs from both palettes, where the terminal's said it was not built, and its words, at the command line too,
  say that driving the agent's native session is not built, where they said it held deliveries so that a human could drive it.
- The page's form takes the pane, so opening a thread or provenance closes it, as each closes the other.
- `view_info` reads `ops.list` on every link and every load, where it read it on a live control link alone.
- Every pane milestone 4 adds reads through `x_read`, and words its answer in Python.
- Every kind of place carries its act or says in its gist what settles it, in the dock, in Needs you and in `session show` alike, and
  a test walks every kind.
- An attention action carries `form`, which every client of the view reads, and the view's version moves from 4 to 5, so an older
  session's view is refolded.
- A dead task's place closes once a task citing it is added, where it stood until the session ended.

## Rollout plan

Its seven milestones were built while it is a draft, ahead of the acceptance the RFC process asks for, so the owner decides on
code already written. Accepted, a last change sets its status to `Implemented` once they are all on main. Rejected, their commits
are reverted.

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 The rule | `forms` in the command line's package, and the terminal's palette made of it from `ops.list` | `test_the_palette_offers_each_write_op_the_person_holds_as_ops_list_gives_it`, `test_the_palette_offers_no_wait_and_no_query` | `refactor: Build the palette from the write ops a person holds, by one rule both clients share` |
| M2 One read route | `/v1/x_read`, its `provenance` and `attention` panes, and `x_provenance` gone | `test_every_pane_reads_through_x_read_and_a_view_credential_reaches_it_and_never_x_command`, and `tests/e2e/test_provenance.py` through it | `refactor: Read every pane of the page through one route, which x_provenance becomes` |
| M3 The page's form | Each form in `view_info`, Commands, and the form in the pane | `test_the_page_is_given_each_write_op_s_form_worded_as_the_command_line_s_help`, `test_the_page_runs_every_write_op_the_person_holds_through_one_form`, `test_an_op_that_ends_an_agent_or_erases_a_body_is_asked_about_once_in_the_page`, `test_a_json_field_takes_only_json_and_shows_it_as_text`, `test_on_a_view_link_or_on_history_every_form_is_disabled_saying_why` | `feat: Run every write op a person holds from the page through one generated form` |
| M4 An extension's op | An extension's op offered in both palettes, and its event drawn | `test_the_palette_offers_an_extension_s_op_with_no_core_edit_and_never_asks_about_it`, `test_an_extension_s_event_is_drawn_by_its_gist`, `test_the_page_is_given_an_extension_s_op_s_form_with_no_core_edit` and `test_the_page_runs_an_extension_s_op_through_its_form_and_never_asks_about_it` | `test: Show an extension's op in the palette and the page with no core edit` |
| M5 An action that leaves the rest | `form` on an action, the dock's and Needs you's form filled in with what it fixes, and a budget place's `budget.set` | `test_a_budget_place_offers_budget_set_with_its_scope_fixed`, `test_an_action_names_only_the_arguments_it_knows`, `test_an_action_that_leaves_arguments_opens_its_op_s_form_prefilled`, `test_needs_you_settles_a_budget_place_through_the_form`, `test_an_action_that_leaves_flags_to_you_is_shown_with_them_still_to_give` | `feat: Let an attention action fix some arguments and leave the rest to its op's form` |
| M6 Every kind | Each kind's action or the words of its gist, as section 7 lists them | `test_every_kind_of_place_carries_an_action_or_names_what_settles_it`, `test_a_dead_task_s_place_closes_once_a_task_citing_it_is_added` | `feat: Give every kind of place its act, or say in its gist what settles it` |
| M7 A conflict | A conflict's gist sends the person to its agent or their own checkout, and the workspace guide says why | `test_a_conflict_says_to_tell_its_agent_or_resolve_it_in_your_own_checkout`, `test_a_conflict_in_the_dock_says_to_tell_its_agent_or_resolve_it_in_your_own_checkout`, `test_needs_you_lists_a_conflict_its_agent_rests_on`, `test_a_commit_made_in_an_agent_s_worktree_is_recorded_as_that_agent_s_whoever_made_it` | `fix: Send a person who meets a conflict to its agent or their own checkout`; `docs: Say a commit made in an agent's worktree is recorded as that agent's` |

## Open questions

1. Whether the browser may list, start, resume or stop sessions is the owner's, as [RFC 0027](0027-the-browser-on-our-backend.md)
   says it may not. The default, pending the owner's ruling, is that it may not: the page's palette offers the ops of the one
   session it serves, and starts or resumes nothing. A ruling the other way would add to the palette, and tear nothing out.
2. Whether both palettes run `agent takeover` is the owner's to confirm: the terminal's palette kept it out until now, as an
   earlier fix said a hold for a terminal not built was a defect. The default, pending the owner's ruling, is that every write op
   a person holds runs from both, as the plan's definition of done asks, with the op's words saying what it does and that driving
   the agent's native session is not built, which the owner's question on the terminal's features defers by default. A ruling
   the other way would leave it out of both palettes, and tear nothing else out.
3. Where a person resolves a conflict in an agent's workspace is the owner's. The default, pending the owner's ruling, is that the
   conflict's gist says to tell its agent or to resolve it in your own checkout, never in the agent's workspace, and the workspace
   guide says a commit made there is recorded as that agent's, as evidence at the workspace's assurance. Recording a commit's
   committer waits for the owner to ask. A ruling the other way would change the gist's words, and tear nothing out.
4. Whether a person may close a place nothing settles, a failure of no agent's, is the owner's. The default, pending the owner's
   ruling, is that it stands as news until the session ends, as no op redoes an effect, saying that nothing tries it again. A
   ruling the other way would add an op, and tear nothing out.

## Evidence

- `ops.list` returns each op a principal holds with its schema and its `query` and `exposes` flags
  ([`kernel/core.py`](../../packages/sdk/src/platoon_harness/kernel/core.py)), and `web` already read it for `view_info`.
- `person_ops` leaves out `wait` and the ops on a wait ([`ops.py`](../../packages/cli/src/platoon_harness_cli/ops.py)), and
  `primitives/waits.py` keeps neither to an agent, so a person holds both.
- [`tests/unit/runtime/test_session.py`](../../tests/unit/runtime/test_session.py),
  `test_an_op_a_team_s_extension_adds_works_with_no_core_edit`: an extension's op run by `Session.submit`, which a person holds.
- `Attention` in [`primitives/clients.py`](../../packages/sdk/src/platoon_harness/primitives/clients.py) gave actions to approvals
  and uncertain effects alone, and `unsettled` in [`primitives/repo.py`](../../packages/sdk/src/platoon_harness/primitives/repo.py)
  said to resolve a conflict in the agent's worktree's path.
- `SetBudget` replaces a scope's limits whole, so `budget.set` with a scope alone sets none: an action cannot run it as it stands.
- A person's message has no hops (`_hops` in [`primitives/messages.py`](../../packages/sdk/src/platoon_harness/primitives/messages.py)),
  so it wakes an agent a wake past `max_hops` left resting.
- `wake.refused` names the scope that held it up in its detail for `over_budget`, and none for `unavailable`, which says in words a
  limit no amount can hold.
- A test and a diff record their own failures as outcomes (`Host._test` and `Host._diff` in
  [`runtime/host.py`](../../packages/sdk/src/platoon_harness/runtime/host.py)), so only an error of the runtime's own fails one.
