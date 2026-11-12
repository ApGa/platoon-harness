# Write an extension

An extension adds ops, views, daemons, presets or an isolation to platoon-harness from a package of your own, with no
core edit. This page writes one step by step: `ballot`,
[the sample extension package](../../examples/extension-package/README.md), a vote on an agent's work, the view that
holds each vote, and a preset that pairs an author with the reviewer who votes on its work.
[Extending platoon-harness](index.md) lists every other way in.

**Goal:** a package of your own that a team names, its op run from Python with no harness, checked against what a core
primitive keeps to, and ready to publish.

**Prerequisites:** a checkout of this repository, set up as
[CONTRIBUTING](../../CONTRIBUTING.md#set-up-a-development-environment) says, where each command runs through `uv run`.
Nothing here needs a harness, a key or a model.

## 1. Lay out the package

```text
extension-package/
  pyproject.toml
  src/ballot/__init__.py
```

<!-- pyproject.toml -->
```toml
# The ballot extension of architecture section 17, packaged as a third party's would be. Installed beside
# platoon-harness, it activates nothing until a team names it.

[project]
name = "ballot"
version = "0.1.0"
description = "A sample extension of platoon-harness: a vote on an agent's work, the view that holds each vote, and a preset that pairs an author with its reviewer."
requires-python = ">=3.12"
license = "MIT"
dependencies = ["platoon-harness>=0.1,<0.2"]

# The entry point's name is the name a team gives in `extensions = [...]`, and its value is the Extension, imported only
# when a team names it.
[project.entry-points."platoon_harness.extensions"]
ballot = "ballot:extension"

[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ballot"]
```

- **The entry point**, under the group `platoon_harness.extensions`, is how a team finds the extension: its name, `ballot`,
  is what a team names, and its value, `ballot:extension`, is the `Extension`, which nothing imports until a team names it.
- **The requirement on the SDK** names one minor release, as below 1.0 a minor release may change the Python API. Discovery
  reads it from metadata and refuses the extension, before importing it, on an SDK the range leaves out.

## 2. Import the kernel's names

The module, `src/ballot/__init__.py`, opens with what the extension is and what it imports:

<!-- src/ballot/__init__.py -->
```python
"""ballot: a vote on an agent's work, cast by a person or by a teammate the topology lets, and kept among that agent's
own events, so a client that shows the agent draws it by its gist. An op, the view that holds each vote, and a preset
that pairs an author with the reviewer who votes on its work."""

from typing import Annotated, Literal

from pydantic import Field

from platoon_harness.kernel import NAME, Args, Event, Extension, Grant, Principals, Refused, Txn, View, fold, op
from platoon_harness.topology import Topology
```

It reaches the kernel by the names its `__all__` publishes, as each of the SDK's own primitives does, and imports
`Topology`, which a preset returns. From outside the SDK, only its public API is yours to reach: each name
`tests/public_api.txt` lists, and each attribute and method without a leading underscore that a class it lists defines,
such as `Txn.emit` and `Session.submit`, which [the Python API reference](../reference/python.md) shows.

## 3. Declare the op's arguments

<!-- src/ballot/__init__.py -->
```python
class Cast(Args):
    agent: Annotated[str, Field(pattern=f"^@{NAME}$", description="The agent whose work it is on, as `@agent`.")]
    choice: Annotated[Literal["yes", "no"], Field(description="Yes or no.")]
```

`Args` refuses an undeclared field and coerces no type. Each field's `description` is what an agent's tool schema, the
command line's `--help` and each client's form say of it. Nothing here says who casts the vote: who calls an op comes
from the credential it calls with, as `txn.me`, and `op` refuses to define a tool whose arguments claim an identity, such
as a `caller` or a `user` field.

## 4. Write the view

<!-- src/ballot/__init__.py -->
```python
class Votes(View):
    """Each vote, by the agent whose work it is on and whoever cast it."""

    schema = """
    CREATE TABLE v_votes(
        agent TEXT NOT NULL,
        voter TEXT NOT NULL,
        choice TEXT NOT NULL,
        PRIMARY KEY (agent, voter)
    ) WITHOUT ROWID, STRICT;
    """

    @fold("ballot.voted")
    def voted(self, event: Event) -> None:
        self.db.execute(
            "INSERT INTO v_votes VALUES (?, ?, ?)", (event.data["agent"], event.actor, event.data["choice"])
        )

    def choice(self, agent: str, voter: str) -> str | None:
        """What `voter` voted on `agent`'s work, or None where it has not voted on it."""
        row = self.db.execute("SELECT choice FROM v_votes WHERE agent = ? AND voter = ?", (agent, voter)).fetchone()
        return None if row is None else row["choice"]
```

A view is a schema and the folds that fill it. Its tables are named `v_` and its name, the class's in lower case, here
`v_votes`. `@fold("ballot.voted")` runs `voted` on each `ballot.voted` event, and a fold sees its own tables and that one
event, no clock, no network and no other view, so the table made again from the journal is the table it was live. `choice`
is a query, which the op reads it through. Raising its `version` drops the view and folds it again.

## 5. Write the op

<!-- src/ballot/__init__.py -->
```python
@op("ballot.cast", on=lambda a: f"agent/{a.agent[1:]}", tool=True)
def cast(txn: Txn, a: Cast) -> dict[str, str]:
    """Cast a vote on an agent's work, kept among that agent's own events. Refused `not_found` when there is no such
    agent, and `conflict` when you have voted on its work already."""
    if txn.view(Principals).get(f"agent:{a.agent[1:]}") is None:
        raise Refused("not_found", f"no agent {a.agent}")
    if (choice := txn.view(Votes).choice(a.agent, txn.me.id)) is not None:
        raise Refused("conflict", f"you voted {choice} on {a.agent}'s work already")
    txn.emit("ballot.voted", f"agent/{a.agent[1:]}", gist=f"a vote on {a.agent}'s work: {a.choice}", data=a)
    return {"choice": a.choice}
```

- **Its name**, `ballot.cast`, is the extension's name and then a verb in the imperative, and the event it records,
  `ballot.voted`, is in the past tense.
- **`on`** names what one call acts on, the agent's own stream, `agent/<name>`, which a grant must reach for an agent to
  call it. A person and a program hold every op.
- **`tool=True`** makes it a tool, `ballot_cast` on MCP, and so a command of `ph`, for an agent whose grants reach it.
- **Its docstring** is its description wherever it is offered, and says what each refusal means.
- **Its body** is synchronous, does no I/O and runs inside one transaction. It reads `Principals`, the kernel's view of
  who is in the session, and its own `Votes`, refuses with a code and the reason, and records one event with
  `txn.emit` on the agent's stream: its `gist` is how every client draws it, and its `data` is the vote. What it returns
  is its caller's result.

What the world must do, such as a request to a server, is an effect: an op asks for one with `txn.effect`, and a daemon of
the extension does it and reports through ops ([architecture §5.4](../architecture.md#54-effects)). `ballot` needs none.

## 6. Write the preset

<!-- src/ballot/__init__.py -->
```python
def pair_review(author: str, reviewer: str) -> Topology:
    """An author and a reviewer who talk directly, bounded by hops, and the reviewer's vote on the author's work."""
    vote = Grant(who=f"role:{reviewer}", ops="ballot.cast", on=f"agent/{{role:{author}}}")
    edges = {author: [f"role:{reviewer}"], reviewer: [f"role:{author}"]}
    return Topology(edges=edges, limits={"max_hops": 8}, grants=(vote,))
```

A preset is a plain function that returns a `Topology` fragment. A team uses it as the table `[topology.pair-review]`,
named after the function with dashes for underscores, whose keys are its arguments, and it may not take the name of a
built-in preset or of a key of `[topology]`. This one lets the two roles message each other, for at most 8 hops, and
grants the reviewer `ballot.cast` on each agent of the author's role.

## 7. Name them in an extension

<!-- src/ballot/__init__.py -->
```python
extension = Extension("ballot", ops=[cast], views=[Votes], presets=[pair_review])
```

Its name is its ops' namespace, so the kernel refuses an op of it whose name begins otherwise, and a name of an op, a
tool, a view, a table or a daemon that another extension loaded beside it defines. The name is also its group of commands
on the command line, so one named as a command of the command line's own, such as `run`, gets no commands, and no session
loads one named as an extension of the SDK's own, which every session holds, such as `task` or `lease`.
[Extending](index.md#an-extensions-parts) says what each field becomes.

## 8. Install it

From the root of the checkout:

```console
$ uv pip install examples/extension-package
$ uv run platoon-harness extension list
```

`uv pip install` builds the package's wheel and installs it in the checkout's environment. `extension list` reads each
installed driver and extension from metadata alone, importing none, and names this one among them:

```text
extension  ballot       ballot 0.1.0
```

Installing activates nothing: no session loads `ballot` until its team names it. Where two installed distributions both
register an extension called `ballot`, a team that names `ballot` is refused before either is imported, and one that pins
this one by its version, `ballot@0.1.0`, loads it alone, as long as the other is of another version.

## 9. Name it in a team

A team file, `team.toml`, at the root of the checkout, names the extension and uses its preset:

<!-- team.toml -->
```toml
extensions = ["ballot"]

[roles.author]
harness = "codex"

[roles.reviewer]
harness = "claude"

[topology.pair-review]
author = "author"
reviewer = "reviewer"
```

```console
$ uv run platoon-harness team show team.toml
```

```text
author (codex) may message reviewer. reviewer (claude) may message author.
Limits: hops 8. role:reviewer may ballot.cast on agent/{role:author}. Closes when the session settles.
```

## 10. Cast a vote

A script, `vote.py`, beside `team.toml`, runs that team with a stand-in in place of each role's harness, so it needs no
harness or login, and casts a vote, then the same voter's second, then one on no agent:

<!-- vote.py -->
```python
import asyncio
from pathlib import Path

from platoon_harness import Session, load_team
from platoon_harness.testing import ScriptedDriver


def stand_in() -> ScriptedDriver:
    """A harness that does only what its script says, which is nothing."""
    return ScriptedDriver([])


async def main() -> None:
    sets = [f'roles.{role}.harness = "__main__:stand_in"' for role in ("author", "reviewer")]
    async with Session.start(load_team(Path("team.toml"), sets=sets)) as session:
        cast = await session.submit("ballot.cast", agent="@author", choice="yes")
        again = await session.submit("ballot.cast", agent="@author", choice="no")
        nobody = await session.submit("ballot.cast", agent="@nobody", choice="yes")
        votes = [event.gist async for event in session.events() if event.type == "ballot.voted"]
    print(cast.result)
    for outcome in (again, nobody):
        print(f"{outcome.refusal.code}: {outcome.refusal.detail}")
    print(votes)


asyncio.run(main())
```

```console
$ uv run python vote.py
```

```text
{'choice': 'yes'}
conflict: you voted yes on @author's work already
not_found: no agent @nobody
["a vote on @author's work: yes"]
```

`load_team` lays `sets` over the file as `--set` does on the command line, here naming each role's harness by
`module:attr`: `stand_in`, the testing kit's `ScriptedDriver`. `Session.submit` returns what the op came to, its result or
its refusal, and never raises a refusal. The vote lies on the author's stream, `agent/author`, so a client that shows the
author draws it by its gist.

The same op runs from every other surface with no code of yours:

- **An agent** whose grants reach it is shown `ballot_cast` among platoon-harness's MCP tools, and its shell runs
  `ph ballot.cast --agent @author --choice yes`.
- **The command line.** `platoon-harness ballot cast SESSION --agent @author --choice yes` imports `ballot` and nothing
  else installed, and is refused on a session whose team does not name it. `platoon-harness --help` lists `ballot` under
  Installed extensions, from metadata.
- **The terminal's palette** offers `ballot cast`, worded by the op's docstring, and runs it through a form made from its
  schema, and the page's Commands offers the same form.

Each vote is drawn by its gist, `a vote on @author's work: yes`, in the author's transcript in the terminal, and
`platoon-harness events` reads it back with its ref, `agent/author@<version>`. The page draws it in no transcript: it
shows the vote in that ref's Provenance pane, which opens where the page's address names it, `#provenance=<ref>`.

An extension's op is never asked about: the clients ask once before the command line's own ops that end an agent or the
session, erase a body, or run a commit's code as you, a list no extension adds to, so neither client asks before an op of
yours runs, whatever it does.

## 11. Check it

`check_extension`, from `platoon_harness.testing`, loads an extension beside the SDK's own primitives and holds it to what
they keep to, reporting every failure its checks find at once, and a check that could not run as a skip, saying why. A
script, `check.py`, checks `ballot`, with a scenario that casts two votes on a live kernel:

<!-- check.py -->
```python
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from ballot import extension
from platoon_harness.kernel import Kernel
from platoon_harness.testing import check_extension


async def votes(kernel: Kernel) -> None:
    """Two agents, and a vote on each one's work, cast as the runtime."""
    for agent, choice in (("author", "yes"), ("reviewer", "no")):
        added = {"id": f"agent:{agent}", "role": agent}
        for name, args in (("principal.add", added), ("ballot.cast", {"agent": f"@{agent}", "choice": choice})):
            outcome = await kernel.submit(kernel.runtime, name, args)
            assert outcome.refusal is None, outcome.refusal


async def main() -> None:
    with TemporaryDirectory() as folder:
        result = await check_extension(extension, folder=Path(folder) / "session", scenario=votes)
    print(result)


asyncio.run(main())
```

```console
$ uv run python check.py
```

```text
passed  names
passed  naming_law
passed  schemas
passed  descriptions
passed  public_api_only
passed  rebuild_equals_live
unchecked preset pair-review: no check runs it, so nothing here says the topology it returns is valid
```

In a test of your package, assert `result.failed == ()`, with `str(result)` as the message, so a failure says each check
that failed and why.

| Check | What it holds the extension to |
|---|---|
| `names` | Neither its name nor that of an op, a tool, a view, a table or a daemon of it is one the SDK's primitives take |
| `naming_law` | Each op's name is in the extension's namespace and does not read as past tense, which is as far as a machine checks the imperative, and each event a view folds is under a namespace and reads as past tense |
| `schemas` | Each tool's arguments refuse an undeclared field and describe each field |
| `descriptions` | Each tool's docstring mentions `Refused`, which is as far as a machine checks that it says what a refusal means, and each dotted name it puts in backticks is an op |
| `public_api_only` | The files that define its ops, views, daemons and presets reach into no module of the kernel's package, import from the package only the names it publishes, and reach no underscored attribute but on `self` or `cls` |
| `rebuild_equals_live` | Each view's rows, once the scenario has run on a live kernel, are the rows a rebuild from the journal makes. With no scenario, or where the kernel refuses to load the extension, it is a skip, which is no pass |

What it does not check:

- **A second fault in loading.** The kernel stops loading at the first fault, so the checks it cut short are skips.
- **Its daemons, its presets and its isolation.** It runs none, and names each in `unchecked`, so a pass never reads as more
  than ran: the SDK's `bwrap`, which is [experimental](../reference/python.md#platoon_harnessbwrap), passes with nothing
  in it saying Bubblewrap confines. `team show` and `team check` show a preset's topology.
- **Names outside the kernel.** One named as a command of the command line's own passes and gets no commands, and a preset
  that takes another preset's name or a key of `[topology]` passes and is refused when a team names the extension.
- **What an op does.** Beyond what the scenario runs and the rebuild compares, that is your test's to show.
- **Who may run an op.** No check reads a grant.
- **An op that is no tool.** `schemas` and `descriptions` read tools alone.
- **Every file of the package.** `public_api_only` reads only the files its parts are defined in.
- **The package.** Its metadata, its entry point and its requirement on the SDK are discovery's, which
  `platoon-harness extension list` shows.

## 12. Publish it

A package on an index is installed by name, so before you publish one:

- **Choose its names.** The distribution's name is yours to make unique on the index. The entry point's name is what
  teams name, and another distribution may register the same: a team that names a name two installed distributions
  register is refused, saying both, and pins one as `name@version` where their versions differ.
- **Say what it needs.** Require the minor releases of platoon-harness you have tested on, as `platoon-harness>=0.1,<0.2` does.
  Below 1.0, as [CHANGELOG](../../CHANGELOG.md) says, a minor release may change the Python API, the team file or the
  command line, and a patch release only fixes bugs.
- **Describe it.** Give `readme`, which an index shows as its description, and the project's URLs. The sample, which is
  never published, has neither.

Then, from the package's folder, build it, check what was built, and upload it:

```console
$ uv build
$ uvx twine@7.0.0 check --strict dist/*
$ uv publish
```

`uv build` writes an sdist to `dist/`, then a wheel built from it. `twine check --strict` checks their metadata, and that
the README renders as the index's description, failing on a warning too, as it does for the sample, which has no
`readme`. `uv publish` uploads `dist/` to PyPI, with a token, or from a CI workflow by trusted publishing. A person
installs it beside the command line, as `uv tool install "platoon-harness[cli]" --with <your package>`, or beside a
checkout, as step 8 does.
