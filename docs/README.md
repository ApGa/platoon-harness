# platoon-harness documentation

This page is the table of contents. New here? [Install](../README.md#install) from a checkout, then follow
[the quickstart](../README.md#quickstart), which starts with [the mixed team](../examples/mixed-team/README.md) on no
keys.

## Getting started

- [Install](../README.md#install) and [the quickstart](../README.md#quickstart): what you need, and the first
  commands, from a checkout.
- [Changelog](../CHANGELOG.md): what changed.

## Tutorials

Each example has a README that says what it does and how to run it.

- [A mixed team](../examples/mixed-team/README.md): a Claude Code lead and a Codex worker in one session, run, watched,
  steered and read back, with no keys too.
- [A headless script](../examples/sdk-script/README.md): a team run from Python on the SDK alone, waited on and read back,
  with no key and no model.

## How-to guides

- [The terminal UI](how-to/tui.md): what `platoon-harness` opens on a terminal, its screens and its keys.
- [The browser](how-to/web.md): `platoon-harness web SESSION`, SwarmChat's page over one session's journal.
- [Headless quickstart](how-to/headless.md): from a terminal or CI, with harnesses you already use and their own logins.
- [Topologies](how-to/topologies.md): teams and topologies, with a worked example per preset.
- [Workspaces](how-to/workspaces.md): where each agent works, a worktree of its own among them, and what becomes of it.
- [Provenance](how-to/provenance.md): what reached each agent, what it rests on, whose work an outcome reaches, and
  credit beside the journal.

## Extending

- [Drivers](extending/drivers.md): how a harness is driven, and how to write a driver, in Python or any other language,
  and prove it works.
- [Training on sessions](extending/training.md): the one contract a training system builds on, what the SDK owns and
  what the training system owns.

## Reference

- [Command line](reference/cli.md): every command, the exit codes and the JSONL shape, made from the command
  definitions.
- [Team file](reference/team-file.md): every table and key of a team file, with its type and default, and every preset,
  made from the schema.
- [Compatibility](reference/compatibility.md): what each upstream is, how we use it, and what is known about it.
- [Status](STATUS.md): what is implemented, what is tested and how, and what is planned.

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
