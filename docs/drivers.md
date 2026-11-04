# Drivers

A driver presents one harness session to the runtime through seven methods. One instance serves one agent. Drivers for
`claude`, `codex` and `pi` ship with the SDK, and `openhands` is a wire worker of its own, [below](#openhands-a-wire-worker).
This page is for everyone else: how to write a driver, in Python or any other language, and how to prove it works.

There are three ways in, cheapest first.

| You have | Use | You write |
|---|---|---|
| A CLI that takes a task and exits | `exec` | One line of config |
| A program in any language, or a dependency set that cannot share ours | `wire` | A program that speaks JSON-RPC on stdio |
| A Python package | The `platoon_harness.drivers` entry-point group | A class with the seven methods |

## The contract

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

A method it cannot honor raises `DriverError`, with the reason. That is how "unsupported" stays loud. The rest is what each
method promises:

- **`describe`** runs before anything is spent. It must start no harness, and it is asked twice with the same answer. `login` comes
  from the harness's own status command, with a short timeout, reading that one field and no credential file, and is None when it cannot
  tell. `prepare` reads it to refuse several agents on one plan login.
- **`start`** begins the first turn on `spec.goal`. With no goal, or given `spec.resume`, which reopens that native session, it waits
  for a delivery. The runtime gives `resume` only for a session that took a turn, and starts anew an agent whose harness took none. An unset model on the harness's own login means the harness's own default, and `ready` says which. Where access was
  given, in `spec.access`, a driver refuses an unset model, since the default may then go somewhere nobody chose. `spec.effort` goes to
  the harness as it stands, and a driver that cannot honor one raises `DriverError`. `spec.sandbox` is one of the values declared in
  `sandboxes`, and None leaves it to the harness. Unless `spec.allow_native_children` says otherwise, the harness offers its model nothing of
  its own for starting agents: turn that off by a setting for this launch alone, and say in your docs what that cannot reach, such as
  an extension's tool. `spec.instructions` holds the preamble and then the role's words, fixed at launch: hand
  them over once, as they are, through the harness's supported path, and never per turn. A resume gives the same text again, as
  Claude Code and Codex keep what a session began with whatever a resume passes. The runtime journals them as what the agent was told.
- **`deliver`** hands over `delivery.text`. The id goes out with it, so `input.delivered` can say what landed, and `reconcile` can
  answer after a crash. It returns once the harness has the text, so a harness that has stopped reading holds it up. The host drops it
  after a minute and queues its entries again under a new input, and a driver may leave what it wrote in the pipe: if the harness reads
  again, that lands too, at-least-once, and its refs dedupe it. `interrupt` and `answer` get the same minute.
- **`interrupt`** stops the turn, or the one a delivery on its way is about to begin, and that turn ends `interrupted`. The agent lives
  on. A delivery the harness took and has not landed when a turn stops short goes back on the runtime's queue, and comes again under a
  new input, so a driver sends nothing again. Tell a harness that keeps such a thing to drop it, where it can be told, or it may hear it
  twice, which at-least-once allows.
- **`stop`** leaves no process behind, a running tool and what it put in the background included. A tool that leads a group of its
  own outlives a `SIGKILL` of its harness, so ask a harness to end first, and with real grace. `Process` then ends, on Linux, what
  carries the harness's own `TMPDIR`, whichever group it left for. It reports the gap `crash_window` when it comes to `SIGKILL`, and the
  workspace may still be being written.

### What a driver reports

`report` is a plain async callable. It takes this vocabulary and no other.

| Report | Fields | When |
|---|---|---|
| `Ready` | `native`, `version`, `effective_model`, `tools_visible` | The harness is up. `tools_visible` is a list only when it was observed |
| `TurnStarted` | `turn` | No two turns of one agent share a name, across a resume too: a tool call with no id of its own is keyed on it |
| `TurnEnded` | `reason` | `stopped` if it stopped on its own, `interrupted` after an interrupt, and otherwise what went wrong, such as `aborted` for a turn the harness cut with nobody asking. An `interrupted` turn was someone's own doing, so it wakes nobody. `lost` and `stopped by its owner` are the runtime's own, and a driver that says one has sent an unknown frame. For a one-shot harness this is its end, and `stopped` means it finished |
| `Delta` | `text` | Live text. It is lossy and never journaled |
| `Item` | `kind`, `gist`, `phase`, `native_id`, `call_id`, `body`, `approval`, `outcome` | A `message`, `thought`, `tool` or `patch`. `gist` holds at most 280 characters and `body` the whole text. A `tool` or a `patch` is `started`, then `completed`, and a message or a thought has no `phase`. `approval` names the approval an outcome answers. `call_id` names the model call that made it, and `native_id` is the harness's own id for the item |
| `InputDelivered` | `input`, `boundary`, `evidence`, `native_id` | A delivery reached the harness. `evidence` names what showed it, and `native_id` is the harness's own id for what landed |
| `ApprovalRequested` | `id`, `gist` | The harness is waiting on a decision |
| `ModelCall` | `call_id`, `model`, `purpose` | A model call, with its id only when the id is real. `purpose` is the harness's own word for why, such as `compaction`, and None unless it said |
| `Usage` | `tokens`, `usd`, `label`, `scope`, `call_id` | What was spent, once. `scope` is `call`, `turn` or `tree`, and `label` is `provider`, `estimated`, `lower_bound` or `unavailable`. `call_id` names the call a `call` scope paid for |
| `Compacted` | `forgotten`, `summary` | Context was compacted. `forgotten` holds the native ids of what left it, and `summary` the text that took its place |
| `ChildSeen` | `native`, `parent`, `attribution` | A native child it made on its own |
| `GapReport` | `plane`, `what` | Something went unseen, from a closed list |
| `Native` | `kind`, `raw`, `cut` | A frame nobody's vocabulary covers |
| `Exited` | `reason` | The harness is gone |

Never guess. Unknown is `None`, not zero, not an empty list, and not a plausible id. A frame you cannot read becomes `Native` plus a
gap, which is what `unknown_frame(kind, raw)` returns, and never a log line. That holds for a frame of a known type with a shape you did
not expect, whichever part of it would not read, and `UNREADABLE` names what reading one raises: one changed field in a harness's update
must cost a gap, not the agent. A request the harness waits on still gets an answer, and a turn's end still ends the turn.

Send `started` where the harness shows it. A tool that has begun and not finished is an `Item` of kind `tool` in that phase, and it is
all a person watching has to say what is running, since `activity` is the gist of the latest item. Then send its `completed`.

`Usage.tokens` counts every token of what the scope covers, input and output, with cached input included, as a provider's total does, so
that budgets mean the same across drivers. A harness that gives you parts, add them. A zero on an aborted call means unknown, because a
harness writes it for a call it stopped hearing: report `tokens=None` with the label `unavailable`, which a budget treats as unmeasured.

`forgotten` holds native ids, the harness's own for what left the context, and no journal refs, since nothing else can say what those
were. If a harness names a position, such as the first entry it kept, expand it into ids where it can list them. If what it forgot is
unknown, leave `forgotten` `None`, and the runtime records the gap `compaction_opaque`. The host stores `forgotten` and `summary` as
bodies, however long, and `context.compacted` cites them.

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
| `tool_names` | How it shows our MCP tools to its model: `namespaced`, as `mcp__<ns>__<tool>`, unless said, or `bare`, by their own names |
| `tool_timeout_s` | The harness's cap on one tool call |
| `interrupt` | Whether a turn can be stopped |
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
exit can show: the model it ran stays unknown, and nothing pretends otherwise. It has no way to take the preamble, so `ph --help` is
what teaches it its tools. A `command` in a project file needs explicit trust.

It needs a goal to start, so set `count = 0` on the role and spawn it with one, and `team check` refuses it otherwise. Its agent ends
with its turn: `finished` if the turn `stopped`, and `failed` otherwise.

`{goal}` standing alone as an argument reaches the program's option parser, so a goal that starts with `-` is refused, since a model
may have written it. Inside an argument, as in `--task={goal}`, it cannot be taken for an option.

## A program: the wire

A wire driver is a program that speaks line-delimited JSON-RPC 2.0 on stdio. Lines split on LF only, stderr goes to the agent's
bounded log, and nothing else may reach stdout. In a team file:

```toml
[roles.worker]
harness = { command = ["python", "/opt/my-agent/my_driver.py"], mode = "wire" }
```

Use an absolute path. A relative one resolves against the session's `cwd` when the harness runs, and against your own directory when
it describes itself, so it can pass one and fail the other. If the program dies, the reason is in the agent's `stderr.log`, which the
error names.

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
        return DriverInfo(name="one-call", capabilities=capabilities)

    async def start(self, spec, report):
        if spec.model is None:
            raise DriverError("set a model: this harness will not pick one")
        if spec.effort is not None:
            raise DriverError("this harness has no effort to set")
        self.model, self.report = spec.model, report
        await report(Ready(version="1.0", effective_model=spec.model))
        if spec.goal:
            self.turn = asyncio.create_task(self.take_turn(spec.goal))

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
< {"jsonrpc":"2.0","id":1,"result":{"protocol":1,"name":"mine","login":null,"capabilities":{"persistent":true,"boundaries":["turn"]}}}
```

That was one short process: `describe` runs your program, sends this one frame, closes stdin and expects you to exit, so no harness
may start for it. Starting an agent is a new process.

```jsonc
> {"jsonrpc":"2.0","id":1,"method":"start","params":{"protocol":1,"spec":{"agent":"ada","role":"worker","goal":"...","cwd":"...","folder":"...","model":"m","effort":null,"sandbox":null,"allow_native_children":false,"tools":{"url":"...","namespace":"ph","bin":"..."},"access":["OPENAI_API_KEY"],"env":{},"instructions":null,"resume":null}}}
< {"jsonrpc":"2.0","id":1,"result":null}
< {"jsonrpc":"2.0","method":"report","params":{"type":"ready","native":"s-9","version":"1.0","effective_model":"m","tools_visible":null}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"turn.started","turn":"1"}}
> {"jsonrpc":"2.0","id":2,"method":"deliver","params":{"input":"41","boundary":"turn","text":"New messages (delivery 41):\n- inbox/ada@3 from @lead: Keep the API stable","items":[{"ref":"inbox/ada@3","gist":"Keep the API stable","sender":"@lead","body":null}],"behind":0}}
< {"jsonrpc":"2.0","id":2,"result":null}
< {"jsonrpc":"2.0","method":"report","params":{"type":"input.delivered","input":"41","boundary":"turn","evidence":"message_start"}}
> {"jsonrpc":"2.0","id":3,"method":"stop","params":{"grace":5.0}}
< {"jsonrpc":"2.0","id":3,"result":null}
```

| Verb | Params | Result |
|---|---|---|
| `describe` | `protocol` | `protocol` plus the fields of `DriverInfo` |
| `start` | `protocol`, `spec` | null |
| `deliver` | `input`, `boundary`, `text`, `items`, `behind` | null |
| `interrupt` | none | null |
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
  On Linux, what leaves the group is found by the `TMPDIR` it inherited, and ended too. A driver of your own that uses `Process` keeps its record in `spec.folder`, which
  on the wire is a folder of its own, so recovery finds both.

## OpenHands: a wire worker

`harness = "openhands"` runs `platoon-harness-openhands`, a wire program in an environment of its own, as the OpenHands SDK shares
one with nothing else: `uv tool install platoon-harness-openhands` makes it, the runtime finds it on `PATH`, and `doctor` shows it
with the version of the SDK it runs. The command is not `openhands`, which is the OpenHands CLI's. Each rule it keeps, in a sentence:

- **One process per agent** holds one `LocalConversation` of OpenHands SDK 1.59.0, driven only through `arun()`, so an interrupt can
  abandon a model call and a message can land while one runs.
- **Sign-in** is a key alone: `OPENAI_API_KEY` from the role's auth profile, with `OPENAI_BASE_URL` for an endpoint other than
  OpenAI's, and a role with none is refused, as is a ChatGPT subscription or an OpenHands Cloud login, which needs a person.
- **The model** is the role's, sent as it is named through litellm's OpenAI provider in the Chat Completions dialect, and an effort
  goes as `reasoning_effort`, refused for a model litellm's catalog says takes none, as litellm would drop it unsaid.
- **No retries:** the SDK retries no model call, as a retry is a second call a gateway records, so a failed one ends the turn.
- **No step cap:** the SDK's cap on the steps of a run is lifted, as a role's budget is what limits it.
- **Credentials:** the key, the endpoint and our token leave the worker's environment once read, so its terminal cannot read them,
  and `LITELLM_LOCAL_MODEL_COST_MAP` and `OPENHANDS_SUPPRESS_BANNER` keep it off the network and off stdout.
- **Tools** are OpenHands' terminal, in a subprocess, its file editor and its task tracker, as its own CLI gives them, and ours
  through the stdio shim, which gives each call an id of its own, so two identical calls in a turn are two calls. `tool_names` is
  `bare`, as OpenHands shows a server's tools by their own names.
- **`ready`** says the conversation's id, the SDK's version, the role's model and the tools the agent offers its model once readied,
  and the start fails if none of ours is among them, as the SDK only warns of a server that failed.
- **Instructions:** ours are `AgentContext.system_message_suffix`, the project's load with `load_project_skills=True`, as its own
  CLI loads them, and a conversation keeps the system prompt it began with, so a resume hands it the same text for nothing.
- **A delivery** begins a turn, or goes to the one under way and lands at a later model call, and `input.delivered` comes from the
  request that carried it, which the SDK's completion log shows, and never from the order of its events.
- **Approvals:** every action asks the runtime but a call of our tools and a lone `finish` or `think`, which the SDK never asks
  about, and one approval covers what a step holds, as the SDK confirms a step whole; `deny` rejects it with `The runtime denied
  this.`
- **Held deliveries:** a delivery waits while an approval is open, as a message would supersede the action, and then until what
  was allowed has its result, as a message must not come between a call and its result.
- **An interrupt** abandons a model call in flight, which a gateway may have recorded all the same, and rejects an approval left
  open, and its turn says its usage is a lower bound.
- **A turn ends** when `arun()` returns with nothing it was handed left to run on: `stopped` when the agent finished,
  `interrupted`, `stuck` when the SDK found it repeating itself, and otherwise the code of the SDK's error, such as
  `MaxBudgetReached`.
- **Items** come from actions, their observations and the agent's own messages: `finish` is its last message, `think` a thought,
  and a message the SDK calls the user's is never read as anyone's, as the SDK writes such messages itself.
- **A model call** is each one the SDK measured, by its response id, which items carry as `call_id`: its tokens are the provider's,
  prompt and completion, dollars come only where litellm prices the model, as an estimate, and litellm's reasoning tokens, an
  estimate too, are not reported.
- **A condensation** is `compacted`, with the event ids it forgot in the conversation's order and its summary, and its call has the
  purpose `condenser`, the usage id of the SDK's LLM that made it.
- **Its own agents** are off unless a role allows them; allowed, OpenHands' `task` tool starts its built-in kinds, whose steps ask
  the runtime as their parent's do, and a child, which has no identity we can see, is the gap `native_child_unattributed`, its
  spending its parent's at the scope `tree`.
- **A resume** reopens the conversation by its id with the key handed again and the same tools, a conversation that is not there is
  refused, as the SDK would start one anew under that id, and an action a crash or a stop left with no result is rejected before
  the next run, which would run it again.
- **`stop`** ends the turn and closes the conversation, which ends its terminal and the shim, and then the group ends as any wire
  program's does; a tmux that a child's terminal starts keeps its socket in a directory of the agent's beside the runtime's own.

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
- stderr in a bounded log, never journaled, with credentials masked;
- `stop(grace)`: end of stdin, wait, `SIGTERM`, wait, `SIGKILL`, then verify;
- the allowlisted environment from `harness_env(spec)`, with what a login needs from the shell added by name, as in
  `harness_env(spec, "CODEX_HOME")`.

The host masks every report on its way in, whichever driver said it, and holds back the end of live text until the next delta or any
other report, as a secret can straddle two deltas. So if you cut text to fit a field, mask it first, because a cut can split a secret:
`process.gist`, `process.reason` and `process.unknown` do both, and `Held(process.redact)` does the same for a stream of chunks.

For a line protocol, `read_lines` in `platoon_harness.rpc` splits on LF only and bounds a line, and `Lines` adds answers that arrive
among events. For JSON-RPC, `Peer` is the whole client: it takes a handler for inbound calls, and `jsonrpc=False` for a peer that omits
that member.

## Conformance

`check_driver` runs named checks and reports every failure at once. It reads ground truth from a loopback model's log, so "our tool
in the first request" means the tool was in the request, and "connected" counts for nothing. An unsupported check is a skip with a
reason, and a skip is never a pass.

<!-- example: the conformance test a test runs -->
```python
import sys
from pathlib import Path

from platoon_harness.drivers.wire import WireDriver
from platoon_harness.testing import check_driver

PROGRAM = str(Path(__file__).with_name("my_driver.py"))


async def test_my_driver_conforms(tmp_path):
    result = await check_driver(lambda: WireDriver([sys.executable, PROGRAM]), folder=tmp_path)

    assert result.failed == (), str(result)
```

| Check | What it proves |
|---|---|
| `describe_starts_nothing` | `describe` reaches nothing, and two answers agree |
| `ready_with_pinned_model` | `ready` names the model asked for, and the first request asked for it |
| `effort_honored_or_refused` | An effort reaches the first request as it was given, or `start` refuses it. Needs a dialect |
| `unset_model_refused` | With access given and no model, `start` refuses. Needs a dialect |
| `tool_in_first_request` | Our tool is in the first model request. Needs an MCP path |
| `delivered_text_in_next_prompt` | A delivery's text is in the next prompt, and `input.delivered` came. Needs a persistent session and a `turn` boundary |
| `turn_end_reported` | A turn starts and ends |
| `no_goal_takes_no_turn` | With no goal it waits, and its first prompt is what it was sent. Needs a persistent session and a `turn` boundary |
| `interrupt` | A stalled turn ends `interrupted`, and the agent lives on. Needs `interrupt` |
| `resume` | A new instance resumes, takes a delivery and still knows what came before. Needs `resume` |
| `reconcile_claims_nothing_unseen` | After a restart, an input that landed is no `not_landed`, and one never sent is no `landed`. Needs `resume` |
| `approval_answered` | An approval is requested, and its answer reaches the model. Needs `approvals` |
| `denial_holds` | A tool denied never runs: the file only its command makes is not there. Needs `approvals` |
| `exit_reported` | A harness killed from outside is reported gone |
| `stop_leaves_no_process` | Every recorded group is gone after `stop`. Skipped for a driver that starts no process |
| `stop_ends_a_running_tool` | A shell tool under way when `stop` comes ends too, and so do the child it put in the background and the one it put in a session of its own. Pass `shell`, or it is skipped, and `operational` stays `unverified` |
| `malformed_frame_is_a_gap` | A bad frame becomes `native` plus a gap. Pass `garble`, or it is skipped |
| `steers_at_declared_boundary` | A delivery lands at a boundary inside a turn. Needs one, and an MCP path, as a call of our tool is what makes the boundary |
| `measures_reported` | Each declared unit comes with a turn, and `tokens` adds up to the input and output the model said |
| `call_ids_reported` | `model.call` carries the id the model gave, an item names it, and so does usage of one call. Needs `call_ids = "call"` |
| `preamble_once_per_request` | `spec.instructions` appears once in every model request, across a tool call and a next turn. Needs an MCP path |
| `tool_item_carries_its_anchor` | A tool item's `native_id` equals the anchor its harness sent on the MCP call. Skipped for a harness that sends none |
| `native_children_off_by_default` | The first request offers no tool for a native child, and with `spec.allow_native_children` it does. Needs `native_children`. Pass `child`, or it is skipped |
| `native_child_seen` | A native child is reported. Needs `native_children`. Pass `child`, or it is skipped |
| `dialects_spoken` | Every model call was in a declared dialect |
| `one_shot_exits` | A harness that is not persistent exits after its turn |
| `declared_but_unproven` | Always a skip: it names what you declared that no check can prove yet |

Each check gets a fresh instance, a fresh model and a fresh folder, and `timeout` bounds each one, so a wedged harness costs only its
own checks. What a driver leaves running, the suite reaps.

| Argument | Default | Say |
|---|---|---|
| `access` | `chat_access`, which sets `OPENAI_BASE_URL` and `OPENAI_API_KEY` | How your harness reaches the model, as a function of `FakeModel`. The key is a dummy |
| `garble` | None | A coroutine function, given the driver, that makes the harness write a frame no parser knows |
| `gated` | A `shell` tool call | A function from a command to a tool call your harness asks approval for |
| `shell` | None | A function from a command to the tool call that runs it. An approval it asks for is allowed |
| `tool` | A call of `conformance_ping` by that name | A function from a note to a call of our tool, by the name this harness's model knows it by, such as `mcp__conformance__conformance_ping` |
| `child` | None | A tool call that starts a native child, by the name the harness shows its model |
| `timeout` | 10 s | How long one check may take |

The result is pinned to the driver and the harness version it reported, and `levels` reads it. A result for another version says
nothing of this one.

```python
from platoon_harness.drivers.levels import Profile, levels

earned = levels(capabilities, Profile(driver="pi", version="1.5.0", login="key", tools="unverified"), result)
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

A role's `harness` is a name, so a team reaches one through a function that makes a driver per agent:

```python
def lead():
    return ScriptedDriver([[Say("done")]])

team = Team(roles={"lead": Role(harness="my_tests:lead")})
```

The module is imported by that name, so keep a script behind `if __name__ == "__main__"`, or importing it runs it again.

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
