# RFCs

[architecture.md](../architecture.md) says what the system is. These RFCs say why, and what else was on the table. Each one
names the alternatives considered and the research or spike behind it.

Until 2026-11-07, RFCs 0001 to 0060 were architecture decision records in `docs/adr`; earlier commits and other repositories
cite them as ADR NNNN, under the same numbers. They give only their status and date, and each Summary is its old one-line
index entry.

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

## Adding or changing one

- One decision per file, named `NNNN-short-title.md`, with the next free number.
- Sections, in order: Summary, Motivation, Proposal, Alternatives, Consequences, Evidence.
- Write why, not what. If the content is a description of the system, it belongs in the architecture.
- Cite evidence by repo-relative link. A decision with no evidence says so.
- RFCs are not rewritten when a decision changes. Add a new RFC, and mark the old one superseded by RFC NNNN.
