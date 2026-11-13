# RFC 0082: A launch in the environment keeps the harness's own tools

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-13 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`drivers/__init__.py`](../../packages/sdk/src/platoon_harness/drivers/__init__.py), [`runtime/authority.py`](../../packages/sdk/src/platoon_harness/runtime/authority.py), [`runtime/host.py`](../../packages/sdk/src/platoon_harness/runtime/host.py), [`drivers/levels.py`](../../packages/sdk/src/platoon_harness/drivers/levels.py), [`drivers/env.py`](../../packages/sdk/src/platoon_harness/drivers/env.py), [`drivers/wire.py`](../../packages/sdk/src/platoon_harness/drivers/wire.py), [`drivers/pi.py`](../../packages/sdk/src/platoon_harness/drivers/pi.py), [`drivers/openhands/agent.py`](../../packages/sdk/src/platoon_harness/drivers/openhands/agent.py), [`testing/scripted.py`](../../packages/sdk/src/platoon_harness/testing/scripted.py), [`testing/conformance.py`](../../packages/sdk/src/platoon_harness/testing/conformance.py), [architecture sections 9](../architecture.md#9-drivers), [14](../architecture.md#14-training) and [15](../architecture.md#15-security), [RFC 0049](0049-the-contract-a-training-authority-gets.md), which this extends, and [RFC 0053](0053-a-gateway-admission-launches-sealed.md), which this amends |
| Discussion | None yet |
| Implementation | None yet |

## Summary

A training system that runs a whole session inside its environment's own sandbox says so on each agent's gateway,
`Gateway.in_environment`, and that launch keeps the harness's own tools: OpenHands its terminal, file editor and task
tracker, pi its `read`, `bash`, `edit` and `write`, and the scripted harness its `shell`. The rest of RFC 0053's sealed
launch stands: the gateway's model on its bearer, nothing of the user's setup or the project's instructions, no
retries, each compaction labelled as it is made, and no MCP server but ours and the environment's. Only an authority
gives a gateway, so nothing a team, a role, a person or the command line names can keep a harness's own tools on one,
and a session runs in one place, so the host refuses an admission whose gateway says otherwise than the first. A driver
that has the launch declares `in_environment`, and the host refuses such a gateway to any other before that agent's
harness launches; the start records the launch, and `trainable` stands on one more check,
`own_tools_in_first_request_in_the_environment`. What those tools do is in the record only as the harness reports it.
The SDK cannot see where it runs, so the word is the authority's to keep true. Every harness, the runtime and whatever
the model runs share one user there, as on any session whose agents have a shell, so a command can read any agent's
bearer and write the journal. The host masks every credential the runtime has given a harness in every report, so a
bearer a command prints stays out of the journal, though not out of a harness's own transcript, which the export holds;
and a call no harness reported has no id in a record no command altered. A user for each harness is left open.

## Motivation

A training system that runs a whole session inside a task's sandbox, from a read-only toolchain that holds the SDK,
needs this: the runtime, the journal, the tool server and every harness process in the sandbox, with every agent
admitted through its gateway, trainable. Platoon, a training system, places a single harness there today, from a
read-only toolchain that holds that harness and not this SDK, and runs its platoon-harness team on its own host
(Evidence). In the sandbox a harness could act on the task with its own tools, as it does when a person runs it, and as
it does when a training system places it there alone. It cannot: a gateway admission launches sealed
([RFC 0053](0053-a-gateway-admission-launches-sealed.md)), with no tool of its own that acts, so a team's agents reach
the task only through what the environment's server serves, and a harness behaves otherwise as a member of a team than
alone on the same task.

RFC 0053 seals a gateway's launch for what a training system needs of it, in its own words:

| Need | Inside the environment's sandbox |
|---|---|
| "Every call must go on the agent's own bearer, which ties it to that agent, and no credential may outlive the rollout in a file of the session's, which is its export" | Holds of what the SDK and the harness do on their own; not against a command the model runs, which can use any agent's bearer, write the journal and into any harness's pipes, so as to report a call it made as any agent's, and print a bearer that its harness's transcript keeps in the export (section 7) |
| "The policy must see nothing of the user's setup" | Holds: the launch still keeps every setup it finds out of the prompt; what an agent reads with its own tools is the task's, as the environment's tools could read it |
| "and no tool that acts outside the training system's environment, whose own tools come through an MCP server of its own" | Stops holding: the harness runs in the environment, so its own tools act on the environment's machine, and on whatever its network reaches, as a shell the environment serves would |
| "a call a harness makes to compact its context must be told apart when it is made" | Holds |

Its launch also retries nothing, as a retry is a second call a gateway records, which holds as well. So in the sandbox
the third need stops holding where a launch keeps the harness's own tools, as this RFC means it to, and the first holds
only of what the SDK and the harness do on their own, sealed or not, as whatever the environment's own tools run shares
the sandbox with the session. Code is cited below as `path:line` at `e73a221`, under
`packages/sdk/src/platoon_harness/`. Nothing tells the two launches apart today:

- pi takes `--no-builtin-tools` among what a sealed launch keeps out (`drivers/pi.py:102-111`), on every gateway
  (`drivers/pi.py:330-337`).
- OpenHands gets `tools = []` on every gateway (`drivers/openhands/agent.py:147-153`).
- On a gateway, the scripted harness answers a call of a tool that is neither ours nor the environment's with "there is
  no tool" (`testing/scripted.py:155-157`, `431-432`).
- The host gives a gateway only to a driver that declares `sealed` (`runtime/host.py:420-423`), and `trainable` stands
  on `sealed_first_request_holds_only_ours` (`drivers/levels.py:63-72`), which fails on any tool of the harness's own
  but one its check names as acting on nothing (`testing/conformance.py:690-707`).

## Proposal

### 1. The gateway says the session runs in the environment

Nothing the SDK holds today can tell a session inside the environment's sandbox from one beside it:

- **The admission** (`runtime/authority.py:36-55`) is a token, model access and the backend's ids. A training system
  that admits through its gateway gives the same in either place.
- **The session's start** (`session.py:217-231`) takes a name, a principal, approvals, an authority, `detach`, `cwd`,
  `root`, a clock, `plan_login` and `trainable`. A session started in the sandbox passes what one started on a training
  system's own host passes, and none of it says where.
- **The principal** is "a name and not a claim" (`session.py:234`): `program:<name>` names a training system in either
  place.

The SDK cannot see where it runs, and a guess would be a word nobody gave. The party that placed the session knows, and
in a trainable session it admits every agent through its authority. So the gateway carries that word:

```python
class Gateway(Model):
    origin: str
    bearer: Secret
    model: str
    tools: str | None = None
    compaction_headers: Mapping[str, str] = {}
    in_environment: bool = False  # the session runs in the environment, on the machine its tools act on
```

**The rule: a gateway admission launches sealed, and keeps its harness's own tools only when its gateway says the
session runs in the environment.**

The gateway is the place because of what it already is:

- **Only an authority gives one** ([RFC 0049](0049-the-contract-a-training-authority-gets.md)), and access by variables
  is a person's own launch, which was never sealed. So no team file, role, setting, command or person's act can keep a
  harness's own tools on a gateway: nothing they name reaches `Gateway`. `LocalAuthority`, which the command line runs
  on, gives none.
- **It already carries what the environment gives a launch**: its server's tools, `tools`, beside the model.
- **It already reaches the driver**, as `spec.access`, so `AgentSpec`, `Session.start` and the team file stay as they
  are.

**One place for a session.** A session runs in one place, so its gateways say one thing. The host keeps the word of the
first gateway it admits for the runtime's life, and refuses, saying so, an admission whose gateway says otherwise, as it
refuses an admission on a bearer another agent holds (`runtime/host.py:310-316`). That agent's spawn fails before its
harness launches, and the agents admitted before it run on.

**A wire frame names the word only where it is true.** Today a frame dumps the gateway with every field, defaults among
them (`drivers/wire.py:54-55`), so every gateway frame would carry `"in_environment": false`, which a program built on
an earlier SDK refuses, as a model refuses a field it does not declare (`schema.py:68`). So the frame leaves
`in_environment` out where it is false and names every other field as now, and a program built on an earlier SDK, or
one in another language that reads today's frame, takes every frame it took before, unchanged. It never meets a gateway
in the environment: it cannot declare the launch, and the host refuses it such a gateway first (section 2). In the
other direction nothing changes: a program describes itself with every field (`drivers/wire.py:231-233`), so a runtime
of an earlier SDK refuses the description of a program built on this one, as it refuses any field added since, saying
the program did not describe itself (`drivers/wire.py:115-124`).

The SDK cannot check the word. A gateway that says it of a session outside the environment gives that session's
harnesses their own tools wherever it runs. Keeping it true is the authority's, as its tools' URL and its model are, and
every start records it (section 4), so the record shows each launch that kept its harness's tools.

### 2. A launch in the environment, driver by driver

A launch in the environment is RFC 0053's sealed launch with the harness's own tools kept, and nothing else changed. It
admits no MCP server but ours and the environment's, so a task's own servers reach no agent (section 8). A driver says
it has the launch with a capability:

```python
class Capabilities(Model):
    ...
    sealed: bool = False
    in_environment: bool = False  # on a gateway in the environment, its sealed launch keeps the harness's own tools
```

The host gives a gateway in the environment only to a driver that declares it, and refuses it to any other, saying so,
before that agent's harness launches, as it refuses a gateway to a driver with no sealed launch
(`runtime/host.py:420-423`): "`<driver>` has no launch in the environment, which its gateway asks for".
`check(team, trainable=True)` cannot refuse it sooner, as it never sees a gateway (`runtime/opening.py:81-93`). A
training system that places its sessions in its environment can refuse such a role before any cost, from what the
role's driver declares in `describe`.

| Driver | Its launch in the environment | What it needs there |
|---|---|---|
| OpenHands | Its coding tools, as on a key: the terminal, run as a subprocess (`drivers/openhands/agent.py:148`), the file editor and the task tracker, beside `finish`, `think`, ours and the environment's. Project skills stay off (`drivers/openhands/agent.py:165`) and its condenser sends the compaction headers, as sealed | The toolchain's Python with the `openhands` extra, as the worker is the runtime's own interpreter (`drivers/openhands/__init__.py:14`). `bash` on `PATH` and a pseudoterminal, which its terminal opens (`openhands-tools@1.59.0:openhands/tools/terminal/terminal/subprocess_terminal.py`). No tmux: the folder its driver gives tmux (`drivers/openhands/__init__.py:42-46`) is for the terminals of its own agents, which a gateway refuses (`drivers/openhands/worker.py:116-117`) |
| pi | The sealed argv without `--no-builtin-tools`, so pi's default tools, `read`, `bash`, `edit` and `write` (`@earendil-works/pi-coding-agent@1.5.0:dist/core/settings-manager.js:35`), beside ours and the environment's, with its own agent directory, no context files, skills, templates, themes or project files, and `--offline` | Node and pi's `node_modules`, which `DriverInfo.installed` names (`drivers/pi.py:170-175`), so a toolchain must hold them. A shell: pi runs `/bin/bash`, else `bash` on `PATH` as `which` finds it, else `sh` (`dist/utils/shell.js:54-67`, `111-119`). `rg` and `fd` only for `grep` and `find`, which pi leaves off by default and, offline, never downloads (`dist/main.js:455-457`, `dist/utils/tools-manager.js:296-299`) |
| The scripted harness, and the conformance wire program that serves it | Its `shell`, shown in each request, asked about before each call and run in `spec.cwd` once allowed | Nothing |
| A wire program | Its own, if it declares `in_environment` | What it says |
| `claude`, `codex`, `exec`, `acp`, `opencode` | Refused, as every gateway is: none has a sealed launch | |

OpenHands' launch needs only what a toolchain of the SDK and the image's `bash` give, so it comes first; pi's needs Node
in the toolchain too.

**The scripted harness** shows no tool of its own today. On a key it asks about any name a scripted model calls that is
no server's, and runs `shell` once allowed; on a gateway such a name is no tool (`testing/scripted.py:425-445`). On a
launch in the environment it shows `shell`, with a schema of one `command`, in each request beside ours and the
environment's, so the check of section 6 finds it there. It asks before each call and runs it as on a key, reports it as
pi and OpenHands report their own tools (section 3), and answers a name it does not show with "there is no tool", as on
a sealed launch. It looks a call up among its servers first (`testing/scripted.py:428-430`), so a tool of ours named
`shell` would take every call of that name: on this launch it refuses one at start. On a key it stays as it is, as a
scripted model calls `shell` there unshown and nothing on a key needs it shown.

Each tool of a harness's own that asks goes to the runtime, as on any launch: OpenHands asks for every action but a call
of an MCP server's, ours or the environment's, or a lone `finish` or `think` (`drivers/openhands/agent.py:44-54`;
`openhands-sdk@1.59.0:openhands/sdk/agent/agent.py`); pi's driver for every tool but ours, the environment's and those
that only read (`drivers/pi_extension.js:45-50`), so for `bash`, `edit` and `write`; and the scripted harness for its
`shell`. A trainable session answers by its policy, `allow` or `deny`, as nobody answers `ask` in a rollout
(`team.py:527-528`), and the record keeps each ask, masked, up to 64 KiB, with how much it cut
(`primitives/approvals.py:14`, `113-116`), and its verdict.

### 3. What the session records of the harness's own tools

Only what the harness reports. Its own tools reach neither our tool server nor the environment's, so the runtime
observes none of them, and the record holds what the harness says of each call (architecture section 9):

- **Its items.** pi and OpenHands report each call of a tool of their own as an `item.recorded`: a `started` item with
  the harness's own id for the call and its arguments as the model gave them, then a `completed` one whose outcome is
  `completed`, `failed` or, on OpenHands, `rejected`, with its result as the harness gave it (`drivers/pi.py:616-636`;
  `drivers/openhands/worker.py:448-454`, `476-516`). The scripted harness reports its `shell` today only as the item
  that answers its approval (`testing/scripted.py:334-341`); on a launch in the environment it reports it as they do,
  under the id the model gave the call.
- **`call_id`**, the model call that made it, only where the harness names that call: pi by the tool call in the message
  whose end it reports (`drivers/pi.py:600-601`, `616-621`), OpenHands by the response its action came from
  (`drivers/openhands/worker.py:476-501`), and the scripted harness by the reply that called it
  (`testing/scripted.py:412-413`). Where the harness names none it is None, and nothing joins the two by order or time
  ([architecture section 11](../architecture.md#11-provenance)).
- **Its approval**, for each call that asked: the ask, masked, up to 64 KiB, with how much it cut, and the policy's
  verdict, which the item's outcome answers.

**Which tool an item is of.** An item names no tool. Each of these drivers starts a tool item's gist with the name the
model called (`drivers/pi.py:619`, `drivers/openhands/worker.py:491`, `testing/scripted.py:387`), which section 5 gives
for each harness, and the start says the launch kept the harness's own tools (section 4). On pi and the scripted
harness, a call of ours is also joined to the op it made, by the anchor the harness sends
(`drivers/pi_extension.js:56`; `testing/scripted.py:65`, `391`; `primitives/provenance.py:669-671`). OpenHands sends no
anchor ([the compatibility reference](../reference/compatibility.md#driver-status)), so the shim gives each call of ours
an id of its own, which joins no item (`tools/shim.py:46-47`): there ours, the environment's and its own are told apart
only by the name at the start of an item's gist. An item is its harness's report by construction
(`primitives/lifecycle.py:765-797`), so what a harness's own tools did is known only as reported.

What the record cannot know stays unknown, and no gap is added for it, as the standing ones already say it:

- **What they read.** Every surface stands for every agent, whatever its harness, as no check proves one yet
  (`primitives/provenance.py:53-54`, `597-600`), so exposure answers `Unknown` of whatever its own tools read, never
  `NotSeen`.
- **What they changed.** Where the agent's workspace is a git work tree, the runtime's own look records it after each
  turn ([architecture section 13](../architecture.md#13-workspaces)). Elsewhere the session observes no repository, and
  an ask for a diff says so.
- **A call the model's code makes.** A command can call a model on any agent's bearer, which it can read. No harness
  reported that call, so the record holds no id for it, and it does not train, in a session whose journal and harness
  pipes no command wrote. A command can also write the journal, or have the call recorded as that agent's own, under
  the id the gateway gave it, by writing a report of it into that agent's harness's pipes, and nothing here detects
  either (section 7). What the call returned reaches the agent that ran the command as a tool's output.

### 4. The start records the launch

The profile an agent's start records as `verified` gains the word, so every `agent.started` and `agent.resumed` says
whether its harness kept its own tools:

```python
class Profile(Model):
    ...
    login: Login | None = None
    in_environment: bool = False  # its gateway said its session runs in the environment, so it kept its own tools
```

The host takes it from the agent's gateway, as it takes `login` (`runtime/host.py:425`, `1076-1083`), and `levels`
reads it (section 6). The start's `declared` holds the driver's `in_environment` too. No event is added.

### 5. Ours and the environment's beside the harness's own

Our tools and the environment's stay as a sealed launch has them, and each harness names them apart from its own:

| Harness | Its own | Ours | The environment's |
|---|---|---|---|
| OpenHands | `terminal`, `file_editor`, `task_tracker`, `finish`, `think` | Bare, as `task_claim` or `wait`, through the stdio shim ([RFC 0029](0029-a-harness-names-our-tools-as-it-shows-them.md)) | `environment_<tool>`, from a client of their own (`drivers/openhands/agent.py:185-205`) |
| pi | `read`, `bash`, `edit`, `write` | `mcp__ph__<tool>` | `mcp__environment__<tool>` (`drivers/pi.py:201-210`) |
| The scripted harness | `shell` | By their own names, as `task_claim` | `mcp__environment__<tool>` (`testing/scripted.py:343-350`) |

pi shows a server's tools under the server's name, so no name of ours or the environment's can be one of its own. The
environment's tools are named by their server on every harness, so none can be a harness's own. On OpenHands and the
scripted harness ours go by their own names, and none of the SDK's ops is named as a tool of either's own. An
extension's op that was would make two tools of one name: OpenHands refuses that at launch
(`openhands-sdk@1.59.0:openhands/sdk/agent/base.py`), as it refused the environment's `finish` before the environment's
tools were named by their server (RFC 0053), and the scripted harness refuses a tool of ours named `shell` at start
(section 2). So a collision fails its launch, loudly. The preamble teaches our tools by their exact names, as now, and
the harness's own prompt teaches its own.

### 6. What conformance checks, and what `trainable` stands on

One check is added, in the one result kept for the driver, which runs on FakeModel acting as a gateway that says its
session runs in the environment:

- **`own_tools_in_first_request_in_the_environment`**: the first request goes under the gateway's bearer, holds none of
  the instructions a project's `AGENTS.md` or `CLAUDE.md` gives, and shows the harness's own shell, by the name
  `check_driver`'s `shell` gives it, beside ours and each of the environment's tools named by its server. It skips,
  saying why, for a driver that declares no `in_environment`, or with no `shell` given.

It proves the launch keeps the harness's own shell, and keeps the project's instructions out, as the sealed check proves
of a sealed launch. That the shell runs, in the agent's workspace, is what the shell checks under `operational` prove of
the same tool on a launch on a key (`runs_in_its_workspace`, `stop_ends_a_running_tool` and the approval checks). What
else the launch keeps and keeps out is how its driver builds it, as for a sealed launch, which its slow tests read and
no check proves.

`trainable` stands on it two ways. At a launch in the environment it must have passed, beside the five checks
`trainable` stands on now. For any launch of a driver that declares `in_environment`, it must not have failed, as a
capability a check shows false leaves a level unmet. So `check(team, trainable=True)`, before any harness launches,
refuses a driver whose launch in the environment failed its check, and the levels each start records hold the launch
that ran to its own proof.

Each promise has a test named for it:

| Promise | Test |
|---|---|
| A sealed launch keeps the harness's own tools only on a gateway in the environment, on each driver that has one | `tests/unit/drivers/test_sealed.py::test_a_sealed_launch_keeps_the_harness_s_own_tools_only_on_a_gateway_in_the_environment` |
| Nothing but a gateway keeps a harness's own tools on a sealed launch | `tests/unit/runtime/test_authority.py::test_only_a_gateway_keeps_a_harness_s_own_tools_on_a_sealed_launch` |
| A session's gateways say one place, and an admission whose gateway says another is refused before its harness launches | `tests/unit/runtime/test_authority.py::test_an_admission_whose_gateway_says_another_place_than_the_first_is_refused` |
| A gateway in the environment goes to no driver that does not declare a launch there, which is refused before its harness launches | `tests/unit/runtime/test_authority.py::test_a_driver_with_no_launch_in_the_environment_refuses_a_gateway_in_it` |
| A wire frame names `in_environment` only where it is true | `tests/unit/drivers/test_wire.py::test_a_wire_frame_names_a_gateway_in_the_environment_only_where_it_is_one` |
| The start records the launch | `tests/unit/runtime/test_host.py::test_a_launch_in_the_environment_is_recorded_on_its_start` |
| Every report is masked of every credential the runtime has given a harness, an ended agent's among them, whichever agent's harness said it | `tests/unit/runtime/test_host.py::test_every_report_is_masked_of_every_credential_the_runtime_has_given_a_harness` |
| A value too short to be a credential is masked in the reports of the agent it was handed to alone | `tests/unit/runtime/test_host.py::test_a_value_too_short_to_be_a_credential_is_masked_in_its_own_agent_s_reports_alone` |
| `trainable` there stands on the new check, and a failed one leaves every trainable launch of its driver unmet | `tests/unit/drivers/test_levels.py::test_trainable_in_the_environment_stands_on_its_own_tools_check` and `test_a_failed_launch_in_the_environment_leaves_trainable_unmet_everywhere` |
| The check fails a launch in the environment that shows no shell of its own | `tests/unit/drivers/test_check_driver.py::test_a_launch_in_the_environment_that_shows_no_shell_of_its_own_fails_its_check` |
| In the environment the scripted harness shows its `shell`, reports each call as pi and OpenHands do, and refuses a tool of ours of that name | `tests/unit/drivers/test_scripted.py::test_in_the_environment_the_scripted_harness_shows_and_reports_its_shell` and `test_in_the_environment_a_tool_of_ours_named_shell_is_refused_at_start` |
| A tool of the harness's own is recorded as its harness reported it, joined to no call it did not name | `tests/unit/runtime/test_host.py::test_a_harness_s_own_tool_is_recorded_as_reported_and_joined_to_no_call_it_did_not_name` |
| A call a command makes on a bearer it read has no id in the record, in a session whose journal and harness pipes no command wrote | `tests/unit/runtime/test_training.py::test_a_call_a_command_makes_on_a_bearer_it_read_has_no_id_in_the_record` |
| The whole contract, in the environment | `tests/integration/test_contract.py::test_a_session_in_the_environment_runs_as_a_training_authority_drives_it`, on the scripted harness in the fast pass and on OpenHands and pi in the slow |

### 7. Who can read what in the sandbox

The runtime, its journal, every harness and every command a model runs share the sandbox, and, as the SDK launches each
harness as itself, one user. That is architecture section 15's agent with a shell at the same user.
[The security guide](../security.md#what-it-does-not-protect) says such an agent can read the session folder, the
owner's token and another agent's token in that agent's environment. A bearer in the same environment is read the same
way, and the journal is a file of that same user's, which such a command can write. It can write into the pipes between
the runtime and each harness too, as it can open either end at `/proc/<pid>/fd` of the process that holds it (proc(5)),
and so report as that harness or steer it. The OpenHands worker takes its key, the bearer and our token out of its
environment once read (`drivers/openhands/worker.py:180-184`), which keeps them out of what its terminal is handed, and
not out of `/proc/<pid>/environ`, which holds a process's environment as it began (proc(5)). pi's `bash` hands each
command pi's environment, with five `PI_*` variables set from its session
(`@earendil-works/pi-coding-agent@1.5.0:dist/core/tools/bash.js:135-161`), and a sealed launch puts the bearer and our
token there (`drivers/env.py:58-63`). So, on a launch in the environment:

- **Assurance is `cooperative`**, as every start that is not isolated records now.
- **The bearer.** What the SDK promises of it, that only the harness's environment holds it and no file of the session's
  or command line does ([architecture section 14](../architecture.md#14-training)), holds of what the SDK and the
  harness do on their own, and not of a command the model runs, which can write it wherever its user can write, the
  session's folder among them, or print it for its harness's transcript to keep (below). A bearer that dies with its
  rollout bounds the rest, and that is the training system's.
- **Every credential is masked in every report.** Today the host masks what an agent's harness says of that agent's own
  credentials alone (`runtime/host.py:438`, `978`; `drivers/env.py:106-109`), so another agent's bearer that a command
  printed would reach the journal in the clear. The host masks every credential the runtime has given a harness, in
  every report and in each form it masks a secret in (`config.py:76-88`): each agent's bearer or auth profile's values,
  and its token, an ended agent's among them, as a bearer can work until its rollout ends. So a bearer that a command
  prints reaches no report, and so not the journal. This holds on every launch, as a shell on a key can read another
  agent's token too. A command that recodes a credential before it prints it gets it past, as on any session whose
  agents have a shell. A value shorter than eight characters, as an auth profile's `PI_OFFLINE` may be, is no
  provider's key, and is found in ordinary words and in the ids reports name, where its mask would lose the agent
  whose report it is, so it is masked in the reports of the agent it was handed to alone, as today.
- **The export.** A harness's own transcript keeps a command's output as the harness wrote it
  ([the security guide](../security.md#redaction)), and stays in its agent's folder as the record, which the export
  holds ([RFC 0075](0075-an-ended-agent-s-folder-keeps-its-record-and-no-credential.md)). OpenHands keeps each event of
  its conversation there (`drivers/openhands/agent.py:172`;
  `openhands-sdk@1.59.0:openhands/sdk/conversation/event_store.py`), and pi its sessions, in the agent directory a
  sealed launch gives it (`drivers/pi.py:325-328`; `@earendil-works/pi-coding-agent@1.5.0:dist/config.js:546-547`). So
  the export of a session in the environment can hold a bearer a command printed, and the promise of
  [architecture section 15](../architecture.md#15-security), "No model-access credential reaches a log, event,
  artifact, export or resolved config", holds there only of the journal. The bearer dying with its rollout bounds that,
  and a training system that keeps only the journal and its bodies keeps it out.
- **What trains.** A call a command makes on any agent's bearer is no call a harness reported, so the record holds no
  id for it, and it does not train, in a session whose journal and harness pipes no command wrote. But a command can
  write the journal, and, without writing it, can have such a call recorded as that agent's own, under the id the
  gateway gave it, by writing a report of it into that agent's harness's pipes. Nothing here detects either, nor can a
  check against the gateway's records for that agent's key, which did serve the call. A training system that trains on
  the record of a session in its sandbox trusts what the agents' commands left of it, so a session there is for agents
  of one policy only: with two, one policy's commands could write what the other trains on. So architecture section
  14's "a call no harness reported has no id to join, so it never trains", and the training guide's sentence like it,
  hold only in a session whose journal and harness pipes no command wrote, and say so; they and the security guide say
  that a session in the environment is for agents of one policy only. A call of our tools on another agent's token is
  that agent's in the record, as law 6 has it for any credential.

### 8. What it does not do

**One sandbox per agent.** Every agent of a session shares the one sandbox the session runs in, its files and its
processes, as the SDK runs each harness as a process on its own machine
([RFC 0031](0031-a-workspace-is-a-place-git-already-knows.md): "The core uses git and the filesystem alone"). A sandbox
per agent needs a place an agent runs apart from the runtime's: a launch through the environment's own exec, the
runtime's process tracking and git across that boundary, and a route from it to our tool server, which is on loopback
([RFC 0034](0034-isolation-is-an-extension-s-and-the-runtime-s-git-runs-inside-it.md) rejected a network namespace for
an agent: "It cuts the tool plane, which is on loopback"). That changes the driver contract, and nobody has asked for it
yet.

**A user for each harness.** Running each harness as a user of its own would keep each agent's credentials from the
others' commands, and would change how a harness launches, how the runtime stops and reaps processes of other users,
who owns each agent's folder, and what assurance a start records. It needs a sandbox user that can switch users, which
Docker's root can, Singularity's only under `fakeroot`, and Enroot's cannot, as Platoon's sandbox providers say
(Evidence). Open question 2 asks whether to.

**A task's own MCP servers.** A launch in the environment admits no MCP server but ours and the environment's, so a
task's own servers, `stdio` ones among them, reach no agent. Handing a launch more would need a field through which an
authority gives them, with a check of its own, in an RFC of its own.

## The hard parts

- **The SDK cannot see where it runs.** The rule rests on a word the SDK cannot check. A gateway that says it of a
  session on a training system's own host gives that host's harnesses their own tools. The record shows it on every
  start, so a false word is found after the fact, never prevented.
- **One user.** A command the model runs can read every credential in the sandbox, write the journal and write into any
  harness's pipes, as on any session whose agents have a shell, so it can have a call it made on any agent's bearer
  recorded as that agent's own, and nothing here detects it. The host masks every credential the runtime has given a
  harness in what the journal keeps, though not in a harness's own transcript, which the export holds. A training
  system that trains on such a record trusts what the agents' commands left of it, so a session there is for agents of
  one policy only.
- **The image holds the shell.** A toolchain holds the SDK and the harness, and the task's image holds the shell they
  run: OpenHands' terminal cannot start where the image has no `bash`, so its agent's start fails, and pi falls back to
  `sh` (section 2).

## Alternatives

| Alternative | Why not |
|---|---|
| Keep every gateway's launch sealed, and have the environment serve the tools a harness needs through its server | The harness would train on tools other than its own, and run otherwise in a team than alone on the same task |
| `Session.start(..., in_environment=True)` | Two places for one word: the driver still needs it at launch, through its spec or its gateway. A word on the session would let `check` refuse a role whose driver has no launch in the environment before any cost, but whoever starts a session could give it, where only an authority gives a gateway, and a training system can refuse such a role before any cost from what its driver declares |
| A field on `Admission` | It never reaches a driver: `AgentSpec` would need one too, for what only a gateway's launch reads |
| A field named for what it does, as `own_tools` | It reads as a switch for the tools, where what decides is where the session runs: named for that, a wrong value is a false statement about the world, which the record keeps |
| Read it from the principal | A principal is a name and not a claim, and a training system's is the same on its host and in its sandbox |
| A setting of the team file or a role | Project config, and a person's: it would keep a harness's own tools on any machine a session runs on |
| Tell an environment's sandbox from inside | Nothing tells it from any other container or machine, so it would be a guess |
| Prove the session shares the environment's machine, as by a file one of the environment's tools writes and the runtime reads back | An environment's tools are its own, and no tool the SDK could count on to write a file is among every environment's |
| Every sealed driver has a launch in the environment, with no capability | A sealed wire program built on an earlier SDK refuses the frame, so its check would fail and leave every trainable launch of it unmet; and drivers gain the launch one at a time |
| A tool's name on `Item` | One more field every driver fills and every `item.recorded` carries, for the name the gist of every driver with this launch already starts with; a reader still tells ours from the environment's and the harness's own by the names each harness gives them |
| Keep the bearer and our token out of what pi's `bash` hands a command | pi needs the bearer in its environment for its whole life, as our extension reads it there at each compaction (`drivers/pi_extension.js:82`), and its `bash` hands a command that environment (section 7), so it would take a `bash` of ours in place of pi's. The OpenHands worker drops them once read, which keeps them only from what its terminal is handed: at one user `/proc/<pid>/environ` holds them still in either |
| Mask only each agent's own credentials in its reports, as now | Another agent's bearer that a command prints would reach the journal in the clear |
| `isolated` workspaces in the sandbox | An isolated workspace is a snapshot of its own, not the task's tree, which a verifier reads, and it rests on user namespaces a container can withhold |
| One sandbox per agent | Section 8: a place an agent runs apart from the runtime's, which changes the driver contract, and nobody has asked for |
| A user for each harness | Section 8: a sandbox user that can switch users, which not every sandbox has, and a launch, process control and an assurance of its own |
| Doing nothing | Agents act on the task only through the environment's server, and a harness runs one way alone and another in a team |

## Consequences

- A training system that runs a session in its environment's sandbox gets agents that use their harness's own tools on
  the task, beside ours and the environment's, trainable as a sealed launch is.
- A gateway that does not say it launches sealed as before, and nothing a person runs changes.
- `Gateway`, `Capabilities` and `Profile` each gain `in_environment`, which `tests/public_api.txt` lists through
  `Gateway`'s signature, so the Python reference is made again, and conformance gains a check. The team file, the
  command line and the journal's events stay as they are; a start's `verified` and `declared` carry one more field.
- A session's gateways say one place, and an admission whose gateway says another is refused before its harness
  launches.
- Each tool of a harness's own that asks costs an approval through the session's policy, whose ask the journal keeps,
  masked, up to 64 KiB, with how much it cut.
- What a harness's own tools read is a standing gap, and a call a command makes is unknown, so exposure there answers
  `Unknown`.
- Every report is masked of every credential the runtime has given a harness, an ended agent's among them, on every
  launch, and a value shorter than eight characters only in its own agent's, and the security guide's Redaction
  section says so. A harness's own transcript is not, so the export of a session in the environment can hold a bearer
  a command printed, and architecture section 15, which says no model-access credential reaches an export, says that
  there it holds only of the journal.
- A session in the environment is a session whose agents have a shell at its user: assurance `cooperative`, and a
  record that commands the model ran could write, in the journal or through any harness's pipes, so it is for agents of
  one policy only, as architecture section 14, the training guide and the security guide say. Section 14 and the
  training guide say too that a call no harness reported has no id only in a session whose journal and harness pipes no
  command wrote.
- The scripted harness shows its `shell` on a launch in the environment and reports it as pi and OpenHands report their
  own tools; on a key it stays as it is.
- A wire frame names `in_environment` only where it is true, and every other field as now, so a wire program built on
  an earlier SDK, or one in another language, takes every frame it took before, unchanged. A runtime of an earlier SDK
  refuses the description of a program built on this one, as for any field added since.
- Unknown: how training on a harness's own tools compares with training on the environment's tools alone, which nothing
  has measured.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 the word | `Gateway.in_environment`, `Capabilities.in_environment` and `Profile.in_environment`; one place for a session; the host's refusal; the start's record; a wire frame that names `in_environment` only where it is true; every credential the runtime has given a harness masked in every report; architecture sections 9, 14 and 15, the training guide and the security guide's Redaction section | `test_only_a_gateway_keeps_a_harness_s_own_tools_on_a_sealed_launch`, `test_an_admission_whose_gateway_says_another_place_than_the_first_is_refused`, `test_a_driver_with_no_launch_in_the_environment_refuses_a_gateway_in_it`, `test_a_wire_frame_names_a_gateway_in_the_environment_only_where_it_is_one`, `test_a_launch_in_the_environment_is_recorded_on_its_start`, `test_every_report_is_masked_of_every_credential_the_runtime_has_given_a_harness` | |
| M2 the check | `own_tools_in_first_request_in_the_environment`, and what `trainable` stands on | `test_trainable_in_the_environment_stands_on_its_own_tools_check`, `test_a_failed_launch_in_the_environment_leaves_trainable_unmet_everywhere`, `test_a_launch_in_the_environment_that_shows_no_shell_of_its_own_fails_its_check` | |
| M3 the scripted harness | Its `shell` on a gateway in the environment, shown, asked about and reported as section 2 says; a tool of ours named `shell` refused there; the conformance wire program | `test_a_sealed_launch_keeps_the_harness_s_own_tools_only_on_a_gateway_in_the_environment` on the scripted harness, `test_in_the_environment_the_scripted_harness_shows_and_reports_its_shell`, `test_in_the_environment_a_tool_of_ours_named_shell_is_refused_at_start`, `test_a_harness_s_own_tool_is_recorded_as_reported_and_joined_to_no_call_it_did_not_name`, `test_a_call_a_command_makes_on_a_bearer_it_read_has_no_id_in_the_record`, and the fast pass of the contract test | |
| M4 OpenHands | Its coding tools on a gateway in the environment | The slow `tests/integration/test_openhands.py`, its check passing the new one, and the contract test on OpenHands | |
| M5 pi | Its default tools on a gateway in the environment | The slow `tests/integration/test_pi.py`, its check passing the new one, and the contract test on pi | |

## Open questions

1. **The project's instructions in the environment.** Open. Today: kept out of the prompt, as on a sealed launch, so an
   `AGENTS.md` in the task's tree reaches no agent's prompt, though an agent can read it with its own tools. A training
   system that wants them gives them in the task. The maintainers decide before M3.
2. **A user for each harness, and what `trainable` asks of the user an agent runs as.** Open. Today: nothing more than
   now. Every process in the sandbox runs as one user, the start says `cooperative`, every report is masked of every
   credential the runtime has given a harness, and a training system decides what trains. A user for each harness
   (section 8) would keep each agent's credentials from the others' commands where the sandbox's user can switch users,
   and needs an RFC of its own. The maintainers decide before M2, which sets what `trainable` stands on.
3. **pi's bearer in what its `bash` hands a command.** Open. Today: left there, as pi needs it in its environment
   (Alternatives), and masked in every report. The maintainers decide before M5.

## Evidence

- Code at `e73a221`, as cited above: the sealed launches of pi (`drivers/pi.py:102-111`, `330-337`), OpenHands
  (`drivers/openhands/agent.py:147-153`) and the scripted harness (`testing/scripted.py:155-157`, `425-445`); the
  host's refusals of a gateway and of a bearer another agent holds (`runtime/host.py:310-316`, `420-423`); its masking
  (`runtime/host.py:438`, `978`); the wire's frames (`drivers/wire.py:54-55`, `231-233`); what `trainable` stands on
  (`drivers/levels.py:63-72`); and the sealed checks (`testing/conformance.py:690-718`).
- [`tests/unit/drivers/test_sealed.py`](../../tests/unit/drivers/test_sealed.py),
  `test_a_sealed_scripted_harness_runs_no_tool_of_its_own` and `test_a_harness_with_no_sealed_launch_refuses_a_gateway`:
  what a sealed launch is today, which a gateway that does not say it keeps.
- [`tests/integration/test_contract.py`](../../tests/integration/test_contract.py),
  `test_an_isolated_sealed_agent_reaches_its_gateway_on_loopback`: a result written into a fresh root before the session
  starts, and the bearer in the harness's environment alone, which section 7 says no longer holds against a command the
  model runs.
- `openhands-sdk` and `openhands-tools` 1.59.0, which the `openhands` extra installs, read in the repository's own
  environment: `openhands-tools@1.59.0:openhands/tools/terminal/terminal/subprocess_terminal.py`, whose terminal finds
  `bash` on `PATH` with `shutil.which`, fails without one, and opens a pseudoterminal;
  `openhands-sdk@1.59.0:openhands/sdk/agent/agent.py`, which asks nothing of a lone `finish` or `think`;
  `openhands/sdk/agent/base.py`, which refuses two tools of one name; `openhands/sdk/conversation/event_store.py`, which
  keeps each event of a conversation, a command's output among them, as a file of its own where it persists; and
  `openhands/sdk/subagent/registry.py`, which gives each tool of a built-in agent no parameters, so its terminal is of
  no set kind, which `openhands-tools@1.59.0:openhands/tools/terminal/terminal/factory.py` makes tmux where tmux is
  installed.
- pi 1.5.0's own modules, read in its published package and not run, whose `pi` command runs a bundle of the same
  code, `dist/bundle/`: `@earendil-works/pi-coding-agent@1.5.0:dist/core/settings-manager.js:35`, whose default tools
  are `read`, `bash`, `edit` and `write`; `dist/utils/shell.js:54-67` and `111-119`, which runs `/bin/bash`, else `bash`
  on `PATH` as `which` finds it, else `sh`; `dist/core/tools/bash.js:135-161`, which by default hands a command pi's
  environment with five `PI_*` variables set from its session; `dist/config.js:546-547`, which keeps its sessions in
  its agent directory; and `dist/main.js:455-457` with `dist/utils/tools-manager.js:296-299`, by which `--offline`
  downloads no `rg` or `fd`, which, in the RPC mode the driver runs, only its `grep` and `find` fetch
  (`dist/core/tools/grep.js:52`, `dist/core/tools/find.js:119`).
- Platoon's own code at `411cfe55ea45`: `platoon@411cfe55ea45:platoon/harness/builtin/specs/openhands.toml` runs one
  OpenHands agent from a read-only toolchain inside the task sandbox, a toolchain whose lock,
  `platoon/harness/builtin/specs/openhands-1.54.0.txt`, holds OpenHands' SDK and tools and their closure, and not this
  SDK; and `platoon@411cfe55ea45:platoon/harness/builtin/platoon_harness/bridge.py` starts a team's session in the
  rollout worker, on the host. Its sandbox providers say who a command runs as: on Docker the image's user, else root,
  or any user of the image on request (`platoon/sandbox/docker.py`); on Singularity your own user, or under `fakeroot` a
  root that can switch users (`platoon/sandbox/singularity.py`); and on Enroot a root mapped to your own uid, which
  cannot switch users (`platoon/sandbox/enroot.py`).
- A probe the repository does not hold ran a session of platoon-harness 0.1.0 inside a task's sandbox under
  SingularityCE 4.4.1, from a toolchain bound read-only, on the host's network and on none: every launch sealed, as
  0.1.0 has no launch in the environment, and every command run as the user's own uid, with no capability. There
  OpenHands' terminal, made by its own factory from that toolchain in `python:3.12-slim`, which holds no `tmux`, ran
  `bash` as a subprocess on a pseudoterminal and kept its state from one command to the next. A second probe, which the
  repository does not hold either, ran a session of this SDK there, from that toolchain with this SDK in place of
  0.1.0, on a gateway FakeModel acted as, saying its session runs in the environment and naming the image's `PATH`:
  OpenHands' terminal ran its command on the agent's `bin` and that `PATH`, which found the image's `python3`. A
  harness's own tools have run on a gateway only on FakeModel acting as one in the environment: OpenHands' there, and
  pi's and OpenHands' in the slow passes of `tests/unit/drivers/test_sealed.py` and
  `tests/integration/test_contract.py`.
