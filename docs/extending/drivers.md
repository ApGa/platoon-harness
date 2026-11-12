# Drivers

A driver presents one harness session to the runtime through seven methods. One instance serves one agent. Drivers for
`claude`, `codex`, `pi`, `openhands` and `opencode` ship with the SDK: `openhands` a wire worker whose OpenHands comes
with the SDK's `openhands` extra, [below](#openhands-a-wire-worker), and `opencode` on the SDK's driver of agents that
speak ACP, [below](#acp-agents).
This page is for everyone else: how to write a driver, in Python or any other language, and how to prove it works. A
one-shot CLI needs only a line of config, a program in any language speaks the wire, and a Python package registers a
class, as [the ways in](index.md#ways-in) list.

## The contract

```python
class Driver(Protocol):
    def describe(self) -> DriverInfo: ...  # name, login kind, capabilities, installed, credentials. Starts nothing
    async def start(self, spec: AgentSpec, report: Reporter) -> None: ...  # fresh, or resume from spec.resume
    async def deliver(self, delivery: Delivery) -> None: ...     # delivery.boundary is one the driver declared
    async def interrupt(self) -> None: ...                       # stops the turn, at the boundary it can
    async def answer(self, approval: str, verdict: Verdict) -> None: ...
    async def reconcile(self, input_id: str) -> Reconciled: ...  # landed | not_landed | unknown
    async def stop(self, grace: float) -> None: ...              # ends the process tree it owns
```

A method it cannot honor raises `DriverError`, with the reason. That is how "unsupported" stays loud. The rest is what each
method promises:

- **`describe`** runs before anything is spent. It starts no harness, and gives the same answer when asked twice. `login`
  comes from the harness's own status command, with a short timeout, reading that one field and no credential file, and is
  None when it cannot tell. `version` is the harness version it would run, where it can tell without starting one; `ready`
  says the version that runs. `installed` is the paths its harness reads to run, as it reaches them: where `PATH` finds its
  binary, and what that resolves into. An isolation shows it those, read-only, and nothing else of your home
  ([workspaces.md](../how-to/workspaces.md#where-an-isolated-agent-runs)); a harness in the runtime's own process declares
  none, as nothing can confine it. `credentials` is where, beneath `spec.folder`, your harness keeps a credential, as
  relative paths with no `..`, which the agent's stop removes, whole, once it ends: name the files your harness's own code
  keeps a login or a key in, where your launch puts its state, and no transcript, as that is the record. A wire program names
  its own beneath the folder its frame names.
- **`start`** begins the first turn on `spec.goal`, which is a `Delivery` like any other: hand it over as `deliver` would, under its
  `input`, which is the id of the offer that launched the agent, and say `input.delivered` once it lands, as for any input. That
  report is what confirms the launch. With no goal, or given `spec.resume`, which reopens that native session, it waits
  for a delivery. An unset model on the harness's own login means the harness's own default, and `ready` says which. Where access was
  given, in `spec.access`, a driver refuses an unset model, since the default may then go somewhere nobody chose. That access is
  variables by name, which `keys_of(spec)` reads and `harness_env` puts in the harness's environment, or a `Gateway`, which only a
  driver that declares `sealed` is given, with `spec.model` the model it serves. Any process on the machine can read a command line,
  so one may name a variable of that access and never hold its value. `spec.effort` goes to
  the harness as it stands, and a driver that cannot honor one raises `DriverError`. `spec.sandbox` is one of the values declared in
  `sandboxes`, and None leaves it to the harness. Unless `spec.allow_native_children` says otherwise, the harness offers its model nothing of
  its own for starting agents: turn that off by a setting for this launch alone, declare `native_children_off`, and say in your docs
  what that cannot reach, such as an extension's tool. A driver that cannot turn them off declares agents of its own and not that, and
  `team check` then refuses a role on it that does not allow them. `spec.instructions` holds the preamble and then the role's words, fixed at launch: hand
  them over once, as they are, through the harness's supported path, and never per turn. A resume gives the same text again, as
  Claude Code and Codex keep what a session began with whatever a resume passes. The runtime journals them as what the agent was told.
  A `HOME` in `spec.env` is the harness's home, as the runtime gives an isolated harness one in its folder: `harness_env` then passes
  none of the variables that keep a harness's state elsewhere, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `PI_CODING_AGENT_DIR` and
  `PI_CODING_AGENT_SESSION_DIR`, so the harness keeps its state there, and the driver reads it there. `spec.wrap` is the argv of the
  isolation it runs in, empty for a harness that runs unconfined. `Process.launch` puts it between the trampoline and the command, so
  the confiner is the group's leader and what the harness starts is confined with it. A driver that starts its harness otherwise must
  do the same.
- **`deliver`** hands over `delivery.text`. The id goes out with it, so `input.delivered` can say what landed, and `reconcile` can
  answer after a crash. It returns once the harness has the text. Delivery is at-least-once: a delivery can land twice, and its
  refs dedupe it.
- **`interrupt`** stops the turn, or the one a delivery on its way is about to begin, and that turn ends `interrupted`. The agent lives
  on. A delivery the harness took and had not landed comes again under a new input, so tell a harness that keeps such a thing to
  drop it, where it can be told.
- **`stop`** leaves no process behind, a running tool and what it put in the background included. A tool that leads a group of its
  own outlives a `SIGKILL` of its harness, so ask a harness to end first, and with real grace. It reports the gap `crash_window`
  when it comes to `SIGKILL`.

### What a driver reports

`report` is a plain async callable. It takes this vocabulary and no other.

| Report | Fields | When |
|---|---|---|
| `Ready` | `native`, `version`, `effective_model`, `tools_visible` | The harness is up. `tools_visible` is a list only when it was observed |
| `TurnStarted` | `turn` | No two turns of one agent share a name, across a resume too: a tool call with no id of its own is keyed on it |
| `TurnEnded` | `reason` | `stopped` if it stopped on its own, `interrupted` after an interrupt, and otherwise what went wrong, such as `aborted`. `lost` and `stopped by its owner` are the runtime's own, never a driver's. For a one-shot harness this is its end |
| `Delta` | `text` | Live text. It is lossy and never journaled |
| `Item` | `kind`, `gist`, `phase`, `native_id`, `call_id`, `body`, `approval`, `outcome` | A `message`, `thought`, `tool` or `patch`, its `gist` at most 280 characters and its `body` the whole text. A `tool` or a `patch` is `started`, then `completed`. `call_id` names the model call that made it, and `native_id` is the harness's own id. A tool item whose `native_id` is its call's anchor and whose `outcome` is `completed` confirms what that call's result showed, so report it once the result is in, and `failed` when the result never came back |
| `InputDelivered` | `input`, `boundary`, `evidence`, `native_id` | A delivery reached the harness, the goal at launch among them: this is the one way an offer is confirmed. `evidence` names what showed it, and `native_id` is the harness's own id for what landed, verbatim, the one its compaction would name that input by, or None when it gives none |
| `ApprovalRequested` | `id`, `gist`, `body`, `cut` | The harness is waiting on a decision. `body` is the whole of what it asks to do, as the harness gave it, or None when you cannot say, which is unknown and fails `approval_shows_its_ask`. Send it whole: the host masks it and keeps its first 64 KiB, adding the bytes it left out to `cut`. A program that cuts it first says in `cut` how many bytes it left out |
| `ModelCall` | `call_id`, `model`, `purpose` | A model call, with its id only when the id is real. `purpose` is the harness's own word for why, such as `compaction`, and None unless it said |
| `Usage` | `tokens`, `usd`, `label`, `scope`, `call_id` | What was spent, once. `scope` is `call`, `turn` or `tree`, and `label` is `provider`, `estimated`, `lower_bound` or `unavailable`. `call_id` names the call a `call` scope paid for |
| `Compacted` | `forgotten`, `summary` | Context was compacted. `forgotten` holds the native ids of what left it, and `summary` the text that took its place |
| `ChildSeen` | `native`, `parent` | A native child it made on its own, and the tool call that started it. It claims no attribution: how well a call is tied to an agent is the record's to say |
| `GapReport` | `what` | Something went unseen, from a closed list, `GAPS`, which gives each its plane |
| `Native` | `kind`, `raw`, `cut` | A frame nobody's vocabulary covers |
| `Exited` | `reason` | The harness is gone. One that went on its own, which no `stop` asked for, rests its agent once: a turn it was in is cut off, and the agent's next handover starts the harness again with `spec.resume`, so a driver whose harness can reopen its session needs nothing more |

What changed in a workspace is not a report: the runtime looks at it itself at each turn's end, so even a harness that reports nothing
of its files is covered, and a program that sends `changes`, which an earlier vocabulary had, gets `native` plus a gap.

Never guess. Unknown is `None`, not zero, not an empty list, and not a plausible id. A frame you cannot read becomes `Native` plus a
gap, which is what `unknown_frame(kind, raw)` returns, and never a log line. That holds for a frame of a known type with a shape you did
not expect, whichever part of it would not read, and `UNREADABLE` names what reading one raises: one changed field in a harness's update
must cost a gap, not the agent. A request the harness waits on still gets an answer, and a turn's end still ends the turn.

Send `started` where the harness shows it. A tool that has begun and not finished is an `Item` of kind `tool` in that phase, and it is
all a person watching has to say what is running, since `activity` is the gist of the latest item. Then send its `completed`.

**What the provenance queries read of your reports.** `exposure`, `lineage` and `contributors` say only what your ids let them, and
nothing joins by order or timing:

- A `ModelCall` with a real `call_id`, sent before the tool items that call chose, each naming that `call_id`, lets a tool call join
  the model call that chose it. An answer about an event that call made then counts only what was confirmed before the call, on your
  agent's own report stream. With no `call_id` the bound is the event's commit, and the answer says `commit`.
- A tool item whose `native_id` is the anchor the MCP call went under, and whose `outcome` is `completed`, confirms what that call's
  result showed, and reaches the item. One that `failed` confirms nothing, as the result it would vouch for never landed. A harness
  whose MCP client sends no id of its own can put it among a call's arguments as `_meta`, which the stdio shim moves to where MCP
  keeps it, as the `pi` driver's extension does with pi's tool call id.
- `InputDelivered.native_id`, the id your harness's compaction would name that input by, and `Compacted.forgotten` naming those ids,
  let a compaction mark a handover `forgot` or `kept`. Otherwise it is `unsaid`, as a read always is. If your harness names that id
  only after the input has landed, hold what it says after the input until you have it, so that your reports keep its order, as the
  `pi` driver does with the entry pi wrote an input down as.
- Every `GapReport` you send is a reason an answer is `unknown` from where it began, if content could come through it: `GAPS` says which.

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
| `native_children_off` | Whether it turns them off for a launch whose role does not allow them. A role on a harness with them that cannot must allow them |
| `call_ids` | `none`, `agent`, `call` |
| `dialects` | `chat`, `responses`, `messages` |
| `coverage` | For each of `prompt`, `tool_results`, `shell_reads`, `files`, `native_children`, `compaction`, `external`: `observed`, `partial` or `none` |
| `measures` | Which of `tokens` and `usd` it reports |
| `sandboxes` | The values a role's `sandbox` may take |
| `sealed` | Whether it launches on a gateway's access with nothing of the user's: only a driver that says so is given a `Gateway` |

A declaration earns nothing by itself. See [Conformance](#conformance).

### A sealed launch

A training system's authority admits an agent through its gateway: `spec.access` is then a `Gateway`, and only a driver that
declares `sealed` is given one. Such a driver launches its harness with nothing of the user's:

- **The gateway's model, under its bearer.** Its models are at `origin`, which is a scheme and a host, so a client that wants a base
  with `/v1` adds it, and `model` is the one `spec.model` names.
- **The bearer goes by environment alone,** under `BEARER_VARIABLE`, `PLATOON_HARNESS_BEARER`, where `harness_env` puts it. A file
  the launch writes names the variable, as `${PLATOON_HARNESS_BEARER}`, never its value: the agent's folder is part of the session's
  export.
- **Ours and the environment's tools.** `Gateway.tools`, when there is one, is the environment's own MCP server, under the same bearer:
  give it to the harness beside ours, named `ENVIRONMENT`, `environment`. Its tools reach the model named by that server, never bare,
  in the harness's own form for a server's tools, so none can collide with one of the harness's own: an environment may well have a
  `finish`. No tool of the harness's own that acts on the world stays:
  no shell, no file tool, no agents of its own, and a call of one the model makes runs nothing.
- **Nothing of the user's.** None of their settings, extensions, skills or project instructions, and no retries, as a retry is a
  call a gateway records twice.
- **Compaction on, labelled.** Each call the harness makes to compact its context carries `Gateway.compaction_headers`, and is
  reported as `ModelCall(purpose="compaction", call_id=...)` with the id the model gave it.

How each harness here does it:

| Harness | Sealed launch | Compaction calls |
|---|---|---|
| ScriptedDriver | Its access is the gateway's, and it lists the environment's tools beside ours, as `mcp__environment__<tool>`; a call of its `shell`, or of any tool neither lists, is told there is no such tool and runs nothing | A `Compact` step: one call, with the headers, reported with its id |
| A wire program | It finds the gateway in its launch frame, and the bearer in the variable the frame names, and names the environment's tools by their server | It sends the headers from its frame, and reports each call with its id |
| `pi` | An agent directory of its own in the agent's folder, settings that retry nothing and warm no cache, `--no-builtin-tools`, `--no-context-files`, `--no-skills`, `--no-prompt-templates`, `--no-themes`, `--no-approve`, `--offline`, and the environment's server registered by our extension, whose tools pi shows as `mcp__environment__<tool>` | Our extension takes `session_before_compact` and runs pi's own `compact` with the headers and a stream function that keeps each response's id, one call or two for a split turn; it says each call made, by its id or null for one that never answered, as a status the driver reads before pi says the compaction ended, so a compaction cut after its first call still reports both |
| `openhands` | None of its coding tools, so ours and the environment's, the latter through an MCP client of their own and named by it as the SDK's client of two servers names a server's tools, `environment_<tool>`, beside its `finish` and `think`; no project instructions | Its condenser's LLM sends the headers as `extra_headers`, and its calls are reported as `compaction` |

A driver with no sealed launch reads access through `keys_of(spec)`, which refuses a gateway, and the host refuses one before that.
Declaring `sealed` earns nothing either: two checks earn it, in the one result kept for the driver. They prove, on the machine's own
home as a rollout runs, that the first request goes under the gateway's bearer, holds none of the project's instructions and shows
only ours, the environment's and the tools `check_driver(kept=)` names. What else of the user's a launch keeps out is how it is
built, as the table says, which no check proves.

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

A relative program, one with a `/` in it, resolves against the session's `cwd`, both when the harness runs and when it describes
itself, whatever its agent's workspace: a worktree holds only what is committed, and your program may not be. If the program dies,
the reason is in the agent's `stderr.log`, which the error names.

A driver runs its harness in `spec.cwd`. That is where the journal says its agent works, which the host takes from the agent's
workspace, so no driver knows the mode. Nothing checks that a wire program's own harness runs there, and `runs_in_its_workspace` in
`check_driver` is how to show it does. An isolated agent's program runs inside its isolation, so its frames name no wrap, and its
`installed` is where `PATH` finds it, with any paths its description adds for what it reads beside.

### In Python

`serve` does the protocol, so a wire driver in Python is a driver plus one line. This one is complete, and a test runs it through the
conformance checks. It asks a model once per turn over Chat Completions.

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
        if spec.goal is not None:
            await self.deliver(spec.goal)

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
> {"jsonrpc":"2.0","id":1,"method":"describe","params":{"protocol":2}}
< {"jsonrpc":"2.0","id":1,"result":{"protocol":2,"name":"mine","login":null,"capabilities":{"persistent":true,"boundaries":["turn"]}}}
```

That was one short process: `describe` runs your program, sends this one frame, closes stdin and expects you to exit, so no harness
may start for it. Starting an agent is a new process.

```jsonc
> {"jsonrpc":"2.0","id":1,"method":"start","params":{"protocol":2,"spec":{"agent":"ada","role":"worker","goal":{"input":"7","boundary":"turn","text":"...","items":[{"ref":"agent/ada@1","gist":"...","sender":null,"body":false}],"behind":0},"cwd":"...","folder":"...","model":"m","effort":null,"sandbox":null,"allow_native_children":false,"tools":{"url":"...","namespace":"ph","bin":"..."},"access":["OPENAI_API_KEY"],"env":{},"instructions":null,"resume":null}}}
< {"jsonrpc":"2.0","id":1,"result":null}
< {"jsonrpc":"2.0","method":"report","params":{"type":"ready","native":"s-9","version":"1.0","effective_model":"m","tools_visible":null}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"input.delivered","input":"7","boundary":"turn","evidence":"prompt"}}
< {"jsonrpc":"2.0","method":"report","params":{"type":"turn.started","turn":"1"}}
> {"jsonrpc":"2.0","id":2,"method":"deliver","params":{"input":"41","boundary":"turn","text":"New messages (delivery 41):\n- inbox/ada@3 from @lead: Keep the API stable","items":[{"ref":"inbox/ada@3","gist":"Keep the API stable","sender":"@lead","body":false}],"behind":0}}
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

- **`protocol`** is an integer, currently 2, and whichever side does not know the other's refuses it. Your side answers `-32002`.
- **Errors.** A method you cannot honor answers `-32001` with the reason, which surfaces as `DriverError`.
- **Credentials never travel in a frame.** `spec.access` names variables, and their values are in your environment. So is the tool
  token, in `PLATOON_HARNESS_TOKEN`, with `PLATOON_HARNESS_URL` beside it. `ph` is on your `PATH`. A program that declares `sealed` may
  be given a gateway instead, as an object: `{"origin": ..., "bearer": "PLATOON_HARNESS_BEARER", "model": ..., "tools": ...,
  "compaction_headers": {...}}`, whose `bearer` names the variable the bearer is in. `serve` gives a Python driver a `Gateway` back.
- **Your environment is an allowlist:** `PATH`, `HOME`, a `TMPDIR` of your own, and what the spec names. Nothing else is inherited,
  but what a driver in Python names in `WireDriver(command, inherited)`, as `openhands` names the proxy variables and what tells
  Python where its modules are, to describe your program as to start it.
- **A line is at most 16 MiB.** Past that the agent stops with a gap, since the line may have held an answer.
- **Stdout is the protocol.** A line that is not a frame costs you a `native` frame and a gap, and an unknown report the same.
- **Exit when stdin ends.** A program still there is sent `SIGTERM`, then `SIGKILL`.
- **Your own subprocesses are yours to end,** in `stop`. Stay in your process group, and the runtime can end them if you cannot.
  On Linux, what leaves the group is found by the `TMPDIR` it inherited, and ended too. A driver of your own that uses `Process` keeps its record in `spec.folder`, which
  on the wire is a folder of its own, so recovery finds both.

## OpenHands: a wire worker

`harness = "openhands"` runs a wire worker per agent, `python -P -m platoon_harness.drivers.openhands` on the runtime's own
interpreter, so nothing is looked up on `PATH` and nothing else is installed. It finds its modules where the runtime does, as
`PYTHONPATH`, `PYTHONUSERBASE` and the rest of what tells Python where they are pass by name, and `-P` keeps the workspace it
runs in off its path. The worker alone loads OpenHands, which the SDK's `openhands` extra brings, pinning `openhands-sdk` and
`openhands-tools` at 1.59.0 exactly. Install it beside the SDK, for the interpreter that runs the runtime, which is the command
line's when it starts a session, as [Install](../getting-started/install.md#openhands) says.

`doctor` shows it with the version of the OpenHands SDK, from its metadata, and its login unknown, as OpenHands keeps none and
only a role's auth profile gives it a key. Without the extra, `doctor` names the interpreter to install it for, and an agent's
start is refused in the same words. Nothing else changes: the SDK, the runtime and the command line never load it.

**An environment of its own.** OpenHands' pins share an environment with little, `mcp` 2.3.0 not among it. Where yours cannot hold
them, install the SDK with the extra in an environment of its own, and name its interpreter and the module as a wire command:

```toml
[roles.worker]
harness = { command = ["/opt/openhands/bin/python", "-P", "-m", "platoon_harness.drivers.openhands"], mode = "wire" }
model = "gpt-5.4"
auth = "openai"
```

The worker is then a wire program like any other, so the shell's proxy variables and `SSL_CERT_FILE` reach it only where
its auth profile names them.

What an OpenHands agent does differently from the others:

- **Sign-in** is a key alone, `OPENAI_API_KEY` from the role's auth profile, with `OPENAI_BASE_URL` for an endpoint other than
  OpenAI's; a role with none is refused.
- **No retries:** a failed model call ends the turn, as a retry is a second call a gateway records.
- **No step cap:** the role's budget is what limits a run.
- **One approval per step:** every action asks the runtime but a call of our tools and a lone `finish` or `think`, and one
  approval covers what a step holds, with each of its actions as its ask.
- **Its own agents are off** unless a role allows them; allowed, a child is the gap `native_child_unattributed`, its spending
  its parent's.
- **Spending:** tokens are the provider's, and dollars come only where litellm prices the model, as an estimate. An interrupt
  abandons a model call in flight, which a gateway may have recorded all the same, so that turn says its usage is a lower bound.

## ACP agents

`AcpDriver(command)`, the SDK's `platoon_harness.drivers.acp`, drives an agent that speaks the Agent Client Protocol on
stdio, at protocol 1 alone, over the SDK's `Peer`, adding no dependency. It is experimental: no real ACP agent has
passed its checks, and OpenCode 2.2.6, run by hand on 2026-11-08, failed 7 of 18 ([STATUS](../STATUS.md)).
`harness = "opencode"` is that driver on `opencode acp`, and a driver for another agent of ACP is a subclass that names
its command, as `OpenCodeDriver` does:

```python
from platoon_harness.drivers.acp import AcpDriver


class MyAgentDriver(AcpDriver):
    name = "my-agent"

    def __init__(self) -> None:
        super().__init__(("my-agent", "--acp"))
```

Each rule it keeps, in a sentence:

- **Protocol 1 alone:** it asks for 1, and stops an agent that answers anything else before it opens a session, as ACP has
  a client disconnect from a version it does not speak. It offers no file system and no terminal, so the agent keeps its own
  tools, and takes compaction updates.
- **The session** opens with the agent's workspace as `cwd` and our tools as one MCP server over HTTP under the agent's bearer,
  so an agent that reaches no server over HTTP is refused. A resume takes it up again by `session/resume`, which an agent that
  offers none refuses.
- **Instructions** go as `systemPrompt`, appended, where the agent offers one, sent again on a resume, and otherwise before
  the session's first prompt, once.
- **The model** is set through the session's config option of category `model`, and `ready` names what that option then
  holds. An agent that offers none refuses a start that names a model, and `opencode` refuses one that names none, as
  OpenCode then sends prompts to a hosted model nobody chose.
- **A turn** is one `session/prompt`, from its request to its answer, and the turn is the one boundary declared. A delivery
  during a turn waits for its end and goes as the next prompt, an interrupt drops what waits, and one for any other boundary is
  refused.
- **A delivery lands** at the first update after its prompt that is not of the session's state, or at the prompt's answer.
- **Text** comes as live deltas, and a message or a thought is one item once another kind of update, another message or the
  turn's end follows.
- **A tool call** is an item from its `tool_call` to the update that ends it, `completed` or `failed`, which names the approval
  that let it through.
- **A permission request** is an approval whose whole ask is the tool call it names, as the agent last updated it, so a
  request that names its call by id alone asks what the agent said of it before: a line for each of its title, tool name and
  kind and each place it names, then its input as JSON, then its content as it is, a diff as its path and new text. A call that
  says none of these carries no ask, and its gist says so. The verdict goes back as the option of its kind for this once, as
  an `always` option would decide more than was asked. Where the request offers none, the answer is `cancelled`, which runs
  nothing, so a denial holds and an allow fails, saying it was not carried out. An interrupt and a turn's end answer each
  request still waiting `cancelled`, as ACP asks.
- **A compaction** that completed is `compacted`, with its summary and what it forgot unknown.
- **A change of mode or of a config option**, the model among them, once the session is ready, is `native` with its raw frame
  and the gap `unknown_update`, as `ready` named the model the record holds. One that says what was said already is not
  reported.
- **What says nothing** of the agent's work, its commands, title, context size and notices, is not reported. Any other
  update, method or line is `native` with its raw frame and the gap `unknown_update`, and a prompt answered with no stop
  reason ends its turn saying so.
- **Never trainable:** ACP names no model call and says no spend of one, so it reports no `model.call` and no `usage`, declares
  no `call_ids` and no `measures`, and has no sealed launch.
- **An agent's own agents** are `opaque`, and it declares no `native_children_off`, as stable ACP neither shows them nor turns
  them off, so a role on it must say `allow_native_children = true`, and `team check` refuses it otherwise.

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
| `delivered_text_in_next_prompt` | The goal, the first delivery, is in the first prompt and said to have landed under its launch offer's id, and a later delivery's text is in the next prompt once `input.delivered` came. Needs a persistent session and a `turn` boundary |
| `turn_end_reported` | A turn starts and ends |
| `no_goal_takes_no_turn` | With no goal it waits, and its first prompt is what it was sent. Needs a persistent session and a `turn` boundary |
| `interrupt` | A stalled turn ends `interrupted`, and the agent lives on. Needs `interrupt` |
| `resume` | A new instance resumes, takes a delivery and still knows what came before. Needs `resume` |
| `reconcile_claims_nothing_unseen` | After a restart, an input that landed is no `not_landed`, and one never sent is no `landed`. Needs `resume` |
| `approval_answered` | An approval is requested, and its answer reaches the model. Needs `approvals` |
| `denial_holds` | A tool denied never runs: the file only its command makes is not there. Needs `approvals` |
| `approval_shows_its_ask` | An approval carries as its body the whole command it asks about, of some 5 KiB, with its letters outside ASCII as themselves. Needs `approvals`. A failure leaves `operational` unmet, as one of `approval_answered` or `denial_holds` does |
| `exit_reported` | A harness killed from outside is reported gone |
| `stop_leaves_no_process` | Every recorded group is gone after `stop`. Skipped for a driver that starts no process |
| `runs_in_its_workspace` | A shell tool runs in `spec.cwd`, a folder that is no default: its `pwd -P`, written to a pipe, names that folder. Pass `shell`, or it is skipped, and `operational` stays `unverified` |
| `stop_ends_a_running_tool` | A shell tool under way when `stop` comes ends too, and so do the child it put in the background and the one it put in a session of its own. Pass `shell`, or it is skipped, and `operational` stays `unverified` |
| `malformed_frame_is_a_gap` | A bad frame becomes `native` plus a gap. Pass `garble`, or it is skipped |
| `steers_at_declared_boundary` | A delivery lands at a boundary inside a turn. Needs one, and an MCP path, as a call of our tool is what makes the boundary |
| `measures_reported` | Each declared unit comes with a turn, and `tokens` adds up to the input and output the model said |
| `call_ids_reported` | `model.call` carries the id the model gave, an item names it, and so does usage of one call. Needs `call_ids = "call"` |
| `preamble_once_per_request` | `spec.instructions` appears once in every model request, across a tool call and a next turn. Needs an MCP path |
| `tool_item_carries_its_anchor` | A tool item's `native_id` equals the anchor its harness sent on the MCP call. Skipped for a harness that sends none |
| `native_children_off_by_default` | The first request offers no tool for a native child, and with `spec.allow_native_children` it does. Needs `native_children` and `native_children_off`. Pass `child`, or it is skipped |
| `native_child_seen` | A native child is reported. Needs `native_children` that are `observed`. Pass `child`, or it is skipped |
| `dialects_spoken` | Every model call was in a declared dialect |
| `one_shot_exits` | A harness that is not persistent exits after its turn |
| `sealed_first_request_holds_only_ours` | On a gateway, the first request goes under its bearer, holds none of the instructions an `AGENTS.md` or `CLAUDE.md` in the folder it works in gives, and shows no tool but ours, the environment's named by its server, and those `kept` names. Needs `sealed` |
| `environment_tools_in_first_request` | On a gateway, each of the environment's tools, at the URL the gateway names, is in the first model request named by the environment's server, never bare, so FakeModel's `finish` and `think` collide with no tool of the harness's own. Needs `sealed` |
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
| `kept` | None | The names of the tools of the harness's own that a sealed launch keeps, each of which acts on nothing, such as OpenHands' `finish` and `think` |
| `timeout` | 10 s | How long one check may take |

The result is pinned to the driver, by its name and the class that implements it, the harness version it reported, the SDK, the
host it ran on and, for a class outside the SDK, the release of each distribution that holds it. So a program calling itself
`claude` earns nothing from what was kept of the claude driver's checks, a result made elsewhere, or of a version nobody said,
says nothing of this agent, and an upgrade reads `unverified` until it is checked again. The runtime reads a result kept under the
root at every launch and resume, where `write_conformance(root, result)`, from `platoon_harness.runtime.paths`, keeps one, and
`platoon-harness doctor --check` makes one for each harness `levels.CHECKED` names and for an installed driver whose
`DriverInfo.check` names its check, as `module:function`, imported only to run it. A level with no result that speaks for the
harness that runs says so, and names what makes one.

```python
from platoon_harness.drivers.levels import Profile, implementation, levels

profile = Profile(driver="pi", implementation=implementation(driver), version="1.5.0", login="key", tools="unverified")
earned = levels(capabilities, profile, result)
```

`levels` gives `operational`, `observable` and `trainable`, each `met`, `unmet` or `unverified`, with reasons. It is a pure function,
and nothing a driver says reaches it except through a check that passed. Native and plan logins are never trainable: `trainable`
needs a gateway login, a driver that declares `sealed`, our tools seen, and a kept result whose sealed checks passed beside
`ready_with_pinned_model`, `tool_in_first_request` and `call_ids_reported`.

### A real binary for free

`FakeModel` speaks Anthropic Messages, OpenAI Chat Completions and OpenAI Responses, with streaming, so a real harness runs against it
on a dummy key and spends nothing. Give it an isolated home, so that no login of yours takes part. A tool call you give no id gets
one of its reply's own, `call_<reply>_<place>`, so no two calls share one, as a model's never do.

```python
from platoon_harness.testing import FakeModel, ToolCall

async with FakeModel(ToolCall("wait", {"timeout": 60}), "done") as model:
    ...  # point the harness at model.url

model.calls[0].offers("wait")   # was the model shown the tool?
model.calls[1].says("call_1_0") # did its result come back?
model.requests                  # everything that arrived, exactly as it arrived
```

### A scripted harness

`ScriptedDriver` is a deterministic harness for tests and demos: one list of steps per turn. Its tool calls are real MCP over the
binding, so a scripted team exercises the real tool plane. It has one tool of its own, `shell`, which runs its `command` once an
approval allows it, in `spec.cwd`, in a group recorded before it can run, so `check_driver` with `shell` holds it, in this process or
behind a wire program, to every check a harness's shell meets. Its capabilities are data, and it holds to them, so a test can make it
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

A step that goes on from what a call answered is a `Do`: code of the harness's own, run as `act(spec, call)`, where `spec` is the
agent's `AgentSpec` and `call(tool, arguments)` calls a tool as a `Call` step does and returns its MCP result. Each of its calls goes
under an id of its own, as a harness's own calls do, so two identical calls in one turn are two calls, and its ops join no model
call, as no model chose them. `ScriptedDriver(itertools.repeat([Do(act)]))` runs `act` every turn.

The steps are `Say`, `Think`, `Call`, `Do`, `Wait`, `EndTurn`, `Fail`, `Exit`, `Ask`, `Hang` and `AskModel`, which makes real model calls
until the model only talks. A tool call the model chose goes under the id the model gave it, as `scripted/toolCallId` in MCP's
`_meta`, which its tool item holds, so its op joins that model call as a Claude Code or pi tool call does, and conformance's
`tool_item_carries_its_anchor` holds it to that. A call under an id it has sent already fails its turn, since its op would join the
call that sent it first. A `Call` step, which no model chose, sends no id, so the tool plane keys it by its turn, and an identical
one in the same turn is answered as a repeat. `Ask(gist, body)` asks for an approval with `body` as its whole ask, and the approval
its `shell`, or any tool of its own that `AskModel` meets, asks for carries the tool's name and its input as JSON. A step that
raises, of its own or of a subclass's, fails its turn saying what it raised, and the next turn runs.
