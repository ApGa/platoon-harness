# RFC 0075: An ended agent's folder keeps its record and no scratch or credential

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`drivers/__init__.py`](../../packages/sdk/src/platoon_harness/drivers/__init__.py), [`drivers/process.py`](../../packages/sdk/src/platoon_harness/drivers/process.py), [`runtime/host.py`](../../packages/sdk/src/platoon_harness/runtime/host.py), [architecture sections 4](../architecture.md#4-session-folder-and-process-model), [7](../architecture.md#lifecycle), [9](../architecture.md#9-drivers) and [15](../architecture.md#15-security), [security.md](../security.md#retention), [RFC 0008](0008-driver-contract-and-wire.md), [RFC 0021](0021-what-a-harness-leaves-behind.md), [RFC 0045](0045-an-agent-s-process-is-not-its-identity.md), [RFC 0053](0053-a-gateway-admission-launches-sealed.md) and [RFC 0055](0055-the-export-is-the-session-as-it-ended.md) |
| Discussion | The owner's request of 2026-11-08, from the copies of the sessions of the GPU runs, kept outside this repository. The request accepts no design: this one waits for the owner's acceptance |
| Implementation | `fix: Remove an ended agent's scratch and the credential files its driver names`, and the fixes `fix: Tell an ended agent's authority even when removing its harness's files fails` and `fix: Say what an ended agent's stop leaves behind a symlink an agent planted` |

## Summary

Each driver names, in `DriverInfo.credentials`, the files beneath an agent's folder where its harness keeps a credential, and
when an agent ends, finished, retired, cancelled, failed or lost, its stop removes those and its harness's `TMPDIR`, and keeps
the rest of the folder, before it tells the agent's authority how it ended. An agent put to rest, or in a session that stops,
keeps everything, as its harness comes back. So once each ended agent's stop has run, which its authority hears of last, a
session's folder, which is its export, holds neither a harness's scratch nor a file its driver names as a credential, as it
already holds none of the runtime's own token files after a clean stop. An agent that has not ended keeps both.

## Motivation

An agent's folder, `agents/<name>/`, is where its harness runs: its process record, its `stderr.log`, its `TMPDIR`, and for a
sealed launch or an isolated agent a home or an agent directory of the harness's own. Nothing removes any of it, so a session
keeps it for as long as it is kept, and the folder is the export ([RFC 0055](0055-the-export-is-the-session-as-it-ended.md)), so
every copy carries it.

The owner reports that in the copies of the sessions of the GPU runs an agent's folder held some 56 files, of which some 45
were Node's compile cache and pi's jiti cache under `agents/<name>/tmp`, and that pi's `auth.json` under `agents/<name>/pi`
held the run's gateway credential, dead once the run had ended. That is the owner's measurement, unverified here. Here, one
turn of pi 1.5.0 on FakeModel leaves 40 files in `tmp` and an `auth.json`, which pi makes as it starts, in its agent
directory: a sealed launch's, `agents/<name>/pi`, or an isolated home's. Its sealed launch here leaves that file holding no
credential, as `test_contract.py` shows no form of the bearer in any file, so why the runs' copies held one is unknown. RFC
0055 says the export holds no key, and the runtime removes its own token files at a clean stop, but nothing removed what a
harness kept.

## Proposal

### 1. A driver names where its harness keeps credentials

```python
class DriverInfo(Model):
    ...
    credentials: tuple[Path, ...] = ()  # beneath the folder its spec names; refused if one could leave it
```

Only the driver knows its harness, so it names them, and the runtime guesses none. A path is relative to the folder the spec
names, with no `..`, and `DriverInfo` refuses any other, since the end removes it. A wire program names its own beneath the
folder its frame names, which `WireDriver` says beneath `wire/` in the agent's. An isolated harness's home is `home/` in the
agent's folder, which `drivers.env.homedir` names, so a driver names its harness's files there as in any home. A harness on your
own login keeps its state in your home, outside the agent's folder, so nothing of it is named, or touched.

| Driver | Names | Where its harness keeps a credential there |
|---|---|---|
| `pi` | `pi/auth.json`, `pi/mcp-auth.json`, `home/.pi/agent/auth.json`, `home/.pi/agent/mcp-auth.json` | Its agent directory, a sealed launch's or an isolated home's: its providers' keys and logins in `auth.json`, and its MCP servers' logins in `mcp-auth.json` |
| `codex` | `home/.codex/auth.json`, `home/.codex/.credentials.json` | Its login, as `codex login` writes it, and its MCP servers' logins where no keyring holds them |
| `claude` | `home/.claude/.credentials.json`, `home/.claude.json`, `home/.claude/backups` | Its login, a key it signed in with where no keychain holds one, in its config, and the copies it keeps of that config |
| `openhands` | None | Its key reaches the worker's environment alone, which reads it and lets it go, and the SDK keeps it in no file |
| `exec`, `ScriptedDriver` | None | |

### 2. An ended agent's stop removes them, and its harness's `TMPDIR`

The ended transition requests one `stop` effect for every status, which ends what the agent's harness left, looks at its
workspace and ends that. Then, in a `finally`, it removes the harness's `TMPDIR`, `tmp/`, whole, and each file or folder the
role's driver names, and last, in a `finally` of its own, it tells the authority how the agent ended, so each happens even when
a step before it fails. It follows no symlink an agent could plant: one at a name is removed itself, and what it names stays,
and one on the way is not followed, so what lies past it stays. Each step is safe to repeat, as a stop retried after a crash
is. A rest and the owner's stop end processes and remove nothing, since the agent comes back on its native session.

What stays of them is said in the runtime's log, as a harness that would not stop is: `<agent>'s stop: tmp could not be
removed: Permission denied`, or `own/auth.json stays, as a symlink on its way is not followed`. So is a driver that could not
say where its credentials are, whose harness's `tmp` goes all the same. A driver that raises what no driver should fails the
stop, saying why, and its harness's `tmp` goes and the authority hears all the same.

### 3. What stays, and what goes with `tmp/`

The journal, `annotations.sqlite`, the manifest, bodies, what the agent was told, `instructions.md` among it, its harness's
own transcripts, pi's `sessions/*.jsonl`, Codex's `sessions/` and Claude Code's `projects/` among them, and `stderr.log`. These
are the record, which the export is for.

Whatever a harness keeps in its `TMPDIR` goes with it. pi 1.5.0 keeps there the full text of a tool result it cut for the
model, `pi-mcp-*.txt`, and of a long command's output, `pi-bash-*.log`, and its transcript names each by its path, which names
nothing once the agent has ended: what the model was shown of it stays, in the transcript and in the journal. Claude Code keeps
a tool result it cut beside its transcript, in its session's `tool-results/` under `projects/`, which stays. What Codex keeps
in its `TMPDIR` was not looked into.

## The hard parts

- **A stop the owner's stop cuts short** still removes them, in its `finally`, once the shutdown has ended the harness. A stop
  that had not begun when the runtime stopped, or one a killed runtime cut off before its `finally`, runs again only at the next
  runtime, so a session that is never resumed, as a trainable one never is, keeps that agent's scratch and credentials, as a
  killed runtime's token files stay until the next stop. The authority hears of the end only once they are removed, so a
  program that waits for that before it leaves its session leaves none.
- **An agent that never ends** keeps its own: one in a session that stopped, which comes back on a resume, and one idle when
  its session closed or settled, as a close ends no agent, though a closed session runs no harness again. A trainable session
  is never resumed, so nothing removes them later. Whether the GPU runs' sessions ended this way is not known here (Open
  questions).
- **A harness its driver could not stop** is ended before the removal by `reap`, which the stop runs whatever the driver did,
  where its group is provably ours. A process left alone, a group not provably ours, may still write in `tmp/` or a
  credential file after the removal, and is named by the stop as before.
- **A symlink an agent planted** at a name or on its way is not followed, so a credential it leads to stays, which the stop
  says in the runtime's log.
- **A wire program's harness in an isolated home**: the home, `home/`, lies beside the program's own folder, `wire/`, so a
  program can name no file there. OpenHands, the one wire worker shipped, keeps its key in no file.
- **A credential outside the files named**, such as a key an agent wrote in its workspace or a harness put in a transcript, is
  content, which security.md says nothing sanitizes.

## Alternatives

| Alternative | Why not |
|---|---|
| The runtime removes every file named like a credential | A guess removes what it should not and misses what it should; each harness's own code says where it keeps one, and its driver is what knows its harness |
| Remove the whole folder but what is the record | The record differs by harness, pi's `sessions/`, Codex's `sessions/`, Claude Code's `projects/`, so naming what stays is as much as naming what goes, and the credentials are fewer and change less |
| A `TMPDIR` outside the session's folder | `TMPDIR` carries the folder's name, which is how `stop` and `reap` find what left a harness's group ([RFC 0021](0021-what-a-harness-leaves-behind.md)), and a second place would need owning and removing too |
| A method `Driver.credentials(spec)` | A stop after a crash has no driver started and no spec; `describe` answers without either, and over the wire too |
| Remove them at a rest, or at the owner's stop | The agent comes back on its native session, and a harness may need its login there |
| An export command that leaves them out | The folder is the export, with no second format ([RFC 0055](0055-the-export-is-the-session-as-it-ended.md)) |
| Keep pi's full text of a cut tool result | pi names those files by a prefix and a random suffix in the `TMPDIR` its caches share, with no setting to put them elsewhere (`dist/utils/output-files.js`), so keeping them would mean guessing by name; they hold what the model was not shown, and the record holds what it was |

## Consequences

- A session copied once each ended agent's stop has run holds neither a harness's scratch nor a file its driver names as a
  credential, and its record whole, but for what a harness kept in `tmp/`, such as pi's full text of a tool result it cut.
- A driver of yours names none until it says them, so its harness's `tmp/` goes at an end and nothing else.
- Each end costs a walk of `tmp/`, some 40 files for pi here.
- `DriverInfo` gains `credentials`, which a wire program may give in its `describe` within protocol 2, and
  `drivers.env.homedir` and `drivers.process.clean` are public.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| One step | `DriverInfo.credentials`, named by each first-party driver and carried over the wire; the stop's removal; the docs | `test_an_ended_agent_s_tmp_and_credentials_go_and_its_record_stays`, `test_an_ended_agent_s_tmp_and_credentials_go_even_when_a_step_before_fails`, `test_an_agent_put_to_rest_keeps_what_it_needs_to_resume_and_resumes`, `test_a_session_copied_after_its_agents_ended_holds_no_credential_file`, and each first-party driver's on its real binary in the slow pass | `fix: Remove an ended agent's scratch and the credential files its driver names`, `fix: Tell an ended agent's authority even when removing its harness's files fails` and `fix: Say what an ended agent's stop leaves behind a symlink an agent planted` |

## Open questions

1. Whether a session's close removes the same of an agent that never ended, since a closed session runs no harness again. The
   default is no, as an end is the one point where an agent is known never to come back, pending the owner's ruling, and a
   different answer adds a step to the close and removes none of this. Under the default, a session that closes or settles with
   its agents idle keeps every one's scratch and credential files, and a trainable one keeps them for good, as it is never
   resumed: that may be the GPU runs' case, which this change then leaves as it was. A program that ends every agent and waits
   for its authority to hear of each, as the training guide says, leaves none.

## Evidence

- Where each harness keeps a credential, read from its code and never from a credential: `@earendil-works/pi-coding-agent`
  1.5.0, `dist/core/auth-storage.js`, which makes `auth.json` in the agent directory as `{}`, and `dist/extensions/mcp/oauth.js`,
  which keeps MCP logins in `mcp-auth.json`; the strings of the `codex` 0.167.0 binary, which name `auth.json` and, beside its
  MCP OAuth store, `.credentials.json`; and those of Claude Code 2.1.319, which keeps its login in `.credentials.json` in its
  config folder and a key it signed in with in `.claude.json`'s `primaryApiKey`, and keeps copies of that config in `backups`.
- One turn of each real harness on FakeModel in an agent's folder, file names and sizes alone: pi left 40 files in `tmp/`, and
  `auth.json` and `models-store.json` at two bytes each beside its `sessions/`, sealed or in an isolated home; Codex in an
  isolated home its databases, `sessions/` and skills, and no `auth.json`; Claude Code `.claude.json`, `.claude/backups/` and
  `projects/`, and no `.credentials.json`; and no file held a key or a bearer of the run.
- pi's full text of a cut tool result, read from its code: `dist/utils/output-files.js`, which writes every such file in the OS
  temp directory, and `dist/extensions/mcp/tools.js` and `dist/core/tools/bash.js`, which name it in the result's
  `fullOutputPath`. Claude Code 2.1.319's `tool-results`, read from its binary's strings.
- Tests: [tests/unit/runtime/test_host.py](../../tests/unit/runtime/test_host.py),
  `test_an_ended_agent_s_tmp_and_credentials_go_and_its_record_stays`, finished, retired and cancelled,
  `test_a_failed_agent_s_tmp_and_credentials_go_and_its_record_stays`,
  `test_a_lost_agent_s_tmp_and_credentials_go_and_its_record_stays`,
  `test_an_ended_agent_s_tmp_and_credentials_go_even_when_a_step_before_fails`,
  `test_an_agent_put_to_rest_keeps_what_it_needs_to_resume_and_resumes`,
  `test_a_session_copied_after_its_agents_ended_holds_no_credential_file`,
  `test_what_an_ended_agent_s_stop_could_not_remove_is_said_in_the_log`,
  `test_a_driver_that_cannot_say_where_its_credentials_are_leaves_them_and_says_so`,
  `test_an_authority_hears_of_an_end_whose_driver_broke_saying_where_its_credentials_are` and
  `test_an_authority_hears_of_an_end_whose_stop_a_shutdown_cut_as_its_driver_described_itself`;
  [tests/unit/drivers/test_process.py](../../tests/unit/drivers/test_process.py), `clean`'s, among them
  `test_clean_follows_no_symlink_an_agent_planted`, which says what stays;
  [tests/unit/drivers/test_wire.py](../../tests/unit/drivers/test_wire.py),
  `test_a_program_s_credentials_lie_beneath_its_own_folder_in_the_agent_s` and
  `test_a_credential_s_path_that_could_leave_the_agent_s_folder_is_refused`; on the real binaries, slow,
  [tests/integration/test_pi.py](../../tests/integration/test_pi.py), `test_the_credential_files_pi_names_are_the_ones_it_writes`,
  [tests/integration/test_codex.py](../../tests/integration/test_codex.py),
  `test_the_credential_file_codex_names_is_the_one_its_login_writes`, and
  [tests/integration/test_claude.py](../../tests/integration/test_claude.py),
  `test_the_files_claude_code_names_are_where_it_keeps_a_login_in_an_isolated_home`; and
  [tests/integration/test_contract.py](../../tests/integration/test_contract.py),
  `test_a_managed_session_runs_as_a_training_authority_drives_it`, whose copy of the closed session holds neither, on
  ScriptedDriver, pi and OpenHands.
