# AGENTS.md

Rules for every change, human or agent. [CONTRIBUTING.md](CONTRIBUTING.md) says how to set up, test and propose a change;
[architecture.md](docs/architecture.md) §1-§3 is the design. Read the section you touch before changing the kernel or a
primitive.

## Clean room

This project is implemented from scratch. Never open, clone, install, fetch or search for any other implementation named
platoon-harness, platoon_harness, platoon-harness-sdk or platoon-harness-cli, anywhere. Not even to check whether a name is
taken. This repository and its own PyPI release are not such an implementation. Toad is AGPL-3.0: use it for interaction
ideas only, and never copy its code.

## Taste

Every change is held to very good taste. In practice:

- **Fewer concepts.** Before adding a concept, try to derive it from one that exists. Before adding a parameter, try to remove
  the need for it. One way to do each thing.
- **Names a reader would guess.** Follow the naming law in architecture §2. If a name needs a comment, change the name.
- **Semantics you can state in a sentence.** If you cannot, the design is not finished.
- **Honest about what is unknown.** Unknown is not zero, not false and not empty. Never fabricate token ids, logprobs, context
  contents, child identities or tool-to-call links. Never say "exactly once" or "mid-generation".
- **Loud failure.** Unsupported states are refused or labelled, never silently degraded. A disabled control says why.
- **No speculation.** No abstraction with one user and no second in sight. No options nobody asked for. No compatibility shims.
  Delete dead code; do not comment it out.
- **Read the neighbors.** Match the surrounding code's comment density, naming and idiom. Docstrings are short and say what a
  thing is; design history belongs in `docs/rfcs/`.

## Layers

`kernel` imports only the standard library and pydantic. `primitives`, drivers and extensions use only public kernel names. An
AST test enforces this. If a primitive needs a private call, the kernel is wrong: fix the kernel.

The SDK never imports the CLI, Textual, Platoon, Torch, Tinker or an agent implementation. The one exception is OpenHands,
platoon-harness's `openhands` extra, which only the OpenHands worker imports, in a process of its own. A boundary test
enforces this.

## Engineering conventions

- Python 3.12+, one uv project, one `uv.lock`. Run things with `uv run`.
- `ruff check`, `ruff format --check` and `ty check` pass on every change.
- Tests are CPU only with no network, use port 0 and `tmp_path`, and never sleep to wait for a condition: use `ManualClock` and
  await the event.
- Live tests are marked `live`, need `PLATOON_HARNESS_LIVE=1`, and state their budget. A skipped live test is not a passing
  integration. Say which was run.
- Public API changes update `tests/public_api.txt`. Generated docs are regenerated, not hand-edited.
- Public docs, docstrings and fixtures carry no local paths, cluster names, account details or tokens, which a test scans for,
  and no private notes or process records (rulings, milestones, run numbers, hosts), which a test scans the docs for.
- Every primitive promise in architecture §7 has a test named for it.

## Commits

Conventional Commits with no scope, in sentence case, with no final period: `feat: Add leased task queue`. The body says why. Agents
commit locally only: never push, tag or publish unless the person you work for asks; only maintainers tag or publish. Never
pass `--no-verify`.

## Status

`docs/STATUS.md` lists every capability as planned, implemented, tested, experimental or deferred. An interface, a mock, a
screenshot or a TODO does not count as implemented. Update it in the same change.
