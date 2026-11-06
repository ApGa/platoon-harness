"""Owning a session in the foreground: what ends a run is the owner's, whatever its events' printer met."""

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from platoon_harness import JournalError, Refused
from platoon_harness_cli import running


class _Failing:
    """A session whose runtime a failed commit ended while it settled."""

    name = "s"

    def __await__(self):
        yield from ()
        return self

    async def events(self, *_, **__) -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(seq=1, type="runtime.started")

    async def settled(self, _span):
        raise JournalError("journal.sqlite: a commit failed, so nothing more is recorded: disk I/O error")

    async def leave(self) -> None:
        pass


async def test_a_failed_commit_ends_a_run_even_when_its_printer_was_refused(monkeypatch):
    async def refused(*_, **__) -> None:
        raise Refused("unavailable", "journal.sqlite: a commit failed, so nothing more is recorded: disk I/O error")

    monkeypatch.setattr(running, "printing", refused)

    with pytest.raises(JournalError):
        await running.own(_Failing(), span=None, json=True)  # ty: ignore[invalid-argument-type]
