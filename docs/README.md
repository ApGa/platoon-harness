# platoon-harness documentation

New here? [Install](getting-started/install.md), then run [your first session](getting-started/first-session.md).

## Getting started

- [Install](getting-started/install.md): what you need, the install, OpenHands, and what `doctor` says.
- [Concepts](getting-started/concepts.md): the nine words, a session on disk, and one session traced.
- [Your first session](getting-started/first-session.md): a team on a model you name, run, read back and opened.

## Examples

[The examples](../examples/README.md) say what each needs and what a live run took. Each is a team at work on a copy of
[the sample project](../examples/sample-project/README.md), on a model you name.

- [A mixed team](../examples/mixed-team/README.md): a pi lead and an OpenHands worker fixing a bug, run, watched, steered
  and read back.
- [A headless script](../examples/sdk-script/README.md): a team run from Python on the SDK alone.
- [A worktree team with a merge queue](../examples/worktree-merge-queue/README.md): workers on branches of their own,
  handing them to one merger.
- [A review and verification team](../examples/review-verification/README.md): a fix reviewed, and verified with your
  test as evidence.
- [A GitSwarm population](../examples/git-swarm/README.md): workers in worktrees of their own, each with one outcome.
- [A sample extension package](../examples/extension-package/README.md): an op, a view and a preset of your own.

## How-to guides

- [The terminal UI](how-to/tui.md): open, watch and steer sessions in a terminal.
- [The browser](how-to/web.md): your sessions and a session's chats in a browser, and the links to share them.
- [Edit a team](how-to/edit-a-team.md): the project's team as fields, in the terminal or the browser.
- [Replay a session](how-to/replay.md): a session's record played back, forward and back, acting on nothing.
- [Run headless](how-to/headless.md): sessions from a terminal or CI.
- [Topologies](how-to/topologies.md): who may reach whom, with a worked team for each preset.
- [Workspaces](how-to/workspaces.md): where each agent works, and what becomes of its work.
- [Provenance](how-to/provenance.md): what reached each agent, what it rests on, and whose work an outcome reaches.
- [Troubleshooting](how-to/troubleshooting.md): what a common refusal says, why, and what to do.

## Extending

- [Extending platoon-harness](extending/index.md): every way in, how your code is found, and the rules it keeps.
- [Write an extension](extending/extensions.md): the sample extension package, step by step.
- [Drivers](extending/drivers.md): how a harness is driven, and how to write a driver and prove it works.
- [Training on sessions](extending/training.md): the contract a training system builds on.

## Reference

- [Command line](reference/cli.md): every command, the exit codes and the JSONL shape.
- [Team file](reference/team-file.md): every table and key of a team file, and every preset.
- [Python API](reference/python.md): every public name of the SDK, with its signature and docstring; experimental names
  are marked.
- [Compatibility](reference/compatibility.md): each upstream, how it is used, and what is known about it.
- [Scale](reference/scale.md): 100 agents and 100,000 events, what each measurement came to, and on what hardware.
- [Status](STATUS.md): what is implemented, tested and experimental.
- [Security](security.md): what is protected and what is not, credentials, retention and redaction.

## Design

- [Architecture](architecture.md): the design.
- [RFCs](rfcs/README.md): why each decision was made, and how to propose a change.

## Contributing

[CONTRIBUTING.md](../CONTRIBUTING.md) says how to set up a checkout, run the tests and propose a change, and
[AGENTS.md](../AGENTS.md) holds the rules every change follows, human or agent.
