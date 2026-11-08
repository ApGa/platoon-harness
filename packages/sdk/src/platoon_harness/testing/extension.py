"""check_extension: named checks that an extension keeps the contract a core primitive keeps."""

import ast
import inspect
import sqlite3
from collections.abc import Awaitable, Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from platoon_harness import kernel as kernel_package
from platoon_harness.drivers.levels import Check, Checks
from platoon_harness.kernel import Extension, Kernel, ManualClock, Op, Refused
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.tools.surface import OP_NAMED
from platoon_harness.topology import preset_name

_JOURNAL = "journal.sqlite"

Scenario = Callable[[Kernel], Awaitable[Any]]

__all__ = ["ExtensionChecks", "Scenario", "check_extension", "private_reaches"]


class ExtensionChecks(Checks):
    """What `check_extension` found, and `unchecked`: each part the extension declares that no check runs, its
    daemons, its presets and its isolation, saying what that leaves unknown, so a pass never reads as more than the
    checks ran."""

    unchecked: tuple[str, ...]

    def __str__(self) -> str:
        return "\n".join((super().__str__(), *(f"unchecked {part}" for part in self.unchecked)))


def _dump(folder: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every view's rows, read outside the kernel."""
    db = sqlite3.connect(folder / _JOURNAL)
    try:
        names = db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name GLOB 'v_*' ORDER BY name")
        tables = [name for (name,) in names if name != "v_folds"]
        return {table: sorted(db.execute(f'SELECT * FROM "{table}"'), key=repr) for table in tables}
    finally:
        db.close()


def private_reaches(tree: ast.AST) -> list[str]:
    """Underscored names reached on anything but `self` or `cls`."""
    return [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr.startswith("_")
        and not (node.attr.startswith("__") and node.attr.endswith("__"))
        and not (isinstance(node.value, ast.Name) and node.value.id in ("self", "cls"))
    ]


def _sources(extension: Extension) -> set[str]:
    """The files an extension's code lives in."""
    parts: list[Any] = [
        *(operation.fn for operation in extension.ops),
        *extension.views,
        *(daemon.run for daemon in extension.daemons),
        *extension.presets,
    ]
    return {source for part in parts if (source := inspect.getsourcefile(part)) is not None}


def _private_uses(source: str) -> Iterator[str]:
    tree = ast.parse(Path(source).read_text())
    yield from (f"{Path(source).name} reaches {name}" for name in private_reaches(tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("platoon_harness.kernel."):
                    yield f"{Path(source).name} reaches into {alias.name}"
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("platoon_harness.kernel"):
            if node.module != "platoon_harness.kernel":
                yield f"{Path(source).name} reaches into {node.module}"
            for alias in node.names:
                if alias.name not in kernel_package.__all__:
                    yield f"{Path(source).name} imports {alias.name}, which the kernel does not publish"


def _tool_problems(tool: Op, loaded: Iterable[str]) -> Iterator[str]:
    schema = tool.input.model_json_schema()
    if schema.get("additionalProperties") is not False:
        yield f"{tool.name} lets undeclared arguments through"
    bare = [name for name, field in schema.get("properties", {}).items() if not field.get("description")]
    if bare:
        yield f"{tool.name} does not describe {', '.join(bare)}"


def _description_problems(tool: Op, loaded: Iterable[str]) -> Iterator[str]:
    text = tool.fn.__doc__ or ""
    if "Refused" not in text:
        yield f"{tool.name} does not say what a refusal means"
    for name in OP_NAMED.findall(text):
        if "." in name and name not in loaded:
            yield f"{tool.name} names {name}, which is not an op"


def _unchecked(extension: Extension) -> Iterator[str]:
    """Each part of `extension` that no check runs, and what that leaves unknown."""
    for daemon in extension.daemons:
        yield f"daemon {daemon.name}: no check runs it, so nothing here says what it does or which effects it performs"
    for preset in extension.presets:
        yield f"preset {preset_name(preset)}: no check runs it, so nothing here says the topology it returns is valid"
    if extension.isolation is not None:
        yield f"isolation {type(extension.isolation).__name__}: no check runs it, so nothing here says it confines"


def _verdict(name: str, problems: Iterable[str]) -> Check:
    found = list(problems)
    return Check(name=name, state="failed", reason="; ".join(found)) if found else Check(name=name, state="passed")


async def check_extension(extension: Extension, *, folder: Path, scenario: Scenario | None = None) -> ExtensionChecks:
    """Load an extension beside the primitives and report every problem at once, and each part no check runs.
    `scenario` runs some of it on a live kernel, so that its views can be compared with a rebuild. Without one that
    check is skipped, which is no pass."""
    tools = [operation for operation in extension.ops if operation.tool]
    unchecked = tuple(_unchecked(extension))
    try:
        kernel = Kernel.open(folder, clock=ManualClock(1000.0), extensions=(*PRIMITIVES, extension))
    except Refused as refused:
        reason = str(refused.refusal.detail)
        names = Check(name="names", state="failed" if refused.refusal.code == "conflict" else "passed", reason=reason)
        law = Check(name="naming_law", state="failed" if refused.refusal.code == "invalid" else "passed", reason=reason)
        return ExtensionChecks(checks=(names, law), unchecked=unchecked)
    checks = [Check(name="names", state="passed"), Check(name="naming_law", state="passed")]
    checks.append(_verdict("schemas", (problem for tool in tools for problem in _tool_problems(tool, kernel.ops))))
    descriptions = (problem for tool in tools for problem in _description_problems(tool, kernel.ops))
    checks.append(_verdict("descriptions", descriptions))
    private = (problem for source in sorted(_sources(extension)) for problem in _private_uses(source))
    checks.append(_verdict("public_api_only", private))
    try:
        checks.append(await _rebuild(kernel, folder, scenario))
    finally:
        kernel.close()
    return ExtensionChecks(checks=tuple(checks), unchecked=unchecked)


async def _rebuild(kernel: Kernel, folder: Path, scenario: Scenario | None) -> Check:
    name = "rebuild_equals_live"
    if scenario is None:
        return Check(name=name, state="skipped", reason="no scenario was given, so its views hold nothing to compare")
    await scenario(kernel)
    before = _dump(folder)
    await kernel.rebuild_all()
    differing = sorted(table for table, rows in _dump(folder).items() if rows != before[table])
    return _verdict(name, (f"{table} differs after a rebuild" for table in differing))
