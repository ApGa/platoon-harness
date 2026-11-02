# Drivers

A driver presents one harness session to the runtime through seven methods. One instance serves one agent. Drivers for
`claude`, `codex` and `pi` ship with the SDK, as they land. This page is for everyone else: how to write a driver, in Python or
any other language, and how to prove it works.

There are three ways in, cheapest first.

| You have | Use | You write |
|---|---|---|
| A CLI that takes a task and exits | `exec` | One line of config |
| A program in any language, or a dependency set that cannot share ours | `wire` | A program that speaks JSON-RPC on stdio |
| A Python package | The `platoon_harness.drivers` entry-point group | A class with the seven methods |

## The contract

```python
class Driver(Protocol):
    def describe(self) -> DriverInfo: ...                        # name, version, login kind, capabilities. Starts nothing
    async def start(self, spec: AgentSpec, report: Reporter) -> Started: ...  # fresh, or resume from spec.resume
    async def deliver(self, delivery: Delivery) -> Receipt: ...  # delivery.boundary is one the driver declared
    async def interrupt(self) -> Receipt: ...                    # stops at the boundary it can, says what was queued
    async def answer(self, approval: str, verdict: Verdict) -> None: ...
    async def reconcile(self, input_id: str) -> Reconciled: ...  # landed | not_landed | unknown
    async def stop(self, grace: float) -> None: ...              # ends the process tree it owns
```

A method it cannot honor raises `DriverError`, with the reason. That is how "unsupported" stays loud. The rest is what each
method promises:

- **`describe`** runs before anything is spent. It must start no harness, and it is asked twice with the same answer.
- **`start`** begins the first turn on `spec.goal`. With no goal, or given `spec.resume`, which reopens that native session, it waits
  for a delivery. A driver refuses an unset model where the harness would otherwise pick a hosted default.
- **`deliver`** hands over `delivery.text`. The id goes out with it, so `input.delivered` can say what landed, and `reconcile` can
  answer after a crash.
- **`interrupt`** stops the turn. The agent lives on.
- **`stop`** leaves no process behind.

### What a driver reports

`report` is a plain async callable. It takes this vocabulary and no other.

| Report | Fields | When |
|---|---|---|
| `Ready` | `native`, `version`, `effective_model`, `tools_visible` | The harness is up. `tools_visible` is a list only when it was observed |
| `TurnStarted` | `turn` | |
| `TurnEnded` | `reason` | `stopped`, unless something went wrong. For a one-shot harness this is its end, and `stopped` means it finished |
| `Delta` | `text` | Live text. It is lossy and never journaled |
| `Item` | `kind`, `gist`, `phase`, `native_id`, `body`, `approval`, `outcome` | A `message`, `thought`, `tool` or `patch`. `gist` holds at most 280 characters and `body` the whole text |
| `InputDelivered` | `input`, `boundary`, `evidence` | A delivery reached the harness. `evidence` names what showed it |
| `ApprovalRequested` | `id`, `gist` | The harness is waiting on a decision |
| `ModelCall` | `call_id`, `model` | A model call, with its id only when the id is real |
| `Usage` | `tokens`, `usd`, `label`, `scope` | What was spent, once. `scope` is `call`, `turn` or `tree`, and `label` is `provider`, `estimated`, `lower_bound` or `unavailable` |
| `Compacted` | `forgotten` | Context was compacted. If what it forgot is unknown, also report the gap `compaction_opaque` |
| `ChildSeen` | `native`, `parent`, `attribution` | A native child it made on its own |
| `GapReport` | `plane`, `what` | Something went unseen, from a closed list |
| `Native` | `kind`, `raw`, `cut` | A frame nobody's vocabulary covers |
| `Exited` | `reason` | The harness is gone |

Never guess. Unknown is `None`, not zero, not an empty list, and not a plausible id. A frame you cannot read becomes `Native` plus a
gap, which is what `unknown_frame(kind, raw)` returns, and never a log line.

Levels are not in this list, and neither are capabilities. A driver declares capabilities in `describe`, and the runtime works
out what they earned. A `ready` that tries to state a level is an unknown frame.

### What a driver declares

`Capabilities` says what a harness can do, and absence means unsupported.

| Field | Values |
|---|---|
| `persistent` | Whether a session outlives a turn. A one-shot worker cannot park |
| `resume` | Native resume is available |
| `boundaries` | Where a delivery can land: `turn`, `tool`, `model_call` |
| `tool_paths` | `mcp-http`, `mcp-stdio`, `shell` |
| `tool_timeout_s` | The harness's cap on one tool call |
| `interrupt` | `none`, `turn`, `tool`, `call` |
| `approvals` | `none`, `gated`, `native` |
| `native_children` | `none`, `observed`, `opaque` |
| `call_ids` | `none`, `agent`, `call` |
| `dialects` | `chat`, `responses`, `messages` |
| `coverage` | For each of `prompt`, `tool_results`, `shell_reads`, `files`, `native_children`, `compaction`, `external`: `observed`, `partial` or `none` |
| `measures` | Which of `tokens` and `usd` it reports |
| `sandboxes` | The values a role's `sandbox` may take |

A declaration earns nothing by itself. See [Conformance](#conformance).

## A one-shot CLI: `exec`

```toml
[roles.worker]
harness = { command = ["my-agent", "--task", "{goal}"], mode = "oneshot" }
```

`{goal}` becomes the goal. The process is the agent's one turn: its stdout is the message, stdin is closed so it cannot hang, and its
exit ends the turn and the agent. It coordinates through `ph`, which is on its `PATH`, along with what `ph` needs to reach the tools.

It cannot park, take a delivery or resume, and every one of those is refused with the reason. All it reports is what stdout and an
exit can show: the model it ran stays unknown, and nothing pretends otherwise. A `command` in a project file needs explicit trust.

## A program: the wire

A wire driver is a program that speaks line-delimited JSON-RPC 2.0 on stdio. Lines split on LF only, stderr goes to the agent's
bounded log, and nothing else may reach stdout. In a team file:

```toml
[roles.worker]
harness = { command = ["python", "my_driver.py"], mode = "wire" }
```

### In Python

`serve` does the protocol, so a wire driver in Python is a driver plus one line. This one is complete, and it is the program the test
suite runs through the conformance checks. It asks a model once per turn over Chat Completions.

<!-- example: the wire driver a test runs -->
```python
import asyncio
import json
import os
import urllib.request

from platoon_harness.drivers import (
    Capabilities,
    DriverError,
    DriverInfo,
    Exited,
    InputDelivered,
    Item,
    Ready,
    Receipt,
    Started,
    TurnEnded,
    TurnStarted,
)
from platoon_harness.drivers.wire import serve


class OneCall:
    """A harness that asks a model one question per turn."""

    def __init__(self):
        self.turns = 0
        self.turn = None

    def describe(self):
        capabilities = Capabilities(persistent=True, boundaries={"turn"}, dialects={"chat"})
        return DriverInfo(name="one-call", version="1.0", capabilities=capabilities)

    async def start(self, spec, report):
        if spec.model is None:
            raise DriverError("set a model: this harness will not pick one")
        self.model, self.report = spec.model, report
        await report(Ready(version="1.0", effective_model=spec.model))
        if spec.goal:
            self.turn = asyncio.create_task(self.take_turn(spec.goal))
        return Started()

    async def take_turn(self, prompt):
        self.turns += 1
        await self.report(TurnStarted(turn=str(self.turns)))
        reply = await asyncio.to_thread(self.ask, prompt)
        await self.report(Item(kind="message", gist=reply[:280], body=reply))
        await self.report(TurnEnded())

    def ask(self, prompt):
        request = urllib.request.Request(
            f"{os.environ['OPENAI_BASE_URL']}/chat/completions",
            json.dumps({"model": self.model, "messages": [{"role": "user", "content": prompt}]}).encode(),
            {"authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "content-type": "application/json"},
        )
        with urllib.request.urlopen(request) as reply:
            return json.load(reply)["choices"][0]["message"]["content"]

    async def deliver(self, delivery):
        if self.turn is not None:
            await self.turn
        await self.report(InputDelivered(input=delivery.input, boundary="turn", evidence="prompt"))
        self.turn = asyncio.create_task(self.take_turn(delivery.text))
        return Receipt(boundary="turn")

    async def interrupt(self):
        raise DriverError("one call cannot be cut short")

    async def answer(self, approval, verdict):
        raise DriverError("this harness asks for nothing")

    async def reconcile(self, input_id):
        return "unknown"

    async def stop(self, grace):
        if self.turn is not None:
            self.turn.cancel()
        await self.report(Exited(reason="stopped"))


serve(OneCall())
```

### In any other language

The verbs equal the Python methods. A session reads like this, with `>` for what the runtime writes and `<` for what you write.

```jsonc
> {"jsonrpc":"2.0","id":1,"method":"describe","params":{"protocol":1}}
< {"jsonrpc":"2.0","id":1,"result":{"protocol":1,"name":"mine","version":"1.0","login":null,"capabilities":{"persistent":true,"boundaries":["turn"]}}}
```

That was one short process: `describe` runs your program, sends this one frame, closes stdin and expects you to exit, so no harness
may start for it. Starting an agent is a new process.

```jsonc
> {"jsonrpc":"2.0","id":1,"method":"start","params":{"protocol":1,"spec":{"agent":"ada","role":"worker","goal":"...","cwd":"...","folder":"...","model":"m","tools":{"url":"...","namespace":"ph","bin":"..."},"access":["OPENAI_API_KEY"],"env":{},"instructions":null,"resume":null}}}
< {"jsonrpc":"2.0","id":1,"result":{"native":"s-9"}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"ready","native":"s-9","version":"1.0","effective_model":"m","tools_visible":null}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"turn.started","turn":"1"}}
> {"jsonrpc":"2.0","id":2,"method":"deliver","params":{"input":"41","boundary":"turn","text":"New messages (delivery 41):\n- inbox/ada@3 from @lead: Keep the API stable","items":[{"ref":"inbox/ada@3","gist":"Keep the API stable","sender":"@lead","body":null}],"behind":0}}
< {"jsonrpc":"2.0","id":2,"result":{"boundary":"turn","queued":["41"]}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"input.delivered","input":"41","boundary":"turn","evidence":"message_start"}}
> {"jsonrpc":"2.0","id":3,"method":"stop","params":{"grace":5.0}}
< {"jsonrpc":"2.0","id":3,"result":null}
```

| Verb | Params | Result |
|---|---|---|
| `describe` | `protocol` | `protocol` plus the fields of `DriverInfo` |
| `start` | `protocol`, `spec` | `{native}` |
| `deliver` | `input`, `boundary`, `text`, `items`, `behind` | `{boundary, queued}` |
| `interrupt` | none | `{boundary, queued}` |
| `answer` | `approval`, `verdict` | null |
| `reconcile` | `input` | `"landed"`, `"not_landed"` or `"unknown"` |
| `stop` | `grace` | null |

Each report is a `report` notification whose params are the report, with its `type`: `ready`, `turn.started`, `turn.ended`, `delta`,
`item`, `input.delivered`, `approval.requested`, `model.call`, `usage`, `compacted`, `child.seen`, `gap`, `native`, `exited`.

- **`protocol`** is an integer, currently 1, and whichever side does not know the other's refuses it. Your side answers `-32002`.
- **Errors.** A method you cannot honor answers `-32001` with the reason, which surfaces as `DriverError`.
- **Credentials never travel in a frame.** `spec.access` names variables, and their values are in your environment. So is the tool
  token, in `PLATOON_HARNESS_TOKEN`, with `PLATOON_HARNESS_URL` beside it. `ph` is on your `PATH`.
- **Your environment is an allowlist:** `PATH`, `HOME`, a `TMPDIR` of your own, and what the spec names. Nothing else is inherited.
- **A line is at most 16 MiB.** Past that the agent stops with a gap, since the line may have held an answer.
- **Stdout is the protocol.** A line that is not a frame costs you a `native` frame and a gap, and an unknown report the same.
- **Exit when stdin ends.** A program still there is sent `SIGTERM`, then `SIGKILL`.
- **Your own subprocesses are yours to end,** in `stop`. Stay in your process group, and the runtime can end them if you cannot.
  What leaves the group by `setsid` escapes it. A driver of your own that uses `Process` keeps its record in `spec.folder`, which
  on the wire is a folder of its own, so recovery finds both.

## A Python package

Give the class the seven methods, and register it. A `Driver` is structural, so nothing needs subclassing.

```toml
[project.entry-points."platoon_harness.drivers"]
mine = "my_package:MyDriver"
```

The name is the command you type: `claude`, not `claude-code`. Installing activates nothing: a role names a harness.

If your driver runs a subprocess, build on `Process` in `platoon_harness.drivers.process`, which gives you what section 5.7 of the
architecture asks for and is easy to get wrong:

- its own process group, recorded before exec, so no harness can exist unrecorded, and a reused pid cannot make recovery kill a
  stranger;
- pipes that always drain, and reports in a bounded queue whose breach stops the agent with a gap;
- stderr in a bounded log, never journaled, with credentials masked there and in reports;
- `stop(grace)`: `SIGTERM`, wait, `SIGKILL`, then verify;
- the allowlisted environment from `harness_env(spec)`.

For a line protocol, `read_lines` in `platoon_harness.rpc` splits on LF only and bounds a line. For JSON-RPC, `Peer` is the whole
client: it takes a handler for inbound calls, and `jsonrpc=False` for a peer that omits that member.

## Conformance

`check_driver` runs named checks and reports every failure at once. It reads ground truth from a loopback model's log, so "our tool
in the first request" means the tool was in the request, and "connected" counts for nothing. An unsupported check is a skip with a
reason, and a skip is never a pass.

```python
from platoon_harness.drivers.wire import WireDriver
from platoon_harness.testing import check_driver


async def test_my_driver_conforms(tmp_path):
    result = await check_driver(lambda: WireDriver(["python", "my_driver.py"]), folder=tmp_path)

    assert result.failed == (), str(result)
```

| Check | What it proves |
|---|---|
| `describe_starts_nothing` | `describe` reaches nothing, and two answers agree |
| `ready_with_pinned_model` | `ready` names the model asked for, and the first request asked for it |
| `tool_in_first_request` | Our tool is in the first model request. Needs an MCP path |
| `delivered_text_in_next_prompt` | A delivery's text is in the next prompt, and `input.delivered` came. Needs a persistent session and a `turn` boundary |
| `turn_end_reported` | A turn starts and ends |
| `no_goal_takes_no_turn` | With no goal it waits, and its first prompt is what it was sent. Needs a persistent session and a `turn` boundary |
| `interrupt` | A stalled turn ends, and the agent lives on. Needs `interrupt` |
| `resume` | A new instance resumes, takes a delivery and still knows what came before. Needs `resume` |
| `approval_answered` | An approval is requested, and its answer reaches the model. Needs `approvals` |
| `exit_reported` | A harness killed from outside is reported gone |
| `stop_leaves_no_process` | Every recorded group is gone after `stop`. Skipped for a driver that starts no process |
| `malformed_frame_is_a_gap` | A bad frame becomes `native` plus a gap. Pass `garble`, or it is skipped |
| `steers_at_declared_boundary` | A delivery lands at a boundary inside a turn. Needs one |
| `measures_reported` | Each declared unit comes with a turn |
| `call_ids_reported` | `model.call` carries the id the model gave. Needs `call_ids = "call"` |
| `dialects_spoken` | Every model call was in a declared dialect |
| `one_shot_exits` | A harness that is not persistent exits after its turn |
| `declared_but_unproven` | Always a skip: it names what you declared that no check can prove yet |

Each check gets a fresh instance, a fresh model and a fresh folder, and `timeout` bounds each one, so a wedged harness costs only its
own checks. What a driver leaves running, the suite reaps.

| Argument | Default | Say |
|---|---|---|
| `access` | `chat_access`, which sets `OPENAI_BASE_URL` and `OPENAI_API_KEY` | How your harness reaches the model, as a function of `FakeModel`. The key is a dummy |
| `garble` | None | A coroutine function, given the driver, that makes the harness write a frame no parser knows |
| `gated` | A `shell` tool call | A tool call your harness asks approval for |
| `timeout` | 10 s | How long one check may take |

The result is pinned to the driver and the harness version it reported, and `levels` reads it. A result for another version says
nothing of this one.

```python
from platoon_harness.drivers.levels import Profile, levels

earned = levels(capabilities, Profile(driver="pi", version="1.4.0", login="key", tools="unverified"), result)
```

`levels` gives `operational`, `observable` and `trainable`, each `met`, `unmet` or `unverified`, with reasons. It is a pure function,
and nothing a driver says reaches it except through a check that passed. Native and plan logins are never trainable.

### A real binary for free

`FakeModel` speaks Anthropic Messages, OpenAI Chat Completions and OpenAI Responses, with streaming, so a real harness runs against it
on a dummy key and spends nothing. Give it an isolated home, so that no login of yours takes part.

```python
from platoon_harness.testing import FakeModel, ToolCall

async with FakeModel(ToolCall("wait", {"timeout": 60}), "done") as model:
    ...  # point the harness at model.url

model.calls[0].offers("wait")   # was the model shown the tool?
model.calls[1].says("call_1")   # did its result come back?
model.requests                  # everything that arrived, exactly as it arrived
```

### A scripted harness

`ScriptedDriver` is a deterministic harness for tests and demos: one list of steps per turn. Its tool calls are real MCP over the
binding, so a scripted team exercises the real tool plane. Its capabilities are data, and it holds to them, so a test can make it
one-shot or unsteerable.

```python
from platoon_harness.testing import Ask, Call, Hang, Say, ScriptedDriver

driver = ScriptedDriver([[Say("on it"), Call("task_claim", {"queue": "tasks"})], [Ask("run the migration?"), Hang()]])
```

The steps are `Say`, `Think`, `Call`, `Wait`, `EndTurn`, `Fail`, `Exit`, `Ask`, `Hang` and `AskModel`, which makes real model calls
until the model only talks.

### Extensions

`check_extension` holds an extension to what a core primitive keeps to: `names`, `naming_law`, `schemas`, `descriptions`,
`public_api_only`, and with a `scenario` to run, `rebuild_equals_live`.

```python
from platoon_harness.testing import check_extension

result = await check_extension(extension, folder=tmp_path / "session", scenario=cast_three_votes)
assert result.failed == (), str(result)
```
