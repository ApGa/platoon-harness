# RFC 0043: A person follows provenance from where they read

| | |
|---|---|
| Status | Accepted, 2026-11-05; amended by [RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md) (a draft) |

**Amended by [RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md)**, a draft: the pane reads `x_read`'s `provenance` pane, the page's one read of its own, where it read
`x_provenance`, which goes.

## Summary

One wording for both clients, the terminal's `/provenance` on the chosen line and the browser's Provenance pane through `x_provenance`, each link by how it is known, each answer's head, bound and open turn, and credit only as what an estimator said

## Motivation

[RFC 0038](0038-provenance-is-answered-from-the-record.md) made the record answer `exposure`, `lineage`, `uses` and `contributors`
for people and programs, and [RFC 0039](0039-estimators-write-beside-the-journal-at-m2.md) let estimators write credit beside the
journal. Only the command line and `Session` could ask. A person reads a session in the terminal's transcript or in the browser's
chats, and the owner wants provenance to be a selling point there: from any line, what it rests on, what came of it and whose work it
reaches, each link labelled by how it is known, with credit only as what an estimator said. The browser drew a Provenance button,
disabled ([RFC 0028](0028-acting-from-the-page.md)), and the terminal had no act for it.

## Proposal

- **One wording, for both clients.** `platoon_harness_cli.provenance` turns the three answers and the annotations of one event into
  lines, as `roster.py` words a roster row for both: the event, then four parts, Sources, Uses, Contributors, and Credit and
  rewards. A line is a part's heading, a fact of an answer, or a link labelled by the kind it is known by, `declared`, `observed`,
  `cause`, `ancestry` or `gap`, with the ref following it opens, and a warning where it says something is unknown, missing or cut.
  Clients decide nothing and compute nothing (architecture §12): the terminal draws the lines, and the browser asks `web` for them.
- **Every answer says what qualifies it.** Each part says the head it was read at; lineage says where it stops counting, below the
  model call that chose the event, where the journal recorded it, or a commit's look; an answer whose turn had not ended says a later
  report can still confirm an offer or join a call. What an answer does not hold below its bound reads as not held there, "not
  handed over through us below the bound" and "not said taken below the bound", never as never, since a later report can be in the
  record. `unknown` is spelled out with its reasons, `not seen` is said only for `not_seen`, a citation by a person or a program says
  their reading is no evidence, one by nobody the record names, as a commit in the shared workspace, says nobody's is, and no line
  says a share, a weight or a rank.
- **How a harness took an offer is said, and where a read's result went.** A confirmation names the evidence its harness's report
  gave. A read's tool item says its result returned to the harness under that call's id, and under Codex's `callId` to the Code Mode
  script that made the call, which may never have shown it to the model, with how many commands share the id.
- **Who made it, and what joins it to a call, by what the event is.** An agent's command is joined through the tool call it came
  under, and one that came with no id says so. A harness's report of an item names the call its report names, and a tool item
  opens the first event of each command of its agent's that came under its id, so an agent's own transcript, where its writes show
  as tool items, leads to them. A commit says a look found it in git, which names no call, and anything else the runtime recorded
  says so. A contributor that made the outcome says it made it, and what else reached it.
- **Why a link opens nothing is said in its place.** A commit git holds and the journal does not, and a fact are drawn with no link,
  their words saying why. An `Informed-By` value that cites nothing says why, as its record keeps it ([RFC
  0041](0041-a-commit-cites-what-informed-it-by-its-ref.md)), and opens the event it names, if any. A page an answer cut names the
  command line command, with its cursor, that reads on. A ranged citation opens the event it cites.
- **Credit is shown only as what an estimator said.** The fourth part lists the event's annotations, each by its producer, version
  and the first eight digits of its params' hash, so two runs of one estimator are told apart, with its scope, its status, and its
  value only when scored, beside any other, never summed. The SDK ships no estimator.
- **The terminal: `/provenance`, and `p` in the transcript.** It runs on the chosen line, the newest while following, and a line of a
  message that carries another event's words opens on that event, as the record shows it. The panel holds one event at a time: Enter
  on a link follows it, and Esc goes back one hop, and from the first leaves. With no line chosen it says why, and that what an agent
  is saying now is no event until the journal holds it. A long line wraps under its kind, and rows that share a key are one choice.
- **The browser: a Provenance pane on every message, and `x_provenance`.** The button opens a pane with the same lines, read from
  `/v1/x_provenance`, a read of ours beside SwarmChat's `view_*`, which a view link reaches as it reaches those. The pane begins with
  what the record holds and cannot know. The address names the event, `provenance=`, so the browser's Back goes back a hop and a
  reload keeps the pane, and Esc or its close button closes it. The pane is read when it opens and again when its event is asked
  again. Following a link that a chat shows opens that chat at the message too. Each link is a button, and a message's actions,
  which SwarmChat shows on hover, show too while focus is in the message and wrap within it, so the keyboard reaches Provenance and
  every link, and a narrow chat beside the pane keeps them within their message.
- **The projection says what each line shows.** `swarmchat.sqlite`, at version 6, keeps on each line the ref of the event it shows,
  which `x_shows` gives the page, and `x_provenance` names the message an event is in its chat, `at`, by that ref or by the event that
  made the line.

## Alternatives

| Alternative | Why not |
|---|---|
| Each client wording the answers itself | Two wordings drift, and the browser's would be JavaScript the shape tests cannot read |
| A client walk over `lineage` | RFC 0038 made `contributors` an op so that no client walks; a client draws |
| Alt+P for `/provenance` | A terminal sends Alt and a letter as Esc then that letter, so Esc then "please" would open the panel and take the rest of the word; `p` in the transcript is a plain key where nothing is typed, and the typed command reaches it from the composer |
| Paging each part in the panel | It would mix pages read at different heads into one list. The first page shows, and the line that says what was cut names the command that reads on |
| The panel's own back stack in the browser | The address is SwarmChat's place for a pane, so Back, a reload and a copied address all work as they do for a thread |
| Credit beside each contributor | An annotation is about the event it targets, at a head, with its own params; drawing one beside a maker would read as that maker's share of this outcome |
| A line for each surface of the maker's harness | Every surface is unproved until a stored conformance result proves one, which each `unknown` and each contributor already says |
| The interaction graph, a child under the call that spawned it, refs in message text followed, search by ref | Milestone 4, as the design keeps them |

## Consequences

- The terminal's keymap gains a typed act with no chord and a transcript key, and a place of its own for the panel's Esc.
- The page's overlay replaces `route` and `onKey` too, and adds `provenance` to SwarmChat's address keys. An upgrade that renames
  either breaks the browser tests.
- Each hop reads three queries and the annotations, each at its own head, so a live session's parts can name different heads, and
  each says its own.
- A projection folded before version 6 is dropped and folded again when `web` opens it, as any version change is.

## Evidence

- `tests/unit/cli/test_provenance.py`: each link by its kind and the event it opens, each answer's head, bound and open turn, unknown
  with its reasons, what a page left out, a link that opens nothing saying why, a ranged citation, `not seen` and a walk cut short,
  contributors weighing nobody, and an estimate by its producer and version beside another, never summed.
- `tests/unit/tui/test_provenance.py`, Pilot on scripted harnesses: sources, uses and contributors each labelled, an edge followed and
  Esc back, a carried message opening on what it carries, a line with no event, credit only as what estimators said, and history.
  `test_snapshots.py`, `test_the_provenance_panel_draws_each_link_with_how_it_is_known`.
- `tests/unit/web/test_server.py`: `x_provenance` on a view link, writing nothing, naming where a chat shows an event, and refusing
  what is no event. `tests/e2e/test_provenance.py`, in Chromium: the pane's three parts and credit, read again when asked again with a
  second estimate beside the first, a ref followed into its chat or its own pane and Back, and the pane on a view link saying what
  the record cannot know.
- `tests/integration/test_claude.py`, `test_the_tui_shows_the_call_that_chose_a_cited_write_and_what_its_citer_was_handed` and
  `test_a_tool_item_names_the_call_its_report_names_and_opens_the_write_its_command_made`, on Claude Code 2.1.316 against FakeModel.
- A review found the first wording saying "never" where an answer held nothing below its bound, "no tool call's id came with it" of
  a tool item that held one, "no agent" of a commit nobody the record names made, and a Codex read as one its harness took; and
  links unreachable from the keyboard. Each has a test of its own in `tests/unit/cli/test_provenance.py`, and the keyboard and the
  narrow chat in `tests/e2e/test_provenance.py`.
