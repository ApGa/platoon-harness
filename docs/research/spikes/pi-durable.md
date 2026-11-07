# Spike: Pi Durable and pi RPC

> Background research, dated 2026-11-03 and not maintained: [reference/compatibility.md](../../reference/compatibility.md) is current.

Run on 2026-11-03 for the [Pi Durable review](../pi-durable.md): Pi Durable, pi-ai and chord 1.5.0, pi-coding-agent 1.4.0 and 1.5.0, Node
26.13.0, on our `FakeModel` (chat dialect) and pi-ai's faux provider. Dummy keys and no paid call. Nothing below is a real model. Each
scenario ran once unless stated, and timings are from a shared machine on a network filesystem, so treat them as an order of magnitude.

| # | Question | Ran | Result |
|---|---|---|---|
| 1 | Smallest host | yes | Worked. The request body is not stored. Entries are `pi.user`, `pi.system` with `toolsAdded`, `pi.assistant` with `responseId`, usage and `durationMs`, and `pi.tool-result`, and the request is rebuilt from them |
| 2 | SIGKILL mid-tool, `safe` | yes | The tool ran twice. The model saw only the second result and was told nothing |
| 2 | SIGKILL mid-tool, plain | yes | Ran once. The model got `early-output` plus `[error] Tool work was interrupted and may have partially run`. `late-output`, inside the deferred window, was lost |
| 2b | SIGKILL during a model request | yes | The same messages were resent after the backoff, 588 ms to done. The model was told nothing. Nothing partial had streamed, so there was no aborted entry |
| 3 | Same `requestId` after the crash | yes | Same submission id, status `placed`. After done, same id and same answer. **Different text under the same id silently returns the old submission** |
| 4 | Steer | yes, on the second try | During a tool: `queued`, then a user message after the tool result, before the next request. During a text-only stream: after the answer, as the next run. On abort: steer withdrawn `unanswered aborted`, and the model is later told `[error] Tool slow was aborted`. The first run was invalid, because faux defaults to `stopReason: "stop"` and no tool ran |
| 5 | Watch | yes | 1,500 4-character tokens over 7.6 s: 77 callbacks, median gap 101 ms, 18,480 operation bytes, or 12.3 bytes per token and about 7.8 without the final entry. Stored commits: 11 by default, 79 with `persistWithinMs: 0` |
| 6 | Second writer, `safe` tool | yes | **No refusal.** The second process opened in 15 ms and reran the tool while the first was in it, then failed `storage_failed: ID 13 already belongs to entry`. The first finished. Two executions |
| 6 | Second writer, plain tool | yes | **The second process took over.** It wrote `interrupted` while the first's tool was running, and the model was told so. The first then failed `SessionFailed` on the same id collision |
| 6 | Read-only viewer | yes | Point in time: no watch calls in 4 s while the first ran. A second watch showed 5 entries next to a stale `pi.live` (`pending`), a torn view |
| 6 | Attach across processes | source only | Nothing in `packages/durable/src` serves a client. Chord has links. It is left to the application |
| 7 | Time and memory | yes, 3 runs | 0.59 to 0.84 s wall and 65 MB resident for one turn with a tool, with an import of 165 ms. pi RPC, same turn shape plus MCP: ready in 450 ms and a high water of 110 to 117 MB |
| 8 | pi RPC on our real ToolServer | yes, 1.4.0 and 1.5.0 | HTTP MCP through `?surface=mcp__ph` with `${VAR}` headers: tools in the first request, and a call returned. `message_end.responseId` equals the model's id on both. Steer boundaries as in 4. After SIGKILL the tool lives on, a queued steer is lost, and the next request holds `No result provided` |
| 9 | Does pi's bash stay in pi's group | yes | No, it has its own session. A group SIGKILL leaves bash and its child alive. SIGTERM, stdin EOF and abort all end them |
| 10 | A backend through `check_driver` | yes | 127 lines. 15 passed and 3 skipped (`malformed_frame_is_a_gap`, `one_shot_exits`, `declared_but_unproven`). `operational` met, `observable` unverified, `trainable` unmet on a key. No check called `reconcile`, and approval across a crash was not run |
| 11 | A lost turn on our kernel | yes | After `recover`, with nothing queued: `settled: true, done: true`, worker `idle`. Kernel side only |
| 12 | Two claims in one turn, with a client that sends no id | yes, real pi | The second `task_claim` returned the first with "nothing ran", and task 2 stayed open |
| 13 | `--session-id` | yes | The chosen id holds. It is persisted on the first prompt and resumed with history. Before that no file exists |

Scenarios 8, 11 and 12 stubbed our check for a local filesystem in their own process, because the spike ran on a network filesystem. Those
journals were throwaway, single process and single host.
