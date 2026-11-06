# RFCs

An RFC (request for comments) is a design document. [architecture.md](../architecture.md) says what the system is.
These RFCs say why, and what else was on the table. Each one names the alternatives considered and the research or spike
behind it.

Until 2026-11-07, RFCs 0001 to 0060 were architecture decision records in `docs/adr`; earlier commits and other repositories
cite them as ADR NNNN, under the same numbers. They give only their status and date, and each Summary is its old one-line
index entry.

## Index

Every RFC below was accepted on 2026-11-02, during Milestone 0, unless its own date says otherwise.

| RFC | Title | Status |
|---|---|---|
| [0001](0001-session-is-the-durable-noun.md) | Session is the only durable noun, and run is a verb | Accepted |
| [0002](0002-one-journal-per-session.md) | One journal per session folder | Accepted |
| [0003](0003-events-are-the-only-truth.md) | Events are the only truth, and bodies are separate | Accepted |
| [0004](0004-one-operation-table.md) | One operation table, with every surface derived | Accepted |
| [0005](0005-daemons-and-effects.md) | Daemons, effects and explicit uncertainty | Accepted |
| [0006](0006-per-session-runtime.md) | A runtime per session, with ownership modes | Accepted |
| [0007](0007-topology-as-grants.md) | Topology as grants over relations | Accepted |
| [0008](0008-driver-contract-and-wire.md) | Driver contract and JSON-RPC wire protocol | Accepted |
| [0009](0009-tools-only-mcp-server.md) | A tiny tools-only MCP server, HTTP bearer by default, and ph | Accepted |
| [0010](0010-provenance.md) | Provenance: backward references, bounds, evidence and gaps | Accepted |
| [0011](0011-annotations-beside-the-journal.md) | Annotations live beside the journal | Accepted |
| [0012](0012-waiting-and-the-monitor.md) | Waiting parks at turn end, with a monitor and a hop limit | Accepted |
| [0013](0013-platoon-bridge.md) | Platoon bridge on the function-harness seam | Accepted |
| [0014](0014-swarmchat-compatibility-backend.md) | SwarmChat compatibility backend plus overlay | Accepted |
| [0015](0015-textual-and-safetext.md) | Textual, a SafeText boundary and a Line API transcript | Accepted |
| [0016](0016-plan-logins-and-credentials.md) | Plan logins and credentials | Accepted |
| [0017](0017-config-and-entry-points.md) | TOML config, pydantic, and two entry-point groups | Accepted |
| [0018](0018-who-owns-a-process.md) | Who owns a process | Accepted |
| [0019](0019-one-link-two-forms.md) | One link, two forms | Accepted |
| [0020](0020-finish-and-handover-wait-for-the-turn.md) | Finish and handover wait for the turn | Accepted |
| [0021](0021-what-a-harness-leaves-behind.md) | What a harness leaves behind | Accepted |
| [0022](0022-what-a-harness-took-is-the-runtime-s-again.md) | What a harness took is the runtime's again | Accepted |
| [0023](0023-agents-that-stay.md) | Agents that stay | Accepted |
| [0024](0024-a-harness-s-own-agents-are-off.md) | A harness's own agents are off | Accepted |
| [0025](0025-what-an-agent-is-told-is-a-template.md) | What an agent is told is a template | Accepted |
| [0026](0026-every-act-from-any-terminal.md) | Every act from any terminal | Accepted |
| [0027](0027-the-browser-on-our-backend.md) | The browser on our backend | Accepted |
| [0028](0028-acting-from-the-page.md) | Acting from the page | Accepted |
| [0029](0029-a-harness-names-our-tools-as-it-shows-them.md) | A harness names our tools as it shows them | Accepted |
| [0030](0030-openhands-is-an-extra-of-the-sdk.md) | OpenHands is an extra of the SDK | Accepted |
| [0031](0031-a-workspace-is-a-place-git-already-knows.md) | A workspace is a place git already knows | Accepted |
| [0032](0032-the-runtime-looks-and-never-moves-a-branch.md) | The runtime looks and never moves a branch | Accepted |
| [0033](0033-a-harness-s-own-worktrees-are-off.md) | A harness's own worktrees are off | Accepted |
| [0034](0034-isolation-is-an-extension-s-and-the-runtime-s-git-runs-inside-it.md) | Isolation is an extension's, and the runtime's own git runs inside it | Accepted |
| [0035](0035-the-board-and-the-map-over-messages.md) | The board and the map over messages | Accepted |
| [0036](0036-one-ref-names-what-a-model-is-shown.md) | One ref names what a model is shown, and a citation is checked and kept as a claim | Accepted |
| [0037](0037-an-offer-is-confirmed-only-by-its-harness.md) | An offer is confirmed only by its harness, and the record claims nothing more than it holds | Accepted |
| [0038](0038-provenance-is-answered-from-the-record.md) | Provenance is answered from the record, one hop at a time, and never as credit | Accepted |
| [0039](0039-estimators-write-beside-the-journal-at-m2.md) | Estimators write rewards and credit beside the journal from M2 | Accepted |
| [0040](0040-pi-names-what-landed-and-which-call-made-a-tool-call.md) | Pi names what landed and which call made a tool call | Accepted |
| [0041](0041-a-commit-cites-what-informed-it-by-its-ref.md) | A commit cites what informed it by its ref | Accepted |
| [0042](0042-agents-are-asked-to-cite-by-their-template.md) | Agents are asked to cite by their template, on by default | Accepted |
| [0043](0043-a-person-follows-provenance-from-where-they-read.md) | A person follows provenance from where they read | Accepted |
| [0044](0044-a-level-is-earned-on-the-machine-that-runs-it.md) | A level is earned on the machine that runs it | Accepted |
| [0045](0045-an-agent-s-process-is-not-its-identity.md) | An agent's process is not its identity | Accepted |
| [0046](0046-a-daemon-that-keeps-failing-needs-a-person.md) | A daemon that keeps failing needs a person | Accepted |
| [0047](0047-an-empty-read-names-what-was-already-handed-over.md) | An empty read names what was already handed over | Accepted |
| [0048](0048-a-setting-nothing-carries-out-is-refused.md) | A setting nothing carries out is refused | Accepted |
| [0049](0049-the-contract-a-training-authority-gets.md) | The contract a training authority gets | Accepted |
| [0050](0050-a-script-is-a-person-or-a-program.md) | A script is a person or a program | Accepted |
| [0051](0051-one-rule-for-whom-a-prompt-goes-to.md) | One rule for whom a session's prompt goes to | Accepted |
| [0052](0052-a-reward-has-five-statuses-and-eligibility-is-read-from-the-record.md) | A reward has five statuses, and eligibility is read from the record | Accepted |
| [0053](0053-a-gateway-admission-launches-sealed.md) | A gateway admission launches sealed | Accepted |
| [0054](0054-credit-is-a-producers-annotation-and-propagate-is-the-first.md) | Credit is a producer's annotation, and `propagate@1` is the first | Accepted |
| [0055](0055-the-export-is-the-session-as-it-ended.md) | The export is the session as it ended | Accepted |
| [0056](0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md) | A runtime test is a person's act, and isolated code never leaves | Accepted |
| [0057](0057-an-agent-cites-a-commit-by-the-ref-the-journal-gives.md) | An agent cites a commit by the ref the journal gives | Accepted |
| [0058](0058-a-merge-queue-is-a-queue-and-a-merger-written-out.md) | A merge queue is a queue and a merger, written out | Accepted |
| [0059](0059-a-parent-hears-of-a-child-s-end-once-its-authority-has.md) | A parent hears of a child's end once its authority has | Accepted |
| [0060](0060-an-agent-that-does-not-stay-finishes-with-a-turn-that-leaves-nothing-to-come.md) | An agent that does not stay finishes with a turn that leaves nothing to come | Accepted |

`tests/unit/docs/test_rfcs.py` checks that this table lists every RFC with the title and status the RFC itself gives, so
add the row in the same pull request as the RFC.

## When to write an RFC

Write an RFC before the code when a change touches any of these:

- a public name of the kernel;
- the semantics of the op table ([architecture section 6](../architecture.md#6-operations));
- an event type, or the journal's schema;
- the driver contract or the wire protocol ([section 9](../architecture.md#9-drivers));
- the tool plane ([section 10](../architecture.md#10-tool-plane));
- the schema of the team file or the config ([section 17](../architecture.md#17-extensions-and-configuration));
- the [command line](../cli.md);
- the training contract ([section 14](../architecture.md#14-training));
- a new required dependency, or a new layer;
- a name in `tests/public_api.txt`, renamed or removed;
- a law of [section 3](../architecture.md#3-laws).

Bug fixes, tests, docs and internal refactors need none. If you are unsure, open an issue that describes the problem and
ask.

## How to propose a change

1. **Start a discussion (optional).** For a large idea, open an issue first that states the problem and the rough
   direction, so you learn early whether the maintainers want it.
2. **Take a number.** Use the next free number: one more than the highest number in this directory and in the open pull
   requests that add RFCs. `0000` is the template. If two open RFCs collide, the one that merges second takes the next
   free number before it merges.
3. **Write it.** Copy the template and fill it in:

   ```bash
   cp docs/rfcs/0000-template.md docs/rfcs/NNNN-short-title.md
   ```

   The file name is the number and a few lower-case words joined by hyphens. Set `Status` to `Draft` and `Created` to
   today's date.
4. **Add it to the index.** Add a row to the table above with the status `Draft`.
5. **Open a pull request** that holds only the RFC and its index row, titled in the commit form
   [AGENTS.md](../../AGENTS.md#commits) gives, such as `docs: Add RFC NNNN on <topic>`.
6. **Review.** Discussion happens on the pull request. Answer comments by revising the text; questions that stay open go
   into the RFC's **Open questions**. A maintainer merges the RFC as a `Draft` once it is complete and coherent, so that
   issues, pull requests and other RFCs can link to it. Merging a draft does not accept it.
7. **Decide.** A maintainer accepts, rejects or defers the RFC in a pull request that changes its `Status` and its index
   row. A rejected or deferred RFC keeps its text and gets a short **Decision** paragraph under its status table: why,
   and for a deferred one, what would bring it back.
8. **Implement.** Implementation pull requests link the RFC, as below. When the last milestone merges, a final pull
   request updates the RFC to match the code that landed and sets its status to `Implemented`.

## Lifecycle

```text
Draft ──> Accepted ──> Implemented
  │
  ├────> Rejected
  └────> Deferred ──> Draft (when it is picked up again)
```

| Status | Meaning | Who changes it |
|---|---|---|
| `Draft` | Proposed and open for comments. A draft may be merged so others can link it. | The author, when the RFC is first added |
| `Accepted` | The maintainers agree with the design; implementation can start, milestone by milestone. | A maintainer |
| `Implemented` | Every milestone has merged and the RFC describes the code that landed. | The author or a maintainer, in the last pull request |
| `Rejected` | The design will not be adopted. The **Decision** paragraph says why. | A maintainer |
| `Deferred` | Not now: the problem is real, but something else must happen first. The **Decision** paragraph says what. | A maintainer |

A status may carry a note after it, such as superseded by RFC NNNN or amended on a date, with the full note under the
table.

An Accepted RFC is revised as implementation changes course; once it is Implemented, a changed decision is a new RFC
that supersedes it, noted in the old one's Status cell.

## Linking an RFC to its implementation

- **In each implementation pull request**, say which RFC and milestone it implements, with a link, for example
  `Implements RFC NNNN, milestone M2`. A pull request that departs from an Accepted RFC revises it in the same pull
  request, and says why.
- **In the RFC**, list the pull requests as they merge: in the `Implementation` row of the status table, and in the
  `Pull requests` column of the rollout plan.
- **When it is done**, the RFC is updated to the names and behavior that shipped, and its status becomes `Implemented`.
  From then on the code and [architecture.md](../architecture.md) are authoritative; the RFC records why.

## Format

One decision per file. Every RFC follows [the template](0000-template.md). It opens with a status table (`Status`,
`Created`, `Authors`, `Builds on`, `Discussion`, `Implementation`), then has these sections, in order:

1. **Summary**: the proposal in a paragraph.
2. **Motivation**: what platoon-harness cannot do today, and who needs it.
3. **Proposal**: the design, with typed sketches of new interfaces.
4. **The hard parts** (optional): the problems it expects to be difficult.
5. **Alternatives**: what else was considered, and why not.
6. **Consequences**: what becomes true once it lands, what gets easier and harder, and what it costs.
7. **Rollout plan** (optional): milestones, each with an exit check.
8. **Open questions** (optional): what needs a decision, and by when.
9. **Evidence**: the research, spikes, measurements and tests it rests on.

An RFC written before its code includes Rollout plan and Open questions. An RFC numbered 0061 or above has all six
rows of the status table; RFCs 0001 to 0060 have only `Status`.

Write why, not what. If the content is a description of the system, it belongs in the architecture. Cite evidence by
repo-relative link. A decision with no evidence says so. Typed sketches show shape, not final names; the code that lands
is authoritative. EST marks an estimate and UNVERIFIED a claim nobody has checked yet. Citations of other projects name
the project, the commit read and a path inside it, as the research notes do, for example
`platoon@efe3b277c82c:docs/rfcs/0000-template.md`.
