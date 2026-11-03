"""SafeText is the one boundary for untrusted text, and no label-like widget is ever handed a bare str."""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

import platoon_harness_cli.tui as tui
from platoon_harness_cli.tui.safe import SafeText

TUI = Path(tui.__file__).parent
LABELS = {"Static", "Label", "Button", "Option", "Hit", "DiscoveryHit", "Row", "Confirm"}
"""What draws a label: Textual's widgets that read a str as markup, and ours that take a line."""
METHODS = {"update", "notify"}
ATTRIBUTES = {"border_title", "border_subtitle", "tooltip"}


@pytest.mark.parametrize(
    ("given", "shown"),
    [
        ("\x1b]0;owned\x1b\\", "\\x1b]0;owned\\x1b\\"),
        ("\x1b[2J\x1bc", "\\x1b[2J\\x1bc"),
        ("\x9b31m\x85", "\\x9b31m\\x85"),
        ("\x7f\x00\r", "\\x7f\\x00\\r"),
        ("‮evil‬⁦‏؜", "\\u202eevil\\u202c\\u2066\\u200f\\u061c"),
        ("[/x] [@click=app.quit]x[/]", "[/x] [@click=app.quit]x[/]"),
    ],
)
def test_safe_text_shows_each_control_a_terminal_would_act_on_as_its_escape(given, shown):
    assert SafeText(given).plain == shown


def test_safe_text_keeps_tabs_new_lines_and_every_script():
    kept = "a\tb\nc 中文 é 👨‍👩‍👧 🇯🇵 שלום مرحبا"

    assert SafeText(kept).plain == kept


def _name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


def _content(node: ast.expr, known: set[str]) -> bool:
    """Whether an expression is visibly Content: made by `SafeText` or `Content`, a method of Content, a name the file
    says holds it, or a choice between two of these."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in ("SafeText", "Content")
        return isinstance(func, ast.Attribute) and (_name(func.value) == "Content" or _content(func.value, known))
    if isinstance(node, ast.IfExp):
        return _content(node.body, known) and _content(node.orelse, known)
    return _name(node) in known


def _annotated(tree: ast.AST) -> Iterator[tuple[str, ast.expr]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            yield node.arg, node.annotation
        elif isinstance(node, ast.AnnAssign) and (name := _name(node.target)):
            yield name, node.annotation


def _contents(tree: ast.AST) -> set[str]:
    """The names a file says hold Content: annotated so, assigned what is visibly Content, or taken from what is."""
    known = {name for name, annotation in _annotated(tree) if "Content" in ast.unparse(annotation)}
    while True:
        found = set(known)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and _content(node.value, known):
                found |= {name for target in node.targets if (name := _name(target))}
            if isinstance(node, ast.For) and _content(node.iter, known):
                found |= {name for target in ast.walk(node.target) if (name := _name(target))}
        if found == known:
            return known
        known = found


def _named(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def violations(source: str, *, notes: bool = False) -> list[str]:
    """Each place in `source` that hands a label-like widget anything not visibly Content, or toasts by `notify` and
    not `note`."""
    tree = ast.parse(source)
    known = _contents(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (name := _named(node)) in LABELS | METHODS:
            if name == "notify" and not notes:
                found.append(f"{node.lineno}: notify, where `note` is the way")
            text = node.args[0] if node.args else None
            if text is not None and name != "notify" and not _content(text, known):
                found.append(f"{node.lineno}: {name} given {ast.unparse(text)}")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in ATTRIBUTES and not _content(node.value, known):
                    found.append(f"{node.lineno}: {target.attr} = {ast.unparse(node.value)}")
    return found


@pytest.mark.parametrize("path", sorted(TUI.glob("*.py")), ids=lambda path: path.name)
def test_a_label_like_widget_is_never_given_a_bare_str(path):
    assert violations(path.read_text(), notes=path.name == "safe.py") == []


@pytest.mark.parametrize(
    "planted",
    [
        "Static(f'{row}')",
        "label.update(name + gist)",
        "Row(event.gist.join(parts))",
        "self.notify(said)",
        "widget.border_title = 'x' + name",
        "Static(SafeText(gist).plain)",
        "Static(gist)",
        "label.update(event.gist)",
        "Row(name)",
        'Static(row["gist"])',
        "Static(SafeText(gist) if ok else gist)",
    ],
)
def test_the_lint_finds_a_bare_str(planted):
    assert violations(planted) != []


@pytest.mark.parametrize(
    "kept",
    [
        "Static(SafeText(gist))",
        "line = Content.assemble(SafeText(gist))\nRow(line)",
        "def f(said: Content):\n    label.update(said)",
        'Static(Content("\\n").join(lines))',
        "for name, about in fields:\n    Static(about)\ndef g(fields: list[tuple[str, Content]]): ...",
    ],
)
def test_the_lint_takes_what_is_visibly_content(kept):
    assert violations(kept) == []


def test_a_link_is_followed_only_to_http_and_https():
    from rich.console import Console

    from platoon_harness_cli.tui.transcript import markdown

    lines = markdown(
        "[a](https://example.org) [b](javascript:alert(1)) [c](file:///etc/passwd) [d](http://x.org)",
        80,
        Console(width=80),
    )
    links = {segment.style.link for line in lines for segment in line if segment.style and segment.style.link}

    assert links == {"https://example.org", "http://x.org"}
