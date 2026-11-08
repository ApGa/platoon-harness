"""The transcript alone, over a journal of a few events the test writes, read through the kernel's cursor rule."""

import asyncio
from collections.abc import Callable
from typing import Any

from textual.app import App, ComposeResult

from platoon_harness.kernel import Event, Page
from platoon_harness_cli.tui import transcript as transcript_module
from platoon_harness_cli.tui.transcript import Focus, Transcript


def event(seq: int, stream: str, type: str, gist: str, data: dict[str, Any], agent: str = "lead") -> Event:
    return Event(
        v=1,
        seq=seq,
        stream=stream,
        version=seq,
        type=type,
        actor="runtime",
        agent=agent,
        turn=None,
        context_version=None,
        episode=None,
        topology_rev=0,
        correlation=None,
        cause=(),
        based_on=(),
        native={},
        model=None,
        wall_time=0.0,
        gist=gist,
        data=data,
        outcome=None,
    )


def said(seq: int, gist: str) -> Event:
    return event(seq, "turn/lead", "item.recorded", gist, {"kind": "message"})


def tool(seq: int, phase: str, gist: str) -> Event:
    return event(seq, "turn/lead", "item.recorded", gist, {"kind": "tool", "phase": phase, "native_id": "call-1"})


class Journal:
    """`Session.page` over a list of events, with the kernel's cursor rule and a focus's streams or glob, and
    `Session.get_body` over `bodies`. `reading` runs as each page is asked for, and `held` holds the first page until it
    is set."""

    def __init__(
        self,
        events: list[Event],
        reading: Callable[[], None] | None = None,
        held: asyncio.Event | None = None,
        bodies: dict[str, bytes] | None = None,
    ) -> None:
        self.events = events
        self.reading = reading
        self.held = held
        self.bodies = bodies or {}
        self.asked = asyncio.Event()

    async def page(self, *, after=0, before=None, streams=None, match=None, limit=256) -> Page:
        if self.reading is not None:
            self.reading()
        self.asked.set()
        if (held := self.held) is not None:
            self.held = None
            await held.wait()
        focus = Focus("x", streams=tuple(streams or ()), matches=(match,) if match else ())
        found = [e for e in self.events if e.seq > after and (before is None or e.seq < before) and focus.holds(e)]
        head = self.events[-1].seq
        if before is None:
            found = found[:limit]
            return Page(events=tuple(found), cursor=found[-1].seq if len(found) == limit else head, head=head)
        found = found[-limit:]
        return Page(events=tuple(found), cursor=found[0].seq if len(found) == limit else after, head=head)

    async def get_body(self, ref: str, *, limit: int | None = None) -> bytes:
        return self.bodies[ref][:limit]


class Alone(App[None]):
    def compose(self) -> ComposeResult:
        yield Transcript()


def lines(transcript: Transcript) -> list[str]:
    return [block.line.plain for block in transcript.blocks]


async def test_a_window_s_edge_on_a_tool_s_line_reads_back_nothing_twice(monkeypatch):
    """A tool's line stands where its call began and shows how it ended, so the window's edge is where a line began:
    read back from there, nothing shows twice and a finished call never shows as running."""
    called = [tool(3, "started", "Bash ls"), said(4, "between"), tool(5, "completed", "done")]
    journal = Journal([said(1, "m1"), said(2, "m2"), *called, said(6, "m6")])
    monkeypatch.setattr(transcript_module, "WINDOW", 3)
    app = Alone()
    async with app.run_test(size=(80, 10)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 6)  # type: ignore[arg-type]
        assert lines(transcript) == ["✓ done", "@lead  between", "@lead  m6"]
        monkeypatch.setattr(transcript_module, "WINDOW", 100)
        transcript.following = False

        await transcript.page_back()

        assert lines(transcript) == ["@lead  m1", "@lead  m2", "✓ done", "@lead  between", "@lead  m6"]


async def test_a_page_read_while_a_child_is_spawned_is_put_in():
    """A child spawned while the first page is on its way widens nothing: the page is the focus's all the same."""
    history = [said(n, f"said {n}") for n in range(1, 6)]
    spawn = event(6, "agent/w", "agent.spawned", "w spawned as worker", {"parent": "agent:lead"}, agent="w")
    app = Alone()
    async with app.run_test(size=(80, 20)) as pilot:
        transcript = app.query_one(Transcript)
        journal = Journal([*history, spawn], reading=lambda: transcript.take([spawn]))

        await transcript.show(Focus.of_agent("lead"), journal, 5)  # type: ignore[arg-type]
        await pilot.pause()

        assert lines(transcript)[:5] == [f"@lead  said {n}" for n in range(1, 6)]
        assert lines(transcript)[5].strip() == "↳ w spawned as worker"


async def test_a_page_read_for_an_earlier_show_is_not_put_in_and_the_later_one_reads_its_own():
    lead = [said(n, f"said {n}") for n in range(1, 4)]
    held = asyncio.Event()
    journal = Journal([*lead, event(4, "inbox/you", "message.sent", "for you", {"sender": "agent:lead"})], held=held)
    app = Alone()
    async with app.run_test(size=(80, 20)) as pilot:
        transcript = app.query_one(Transcript)
        first = asyncio.ensure_future(transcript.show(Focus.of_agent("lead"), journal, 4))  # type: ignore[arg-type]
        await journal.asked.wait()

        await transcript.show(Focus.of_person("human:you"), journal, 4)  # type: ignore[arg-type]
        held.set()
        await first
        for _ in range(3):
            await pilot.pause()

        assert lines(transcript) == ["@lead → @you  for you"]


def test_an_agent_s_focus_reads_every_agent_s_stream_however_many_children_it_has():
    """A read names at most 256 streams, so a lead's children are read by a glob, and only theirs are drawn."""
    focus = Focus.of_agent("lead", [f"w{n}" for n in range(300)])

    assert len(focus.streams) == 3 and focus.matches == ("agent/*", "approval/*")
    assert focus.holds(event(1, "agent/w299", "agent.ended", "w299 finished", {}, agent="w299"))


async def test_a_lead_draws_its_own_children_and_no_one_else_s():
    journal = Journal(
        [
            event(
                1, "agent/mine", "agent.spawned", "mine spawned", {"parent": "agent:lead", "name": "mine"}, agent="lead"
            ),
            event(
                2,
                "agent/theirs",
                "agent.spawned",
                "theirs spawned",
                {"parent": "agent:other", "name": "theirs"},
                agent="other",
            ),
            event(3, "agent/theirs", "agent.ended", "theirs finished", {"status": "finished"}, agent="theirs"),
            event(4, "agent/mine", "agent.ended", "mine finished", {"status": "finished"}, agent="mine"),
            event(5, "agent/before", "agent.ended", "before finished", {"status": "finished"}, agent="before"),
        ]
    )
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)

        await transcript.show(Focus.of_agent("lead", ["before"]), journal, 5)  # type: ignore[arg-type]

        assert [line.strip() for line in lines(transcript)] == [
            "↳ mine spawned",
            "✓ mine finished",
            "✓ before finished",
        ]


async def test_a_scrollbar_shown_once_the_transcript_is_at_its_end_is_drawn_at_its_end():
    journal = Journal([said(n, f"said {n}") for n in range(1, 21)])
    app = Alone()
    async with app.run_test(size=(80, 10)) as pilot:
        transcript = app.query_one(Transcript)

        await transcript.show(Focus.of_agent("lead"), journal, 20)  # type: ignore[arg-type]
        await pilot.pause()

        assert transcript.scroll_y == transcript.max_scroll_y > 0
        assert transcript.vertical_scrollbar.position == transcript.scroll_y


def asked(seq: int, id: str, gist: str, *, agent: str = "lead", body: str | None = None, cut: int = 0) -> Event:
    """A request for approval `id`, at payload version 2 where it names a body, as a driver that says its ask records
    one, and at version 1, with neither field, where it names none."""
    data = {"id": id, "policy": "ask"} | ({} if body is None else {"body": body, "cut": cut})
    request = event(seq, f"approval/{id}", "approval.requested", gist, data, agent=agent)
    return request if body is None else request.model_copy(update={"v": 2})


def answered(seq: int, id: str, verdict: str, by: str, via: str | None, *, agent: str = "lead") -> Event:
    data = {"id": id, "verdict": verdict, "resolved_by": by, "via": via, "effect": seq}
    return event(seq, f"approval/{id}", "approval.resolved", f"approval {id}: {verdict}", data, agent=agent)


def opened(transcript: Transcript) -> list[str]:
    """What the open lines show, each line of it stripped, where it came from left out."""
    return [strip.text.strip() for block in transcript.blocks if block.open for strip in transcript._body(block)[:-1]]


async def test_an_approval_and_who_answered_it_are_drawn_in_its_agent_s_transcript():
    """An agent's approvals are on streams of their own, `approval/<id>`, as the id is its harness's, so its focus
    reads every approval's and draws its own: what it asked, which opens on the whole ask, drawn as it was asked, and
    who answered, a person through what they said or the role's policy. One recorded before a request carried its ask
    opens on its gist, saying what more it asks is unknown."""
    command = "rm -rf *_old_* # and __this__"
    journal = Journal(
        [
            said(1, "on it"),
            asked(2, "a1", "Bash: rm -rf", body="sha256:ask", cut=7),
            asked(3, "b1", "theirs", agent="other", body="sha256:theirs"),
            answered(4, "a1", "allow", "human:you", "tui"),
            answered(5, "b1", "deny", "human:you", "web", agent="other"),
            asked(6, "a2", "Go on?"),
            answered(7, "a2", "deny", "policy", "policy"),
        ],
        bodies={"sha256:ask": f"Bash\n{command}".encode()},
    )
    app = Alone()
    async with app.run_test(size=(100, 30)) as pilot:
        transcript = app.query_one(Transcript)

        await transcript.show(Focus.of_agent("lead"), journal, 7)  # type: ignore[arg-type]

        assert lines(transcript) == [
            "@lead  on it",
            "@lead asks for approval  Bash: rm -rf ▸",
            "✓ allowed by @you via tui",
            "@lead asks for approval  Go on?",
            "✗ denied by policy",
        ]
        transcript.toggle(transcript.blocks[1])
        transcript.toggle(transcript.blocks[3])
        while any(block.open and block.ask is None for block in transcript.blocks):
            await pilot.pause()

        assert opened(transcript) == [
            "Bash",
            command,
            "Cut here: it asks 7 bytes more, which the record does not keep, and Allow allows them too.",
            "Go on?",
            "What it asks beyond its gist is unknown: the record holds no more of it.",
        ]


async def test_an_agent_s_lines_and_its_approvals_are_read_back_a_page_at_a_time_none_missed_none_twice(monkeypatch):
    """Its streams and each glob are read apart, as a read takes one glob, and a page holds what every read covered."""
    history = [
        asked(seq, f"a{seq}", f"asked {seq}") if seq % 3 == 0 else said(seq, f"said {seq}") for seq in range(1, 31)
    ]
    monkeypatch.setattr(transcript_module, "PAGE", 2)
    app = Alone()
    async with app.run_test(size=(80, 10)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(history), 30)  # type: ignore[arg-type]
        transcript.following = False
        while transcript._before:
            await transcript.page_back()

        assert [block.first for block in transcript.blocks] == list(range(1, 31))
