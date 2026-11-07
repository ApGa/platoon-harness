# Security

This page says what platoon-harness protects and from whom, what it does not protect, how long a session keeps what it
records, and what is redacted and what is not. [Architecture section 15](architecture.md#15-security) is the design of
record; this page is its guide, and links each part to where it is said in full. [STATUS](STATUS.md) says what of it is
tested.

## What it protects, tier by tier

Section 15 keeps each threat in a tier of its own:

| Tier | What protects you | In full |
|---|---|---|
| Model arguments: hallucination, and prompt injection through a tool's arguments | An agent is who its token says, never what its arguments claim: no tool schema has a field for the caller's identity, an undeclared argument is refused and journaled, and every op is authorized by the server, at call time | [§15](architecture.md#15-security), [laws 6 and 7](architecture.md#3-laws), [the tool plane](architecture.md#10-tool-plane) |
| Untrusted content: board entries, repository files, tool output, Markdown | Content is data, never instructions: the terminal draws it through `SafeText`, and the page escapes it and runs scripts by hash alone | [§15](architecture.md#15-security), [the web guide's Security](how-to/web.md#security) |
| Network: the browser, and anything else that reaches a port | Loopback by default; any other address needs TLS, a wildcard is refused, and a session on a plan login stays on loopback. View and control links are separate classes, open once and expire, and `web` keeps only their hashes. `Host` must name the authority served and a POST's `Origin` the page's own | [§15](architecture.md#15-security), [the web guide's Security](how-to/web.md#security) |
| An agent that can run commands, as you | Nothing in this tier: see below | [§15](architecture.md#15-security), [workspaces](how-to/workspaces.md#where-an-isolated-agent-runs) |
| Extensions and drivers | They are trusted code: installing one is trusting it, and a team or project file can select one but never install one | [§15](architecture.md#15-security), [extensions](architecture.md#17-extensions-and-configuration) |

Plan logins have rules of their own. platoon-harness starts your harness under its own login and never reads, copies or
proxies a credential. Several agents headless on one plan login are refused, exit 78, unless you say it is your own work
with `--plan-login`, or `plan_login=True` from Python, and `web` serves a session on a plan login on loopback alone, since
a control link acts as you, on your login. [RFC 0016](rfcs/0016-plan-logins-and-credentials.md) says why.

## What it does not protect

- **Other users on the same machine.** They are out of scope. Every local user reaches loopback, so another user's process
  can connect to a session's tool plane and to `web`'s port. A bearer check keeps it from reading the session or acting on
  it there, so the data is protected, but not availability: each server takes at most 1,024 connections at once, counted
  before any is read, so a process that holds them makes your agents' tool calls answer 503. The control socket is out of
  their reach, in a directory only you can open. Out of scope is the project's default, pending its owner's ruling on the
  threat model.
- **An agent that can run commands, as you.** Claude Code, Codex, pi and OpenHands run shell commands, as your user, so
  such an agent can read the session folder, the owner's token, another agent's token in that agent's environment, other
  sessions and your home. On such a session, approvals and the line between sessions are workflow controls, not
  boundaries, and every agent's assurance is `cooperative`. An `isolated` workspace hides your home, the session root and
  the runtime directory from its harness, but it still reaches the network, every loopback service, every socket file
  outside those folders and everything you can read elsewhere, on the same kernel. It is experimental, Linux only, and has
  passed its escape tests on one host.
- **The network, from an agent.** Nothing confines an agent's network access, an isolated one's included.
- **Resources.** No agent's CPU, memory or disk is limited. Reporting each agent's use is `session.metrics`, which is
  planned, and it will report use, never limit it.
- **macOS.** Nothing has run there yet, and no isolation exists for it.

## Credentials

- **Model access.** A team file names environment variables, never values. A role's auth profile names the variables its
  harness gets, and with none the harness signs itself in, as it does in your shell. Each harness starts with an allowlist of
  variables, so nothing else of yours passes through. `Secret`, which holds a value, prints as a mask and refuses JSON,
  pickling and copying. A training system's gateway bearer lives only in its harness's environment: no form of it is in
  the session folder or in the command line of any of the harness's processes.
- **Agents' tokens.** Each agent has a token of its own for the tool plane, held in memory and in its harness's environment,
  and only its hash is journaled. An ended agent's token is refused, and so is one session's at another's tool plane.
- **The owner's and the view token.** `owner.token`, a control credential, and `view.token`, which reads and never writes,
  are files in the session folder that only you can read, which each runtime writes fresh when it starts. A session a program
  started has no owner token. A stop or a close removes both. A runtime killed outright leaves its own, dead, as no runtime
  answers them, until the session is resumed and stopped; a session never resumed keeps them, and you may delete them before
  you copy its folder.
- **The browser.** A link opens once, within ten minutes, its secret after `#`, for a session in that browser that lasts
  twelve hours. `web` keeps only hashes, in its own memory, so stopping it ends every browser's session. Your own credential
  never reaches a browser.

## Retention

Nothing expires. A session keeps what it records until you delete its folder; no command deletes one. Remove the folder,
under the root `platoon-harness doctor` names, once `platoon-harness session list` says no runtime holds it.

A session's folder, as [§4](architecture.md#4-session-folder-and-process-model) lists it, holds:

- the journal: every event, each with its gist, and bodies, small ones inline and large ones in `blobs/`;
- `annotations.sqlite`, rewards and credit; `marks.sqlite`, how far you have read; and `swarmchat.sqlite`, the page's
  projection, which holds the text of the messages it shows;
- `runtime.log`, what a detached runtime said, and in each agent's folder `stderr.log`, what its harness said, and an
  isolated harness's home, with whatever that harness keeps there;
- `commits.bundle`, the commits the journal recorded.

Outside it: a harness on your own login keeps its own transcripts where it always does, in your home; an agent's worktree or
branch may stay in your repository, as [workspaces](how-to/workspaces.md#when-a-workspace-goes) says; and the root keeps what
`doctor --check` found of each harness. The folder as it ended is the session's export ([RFC
0055](rfcs/0055-the-export-is-the-session-as-it-ended.md)), so copying it copies all of the above.

### Erasing a body

To erase a body, tombstone it: `platoon-harness body tombstone SESSION --sha256 SHA256`, the terminal's palette, or
`Session.tombstone`, on a session a runtime holds. Reads of it stop at once, and the runtime erases its bytes from the
journal, its write-ahead log and `blobs/`. The page's projection drops it when `web` next folds the journal; deleting
`swarmchat.sqlite` drops it too, and `web` folds the projection again. The event and the body's hash stay, so the record
stays whole, and a tombstoned body can never be entered again.

Tombstoning does not reach:

- **A gist.** It is part of its event, which nothing changes. The design's answer is an offline rewrite that makes a new
  session, and no tool does that yet. Keep secrets out of gists.
- **A hash.** It survives, and to whoever reads the journal it is a capability, while a body with few possible values can be
  guessed from it. Bodies are for content, not for secrets.
- **Anything outside the journal:** what a harness keeps of its own, a commit, a copy of the folder, or the bytes on the
  device below the filesystem.

## Redaction

What the runtime gave a harness is masked wherever that harness's words go: its auth profile's values, a gateway's bearer
and its token, plain, JSON-escaped, URL-quoted and in base64 of either alphabet, in what it writes to its `stderr.log`, in
what it reports to the journal, its live text among it, and in the runtime's log. A resolved config refuses a secret's
exact value.

Nothing else is masked. A key an agent reads from a file, one in a repository or one typed into a prompt is content, and is
kept as it was written: in a gist, a body, a commit or a harness's own transcript. Nothing sanitizes a session's folder.
Keep secrets out of what agents read, and tombstone a body that holds one.

## Reporting a vulnerability

The repository has no disclosure policy yet. `SECURITY.md`, through GitHub's private vulnerability reporting, is planned,
awaiting its owner's ruling: see [STATUS](STATUS.md#packaging-and-docs).
