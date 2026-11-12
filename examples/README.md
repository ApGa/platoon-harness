# Examples

Each example is a team at work on a copy of [the sample project](sample-project/README.md), `tally`, a small Python
package with its own tests, defects and feature requests, on a model you name. Its page says what it does, how to run
it and what to expect.

| Example | What it shows | Harnesses | A live run on DeepSeek V4.1 Flash took |
|---|---|---|---|
| [A mixed team](mixed-team/README.md) | A pi lead and an OpenHands worker fix a bug through a queue, a board and messages, and the record says whose work reached the answer | pi, OpenHands | 30 model calls, in each of two runs |
| [A headless script](sdk-script/README.md) | A team run from Python on the SDK alone: two agents each fix an issue on a branch of its own | OpenHands | 29 model calls |
| [A worktree team with a merge queue](worktree-merge-queue/README.md) | Workers fix issues on branches of their own and hand them to one merger, a conflict reaching its worker as its task's result | pi, OpenHands | 74 model calls |
| [A review and verification team](review-verification/README.md) | An author's fix read by a reviewer and checked by a verifier that can run nothing, with your test of it as evidence | pi, OpenHands | 42 model calls |
| [A GitSwarm population](git-swarm/README.md) | Workers in worktrees of their own on one feature, started by a script, each with one outcome, among which you choose | pi | 64 and 80 model calls, in two runs |
| [A sample extension package](extension-package/README.md) | An op, a view and a preset in a package of your own, named by a team, with no core edit | none | no model call |

A real model chooses its own steps, so your run can take more calls or fewer. Each team's budget of turns and minutes
stops a runaway; no budget counts model calls, and one turn can make many.

## Prerequisites

Every example but the extension package needs:

- one environment, active in each shell you use, where platoon-harness is installed with its `cli` and `openhands`
  extras, and this repository cloned at the release you installed, X.Y.Z being what `platoon-harness --version` prints:

  ```console
  $ uv venv --python 3.12 examples-env
  $ source examples-env/bin/activate
  $ echo lmnr-claude-code-proxy > excludes.txt
  $ uv pip install "platoon-harness[cli,openhands]" --excludes excludes.txt
  $ platoon-harness --version
  $ git clone --branch vX.Y.Z https://github.com/ApGa/platoon-harness.git
  ```

  The environment's `python` runs a script example, and its `platoon-harness` every command, with OpenHands on its
  interpreter. [Install](../docs/getting-started/install.md#openhands) says why `excludes.txt` leaves Laminar's proxy
  out. Each page writes the clone's path as `path/to/platoon-harness`;
- for a team with pi, `pi` on your PATH, on Node 22.19 or later, which needs no login here;
- a model at an endpoint that speaks OpenAI's Chat Completions, such as OpenRouter's or any provider's OpenAI-compatible
  URL, and your key for it, in the two variables each team's auth profile names, as
  `export OPENAI_BASE_URL=https://openrouter.ai/api/v1` and `export OPENAI_API_KEY=...`;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the copy's first
  commit is yours, and `python3` 3.9 or later, which runs the sample project's tests.
