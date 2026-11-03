# Architecture

This is the design of record. When code and this page disagree, one of them has a bug. Status lives in
[STATUS.md](STATUS.md); decisions and their alternatives live in [adr/](adr/); upstream facts live in
[compatibility.md](compatibility.md).

## 1. The whole thing in one paragraph

A **session** is a folder holding a journal. Every fact about the work is an immutable event on a named
stream. The only way in is an **operation**: a synchronous function that checks its caller and appends
events in one transaction. The only way out is a **daemon**: a restartable task that reads views, touches
the world, and reports back through an operation. Everything else is derived. Views are folds you can drop.
Inboxes, topics, queues, boards and waits are ordinary streams with ordinary operations. Harnesses do the
thinking; a driver presents each one through seven methods. The terminal, the browser, your Python script
and the agents' own tools are all clients of the same operations, so closing any of them changes nothing.

```text
             clients: TUI · SwarmChat · Python · CLI · agent tools (MCP, ph)
                                      │  operations
                                      ▼
   ┌──────────────── session runtime (one process per live session) ────────────┐
   │  writer thread:  authorize → op → events → folds → COMMIT → ack            │
   │  journal.sqlite  (events are truth; everything else in it is a fold)       │
   │  daemons:        host · courier · clock · effects      (level-triggered)   │
   └───────┬──────────────────────┬─────────────────────────┬───────────────────┘
           │ control plane        │ tool plane              │ model plane
           ▼ native RPC, ACP      ▼ MCP, ph                 ▼ the harness's own auth,
        Claude Code, Codex,     coordination operations       or the Platoon gateway
        pi, OpenHands, …        as tools                      for exact training calls
```

The three planes are independent. A harness can be controlled without showing it our tools; our tools can
be visible without exact model calls; exact model calls imply neither. `Operational`, `Observable` and
`Trainable` are computed per agent from what was verified, never declared (§9.4).

## 2. Vocabulary

Nine everyday words. No other noun may reach a user who is not writing an extension or training.

| Word | Meaning |
|---|---|
| **Session** | The durable thing you start, attach to, resume and export: one folder, one journal. `run` is only a verb. |
| **Agent** | One participant with its own identity and history, driven through one harness. Retiring it leaves the live team, never the journal. |
| **Role** | A template for agents: harness, model, instructions, workspace, what it may spawn. |
| **Harness** | An existing agent program such as `claude`, `codex` or `pi`. |
| **Turn** | One stretch of harness work, from the input that started it until the harness stops. The unit of waking, cost and exposure. |
| **Channel** | A durable named place with readers and writers, of one kind: `inbox`, `topic`, `queue` or `board`. |
| **Team** | Roles plus a topology, as a file or a Python object. It says what may happen, never what happens next. |
| **Topology** | Who may reach whom, as grants over relations such as `parent` and `children` that stay true as agents come and go. |
| **Approval** | A durable decision a harness is waiting on, resolved once by a human or a stated policy. |

For extension and training authors:

| Word | Meaning |
|---|---|
| **Journal** | The append-only ordered events of a session; the only truth. |
| **Event** | One immutable fact with a global `seq`, on exactly one stream. |
| **Stream** | A named, gapless, versioned sequence of events: the unit of order and concurrency control. |
| **Operation (op)** | A named, typed, synchronous function; the only way to change a session. |
| **Command** | One invocation of an op, with an idempotency key. |
| **View** | A table folded from events: droppable, and rebuilt to identical contents. |
| **Effect** | A tracked request to touch the world: requested, started, then finished, failed or uncertain; or cancelled before it starts. |
| **Daemon** | A supervised task that performs effects or reacts to views, keeping nothing that must survive a restart. |
| **Principal** | An authenticated actor (`agent`, `human`, `program`, `judge`, `runtime`), resolved from a credential. A name is unique across kinds and safe as a path part. |
| **Grant** | `(who, ops, on)`, the only authorization input for an op. Absence means deny. |
| **Driver** | The adapter that presents one harness session to the runtime. |
| **Episode** | An explicitly opened span of a session with one outcome. Only events inside one can become training data. |
| **Evidence** | Why a dependency is believed: observed, declared, judged or validated. |
| **Annotation** | A versioned statement about the record (reward, judgment, credit), stored beside the journal, never in it. |

### Naming law

Checked by a test and by the kernel. At load, an op may not be past tense and its namespace must equal its extension's name. At
`emit`, an event must be past tense; it may carry another extension's namespace, because extensions are trusted code (§15).
`effect.uncertain` is the one event named for a state.

- Ops are imperative (`task.claim`); events are past tense (`task.claimed`).
- The extension's name is the namespace. Collisions are refused at load, of the names ops take as tools too. There is no `x.` prefix.
- No abbreviations in a public op table: `message.*`, `channel.*`.
- `call` means a model call and nothing else. An `Operation` is a definition; a `Command` is one invocation.
- `settled` is a session state. A turn `ended`.
- `interrupt` stops a turn. `cancel` ends an agent. `session.close` drains; `session.cancel` stops now.
- `timeout` is a duration. `deadline` is a time.
- `@agent`, `#channel` and `+group` are the one address grammar. A leading sigil is an address; infix `@` and
  `#` are version and range: `board/notes/spec@3#L10-40` is a **ref**, and a ref names immutable content.
- A driver's name is the command you type: `claude`, not `claude-code`.

## 3. Laws

Each law is a sentence, and each has a test of the same name.

1. **The journal is the only truth.** Triggers abort `UPDATE`, `DELETE` and a replacing `INSERT` on `events`.
   Dropping every view and refolding gives identical contents.
2. **Folds are pure.** A fold sees its own tables and one event: no clock, no network, no other view, no emit.
3. **Operations cannot wait on the world.** An op is synchronous, does no I/O, and runs inside one transaction.
4. **Ack follows commit.** A caller learns a result only after the fsync that made it durable.
5. **Replay executes nothing.** Work starts only from `effect.requested` rows and live views. Refolding runs no
   effect, and rendering history to a UI never re-executes a tool.
6. **Identity comes from a credential.** No tool schema has a field claiming the caller's identity, role, session or
   policy. Undeclared arguments are refused and journaled, because a spoof attempt is evidence.
7. **References point backward.** `cause`, `based_on` and every ref in an event resolve to a lower `seq`. So the
   dependency graph is acyclic by construction. `seq` is the order the journal learned things; dependency comes
   only from references. A relation learned later is a new event citing both sides.
8. **Observers cost nothing.** A follower is a cursor, not a queue. No client can slow the writer or hold memory
   in the runtime.
9. **Agent reads are evidence; human reads are nothing.** An agent's read commits what was offered. A human
   watching writes no event and moves no agent cursor.
10. **Absence stays honest.** Unknown is not zero, not false and not empty. Rewards are `float | None`, usage has
    a measurement label, tool visibility has three values, and exposure answers `Seen`, `NotSeen` or `Unknown`.
11. **Nothing has a private API.** Core primitives, presets, patterns and third-party extensions use the same
    public kernel names, enforced by an AST test. If a preset cannot do something, the kernel is wrong.
12. **Nothing claims mid-generation.** No path interrupts a response being generated, and no text may say so.

## 4. Session folder and process model

```text
<root>/sessions/fix-auth/
  journal.sqlite      events and folds; WAL, synchronous=FULL
  annotations.sqlite  rewards, judgments, credit: no agent-reachable read opens it
  marks.sqlite        per-human unread positions: neither evidence nor view; losing it loses badges
  blobs/ab/<sha256>   bodies too large for the journal file
  manifest.json       resolved team, how it was started, component and protocol versions, topology hash; no secrets
  runtime.json        pid, start time, socket path, incarnation: left by a crash, so only `lock` proves it true
  runtime.log         what a detached runtime said
  owner.token         0600: a control credential, fresh each incarnation
  view.token          0600: a view credential, which reads and never writes
  lock                flock: held by the one live runtime
  agents/<id>/        per-agent state: proc.json, stderr.log, native home, workspace pointer, bin/ph
```

- **Root.** `$PLATOON_HARNESS_HOME`, else `$XDG_STATE_HOME/platoon-harness`. If that is on a network filesystem,
  the default falls back to `/var/tmp/platoon-harness-$UID`, with a one-line notice and a `doctor` entry. An
  explicitly chosen root on a network filesystem is refused with exit 78. Only live writers are refused: a closed
  session is a portable artifact (§5.8). A root to write in must be this user's, and writable by nobody else, since a manifest in it
  names what a resume runs. The fallback and `sessions/` are made 0700, and a chosen root is left as it is.
- **A session's folder** is built aside and renamed into place with its manifest in it, so a name is claimed whole or not at all, and
  a crash burns none.
- **Sockets** live at `<runtime dir>/<short hash>.sock` in a 0700 directory from `XDG_RUNTIME_DIR` or a short per-user fallback,
  never inside the session folder: a Python `bind` allows 107 bytes on Linux and 103 on macOS, and a deep folder exceeds that.
  The hash is of the folder, not the session id, since a copy of a closed session keeps its journal and must not take the socket of
  the one still running. The path is checked before binding, abstract names are not used, and `runtime.json` holds the pointer. A
  directory that is not this user's own is refused, one that is gets tightened, and one that cannot be used falls through to the next.
- **One runtime per live session.** It owns `lock` and binds the control socket in every mode. Usually that is one process; a
  Platoon rollout worker hosts several in one. There is no
  central daemon or registry: listing sessions scans folders, and `flock` is the liveness check.

| Mode | Who keeps the process alive | Leaving ends the agents? |
|---|---|---|
| `Session.start(team)` in your script, `platoon-harness run` | You | Yes: documented context-manager shutdown |
| The TUI | A detached runtime it starts, the way tmux starts its server | No: `^D` detaches |
| `platoon-harness serve` | A supervisor | No |

`Session.attach(name)` gives the same class as a guest in every mode, so a script's session and a training rollout
can both be watched. Leaving only disconnects.

- **Attach never has side effects.** With no live runtime, `attach` gives read-only history. Only `resume` restarts
  anything, because restarting can spend money.
- **One path up.** `Session.start` checks the team and writes the manifest before any cost, and that folder is all a runtime
  needs. A runtime is one path for a new session and a resumed one: `Kernel.recover()`, then open, whose steps run under fixed keys
  and so answer from the journal when they have already happened, then per agent reap, resume and reconcile. A crash part of the way
  through opening is finished by the next runtime. A resume under an SDK or component version other than the manifest's is labelled
  on `runtime.started`, in its `gist` and whole in its `drift`, and never refused, since a session survives an upgrade.
- **Detached.** `python -m platoon_harness.runtime <folder>` leads its own session with its log in the folder. `Session.start(team,
  detach=True)` starts one and gives a guest, from the folder and with `-P`, so a module in the caller's working directory cannot stand
  in for one it imports. It takes no authority or clock from its parent, since it is another process. It exits
  on `SIGTERM`, which runs the shutdown below, and once a session that has stopped accepting work has drained. Signal handlers
  live in that entry point and nowhere else, so that several runtimes can share a process.
- **Shutdown contract of an owner:** interrupt turns, wait `grace`, end the process trees it started, release
  reservations, append `session.stopped`, keep the folder resumable. To release is to hand back what will not happen now: a turn
  still open ends, which reconciles its reservation and is told to its agent on resume (§7), and a handover that never started fails,
  which queues its entries again. A spawn
  still to come keeps its reservation, since the next runtime goes on with it. The next `runtime.started` reopens a session stopped
  while open; one that was closing or cancelled stays so, and its harnesses are not resumed, because nothing new may start. A journal
  that stops committing holds this up by at most `grace` and a second, a driver that breaks in `stop` holds up nothing, and the process
  trees end whether or not anything commits.

## 5. Kernel

```python
class Kernel:
    def open(path, *, clock=None, extensions=(), read_only=False) -> Kernel: ...
    async def submit(self, principal, op, args, *, key=None, expected_version=None, native=None) -> Outcome: ...
    def query(self, principal, op, args) -> Outcome: ...      # a read-only op on a read connection
    def read(self, principal, *, after, match=None, limit=512) -> Page: ...  # never for agent principals
    async def follow(self, principal, *, after, match=None) -> AsyncIterator[Page]: ...
    def deltas(self, agent, *, after=None) -> AsyncIterator[Delta]: ...  # lossy live text; never journaled
    def close(self) -> None: ...
```

The kernel knows streams, principals, grants and effects. It does not know what a message, board, task or harness
is; those are primitives, written as `Extension` values on the same contract a third party uses. Its own ops, views and
daemons load the same way, so `effect`, `timer`, `principal`, `grant`, `body`, `runtime`, `op` and `ops` are taken names.

`submit` and `query` return an `Outcome`, whose `refusal` says why nothing happened; they never raise one. `read` and
`follow`, which are not ops, raise `Refused`. `native` holds a backend's ids for one command, stamped on its events as evidence and
read by nothing. Around these sit `authenticate(token)`, `put_body(bytes)`, `get_body(hash, limit=None)`,
`erase_body(hash)`, `recover(*drift)`, `rebuild(view)`, `rebuild_all()`, `supervise()`, `head`, `changed(after)`,
`push_delta(agent, text)`, `session_id`, `closed` and `read_only`, plus what a daemon reaches for: `runtime`, `clock` and `ops`.
`is_held(folder)` says whether a runtime holds a folder's lock, which is how anyone tells a session is live, and `first(work, *rivals)`
races awaitables and drops what lost, which is how anything here sleeps on two things.

### 5.1 One write

`submit → authorize → op → emit → fold → commit → pulse → ack.` Timers, driver reports and effect results enter
through `submit` too, so no second path exists.

1. **Ingress.** The transport maps its credential to a `Principal`. Decoding is strict: nothing is coerced, and an undeclared
   field or an argument that is not JSON is refused and journaled. An op name or key that is not printable, or is over 256
   characters, could not be journaled even as a refusal, so it is refused here with no event. Bodies are written to the content
   store first, so a retry or an orphan is harmless.
2. **Queue.** The command joins a bounded queue drained by the session's one **writer thread**, never the event loop,
   so an fsync cannot stall a client or a Platoon rollout worker. A full queue returns `busy{retry_after}`. `runtime`
   principals have reserved capacity, so evidence is never shed to admit a client.
3. **Transaction.** `BEGIN IMMEDIATE`, then up to 64 commands, each in a `SAVEPOINT`:
   - dedupe on `(actor, key)`, through an index over `events`: same args hash returns the first outcome; different hash
     refuses `key_reused`;
   - `authorize(principal, op, op.on(args))`;
   - check `expected_version` if given;
   - run the op, which may read views and emit events and effects, or refuse;
   - each `emit` inserts into `events` and runs folds inline.

   A refusal rolls back the savepoint, then commits one `op.refused` event, so a retry gets the same answer and a
   denial stays evidence. A command always ends on one event carrying its `outcome`: the last event an op emits is
   folded at once but held back from `events` until the op returns, and an op that emits nothing ends on `op.completed`.
   `op.refused` and `op.completed` go on the stream `commands/<actor>`, so a failed attempt moves no object's version.

   An op that crashes is refused `unavailable` and journaled without its key: a crash answers nothing, so a retry runs. A fold
   failure fails its command even if the op catches it. If `op.refused` itself cannot be written, the command gets
   `unavailable`, journals nothing, and may retry. A refusal's `object` is cut to 256 characters and its `detail` to 512, so
   caller text cannot grow the journal.
4. **Commit.** One fsync per batch. Only then does the head pulse and are futures resolved, so whoever is acked finds their
   write under `head`. If the commit fails, the batch's outcome is unknown, since its bytes may have landed all the same: each command
   gets `unavailable` and should retry under its key, which answers from the journal if they did.

### 5.2 Tables

| Table | Kind | Why it cannot be removed |
|---|---|---|
| `events` | truth | The journal. `UNIQUE(stream, version)` is optimistic concurrency. An index over `outcome` gives a retry the first answer, including a refusal. |
| `bodies` | content | `sha256 → bytes`, inline up to 64 KiB; a larger body has a row and a file in `blobs/`. Separate from `events` so redaction can erase a body while the event and its hash survive. |
| `meta` | fixed | Schema version, session id, creation time. Written once. |
| `v_principals(id, kind, role, parent, path, state, token_hash, scopes)` | fold | `authorize` needs the live graph in-transaction. `path`, a chain of ids, makes `descendants` a prefix test. |
| `v_grants(who, ops, on, rev)` | fold | The compiled topology. |
| `v_effects(id, kind, state, on_uncertain, timeout, priority, agent, attempts, data)` | fold | The outbox and the input to recovery. |
| `v_timers(key, due, op, args, seq)` | fold | The clock daemon's work, which must survive a restart. |
| `v_stamps(scope, value)` | fold | The open turn per agent and the open episode, read at every `emit`. |
| `v_tombstones(sha256, seq)` | fold | Reads of a redacted body stop at commit, before its bytes are gone. |
| `v_folds(view, version, high_water)` | fold bookkeeping | Lets one view rebuild alone, and stops a toggled extension leaving a stale view. |

Everything else belongs to a primitive. Group generation, topology revision, board version and context version need
no counters: each is a stream version, which `txn.view(Stamps).version_of(stream)` reads. A fence is the `seq` of the claim event.
`Stamps` also reads a stream's events and the head, so an op can check history inside its own transaction, as `wait` does.

### 5.3 The envelope

```python
class Event(BaseModel, frozen=True):
    v: int                           # payload version for this type; old payloads upcast on read
    seq: int                         # the cursor; commit order
    stream: str
    version: int                     # gapless per stream
    type: str                        # "task.claimed"; unknown types survive export and replay
    actor: str                       # authenticated: "agent:worker-1", "human:ada", "runtime", "program:map_reduce"
    agent: str | None                # the agent this is about; defaults to the acting agent
    turn: str | None
    context_version: int | None      # the agent's context version at commit; every agent event has one
    episode: str | None
    topology_rev: int
    correlation: str | None          # what larger piece of work this belongs to
    cause: tuple[int, ...]           # seqs this directly followed from
    based_on: tuple[str, ...]        # declared refs, as claimed
    native: Mapping[str, str]        # backend ids, with source and harness version
    model: ModelRef | None           # policy, version, call_id, tool_call_id, token span: only when real
    wall_time: float                 # for humans; never orders anything
    gist: str                        # at most 280 chars; what any client can show for any event
    data: Any                        # JSON, at most 16 KiB; larger content goes by body hash
    outcome: Outcome | None          # on a command's last event: op, key, args_hash, result or refusal
```

The session id is a constant of the file and is added only at export. An op cannot pass `seq`, `version`, `actor`,
`wall_time` or the stamps. Its one say in `actor` is `runtime=True`, for what the runtime posts inside someone else's command,
such as the monitor; it can name nobody else. The kernel takes the rest from cheap state at `emit`:

- `context_version` is the version of the stream `context/<agent>`, and `topology_rev` the version of the stream `topology`.
- `turn` is open from `turn.started{turn}` through `turn.ended` or `turn.lost`, per agent, and those boundary events carry it.
- `episode` is open from `episode.opened{episode}` through `episode.closed`. A session has one open at a time, so `emit`
  refuses a second `conflict`. A boundary event that does not name what it opens is `invalid`.

`refs` passed to `emit` name the refs inside `data`. `cause` and `based_on` and these all resolve to a lower `seq` or `emit`
refuses. A ref is `stream@version`, or `sha256:<hash>` for a body, either with an optional `#range`. `cause`, `based_on`, `native` and
`correlation` can hold caller text, so together they are held to 16 KiB as well, and a stream name to 512 characters.

### 5.4 Effects

An op never touches the world. `txn.effect(kind, data, on_uncertain=..., timeout=..., priority=..., agent=..., after=...)` appends
`effect.requested` and returns the effect's id, which is that event's `seq`. A daemon commits `effect.start`, which returns the
attempt, acts, then commits `effect.finish` or `effect.fail` naming that attempt. While a newer attempt runs, a late report from
an older one is refused `conflict`. Daemons read `v_effects`, so they are level-triggered and hold no durable position. One
agent's effects start in order. A `priority` above zero starts first and ignores that order. With `after`, an effect starts only
once that one has finished, so a failed `admit` stops its `launch`. An op may emit `effect.cancelled` for one still requested.

| Kind | Key sent outward | After a crash |
|---|---|---|
| `launch` | Native session id; pid and start time written by the launcher **before exec** | Kill the recorded group if still ours; resume if the role allows; else agent `lost` with a gap |
| `deliver` | Input id (`uuid`, `clientUserMessageId`) | `reconcile` if capable, else redeliver: at-least-once, with the id visible for dedupe. One that landed but began no turn is redelivered too, since a harness killed before its turn will not begin one now |
| `answer` | Approval id | `reconcile`, else `uncertain` in attention. Success is read from the harness's item event, never inferred. It bypasses per-agent ordering, since a harness blocked on an approval cannot reach the boundary a queued delivery waits for |
| `admit` | None: Platoon mint has no idempotency | Never retried. Spawn fails, reservation released, orphan recorded as a gap. One that finished is not retried either: its token went with the runtime, so `launch` asks the authority again, as a resume |
| `workspace` | Path and branch | Inspect, adopt or fail. Never discard uncommitted work |
| `interrupt`, `stop` | None | Repeat. These bypass per-agent ordering, so Esc works while a delivery hangs, and an interrupt fails a handover under way, which queues it again |
| `erase` | None | Repeat: erasing twice is harmless |

- **Live timeouts.** An effect stuck in `started` past its `timeout` becomes `effect.uncertain` without a crash. `effect.start`
  sets a timer for it, and `effect.finish` clears that timer.
- **Recovery** is one function: take `lock`, write `runtime.started`, then per agent **reap, resume,
  reconcile, dispatch**. Every `started` row becomes `effect.uncertain` and its declared policy applies: `retry`,
  `reconcile` or `surface`. `reconcile` needs a live link, so it runs after resume, and it is `unknown` when resume is
  unavailable. A turn in flight becomes `turn.lost` plus a gap, because its tool effects are unknown and never re-run.
  `retry` appends `effect.retried`, which returns the effect to `requested`. `reconcile` and `surface` stay `uncertain` until
  `effect.finish` or `effect.fail`, or until a person says with `effect.settle`, which the row in `attention` offers.
  `Kernel.recover()` does the journal's part of this, including `turn.lost`, whose data names the gap `crash_window`; the
  incarnation is the version of `runtime.started` on the stream `runtime`.
- **Tool side effects inside a harness are observed, not ours.** We do not perform them, so we do not retry them.
- **A kind of an extension's own.** The host starts only the kinds in this table, and recovery settles only those. An extension that
  requests another brings the daemon that performs it, and that daemon settles its rows, after a crash and past a `timeout` alike:
  `effect.list` names what is `uncertain`, and `effect.finish` or `effect.fail` settles it. `retry` is the one policy that acts by
  itself. Otherwise a row nobody settles waits in `attention`, for a person to say with `effect.settle`.
- **The host** is the daemon that performs these kinds, but for `erase`, which the kernel's own eraser does, on public names. It reads `effect.ready`, level-triggered, and gives each
  effect its own task, so a hung `deliver` holds up nothing with a priority. Driver links live on the `Host` object and not in the
  daemon, so a restarted daemon loses none, and a task it started finishes. A delivery waits while a takeover holds its agent. Each
  agent's reports are heard in order, one at a time, and a driver waits for its turn: `Process`'s own queue is what keeps a pipe
  draining. Every report is masked on the way in, whichever driver said it. Live text is masked as one stream, since a secret can
  straddle two deltas, so its tail waits for the next delta or any other report. Observed activity renews an agent's leases past half their
  time, up to `lease_max`, and it asks `lease.due` first, so idle activity journals nothing. A harness that never says it is ready within
  a minute fails its spawn, as does one that exits first or names a model other than the one pinned. A report that cannot be taken, or a
  driver that raises anything but `DriverError`, ends in `exited`: nothing that goes wrong there is a silent hang. A report the journal
  refuses leaves `native` plus a gap first, unless its agent has ended, when it is no loss. An approval the journal refuses is answered
  `deny`, since a harness is blocked on it. A `deliver` that wakes an agent stays open until the turn begins, so `waking` always has
  an effect behind it and recovery needs no second path: past a minute, or at an interrupt, it fails, and its entries are queued again.
  What a driver wrote stays in the pipe of a harness that has stopped reading, and lands if it reads again, so that is at-least-once. An
  `interrupt` or an `answer` that does not come back in a minute fails too, which leaves the turn open and the approval unanswered, and
  only a wall limit ends a harness that stays that way.
- **Recovery runs per agent at once,** and only for a session still open. A resumed harness gets a fresh credential through
  `Authority.admit(resumed=True)` and commits `agent.start` as `resumed`, which leaves the agent as it stood. `agent.retell` then tells
  it what it cannot know, a goal that never began or a turn that was cut off (§7). With no native id, no
  `resume`, or a failure to resume, its agent is `lost` with the gap `crash_window`, through the normal ended transition, and that is
  the one agent's: a driver that raises anything, or a group that outlives `SIGKILL`, stops no other. A `reconcile` that does not answer
  in 10 s, or fails, is `unknown`, and a stop asked during recovery cuts it short. A group `reap` cannot prove ours is left alone and
  named in a `native` event plus a gap, even for an agent that has ended. `reap` runs after every stop too, because a wire program's own
  harness leads a group of its own.

**Timers.** A `timer.set` event sets one: `{due, op, args, key}`, where `key` names one firing and `op` and `key` are at most 256
characters. The clock daemon sleeps on the injected `Clock` until the next is due, submits `op` as `runtime` under `key`, then
submits `timer.clear`. A crash between the two fires again under the same key, which answers from the journal, so the op runs once.
A refused firing is still cleared and stays journaled. A firing that left no event, because the writer was busy or its commit
failed, stays set and is tried again. Any op can emit `timer.set`, and `timer.cleared` to cancel.

### 5.5 Views

A `View` is a class with a schema, `@fold` methods, and typed query methods. Core and extension views are identical
in kind. Other code reads a view through `txn.view(Tasks).open_in(queue)`, never through its SQL, so a table layout is
not an API. Its tables are named `v_<name>`, or start with that and `_`, and no two views share one. A version bump drops and
refolds that view, and so does finding its high-water mark behind the journal, which is what a toggled extension leaves. A change to
a view's table or to what its folds write bumps its version, or an older session's table stands and its resume fails. A test pins each
schema to its version. Folds
ignore unknown types, which is why unknown events survive. `@fold("*")` sees every event, for a view that cannot name what it
counts, as `Waits` cannot. CI compares live views to a rebuild after every scenario.

A rebuild runs under an SQLite authorizer limited to the view's own tables, so a fold that reaches out fails loudly. A fold
never sees `outcome`, which does not exist yet when a live fold runs.

**One event, many folds** is how a transition stays atomic. `agent.ended` is one event. In that one transaction `Waits`
cancels the agent's waits, `Budgets` returns its reservation, `Tasks` frees its leases, `Deliveries` marks queued
input undeliverable, `Approvals` closes pending requests as moot, and `Principals` revokes the token. The op adds one
message to the monitoring agent's inbox, cancels the effects the agent had still to start, and keeps its final report on the event,
so a root agent's report stays in the journal and, unheard, in attention. A failed handover has the same shape: `effect.failed` on a
`deliver` queues its entries again in `Deliveries`, returns the agent to `idle` in `Agents`, and gives a wake's reservation back in
`Budgets`; a failed steer leaves the running turn its own. `turn.ended`, short of `stopped`, `turn.lost` and `agent.resumed` do that
for what a harness took and never landed, in `Deliveries` alone.

### 5.6 Readers

A subscription is repeated `read(after, match, limit)` plus a shared head pulse. One writer means `seq` order is commit
order, so a cursor cannot skip a late commit. Each page is its own short read transaction, so a slow client cannot pin
the WAL. Catch-up and live are one loop. `match` is a glob over stream names, a filtered page scans at most 4,096 events,
and `Page.cursor` is where to continue, so a page can be empty with more to come.

Followers at the tail share one read per pulse into a bounded tail and take a slice; a lagging follower pages by SQL through
a small pool of idle connections. A private read per follower does not keep up at 100 followers, and slows the writer. A reader
takes one short transaction per page and never holds a cursor, because a half-read cursor pins the WAL while `in_transaction`
says false. The checkpoint thread alarms when unbackfilled frames pass 16,000.

Clients may rely on per-stream order only. Agents never get `read`: their reads are ops, checked per page against
grants. Runtime-only ops are excluded by principal kind, so no grant glob can reach them.

`read` and `follow` are not ops, so they take no grant: the runtime and any live principal that is not an agent may read the
whole journal. A page holding a `principal.revoked` goes by SQL, so a follower is refused at its own revocation. `limit` is 1 to
4,096.

### 5.7 Backpressure

| Pressure | Answer |
|---|---|
| Writers | 32 inflight per principal, 1,024 per session, then `busy{retry_after}`, which is not journaled. `runtime` has no per-principal limit and 256 more |
| Payloads | Op names and keys 256 chars, stream names 512, `gist` 280, `data` 16 KiB, bodies 64 KiB inline, larger in `blobs/`, every list a command returns paged |
| Readers | They pull, so a slow client costs only its own lag |
| Live text | One 256-frame ring per agent, each frame cut at 64 KiB; overflow drops frames with a `lag` marker. The final `item` is authoritative |
| Harness output | Pipes always drain. A driver that stalls its harness's stdout stalls the harness. Reports buffer in a bounded queue; a quota breach stops that agent with a gap |
| Inbox | A depth cap refuses `queue_full` with a `full` receipt, journaled, never a silent drop |
| Topic | Writers never block. A lagging reader gets a capped digest and a gap notice |
| Queue | `max_inflight` per reader, default 1 |

### 5.8 Durability and portability

Pragmas: `journal_mode=WAL`, `synchronous=FULL`, `cache_size=-8192`, `mmap_size=0`, `temp_store=MEMORY`,
`wal_autocheckpoint=16000`, `journal_size_limit=67108864`, `secure_delete=ON`, plus `fullfsync=ON` and `checkpoint_fullfsync=ON`
on macOS. Blob file and directory are fsynced before citation, on a retry too. Erasing a body zeroes its pages and then truncates
the WAL, refusing `busy` while a reader holds it, so an erase effect stays open until the bytes are gone. Checkpoints stay off the
commit path: a background thread runs `PASSIVE` every second on its own connection, with `wal_autocheckpoint` as the writer's hard
cap, because the thread alone lets the WAL grow without bound at saturation. A rebuild runs with `FULL` in one transaction; `OFF` saves little and risks the file that holds the journal.
A client that misses an ack retries under the same key, since a commit without an ack is expected.

| Storage | An ack means | Status |
|---|---|---|
| Linux, local disk | Synced. Survives a process crash, and power loss if the device honors flush | Process crash tested, power loss not |
| macOS, local disk | The same, only because `fullfsync` is on | Not yet measured |
| tmpfs | Survives a process crash, not a reboot. Warned | |
| Network filesystem | Refused for live writers, on guarantee rather than speed: SQLite does not support WAL across hosts | |
| WSL | Linux rules inside the distro filesystem; `/mnt/c` is 9p and refused | Not run |

A closed session is portable: `session.close` checkpoints the WAL to empty, so the folder can be copied anywhere
and opened read-only with `immutable=1`. A reader holding the WAL stops that, and the close logs it. Estimators and exports use
this form; a live journal is never read over a network filesystem. `Kernel.open(path, read_only=True)` picks between the two by
whether `lock` is held or the WAL has content. A read-only kernel folds nothing, so a query refuses `unavailable` if a view it
holds is behind the journal. `immutable=1` tells SQLite not to look for change, so a reader of a closed journal looks itself, and
refuses `unavailable` once a writer has touched the file.

`filesystem(path)` says what holds a path, from `statfs(2)` so that links and bind mounts resolve, and from the mount table by
device for a FUSE subtype. A live journal is refused on a network filesystem with the name of a local directory to use, and
warned on tmpfs or a type not known to be local.

## 6. Operations

```python
class Claim(Args):                 # Args refuses undeclared fields and coerces nothing
    queue: str
    task: str | None = None

@op("task.claim", on=lambda a: f"queue/{a.queue}", tool=True)
def claim(txn: Txn, a: Claim) -> Lease:
    """Claim the next open task. First claim wins; a loss names the owner. Keep working: the runtime renews your
    lease while you are active. Refused with `queue_empty` when nothing is open."""
    ...
```

`Txn` is what an op receives, and all an op receives: `me`, `now`, `view`, `emit`, `effect`. An op refuses by raising `Refused`,
and checks a second object with `txn.view(Grants).authorize(txn.me, op, stream)`. `permits` asks the same question without
refusing, and `Principals.select(me, relation)` lists who stands in a relation.

`Op` holds `name`, `fn`, `input`, `on`, `query`, `exposes`, `tool` and `runtime`. `on` gives the object: the stream that
grants are matched against and `expected_version` is checked on, or `session` when an op has none, or `None` when the op checks
its several objects itself, as `wait` does. `query` keeps an op out of
history. `exposes` marks a read that is a command for agents and a query for everyone else; its body checks `txn.me.kind`,
because a query cannot emit. An op is at most one of `query` and `exposes`. `runtime` is the runtime-only marker. The runtime
principal takes no grant.

`op()` refuses at definition an input that is not `Args` or lets undeclared fields through, a `tool` whose schema claims the
caller's identity by name or alias, at any depth and in the usual spellings (law 6), and a `tool` with no description. That scan
is a denylist, so it catches mistakes; what stops a spoof is that identity comes from a credential.

One definition reaches every surface.

| Surface | Derivation |
|---|---|
| Python | `session.submit("task.claim", ...)` returns the `Outcome`; typed facade methods are thin wrappers that return the result and raise `Refused`, checked against the registry by a test. Boards and queues use the tool's name, `session.task_claim`, since `session.fail` alone reads as failing the session. An agent-only op has no method |
| MCP | `tools/list` is the `tool=True` ops granted to the token's role; `additionalProperties: false`; `readOnlyHint` set honestly, never enforced: true only for a `query`, since an agent's read moves its cursor |
| `ph` | One stdlib file on the agent's `PATH` only: `ph task.claim --queue tasks`. It builds argv and help from `tools/list`, which is `ops.list` for its token, and refuses nothing itself |
| CLI | `platoon-harness tasks claim ...` for curated groups, `platoon-harness op <name>` for any op, flags built from the schema |
| Web | `POST /x/command {op, args, key, expected_version}` |
| TUI | Palette entries and generated forms; buttons come from `actions[]`; disabled entries carry `authorize`'s reason |

**The tool-plane idempotency key** is a hash of `(anchor, op, canonical args)`, where the anchor is the client's id when it sends
one (`claudecode/toolUseId`, Codex `callId`) and the turn otherwise. The op and args stay in the key because one Codex script can
make several calls under shared ids. Either way a harness retry after a timeout is one logical operation. So a client with no id
cannot tell the server that an identical call in one turn is meant, and it gets the first answer, labelled as a repeat. `ph` and
the stdio shim therefore send a fresh `platoon-harness/callId` per call, kept under that name so it cannot pass for a harness's id:
a second `task.claim` on a pipe is a second claim. Outside a turn, a call with no id has no key. A key lasts as long as its anchor, so
a call that committed and lost its ack in a crash can run again if a model reissues it after a resume, under a new turn and a new id.
That is what the cut-off notice's check is for (§7).

**Commands and queries.** A query enters no history and reads a read connection. A command is journaled and returns a
result. An agent's read of content is a command, because it records exposure. A human's read of the same content is a
query. A query that decoding refuses leaves no event, so the tool plane submits an agent's `invalid` query again: `submit` refuses
it the same way and journals it, which keeps law 6.

**Refusals are data:** `{code, op, object, reachable?, retry_after?, detail}`. Codes: `not_permitted invalid not_found
conflict stale_fence queue_full queue_empty over_budget unsupported busy unavailable key_reused undeliverable`.
`over_budget` is policy; `unavailable` is infrastructure. Each tool description ends with what a refusal means and what
to do next.

| Area | Commands | Queries |
|---|---|---|
| Session | `session.close` `session.cancel` `topology.patch` `episode.open` `episode.close` `budget.set` | `session.status` `session.ending` `session.manifest` `topology.show` `ops.list` `budget.status` |
| Agents | `agent.spawn` `agent.finish` `agent.interrupt` `agent.cancel` `agent.retire` `agent.takeover` `agent.release` | `agent.list` `agent.status` `peers` |
| Messages | `message.send` `message.read` `channel.create` | `channel.list` |
| Board | `board.post` `board.revise` `board.get` `board.query` | |
| Queue | `task.add` `task.claim` `task.renew` `task.release` `task.complete` `task.fail` `task.list` | |
| Wait | `wait` `wait.cancel` | `wait.progress` |
| Humans | `approval.resolve` `effect.settle` | `attention.list` `view.watch` |
| Evidence | `blob.get` | `lineage` `exposure` |
| Evidence, kernel | `body.tombstone` | |
| Runtime only | `agent.start` `agent.report` `agent.conclude` `agent.retell` `delivery.offer` `delivery.confirm` `blob.offer` `approval.request` `effect.start` `effect.finish` `effect.fail` `effect.expire` `timer.clear` `runtime.start` `budget.lapse` `principal.add` `principal.issue` `principal.revoke` `grant.add` `grant.remove` `wait.release` `lease.expire` `session.open` `session.stop` `group.define` | `agent.records` `effect.ready` `effect.list` `lease.due` `timer.next` `delivery.ready` `delivery.pending` |

An agent's `board.get`, `board.query`, `message.read`, `task.list` and `blob.get` are commands; for a human or a program they
run as queries and write nothing. `task.claim` writes a lease, so it is a command for everyone. `reply` is `send(reply_to=)`.
Broadcast is `send("+group")`. A join and a wait for any are `wait` with `mode`. Ack is `read(after=n)` or `wait(after=n)`. An op that
requires `expected_version`, as `board.revise` and `approval.resolve` do, takes it as an argument, so a tool call can carry it. A
body enters through `Kernel.put_body` before the op cites it, and an op reads only bodies held in the journal: one in `blobs/`
comes back as its hash beside a null `text`, for the surface to fetch, and `blob.offer` records what the surface showed. A hash is
a capability: `blob.get` checks no stream, so whoever holds a hash may read that body. A ref names where content is, and that it exists is no secret: `based_on` is checked to exist and nothing more.

### Library tier

`platoon_harness.patterns` uses the public API only: `scatter`, `gather`, `reduce`, `barrier`, `latch`, `semaphore`,
`lock`, `request`, `vote`, `supervisor`, `population`, `map_reduce`, `verifier_generator`. These are compositions, never
scheduler modes.

An episode **program** is an async function holding a `program` principal, so control flow never enters config.

## 7. Primitive semantics

Each statement here is a promise with a test.

### Inboxes and topics

- **`inbox`**: one per agent (`inbox/<id>`). **`topic`**: one stream per channel (`channel/<name>`); `+group` has an
  implicit topic, `channel/+<name>`. These streams hold entries and nothing else, so a version numbers an entry.
- **Order.** Total per stream. Nothing is promised across streams.
- **Delivery.** At-least-once to the driver, deduped by event id. Delivery states are `offered` (the runtime handed it
  over), `delivered` (the driver confirmed injection; this is observed exposure), `acked` (the agent's next read or
  wait moved past it). None means understood. A handover that fails is queued again and offered under a new input, even past a
  newer offer: at-least-once allows the repeat, and the event id dedupes it. The next try waits twice as long as the last, from one
  second. Six in a row lose an agent out of a turn, with the reason; a working agent keeps its turn, and what is queued waits for
  its end. What a harness took and never landed is queued again the same way when its turn stops short of `stopped`, and when it comes
  back from a crash, since no harness keeps that for certain and a driver cannot say what a crash left. One that stopped on its own
  lands it in the turn that follows.
- **Cursors** are per `(reader, stream)` and held by the server. An omitted `after` means the reader's server-held
  cursor, never the head. `after=n` acks up to `n`, clamped to what the agent was shown, in a tool's result or by a handover a
  driver confirmed, so a hallucinated number or a read during a handover acks nothing unshown. A number past the head is no cursor,
  and reading from it would hide what is unread, so it is refused `invalid`. A cut-off wait confirms nothing. A filtered read never
  moves past what it left out. A cursor is a `seq`, so one `after` covers every stream of a wait. The server-held cursor is the end
  of the unbroken run offered, and reading from it acks what was shown of that run. An offer hands over everything up to the newest
  entry it wants on a stream, even entries its mode would leave, so the cursor always moves. A human or a program holds none and
  reads from `after`.
- **Broadcast.** One entry plus a recorded member list and group generation. That snapshot is its audience, and a sender
  is not in its own. Late joiners see history only if the channel says `history = "full"`.
- **Entries** are a capped `gist` plus an optional body. A digest shows gists. Exposure of a gist is recorded separately
  from exposure of a body.

**Injection** is `pull < next-turn < wake < steer`, set per channel on the reader's side, so a sender cannot buy a wake,
and an agent creating a channel stops at `next-turn`.
`wake` starts a turn if the agent is idle or parked. `steer` asks for the earliest boundary the harness has and degrades visibly:
`tool`, then `model_call`, then `turn`. Tool results of coordination ops also carry pending `steer` notices, which gives
a tool boundary on any harness whose tools are visible. `coalesce` merges wakes into one turn.

**Hop limit.** Every message carries `hops`, one more than the largest of what it replies to or what was offered to its turn, so a
model need not say. A human message resets it. A program has no turn, so its message starts a chain unless it names `reply_to`. A
wait's notice is one more than what its waiter had heard when it placed the wait, so a loop through a board counts too. A wake past
`max_hops` is refused and shown in attention, and the message waits for the next turn. This bounds reply loops that budgets only
make expensive.

**The monitor.** `spawn` installs a monitor. When an agent ends, however it ends, or a turn ends with no `finish` and no open
wait, the runtime posts the turn's final text, or `<name> <status>: <reason>` for an agent that did not finish, to the
spawning parent's inbox, as a runtime-authored event naming the child as
subject. It wakes at most once per causal chain for each child, so a reply to the same child cannot loop while a second worker
still reports back, and it stops at `max_hops`; past either, its message waits for the next turn.
So a worker reports back even if its harness hides our tools. Tools add power rather than being the only way in.

A report also waits for the next turn when waking would tell the parent nothing. A parent that ended the child itself did it. A
report the parent is counting does not wake it: the wait wakes it when it holds, so a join of N costs one turn. A parent counts a
child when a wait of its stands on the child's end or on a message from it. It also counts one whose doing it has already counted,
such as a task it settled, but only while someone else below it is at work, or it would sleep on what nobody is left to do. A turn
end is no end, so a child that ends a turn with no `finish` still wakes a join on its end, as only that can rescue it, once per chain
like any report.

A turn that did not stop on its own says so, `<name> turn <reason>: <text>`, or it would read as a final answer. One that an
interrupt or its owner's stop ended was someone's own doing, so it wakes nobody. Any other, and a child that ended badly, breaks in on
a parent with a wait open, whatever that wait counts and whatever the chain has spent, since that wait may now never hold. This is
fail-fast with no new wait grammar, and `max_hops` is what bounds it.

A wait that closes with no notice of its own, by `wait.cancel` or by a held call's answer, wakes its reader if a report is queued for
its next turn: that report may have counted on the wait to wake it, and no other turn may come.

### Boards

Objects have stable names and immutable versions (`board/<board>/<name>`). A read of one moves the reader's cursor on it, so
`wait` counts only versions it has not seen. `board.post` makes version 1, and on a taken name
conflicts as a stale `board.revise` does. `board.revise` requires `expected_version`; a
conflict returns the current version and silently overwrites nothing. `board.get` returns a ref naming exactly what it gave, so
a body too long for one result comes back cut, with `rest`, a ref that `blob.get` reads on from. `board.query` is structured; results carry exact
refs, the true total and a cursor. Text search uses SQLite FTS5 when present, over names, gists and fields and never bodies: a
fold cannot read a body, and a tombstoned body must leave nothing behind. Without FTS5 it is refused `unsupported`. Semantic
search is an extension. A board object version with a body is also how artifacts are stored.

### Queues

One stream per task. States: `open → claimed → done | failed | dead`. A `failed` task can be claimed again.

- **Claim.** Atomic, one live lease, fence = `seq` of the claim event.
- **Expiry.** A lease is live until `lease_until` by the transaction's clock. `task.claim` treats an expired lease as
  free, so a late clock cannot break correctness. `task.complete` after expiry is refused `stale_fence` even with no
  reassignment.
- **Fence default.** The caller's live lease, because a model can lose an integer to compaction.
- **Renewal.** The host renews from observed harness activity up to `lease_max`. `task.renew` stays for programs.
- **Retries.** `max_attempts`, then `dead`, shown in attention. Each claim spends an attempt, and `task.release` returns it.
- **Results.** What `task.complete` or `task.fail` reports stays on the task, and `task.list` shows it, as evidence for an agent.
- **`delivery`** works on a queue or board as on a topic. Unless it is `pull`, each `task.add`, `board.post` or `board.revise` posts
  one entry on `queue/<name>` or `board/<name>`, for whoever holds `task.claim` or `board.get`, so `coalesce`, hops and attention
  come with it. It announces work and never assigns it.
- Exclusive ownership is **not** exactly-once execution. External effects cannot be fenced by us, and the docs say so.

### Wait

```python
wait(on=[...], mode="all" | "any", after=None, timeout=None, hold=None)
on(stream, types=..., n=1, distinct=None)   # join, wait-any, version watch and barrier are this one condition
```

- Check and registration are one transaction from `after`, so the read-then-subscribe race cannot exist.
- `Waits` folds progress (`have`, `need`, `missing`), which is what the UI shows, and how each wait closed. `n` counts events
  that are news to the waiter: not its own, and no entry it was never meant to see, so a wait for an answer cannot end on the
  question. With `distinct`, naming an envelope field, it counts different values, its own too, and it may list them, so
  `n=members` can say who is `missing`. `agents` and `tasks` use it, because an end is an end whoever brought it about, so a
  cancel before a join holds that join.
- **One open wait per agent.** Another `wait` replaces it, so a model tracks no ids. A program may hold several.
- **A wait outlives its turn.** While the agent's turn runs its wait stays open, even once it holds. The runtime closes it when
  the turn ends, so a wake cannot race the turn it follows. A `timeout` closes it the same way and acks nothing.
- **Parks by default.** The tool result says the wait is registered and to end the turn. An agent becomes `waiting` when
  its turn ends, not at the call, because a harness can batch `wait` with sibling tools. When the condition holds, the runtime
  starts the next turn with its delivery attached. If the model keeps working, the wait stays open and nothing breaks.
- **The wait lives in the service.** A wake never depends on the model having seen the tool result, because an interrupted
  harness can replace that result. Parking was clean in 10 of 10 trials across Claude Code and Codex with the tool visible.
- **`hold`** keeps the call open below the driver's `tool_timeout_s`. On expiry it returns `pending`; the agent may call again,
  and each stream resumes from its own cursor, so nothing is counted twice. A one-shot driver cannot park, so `wait` beyond `hold`
  is refused `unsupported` with the reason.
- **Tool arguments are friendly** (`agents`, `from`, `tasks`, `board`, `channels`, `queue`) and compile to `on(...)`, which no tool
  schema shows, so a model never learns stream names. `from` counts by subject, so a monitor's report counts as its child's, and a
  human or a program by name. `queue` holds on the oldest open task, or else wherever the next will land, so a task added after
  `queue_empty` cannot slip by. A task that reopens after a lapse releases no such wait, so pass a `timeout` where that matters.
  An agent nobody spawned is refused `not_found`: it is a typo, since a spawn adds its principal in its own transaction.
- A parked agent whose harness cannot resume is `lost` through the normal ended transition.

**Barrier** is library code: a topic plus `wait(on(..., n=members, distinct="actor"))`, with member snapshot and generation
fixed at creation, `timeout`, and `on_failure = shrink | break | wait` driven by monitor events. A member joining later
does not join that barrier. **Lock** and **semaphore** are tokens in a queue, which gives lease and fence for free.

### Lifecycle

- **Spawn** is topology check, budget reservation, `admit`, `workspace`, `launch`, each step starting only once the last has
  finished. One that fails leaves the agent to the courier, which ends it `failed` with that step's error. Depth comes from the parent record,
  never from arguments. A child never holds more than `may_spawn` allows. Membership changes only on success. `may_spawn`
  is a grant on `role/<name>`. Spawn adds the child's principal in its own transaction, so its relations hold from that commit
  and a message can go ahead of it. The host then gives it a credential with `principal.issue`, because a token never enters the
  journal, and an agent that has ended cannot be given one.
- **Ended transition.** `finish`, `cancel`, `retire`, `lost` and a failed spawn are one event, `agent.ended{status}` (§5.5).
  An ended agent has no open turn. Only a turn is charged, so a failed spawn or an agent ended between turns spends nothing. A harness
  that exits ends its agent `lost`, or `failed` if it never started, and one that exits in a turn leaves the gap `crash_window`, since a
  tool of its own can run on. A one-shot agent ends with its turn: `finished` if that turn
  `stopped`, and `failed` otherwise.
- **Finishing** is like parking: `agent.finish` in an open turn records the report as `agent.finished`, and `agent.ended` commits when
  the turn ends, because a harness reports usage and its last message at turn end. Out of a turn it ends the agent at once. A turn
  still going a minute later is cut off, so what it had yet to report goes unmeasured. A harness that exits has finished all the same.
- **Working children.** `agent.finish` and `agent.retire` are refused `conflict`, naming each descendant that would end with the agent
  and is on its way to a turn or in one, which a wake that is due or a wait that holds also means. A wake the budget refused is on its
  way nowhere. The walk follows `cancel-subtree` edges, through a child that holds no turn, and stops at an `adopt` child. Any other
  child `waiting` or `idle` holds no turn, so it does not block, and `on_parent_exit` decides for it. The refusal says what to do next:
  `wait` for them, or `agent.cancel` each, which is never refused. An agent that has finished can spawn nothing. This
  is a check at the call, not a hold, so it has limits: a child that begins work after an accepted `finish` ends with its parent,
  whether the turn ends, the timer fires or the harness exits. So do the working children of a harness that exits, which nothing can
  refuse, and of a one-shot parent, which ends with its turn whatever it was told, as `team check` warns.
- **Goals.** An agent has no goal unless given one. With none it holds no turn's reservation, and it starts idle until a message wakes it.
A goal no turn has begun on keeps the session unsettled, until a wake the budget refused says none is coming. A harness that says
  ready and begins none within a minute is lost, and one resumed before it began takes the goal as a delivery, at-least-once, since a
  resumed harness waits to be told. That wake holds the turn its spawn reserved, and asks for no second. A session that stops accepting
  before that wake comes ends the agent, `lost`, because nothing is handed over now.
- **Cut-off turns.** A turn a crash lost, or one the owner's stop ended, is a turn its agent cannot know the end of, and an agent
  nobody tells sits idle on its leases. So a resume tells it, with one fixed notice and a wake, while the session accepts work: a
  resume is someone wanting the session to go on, and a notice nobody acts on is the stall it fixes. The notice says which of the two
  it was, that any tool call in it may have run, in part or in full, whatever its history shows, that none was repeated, and to check
  before repeating. It lists no calls, since a query leaves no event, so a list could not say that an unlisted call never ran. It is
  at-least-once, as a goal told again is: `stopped` says what to tell until the next turn begins, so a second crash before then repeats
  the line. A human's `agent.interrupt` is no cut-off. A host that is closing reports a turn interrupted as `stopped by its owner`,
  which tells the two apart and leaves a crash part of the way through a stop nothing to lose. Only the runtime gives those two
  reasons: a driver that says one has sent an unknown frame, and its turn ended `unknown`. The wake reserves a turn like any other, so
  a budget that an unmeasured turn left unable to hold refuses it, and the session ends `needs_human`.
- **`on_parent_exit`** is a role policy: `cancel-subtree` or `adopt`. Orphans under `adopt` belong to the session.
- **Retiring** takes an agent that has stopped working out of the live team, never out of history. While a turn is open it is
  refused `conflict`, and over working children as `finish` is: `cancel` is what stops one.
- **Takeover.** `agent.takeover` holds deliveries, and the human drives the native session; `agent.release` returns it, to its
  open turn if it has one, and records a gap. Human-driven turns carry human identity. Disabled with a reason on harnesses without resume.

### Completion

`settled` means, checkably: no agent on its way to a turn, no open turn, no deliverable delivery, no requested or started effect,
no due timer. A wait the runtime could close counts as a deliverable delivery, and so does a wake not yet due. A human
message can un-settle a session. Only `close` ends it. `session.close` with `if_done` closes only if that is still true at commit, so
a message that gets in first keeps a session open, and once it is closing `message.send` is refused `conflict`, since nothing would
reach anyone. `until` picks when a headless session closes: `"settled"`, `"role:lead"` or `"program"`. All stop at budget exhaustion.
A team with no root uses `"settled"`.

A session has **stalled** when it is open and settled short of `until` with nothing scheduled: no timer, no wait deadline to come and
no lease held. So a wall limit, a lease or a wait's `timeout` is waited for, and a lease's timer counts only while its claim does.
Short of exhaustion, a wake the budget refused keeps even a `"settled"` session from being done, because it is work left that only a
human can unblock, and so does a wait that names someone still here, through `agents` or `from`, so two agents parked on each other
stall under every `until` but `"program"`. A worker parked on a `queue` or a channel is no such thing, and a session closes around it.
A `"program"` session is left to its program. An extension daemon's private schedule is not in the journal, so it cannot hold off a
stall: such a daemon sets a timer.

### Approvals

Four facts stay apart: `approval.requested`, `approval.resolved` (a principal decided), `effect.finished` (the answer reached
the harness), and the observed item outcome. Codex's `accept` does not fix the result, so the UI reports the last.

`resolve` carries `expected_version`: the first commit wins, and the loser gets `conflict{resolved_by, via}`, shown as
information. **Approval policy is a durable session setting** (`ask`, `deny`, `allow`, per role), journaled at open, and
`Session.start(approvals=)` states one over every role's own. A headless session states one before its first turn. An `ask` that no
human can answer ends with exit 4: `settled()` returns `needs_human` at once when an approval is left to ask and no other client
holding a control credential is attached. A message from an agent can never carry an approval. An approval goes moot with the turn
that asked, however that turn ended, since a resumed harness has forgotten it.

### Budgets

`Budgets` holds limits for `tokens`, `usd`, `turns`, `agents`, `wall`, shared and per role.

A wake reserves an estimate; turn end reconciles it. An agent holds one turn's reservation. So overshoot is bounded by the
largest turn's cost times the live agents. Spawn reserves in the admission transaction, and a wake refused for budget is an
event, tried again when the budget moves.

Time alone exhausts a `wall` limit, so a timer fires `budget.lapse` at the shared one, which moves the journal for whoever sleeps
until it does. Measurements carry a label: `provider`, `estimated`, `lower_bound` or `unavailable`, and what the runtime counts itself,
`turns` and `agents`, is `counted`, which no driver can claim. A limit in a unit a role cannot measure
is refused by `team check`, or falls back to `turns` when that budget also limits `turns`; it never silently stops enforcing. A turn nobody
measured, a lost one among them, is charged its estimate and counts as unmeasured, so the next reservation in that unit is refused
`unavailable`, and usage shows that unit with no amount: unknown is not zero. Budget exhaustion means spent, never merely reserved. Native
subagents spend outside admission, which is a labelled gap. `over_budget` is policy; `unavailable` is infrastructure.

## 8. Topology

A topology is a set of grants over relations, not a graph of agents. `worker: [parent, children]` stays true as agents
spawn, so nothing rewrites config at runtime. It has no control flow.

```toml
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
workspace = "worktree"

[topology.manager-worker]
manager = "lead"
workers = "worker"
```

```console
$ platoon-harness team show
lead (claude) may message its workers and you. Workers (codex, own worktrees) may message lead.
lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Closes when lead finishes.
```

`team show --resolved` prints the expansion, which is valid input and is what the manifest stores and hashes. Defaults stay out of
it, so a new default never disturbs an old hash:

```toml
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
workspace = "worktree"

[topology]
until = "role:lead"
edges = { lead = ["children", "human"], worker = ["parent"] }

[topology.channels.notes]
kind = "board"
writers = "all"
readers = "all"

[topology.channels.tasks]
kind = "queue"
writers = "role:lead"
readers = "role:worker"
lease = "30m"
```

[topologies.md](topologies.md) is the guide, with a worked example per preset.

| Key | Meaning |
|---|---|
| `<preset>` | A macro: `manager-worker` `tree` `mesh` `star` `blackboard` `pipeline` `ring` `map-reduce` `git-swarm`, or an extension's. A table named after it, or `[[...]]` to use one twice. Several form a union |
| `edges` | Who may send to whose inbox, as `role: [relation...]`, or a lone relation |
| `channels` | Each with `kind`, `writers`, `readers`, `delivery`, and kind-specific fields |
| `groups` | Named membership rules: `roles`, `members` (principal ids), or `order`, which `next` and `prev` walk. Each change bumps the group's stream version, which is its generation |
| `limits` | `max_depth` `max_children` `max_live` `max_hops` |
| `grants` | Written-out `(who, ops, on)` rows, which is how an extension's op reaches a role |
| `program` | Optional control flow, in Python |
| `until` | §7, Completion |

**Selectors** are the same everywhere: `self parent children siblings ancestors descendants next prev human program all
role:x group:x`. They are evaluated on the graph as it stands. A relation outlives its far end, so an op on an ended agent gives
its own answer: `wait` releases, `agent.status` answers, and `message.send` says `undeliverable`. A channel in a team has no agent
to be relative to, so its `writers` and `readers` take only `human program all role:x group:x`.

**Rules.** Default deny. Presets and keys form a union, `a | b` in Python, so order never matters and the hash cannot tell how a
topology was mixed. Edges and grants add up. There is no `deny`, because mixing would stop being monotonic: adding a fragment could
take authority away. Two sources defining
one channel, group, limit, `program` or `until` differently is a load error that names both. Anything a preset can do, you can write
out. A preset that behaves differently from its expansion is a bug.

**Compilation.** Topology compiles to one `(who, ops, on)` table, with relations in `on` (`inbox/{children}`). Grants name
ops by glob, so an extension's op is authorized with no new vocabulary. `who` is a principal id, a kind, `role:x` or `all`.
`authorize` evaluates `self parent children siblings ancestors descendants human program all role:x`. `next`, `prev` and
`group:x` have no evaluator there, so `grant.add` refuses them `unsupported` and compilation never emits them: a group becomes its
roles or principals, and `next` and `prev` become the neighbors in a group's `order`. Humans and programs hold every op, so the
table binds agents. Its objects are `inbox/<id>`, `channel/<name>`, `channel/+<group>`, `queue/<name>`, `board/<board>/<name>`,
`role/<x>` for `agent.spawn` and `agent/<id>` for the rest of the lifecycle. An agent may `wait` only on what it can read: its
inbox, its channels and groups, the tasks of a queue it uses, and its descendants.

| Config | Enforcement | Shown to the agent | UI |
|---|---|---|---|
| `edges` | `message.send` checked against the target's relations | `message_send`, `peers`; absent with no edges | DMs; the team view draws reachable pairs |
| `channels` | Verb and selector checked on every write and read page | Verbs by kind, only for held grants | topic: channel; board: board view; queue: tasks view |
| `groups` | Membership from the live graph; generation in every broadcast | `+name` | Sidebar section |
| `may_spawn`, `limits` | Atomic admission with reservation | `agent_spawn` only if non-empty | Tree; refusal reason |
| `delivery` | Negotiated with the driver, degraded visibly | Nothing | "Queued until turn end" |

- **Role `tools`** attenuates: it lists op globs, which become the token's scopes, so the effective set is grants ∩ tools.
  Compilation always keeps `ops.list` in scope and grants it to `all`, because every surface derives from it.
- **Role `sandbox`** (`read-only`, ...) is a harness-plane setting, not a grant, and an unsupported value fails at `team check`.
- **Role `delivery`** sets the ladder for its agents' inboxes, `wake` unless stated.
- **Role `count`** is how many agents start with the session. Left out, that is one, or none if another role spawns this one.
- **The tool set** is fixed per role at launch, since live tool-list updates vary by harness. Valid targets change, so the preamble
  lists them at launch and `peers` as they stand; tool schemas never enumerate them.
- **Runtime evolution.** `spawn` adds members and journals `group.changed`. `channel.create` is a grant: a creator may use what
  it makes, and may name only readers and writers within its own reach. For an agent each selector means those it covers at that
  moment, since a rule would go on to cover agents past its reach, and one that covers nobody is refused. `topology.patch` comes
  from a human or program, and every event carries `topology_rev`.
- **`team check`** runs before any cost and reports everything at once. It refuses recursive spawning without `max_depth`, whether
  by `may_spawn` or a written grant of `agent.spawn`, a cycle without `max_hops`, a budget unit a role cannot measure, and an unknown
  preset, harness, extension, role, group or auth profile. A team that names no extension has nothing to wait for, so an unknown
  preset is refused at load. A cycle is a loop of wakes between roles. A reply up a tree is not one, so `parent`, `children`,
  `ancestors` and `descendants` edges never count, and neither does a channel or inbox that does not wake. A chain through a program
  is the program's own control flow, which `max_hops` does not bound unless it replies. It warns of a role that can never start, a role
  with no path to anyone, a relation no `may_spawn` makes true, an entry that can wake more than 8 agents, a program it cannot
  resolve, a setting no primitive enforces yet, and a one-shot role over children that would end with its turn. It refuses a one-shot role that starts with the session, which has no goal to start on,
and it says nothing of a `count` of zero, which was said on purpose, since a human or a program can spawn any role.

## 9. Drivers

One driver instance per agent.

```python
class Driver(Protocol):
    def describe(self) -> DriverInfo: ...                        # name, login kind, capabilities. Starts nothing
    async def start(self, spec: AgentSpec, report: Reporter) -> None: ...  # fresh, or resume from spec.resume
    async def deliver(self, delivery: Delivery) -> None: ...     # delivery.boundary is one the driver declared
    async def interrupt(self) -> None: ...                       # stops the turn, at the boundary it can
    async def answer(self, approval: str, verdict: Verdict) -> None: ...
    async def reconcile(self, input_id: str) -> Reconciled: ...  # landed | not_landed | unknown
    async def stop(self, grace: float) -> None: ...              # ends the process tree it owns
```

`AgentSpec` holds agent, role, goal, cwd, the agent's own folder, model, effort (a string handed to the harness as it stands), sandbox
(one of the values the driver declared, or left to the harness), tool binding, model access (`Secret` values by variable name, URLs included), env, instructions (appended by the supported path; native
project files are never touched) and resume. A fresh start begins the first turn on the goal. With no goal, or resumed, it waits for a
delivery. A driver raises `DriverError` for what it cannot do, so a one-shot harness refuses a start with no goal, and a harness with no
such setting refuses an effort.

`Reporter` is a plain async callable a driver awaits. It takes this vocabulary and no other: `ready{native, version,
effective_model, tools_visible}`, `turn.started{turn}`, `turn.ended{reason}`, `delta{text}` (lossy),
`item{kind: message|thought|tool|patch, phase: started|completed, native_id, call_id, gist, body, approval, outcome}`,
`input.delivered{input, boundary, evidence, native_id}`, `approval.requested{id, gist}`, `model.call{call_id, model, purpose}`,
`usage{tokens, usd, label, scope: call|turn|tree, call_id}`, `compacted{forgotten, summary}`,
`child.seen{native, parent, attribution}`, `gap{plane, what}`, `native{kind, raw, cut}`, `exited{reason}`, and
`changes{path, added, removed, tests}` from the runtime's own probe. Unknown frames become `native` plus a gap, never a log line. A
report's `body` is text until the host stores it and journals the hash, as ingress does for a tool's body argument, and `forgotten`
and `summary` go the same way, since either can pass what an event holds. `forgotten` holds native ids, and with `None` the runtime
records `compaction_opaque`. `tokens` counts input and output, cached input included. A `Delivery` carries its `text`, which the host renders in the words of the
agent's surface, with each entry's ref and sender, the ref of any body, and the input id. So a wire program in any language has it
for nothing, and `items` is there for one that wants more.

The host commits each report through `agent.report`, except two: a `delta` goes to `Kernel.push_delta`, and `ready` goes to
`agent.start` with the declared capabilities, the verified result and the levels, as `resumed` when it comes from a resumed harness,
which leaves the agent as it stood. A report cannot carry those, so a driver that tries to state one has sent an unknown frame.

### 9.1 Wire

Another process or language speaks line-delimited JSON-RPC 2.0 on stdio, split on LF only, logs on stderr. `WireDriver(command)`
is the only adapter, verbs equal the Python methods, and `protocol` is an integer refused when unknown. OpenHands runs this
way in its own environment, because its dependency set cannot share one with others, so the custom-driver path is real and
exercised.

```jsonc
> {"jsonrpc":"2.0","id":1,"method":"start","params":{"protocol":1,"spec":{"agent":"ada","role":"worker","goal":"...","access":["OPENAI_API_KEY"],"resume":null}}}
< {"jsonrpc":"2.0","id":1,"result":null}
< {"jsonrpc":"2.0","method":"report","params":{"type":"ready","native":"s-9","version":"1.4.0","effective_model":"m","tools_visible":null}}
> {"jsonrpc":"2.0","id":2,"method":"deliver","params":{"input":"d41","boundary":"turn","items":[{"ref":"inbox/ada@3","gist":"Keep the API stable"}]}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"input.delivered","input":"d41","boundary":"turn","evidence":"message_start"}}
```

Credentials never travel in a frame: `start` names them, and the program finds their values in its environment. `serve(driver)`
is all a wire driver in Python needs. Unknown lines and reports become `native` plus a gap, and a line past 16 MiB stops the agent
with a gap, since it may have held an answer. A team names a program with `harness = { command = [...], mode = "wire" }`.
[drivers.md](drivers.md) is the guide, with a complete wire driver that a test runs through the conformance suite.

A simple one-shot CLI needs no code: `harness = { command = ["my-agent", "{goal}"], mode = "oneshot" }` runs under the `exec`
driver, coordinating through `ph`. PTY integration is an explicit degraded fallback, not a substitute for structured events.

Every subprocess driver builds on `Process`, which holds the rest of what this page asks of one. A harness leads its own group. Its
pid and start time are on disk before it can exec: `sh` waits for one line on stdin, and exits unexecuted if we die first. Only a
leader with the recorded start time proves a group is ours, so a reused pid cannot make recovery kill a stranger, and a group whose
leader is gone is left alone and named. `reap` reads the driver's record and a wire program's and no others, because a harness can
write under its folder, and one it cannot read is named too. Pipes always drain, and stderr goes to a bounded log with credentials
masked. A driver that cuts text masks it first, since a cut can split a secret. `stop(grace)` is end of stdin, wait, `SIGTERM`, wait,
`SIGKILL`, then verify, and then what carries the harness's own `TMPDIR`, which everything it starts inherits, whichever group it left for:
on Linux, `stop` and `reap` find those in `/proc` and end them too. What clears its environment escapes, as does anything on macOS, and a
stop that came to `SIGKILL` reports `crash_window`, because a harness gets no chance to end what it started. See
[ADR 0018](adr/0018-who-owns-a-process.md) and [ADR 0021](adr/0021-what-a-harness-leaves-behind.md).

### 9.2 Capabilities

Absence means unsupported, as in ACP.

| Field | Values |
|---|---|
| `persistent` | One-shot workers cannot park |
| `resume` | Native resume available |
| `boundaries` | Subset of `turn`, `tool`, `model_call` |
| `tool_paths` | `mcp-http`, `mcp-stdio`, `shell` |
| `tool_timeout_s` | The harness's cap on one tool call |
| `interrupt` | A turn can be stopped |
| `approvals` | `none`, `gated`, `native` |
| `native_children` | `none`, `observed`, `opaque` |
| `call_ids` | `none`, `agent`, `call` |
| `dialects` | `chat`, `responses`, `messages` |
| `coverage` | `surface → observed | partial | none`, for `prompt`, `tool_results`, `shell_reads`, `files`, `native_children`, `compaction`, `external` |
| `measures` | Budget units it reports, of `tokens` and `usd`. The runtime counts `turns`, `agents` and `wall` for every harness |
| `sandboxes` | The values a role's `sandbox` may take |

### 9.3 Verified, not believed

- **Tool visibility has three values:** `visible`, `hidden`, `unverified`. `ready.tools_visible` is a list only when it comes from
  an observed source, and otherwise `None`. Unverified never refuses a spawn: the UI says "tools unverified", and the agent
  still works through `ph` and the monitor.
- **Conformance.** `check_driver(factory, folder=...)` runs named checks and reports all failures at once, against a loopback model
  that logs each request exactly as it arrived. So "tool in the first model request" and "delivered text in the next prompt" are tested
  against ground truth, and "connected" counts for nothing. Unsupported is a skip with a reason, never a pass. Results pin to
  `(driver, harness version)`, and a result pinned elsewhere says nothing of this agent. A wire `describe` runs the program once and
  starts no harness.
- **Model pinning.** The effective model must equal the requested one, so an alias a harness resolves to another name fails. The host
  holds `ready` to this and fails a spawn or a resume that differs. An effective model a harness does not name stays unknown, and refuses
  nothing. An unset model on the harness's own login means the harness's own default, and `ready` says which. A driver refuses an unset
  model only where access was given, since the default may then go somewhere nobody chose.

### 9.4 Levels

`levels(capabilities, profile, conformance)` is a pure function giving `operational`, `observable` and `trainable`, each `met`,
`unmet` or `unverified` with reasons, journaled in `agent.started` beside `declared` and `verified`. A `Profile` is how one agent runs:
its driver and observed harness version, its login, and whether its tools were seen. No driver can claim a level: the host commits
all of this through `agent.start`, and a report has no field for it.

### 9.5 Mappings

| Harness | Path | Notes that matter |
|---|---|---|
| `claude` | `claude -p` stream-json plus control protocol, stdin held open | The user's own setup, with ours beside it: HTTP MCP inline with `alwaysLoad`, naming the token's variable so that no file holds it, and no `--setting-sources`, no `--strict-mcp-config`. `--permission-prompt-tool stdio --permission-mode default` is the one launch path, as a user's `defaultMode` would answer first, and the runtime applies the approval policy to every request; `AskUserQuestion`, which that prompt tool brings in and no verdict can answer, is disallowed; a role's budget is what limits it, so no `--max-turns`. `uuid` on every input, and `command_lifecycle` says what landed where; an interrupt passes `cancel_queued`, as the runtime offers again what never landed, and the harness would otherwise begin a turn on it by itself; `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, since a result is not a turn end while background tasks run, and it keeps a native child inside the tool call that started it, so an open turn covers it and `child.seen` needs no end; exit 1 after our own interrupt is normal. `get_settings` says the effective model before any model call, and `mcp_status` that our server failed, which fails the start. Its `toolUseId` equals the model's tool id. Never `ANTHROPIC_BASE_URL` without a gateway credential |
| `codex` | `codex app-server` over stdio, no `experimentalApi` | The user's own setup, with ours beside it: `thread/start.config` overlays it for one thread, the same fields again on `thread/resume`, and what that overlay would replace, `developer_instructions` and `shell_environment_policy.exclude`, is read from `config/read` and kept. `approvalPolicy: "on-request"`, so every approval it asks for comes to the runtime, and `approvalsReviewer: "user"`, as user config can send them elsewhere. MCP with `default_tools_approval_mode: "approve"`, `required: true` and `omit_tools_from: ["deferred"]`, or the model must find our tools by writing a filter, and sometimes misses; `shell_environment_policy.exclude` names the token variable, or it reaches the agent shell. `turn/start` is one way in: it steers a turn under way and otherwise begins one. `turn/interrupt` stops one thread, so the driver walks its children. A turn ends with the last thread at work, since a child can outlive its parent's turn, so an open turn covers it and `child.seen` needs no end. `item/completed` is truth. `callId` joins to the `exec` script, not to a model call. `ph` is blocked by the default sandbox, so MCP is the path. Access by key is a provider of the thread's own, so no saved login pays |
| `pi` | `pi --mode rpc` | The user's own setup, with ours beside it: pi keeps its own agent directory, so their login, settings and extensions stay theirs, and one extension loaded with `-e` adds our tools through the stdio shim, `exposure: direct`, with the timeout `tool_timeout_s` says, and our instructions as a section of their own, since `--append-system-prompt` replaces the user's `APPEND_SYSTEM.md`. A provider of the agent's own is how access by URL arrives, so no saved login pays. `prompt` with a `streamingBehavior` is one way in: it begins a turn or queues in one, and the id goes in the text, as `reconcile` finds it in `get_entries`. A provider with no login is refused at start, as only a prompt would say so. `agent_settled` is `turn.ended`. What an interrupt leaves in pi's queue no run takes, so it is cleared. `gated` approvals through that extension, and no boundary. `message_end` gives `model.call`, with `responseId`; the gateway join is claimed at M3. `compaction_end` gives a `model.call` of purpose `compaction`, and `forgotten` from `get_entries`. Cache warming off when trainable |
| `openhands` | Wire worker on SDK `arun()`, own environment | Boundary is the next LLM request; `llm_response_id` gives `model.call`; `Condensation` gives `compacted{forgotten}`; hold deliveries while an approval is open, since `send_message` supersedes it |
| ACP agents | Generic driver, protocol 1, `fs` and `terminal` false | Turn boundary only; raw frames captured before parsing; `steer` only after a fixture passes. OpenCode must set `codemode: false`, or tools hide behind Code Mode, and must never run with an unset model |

## 10. Tool plane

The SDK ships a tiny tools-only MCP server: Streamable HTTP on loopback with a per-agent bearer token, plus a stdlib stdio
shim for harnesses without HTTP. It is ours rather than the `mcp` package because that package cannot share an environment
with `platoon[ors]` or OpenHands, and because we need strict argument refusal and token-only identity. It is contract-tested
against the official client and against each real harness.

- Tokens are per `(session, agent)` and per incarnation, revoked at `agent.ended`, and hashed in the journal. Re-supplied on resume.
- Identity never comes from `clientInfo`, `_meta` or arguments. `_meta` anchors are correlation evidence only.
- `tools/list` is filtered by authorization and enforced again at call time.
- Coordination state uses explicit handles (`cursor`, `lease`, `version`). No session semantics.
- A body argument is offered as a string of text. Ingress stores it and puts the hash in its place before `submit`, as ingress
  already stores bodies first, so a model never handles a hash it has to make.
- JSON replies, no SSE, no sessions; `GET` and `DELETE` return 405, and `server/discover` returns -32601. Both real clients connect
  through `initialize`, Claude Code after that fallback. We do not claim the stateless 2026-07-28 revision, so a client that speaks
  only that revision cannot connect yet. Undeclared arguments return a tool result with `isError: true`, because clients forward them.
- One request per connection, answered with `Connection: close`, so an idle client holds no task, socket or state here. A client
  that goes during a call drops the call, not what it asked for: a wait stays registered.
- A request is bounded before it is believed: a head of 16 KiB, then `Origin`, `Host` and the bearer, and only then a body of at most
  1 MiB, with a length and no chunking. It has 10 s on the kernel's clock to arrive and its answer 10 s to leave. Past 1,024
  connections the server answers 503.
- `?surface=` on the URL names how tools read to a model: `ph`, or `mcp__<ns>` for a harness that shows them that way. It changes
  descriptions and refusals, never what a token may do. No real harness has been run through a URL with a query yet.
- `tools/call` answers with the result as JSON in the first content block. Later blocks carry a repeat's label and steer notices,
  which `delivery.pending` asks about first, so a call with no notice to carry journals nothing. `ph` sends those to stderr.
- A result holds at most 32 KiB of what an op returned and what the surface read, plus notices. A list as long as a team, `peers` or
  `channel.list`, goes a page at a time, since a refusal would leave a model no other way to find anyone. So only an extension's query
  can answer past that, and it is refused `unsupported` with its size, and nothing runs. A row with a null `text` beside a
  body's ref is a body its op could not read: the surface reads up to 16 MiB of it, shows the lines that fit, says in `rest` where
  the rest is, and journals what it showed with `blob.offer` before the text leaves. `text` stays null for a binary, redacted or
  larger body, or one line too long to show.
- `hold` runs `hold_open` as the runtime, which is right: a held call must close its wait with `wait.release`, a runtime-only op, and
  a role's `tools` can leave out `wait.progress`. Nothing a client sends reaches it: its id comes from the `wait` the agent was
  authorized to place. Holding is bounded by `tool_timeout_s` when `wait` is placed, and by the client hanging up. A wait that holds
  closes as `told` only once its answer has left, so an answer that is lost costs no wake: the wait stays open, and closes with its turn.

**Everyday instruction surface.** The preamble and the tool descriptions teach the tools, by exact name, because no harness's
tool discovery can be relied on. A description names ops as `task.claim`, and each surface renders that as its own name for the tool.
A sentence that names a tool its reader does not hold is left out, in a refusal's reason too, so what a model is told it can do, and
a fact goes in a sentence apart from the tool that serves it. A test holds every argument to a description, every description to what
a refusal means, and every op it names to one that exists, for a reader who holds only that tool. Tool schemas leave out what is
for programs and team files, such as `on` and a queue's lease. The tool list and the preamble are fixed at launch, and go once to each
harness, so the preamble is a snapshot of who could be reached then, and `peers` is what stays current. Besides the tools and who can
be reached, the preamble names the roles an agent may start, since a model guessed a harness's name there and gave up. It says how
to end too: an agent somebody spawned is told to make `agent.finish` its last call, or a join on it never holds, and one the session
started is told to stay, since a human talks to it over many turns. That text is in every request
of every agent, so a test holds each default role's list under a ceiling. We append through each harness's
supported path and never overwrite `CLAUDE.md`, `AGENTS.md`, skills or hooks. The per-harness table of how project
instructions, skills, slash commands, hooks and compaction interact with coordination lives in
[compatibility.md](compatibility.md).

## 11. Provenance

The graph is not stored. Nodes are events, and edges are the references they already hold.

- **Time-expanded dependency graph.** Acyclic by law 7. A's post, B's response and A's next action are three nodes.
- **Agent interaction graph.** The quotient by agent. It may have cycles, and it is for display.
- **Context version.** Each agent has a stream `context/<agent>`. An offer or a compaction advances it, and every agent event
  records it. So `context_version` is an **upper bound** on what an action could have known, `delivered` edges are a **lower
  bound**, and the distance between them is measured uncertainty.

| Evidence | Representation | Sole writer | Means only |
|---|---|---|---|
| **Observed exposure** | `context.offered{items:[{ref, form, digest}], boundary, how}`, raised by `context.delivered` | Courier, and agent-read ops | This content was handed over, then confirmed injected |
| **Declared dependency** | `based_on`, `informed_by` on a write, checked to exist | That op's actor | The agent claims it |
| **Judged attribution** | Annotation: judge, version, evidence refs, value | A `judge` principal | A versioned opinion |
| **Validated intervention** | Annotation: design, comparison, measured result | A `program` principal | One controlled comparison |

Git ancestry, tests and merges are events on `repo/<name>`, never merged with these. **Three axes never merge:** evidence type
says why an edge is believed; **attribution** (`exact`, `declared`, `inferred`, `forked`) says how well a model call is tied to
an agent, tracking a Platoon draft in our own versioned enum; **assurance** (`cooperative`, `isolated`) says how well an actor is
tied to a credential, recorded once on `agent.started`.

**Late joins.** A `model.called`, and an `item` or a `usage` that names its call, carry that `call_id` on the envelope, and nothing else
does. A tool op can commit before the model call that caused it is reported. `call.joined` is a new event citing both, with its quality (`anchor`,
`response_id`, `turn`), for that late case alone. Tools link to a model call only through a real anchor.

**Coverage.** Standing gaps come from `coverage` at `agent.started`: any harness with a shell is blind to `shell_reads` for life.
Incident gaps are events of a closed set: `stream_lost`, `compaction_opaque`, `exposure_unconfirmed`, `native_child_unattributed`,
`usage_lower_bound`, `unknown_update`, `hidden_call`, `crash_window`, `takeover`.

```python
await session.exposure(agent, ref, before=event)   # Seen(edge) | NotSeen(coverage) | Unknown(gaps), never a boolean
await session.lineage(ref)                         # paths and the gaps that qualify them, always together
```

`platoon-harness why <ref>` prints the same thing.

**Annotations** attach to immutable events the way `git notes` attach to commits, in `annotations.sqlite`:
`(id, target, kind, producer, producer_version, params_hash, value, status, evidence, head_seq, wall_time)`, unique on producer,
version, params, target and kind. `head_seq` names the exact trace. Rewards live here with `scope: local | team`, a required
`status`, and `value` nullable, so `invalid`, `error`, `cancelled` and `unscored` are never zero. A new estimator adds rows
beside old ones, on a closed session, with no writer lock.

## 12. Clients

Clients hold no timers, decide nothing and compute no status. They submit ops and render kernel views, so no second scheduler
can exist.

```python
async with Session.start(team, name="fix-auth") as session:   # owner: leaving stops agents and keeps the folder
    await session.send("@lead", "Fix the flaky test")
    ending = await session.settled(timeout="30m")
```

`await Session.start(...)` works too. `Session.attach(name)` is the same class as a guest, and `Session.resume(name)` restarts an
owner, as its own verb because restarting can spend money. The human is one principal, `human:you` unless `start` says otherwise. That
is a name in the journal and not a claim: identity still comes from the credential.

A `Session` has exactly one internal link, in two forms: the kernel in-process (`Local`, or `History` on a read-only kernel, whose
writes are refused `unavailable` naming the resume command), and the control socket (`Remote`). Everything else is written once
on top of it, so following a journal is one loop of `read` and a long-poll in either form. A client that loses its runtime attaches
again, and a command it had sent retries under its key, so it stays one operation. On history it looks for a runtime on each call,
and opens the journal again once a writer has touched it. A session is entered once: awaiting one that was left starts nothing, because
`resume` is the verb for that. A refusal a runtime gives while it comes up is waited out, and any other, such as a protocol it does not
speak, comes back at once.

**The control socket** is line-delimited JSON-RPC 2.0 through `rpc.py`, on a Unix socket: `hello`, then `submit`, `query`, `read`,
`put_body`, `get_body`, `others`, and the long-polls `changed` and `delta`. The server is one `Local` per connection, so the methods
mirror by construction. `hello` checks the credential once and binds the principal to the connection. A connection that never says
it is dropped. A view credential reads and can never write, and a try writes nothing either, so no event can come of it. An agent's
token is refused: its reads are ops, and the tool plane is its way in. A refusal crosses as data. Law 8 holds because a client only
ever pulls, so the runtime has no queue or subscription to fill: a page leaves when asked for, a long-poll comes back within 25 s, a
client that stops reading is dropped by its `Peer`, and live text is refused for a name nobody holds, so no client can grow the rings.
A stop aborts every connection, so no client can hold up shutdown either.

`settled()` waits for `session.status` to say done, closes the session at `until`, waits for it to drain, and returns an `Ending`: the
state, each agent, usage with its labels, every gap, and a reason, which `session.ending` works out in the kernel. Timing out leaves
the session as it is. What only a person can move, an approval left to `ask` or a session that has stalled, ends it with `needs_human`
and leaves the session as it is, unless another client holding a control credential is attached. It waits for that client to act or
to go, and looks once a second, because a client can leave without moving the journal. So a session at rest cannot hang `settled()`
with no timeout, unless a client that stays attached never acts: two clients both in `settled()` wait on each other, so give one a
timeout. A harness that never ends its turn can hang it too, which is what a wall limit is for.

| Reason | Exit code |
|---|---|
| `settled` | 0 |
| `agent_failed` | 1 |
| `budget_exhausted` | 2 |
| `timed_out` | 3 |
| `needs_human` | 4 |
| `cancelled` | 130 |

Three views answer the five questions, through `view.watch(name, after)`: a snapshot, then keyed changes. Almost any event can move a
roster row, under a name that is not that agent's, so `roster` answers with every row whenever the journal has moved, which is about
21 KB at 100 agents.

| View | Row | Answers |
|---|---|---|
| `roster` | `agent, role, harness, model, parent, state, activity, stopped, held_by, why, unread, levels, usage` | Who is working, on what, what is blocked. A row names everyone as `agent` does, so `parent` finds its row |
| `attention` | `id, kind, agent, gist, since_seq, version, actions[]` | Where you must act: `approval`, `mention`, `uncertain`, `failed`, `dead_task`, `budget`, `hops` |
| `changes` | `agent, path or commit, added, removed, tests, since_mark` | What changed. A runtime probe at each `turn.ended` feeds it, so opaque harnesses are covered |

`activity` is the gist of the latest item, so it reads the running tool when a driver sends a `started` item. `stopped` says why the last
turn did not stop on its own, until the next begins. `why` is typed: `Approval(id)`, `Wait(have, need, missing)`, `Budget(code)`, `Lease(id)`, `Peer(id)`, `Timer(at)`, `Infra(detail)`,
`Lost(reason)`, so "barrier 2 of 3, missing w7" needs no guessing. `needs-you` is a derived group, not a state. `actions[]` are
op references, each with whatever keeps a stale button from deciding anything, so any client can draw them.

- **TUI.** Textual. One 15 Hz coalescer between the journal and widgets drops render frames, never events. `TranscriptView` is on
  the Line API with paging from the journal, so history is virtual. Untrusted text crosses one `SafeText` boundary, and a lint
  bans bare `str` in label-like widgets. Approvals never take focus.
- **SwarmChat.** A follower folds the journal into its own rebuildable `swarmchat.sqlite` and serves the pinned, hash-checked
  frontend assets, the `view_*` replies, an overlay, and one `/x/command` route into the same ops. Upstream's server never runs,
  and nothing re-ingests the projection, so two authorities and echo loops have no path. Direct chats key on the unordered
  participant pair, with both inboxes merged in journal order; channel chats key on the channel. One session per port avoids
  the `localStorage` collision. "Read by" becomes "Delivered to".

## 13. Workspaces

`workspace` is `shared`, `worktree`, `snapshot` or `isolated`, as the provider allows. An unavailable mode fails loudly and never
degrades. A worktree is not a security sandbox. Git operations by agents are observed at turn end; commits, tests, merges and
conflicts are events on `repo/<name>`. Git ancestry, declared `informed_by`, observed reads and credit stay different relations.
Uncommitted work is never silently discarded, and conflicts are surfaced, never auto-resolved. Gitea and GitLab are extensions.

## 14. Training

The SDK owns execution and evidence. Platoon owns training-data construction, optimization and eligibility. The kernel has no
Platoon branch: standalone and managed differ only in the `Authority` object and the role's trainable profile.

```python
class Authority(Protocol):
    async def admit(self, spawn: SpawnRequest) -> Admission: ...       # a token and model access, so far
    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None: ...
    def budget_owner(self, resource: str) -> Literal["session", "authority"]: ...
```

`LocalAuthority` issues session-scoped identity and leaves the harness's own auth alone: model access is what a role's auth profile
names, and with none the harness signs itself in. `admit` runs for a spawn, and again with `resumed` for a harness coming back, which
needs its access again. A limit in a resource `budget_owner` says the authority owns is no limit of the session's. `PlatoonAuthority`
lives in the `platoon-harness-platoon` extension, built on Platoon's stable function-harness and program seam. It will add what
`Admission` does not hold yet: tool endpoints, workspace and attribution.

- **Two admission routes.** Tree children use `ctx.agents.spawn` with a member harness, which gives forks, grading and depth. Peers
  with no fork use `POST /v1/platoon/agents`. Mint is never retried.
- **Root.** A single-entry tree uses `ctx.endpoint`, which preserves RAO's depth and row shape. Mesh and git-swarm use a zero-call
  root, labelled as a mapping artifact. The root samples the default policy, so `team check --trainable` refuses a mismatch.
- **Credentials.** A path-form URL is a credential. It is normalized to origin plus bearer before a driver sees it.
- **Eligibility** is `eligibility(agent, episode)`, a pure function of the record with no stored flag. Anything outside an episode
  fails by default, as do frozen agents, judges, humans, shared keys and unverified profiles. Platoon still decides.
- **Reward data** stays in `annotations.sqlite`, which no agent-reachable read opens.
- **Codex behind the gateway has no known coordination path.** Its MCP tools do not survive the gateway's Responses dialect, and its
  default sandbox blocks the shell client. It stays out of trainable teams unless a role grants network access as a journaled trust
  decision.
- **Limits at Platoon 0.5.** `AgentGraph`, `RewardEvent` and attribution levels are draft-only there, so they are not integration
  targets. A guide will hold the bridge, the RAO golden fixture, the no-extra-rollout baseline and the proposed amendments.

| Operation | Authorizes | Executes | Records | Reconciles |
|---|---|---|---|---|
| Spawn | Topology, budget; managed: then Platoon, whose refusal wins | Driver via `Authority.admit` | Journal: requested, then settled | Membership changes only on success |
| Identity | Runtime; managed: Platoon | Runtime; managed: mint or spawn | Journal holds hashes and Platoon ids, never a key | No competing id |
| Model routing, model budget | Harness login; managed: Platoon | Harness; managed: gateway | Journal: call ids. Platoon: tokens | Finalizer joins on `agent_id`; Platoon authoritative |
| Messages, boards, queues, waits | Topology | Kernel in both | Journal | Platoon `bus` is draft: an adapter if it ships |
| Workspace, forks | Role; managed: Platoon | Provider; managed: `EnvSession.fork` | Journal, with mode | An unavailable mode fails loudly |
| Env tools and env boards | Environment | Environment | Tool events, exposure where reported, else a gap | Never remodeled as channels |
| Rewards, credit | Env, judge, Platoon | Env, judge, Platoon trainer | Annotations; `Trajectory` via finalizer | `None` becomes a marker only in the finalizer |
| Eligibility | Platoon | Converter | Export reasons | `eligibility()` gates; Platoon decides |

## 15. Security

Threat tiers stay separate, in docs and in events.

| Tier | Threat | Status |
|---|---|---|
| Model arguments | Hallucination, prompt injection through tool arguments | Closed by construction: laws 6 and 7, server-side authorization, strict decoding |
| Untrusted content | Board contents, repository files, tool output, rendered Markdown | `SafeText` in the terminal; escaping and hash-only CSP in the browser. Content is data, never instructions |
| Network | Browser and remote clients | Loopback by default. View and control tokens are separate classes. Links are one-time and exchanged for expiring tokens. Origin and Host allowlists. Remote exposure needs an explicit flag and TLS |
| Shell-capable agent at the same UID | Reads another agent's token, the owner token, other sessions | **Not closed by this tier.** On such a session, approvals and session isolation are workflow controls, not boundaries. Assurance is `cooperative`; only OS isolation earns `isolated` |
| Plugins | Extensions and drivers | Trusted code unless separately isolated |

- **Bodies.** A body's hash is a capability, and a low-entropy body can be guessed: bodies are for content, not for secrets.
- **Secrets.** Config holds env var names, never values. `Secret` refuses serialization. Redaction covers values, their encoded forms, and URLs.
  No model-access credential reaches a log, event, artifact, export or resolved config.
- **Bodies and retention.** A body can be tombstoned while its hash survives, so the graph stays whole. A secret in a `gist` needs an
  offline rewrite that produces a new session.
- **Plan logins.** We spawn the user's own harness under its own login and never read, copy or proxy a credential. Headless multi-agent on a plan
  login exits 78 and names the fix unless the user opts in, with `Session.start(team, plan_login=True)`. `prepare` refuses it from each role's
  `DriverInfo.login`, which comes from the harness's own status command, and a role with an auth profile is on no login. One agent alone is not
  refused, unless another role can spawn more. `web --remote` refuses a second person on a plan-login session.
- **Project config is untrusted.** It can select installed components but can never install one. What would run code or pass a credential, a
  `command` harness, a `module:attr` reference or an auth profile, needs an explicit trust step in a project or team file. The check reads where
  each value came from, since mappings merge across layers.
- **Harness env.** An allowlist, per process. `PATH`, `HOME` and a supplied `TMPDIR` were enough for Claude Code; Codex ran on the same
  allowlist plus its token variable. Nothing is inherited by default, so variables that change a harness's behavior or leak a parent's
  identity cannot pass through. A role with no auth profile signs in as the harness does in the user's shell, so a driver adds by name what
  stops that, such as where its login lives and a proxy. Provider keys stay in auth profiles.

## 16. Observability

`session.metrics` reads a fold of counters plus runtime gauges: throughput, ack latency, queue depth, failures, active and blocked agents, resource
use, provenance coverage and training eligibility. Counters are folds, so instrumentation adds no journal writes. Display telemetry can be reduced
freely, because credit-critical evidence is an event and deltas are not.

## 17. Extensions and configuration

```python
extension = Extension("ballot", ops=[cast], views=[Votes], daemons=[], presets=[pair_review])
```

A preset is a plain function returning a topology fragment. Its name is the function's with dashes for underscores, and it may not
take the name of a built-in preset or a topology key.

Two entry-point groups: `platoon_harness.drivers` (name → driver) and `platoon_harness.extensions` (name → `Extension`). A kind gets a group when a
second independent user needs a short name. Discovery reads metadata with no import, so duplicates and incompatible `platoon-harness-sdk` requirements
are caught before any code loads or any cost is spent. Installing activates nothing: a role names a harness, a team names `extensions = [...]`,
`name@version` is always accepted, and `module:attr` is accepted from a trusted layer, since it imports. First-party and third-party extensions use
the same contracts.

An extension op is usable through the SDK, MCP, `ph`, the CLI and the generic UI with no core edit: every surface derives from `ops.list`, and any client
can render any event from its `gist`. Unknown events survive export and replay.

**Configuration** is pydantic, frozen, `extra="forbid"`, loaded from TOML with stdlib `tomllib`, or built in Python. Precedence, low to high: defaults, user
config (`$XDG_CONFIG_HOME/platoon-harness/config.toml`), project config (`platoon-harness.toml`), team file, environment (`PLATOON_HARNESS_CONFIG`, TOML text),
command line (TOML lines, such as `budget.usd = 5`). Mappings merge and lists replace. Every problem is reported at once, with did-you-mean.
The sanitized resolved form reloads alone, and is refused if it holds the value of a variable an auth profile names. The manifest records it with resolved
component versions, and schema and protocol versions.

## 18. Left out on purpose

- **`run` as a noun:** session plus episode cover it, and the word collides with Platoon's.
- **Scheduler modes, workflow graphs, an LLM speaker selector:** control flow belongs in a Python program; a selector is a central scheduler in disguise.
- **Middleware in the op path:** an extension adds ops and daemons; nothing intercepts another op.
- **Push subscriptions:** pull with a pulse gives backpressure by construction.
- **A central daemon, a session registry, a database shared across sessions:** one folder per session gives isolation, export and deletion for free.
- **A storage interface:** one SQLite implementation until a second exists. Per-stream ordering keeps sharding possible.
- **Deterministic replay:** replay folds events and never re-runs tools. Event replay, resumable execution, workspace snapshotting and counterfactual
  re-execution are four different things, and only the first three exist.
- **Consensus, 2PC, leader election, vector clocks:** one writer gives order; a leader is a role or one task token.
- **`deny` rules and sender-chosen wakes:** deny breaks monotonicity, since adding a fragment could remove authority; wakes belong to the reader.
- **Multi-machine workers in the first release:** the wire allows them. No fleet code until a user exists.
- **Login flows and credential brokerage:** each harness signs itself in.
- **Raw frames for every harness:** only unknown updates keep their frames, since a spool is a second durable path and a scrubbing problem.
