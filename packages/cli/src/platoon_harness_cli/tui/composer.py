"""The composer: what a person writes, multiline, with history, to the target shown above it."""

import re
from collections.abc import Callable

from textual import events
from textual.message import Message
from textual.widgets import TextArea

from platoon_harness.kernel import NAME

from .keymap import action_of

ADDRESS = re.compile(rf"([@#+]{NAME})\s")
"""An address and a space at the start of what the composer holds."""


class Composer(TextArea):
    """A multiline composer. Enter sends, and the keys the table names start a new line or recall what was sent, over
    an empty draft and never over one being written. An address that `known` takes, typed or pasted at the start, is
    taken out and retargets it."""

    class Send(Message):
        """The person asked to send what the composer holds."""

    class Retarget(Message):
        def __init__(self, to: str) -> None:
            super().__init__()
            self.to = to

    class Empty(Message):
        """The person asked to delete past the end of an empty composer, which detaches."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id, soft_wrap=True, show_line_numbers=False, tab_behavior="focus", compact=True)
        self.sent: list[str] = []
        self.known: Callable[[str], bool] = lambda address: False
        self._recalled: int | None = None

    def remember(self) -> None:
        """Keep what is in the composer as sent, and empty it."""
        if self.text.strip():
            self.sent.append(self.text)
        self._recalled = None
        self.clear()

    def on_key(self, event: events.Key) -> None:
        """The keys the table gives the composer, before the text area's own, which have the rest."""
        action = action_of("composer", event.key)
        row, _ = self.cursor_location
        if action == "send":
            self.post_message(self.Send())
        elif action == "newline":
            self.insert("\n")
        elif action == "older" and row == 0 and self.sent and (not self.text or self._recalled is not None):
            self._recall(-1)
        elif action == "newer" and row == self.document.line_count - 1 and self._recalled is not None:
            self._recall(1)
        else:
            return
        event.stop()
        event.prevent_default()

    def _recall(self, by: int) -> None:
        at = (len(self.sent) if self._recalled is None else self._recalled) + by
        if at >= len(self.sent):
            self._recalled = None
            self.clear()
            return
        self._recalled = max(at, 0)
        self.load_text(self.sent[self._recalled])
        self.move_cursor(self.document.end)

    def action_delete_right(self) -> None:
        if self.text:
            super().action_delete_right()
        else:
            self.post_message(self.Empty())

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        found = ADDRESS.match(self.text)
        if found is not None and self._recalled is None and self.known(found[1]):
            self.load_text(self.text[found.end() :])
            self.move_cursor(self.document.end)
            self.post_message(self.Retarget(found[1]))
