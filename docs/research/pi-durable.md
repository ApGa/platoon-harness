# Pi Durable

Reviewed on 2026-11-03 against Pi v1.5.0 (`packages/durable`, MIT) and platoon-harness commit `4d5e6c5`. Pi paths are relative to the Pi
repository, ours to this one.

Five analysts read Pi Durable's source against our design and code, and a sixth ran it against a local fake model
([spike record](spikes/pi-durable.md)). A fact-checker then opened the citations and tried to refute every claim, including our claims to
already have something. A taste reviewer argued against every proposal. An idea is adopted here only if it survived both.

No real model, provider, Platoon gateway, Claude Code or Codex ran in this review.

## Answer

Pi Durable is a harness one layer below us, beside Claude Code and Codex, so it is not useful as a backend or dependency and we should not build on it. It is useful as a comparison: its rules on crashes, waits and ownership transfer even where its mechanisms do not. Holding our design against it found 41 defects in ours, 13 of them major, led by a lost turn that stalls a session silently, a join that costs one turn per child, a waiter's own cancel that hangs its join, a session that settles short of `until` and hangs, and `finish` silently cancelling working children. Twenty changes survived both attacks, none adds a concept and most are small: 3 land now, 12 in drivers, 2 in clients, 2 in M2 and 1 in M4. Every defect was judged against commit 4d5e6c5 and the live repository has moved on through commits touching the same code, so each must be rechecked before fixing.

Rerunning the saved probes at `61f6230`, after the runtime review's five fix commits, reproduced the join that costs a turn per child,
cancel-then-join, `finish` over a working child, a session settled short of `until`, and a lost turn that leaves a session settled with
nobody told. The other defects below are rechecked as they are fixed. [STATUS](../STATUS.md) says what has landed.

## Decisions

| # | Idea | When | Cost |
|---|---|---|---|
| 1 | Refuse `finish` over working children (adapt) | before drivers | S; no new concept, one refusal |
| 2 | A report the parent is counting does not wake it, unless the child ended badly (adapt) | before drivers | S; no new concept |
| 3 | A session settled short of `until`, with nothing scheduled, says `needs_human` (adapt) | before drivers | S; no new concept, a new path to an existing reason |
| 4 | Tell an agent its turn was cut off (adapt; merges durability-tell-the-agent and driver-tell-the-model-after-a-crash) | with drivers | S; no new concept, one runtime op over `post` |
| 5 | Sweep crash points by cutting a journal (adapt) | with drivers | S; no new concept, test support |
| 6 | Roster row: closed `phase`, `stopped`, `parent`, `held_by` (adapt) | with drivers | S; three row fields and a closed literal |
| 7 | Write down that text is fixed at launch (adapt) | with drivers | S; no new concept |
| 8 | A ceiling on tool list size (adapt) | with drivers | S; no new concept |
| 9 | Refuse a query result over the limit (adopt) | with drivers | S; no new concept |
| 10 | `call_id` on `Item` and `Usage` (adopt) | with drivers | S; two optional fields |
| 11 | Report pi's `responseId`, fix the compat row (adapt) | with drivers; the claim at M3 | S; no new concept |
| 12 | `purpose` on `ModelCall` (adapt) | with drivers | S; one optional field |
| 13 | Store the compaction's summary, expand a position into `forgotten` (adapt) | with drivers | S; one optional field, no second position form |
| 14 | Draw a child under the call that started it (adapt) | with drivers and with clients | S; no new concept |
| 15 | Implement `reconcile` on pi through get_entries (already in the contract; a driver detail) | with drivers | S; no new concept |
| 16 | Make live text a tail bound to its item (adapt) | with clients | S; one field |
| 17 | A stop that reaches a subtree and keeps its agents (adapt) | with clients | S; no new concept |
| 18 | A failed commit ends the runtime (adapt) | M2 | S; no new concept, one small path. A full disk loses every open turn |
| 19 | A context version names a derived view (adapt) | M2; `native_id` in the drivers stage if cheap | M; one field on a designed type |
| 20 | Extension guide with a run-tested example and a footguns list (adopt) | M4 | M; no new concept |

## The changes

**1. Refuse `finish` over working children (adapt).** In packages/sdk/src/platoon_harness/primitives/lifecycle.py, `agent.finish` and `agent.retire` refuse `conflict`, naming each live descendant reached through cancel-subtree edges that is `spawning`, `waking` or `running`. `waiting` and `idle` do not block; an `adopt` child and its subtree do not block. `agent.cancel` is unchanged. Update both op descriptions and architecture section 7, and state the limit: this does not cover a one-shot parent (lifecycle.py:322-325) or an `Exited` harness.

Why: `end` cascades with no refusal (lifecycle.py:116-120), cancel-subtree is the default (team.py:90), and probes show a child mid-turn ending `cancelled`, unheard. Pi's rule transfers but its `completing` hold does not (packages/durable/docs/spec.md:2694-2704, packages/durable/src/harness/scheduler.ts:2433-2450): a hold needs an escape, as its own footgun says (spec.md:6389-6394). Serves BRIEF line 136.

**2. A report the parent is counting does not wake it, unless the child ended badly (adapt).** In `_monitor` (primitives/lifecycle.py:69-77), when the report advances an open wait of the parent and the child `finished`, post at `next-turn` through `post`'s existing downgrade. Keep the wake otherwise. `agent.ended` is emitted after `_monitor` (lifecycle.py:98-99), so read the parent's open conditions, not a fold result. Add a line to RFC 0012, whose Decision says the monitor wakes.

Why: Probe: a lead parked on three children is woken at 1 of 3, against primitives/waits.py:347 and BRIEF.md:144. This ends the N-turn join and gives a model fail-fast with no new wait grammar. Pi's waiter stops until all of `on` is terminal (spec.md:2729-2747).

**3. A session settled short of `until`, with nothing scheduled, says `needs_human` (adapt).** Add to `session.status` whether anything the journal knows is scheduled: timers, plus the wait deadline `work().due` already holds (primitives/delivery.py:65-69). In `Session._settling`, return `needs_human` when settled, not done, `until` is not `program`, nothing is scheduled and no other client holds control.

Why: Probe: `settled()` with no timeout never returns (session.py:399-411), against BRIEF.md:238. Pi's cycle check is a task-graph check and cannot transfer (scheduler.ts:2461-2470). Ours also catches two agents waiting on each other. An extension daemon's private schedule is invisible to the test.

**4. Tell an agent its turn was cut off (adapt; merges durability-tell-the-agent and driver-tell-the-model-after-a-crash).** After a successful `_resume`, and only while accepting, post one fixed runtime notice to the agent's inbox with a wake: the turn was cut off by a crash, tool calls may have run in part or in full, nothing was repeated, check before repeating. No list of committed calls. Change runtime/recovery.py and primitives/lifecycle.py, and fix the docstring at primitives/clients.py:116, since `turn.started` will lower the row (clients.py:122-124). Replace the 'carry on' in tests/integration/test_crash.py:133-137. Name a test for the budgeted case: `turn.lost` counts unmeasured (primitives/budgets.py:125-138), a metered limit without fallback=turns refuses the wake (budgets.py:206-210), and that session must end `needs_human`. Re-read lifecycle.py and recovery.py first.

Why: The largest gap found, and it needs no model loop. Today the agent goes idle and nobody tells it (primitives/agents.py:134-136); the lost-turn probe shows settled true, a parked lead and workers idle on live leases. Pi tells the model only for a plain tool (packages/durable/src/harness/tool.ts:208-226, spike s2); a safe tool reruns and an in-flight model request is resent, and the model hears nothing (s2, s2b). A message serves every harness. Serves the BRIEF Retry/crash row (line 355).

**5. Sweep crash points by cutting a journal (adapt).** One scenario marked `slow`, with a driver that resumes and idles so no script can raise. Cut the journal at each boundary, dropping its triggers because law 1 aborts DELETE, resume, and assert no exception, no `started` effect and rebuild equals live. Add the helper to tests/unit/runtime/support.py. Land it with the crash notice, which adds the path it guards.

Why: One writer means the journal enumerates its own crash points, though a cut is a legal crash state for the journal only: blobs, agent folders and process records stay from a later time. The probe covered 124 of 159 boundaries at about 0.7 s each with no kernel defect, so this is a guard, not a known fix. It came from the comparison, not from Pi, whose recovery tests hang storage or drop a held commit (packages/durable/test/harness-restart-failure.test.ts:60-75).

**6. Roster row: closed `phase`, `stopped`, `parent`, `held_by` (adapt).** Make `Item.phase` a closed literal of started, completed, final and decided (primitives/reports.py:84). State in docs/drivers.md that a driver sends `started` where the harness shows it, so `activity` (primitives/agents.py:174-176) reads the running tool. Add `stopped`, `parent` and `held_by` to the row (primitives/clients.py:228-239). Add no list of running tools and no fold. Fix bug-clients-1 first.

Why: The contract is being written now, and `activity` misleads without a `started` item. A running list would be a second answer to one question and leaves phantom rows if a `completed` is lost. Pi's model: spec.md:4601-4610, 4635-4645.

**7. Write down that text is fixed at launch (adapt).** State in architecture section 10 that the tool list and preamble are fixed at launch and later changes travel in a delivery. Rename `turn preamble` to `preamble` (tools/surface.py:155). Add a `check_driver` row that the preamble appears once per request. Record tool-block stability in docs/compatibility.md as a measurement, not a gate.

Why: Stops a the drivers stage driver resending the preamble because of its name. Pi treats prefix bytes as a budget and change as positional (packages/durable/src/harness/prompt.ts:66-93). Unchecked on a real harness.

**8. A ceiling on tool list size (adapt).** A test in tests/unit/tools/test_surface.py with a ceiling just above today's size for the default manager-worker roles, in one stated JSON form. Separately, drop `tool=True` from `task.renew` (primitives/tasks.py:305), which docs/architecture.md:563 says stays for programs.

Why: That text is in every request of every agent and enters training prompts at M3. A worker has 21 tools at about 22 KB of full list_tools JSON, and `wait` alone is about 2.4 KB. An exact pin would trip on every wording fix.

**9. Refuse a query result over the limit (adopt).** In the query branch of `_run` in tools/mcp.py, refuse a result over `_RESULT_LIMIT`, saying how to narrow. Refuse, do not cut: a generic cut cannot keep JSON valid. An op with nothing to narrow by needs paging first, and `peers` does.

Why: docs/architecture.md:910 promises 32 KiB and queries have no cap (kernel/kernel.py:436). An extension query returned about 1 MB through a real ToolServer. Only queries can overflow, so a refusal never contradicts a committed event. Pi bounds every tool result (packages/durable/src/harness/tool.ts:700-701). Serves BRIEF section 12.

**10. `call_id` on `Item` and `Usage` (adopt).** Add `call_id: str | None` to both (primitives/reports.py:78-88, 114-122). Pass a ModelRef on `item.recorded` and `usage.reported` when the driver gave one (primitives/lifecycle.py:358-364). Keep `call.joined` for the late case only. Add a conformance check, and update docs/drivers.md and tests/public_api.txt.

Why: Harness frames hold both ids (docs/research/fixtures/pi-sample.jsonl:18), the envelope already has the slots (kernel/model.py:105-106), and without a field the driver drops the link. The alternative is inference, which AGENTS.md forbids. Our op to pi's toolCallId stays unanchored (packages/mcp/src/client.ts:405-409), so that stays turn quality. Serves BRIEF sections 6 and 7.

**11. Report pi's `responseId`, fix the compat row (adapt).** In the drivers stage, report `ModelCall(call_id=message.responseId, ...)` from `message_end` and correct docs/compatibility.md:83 and docs/research/adapter-others.md:264. Declare `call_ids="call"` for Platoon's gateway only at M3, after a loopback test with real pi on the real gateway.

Why: Our own fixture contradicts the row. The id comes from the first chunk (packages/ai/src/api/openai-completions.ts:548), and by source Platoon sets chunk ids to its call_id (Platoon platoon/gateway/dialects/openai_chat.py:101). Spike s8 matched on a fake model only; no real gateway or provider was observed. Exceptions: a budget stop, a stream error, retry.provider.maxRetries above 0, and compaction.

**12. `purpose` on `ModelCall` (adapt).** Add `purpose: str | None` to `ModelCall` (primitives/reports.py:106-111), a free native string that is None unless the harness said so. On pi, emit a call at `compaction_end` with its usage. Do not add `outcome` until M3 shows a need.

Why: Training must not read a compaction as a policy sample (BRIEF section 7, compatibility.md:391). Pi Durable writes no entry for a compaction attempt (packages/durable/src/harness/compaction.ts:199-206), which is the shape of a hidden call.

**13. Store the compaction's summary, expand a position into `forgotten` (adapt).** Add `summary: str | None` to `Compacted` (primitives/reports.py:125-127). In `_commit`, store `summary`, and `forgotten` when long, as bodies (runtime/host.py:349-351). State that `forgotten` holds native ids. On pi, expand firstKeptEntryId through get_entries (packages/coding-agent/docs/json.md:136-156, rpc-commands.md:689-699). Test that a long `forgotten` does not lose the agent.

Why: The summary is model text that entered the context, and we cannot represent it today. The body store is required, not a nicety: see bug-provenance-1. No compaction has been observed through pi RPC. Serves BRIEF section 6.

**14. Draw a child under the call that started it (adapt).** the drivers stage: a conformance row, conditional on the harness, that `Item.native_id` equals the MCP anchor where one exists. the clients stage: join `event.native` to `native_id`, falling back to the turn. `agent.spawned.turn` is None because `agent` is the child, so take the parent's open turn at that seq.

Why: The tool plane stamps the anchor, so no convention is needed, where Pi relies on a tool calling api.details itself (spec.md:4046-4049). Claude Code matched 8 of 8 and Codex 0 of 2 (docs/research/spikes/tools-and-parking.md:27-28, read by one analyst only). Serves BRIEF line 160.

**15. Implement `reconcile` on pi through get_entries (already in the contract; a driver detail).** In the pi driver, search user entries from get_entries for the delivery id.

Why: This implements a method already in the contract (drivers/__init__.py:162), so it is not a new adoption. The gain is small: recovery branches only on `landed` for a delivery (runtime/recovery.py:66-76), so finding the id avoids a repeat, and `not_landed` matters only for an answer. Spike s8 ran the entries half; the search itself was not run.

**16. Make live text a tail bound to its item (adapt).** kernel/pulse.py: Ring keeps the current item's text as a bounded tail, and frames(after) yields one Delta joining everything past `after`, with `lag` counting what is no longer held, also on a first read. Delta gains `ended: int | None`, the seq of the event that replaced the text. The host resets the ring after an item of kind message or thought and on turn.ended and turn.lost. Reset needs a new public kernel method, and Delta is public API.

Why: The hand-over property transfers because we own the ring (spec.md:4729-4736, packages/durable/src/harness/live.ts:285-290); durable partials do not and are not needed. Closes bug-clients-2 and bug-clients-4. the clients stage has the first reader.

**17. A stop that reaches a subtree and keeps its agents (adapt).** A client gesture calling `agent.interrupt` over the focused agent's descendants, Stop all as the same loop over every agent, and `session.cancel` a separate labelled action. The client walks `parent`, tolerates `conflict`, and says on screen that it stops turns, not waits.

Why: A human often wants everything below to stop without losing the agents, and today only one agent or the irreversible `session.cancel` is available (primitives/lifecycle.py:219-228, 523-534; docs/research/tui-expectations.md:95). It needs the roster's `parent` and works only once an interrupted child's report goes out at `next-turn`, or each report wakes a parked parent.

**18. A failed commit ends the runtime (adapt).** Try the rule with no constant: a failed commit ends the runtime, as in Pi. Add a count only if a transient case is shown. This needs a small new path from writer to `Runtime.run`, which has no failure channel (runtime/__init__.py:103-111). tests/unit/kernel/test_writer.py and docs/architecture.md:222 must change.

Why: Every failed batch answers `unavailable` (kernel/writer.py:144-147) and Host.insist retries until the kernel closes (runtime/host.py:165-175). Recovery is our tested way back, and a failed commit's outcome is unknown (spec.md:6125-6147).

**19. A context version names a derived view (adapt).** Define `context_at(agent, version)` as a fold of `context/<agent>` when `exposure` is built at M2, and give `Seen` a `forgotten_at` plus an unknown state. Add `native_id` to InputDelivered (primitives/reports.py:91-97) in the drivers stage if cheap. `Seen` and `exposure` do not exist yet, so this is a design note.

Why: It answers acceptance row 356, 'survive compaction', and nothing else does. A compaction with forgotten=None yields unknown, never false. Pi's model: packages/durable/src/harness/context.ts:133-158.

**20. Extension guide with a run-tested example and a footguns list (adopt).** Add docs/extensions.md: one complete extension with op, view, daemon and `check_extension`, run by a docs test; a footguns list; and a table of what is decided when. State no size. Leave AGENTS.md out of the change unless the owner wants it.

Why: A brief deliverable (BRIEF.md:382, acceptance row 360), and agents are the readers. Pi's list of contracts stated with their failures is the model (spec.md:6341-6513), and its snippets are compile-checked (packages/durable/test/spec-usage.test.ts).

## A Pi Durable backend

Decision: skip. A Pi Durable backend would make us own an agent, which the charter rules out, and a user who picked pi would get none of pi. packages/coding-agent does not depend on pi-durable at v1.5.0, so we would supply the prompt, tool policy, compaction settings and an MCP bridge, and users would lose pi's skills, extensions, settings and logins. It has no user, and its last release alone had 34 breaking-change bullets. The gains are reachable at our layer: a crash notice from the runtime, reconcile through get_entries, redelivery from our journal. The door stays open: spike s10 passed check_driver with a 127-line wire program (15 passed, 3 skipped; operational met, observable unverified, trainable unmet on a key), so anyone who wants it can bring it over the wire with no change here.

Against pi --mode rpc. Measured gains: a cut-off plain tool tells the model it may have partly run, a run continues after reopen, lookup of an input by id is exact. A durable queue is by source only. Steer boundaries, gated approvals and per-call ids were equal when run. It used 65 MB against 110 to 117 MB because it contains less agent. Passing 15 checks proves the contract, not that this is a good agent, and stop_leaves_no_process passed only because no tool was running.

Churn: 32 days from 1.0.0 to 1.5.0; source 17,662 to 33,631 lines, spec 4,601 to 6,531. Breaking bullets per release: 1.0.3: 4, 1.0.4: 2, 1.1.0: 2, 1.2.0: 6, 1.4.0: 6, 1.5.0: 34. A backend would need an exact pin and a port every minor.

Spike questions, all seven of which truly ran, against a fake model, each once unless noted. Q1 smallest host: ran; the request body is not stored and is rebuilt from entries. Q2 SIGKILL during a tool: ran; safe tool ran twice and the model was told nothing, plain tool ran once and the model was told it may have partly run, output in the last second was lost. Q2b SIGKILL during a model request: ran; same messages resent after backoff, model told nothing. Q3 same requestId after a crash: ran; same submission, and different text under that id silently returned the old one. Q4 steer: ran on the second try, first run invalid; lands after a tool result, or after the answer on a text-only stream. Q5 watch: ran; 77 callbacks, median gap 101 ms, 12.3 bytes per token, on the faux provider. Q6 second process: ran, one trial each; no refusal, a safe tool reran, a plain tool was reported interrupted while running, readOnly gave a torn snapshot; attach across processes was checked by grep only. Q7 time and memory: ran 3 times; 0.59 to 0.84 s, 65 MB, order of magnitude only. Extras that ran: backend through check_driver; pi rpc on our real ToolServer at 1.4.0 and 1.5.0 (HTTP MCP worked, responseId equals the fake model's id, after SIGKILL the tool survives and a queued steer is lost); pi's bash survives a group SIGKILL while SIGTERM, EOF and abort end it; lost turn on our kernel reads settled, kernel side only; a second identical claim with real pi returned the first; --session-id on 1.5.0 holds. Not run: any real model, a Durable crash with a queued steer, a Durable tool process surviving a kill, reconcile in the backend, approval across a crash, compaction on either.

## What changes next

### Drivers

- Judge everything against the live code first: all of this was read at 4d5e6c5 and the repository has moved on.
- Before the drivers stage starts: refuse finish over working children; counted reports do not wake; settled short of until returns needs_human; fix bug-coordination-1 (cancel-then-join).
- Shared code: the fixed crash notice after a successful resume, the slow journal-cut sweep, and a named test that a budgeted session ends needs_human.
- Contract: `Item.phase` closed, `started` required where the harness shows it, `call_id` on Item and Usage, `purpose` on ModelCall, `summary` on Compacted, `native_id` on InputDelivered if cheap. Update tests/public_api.txt.
- Roster fields stopped, parent, held_by, after bug-clients-1.
- docs/drivers.md lines: `interrupted` as a turn reason, what `forgotten` holds, what Usage.tokens counts, and that a zero on an aborted call means unknown.
- Conformance rows: preamble once per request; native_id equals the MCP anchor where one exists; stop during a running shell tool.
- Query refusal over the limit, tool list ceiling, task.renew no longer a tool, and the 'fixed at launch' sentence in architecture section 10.
- Fix bug-provenance-1 and bug-provenance-2 before drivers report compactions.
- Measure what each harness shows on native resume with a dangling tool call, so the notice does not contradict it. Decide per driver what to do about child.seen (bug-coordination-12).
- pi driver: nothing in the RPC surface changed between 1.4.0 and 1.5.0, so build on the researched protocol.
- pi driver: report ModelCall from message_end, and do not claim the gateway join until M3.
- pi driver: use usage.cost.totalFromProvider, new in 1.5.0, for the usd label; a real provider was not observed.
- pi driver: run tools through the stdio shim, which was not run with pi, so the first driver test must run it. Set the MCP timeout to match tool_timeout_s; the 60 s default is from docs only.
- pi driver: pass --session-id with an id we choose, so native is known before launch (run on 1.5.0 only).
- pi driver: stop order is close stdin or abort, then SIGTERM with real grace, then SIGKILL. After a SIGKILL the tool survives, so report crash_window and treat the workspace as possibly still being written.
- pi driver: declare boundaries turn and model_call only. Treat a dangling tool call on resume as known. Pin the harness version in conformance. --append-system-prompt exists but was not run under --mode rpc.

### Clients

- Live tail with Delta.ended, closing bug-clients-2 and bug-clients-4.
- Stop below, with the screen saying it stops turns and not waits. It needs the roster's `parent`.
- The join from event.native to native_id, falling back to the turn.
- An interrupted or failed child's report says so, and an `interrupted` report goes out at next-turn (bug-coordination-6). Both attackers kept this half, and stop below depends on it.
- A backward read for the transcript: `before` and a set of stream names on Kernel.read, with client rows named `missed`, not `gap`.
- Queue visibility, starting from `unread` for the chip, with a view name added only when the dock line is built.
- TUI notes, ideas only and our own code: a picker that replaces the composer, a spawn row that jumps to the child, a queue line above the composer. No client command queue.
- Draw status from views and read events only for the transcript. Pi deleted watchEvents() for this reason (packages/durable/CHANGELOG.md:56).
- Three decisions needed by the clients stage: the Esc mechanism, how a human steers, and whether withdraw exists. docs/research/tui-expectations.md:86 and :89 depend on them.

## What we already do as well or better

held are one writer enforced at open, key misuse detected, a filesystem WAL cannot trust refused, budgets enforced, grants bounding objects, reader-set injection, approval races telling the loser who won, pull with cursors, boards keeping who and why, check_* functions, and evidence kinds. With limits: on_uncertain for core kinds only; deferred progress only because the harness keeps the transcript; pull for read pages only until the live tail lands; refused collisions for op names, not tool names; memory and group commit figures from the prototype; `ph` not yet run by a real harness; budgets enforce only what is reported. Overturned: 'an effect plus a daemon already covers an extension's durable work', because after a crash only `retry` works, and `_reconcile` has no arm for a third kind (runtime/recovery.py:90-106). The mechanism is built and the contract is not; fix at M4 with bug-durability-4. Also overturned: 'every spawned agent outlives its parent's turns' is false for a one-shot parent.

## Rejected

- Pi Durable as a backend: it makes us own an agent, has no user, and churns heavily. The wire path stays open.
- Phases and a checkpoint per step: a per-step checkpoint belongs to whoever owns the loop, and laws 3 and 5 refuse replay.
- memo: it solves rerun of code, which we never do.
- Group commit with keyed gates: their cost comes from async callbacks and remote storage, and law 3 removes the problem.
- Held `completing` state: a harness kept up or a report held undelivered, plus a second meaning of ended. The refusal covers the real failure.
- Fork a session or a team: native sessions, worktrees, leases and credentials do not fork.
- Journal partial answers: needs the model loop. Pi stores them to recover its own request, and we do not own that request.
- Per-tool `replay: safe`: needs ownership of the tool's execution.
- Deterministic replay: sampling, clocks, hooks and environments sit outside the record.
- Hooks on requests, answers or compaction: we own none of them.
- Hot reload: swapping a fold mid-journal risks a view its rebuild would not reproduce, and a tool list cannot be pushed to a harness.
- Deferred coordination tools: `wait` must be known before it is needed.
- Dial-out relay: no user, and it moves trust to a third party. Pi's stack was never published, so it is no verdict either way.
- Guard seam rules: architecture section 18 lists middleware in the op path and `deny` rules, and there is no user. Keep the fact that an op that raises is refused.
- An extension-added preamble line: no user, and tool descriptions reach the model the same way.
- Held, not rejected: crash count (when `serve` or resume-on-exit is built); versioned pending work (at the first payload v2); native fork of an agent (if Platoon's fork_step needs it); agent.renew (once the drivers stage shows a harness running out); cached tokens in Usage (when budgets first mislead someone; define `tokens` now); rendered request record (M3, at the gateway); prompt or tool change as a context change (when a driver changes tools during a session).

## Lessons

- Do not park what a crash cut off (packages/durable/CHANGELOG.md:118).
- Charge a crash to something (:119, :183).
- A close is not a crash (spec.md:2530-2536).
- A failed commit is an unknown outcome (spec.md:5993), and once a commit is durable nothing may fail it (CHANGELOG.md:182).
- Per-commit work must not grow with history (CHANGELOG.md:167, not rerun), so measure per-pass cost.
- Wait in a durable record, not a call (CHANGELOG.md:193).
- Deltas derived by a second rule drift (packages/durable/src/harness/view.ts:324-378).
- A run that ends without an answer must say why where a renderer sees it (spec.md:4635-4645).
- An optional sink is not loud failure (packages/durable/src/harness/harness.ts:474).
- A thing that can decide fails closed (packages/durable/src/harness/tool.ts:693).
- Zero usage on an aborted call means unknown (docs/research/fixtures/pi-sample.jsonl:136).
- Bounds are assertions (packages/durable/docs/group-commit.md section 7).
- Their crash tests are not our model: no recovery test kills a process.

## Defects in ours

All were confirmed by the fact-checker at `4d5e6c5`, and severity is its ruling. Five later commits touch this code.

- MAJOR. bug-durability-1, bug-driver-1: a lost turn stalls the session silently. primitives/agents.py:134-136, primitives/lifecycle.py:316-334. Reproduced; lease expiry does not rescue it. Fix: the crash notice, which closes it only without a metered limit.
- MAJOR. bug-coordination-1: a waiter's own agent.cancel never counts, so cancel-then-join hangs. primitives/waits.py:105, :288. Reproduced in all orders. Fix: distinct="agent" at :288 and distinct="actor" at :290.
- MAJOR. bug-coordination-3: a headless session can settle short of `until` and hang. session.py:399-411, probe. Fix: return needs_human.
- MAJOR. bug-clients-1: view.watch("roster") silently misses rows, because the delta keys on event.agent, which is None for an ordinary send. primitives/clients.py:262-266, primitives/messages.py:443. Fix: return every row on any head move, and test a delta against a fresh snapshot. Measure the size at 100 agents first.
- MAJOR. bug-provenance-1: a refused report vanishes. 500 forgotten ids are refused invalid and no compaction or gap is recorded. runtime/host.py:352 against its docstring at :328-329. Reproduced. Fix: treat an unexpected refusal as untakeable, and store a long forgotten as a body.
- MAJOR. bug-coordination-4: agent.finish and agent.retire silently cancel working children. primitives/lifecycle.py:116-120, probes. Fix: refuse conflict.
- MAJOR. bug-coordination-2: a parked join is woken by each child, so a join of N costs N turns. primitives/lifecycle.py:69-77, probe. Fix: a counted finished report posts at next-turn.
- MAJOR. bug-coordination-6: an interrupted or failed turn reads to the parent as a final answer and wakes it. primitives/lifecycle.py:326-328, probe. Fix: for any reason but stopped, gist `<name> turn <reason>: <text>`, and post interrupted at next-turn.
- MAJOR. bug-coordination-7: Esc does not stop an agent with something queued. primitives/delivery.py:54-64, probe. The proposed fix does not work; the replacement is contested.
- MAJOR. bug-durability-2: an approval pending when the runtime died stays askable. primitives/approvals.py:77-79. Resolving it commits, then fails loudly; before that settled() can say needs_human for a question nobody can usefully answer. Fix: fold turn.lost into moot and lower the row.
- MAJOR. bug-coordination-9: a harness that exits alone is lost for good, with its subtree, though it can resume. docs/architecture.md:613-615. Design of record, not probed with a real harness. See contested.
- MAJOR. bug-clients-2: a late joiner is shown committed text, and frames cannot be matched to items. kernel/pulse.py:109-133. Reproduced. Fix: the live tail.
- MAJOR. bug-provenance-3: a tool item cannot carry the model call that produced it. primitives/lifecycle.py:358-361. A contract gap that costs real links once drivers exist. Fix: call_id on reports.
- minor. bug-durability-3: an uncertain effect under `surface` cannot be settled by anyone, against RFC 0005. kernel/effects.py:210, :218. It cannot hang a session. Fix: effect.settle for a human, two actions on the row.
- minor. bug-durability-4: how an extension's effect recovers is unwritten, and a live timeout under reconcile reaches nobody. runtime/recovery.py:90-106. Fix: state that the daemon that performs a kind settles its rows.
- minor. bug-durability-5: a committed call that lost its ack can run again if a model reissues it after resume. tools/mcp.py:133-135. A native id still dedupes a harness retry. Fix: note it and rely on the notice.
- minor. bug-durability-6: docs/architecture.md:222 says no command happened after a failed commit, when the outcome is unknown. By reading only. Fix: reword, and give insist a key where a double matters.
- minor. bug-durability-7: Waits.closing scans every wait ever made on each pass. primitives/waits.py:247-255. Not measured. Fix: partial indexes and per-pass cost in the scale test.
- minor. bug-coordination-5: a one-shot parent's children die with its turn, unwarned. primitives/lifecycle.py:322-325, probe. Fix: a warning in team_check, not _warnings. _warnings has no capabilities, while team_check has Capabilities.persistent (team.py:271, primitives/reports.py:36).
- minor. bug-coordination-8: Esc is refused between a wake and its turn. primitives/lifecycle.py:224, probe. Fix: accept waking, or keep a refusal a client can show.
- minor. bug-coordination-10: a parent that cancels its own idle child is woken to hear of it. Probe. Fix: post at next-turn when the actor is the parent.
- minor. bug-coordination-11: no op withdraws an open task. A gap with no user until patterns exist. Decide at M4.
- minor. bug-coordination-12: child.seen has no end, so settled cannot see a live native child. primitives/reports.py:129-135. Unprobed. Decide per driver in the drivers stage.
- minor. bug-clients-3: no backward read of a transcript. kernel/kernel.py:448-476. A planned the clients stage piece, not a defect in anything built. Fix: a backward read.
- minor. bug-clients-4: a late joiner's first frame says lag 0. kernel/pulse.py:128. Fix: the live tail.
- minor. bug-clients-5: delta makes a ring for any name and never ends for an ended agent. kernel/kernel.py:508-522. Reproduced. Fix: refuse unknown names, answer None once drained.
- minor. bug-clients-6: the roster row lacks parent and held_by. Fix: the roster idea.
- minor. bug-clients-7: marks.sqlite is in the design with no code and no STATUS row. docs/architecture.md:120.
- minor. bug-extensions-1: model-facing hints name tools the reader does not hold, and no agent holds agent.list. tools/surface.py:26. Fix: derive hints from held names.
- minor. bug-extensions-2: the 32 KiB limit is not enforced for queries. Reached by a third-party op or about 520 peers. Fix: refuse a result over the limit.
- minor. bug-extensions-3: a resume under different SDK or extension versions leaves no record. kernel/effects.py:241. Harness versions are recorded. Fix: compare and record at start.
- minor. bug-extensions-4: tool name collisions across extensions pass load, then raise at start before the try. runtime/__init__.py:65. Reproduced. Fix: claim tool names in load.
- minor. bug-extensions-5: check_extension misses names with underscores or digits, and plain imports. testing/extension.py:16, :62. Fix: share the surface's pattern and walk ast.Import.
- minor. bug-extensions-6: a refused query renders in the preamble as 'nobody yet'. tools/surface.py:165, :169. Rare. Fix: leave the line out.
- minor. bug-extensions-8: deny is rejected for the wrong reason. platoon-harness@4d5e6c5:docs/architecture.md:1148, platoon-harness@4d5e6c5:docs/adr/0007-topology-as-grants.md:20. Deny-wins is commutative; it loses monotonicity. The decision stands. Doc fix.
- minor. bug-provenance-2: Compacted(forgotten=None) records no gap unless the driver sends a second report. primitives/lifecycle.py:365-367. Nothing is lost, but Ending omits it. Fix: record compaction_opaque there.
- minor. bug-provenance-4: forgotten has no stated meaning; a test passes a journal ref while the compat doc means native ids. tests/unit/primitives/test_delivery.py:294. Fix: state native ids.
- minor. bug-provenance-5: Usage.tokens is undefined, so budgets are not comparable across drivers. primitives/reports.py:114-122. Fix: one sentence and a conformance check.
- minor. bug-provenance-6, bug-driver-4: the compat row says pi has no per-call id, against our fixture and spike s8. docs/compatibility.md:83. Fix the id rows; row 241 reports what was observed, so leave it.
- minor. bug-driver-2: with no client call id, identical calls in one turn collapse into one. tools/mcp.py:336-343, spike s12 on real pi over HTTP MCP. A stated trade-off. The proposed key is wrong, because a retry after a lost ack would run twice. Fix: the stdio shim.
- minor. bug-driver-3: stop_leaves_no_process cannot see a tool, and the promise does not hold past SIGKILL. testing/conformance.py:336-347, spike s9. Only SIGKILL of pi leaves bash alive. Fix: a check during a running tool, and a crash_window gap.

## Contested and open

- RESOLVED, crash count on lost turns: watch, not the drivers stage. A loop needs something that re-enters by itself, and RFC 0006 says only `resume` restarts anything (platoon-harness@4d5e6c5:docs/adr/0006-per-session-runtime.md:11). Build it with `serve` or resume-on-exit. Pi's lesson stands for then: end it, do not park it.
- RESOLVED, notice text: one fixed notice, no list. A list cannot say an unlisted call did not happen, because query ops leave no event for an agent (tools/mcp.py:380-391). A trial where an agent repeats a committed call would reopen this.
- RESOLVED, HTTP MCP or stdio shim on pi: shim. It gives each call a fresh id (tools/shim.py:34-41), so a second identical call is not taken for a retry, and it reads the token from the environment (shim.py:20), which removes HTTP's advantage. Cost: pi needs a python3 beside it. HTTP is the path run on real pi; the shim was not, so the first driver test must run it.
- RESOLVED, transcript shape: a backward read on Kernel.read, with `before` and a set of stream names. The proposed fold would be a second copy of the journal. UNIQUE (stream, version) (kernel/journal.py:65) can serve the newest rows of a sparse stream, which answers the worry about a long walk, though this was not run. A client must add the channel streams an agent reads. Name the client row `missed`.
- RESOLVED, reading the harness's log after a loss: watch at M2. Both attackers agree `concepts_added: none` is false: recovered reports need a label and dedupe, and the gaps are honest as they stand.
- RESOLVED, failFast on gather: no change to on(...); decide the rest at M4 with gather in hand. Any view can be watched: watch at M4, since both attackers moved it there. Demo interactions: drop the client command queue, because rpc.py:94 already runs each request in its own task; keep the rest as the clients stage notes. Queue rows: both keep them.
- LEFT CONTESTED, Esc and what was waiting (bug-coordination-7): both agree the proposal fails, since v_deliveries_blocked is wiped by any agent's turn end, nothing clears it on message.sent, and wake.refused shows as Budget (primitives/messages.py:236-239, primitives/clients.py:104-106). Both keep the report half. One side wants a per-reader 'no wake up to seq' column with the interrupt recording that a human asked. The other wants one fold on turn.ended{reason: interrupted} that needs no telling a human from a parent. The question is whether a parent's interrupt of a child should also quiet the child's queue.
- LEFT CONTESTED, how a human steers: one side wants a human-only `steer: bool` on message.send, hidden from tool schemas. The other wants no argument: a person's message to an inbox set to wake lands at the earliest boundary the harness has. The second is derived, but Session.send from a script is a human principal too (runtime/opening.py:142), so a script would steer, and docs/research/tui-expectations.md:86 changes.
- LEFT CONTESTED, withdraw a queued message: the fact-checker upheld the case for message.withdraw with Pi's three answers (packages/durable/src/harness/submissions.ts:148-161). The taste reviewer rejects it: one op, one event and a fold for a row in a research keymap, when the brief does not ask and a human can send again. The two proposals also disagree on who may withdraw. If rejected, delete docs/research/tui-expectations.md:89.
- LEFT CONTESTED, resume a harness that exits alone (bug-coordination-9): both say cost M, because turn.lost is emitted only at runtime start and reconcile runs only at recovery. The fact-checker wants it in the drivers stage with the notice. The taste reviewer wants a watch at M2, since it reverses the design of record and we do not know which exits a resume cures. the drivers stage runs would show that.
- RAISED, NOT RULED: a clean stop has the same hole as a crash. _hand_back ends an open turn with TurnEnded(reason='the owner stopped') (runtime/__init__.py:143-151); the reason is dropped on the way to the parent, and a resumed worker sits idle on its lease with no notice. The crash notice as written covers only turn.lost. Decide whether it extends.
- RAISED, NOT RULED: keep_running restarts a failing daemon for ever with only a log line (kernel/daemon.py:26-40), so a courier failing every pass looks like a quiet session. Worth a look at M2 as one attention row. Not probed.
- RAISED, NOT RULED: a hostile-mode test run, with our rare-path constants forced small, as Pi does with retention (packages/durable/test/setup-document-retention.ts). Whether an override is clean is unchecked.

### Decisions on the open questions

- A resume wakes an agent whose turn was lost. `resume` is an explicit act by someone who wants the session to go on, and a notice nobody
  acts on is the stall this fixes. A wake the budget refuses ends the session `needs_human`.
- The notice also covers a turn cut off by the owner's stop, since that leaves the same hole.
- `finish` is not refused over children in `waiting`. They hold no turn, and `on_parent_exit` decides for them.
- Agents do not get `agent.list`. They have `peers`, and hints name only tools the reader holds.
- A resume under changed SDK or extension versions is labelled, not refused. A session already survives an upgrade.
- Whether presets narrow `Role.tools` waits for the tool list ceiling's numbers.
- Whether a failed commit ends a training rollout is decided with change 18. How a trainable pi treats compaction is decided at the Platoon
  bridge, with `purpose` on `ModelCall` available either way.
- The Esc mechanism, how a human steers and whether withdraw exists were decided at the clients stage: an interrupt quiets what was
  waiting for its agent, whoever interrupts, and is accepted for an agent on its way to a turn; a person's message to an agent steers,
  with no flag; and no op withdraws a sent message, as a person sends a correction instead. See architecture section 7.
- Whether a harness that exits alone is resumed waits for what the real drivers show. They showed that a native resume cured every `kill -9`, and the recommendation is to build it at M2 with the crash count, in [the spike](spikes/real-harness.md). Not built.
- bug-coordination-12 is closed on Claude Code, by the same spike: with background tasks off a child lives inside the tool call that started it, and an interrupt of that turn ends it, so an open turn covers it.

## Corrections

- A requestId does not give single execution, though the announcement uses the phrase AGENTS.md bans. The source dedupes admission only, compares type alone, and silently returns the old submission for different text (packages/durable/src/harness/submissions.ts:232-240, spike s3).
- 'A model request that was cut off is sent again' omits the charge: at 1.5.0 the attempt counts as failed, goes again after a backoff, and with no retry left the run ends interrupted (packages/durable/src/harness/generation.ts:263-266, 497-535, spike s2b).
- 'One process owns a storage' is not enforced: no lock exists in packages/durable/src/storage, and a second writable open succeeded (spike s6).
- 'Committed before shown' no longer holds: since 1.5.0 partials are shown first and stored within about a second (packages/durable/CHANGELOG.md:50, against README.md:5), and output in that window was lost in spike s2.
- 'Survives crashes' means process crashes: the node SQLite driver sets synchronous = NORMAL (packages/chord/src/sqlite/node.ts:208).
- The announcement's client code is gone: viewState, documentState and taskGraph were replaced, and watchEvents was removed (packages/durable/CHANGELOG.md:49, 56).
- Other clients attaching to the process is left to the application: packages/durable/src has no transport, though Chord links and test/examples/35-36 show the route.
- 'The exact operations of every commit' holds only while a listener keeps up (packages/durable/docs/spec.md:5560-5578).
- 'A restart or a fork sees exactly what the model saw' holds for stored messages, not the rendered request (packages/durable/src/harness/generation.ts:285-295).
- 'Only the change is sent, so the prompt cache stays valid' holds only for models flagged in the catalog (packages/ai/src/utils/transcript.ts:115-120).
- The 15,000 line claim is stale: true at v1.0.0, and 30,230 lines at v1.5.0 without src/testing.
- packages/durable/docs/group-commit.md still says 'design', and it shipped in 1.5.0.
- Ours: docs/compatibility.md:83 and docs/research/adapter-others.md:264 are wrong that pi has no per-call id. It has one on RPC, at 1.4.0 too; the research read headers, not frames.
- Ours: docs/compatibility.md:83 and :384 should record that HTTP MCP is now probed on pi against our real ToolServer.
- Ours: docs/compatibility.md:236 says pi's append path was not researched; pi has --append-system-prompt (packages/coding-agent/src/cli/args.ts:123).
- Ours: primitives/waits.py:347 'Wait without spending a turn' is false for a join today.
- Ours: platoon-harness@4d5e6c5:docs/architecture.md:222 and :1148, platoon-harness@4d5e6c5:docs/adr/0007-topology-as-grants.md:20 and RFC 0005 need the changes under bug-durability-6, bug-extensions-8 and bug-durability-3. RFC 0012 needs a line for the counted report.
- Analysis errors: Pi tells the model after a crash only for a plain tool; packages/durable/test/harness-tools-recovery.test.ts:109 uses harness.close, not a crash; Pi's dial-out relay was never published, not shipped and removed (packages/coding-agent/CHANGELOG.md:281); 'a TUI over ssh already works' was false because no TUI exists; tool name collisions are not all refused at load.
- Citation: tools-and-parking.md is at docs/research/spikes/tools-and-parking.md, not docs/spikes.

## Not read or not run

No real model, provider or Platoon gateway ran. No real Claude Code or Codex ran. No real harness was killed except pi and Pi Durable in spikes on a fake model; our crash probes use an in-process abandon. Neither project's test suite ran, so every Pi performance figure is their claim. The get_entries search and the shim with pi were not run. The sweep covered 124 of 159 boundaries, and only 1 blocked cut was traced. Pi: most of the spec, session.ts, transaction.ts and scheduler.ts beyond cited regions, most test bodies, most of Chord, pi-ai providers other than openai-completions; the Cloudflare page was seen only through a summarizer. Ours: docs/training.md (absent from the frozen tree), most RFCs, tests in part, and all commits after 4d5e6c5. The fact-checker opened every citation a verdict rests on, sampled some others, and re-ran our probes but no Pi spike. Other citations are as the analysts and fact-checker gave them.
