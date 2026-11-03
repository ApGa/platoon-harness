"""SafeText is the one boundary for untrusted text, and no label-like widget is ever handed a bare str."""

import ast
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


def _bare(node: ast.expr) -> bool:
    """Whether an expression is a str of no Content: a literal, an f-string, a joined or formatted one, or `.plain`."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr | ast.BinOp):
        return True
    if isinstance(node, ast.Attribute):
        return node.attr == "plain"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute):
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        return name in ("str", "format", "join", "repr", "safe")
    return False


def _named(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def violations(source: str, *, notes: bool = False) -> list[str]:
    """Each place in `source` that hands a label-like widget a bare str, or toasts by `notify` and not `note`."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and (name := _named(node)) in LABELS | METHODS:
            if name == "notify" and not notes:
                found.append(f"{node.lineno}: notify, where `note` is the way")
            text = node.args[0] if node.args else None
            if text is not None and name != "notify" and _bare(text):
                found.append(f"{node.lineno}: {name} given {ast.unparse(text)}")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in ATTRIBUTES and _bare(node.value):
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
    ],
)
def test_the_lint_finds_a_bare_str(planted):
    assert violations(planted) != []


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
