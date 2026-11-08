# RFC 0072: ACP agents are driven by a first-party extension that names its own check

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`rpc.py`](../../packages/sdk/src/platoon_harness/rpc.py), [`drivers/__init__.py`](../../packages/sdk/src/platoon_harness/drivers/__init__.py), [`drivers/levels.py`](../../packages/sdk/src/platoon_harness/drivers/levels.py), [`testing/harnesses.py`](../../packages/sdk/src/platoon_harness/testing/harnesses.py), the command line's [`machine.py`](../../packages/cli/src/platoon_harness_cli/machine.py), [architecture section 9](../architecture.md#9-drivers) and [section 17](../architecture.md#17-extensions-and-configuration), [RFC 0008](0008-driver-contract-and-wire.md), [RFC 0024](0024-a-harness-s-own-agents-are-off.md), [RFC 0030](0030-openhands-is-an-extra-of-the-sdk.md), [RFC 0044](0044-a-level-is-earned-on-the-machine-that-runs-it.md) and [RFC 0066](0066-an-approval-carries-the-whole-of-what-it-asks.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository, and the owner's questions on where first-party extensions live and what ACP is spoken over, which are open |
| Implementation | `build: Add the platoon-harness-acp distribution under extensions`, `feat: Drive ACP agents on protocol 1 over the SDK's own JSON-RPC peer`, `feat: Let an installed driver name the check doctor runs for it` and `test: Run check_driver on a scripted ACP agent and on OpenCode against FakeModel` |

## Summary

`platoon-harness-acp`, a distribution of its own under `extensions/acp` with its own version and tag, is the first first-party
extension. Its `AcpDriver(command)` drives an agent that speaks the Agent Client Protocol on stdio, at protocol 1 alone, over the
SDK's own `rpc.Peer`, adding no dependency. A turn is one `session/prompt`, which is the only boundary it declares: a delivery for
any other is refused until a recorded fixture shows an agent taking one. An update it does not map keeps its raw frame with a gap. A
permission request is an approval whose whole ask is the tool call it names, as the agent last gave it. It never declares a sealed
launch or an id per model call, so no agent on it is trainable. Stable ACP cannot turn an agent's own agents off, so a role on it
must allow them, as `native_children_off`, a new capability every other driver declares, says. Its one named driver is
`opencode`, on `opencode acp`, and a driver gains a way to name a check of its own, `DriverInfo.check`, which
`platoon-harness doctor --check` runs and keeps as it does the SDK's, pinned to the driver's class and now also to the release
of each distribution outside the SDK that the class stands on.

## Motivation

The SDK drives Claude Code, Codex, pi and OpenHands, each by a protocol of its own. Many agents speak ACP instead, OpenCode among
them, and STATUS has planned a generic ACP driver since milestone 0. Three things stand in its way:

- **Where it lives.** A driver the SDK ships is checked by `doctor` and pinned to the SDK's version, and every other is a user's,
  checked by hand. A driver the project ships outside the SDK has no place: RFC 0030 folded the one distribution apart there was
  into an extra, because an unpublished distribution with pins of its own needed a second environment.
- **What it speaks over.** The ACP Python SDK drops every update it cannot parse before a client sees it
  ([acp-mcp.md](../research/acp-mcp.md#2-acp-python-sdk)), which is the frame a gap must keep, and its 1.0 release candidates
  cannot share a lock with the `openhands` extra's pin of 0.12.1.
- **How it is checked.** `doctor --check` runs only the checks `levels.CHECKED` names, which are the SDK's
  ([`machine.py`](../../packages/cli/src/platoon_harness_cli/machine.py)), so a driver outside the SDK earns a level only from a
  result its user made and kept by hand.

## Proposal

### 1. A first-party extension is a distribution under `extensions/`

`extensions/acp` holds `platoon-harness-acp`: its own `pyproject.toml`, version, README and license, a member of the uv
workspace, locked with the SDK and the command line in the one `uv.lock`. It requires the SDK's own minor release and nothing else,
so it shares the dev environment and every test runs it, unlike the OpenHands distribution RFC 0030 folded away. It releases on a tag
of its own, `platoon-harness-acp-vX.Y.Z`, when the owner tags it; the release workflow builds and checks its wheel beside the SDK's
and loads its driver from it. It uses the SDK's public names alone, which an AST test holds, and neither the SDK nor the command line
imports it, which another holds.

### 2. Protocol 1 over `rpc.Peer`

```python
class AcpDriver:
    name = "acp"
    def __init__(self, command: Sequence[str]) -> None: ...
```

`start` launches `command` through `Process`, sends `initialize` asking for protocol 1, and stops the agent and refuses the start on
any other answer, as ACP has a client disconnect from a version it does not speak. It advertises `fs` and `terminal` as false, so the
agent keeps its own tools, and `session.compaction`, so a compaction is reported. Then `session/new` with the agent's workspace as
`cwd` and our tools as one HTTP MCP server under our bearer, or `session/resume` on a resume, which an agent that offers none
refuses. A role's instructions go as `systemPrompt` in `append` mode where the agent advertises it, sent again on a resume, and
otherwise before the text of the session's first prompt, said once. A model is set through the session's config option of category
`model`, and an agent that offers none refuses a start that names one, as it would run on a model nobody chose. `ready` names the
session, the version `agentInfo` says, and the model that option holds.

### 3. What it reports

| ACP | Report |
|---|---|
| `session/prompt` sent | `turn.started` |
| The first update after it that is not of the session's state, a permission request, or else its answer | `input.delivered`, at the turn boundary |
| `agent_message_chunk`, `agent_thought_chunk` | `delta`, then one `item` a message or thought when another kind of update or the turn's end follows |
| `tool_call`, `tool_call_update` | `item` tool `started`, then `completed` with the status it ended at and the approval that let it through |
| `plan` | `item` thought |
| `compaction_update` completed | `compacted` with what its summary says and `forgotten` unknown |
| `user_message_chunk`, `available_commands_update`, `session_info_update`, `usage_update`, `notice` | Nothing: they say nothing of what the agent did |
| `current_mode_update`, `config_option_update` | Nothing before the session is ready, or where it says the mode and options already said; otherwise `native` with its raw frame and the gap `unknown_update`, as `ready` named the model the record holds |
| Any other update, method or line | `native` with its raw frame and the gap `unknown_update`, as the peer took the line |
| The prompt's answer | `turn.ended`: `stopped` for `end_turn`, `interrupted` for `cancelled` after an interrupt, the stop reason otherwise, and where it gives none, that it gave none |

ACP gives no id of a model call and no spend per call: `usage_update` is the context's size and a running cost, and a prompt's
`usage` is unstable. So the driver reports no `model.call` and no `usage`, declares `call_ids` none and no `measures`, and the
runtime charges each turn its estimate, labelled so. It declares the agent's own agents `opaque`, as stable ACP neither shows nor
turns them off, and so declares no `native_children_off`, below.

### 4. A permission request is an approval whose whole ask is its tool call

`session/request_permission` names a tool call as a `ToolCallUpdate`, whose fields left out are those its last `tool_call` or
`tool_call_update` gave. The driver keeps each tool call as last updated, and the approval's body is that call as a person reads
it: a line for each of its title, its tool's name and its kind, and for each place it names, as `path:line`, then its raw input as
JSON, as a tool's input is in Claude Code's ask, then each entry of its content as it is, a diff as its path and new text, so a
command's quotes and a file's lines read as they will run. Its id and status are not part of the ask. Its gist is the title and the
start of the raw input. A call that gives none of these says nothing of what it would do, so its body is None, unknown, and its gist
says so.

The verdict is answered with the request's `allow_once` or `reject_once` option, as an `always` option would decide more than a
person was asked. Where the request offers none of the verdict's kind, the answer is `cancelled`, which runs nothing: a denial is
carried out so, and an allow is not, so `answer` fails, saying so, and the record holds that failure on the answer's effect. An
interrupt answers each request still waiting `cancelled`, as ACP requires, whatever options it offers, and so does a turn's end,
which makes them moot, as the agent asks nothing of a prompt it has answered.

### 5. Steering is refused until a fixture passes

ACP's version 1 says nothing of a second `session/prompt` during a turn, and OpenCode answered one with -32603. So `boundaries` is
`{"turn"}`, a delivery that comes during a turn waits for its end and is sent as the next prompt, an interrupt drops what waits, as
the runtime offers it again, and a delivery for any other boundary is refused, saying why. An agent's own way to steer, such as an
`_session/steering` extension, is declared only once a recorded fixture shows it landing.

### 6. Never trainable

The driver declares no sealed launch, refuses a gateway, and has no id per model call, so `levels` leaves `trainable` unmet for
every agent on it, whatever a check found. `operational` and `observable` are earned as any driver's are.

### 7. A role on ACP allows its agent's own agents

Every driver turns its harness's own agents off for a launch whose role does not allow them
([RFC 0024](0024-a-harness-s-own-agents-are-off.md)), and stable ACP has no way to. So `Capabilities` gains a declaration of it:

```python
class Capabilities(Model):
    ...
    native_children_off: bool = False  # it turns the harness's own agents off for a launch whose role does not allow them
```

`claude`, `codex` and the OpenHands worker declare it, as each does so and `native_children_off_by_default` proves it on each real
binary. The ACP driver does not. A role on a harness with agents of its own that its driver cannot turn off must say
`allow_native_children = true`, and `team check` refuses it otherwise, as a role left at the default would say they are off while
they run. The role then says what runs, the record holds it, `team check` warns of what that gives up as it does any opt-in, and
`levels` counts its opaque agents against `trainable`. `check_driver` skips `native_children_off_by_default` for such a driver,
as a role on it never asks for them off.

### 8. A driver names its own check

```python
class DriverInfo(Model):
    ...
    check: str | None = None  # "module:function", an async (folder) -> Conformance, imported only to run it
```

`doctor --check` runs the SDK's checks as before, and for each other installed driver it finds whose `describe` names a check, that
check, in the same folder under the root, keeping what it found the same way. `check_harness(name, folder)` runs either. A named
check that returns a result of another class than the driver's, or of another harness's name, is refused, as it would speak for a
driver it did not check, and would replace what was kept of that harness. A check that breaks, or returns no `Conformance`, is
refused too, saying why, as another distribution ships it, and `doctor --check` goes on past it.

A result is pinned to the class that implements the driver, and now also to the release, the distribution and its version, of
each distribution outside the SDK whose driver entry points name the package of that class or of a class it is built on, so that
an upgrade of an extension reads `unverified` until checked again, as an upgrade of the SDK does
([RFC 0044](0044-a-level-is-earned-on-the-machine-that-runs-it.md)). A subclass of `AcpDriver` in a distribution of its own is
pinned to that distribution and to `platoon-harness-acp`, which does its driving. A release is read from entry points, so a base
class from a distribution that names no driver of its own leaves that distribution out of the pin.

`opencode` is `AcpDriver` on `opencode acp`, inheriting the shell's proxy variables, refusing a start with no model, as OpenCode then
sends prompts to a hosted model nobody chose, and naming `platoon_harness_acp.check:opencode`, which runs `check_driver` on it
against `FakeModel` in a home of the check's own, through a provider given in `OPENCODE_CONFIG_CONTENT`.

## The hard parts

- **OpenCode runs, and fails 7 of its checks.** On OpenCode 2.2.6 against FakeModel, run by hand on 2026-11-08, its check passed 11 checks and failed 7: it reaches FakeModel past `initialize`, starts on its pinned model, which a role names as OpenCode does, `fake/fake-model`, takes delivered text, ends, resumes and stops its turns, and reports a malformed frame as a gap; it failed our tool in the first request, the shell checks, approvals and the interrupt, because OpenCode's first request is a title of the session that it asks of the model on the side, with no tools, and because it shows an MCP server that `session/new` gives it only through its `execute` tool, Code Mode, not as a tool of its own ([acp-mcp.md, section 6](../research/acp-mcp.md#6-opencode-past-initialize-2026-11-08)). Its check is
  written from the 2026-11-02 transcript and the 2.2.6 files, UNVERIFIED: the provider's shape, the names its model sees our tool and its shell by,
  and the values its model option takes, which may be `provider/model`, so that a start naming `fake-model` is refused. An ACP
  server reached the model behind Code Mode in that probe, so our tool may not be in the first request.
- **What a tool is called.** In that probe OpenCode showed a server its configuration named as `<server>_<tool>`, and one ACP
  gave it behind Code Mode, neither of which a value of `tool_names` says. The driver declares the default, `namespaced`, as for
  any ACP agent, so our words name its tools `mcp__<ns>__<tool>`, and its check calls our tool by that name, so that it fails
  where OpenCode's model knows our tool by another, UNVERIFIED until it runs. A value of `tool_names` for OpenCode's naming waits
  for a run that shows it.
- **A whole ask can be large.** A diff's text is part of the ask, so a body can pass 64 KiB; the host keeps its first 64 KiB and
  counts the rest in `cut`, and refuses one the journal will not hold, as RFC 0066 says.
- **Landing.** ACP never acknowledges a prompt before its answer, so an input is said to land at the first update that follows it,
  which a stale update of the session's could fake, or at the answer.

## Alternatives

| Alternative | Why not |
|---|---|
| The ACP Python SDK | It drops an update it cannot parse before the client sees it, so the gap would lose its frame, its 1.0 is still at release candidates, and it cannot share the lock with the `openhands` extra's 0.12.1 |
| The driver inside the SDK | The SDK would release with every change of a protocol still moving toward version 2, and a first-party extension shows the path any third party's driver takes |
| `harness = { command = [...], mode = "acp" }` in the team file | A change of the team file's schema with one agent to serve. A driver named for its command is the naming law's way, so a second agent gets a driver of its own until a team needs the generic one |
| Name a check by an entry point of its own group | A second registry for one fact about a driver, which `describe` already answers |
| Move the SDK's own checks onto `DriverInfo.check` | `levels`, a pure function, reads `CHECKED` to say what makes a result, so moving them is a change of its own |
| A role on ACP left at `allow_native_children = false`, with that labelled in the docs alone | The role and the record would say the agent's own agents are off while they run, which only a reader of the docs would know |
| The ACP driver refuses a start that leaves them off | `check_driver` starts every check at the default, so every check would fail, and the role still could not say what runs |
| A gap at start | No gap of the closed set says this: `native_child_unattributed` is of a child seen, and a child that may never start is none |
| `session/load` for a resume | It replays the whole session as updates the record already holds; `session/resume` replays nothing, and OpenCode offers it |
| A delivery during a turn sent as it comes | Undefined in version 1, and OpenCode refuses it |

## Consequences

- An ACP agent can run as a team's harness, with a level earned only by a check on its machine, and an agent of any other ACP
  harness needs only a subclass naming its command. `opencode`, the one so named, passes 11 of its checks on OpenCode 2.2.6 and fails 7.
- `doctor` lists `opencode` where the extension is installed, and `--check` checks it there, as it does the SDK's harnesses.
- A result kept for any driver outside the SDK made before this pinned no distribution, so it reads `unverified` until checked
  again.
- No agent on ACP is trainable, and none reports what a model call cost, so every turn is charged its estimate.
- An agent's own agents run unseen, and a role on an ACP harness must allow them, or `team check` refuses it. A third party's
  driver that declares agents of its own and not `native_children_off` meets the same refusal, until it declares it.
- The workspace gains a member, which reverses the commit that dropped the empty `extensions/*` member.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 the distribution | `extensions/acp` in the workspace, the release workflow | `uv build --all-packages`, and the boundary tests `test_the_sdk_never_imports_a_first_party_extension` and `test_the_acp_extension_uses_only_public_names` | |
| M2 the driver | `AcpDriver`, `opencode` | `tests/unit/drivers/test_acp.py`: `test_protocol_1_is_negotiated_and_anything_else_disconnects`, `test_an_unknown_update_keeps_its_raw_frame_and_a_gap`, `test_permission_requests_go_through_the_runtime_s_approvals_with_their_tool_call_as_the_ask`, `test_steering_is_refused_until_a_fixture_passes` and `test_acp_levels_never_reach_trainable`; `tests/unit/topology/test_check.py::test_a_role_on_a_harness_whose_own_agents_cannot_be_turned_off_must_allow_them` and `tests/unit/drivers/test_check_driver.py::test_a_harness_whose_own_children_cannot_be_turned_off_skips_that_check` | |
| M3 a named check | `DriverInfo.check`, `check_harness`, `doctor --check`, the pin to a distribution | `tests/unit/cli/test_machine.py::test_doctor_checks_an_installed_driver_that_names_its_check` | |
| M4 conformance | `check_driver` on a scripted ACP agent, and on OpenCode against `FakeModel` | `tests/conformance/test_conformance.py::test_the_acp_driver_passes_check_driver_on_a_scripted_acp_agent`, and the slow `tests/integration/test_acp.py::test_opencode_through_acp_passes_check_driver_against_fake_model` where `opencode` is on `PATH` | |

## Open questions

1. Where do first-party extensions live and ship? This builds the default, pending the owner's ruling: `extensions/<name>`, each a
   distribution with its own version and tag. Another place moves a folder and a workspace member and removes nothing else.
2. Should ACP be spoken over the ACP Python SDK or the SDK's own `rpc.Peer`? This builds the default, pending the owner's ruling:
   `rpc.Peer` on protocol 1. The SDK's client would replace `driver.py`'s use of the peer, and it drops an update it cannot parse
   before a client sees it, so an unknown update would keep its gap and lose its raw frame: that answer would change
   `test_an_unknown_update_keeps_its_raw_frame_and_a_gap` and what STATUS says of it, and nothing else built here.
3. Which agent is the reference, and is Prime Agent's live probe approved? This builds the default, pending the owner's ruling:
   OpenCode is the reference, checked once it runs on a test host, and Prime Agent waits.

## Evidence

- [acp-mcp.md](../research/acp-mcp.md): the version 1 surface, what ACP cannot express, the ACP SDK's dropped updates and the
  resolver probes, and section 6, the probe that did not run and the schema read again.
- [adapter-others.md](../research/adapter-others.md#acp-behaviour-live) and
  [the OpenCode transcript](../research/fixtures/opencode-sample.jsonl): OpenCode 2.2.5 through ACP against a scripted fake server,
  a permission request's `toolCall` and options, a cancelled prompt, and -32603 for a second prompt.
- The tests the rollout plan names, run on a scripted ACP agent that is `ScriptedDriver` behind ACP on `FakeModel`. Nothing here
  ran on OpenCode.
