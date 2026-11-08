"""`python -m platoon_harness_cli.reference > docs/reference/cli.md`: the command line's reference, made from its
definitions. With `python`, `> docs/reference/python.md`, run at the checkout's root: the Python API's, made from
`tests/public_api.txt` and the docstrings."""

import ast
import importlib
import importlib.util
import inspect
import io
import re
import sys
import textwrap
import tokenize
from dataclasses import dataclass
from pathlib import Path

from platoon_harness import Ending
from platoon_harness.kernel import Event

from .exits import ENDINGS, SHARED
from .main import build
from .output import FORMAT


def reference() -> str:
    """The reference: exit codes, the JSONL shape and every command, from what defines them."""
    endings = "\n".join(f"| `{reason}` | {code} |" for reason, code in ENDINGS.items())
    shared = "\n".join(f"| {code} | {when} |" for code, when in SHARED.items())
    envelope = ", ".join(f"`{name}`" for name in Event.model_fields)
    ending = ", ".join(f"`{name}`" for name in ("type", *Ending.model_fields, "code"))
    return f"""# Command line reference

<!-- Made from the command definitions by `uv run python -m platoon_harness_cli.reference > docs/reference/cli.md`.
Do not edit: change the definitions, and make it again. A test holds it to them. -->

Each command under Ops on a session takes the session's name first, and runs one op there as a guest, by the name and
with the arguments an agent's `ph` uses: `ph task.claim --queue tasks` is `platoon-harness task claim SESSION --queue
tasks`. A read runs on a view credential, which writes nothing, and anything else on a control credential. `wait` and
the ops on a wait have no command, as a wait parks a turn and a person has none: `events --follow` watches a session,
and a script has `Session.wait`. The [headless quickstart](../how-to/headless.md) shows them together.

An installed extension's op is a command too, made in the same way under the extension's name: `ph ballot.cast --agent
@author --choice yes`, the op of [the sample extension package](../../examples/extension-package/README.md), is
`platoon-harness ballot cast SESSION --agent @author --choice yes`. `--help` lists each installed extension under
Installed extensions, read from metadata with none imported, and a command line imports only the one it names first. Its
op runs only on a session whose team names that extension, and is refused, with exit 1, on any other: before anything is
asked of it, saying so, where the session's manifest shows its team does not name it, and by its runtime where its team
names an extension by `module:attr`, which the manifest cannot resolve. This reference is made from the command line's
own commands, so it lists no extension's. An installed extension named as one of them has no commands, and nor has one
named as an extension every session holds, such as `lease`, which the kernel refuses in any session: discovery refuses
either from metadata, before any import, and says why on stderr.

## Exit codes

`run` and `session resume` exit with how their session ended, as architecture section 12 lists it:

| Reason | Code |
|---|---|
{endings}

Every command shares these:

| Code | When |
|---|---|
{shared}

## JSONL

With `--json`, `run`, `session resume` and `events` print one JSON object per line on stdout, and nothing else reaches
it: logs, notes and refusals go to stderr. Each line has `format`, which is {FORMAT}, and holds ASCII alone, anything
else escaped. `run` and `session resume` print each event the runtime they own journals, from its `runtime.started`,
and `events` each event past `--after`.

An event's line is its envelope as the journal holds it, as architecture section 5.3 says, with these keys:

{envelope}

Its `v` is its payload's version. Its `seq` is a cursor: pass the last one as `--after` to go on exactly where you
stopped. The last line of `run` and `session resume` is the ending, with these keys, where `type` is `ending` and
`code` is what the command exits with. One stopped while its runtime starts prints its ending alone:

{ending}

Without `--json` each event is one readable line, which is no contract. JSONL is the one versioned shape here: what
another command prints with `--json`, and what an op's command prints, is that op's result or that command's report,
whose shape follows it, with no `format`.

{build().generate_docs(heading_level=2)}"""


LISTED = Path("tests", "public_api.txt")
STATUS = Path("docs", "STATUS.md")
EXPERIMENTAL = {
    "platoon_harness.bwrap": "`bwrap`, the SDK's own extension, under the `platoon_harness.extensions` group",
    "platoon_harness.credit.propagate": (
        "`platoon_harness.credit.propagate`, `propagate@4`, experimental and heuristic, in the one producer signature, "
        "at version 4 in place of 1 and 2, with version 3 kept for a run recorded on it"
    ),
    "platoon_harness.drivers.claude": "The `claude` driver",
    "platoon_harness.drivers.codex": "The `codex` driver",
    "platoon_harness.drivers.openhands": "OpenHands as a wire worker",
    "platoon_harness.drivers.pi": "The `pi` driver",
    "platoon_harness.drivers.process.Process": "`Process` on macOS",
    "platoon_harness.kernel.filesystem": "macOS filesystem detection and `F_FULLFSYNC`",
    "platoon_harness.runtime.isolation": "`isolated`",
}
"""Each public module or name that a row of STATUS on the SDK calls experimental, by that row's lead, the words before
its first colon, which its mark quotes."""
_CELL = re.compile(r"(?<!\\)\|")
_CODE = re.compile(r"(`[^`]*`)")


def _leads(status: str) -> set[str]:
    """The lead of each row of STATUS's capabilities, under a heading that names a module of the SDK, whose state or
    capability says experimental."""
    leads, sdk = set(), False
    for line in status.partition("\n## Capabilities\n")[2].splitlines():
        if line.startswith("### "):
            sdk = "`platoon_harness`" in line or "`platoon_harness." in line
        elif sdk and line.startswith("| ") and not line.startswith(("| Capability |", "|---")):
            capability, state, *_ = (cell.strip() for cell in _CELL.split(line)[1:-1])
            if "experimental" in f"{capability} {state}":
                leads.add(capability.partition(": ")[0])
    return leads


def _public(listed: str) -> dict[str, list[str]]:
    """Each module the list names, and its names, in the list's order: a line's module is the shortest prefix whose
    `__all__` holds the part after it."""
    modules: dict[str, list[str]] = {}
    for line in listed.split():
        parts = line.partition("(")[0].partition("[")[0].split(".")
        for cut in range(1, len(parts)):
            module = importlib.import_module(".".join(parts[:cut]))
            if parts[cut] in getattr(module, "__all__", ()):
                names = modules.setdefault(module.__name__, [])
                names += [] if parts[cut] in names else [parts[cut]]
                break
        else:
            raise ValueError(f"{line}: no module's `__all__` holds it")
    return dict(sorted(modules.items()))


@dataclass(frozen=True)
class _Definition:
    """Where a public name is defined: each module and name it is imported through, from the module that lists it, the
    source of the last, and the statement there that defines it, with the statement after it, its docstring where that
    is a string."""

    through: tuple[str, ...]
    source: str
    node: ast.stmt
    after: ast.stmt | None


def _defines(node: ast.stmt, name: str) -> bool:
    match node:
        case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
            return node.name == name
        case ast.Assign(targets=targets):
            return any(isinstance(target, ast.Name) and target.id == name for target in targets)
        case ast.AnnAssign(target=ast.Name(id=found)) | ast.TypeAlias(name=ast.Name(id=found)):
            return found == name
    return False


def _definition(module: str, name: str) -> _Definition:
    """Where `module`'s `name` is defined, followed through each `from ... import` the sources show."""
    through = [f"{module}.{name}"]
    while True:
        here = importlib.import_module(module)
        source = inspect.getsource(here)
        body = ast.parse(source).body
        for index, node in enumerate(body):
            if _defines(node, name):
                return _Definition(tuple(through), source, node, body[index + 1] if index + 1 < len(body) else None)
        imports = [
            (node, alias)
            for node in body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if (alias.asname or alias.name) == name
        ]
        if len(imports) != 1:
            raise ValueError(f"{through[0]}: {module} neither defines nor imports it once")
        [(node, alias)] = imports
        module = importlib.util.resolve_name("." * node.level + (node.module or ""), here.__package__ or "")
        name = alias.name
        through.append(f"{module}.{name}")


def _docstring(definition: _Definition) -> str | None:
    match definition.node, definition.after:
        case (ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef()) as node, _:
            return ast.get_docstring(node)
        case _, ast.Expr(value=ast.Constant(value=str() as text)):
            return inspect.cleandoc(text)
    return None


def _uncommented(text: str) -> str:
    """Python source without its comments, dedented, each line's end trimmed and no line left empty at its end."""
    lines = text.splitlines()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            row, column = token.start
            lines[row - 1] = lines[row - 1][:column]
    return textwrap.dedent("\n".join(line.rstrip() for line in lines)).strip("\n")


def _header(source: str, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    """A function's or a class's decorators and the line that declares it, up to its colon, as its source has them."""
    lines = source.splitlines()
    first = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
    body = node.body[0]
    before = lines[body.lineno - 1].encode()[: body.col_offset].decode()
    return _uncommented("\n".join([*lines[first - 1 : body.lineno - 1], before]))


def _attribute(node: ast.stmt) -> bool:
    """Whether a statement in a class's body gives it an attribute, annotated or assigned, whose name has no leading
    underscore."""
    match node:
        case ast.AnnAssign(target=ast.Name(id=name)):
            return not name.startswith("_")
        case ast.Assign(targets=targets):
            return all(isinstance(target, ast.Name) and not target.id.startswith("_") for target in targets)
    return False


def _stub(source: str, node: ast.stmt) -> str:
    """A statement as a stub declares it, in its source's own words: a function with no body, a class with its
    attributes and its `__init__`, and anything else whole."""
    match node:
        case ast.FunctionDef() | ast.AsyncFunctionDef():
            return f"{_header(source, node)} ..."
        case ast.ClassDef():
            kept = [
                _stub(source, item) if isinstance(item, ast.FunctionDef) else _segment(source, item)
                for item in node.body
                if _attribute(item) or (isinstance(item, ast.FunctionDef) and item.name == "__init__")
            ]
            members = textwrap.indent("\n".join(kept), "    ")
            return f"{_header(source, node)}\n{members}" if kept else f"{_header(source, node)} ..."
    return _segment(source, node)


def _segment(source: str, node: ast.stmt) -> str:
    return _uncommented(ast.get_source_segment(source, node, padded=True) or "")


def _methods(node: ast.stmt) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """A class's own methods whose names have no leading underscore."""
    if not isinstance(node, ast.ClassDef):
        return []
    return [
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and not item.name.startswith("_")
    ]


def _prose(text: str) -> str:
    """A docstring as Markdown, each `<` outside code an entity, so that none reads as a tag."""
    return "".join(part if part.startswith("`") else part.replace("<", "&lt;") for part in _CODE.split(text))


def _anchors(titles: list[str]) -> list[str]:
    """The anchor GitHub gives each heading, in the page's order, a repeated one numbered by the headings before it."""
    seen: dict[str, int] = {}
    found = []
    for title in titles:
        slug = re.sub(r"[^\w\- ]", "", title.replace("`", "").strip().lower()).replace(" ", "-")
        found.append(f"{slug}-{seen[slug]}" if slug in seen else slug)
        seen[slug] = seen.get(slug, 0) + 1
    return found


def python_reference(root: Path) -> str:
    """The Python API's reference, made from the list of public names and the docstrings of the checkout at `root`,
    marking what its STATUS calls experimental."""
    modules = _public((root / LISTED).read_text())
    named = [f"{module}.{name}" for module, names in modules.items() for name in names]
    leads = _leads((root / STATUS).read_text())
    if stray := sorted(set(EXPERIMENTAL) - set(modules) - set(named)):
        raise ValueError(f"EXPERIMENTAL marks what the list does not name: {', '.join(stray)}")
    if stale := sorted(set(EXPERIMENTAL.values()) - leads):
        raise ValueError(f"STATUS no longer calls these experimental, as EXPERIMENTAL says: {'; '.join(stale)}")
    if unmarked := sorted(leads - set(EXPERIMENTAL.values())):
        raise ValueError(f"STATUS calls these experimental, and EXPERIMENTAL marks none: {'; '.join(unmarked)}")
    definitions = {dotted: _definition(*dotted.rsplit(".", 1)) for dotted in named}
    homes = {
        dotted: next((step for step in reversed(found.through[1:]) if step in definitions), None)
        for dotted, found in definitions.items()
    }
    headings = ["Contents"]
    for module, names in modules.items():
        headings += [module, *(f"{module}.{name}" for name in names)]
    anchors = dict(zip(headings, _anchors(headings), strict=True))

    def mark(dotted: str) -> list[str]:
        return [f"**Experimental.** [STATUS](../STATUS.md): {EXPERIMENTAL[dotted]}."] if dotted in EXPERIMENTAL else []

    def entry(dotted: str) -> list[str]:
        if (home := homes[dotted]) is not None:
            return [*mark(dotted), f"Imported from [`{home}`](#{anchors[home]})."]
        found = definitions[dotted]
        lines = [*mark(dotted), f"```python\n{_stub(found.source, found.node)}\n```"]
        lines += [_prose(said)] if (said := _docstring(found)) else []
        for method in _methods(found.node):
            lines += [f"**`{method.name}`**", f"```python\n{_stub(found.source, method)}\n```"]
            lines += [_prose(said)] if (said := ast.get_docstring(method)) else []
        return lines

    contents = "\n".join(f"- [`{module}`](#{anchors[module]})" for module in modules)
    sections = []
    for module, names in modules.items():
        said = inspect.getdoc(importlib.import_module(module))
        sections += [f"## `{module}`", *mark(module), *([_prose(said)] if said else [])]
        for name in names:
            sections += [f"### `{module}.{name}`", *entry(f"{module}.{name}")]
    body = "\n\n".join(sections)
    return f"""# Python API reference

<!-- Made from `tests/public_api.txt` and the docstrings by
`uv run python -m platoon_harness_cli.reference python > docs/reference/python.md`. Do not edit: change the code or the
list, and make it again. A test holds it to them. -->

Every name `tests/public_api.txt` lists, under the module whose `__all__` holds it: the SDK's, `platoon_harness` and
the modules beneath it, and the ACP extension's, `platoon_harness_acp`.

By default, pending the owner's ruling, the public API is each name `tests/public_api.txt` lists, and each attribute and
method without a leading underscore that a class it lists defines, of which the list records only some, and nothing
else is, whatever its spelling. 0.1.0 promises it under the policy below 1.0 that [CHANGELOG](../../CHANGELOG.md)
states, so a minor release may change any of it and a patch release only fixes bugs, and there is no experimental
namespace.

Each name is shown as a stub declares it, in its source's own words without comments, then its docstring: a function by
its signature, a class by its attributes whose names have no leading underscore and its `__init__`, then each method of
its own whose name has no leading underscore, and anything else by its assignment. A name that a module imports from
another that lists it links there.

A module or name marked **Experimental** is one that a row of [STATUS](../STATUS.md) calls experimental, by its state,
which says it works but rests on an unstable upstream surface or lacks coverage, or in its own words, whatever its
state. The mark quotes the start of the row, so it says which.

## Contents

{contents}

{body}
"""


if __name__ == "__main__":
    match sys.argv[1:]:
        case []:
            sys.stdout.write(reference())
        case ["python"]:
            sys.stdout.write(python_reference(Path()))
        case _:
            sys.exit("usage: python -m platoon_harness_cli.reference [python]")
