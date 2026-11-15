# RFC 0083: A result made from a read-only installation speaks for it wherever it is mounted

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-13 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`drivers/levels.py`](../../packages/sdk/src/platoon_harness/drivers/levels.py), [`testing/conformance.py`](../../packages/sdk/src/platoon_harness/testing/conformance.py), [`testing/harnesses.py`](../../packages/sdk/src/platoon_harness/testing/harnesses.py), [`runtime/paths.py`](../../packages/sdk/src/platoon_harness/runtime/paths.py), [`runtime/opening.py`](../../packages/sdk/src/platoon_harness/runtime/opening.py), [`runtime/host.py`](../../packages/sdk/src/platoon_harness/runtime/host.py), the command line's [`machine.py`](../../packages/cli/src/platoon_harness_cli/machine.py), [architecture section 9.3](../architecture.md#93-verified-not-believed), [RFC 0034](0034-isolation-is-an-extension-s-and-the-runtime-s-git-runs-inside-it.md), [RFC 0044](0044-a-level-is-earned-on-the-machine-that-runs-it.md), which this amends, [RFC 0072](0072-acp-agents-are-driven-by-a-first-party-extension-that-names-its-own-check.md), [RFC 0081](0081-platoon-harness-is-one-distribution-with-the-command-line-as-its-cli-extra.md) and [RFC 0082](0082-a-launch-in-the-environment-keeps-the-harness-s-own-tools.md) |
| Discussion | None yet |
| Implementation | None yet |

## Summary

A kept conformance result is pinned to the driver, the harness version, the SDK and the host it was made on
([RFC 0044](0044-a-level-is-earned-on-the-machine-that-runs-it.md)). In a sandbox that pin fails a harness: a fresh
root holds no result, and a host does not stand for an image, as a sandbox goes by its host's name or by one of its
own, depending on how it runs. Where every path a harness reads to run is read-only, a result now names those paths,
resolved, as its installation, and speaks for any agent whose harness runs from that installation, at the same paths
and read-only, on any host. A result that names none speaks only on the host it was made on, and only for an agent
whose harness runs from no installation; every result kept before this parses as one. A training system that runs a
session in a sandbox from a read-only toolchain makes one result from each build of it, keeps the result inside that
build, and places it in each fresh root as the file `doctor --check` keeps, `conformance/<driver>.json`, which
`write_conformance` writes: no new concept. The result still names the host it was made on, which the record keeps,
and a level earned from it elsewhere says where it was made.

## Motivation

`trainable` needs a kept result that speaks for the harness that runs (architecture section 9.4), and so do the other
levels. Code is cited below as `path:line` at `e73a221`, under `packages/sdk/src/platoon_harness/` but for the command
line's and the tests', which are named from the repository's top. A result is read from the session's root before any
harness launches, for a trainable session (`runtime/opening.py:81-93`), and at each launch and resume
(`runtime/host.py:1076-1085`), and it speaks only where its pin matches what runs: the driver's name and class, the
harness version, the SDK and the host, `socket.gethostname()` (`drivers/levels.py:122-145`, `186-204`), which
`check_driver` records where the checks ran (`testing/conformance.py:803`).

In a sandbox the pin fails a harness both ways:

- **A fresh root holds no result.** Every agent reads `unverified`, and `check(team, trainable=True)` refuses a
  trainable team before anything runs, naming `doctor --check`.
- **A host does not stand for an image.** A sandbox goes by its host's name or by one of its own. Docker gives a
  container on the host's network the host's name, so a result made on that host speaks for a harness in any image
  there, and gives a container with no network the start of its id, which no result made elsewhere matches
  (UNVERIFIED: documented by Docker, not run here). SingularityCE 4.4.1, run with `--containall`, kept the host's
  name, on the host's network and on none, as it shares the host's UTS namespace (Evidence); Apptainer keeps it unless
  told otherwise (UNVERIFIED), and what Enroot does is not known here.

A training system that runs a whole session inside a task's sandbox, from a read-only toolchain that holds the SDK and
the harness, needs a result that speaks there, whether its agents launch sealed or keep their own tools
([RFC 0082](0082-a-launch-in-the-environment-keeps-the-harness-s-own-tools.md)). Platoon, a training system, places a
single harness in a task's sandbox today, from a read-only toolchain that holds that harness and not this SDK, and runs
its platoon-harness team on its own host (Evidence).

RFC 0044 put the host in the pin "since the checks prove the driver's code and the binary together, where they ran", and
added it "because a driver changed by an upgrade, or a machine whose shell behaves otherwise, as Codex's did here, is
not what was checked". It rejected shipping results from CI because "It vouches from another machine for a binary the
user may not run", and pinning the binary's path because "A path says where a binary is, not what it is: the version
names it, and the same binary moved would read `unverified`".

So the host stands for the machine: what the checks ran on besides the driver and the binary, the shell a harness runs,
and a harness's own sandbox where it has one, as Codex's. A harness that runs from a read-only toolchain brings its
binary and what that runs on with it, its runtime and the packages it loads, as the SDK and the driver come too. Those
are the same wherever the toolchain is mounted. The machine around them is not: its kernel, and the image the toolchain
is mounted into, which in a training system differs by design, as each task brings an image of its own.

## Proposal

### 1. A result names the read-only installation it was made from

```python
class Conformance(Checks):
    driver: str
    implementation: str
    version: str | None
    sdk: str
    host: str
    installation: tuple[str, ...] | None = None  # the paths its harness reads to run, resolved, where each is read-only

class Profile(Model):
    ...
    host: str = Field(default_factory=socket.gethostname)
    installation: tuple[str, ...] | None = None  # the same, of the harness that runs
```

The installation comes from `DriverInfo.installed` (`drivers/__init__.py:97-114`), "the paths its harness reads to run,
as it reaches them", which every driver declares for isolation
([RFC 0034](0034-isolation-is-an-extension-s-and-the-runtime-s-git-runs-inside-it.md)): each path resolved, in the order
the driver names them, where there is at least one and each lies on a mount that is read-only where the runtime looks,
as `os.statvfs` says by `ST_RDONLY`; None where a path is writable, or where the driver names none. Where no path is
writable and the mount of one cannot be read, whether there is an installation is unknown, which is not none: it raises
`DriverError`, naming that path and why. pi names itself, its `node_modules`, node and the Python our shim runs on
(`drivers/pi.py:170-175`), and OpenHands the runtime's own Python (`drivers/env.py:23-25`,
`drivers/openhands/worker.py:167-170`).

`check_driver` records it beside the host (`testing/conformance.py:803`), and none where it is unknown, which vouches
for no installation. The host's profile at each launch and resume (`runtime/host.py:1076-1083`), and the one `check`
builds before any launch (`runtime/opening.py:90-92`), take it from the `DriverInfo` the driver gave; where it is
unknown, the launch and `check` refuse, naming the path, and `doctor` says that whether a kept result speaks for the
binary is unknown. A harness in the runtime's own process declares no path, so it has no installation. A
harness installed in a sandbox's image names none where the image is writable, and names its installation where the
image is mounted read-only, as a toolchain does.

### 2. A result that names an installation speaks for it in place of its host

**The rule: a kept result speaks for an agent of the driver, the harness version and the SDK it was made with: where it
names an installation, wherever the agent's harness runs from that installation, at the same paths and read-only, on any
host; where it names none, only on the host it was made on, and only for an agent whose harness runs from no
installation.**

- `_pin` compares the installations, and the hosts only where the result names none (`drivers/levels.py:196-203`). The
  rest of the pin stands: the driver by its name, its class and the releases it stands on
  ([RFC 0072](0072-acp-agents-are-driven-by-a-first-party-extension-that-names-its-own-check.md)), the harness version
  and the SDK.
- **A result that names none.** A result made from an installation that could change names none, so it speaks for its
  host alone, as RFC 0044 has it, and there only for an agent whose harness runs from no installation either: what it
  checked could have changed under it, so it vouches for no installation. A result kept before this parses as one that
  names none, and, as after any SDK upgrade (RFC 0044), speaks again once made with this SDK.
- **What it vouches for.** A result that speaks by its installation vouches for the driver, the SDK, and the harness
  with what it runs on, as the installation holds them. It does not vouch for the machine around them: the kernel, and
  the shell and libraries of the image the installation is mounted into. What the checks proved of those, the shell
  checks under `operational` among them, they proved on the host the result names. So a level earned from a result made
  on another host says so, with a reason beside it: "its result was made on `<host>`, from this installation". The
  record keeps the result whole, with its host and its installation, beside the agent's own profile, as now.
- **What names the installation.** Its paths, and nothing the SDK reads in them. The SDK checks that each path lies on
  a mount that is read-only where the runtime looks, when it looks. It cannot see whether that stays so, as a process
  allowed to remount a path can make it writable, and a rootless runtime's root may be allowed to (UNVERIFIED); nor
  what the paths hold; nor whether a mount's source changes elsewhere, as a read-only bind of a writable folder does.
  That the paths still hold what the checks ran on is the training system's to keep, as RFC 0044 takes a version to
  name a binary: it keeps a mounted build unchanged in place, and keeps each build's result inside that build
  (section 3), so one build's result never speaks for another's at the same paths, and the paths need not be
  content-addressed.
- **What an agent with no result that speaks is told.** It reads `unverified`, with a reason that names what makes a
  result that speaks, which for a harness whose check ships with the SDK is `platoon-harness doctor --check`
  (`drivers/levels.py:179-183`). Where the agent's profile names an installation, the reason says to make a result
  from this installation: with `doctor --check`, which records the installation, or, where the command line is not
  installed, as an installation made for a sandbox need not hold the SDK's `cli` extra
  ([RFC 0081](0081-platoon-harness-is-one-distribution-with-the-command-line-as-its-cli-extra.md)), with
  `check_harness`, and to place it in the root with `write_conformance`; for a harness no check ships for, with
  `check_driver` and `write_conformance` (`testing/harnesses.py:218-221`).
- **A harness that cannot start.** Where `pi --version` exits other than 0, as it does where the image lacks a library
  pi's Node loads (The hard parts), pi's driver refuses to describe pi, with what pi printed on stderr, which `check`,
  a start and `doctor` then say (`runtime/opening.py:49-60`). Today a `pi --version` that fails reads as a version
  nobody said, so a trainable start says only that pi said none, and not why (`drivers/pi.py:178-181`,
  `drivers/levels.py:192-193`).

### 3. A training system places the result in each fresh root

1. **Make it once for each build**, from the build mounted read-only at the path its sandboxes mount it at, in a sandbox
   like those it will run. `check_harness(name, folder)`, which `doctor --check` runs, and `check_driver`, for a harness
   no check ships for, are the SDK's own, so the build needs no command line, and each runs against FakeModel on
   loopback and on no account (RFC 0044).
2. **Keep it inside the build**, written there before the build is marked finished, so whatever names the build covers
   it, a build made again at the same paths brings a result of its own, and one build's result never speaks for
   another's.
3. **Place it before the session starts**, in the root the session will use: `write_conformance(root, result)`
   (`runtime/paths.py:135-144`), or a copy of the file, to `<root>/conformance/<driver>.json`. `read_conformance` reads
   whatever is there (`runtime/paths.py:147-155`), before any harness launches and at each launch, and the pin decides
   the rest. Keep `<root>/conformance` read-only in the sandbox, as by binding a folder of the build's results there
   read-only: the model's commands can run as the root's user there, so one could otherwise remove a result, which
   leaves each later start of its driver short of `trainable`, or write a result of its own for those starts to read.

That is a file, and no new concept: the one `doctor --check` keeps. A root is its user's alone
(`runtime/paths.py:96-101`), so the training system places the file as the user the session runs as. The contract test
already writes a result into a fresh root before its session starts (`tests/integration/test_contract.py:349`).

### 4. What stays refused

| A result | Speaks for an agent? | Why |
|---|---|---|
| Made on another host, from no installation | No, as now | RFC 0044: the machine is part of what was checked |
| Made from no installation, for an agent whose harness runs from one, on any host, its own included | No | What it checked could have changed under it, so it vouches for no installation |
| Of another installation: other paths, or one of the same paths writable now | No | It was made from something else, or what runs could have changed under it |
| Of another driver, class, release, harness version or SDK | No, as now | The rest of the pin stands |
| That names no version, or of a harness that says none | No, as now | A version nobody said pins nothing |
| A file in the root that is no result | No: it reads as none | `runtime/paths.py:147-155` |
| Of a harness in the runtime's own process, or one installed in a writable image | Only on its host, for an agent whose harness runs from no installation | It names no installation |
| Made where the mount of a path its harness reads to run could not be read | Only on its host, for an agent whose harness runs from no installation | `check_driver` could not tell whether there was one, so it names none, which vouches for none |
| Any, for an agent whose harness reads to run a path whose mount cannot be read, where no path is writable | No: its start and `check` are refused, naming the path | Whether it runs from an installation is unknown, which is not none |

What it cannot refuse is what it cannot refuse now: a result written by hand, as a root's files are its user's to write.

Each promise has a test named for it:

| Promise | Test |
|---|---|
| A result made from a read-only installation speaks for it on any host | `tests/unit/drivers/test_levels.py::test_a_result_made_from_a_read_only_installation_speaks_for_it_on_any_host` |
| A result made from an installation that could change speaks for its host alone | `tests/unit/drivers/test_levels.py::test_a_result_made_from_a_writable_installation_speaks_for_its_host_alone` |
| A result that names no installation says nothing of an agent whose harness runs from one, even on its host | `tests/unit/drivers/test_levels.py::test_a_result_that_names_no_installation_says_nothing_of_an_agent_that_runs_from_one` |
| A result of another installation, or of the same paths made writable, says nothing of this agent | `tests/unit/drivers/test_levels.py::test_a_result_of_another_installation_says_nothing_of_this_agent` |
| A level earned from a result made on another host says where it was made | `tests/unit/drivers/test_levels.py::test_a_level_earned_from_another_host_says_where_its_result_was_made` |
| An agent that runs from an installation, with no result that speaks for it, is told to make one there with `doctor --check`, or, without the command line, with `check_harness`, or `check_driver` for a harness no check ships for, and place it with `write_conformance` | `tests/unit/drivers/test_levels.py::test_an_agent_that_runs_from_an_installation_is_told_to_make_its_result_there` |
| A result kept before this parses as one that names no installation | `tests/unit/drivers/test_levels.py::test_a_result_kept_before_installations_parses_as_naming_none` |
| A pi that cannot start is refused with what it printed, which `check` and `doctor` say | `tests/unit/drivers/test_pi.py::test_a_pi_that_cannot_start_is_refused_with_what_it_printed` and `tests/unit/cli/test_machine.py::test_doctor_names_what_a_pi_that_cannot_start_printed` |
| `check_driver` names the installation only where every path is read-only, and none where a harness reads no path or the mount of one cannot be read | `tests/unit/drivers/test_check_driver.py::test_a_result_names_its_installation_only_where_every_path_is_read_only` |
| A result placed in a fresh root earns trainable before any harness launches, and at its launch | `tests/unit/runtime/test_host.py::test_a_result_placed_in_a_fresh_root_speaks_for_the_installation_it_names` |
| Where no path is writable and the mount of one cannot be read, whether there is an installation is unknown, never none | `tests/unit/drivers/test_levels.py::test_an_installation_whose_mount_cannot_be_read_is_unknown_and_never_none` |
| `check` and a launch refuse an agent whose installation is unknown, naming the path and why | `tests/unit/runtime/test_host.py::test_an_installation_whose_mount_cannot_be_read_is_refused_naming_why` |
| `doctor` says that whether a kept result speaks for a binary is unknown where the mount of a path it runs from cannot be read | `tests/unit/cli/test_machine.py::test_doctor_says_unknown_where_the_mount_of_a_path_the_binary_runs_from_cannot_be_read` |
| A result made under one host name speaks under another, from the same read-only installation, on a real harness | `tests/integration/test_installation.py::test_a_result_made_under_one_host_name_speaks_under_another_from_the_same_installation`, slow, under `bwrap`, which can mount a folder read-only and give a host name of its own |

### 5. What changes for users

`Conformance` and `Profile` gain `installation`, and their docstrings say what it is, so the Python reference is made
again. `platoon-harness doctor` says a kept result speaks for the binary that runs by the same rule, naming the host it
was made on and, where it names one, the installation, where it now pins the result to the host
(`packages/cli/src/platoon_harness_cli/machine.py:98-99`). An agent that runs from an installation, with no result that
speaks for it, is told to make one there with `doctor --check`, or, without the command line, with `check_harness`, or
`check_driver` for a harness no check ships for, and to place it with `write_conformance`. A pi that cannot start is
refused with what it printed, which `doctor` says too, where today it reads as a pi that said no version.

Three pages that tie a result to the machine it was made on say too where one that names an installation speaks:
[architecture section 9.3](../architecture.md#93-verified-not-believed), which pins a result to its host, so that "an
agent's levels come from proof made on its own machine"; the levels row of [STATUS](../STATUS.md), "pinned to its
driver, the harness's version, the SDK and the host"; and [the training guide](../extending/training.md), whose advice
to run `doctor --check` "on each machine that runs rollouts" gains its counterpart for a session in a sandbox: make one
result for each build with `check_harness`, and place it in each fresh root. Nothing else changes: no command, no team
field, no event. A result kept before this parses as one that names no installation, and, as after any SDK upgrade,
speaks again once made with this SDK.

## The hard parts

- **Read-only is not content.** The SDK can see that a path is read-only where the runtime looks, when it looks, and
  not whether it stays so, what it holds, or whether it changed since the result was made. A process allowed to
  remount a path can make it writable. Linux locks the read-only flag of a mount that came from a more privileged mount
  namespace (mount_namespaces(7)), and a rootless runtime makes its mounts in a mount namespace its container's root
  owns, so that root may be allowed to (UNVERIFIED). A training system that changed a mounted build in place, or kept
  one build's result beside another build at the same paths, would have one build's result speak for the other at the
  same harness version and SDK. Keeping each build unchanged once mounted, and its result inside it, is the training
  system's to do.
- **A host name is not a machine.** A result that names no installation speaks by its host, as RFC 0044 has it, and a
  sandbox on its host's network can go by the host's name. So a result made on a host from no installation speaks for a
  harness installed in the writable image of a sandbox there, whose shell may differ, as it does today.
- **The machine around the installation.** A task's image brings the shell a harness runs, so what the shell checks
  proved in the image a result was made in may not hold in another: OpenHands' terminal cannot start where an image has
  no `bash`, which fails its agent's start. The level says where its result was made, and the start fails loudly where
  the harness cannot run, but `operational` reads met from checks made elsewhere.
- **What the installation leaves out.** `DriverInfo.installed` names the harness, its runtime and our Python, and not
  the C libraries they load, which come from the image: pi's Node, in its official Linux builds, loads libstdc++ at
  `GLIBCXX_3.4.21` and `CXXABI_1.3.11` or newer, libgcc_s and libatomic, and needs glibc 2.28 or newer (Evidence). So a
  result made in one image speaks in another whose libraries differ. Where Node cannot load them, pi cannot start, and
  its driver refuses it, naming the library (section 2). A toolchain that holds what its harness loads keeps that from
  happening only if the harness loads them from there: Node's builds name no RPATH, so the toolchain's build would have
  to set one.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep the host, and give every sandbox the host name the result was made under | Every sandbox would go by one name, so the record would say each agent ran where its result was made, which it did not; and not every container runtime gives a container a name of its own to set |
| Write the sandbox's host name into the result the training system places | It would say the checks ran where they did not |
| Make the result in every sandbox | A check runs each harness some thirty times (RFC 0044), minutes before each rollout, for a result that changes only with the build |
| Pin the image too | Each task brings its own image, so a result per image is a result per sandbox, made minutes before each rollout |
| Drop the host from the pin, or pin the installation always in its place | A root a container shares with its host, or one copied to another machine, would carry results that speak for whatever runs there at the same versions or paths, which RFC 0044 refused, as Codex's shell ran on one host and not on another |
| A digest of the installation's files | Reading hundreds of megabytes at every launch (EST), where a result kept inside its build already goes with what it was made from |
| Results shipped with the SDK or by CI | It vouches from another machine for a binary the user may not run (RFC 0044); here the installation is the one that runs, and the training system that made the result is the one that runs it |
| A setting that names a result file, or a folder of results apart from the root | A second place to look for one thing, where a file in the root already is that |
| Doing nothing | Every agent in a sandbox reads `unverified`, so no trainable session starts there |

## Consequences

- A training system that runs a harness from a read-only toolchain makes its result once for each build, keeps it there,
  places it in each fresh root, and its agents earn their levels there, trainable among them.
- A result made from a writable installation speaks where it did, for an agent whose harness runs from no installation.
  A result kept before this parses as one, and speaks again once made with this SDK, as after any upgrade.
- A root copied to another machine carries the results of its read-only installations with it, which speak there where
  the same paths are read-only, each saying the host it was made on. On a system whose own `/usr` is read-only, that
  takes in a harness installed there.
- A harness installed in a read-only image names its installation too, and its result speaks for any sandbox that runs
  it from the same paths; keeping one image's result from speaking for another's is the training system's, as for a
  build.
- What a level rests on can now be a check made on another host. The record says which, and a reader reaches the result
  from the start, as now.
- Unknown: whether a harness from one toolchain behaves alike across the images of a training system's tasks, beyond
  what its start shows, as nothing has run it so.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 the pin | `Conformance.installation`, `Profile.installation`, `_pin`, `check_driver`, the host's profile and `check`'s; architecture section 9.3 and the levels row of STATUS | The unit tests in section 4 but those of M2 | |
| M2 the words | The reason a level earned elsewhere gives, the reason an agent that runs from an installation reads when no result speaks for it, and `doctor`'s; pi's refusal of a pi that cannot start; the training guide's advice for a session in a sandbox | `test_a_level_earned_from_another_host_says_where_its_result_was_made`, `test_an_agent_that_runs_from_an_installation_is_told_to_make_its_result_there`, `test_a_pi_that_cannot_start_is_refused_with_what_it_printed`, and a test of `doctor`'s words in `tests/unit/cli/test_machine.py` | |
| M3 a real harness | A result made under one host name speaking under another | `test_a_result_made_under_one_host_name_speaks_under_another_from_the_same_installation`, slow, on pi and OpenHands | |

## Open questions

1. **What marks an installation that can stand in for a host.** Open. Today: each path read-only where the runtime
   looks, when it looks. Content cannot be checked at a launch's cost, so it is the training system's to keep, by a
   result kept inside its build, as a version is the harness's. M1 was built with this default, and no decision is
   recorded.
2. **Checks that rest on the machine.** Open. Today: a result that speaks by its installation speaks for every level,
   with a reason that says where it was made. The alternative is to leave `operational`'s shell checks unverified when
   the result was made on another host, which names a list of checks that rest on the machine. M2 was built with this
   default, and no decision is recorded.

## Evidence

- Code at `e73a221`, as cited above: the pin (`drivers/levels.py:122-145`, `179-204`), where `check_driver` sets the
  host (`testing/conformance.py:803`), and where a kept result is read (`runtime/opening.py:81-93`,
  `runtime/host.py:1076-1085`) and written (`runtime/paths.py:135-155`).
- [`tests/unit/drivers/test_levels.py`](../../tests/unit/drivers/test_levels.py),
  `test_a_result_pinned_elsewhere_says_nothing_of_this_agent`: a result made on another host speaks for nothing here,
  which stands for a writable installation.
- [`tests/integration/test_contract.py`](../../tests/integration/test_contract.py),
  `test_an_isolated_sealed_agent_reaches_its_gateway_on_loopback`: a result written into a fresh root with
  `write_conformance` before the session starts earns trainable there, on the same host.
- Platoon's own code at `411cfe55ea45`: `platoon@411cfe55ea45:platoon/harness/builtin/specs/openhands.toml` runs one
  OpenHands agent from a read-only toolchain inside the task sandbox, a toolchain whose lock,
  `platoon/harness/builtin/specs/openhands-1.54.0.txt`, holds OpenHands' SDK and tools and their closure, and not this
  SDK; `platoon/harness/toolchains.py` builds a toolchain at one path for each name, which only a forced build
  replaces, and binds a copy of it on the node's own disk read-only at that path, which `platoon/sandbox/docker.py`
  mounts with Docker's `:ro`, passing no host name; and `platoon/harness/builtin/platoon_harness/bridge.py` starts a
  team's session in the rollout worker, on the host.
- The official linux-x64 and linux-arm64 builds of Node 26.13.0, read with `readelf`: beside glibc's own libraries,
  which each needs at 2.28 or newer, each loads `libstdc++.so.6`, at `GLIBCXX_3.4.21` and `CXXABI_1.3.11` or newer,
  `libgcc_s.so.1` and `libatomic.so.1`, and names no RPATH or RUNPATH. Other versions were not read. A probe the
  repository does not hold ran the linux-x64 build in `python:3.12-slim`, Debian 13, which holds no `libatomic.so.1`:
  it exited 127, naming that library, as `pi --version` did, and with the library added, Node, pi 1.5.0 and pi's check
  ran there.
- The same probe ran platoon-harness 0.1.0 under SingularityCE 4.4.1, with `--containall`. The container shared the
  host's UTS namespace and went by the host's name, on the host's network and on none. `check_harness('openhands')`
  passed in a sandbox, from a toolchain bound read-only, and a result made in one sandbox spoke in another on the same
  host, by the host it names, as 0.1.0 pins a result, while one that named another host refused every start.
- A second probe, which the repository does not hold either, ran this SDK under SingularityCE 4.4.1, from that
  toolchain with this SDK in place of 0.1.0, bound read-only, and for pi with Node and its packages bound read-only
  beside it. OpenHands' and pi's results, each made with `check_harness` in one sandbox, named their installations,
  and, each renamed to another host as one made there would be, earned `trainable` in a second sandbox, whose start
  recorded the same installation and where its result was made, as `bwrap` shows in the slow test of section 4.
