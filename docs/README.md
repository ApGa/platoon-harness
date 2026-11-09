# platoon-harness documentation

This page is the table of contents. New here? [Install](getting-started/install.md) from a checkout, then run
[your first session](getting-started/first-session.md), which starts with
[the mixed team](../examples/mixed-team/README.md) on a model you name.

## Getting started

- [Install](getting-started/install.md): what you need, installing from a checkout, OpenHands, and what `doctor` says.
- [Concepts](getting-started/concepts.md): what platoon-harness is and is not, a session on disk, and one session traced.
- [Your first session](getting-started/first-session.md): a team on your model, read back and opened, then a team of
  your own.
- [The quickstart](../README.md#quickstart): the first commands, on one page.
- [Changelog](../CHANGELOG.md): what changed.

## Tutorials

Each example has a README that says what it does and how to run it. Each team runs on pi and OpenHands, on a model you
name at any endpoint that speaks OpenAI's Chat Completions, and works on a copy of
[the sample project](../examples/sample-project/README.md), a small Python package with its own tests, defects and
feature requests.

- [A mixed team](../examples/mixed-team/README.md): a pi lead and an OpenHands worker in one session fixing a bug, run,
  watched, steered and read back.
- [A headless script](../examples/sdk-script/README.md): a team run from Python on the SDK alone, two OpenHands agents
  each fixing an issue on a branch of its own, waited on and read back.
- [A worktree team with a merge queue](../examples/worktree-merge-queue/README.md): workers fixing issues on branches of
  their own and handing them to one merger through a queue, a conflict reaching its worker as its task's result.
- [A review and verification team](../examples/review-verification/README.md): an author's fix read by a reviewer and
  checked by a verifier that can run nothing, with your test of it as evidence.
- [A GitSwarm population](../examples/git-swarm/README.md): workers in worktrees of their own on one feature, started by
  a script that owns the session and gives each one outcome, among which you choose.
- [A sample extension package](../examples/extension-package/README.md): an op, a view and a preset in a package of
  your own, installed beside platoon-harness, named by a team and reached from every surface with no core edit.

## How-to guides

- [The terminal UI](how-to/tui.md): what `platoon-harness` opens on a terminal, its screens and its keys.
- [The browser](how-to/web.md): `platoon-harness web`, a page of your sessions, and `web SESSION`, SwarmChat's page over one
  session's journal.
- [Edit a team in the terminal or the browser](how-to/edit-a-team.md): the project's team as fields, each problem at its
  field, its diff, then saved in place and started.
- [Replay a session](how-to/replay.md): a session's record played back in the terminal or the browser, at its pace or
  faster, forward and back, acting on nothing.
- [Headless quickstart](how-to/headless.md): from a terminal or CI, with harnesses you already use and their own logins.
- [Topologies](how-to/topologies.md): teams and topologies, with a worked example per preset.
- [Workspaces](how-to/workspaces.md): where each agent works, a worktree of its own among them, and what becomes of it.
- [Provenance](how-to/provenance.md): what reached each agent, what it rests on, whose work an outcome reaches, and
  credit beside the journal.
- [Troubleshooting](how-to/troubleshooting.md): what a common refusal says, why, and what to do.

## Extending

- [Extending platoon-harness](extending/index.md): every way to extend it, how it finds your code, and the rules your
  code keeps.
- [Write an extension](extending/extensions.md): the sample extension package, step by step, from an empty folder to a
  package checked and ready to publish.
- [Drivers](extending/drivers.md): how a harness is driven, and how to write a driver, in Python or any other language,
  and prove it works.
- [Training on sessions](extending/training.md): the one contract a training system builds on, what the SDK owns and
  what the training system owns.

## Reference

- [Command line](reference/cli.md): every command, the exit codes and the JSONL shape, made from the command
  definitions.
- [Team file](reference/team-file.md): every table and key of a team file, with its type and default, and every preset,
  made from the schema.
- [Python API](reference/python.md): every public name of the SDK and the ACP extension, with its signature and
  docstring, and what STATUS calls experimental marked, made from `tests/public_api.txt` and the docstrings.
- [Compatibility](reference/compatibility.md): what each upstream is, how we use it, and what is known about it.
- [Scale](reference/scale.md): 100 agents and 100,000 events on the real stack, what each measurement came to, on what
  hardware, and the budget a slow test holds it to.
- [Status](STATUS.md): what is implemented, what is tested and how, and what is planned.
- [Security](security.md): what is protected and what is not, credentials, how long a session keeps what it records, and
  what is redacted.

## Architecture and RFCs

- [Architecture](architecture.md): the design of record.
- [RFCs](rfcs/README.md): why each decision was made, what else was on the table, and
  [how to propose a change](rfcs/README.md#how-to-propose-a-change).
- [RFC template](rfcs/0000-template.md): the sections every new RFC fills in.

## Background

- [Research](research/README.md): the Milestone 0 research and the spikes after it, dated;
  [compatibility](reference/compatibility.md) is current.
- [Product brief](spec/BRIEF.md): the project owner's brief, reproduced verbatim.

## Contributing

[CONTRIBUTING.md](../CONTRIBUTING.md) says how to set up a checkout, run the tests and propose a change.
[AGENTS.md](../AGENTS.md) holds the rules for changing this repository, human or agent. Some changes start as an RFC:
see [when to write an RFC](rfcs/README.md#when-to-write-an-rfc) and
[how to propose a change](rfcs/README.md#how-to-propose-a-change).
