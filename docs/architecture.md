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
| **Effect** | A tracked request to touch the world: requested, started, then finished, failed or uncertain. |
| **Daemon** | A supervised task that performs effects or reacts to views, keeping nothing that must survive a restart. |
| **Principal** | An authenticated actor (`agent`, `human`, `program`, `judge`, `runtime`), resolved from a credential. |
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
- The extension's name is the namespace. Collisions are refused at load. There is no `x.` prefix.
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
  manifest.json       resolved team, component and protocol versions, topology hash; no secrets
  runtime.json        pid, start time, socket path, incarnation: present only while live
  owner.token         0600
  lock                flock: held by the one live runtime
  agents/<id>/        per-agent state: proc.json, native home, workspace pointer
```

- **Root.** `$PLATOON_HARNESS_HOME`, else `$XDG_STATE_HOME/platoon-harness`. If that is on a network filesystem,
  the default falls back to `/var/tmp/platoon-harness-$UID`, with a one-line notice and a `doctor` entry. An
  explicitly chosen root on a network filesystem is refused with exit 78. Only live writers are refused: a closed
  session is a portable artifact (§5.8).
- **Sockets** live in a short per-user runtime directory, never inside the session folder, because `sun_path` is
  about 104-108 bytes. `runtime.json` names the path.
- **One runtime process per live session.** It owns `lock` and binds the control socket in every mode. There is no
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
- **Shutdown contract of an owner:** interrupt turns, wait `grace`, end the process trees it started, release
  reservations, append `session.stopped`, keep the folder resumable.

## 5. Kernel

```python
class Kernel:
    def open(path, *, clock=None, extensions=(), read_only=False) -> Kernel: ...
    async def submit(self, principal, op, args, *, key=None, expected_version=None) -> Outcome: ...
    def query(self, principal, op, args) -> Outcome: ...      # a read-only op on a read connection
    def read(self, principal, *, after, match=None, limit=512) -> Page: ...  # never for agent principals
    async def follow(self, principal, *, after, match=None) -> AsyncIterator[Page]: ...
    def deltas(self, agent) -> AsyncIterator[Delta]: ...      # lossy live text; never journaled
    def close(self) -> None: ...
```

The kernel knows streams, principals, grants and effects. It does not know what a message, board, task or harness
is; those are primitives, written as `Extension` values on the same contract a third party uses. Its own ops, views and
daemons load the same way, so `effect`, `timer`, `principal`, `grant`, `body`, `runtime`, `op` and `ops` are taken names.

`submit` and `query` return an `Outcome`, whose `refusal` says why nothing happened; they never raise one. `read` and
`follow`, which are not ops, raise `Refused`. Around these sit `authenticate(token)`, `put_body(bytes)`, `get_body(hash)`,
`erase_body(hash)`, `recover()`, `rebuild(view)`, `rebuild_all()`, `supervise()`, `head`, `changed(after)`,
`push_delta(agent, text)`, `session_id` and `closed`, plus what a daemon reaches for: `runtime`, `clock` and `ops`.

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
   write under `head`. If the commit fails, no command in the batch happened: each gets `unavailable`, journals nothing, and
   may retry under its key.

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
refuses. A ref is `stream@version`, with an optional `#range`, or `sha256:<hash>` for a body. `cause`, `based_on`, `native` and
`correlation` can hold caller text, so together they are held to 16 KiB as well, and a stream name to 512 characters.

### 5.4 Effects

An op never touches the world. `txn.effect(kind, data, on_uncertain=..., timeout=..., priority=..., agent=...)` appends
`effect.requested` and returns the effect's id, which is that event's `seq`. A daemon commits `effect.start`, which returns the
attempt, acts, then commits `effect.finish` or `effect.fail` naming that attempt. While a newer attempt runs, a late report from
an older one is refused `conflict`. Daemons read `v_effects`, so they are level-triggered and hold no durable position. One
agent's effects start in order. A `priority` above zero starts first and ignores that order.

| Kind | Key sent outward | After a crash |
|---|---|---|
| `launch` | Native session id; pid and start time written by the launcher **before exec** | Kill the recorded group if still ours; resume if the role allows; else agent `lost` with a gap |
| `deliver` | Input id (`uuid`, `clientUserMessageId`) | `reconcile` if capable, else redeliver: at-least-once, with the id visible for dedupe |
| `answer` | Approval id | `reconcile`, else `uncertain` in attention. Success is read from the harness's item event, never inferred |
| `admit` | None: Platoon mint has no idempotency | Never retried. Spawn fails, reservation released, orphan recorded as a gap |
| `workspace` | Path and branch | Inspect, adopt or fail. Never discard uncommitted work |
| `interrupt`, `stop` | None | Repeat. These bypass per-agent ordering, so Esc works while a delivery hangs |
| `erase` | None | Repeat: erasing twice is harmless |

- **Live timeouts.** An effect stuck in `started` past its `timeout` becomes `effect.uncertain` without a crash. `effect.start`
  sets a timer for it, and `effect.finish` clears that timer.
- **Recovery** is one function: take `lock`, write `runtime.started`, then per agent **reap, resume,
  reconcile, dispatch**. Every `started` row becomes `effect.uncertain` and its declared policy applies: `retry`,
  `reconcile` or `surface`. `reconcile` needs a live link, so it runs after resume, and it is `unknown` when resume is
  unavailable. A turn in flight becomes `turn.lost` plus a gap, because its tool effects are unknown and never re-run.
  `retry` appends `effect.retried`, which returns the effect to `requested`. `reconcile` and `surface` stay `uncertain` until
  `effect.finish` or `effect.fail`. `Kernel.recover()` does the journal's part of this, including `turn.lost`, whose data names
  the gap `crash_window`; the incarnation is the version of `runtime.started` on the stream `runtime`.
- **Tool side effects inside a harness are observed, not ours.** We do not perform them, so we do not retry them.

**Timers.** A `timer.set` event sets one: `{due, op, args, key}`, where `key` names one firing and `op` and `key` are at most 256
characters. The clock daemon sleeps on the injected `Clock` until the next is due, submits `op` as `runtime` under `key`, then
submits `timer.clear`. A crash between the two fires again under the same key, which answers from the journal, so the op runs once.
A refused firing is still cleared and stays journaled. A firing that left no event, because the writer was busy or its commit
failed, stays set and is tried again. Any op can emit `timer.set`, and `timer.cleared` to cancel.

### 5.5 Views

A `View` is a class with a schema, `@fold` methods, and typed query methods. Core and extension views are identical
in kind. Other code reads a view through `txn.view(Tasks).open_in(queue)`, never through its SQL, so a table layout is
not an API. Its tables are named `v_<name>`, or start with that and `_`, and no two views share one. A version bump drops and
refolds that view, and so does finding its high-water mark behind the journal, which is what a toggled extension leaves. Folds
ignore unknown types, which is why unknown events survive. `@fold("*")` sees every event, for a view that cannot name what it
counts, as `Waits` cannot. CI compares live views to a rebuild after every scenario.

A rebuild runs under an SQLite authorizer limited to the view's own tables, so a fold that reaches out fails loudly. A fold
never sees `outcome`, which does not exist yet when a live fold runs.

**One event, many folds** is how a transition stays atomic. `agent.ended` is one event. In that one transaction `Waits`
cancels the agent's waits, `Budget` returns its reservation, `Tasks` frees its leases, `Deliveries` marks queued
input undeliverable, `Approvals` closes pending requests as moot, and `Principals` revokes the token. The op adds one
message to the monitoring agent's inbox.

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
| Payloads | Op names and keys 256 chars, stream names 512, `gist` 280, `data` 16 KiB, bodies 64 KiB inline, larger in `blobs/`, every list paged |
| Readers | They pull, so a slow client costs only its own lag |
| Live text | One 256-frame ring per agent; overflow drops frames with a `lag` marker. The final `item` is authoritative |
| Harness output | Pipes always drain. A driver that stalls its harness's stdout stalls the harness. Reports buffer in a bounded queue; a quota breach stops that agent with a gap |
| Inbox | A depth cap returns a `full` receipt, journaled, never a silent drop |
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
caller's identity by name or alias (law 6), and a `tool` with no description.

One definition reaches every surface.

| Surface | Derivation |
|---|---|
| Python | `session.call("task.claim", ...)`; typed facade methods are thin wrappers, checked against the registry by a test |
| MCP | `tools/list` is the `tool=True` ops granted to the token's role; `additionalProperties: false`; `readOnlyHint` set honestly, never enforced |
| `ph` | One stdlib file on the agent's `PATH` only: `ph task.claim --queue tasks`. It builds argv and help from `ops.list` for its token |
| CLI | `platoon-harness tasks claim ...` for curated groups, `platoon-harness op <name>` for any op, flags built from the schema |
| Web | `POST /x/command {op, args, key, expected_version}` |
| TUI | Palette entries and generated forms; buttons come from `actions[]`; disabled entries carry `authorize`'s reason |

**The tool-plane idempotency key** is the client's anchor when present (`claudecode/toolUseId`, Codex `callId`), else
derived from `(turn, op, canonical args hash)`. Either way a harness retry after a timeout is one logical operation.

**Commands and queries.** A query enters no history and reads a read connection. A command is journaled and returns a
result. An agent's read of content is a command, because it records exposure. A human's read of the same content is a
query. A query that decoding refuses leaves no event, so the tool plane submits an agent's `invalid` query again: `submit` refuses
it the same way and journals it, which keeps law 6.

**Refusals are data:** `{code, op, object, reachable?, retry_after?, detail}`. Codes: `not_permitted invalid not_found
conflict stale_fence lease_lost queue_full queue_empty over_budget unsupported busy unavailable key_reused undeliverable`.
`over_budget` is policy; `unavailable` is infrastructure. Each tool description ends with what a refusal means and what
to do next.

| Area | Commands | Queries |
|---|---|---|
| Session | `session.close` `session.cancel` `topology.patch` `episode.open` `episode.close` `budget.set` | `session.status` `session.manifest` `topology.show` `ops.list` `budget.status` |
| Agents | `agent.spawn` `agent.finish` `agent.interrupt` `agent.cancel` `agent.retire` `agent.takeover` `agent.release` | `agent.list` `agent.status` `peers` |
| Messages | `message.send` `message.read` `channel.create` | `channel.list` |
| Board | `board.post` `board.revise` `board.get` `board.query` | |
| Queue | `task.add` `task.claim` `task.renew` `task.release` `task.complete` `task.fail` | `task.list` |
| Wait | `wait` `wait.cancel` | |
| Humans | `approval.resolve` | `attention.list` `view.watch` |
| Evidence | `blob.put` | `blob.get` `lineage` `exposure` |
| Evidence, kernel | `body.tombstone` | |
| Runtime only | `agent.report` `delivery.offer` `delivery.confirm` `approval.request` `effect.start` `effect.finish` `effect.fail` `effect.expire` `timer.clear` `runtime.start` `principal.add` `principal.revoke` `grant.add` `grant.remove` `wait.release` `lease.expire` | `effect.ready` `timer.next` |

An agent's `board.get`, `board.query` and `message.read` are commands; for a human or a program they run
as queries and write nothing. `task.claim` writes a lease, so it is a command for everyone. `reply` is `send(reply_to=)`.
Broadcast is `send("+group")`. `join` and `wait_any` are `wait` with `mode`. Ack is `read(after=n)` or `wait(after=n)`.

### Library tier

`platoon_harness.patterns` uses the public API only: `scatter`, `gather`, `reduce`, `barrier`, `latch`, `semaphore`,
`lock`, `request`, `vote`, `supervisor`, `population`, `map_reduce`, `verifier_generator`. These are compositions, never
scheduler modes.

An episode **program** is an async function holding a `program` principal, so control flow never enters config.

## 7. Primitive semantics

Each statement here is a promise with a test.

### Inboxes and topics

- **`inbox`**: one per agent (`inbox/<id>`). **`topic`**: one stream per channel (`channel/<name>`); `+group` has an
  implicit topic.
- **Order.** Total per stream. Nothing is promised across streams.
- **Delivery.** At-least-once to the driver, deduped by event id. Delivery states are `offered` (the runtime handed it
  over), `delivered` (the driver confirmed injection; this is observed exposure), `acked` (the agent's next read or
  wait moved past it). None means understood.
- **Cursors** are per `(reader, stream)` and held by the server. An omitted `after` means the reader's server-held
  cursor, never the head. `after=n` acks up to `n`, clamped to the highest offered, so a hallucinated number acks
  nothing unshown. A cut-off wait confirms nothing. A filtered read never moves past what it left out.
- **Broadcast.** One entry plus a recorded member list and group generation. That snapshot is its audience. Late joiners
  see history only if the channel says `history = "full"`.
- **Entries** are a capped `gist` plus an optional body. A digest shows gists. Exposure of a gist is recorded separately
  from exposure of a body.

**Injection** is `pull < next-turn < wake < steer`, set per channel on the reader's side, so a sender cannot buy a wake.
`wake` starts a turn if the agent is idle. `steer` asks for the earliest boundary the harness has and degrades visibly:
`tool`, then `model_call`, then `turn`. Tool results of coordination ops also carry pending `steer` notices, which gives
a tool boundary on any harness whose tools are visible. `coalesce` merges wakes into one turn.

**Hop limit.** Every message carries `hops`, one more than the largest in its `cause`; a human message resets it. A wake
past `max_hops` is refused and shown in attention. This bounds reply loops that budgets only make expensive.

**The monitor.** `spawn` installs a monitor. When an agent finishes, or a turn ends with no `finish` and no open wait,
the runtime posts the turn's final text to the spawning parent's inbox, as a runtime-authored event naming the child as
subject. It wakes at most once per causal chain and stops at `max_hops`. So a worker reports back even if its harness
hides our tools. Tools add power rather than being the only way in.

### Boards

Objects have stable names and immutable versions (`board/<board>/<name>`). `board.revise` requires `expected_version`; a
conflict returns the current version and silently overwrites nothing. `board.query` is structured; results carry exact
refs, the true total and a cursor. Text search uses SQLite FTS5 when present. Semantic search is an extension. A board
object version with a body is also how artifacts are stored.

### Queues

One stream per task. States: `open → claimed → done | failed | dead`.

- **Claim.** Atomic, one live lease, fence = `seq` of the claim event.
- **Expiry.** A lease is live until `lease_until` by the transaction's clock. `task.claim` treats an expired lease as
  free, so a late clock cannot break correctness. `task.complete` after expiry is refused `stale_fence` even with no
  reassignment.
- **Fence default.** The caller's live lease, because a model can lose an integer to compaction.
- **Renewal.** The host renews from observed harness activity up to `lease_max`. `task.renew` stays for programs.
- **Retries.** `max_attempts`, then `dead`, shown in attention.
- Exclusive ownership is **not** exactly-once execution. External effects cannot be fenced by us, and the docs say so.

### Wait

```python
wait(on=[...], mode="all" | "any", after=None, timeout=None, hold=None)
on(stream, types=..., n=1, distinct=None)   # join, wait-any, version watch and barrier are this one condition
```

- Check and registration are one transaction from `after`, so the read-then-subscribe race cannot exist.
- `Waits` folds progress (`have`, `need`, `missing`), which is what the UI shows.
- **Parks by default.** The tool result says the wait is registered and to end the turn. When the turn ends the agent is
  `waiting`. When the condition holds, the runtime starts the next turn with its delivery attached. If the model keeps
  working, the wait stays open and nothing breaks.
- **`hold`** keeps the call open below the driver's `tool_timeout_s`. On expiry it returns `pending` with a cursor; the
  agent may call again. A one-shot driver cannot park, so `wait` beyond `hold` is refused `unsupported` with the reason.
- **Tool arguments are friendly** (`agents`, `from`, `tasks`, `board`) and compile to `on(...)`, so a model never learns
  stream names. The Python sugar is `lead.finished()`.
- A parked agent whose harness cannot resume is `lost` through the normal ended transition.

**Barrier** is library code: a topic plus `wait(on(..., n=members, distinct="actor"))`, with member snapshot and generation
fixed at creation, `timeout`, and `on_failure = shrink | break | wait` driven by monitor events. A member joining later
does not join that barrier. **Lock** and **semaphore** are tokens in a queue, which gives lease and fence for free.

### Lifecycle

- **Spawn** is topology check, budget reservation, `admit`, `workspace`, `launch`. Depth comes from the parent record,
  never from arguments. A child never holds more than `may_spawn` allows. Membership changes only on success.
- **Ended transition.** `finish`, `cancel`, `retire` and `lost` are one event, `agent.ended{status}` (§5.5).
- **`on_parent_exit`** is a role policy: `cancel-subtree` or `adopt`. Orphans under `adopt` belong to the session.
- **Retiring** removes an agent from relations, never from history.
- **Takeover.** `agent.takeover` holds deliveries, and the human drives the native session; `agent.release` returns it and
  records a gap. Human-driven turns carry human identity. Disabled with a reason on harnesses without resume.

### Completion

`settled` means, checkably: no open turn, no deliverable delivery, no requested or started effect, no due timer. A human
message can un-settle a session. Only `close` ends it. `until` picks when a headless session closes: `"settled"`,
`"role:lead"` or `"program"`. All stop at budget exhaustion. A team with no root uses `"settled"`.

### Approvals

Four facts stay apart: `approval.requested`, `approval.resolved` (a principal decided), `effect.finished` (the answer reached
the harness), and the observed item outcome. Codex's `accept` does not fix the result, so the UI reports the last.

`resolve` carries `expected_version`: the first commit wins, and the loser gets `conflict{resolved_by, via}`, shown as
information. **Approval policy is a durable session setting** (`ask`, `deny`, `allow`, per role), journaled at open. A
headless session states one before its first turn. An `ask` that no human can answer ends with exit 4. A message from an
agent can never carry an approval.

### Budgets

`Budget` holds limits for `tokens`, `usd`, `turns`, `agents`, `wall`, shared and per role.

A wake reserves an estimate; turn end reconciles it. So overshoot is bounded by the largest turn's cost times the live
agents. Spawn reserves in the admission transaction.

Measurements carry a label: `provider`, `estimated`, `lower_bound` or `unavailable`. A limit in a unit a role cannot measure
is refused by `team check`, or falls back to `turns` when the team says so; it never silently stops enforcing. Native
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
| `edges` | Who may send to whose inbox, as `role: [relation...]` |
| `channels` | Each with `kind`, `writers`, `readers`, `delivery`, and kind-specific fields |
| `groups` | Named membership rules: `roles`, `members` (principal ids), or `order`, which `next` and `prev` walk. Each change bumps the group's stream version, which is its generation |
| `limits` | `max_depth` `max_children` `max_live` `max_hops` |
| `grants` | Written-out `(who, ops, on)` rows, which is how an extension's op reaches a role |
| `program` | Optional control flow, in Python |
| `until` | §7, Completion |

**Selectors** are the same everywhere: `self parent children siblings ancestors descendants next prev human program all
role:x group:x`. They are evaluated on the live graph. A channel in a team has no agent to be relative to, so its `writers` and
`readers` take only `human program all role:x group:x`.

**Rules.** Default deny. Presets and keys form a union, `a | b` in Python, so order never matters and the hash cannot tell how a
topology was mixed. Edges and grants add up. There is no `deny`, because it would make mixing non-commutative. Two sources defining
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
- **The tool set** is fixed per role at launch, since live tool-list updates vary by harness. Valid targets change, so `peers`
  and the turn preamble list them; tool schemas never enumerate them.
- **Runtime evolution.** `spawn` adds members and journals `group.changed`. `channel.create` is a grant: a creator may name
  only readers and writers within its own reach. `topology.patch` comes from a human or program, and every event carries
  `topology_rev`.
- **`team check`** runs before any cost and reports everything at once. It refuses recursive `may_spawn` without `max_depth`, a
  cycle without `max_hops`, a budget unit a role cannot measure, and an unknown preset, harness, extension, role, group or auth
  profile. A cycle is a loop of wakes between roles. A reply up a tree is not one, so `parent`, `children`, `ancestors` and
  `descendants` edges never count, and neither does a channel or inbox that does not wake. It warns of a role that can never
  start, a role with no path to anyone, an entry that can wake more than 8 agents, and a setting no primitive enforces yet.

## 9. Drivers

One driver instance per agent.

```python
class Driver(Protocol):
    def describe(self) -> DriverInfo: ...                        # name, version, login kind, capabilities. Starts nothing
    async def start(self, spec: AgentSpec, report: Report) -> Started: ...   # fresh, or resume from spec.resume
    async def deliver(self, delivery: Delivery) -> Receipt: ...  # delivery.boundary is one the driver declared
    async def interrupt(self) -> Receipt: ...                    # stops at the boundary it can, says what was queued
    async def answer(self, approval: str, verdict: Verdict) -> None: ...
    async def reconcile(self, input_id: str) -> Reconciled: ...  # landed | not_landed | unknown
    async def stop(self, grace: float) -> None: ...              # ends the process tree it owns
```

`AgentSpec` holds agent, role, goal, cwd, model, tool binding, model access (`Secret` values, URLs included), env,
instructions (appended by the supported path; native project files are never touched) and resume.

`report` takes this vocabulary and no other: `ready{native, version, effective_model, tools_visible}`, `turn.started`,
`turn.ended{reason}`, `delta` (lossy), `item{kind: message|thought|tool|patch, phase, native_id, gist, body}`,
`input.delivered{input, boundary, evidence}`, `approval.requested`, `model.call`, `usage{scope, label}`,
`compacted{forgotten}`, `child.seen{native, parent, attribution}`, `gap{plane, what}`, `native{kind, raw}`, `exited`. Unknown
frames become `native` plus a gap, never a log line.

### 9.1 Wire

Another process or language speaks line-delimited JSON-RPC 2.0 on stdio, split on LF only, logs on stderr. `WireDriver(command)`
is the only adapter, verbs equal the Python methods, and `protocol` is an integer refused when unknown. OpenHands runs this
way in its own environment, because its dependency set cannot share one with others, so the custom-driver path is real and
exercised.

```jsonc
> {"jsonrpc":"2.0","id":1,"method":"start","params":{"protocol":1,"spec":{"agent":"ada","role":"worker","goal":"...","resume":null}}}
< {"jsonrpc":"2.0","id":1,"result":{"native":"s-9"}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"ready","version":"1.4.0","effective_model":"m","tools_visible":null}}
> {"jsonrpc":"2.0","id":2,"method":"deliver","params":{"input":"d41","boundary":"turn","items":[{"ref":"inbox/ada@3","gist":"Keep the API stable"}]}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"input.delivered","input":"d41","boundary":"turn","evidence":"message_start"}}
```

A simple one-shot CLI needs no code: `harness = { command = ["my-agent", "{goal}"], mode = "oneshot" }` runs under the `exec`
driver, coordinating through `ph`. PTY integration is an explicit degraded fallback, not a substitute for structured events.

### 9.2 Capabilities

Absence means unsupported, as in ACP.

| Field | Values |
|---|---|
| `persistent` | One-shot workers cannot park |
| `resume` | Native resume available |
| `boundaries` | Subset of `turn`, `tool`, `model_call` |
| `tool_paths` | `mcp-http`, `mcp-stdio`, `shell` |
| `tool_timeout_s` | The harness's cap on one tool call |
| `interrupt` | `none`, `turn`, `tool`, `call` |
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
- **Conformance.** `check_driver(driver)` runs named checks and reports all failures at once, against a loopback model that logs
  each request. So "tool in the first model request" and "delivered text in the next prompt" are tested against ground truth,
  and "connected" counts for nothing. Results pin to `(driver, harness version)`.
- **Model pinning.** The effective model must equal the requested one, and a driver refuses an unset model where the harness
  would otherwise pick a hosted default.

### 9.4 Levels

`levels(capabilities, profile, conformance)` is a pure function giving `operational`, `observable` and `trainable`, each with
reasons, journaled in `agent.started` beside `declared` and `verified`. No driver can claim a level.

### 9.5 Mappings

| Harness | Path | Notes that matter |
|---|---|---|
| `claude` | `claude -p` stream-json plus control protocol, stdin held open | HTTP MCP with `alwaysLoad`; `uuid` on every input; `--permission-prompt-tool stdio`; `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` for workers, since a result is not a turn end while background tasks run. Never `ANTHROPIC_BASE_URL` without a gateway credential |
| `codex` | `codex app-server` over stdio, no `experimentalApi` by default | `turn/start` idle, `turn/steer` with `expectedTurnId` active; `approvalsReviewer: "user"`; `default_tools_approval_mode: "approve"`; interrupt walks descendants; `item/completed` is truth. `ph` is blocked by the default sandbox, so MCP is the path |
| `pi` | `pi --mode rpc` | `prompt`, `steer`, `follow_up`; `agent_settled` is `turn.ended`; `exposure: direct`; `gated` approvals through a shipped extension; cache warming off when trainable |
| `openhands` | Wire worker on SDK `arun()`, own environment | Boundary is the next LLM request; `llm_response_id` gives `model.call`; `Condensation` gives `compacted{forgotten}`; hold deliveries while an approval is open, since `send_message` supersedes it |
| ACP agents | Generic driver, protocol 1, `fs` and `terminal` false | Turn boundary only; raw frames captured before parsing; `steer` only after a fixture passes. OpenCode must set `codemode: false`, or tools hide behind Code Mode, and must never run with an unset model |

## 10. Tool plane

The SDK ships a tiny tools-only MCP server: Streamable HTTP on loopback with a per-agent bearer token, plus a stdlib stdio
shim for harnesses without HTTP. It is ours rather than the `mcp` package because that package cannot share an environment
with `platoon[ors]` or OpenHands, and because we need strict argument refusal and token-only identity. It is contract-tested
against the official client and against each real harness.

- Tokens are per `(session, agent)`, short-lived, revoked at `agent.ended`, and hashed in the journal. Re-supplied on resume.
- Identity never comes from `clientInfo`, `_meta` or arguments. `_meta` anchors are correlation evidence only.
- `tools/list` is filtered by authorization and enforced again at call time.
- Coordination state uses explicit handles (`cursor`, `lease`, `version`). No session semantics.

**Everyday instruction surface.** The turn preamble and the tool descriptions teach the tools. We append through each harness's
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

**Late joins.** A tool op can commit before the model call that caused it is reported. `call.joined` is a new event citing both,
with its quality (`anchor`, `response_id`, `turn`). Tools link to a model call only through a real anchor.

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
can exist. Three views answer the five questions, through `view.watch(name, after)`: a snapshot, then keyed changes.

| View | Row | Answers |
|---|---|---|
| `roster` | `agent, role, harness, model, state, activity, why, unread, levels, usage` | Who is working, on what, what is blocked |
| `attention` | `id, kind, agent, gist, since_seq, version, actions[]` | Where you must act: `approval`, `mention`, `uncertain`, `failed`, `dead_task`, `budget` |
| `changes` | `agent, path or commit, added, removed, tests, since_mark` | What changed. A runtime probe at each `turn.ended` feeds it, so opaque harnesses are covered |

`why` is typed: `Approval(id)`, `Wait(have, need, missing)`, `Budget(kind)`, `Lease(id)`, `Peer(id)`, `Timer(at)`, `Infra(detail)`,
`Lost(reason)`, so "barrier 2 of 3, missing w7" needs no guessing. `needs-you` is a derived group, not a state. `actions[]` are
op references with `expected_version`, so any client can draw the buttons.

- **TUI.** Textual. One 15 Hz coalescer between the journal and widgets drops render frames, never events. `TranscriptView` is on
  the Line API with paging from the journal, so history is virtual. Untrusted text crosses one `SafeText` boundary, and a lint
  bans bare `str` in label-like widgets. Approvals never take focus. See [tui.md](tui.md).
- **SwarmChat.** A follower folds the journal into its own rebuildable `swarmchat.sqlite` and serves the pinned, hash-checked
  frontend assets, the `view_*` replies, an overlay, and one `/x/command` route into the same ops. Upstream's server never runs,
  and nothing re-ingests the projection, so two authorities and echo loops have no path. Direct chats key on the unordered
  participant pair, with both inboxes merged in journal order; channel chats key on the channel. One session per port avoids
  the `localStorage` collision. "Read by" becomes "Delivered to". See [swarmchat.md](swarmchat.md).

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
    async def admit(self, spawn: SpawnRequest) -> Admission: ...       # model access, tool endpoints, workspace, attribution
    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None: ...
    def budget_owner(self, resource: str) -> Literal["session", "authority"]: ...
```

`LocalAuthority` issues session-scoped identity and leaves the harness's own auth alone. `PlatoonAuthority` lives in the
`platoon-harness-platoon` extension, built on Platoon's stable function-harness and program seam.

- **Two admission routes.** Tree children use `ctx.agents.spawn` with a member harness, which gives forks, grading and depth. Peers
  with no fork use `POST /v1/platoon/agents`. Mint is never retried.
- **Root.** A single-entry tree uses `ctx.endpoint`, which preserves RAO's depth and row shape. Mesh and git-swarm use a zero-call
  root, labelled as a mapping artifact. The root samples the default policy, so `team check --trainable` refuses a mismatch.
- **Credentials.** A path-form URL is a credential. It is normalized to origin plus bearer before a driver sees it.
- **Eligibility** is `eligibility(agent, episode)`, a pure function of the record with no stored flag. Anything outside an episode
  fails by default, as do frozen agents, judges, humans, shared keys and unverified profiles. Platoon still decides.
- **Reward data** stays in `annotations.sqlite`, which no agent-reachable read opens.
- **Limits at Platoon 0.5.** `AgentGraph`, `RewardEvent` and attribution levels are draft-only there, so they are not integration
  targets. See [training.md](training.md) for the bridge, the RAO golden fixture, the no-extra-rollout baseline and the proposed
  amendments.

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

- **Secrets.** Config holds env var names, never values. `Secret` refuses serialization. Redaction covers values, their encoded forms, and URLs.
  No model-access credential reaches a log, event, artifact, export or resolved config.
- **Bodies and retention.** A body can be tombstoned while its hash survives, so the graph stays whole. A secret in a `gist` needs an
  offline rewrite that produces a new session. See [security.md](security.md).
- **Plan logins.** We spawn the user's own harness under its own login and never read, copy or proxy a credential. Headless multi-agent on a plan
  login exits 78 and names the fix unless the user opts in. `web --remote` refuses a second person on a plan-login session.
- **Project config is untrusted.** It can select installed components but can never install one, and a `command` harness in a project file needs
  an explicit trust step.
- **Harness env.** An allowlist, per process. The driver strips variables that change a harness's behavior or leak the parent's identity.

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
are caught before any code loads or any cost is spent. Installing activates nothing: a role names a harness, a team names `extensions = [...]`, and
`name@version` and `module:attr` are always accepted. First-party and third-party extensions use the same contracts.

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
- **`deny` rules and sender-chosen wakes:** deny breaks commutativity; wakes belong to the reader.
- **Multi-machine workers in the first release:** the wire allows them. No fleet code until a user exists.
- **Login flows and credential brokerage:** each harness signs itself in.
- **Raw frames for every harness:** only unknown updates keep their frames, since a spool is a second durable path and a scrubbing problem.
