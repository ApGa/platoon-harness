# A sample extension package

**Goal:** add an op, a view and a preset to platoon-harness from a package of your own, with no core edit, installed
beside platoon-harness, where it activates nothing until a team names it.

| File | What it is |
|---|---|
| [`pyproject.toml`](pyproject.toml) | The distribution, `ballot`, its requirement on platoon-harness, and the entry point under `platoon_harness.extensions` by which a team names it |
| [`src/ballot/__init__.py`](src/ballot/__init__.py) | The extension: `ballot.cast`, the op; `Votes`, the view; `pair_review`, the preset |

Install it from a clone of this repository, beside the command line:

```console
$ uv tool install "platoon-harness[cli]" --with ./examples/extension-package
```

or into an environment where platoon-harness is installed, as `uv pip install ./examples/extension-package`. It needs no
harness, key or model. [Write an extension](../../docs/extending/extensions.md) builds it step by step, casts its vote
from each surface, checks it, and says how to publish a package of your own.
