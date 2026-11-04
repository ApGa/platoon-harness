# Architecture decision records

[architecture.md](../architecture.md) says what the system is. These records say why, and what else was on the table. Each one
names the alternatives considered and the research or spike behind it.

Every record below was accepted on 2026-11-02, during Milestone 0, unless its own date says otherwise.

| # | Decision | In one line |
|---|---|---|
| [0001](0001-session-is-the-durable-noun.md) | Session is the only durable noun | One word for the thing you attach to. `run` is a verb, because the noun collides with Platoon's |
| [0002](0002-one-journal-per-session.md) | One journal per session folder | SQLite, one writer thread, WAL, `synchronous=FULL`, group commit, hybrid checkpoints |
| [0003](0003-events-are-the-only-truth.md) | Events are the only truth | Bodies sit apart so redaction works, and commands fold from events |
| [0004](0004-one-operation-table.md) | One operation table | Every surface is derived. An `Operation` is a definition and a `Command` is one invocation |
| [0005](0005-daemons-and-effects.md) | Daemons and effects | Level-triggered, requested then started then finished, explicit uncertainty, recovery per kind |
| [0006](0006-per-session-runtime.md) | A runtime per session | Ownership is who keeps the process alive. `Session.start` owns, `Session.attach` has no side effects |
| [0007](0007-topology-as-grants.md) | Topology as grants | Grants over relations, presets as macros, no `deny`, delivery set on the reader's side |
| [0008](0008-driver-contract-and-wire.md) | Driver contract and wire protocol | Seven methods, JSON-RPC on stdio, OpenHands as a wire worker |
| [0009](0009-tools-only-mcp-server.md) | Tiny tools-only MCP server | Our own server rather than the `mcp` package, HTTP bearer by default, `ph` as the shell client |
| [0010](0010-provenance.md) | Provenance | Backward references, context bounds, sole writers, three axes, gaps, `Seen`, `NotSeen` or `Unknown` |
| [0011](0011-annotations-beside-the-journal.md) | Annotations beside the journal | Like `git notes`: rewards and judgments never enter the journal or a policy's context |
| [0012](0012-waiting-and-the-monitor.md) | Waiting and the monitor | Park at turn end, a monitor instead of a broader return rule, a hop limit on wakes |
| [0013](0013-platoon-bridge.md) | Platoon bridge | The function-harness seam, two admission routes, a root rule, no kernel branch |
| [0014](0014-swarmchat-compatibility-backend.md) | SwarmChat compatibility backend | Upstream's page and our projection, one way, plus an overlay. Upstream's server never runs |
| [0015](0015-textual-and-safetext.md) | Textual and `SafeText` | One sanitizing boundary for untrusted text, and a Line API transcript paged from the journal |
| [0016](0016-plan-logins-and-credentials.md) | Plan logins and credentials | The user's own harness under its own login. We never read a credential |
| [0017](0017-config-and-entry-points.md) | Config and entry points | TOML, frozen pydantic, two entry-point groups, nothing active until named |
| [0018](0018-who-owns-a-process.md) | Who owns a process | Recorded before exec, a start time tells pids apart, and only a recorded leader proves a group ours |
| [0019](0019-one-link-two-forms.md) | One link, two forms | `Session` has one link, in-process or over a socket. Start and resume are one path, and a client only pulls |
| [0020](0020-finish-and-handover-wait-for-the-turn.md) | Finish and handover wait for the turn | `agent.finish` takes effect at turn end and a wake's `deliver` stays open until its turn begins, each with a live bound |
| [0021](0021-what-a-harness-leaves-behind.md) | What a harness leaves behind | A harness's own `TMPDIR` marks what it started, so `stop` and `reap` end it whichever group it left for |
| [0022](0022-what-a-harness-took-is-the-runtime-s-again.md) | What a harness took is the runtime's again | An offer taken and never landed is queued again when its turn stops short or its harness comes back, and no driver sends it again |
| [0023](0023-agents-that-stay.md) | Agents that stay | `stays` keeps an agent for follow-ups, a report wakes its parent once for each thing the parent asked, and an idle child ends `retired` |
| [0024](0024-a-harness-s-own-agents-are-off.md) | A harness's own agents are off | `allow_native_children` on a role, false unless said, and each driver turns them off by the harness's own setting for one launch |
| [0025](0025-what-an-agent-is-told-is-a-template.md) | What an agent is told is a template | `preamble` on a team or a role, with slots the runtime fills, the default saying what it said before, and the text journaled |
| [0026](0026-every-act-from-any-terminal.md) | Every act from any terminal | A chord is a shortcut and never decides: each act has a typed command or a plain key, Tab reaches the dock with no place chosen, and Esc leaves a panel without interrupting |
| [0027](0027-the-browser-on-our-backend.md) | The browser on our backend | `web` is a guest that folds the journal one way into a projection of fixed ids, lets a browser in by a one-time link of a fixed class, and bounds every request as the tool server does |
| [0028](0028-acting-from-the-page.md) | Acting from the page | Each act keeps its key until answered, across a reload; one cut in Python for both clients; Needs you is the runtime's `attention`; asking first in the page |
| [0029](0029-a-harness-names-our-tools-as-it-shows-them.md) | A harness names our tools as it shows them | `tool_names` on `Capabilities`, `bare` for OpenHands, picks the surface our words and a tool's URL use |
| [0030](0030-openhands-is-an-extra-of-the-sdk.md) | OpenHands is an extra of the SDK | `platoon-harness-sdk[openhands]`, a worker per agent on the runtime's own interpreter that alone loads OpenHands, and an environment of its own as a wire command |
| [0031](0031-a-workspace-is-a-place-git-already-knows.md) | A workspace is a place git already knows | Modes as a ladder; every name a branch part; a worktree locked in the session folder, made in steps a retry adopts, refused before any cost where it would fail, and removed only when git says nothing would go with it; recorded commits kept in a bundle |
| [0032](0032-the-runtime-looks-and-never-moves-a-branch.md) | The runtime looks and never moves a branch | A look after each turn, one at a time, recording on `repo/<name>` with no agent in the envelope; a commit is its maker's by the HEAD reflog entry at its committer time; `Informed-By` resolved from hex alone; conflicts surfaced and never resolved |
| [0033](0033-a-harness-s-own-worktrees-are-off.md) | A harness's own worktrees are off | Claude Code's `EnterWorktree` and `ExitWorktree` off on every launch, and a Codex thread held to `spec.cwd` |
| [0035](0035-the-board-and-the-map-over-messages.md) | The board and the map over messages | Posts and activity answer from the projection by the journal's times; votes are null, hot and top refused and drawn disabled; a queue's or a board's own view stays disabled, saying why |
| [0036](0036-one-ref-names-what-a-model-is-shown.md) | One ref names what a model is shown, and a citation is checked and kept as a claim | `stream@version` with `#La-b` in every result, a carried message shown by what it carries, `based_on` on all eight writes of content checked to name events and lines, a spawn its spawner's, and `blob.get` reading what its caller was handed or made |
| [0037](0037-an-offer-is-confirmed-only-by-its-harness.md) | An offer is confirmed only by its harness, and the record claims nothing more than it holds | A `context.delivered` only from an `input.delivered` or a completed tool item that holds a read's anchor, a launch offer whose goal is the first delivery and which only its own harness confirms, `ModelRef` holding `call_id` alone, `child.seen` claiming no attribution, and every gap one `gap.recorded` with where it began |
| [0038](0038-provenance-is-answered-from-the-record.md) | Provenance is answered from the record, one hop at a time, and never as credit | Three views index what events already hold, and `exposure`, `lineage`, `uses` and `contributors` answer people and programs from them, bounded on an agent's own report stream, with nothing answering `NotSeen` until coverage is proved |
| [0039](0039-estimators-write-beside-the-journal-at-m2.md) | Estimators write rewards and credit beside the journal from M2 | `annotations.sqlite` written with no runtime, by a named producer at a version, about the trace up to `head_seq`, a value only when scored, through `Session.annotate` and `platoon-harness annotate` |

## Adding or changing one

- One decision per file, named `NNNN-short-title.md`, with the next free number.
- Sections, in order: Status, Context, Decision, Alternatives considered, Consequences, Evidence.
- Write why, not what. If the content is a description of the system, it belongs in the architecture.
- Cite evidence by repo-relative link. A decision with no evidence says so.
- Records are not rewritten when a decision changes. Add a new record, and mark the old one `Superseded by NNNN`.
