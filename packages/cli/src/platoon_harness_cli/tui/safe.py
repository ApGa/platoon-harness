"""SafeText: the one way text from outside reaches the screen."""

from textual.content import Content, Span
from textual.notifications import SeverityLevel
from textual.widget import Widget

from ..output import safe


class SafeText(Content):
    """Content made from text from outside: agent, tool, branch and file names, messages and tool output. Each control
    a terminal would act on, C0 but tab and newline, DEL, C1 and the bidi controls, is shown as its escape, and nothing
    in it is read as markup."""

    __slots__ = ()

    def __init__(self, text: str, style: str = "") -> None:
        shown = safe(text)
        super().__init__(shown, [Span(0, len(shown), style)] if style and shown else None)


def note(widget: Widget, text: str, severity: SeverityLevel = "information") -> None:
    """Tell the person something in a toast, the text made safe and never read as markup."""
    widget.notify(safe(text), severity=severity, markup=False)
