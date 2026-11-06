# RFC 0034: Isolation is an extension's, and the runtime's own git runs inside it

| | |
|---|---|
| Status | Accepted, 2026-11-06 |

## Summary

`Extension.isolation` with `refusal()` and `wrap(writable, readable, hidden)`, the core saying what an isolated agent may write and see; everything the runtime runs in its tree through the same wrap; its home in its folder; `DriverInfo.installed` from every driver; `bwrap` shipped in the SDK, loaded only when named

## Motivation

RFC 0031 made `isolated` the top of the workspace ladder, a snapshot whose harness an extension confines, and refused it until an
extension gave one. Without it, a shell-capable agent runs as you and can read another agent's token, the owner's token and every
other session (§15). The workspaces design named the seam and the first provider. Its safety review verified that a `filter.*.clean`
or a `core.fsmonitor` in an agent's own git config ran unconfined under the runtime's `status` and `diff`, and filter names cannot be
known in advance to be overridden. So confining the harness alone would hand an isolated agent an unconfined command at every turn's
end. Building it showed the design wrong in a few details, each changed below in the smallest way that keeps its rules.

## Proposal

- **One kernel field, one value.** `Extension.isolation`, typed `Any` as `presets` carries values the kernel does not know, holds an
  isolation with two members. `refusal()` says why it cannot confine anything on this machine now, or None. `wrap(writable, readable,
  hidden)` is the argv that runs a command after it. That command writes only in `writable` and a /tmp of its own. It finds each of
  `hidden` empty but for the `readable` paths in it, each as it resolves outside. It sees only the processes it starts, which all end
  when it does, and it keeps the network. The design passed `refusal(role, info)` and `wrap(spec, workspace, installed)`. The core
  already knows every path those carried, and the runtime's own git has no `AgentSpec`. So the core decides what an isolated agent
  may write, read and see, in `runtime/isolation.py`, and a provider only enforces it, knowing nothing of the session folder's
  layout. `refusal` takes no role, as nothing a provider checks depends on one.
- **What an isolated agent gets.** It writes its agent folder, which holds its workspace and its harness's home, and a private /tmp.
  Its hidden folders are your home, as `HOME` names it and as your account does, the session root with every session under it, and
  `XDG_RUNTIME_DIR`, where sockets are made. It reads your repository's objects, which its snapshot borrows, and where its harness is
  installed. The design hid `$HOME` alone, which leaves your real home and your keys readable to a runtime started with `HOME` set
  elsewhere. What stays reachable: everything you can read outside the hidden folders, the network, every loopback service, every
  abstract socket, and every socket file outside the hidden folders, which a read-only mount does not stop a connect to. It runs on
  the same kernel, as the same uid.
- **Everything the runtime runs in an isolated tree goes through that wrap,** so nothing an agent writes into its repository's config
  or attributes runs outside its isolation. That covers the look, the launch's and resume's check that the tree is still a work tree
  of its repository, the stop's reading of what removal would lose, making a kept snapshot whole, and finding its objects for the
  session's bundle. The design listed the look, the stop and making whole. The code also ran git there for the presence check and for
  the bundle's `rev-parse`, so those run through the wrap too. Building the snapshot does not, since no agent has run there yet.
- **The runtime's git in an isolated tree runs on the allowlist its harness gets,** `PATH` and `HOME` plus the three git settings
  the runner always sets, never the runtime's whole environment. A program the agent's own git config names, a `filter.*.clean`
  among them, runs inside the isolation on that allowlist, so it cannot read a variable the runtime holds that §15 keeps from the
  harness. Outside an isolated tree the runner passes the environment as before.
- **The runtime's own writes into the agent folder follow no symlink the agent could plant.** The whole agent folder is the isolated
  harness's to write, so it could leave a symlink where the runtime next writes its own files — the process record, the stderr log,
  the instructions file, the `ph` shim, pi's sealed settings — or reads them back, and the runtime runs those unconfined. Each such
  open goes through `open_beneath`, which opens every component below the agent folder with `O_NOFOLLOW`, so a planted symlink is
  refused, never followed out of the tree. A log whose path was made a symlink is dropped, not followed and not a stall; a record a
  symlink shadows is named and removed in place. The agent folder itself is the runtime's, reached through its own path.
- **The harness's home is `<agent folder>/home`,** given as `HOME` in `spec.env`. A driver given a `HOME` there inherits none of the
  variables that keep a harness's state elsewhere: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `PI_CODING_AGENT_DIR` and, beyond the design's
  three, `PI_CODING_AGENT_SESSION_DIR`. So the harness keeps its state there, and the driver's own reads, such as Claude's
  `reconcile`, find it there. The rule rests on `spec.env`, so no driver knows the mode.
- **`AgentSpec.wrap` carries the argv,** which `Process.launch` puts between the trampoline that records the pid and the command. The
  recorded group leader is then the confiner. A wire frame names no wrap, since the program runs inside it.
- **Every driver declares `DriverInfo.installed`,** the paths its harness reads to run, as it reaches them. Claude Code declares where
  `PATH` finds `claude`, a link into a versions folder in your home, so what it resolves to is bound and each link on the way is made
  again. Codex declares its `PATH` entry and the standalone release that `codex-package.json` names, which holds the `bwrap` of its
  own sandbox. pi declares itself, its `node_modules`, node, and the Python our shim runs on. The OpenHands worker declares the
  runtime's Python. `exec` and `wire` declare where `PATH` finds the program, and a wire program may add paths in its description. A
  harness in the runtime's own process declares none and is refused, as nothing can confine it.
- **Refused before any cost,** at exit 78, in the loop that checks a role's sandbox: no extension the team names gives an isolation;
  two do, naming both; the isolation's refusal, such as `bwrap` failing to confine `true` where user namespaces are blocked; a harness
  that declares no installed path; and a role with no auth profile whose harness signs itself in. The design refused a plan login;
  any login of a harness's own lives in your home, which an isolated harness never sees, so every kind is refused. On a training
  system's gateway, no login is the harness's own. A spawn asks the refusal again before it builds the snapshot, where the design
  asked after, so nothing is built that cannot run. A launch whose harness was signed in since fails, as §15 holds the plan login line
  at launch too.
- **Assurance `isolated` is recorded only for a launch through the wrap.** Only an isolated workspace's record says it, and launching
  one fails without its isolation.
- **The first provider, `bwrap`, ships in the SDK distribution** as the module `platoon_harness.bwrap`, registered as `bwrap` under the
  existing `platoon_harness.extensions` entry point group, and imported only when a team names it. A boundary test holds every other
  module of the SDK and the command line to never importing it. It is a few dozen lines over the system's `bwrap`, with no
  dependency, so it gets no distribution of its own and no `extensions/` folder, where the design put one. Its argv is
  `--unshare-user --unshare-pid --unshare-ipc --new-session --die-with-parent`, `--ro-bind / /`, `--proc /proc` and `--dev /dev`, a
  tmpfs over /tmp and over each hidden folder, each link on the way to what it binds made again, read-only binds of what may be
  read, a writable bind of the agent folder, and each hidden folder remounted read-only. A hidden folder inside /tmp stays hidden and
  read-only there too. With `--new-session`, a git filter that the look runs from a runtime in your terminal has no controlling
  terminal to push keystrokes into. The probe confines `true` the same way.

## Alternatives

| Alternative | Why not |
|---|---|
| The design's `wrap(spec, workspace, installed)` | Each provider would learn the session folder's layout, and the runtime's own git, which has no spec, would need another call |
| Make only `workspace/` and `home/` writable in the wrap, moving the runtime's files out of the folder | The harness writes its home, workspace, `/tmp`, and pi's and OpenHands' state across the folder; binding each writable subtree would couple the provider to the layout. Hardening the runtime's own writes with `O_NOFOLLOW` is smaller and keeps the one writable bind |
| Pass the runtime's whole environment to git in an isolated tree | A program the agent's git config names would read a variable §15 keeps from the harness |
| A network namespace of its own | It cuts the tool plane, which is on loopback, and a training system's gateway on loopback with it |
| The look unconfined, with risky settings overridden | Filter names cannot be known in advance, and the safety review saw a filter and an fsmonitor run unconfined |
| Hiding only `$HOME` | A runtime started with `HOME` elsewhere would leave your real home readable |
| Copying the harness's login into its home | A credential is never read, copied or proxied (§15); an auth profile gives model access instead |
| `bwrap` as a distribution of its own, or under `extensions/` | One more package to version for a module with no dependency |
| A Landlock provider for hosts that block user namespaces, Seatbelt on macOS | Until someone asks |

## Consequences

- An isolated workspace stays `experimental` in STATUS. It rests on unprivileged user namespaces, which a kernel setting, AppArmor or a
  container's seccomp can block. Its escape tests have passed on one Linux host, on bubblewrap 0.4.1. A provider on another host
  says why it cannot confine before anything is spent.
- A session's folder lives under a test's `tmp_path`, which is under the system temp dir, and the wrap mounts a private /tmp, so an
  integration test cannot show a hidden session folder is hidden on its own there. The bwrap unit test shows the per-folder masking
  and the read-only root on folders outside the system temp dir, where the private /tmp cannot be what hides them; where no such
  directory is writable it says so and does not pretend to have shown it.
- Neither the harness's git nor the runtime's git in an isolated tree reads your global git config, so your global excludes do not
  apply there. A file only they would ignore shows as untracked, and the stop keeps the workspace for it.
- Each git call in an isolated tree pays the confiner's start: about 0.05 s on the host it ran on, a dozen times in a look.
- `--die-with-parent` ends an isolated harness with the runtime that started it, so a runtime killed outright takes it down, where
  an unconfined harness lives on until the next runtime reaps it. A resume starts it again, as after any crash.
- bubblewrap passes no `SIGTERM` on, and its confiner dies of one, which kills the harness outright. So `Process` gives a harness under
  a wrap the end of its stdin and its grace, then `SIGKILL`, and reports `crash_window`, where it would otherwise have seen the group
  gone after `SIGTERM` and said nothing of the kill.
- A harness installed by a route its driver does not declare, such as an npm install of Claude Code, has not run isolated. If what
  it needs lies in a hidden folder, its spawn fails, as any harness that cannot start does.
- The agent's record keeps its workspace's `mode`, `isolated`, which marks the launch's assurance. Whether a commit's code is
  confined is decided elsewhere, by the look that found it: the `Looks` view marks a commit found in an isolated workspace, and one
  built on such a commit, and `repo.test` (RFC 0056) refuses to run either outside its isolation. Attribution does not decide it,
  since an isolated agent writes its own reflog.

## Evidence

- `tests/unit/runtime/test_isolation.py`: the refusals before any cost, `test_isolated_on_a_plan_login_is_refused`,
  `test_isolated_assurance_is_recorded_only_for_a_confined_launch`, `test_an_isolated_harness_keeps_its_state_in_its_own_home`,
  `test_the_runtime_s_git_in_an_isolated_tree_runs_under_its_wrap` and, on real bubblewrap,
  `test_an_isolated_agent_s_git_config_runs_nothing_outside_its_isolation`, which also shows a variable only the runtime's
  environment holds does not reach a program the agent's git config names.
- `tests/unit/drivers/test_env.py`, `test_a_write_beneath_a_folder_does_not_follow_a_symlink_planted_in_it`, and
  `tests/unit/drivers/test_process.py`, `test_a_symlink_planted_where_the_log_goes_is_not_followed`: the runtime's own writes into
  the agent folder follow no symlink the agent could plant.
- `tests/unit/runtime/test_bwrap.py`: what a wrapped command can write, read and see, that nothing it starts outlives it, that it
  still reaches loopback, and, on folders outside the system temp dir, that a hidden folder and the read-only root hold where the
  private /tmp does not reach, on the machine's bubblewrap.
- `tests/integration/test_isolated.py`, slow: Claude Code 2.1.319, Codex 0.167.0 with its own sandbox nested inside, pi 1.5.0 and the
  OpenHands worker on SDK 1.59.0, each isolated against FakeModel with your home hidden. From its own shell each tried the ways out
  its probe names, committed, left a process in a session of its own, set a git filter the look then ran, and called our tools.
- `tests/unit/drivers/test_boundaries.py`, `test_nothing_but_a_team_that_names_it_loads_bwrap`.
- On the host it ran on, a socket file on a read-only mount and an abstract socket were both reached from inside, and a write to a
  separate Lustre mount was refused.
