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

## Adding or changing one

- One decision per file, named `NNNN-short-title.md`, with the next free number.
- Sections, in order: Status, Context, Decision, Alternatives considered, Consequences, Evidence.
- Write why, not what. If the content is a description of the system, it belongs in the architecture.
- Cite evidence by repo-relative link. A decision with no evidence says so.
- Records are not rewritten when a decision changes. Add a new record, and mark the old one `Superseded by NNNN`.
