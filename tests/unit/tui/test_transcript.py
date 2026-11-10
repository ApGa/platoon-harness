"""The transcript alone, over a journal of a few events the test writes, read through the kernel's cursor rule."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from textual.app import App, ComposeResult

from platoon_harness.kernel import Event, Page, Refused
from platoon_harness.primitives import Span, Spans
from platoon_harness_cli.approvals import Ask
from platoon_harness_cli.tui import transcript as transcript_module
from platoon_harness_cli.tui.transcript import (
    GUTTER,
    Block,
    Focus,
    Fold,
    Transcript,
    inline,
    line_of,
    replying_to,
    summary,
    text_of,
    tool_named,
)


def event(
    seq: int,
    stream: str,
    type: str,
    gist: str,
    data: dict[str, Any],
    agent: str = "lead",
    actor: str = "runtime",
    native: dict[str, str] | None = None,
    turn: str | None = None,
) -> Event:
    return Event(
        v=1,
        seq=seq,
        stream=stream,
        version=seq,
        type=type,
        actor=actor,
        agent=agent,
        turn=turn,
        context_version=None,
        episode=None,
        topology_rev=0,
        correlation=None,
        cause=(),
        based_on=(),
        native=native or {},
        model=None,
        wall_time=0.0,
        gist=gist,
        data=data,
        outcome=None,
    )


def said(seq: int, gist: str) -> Event:
    return event(seq, "turn/lead", "item.recorded", gist, {"kind": "message"})


def tool(seq: int, phase: str, gist: str, id: str = "call-1") -> Event:
    """A call's start, or its end, which says it completed, as a harness says how a call ended."""
    ended = {"outcome": "completed"} if phase == "completed" else {}
    return event(seq, "turn/lead", "item.recorded", gist, {"kind": "tool", "phase": phase, "native_id": id, **ended})


def spawned(seq: int, name: str, native: dict[str, str] | None) -> Event:
    """A child the lead spawned under the call its anchor, `native`, names, or under none."""
    data = {"parent": "agent:lead", "name": name}
    gist = f"{name} spawned as worker"
    return event(seq, f"agent/{name}", "agent.spawned", gist, data, actor="agent:lead", native=native)


class Journal:
    """`Session.page` over a list of events, with the kernel's cursor rule and a focus's streams or glob,
    `Session.get_body` over `bodies` and `Session.spans` as `cut`, one page of them. `reading` runs as each page is
    asked for, and `held` holds the first page until it is set."""

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
        self.cut: list[Span] = []
        self.asked = asyncio.Event()
        self.before: int | None = None

    async def page(self, *, after=0, before=None, streams=None, match=None, limit=256) -> Page:
        self.before = before
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

    async def spans(self, agent: str, *, after: str | None = None) -> Spans:
        head = self.events[-1].seq
        return Spans(agent=agent, spans=tuple(self.cut), total=len(self.cut), cursor=None, head=head, open=False)


class Alone(App[None]):
    def compose(self) -> ComposeResult:
        yield Transcript()


def lines(transcript: Transcript) -> list[str]:
    return [block.line.plain for block in transcript.blocks]


def drawn(transcript: Transcript) -> list[str]:
    """The lines as they are drawn, top to bottom."""
    return [block.line.plain for block, row in transcript._rows if row == 0]


def shown(transcript: Transcript) -> list[str]:
    """Each row as it is drawn, top to bottom, headings and blank rows among them, without the gutter that marks the
    chosen line, the padding at its end or a rule's run to the edge."""
    width = transcript.scrollable_content_region.width
    rows = [transcript._strip(block, line, width).text[GUTTER:].rstrip() for block, line in transcript._rows]
    return [row.rstrip("─").rstrip() if row.lstrip().startswith("──") else row for row in rows]


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
        assert lines(transcript) == ["@lead  Bash ls", "@lead  between", "@lead  m6"]
        assert transcript.blocks[0].event.data["phase"] == "completed"
        monkeypatch.setattr(transcript_module, "WINDOW", 100)
        transcript.following = False

        await transcript.page_back()

        assert lines(transcript) == ["@lead  m1", "@lead  m2", "@lead  Bash ls", "@lead  between", "@lead  m6"]


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
        assert lines(transcript)[5] == "w spawned as worker · joins no known call"


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

        assert lines(transcript) == ["mine spawned · joins no known call", "mine finished", "before finished"]


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
    return [
        strip.text.strip()
        for block in transcript.blocks
        if block.open
        for strip in transcript._body(block, transcript._inner())[:-1]
    ]


async def test_an_approval_and_who_answered_it_are_drawn_in_its_agent_s_transcript():
    """An agent's approvals are on streams of their own, `approval/<id>`, as the id is its harness's, so its focus
    reads every approval's and draws its own: what it asked, which opens on the whole ask, drawn as it was asked, and
    who answered, a person through what they said or the role's policy. One recorded before a request carried its ask
    opens on its gist, saying what more it asks is unknown. One nobody answered before its turn ended went moot, which
    no event records, so no answer is drawn under it."""
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
            asked(8, "a3", "Delete it?"),
            event(9, "turn/lead", "turn.ended", "turn ended", {"reason": "interrupted"}),
        ],
        bodies={"sha256:ask": f"Bash\n{command}".encode()},
    )
    app = Alone()
    async with app.run_test(size=(100, 30)) as pilot:
        transcript = app.query_one(Transcript)

        await transcript.show(Focus.of_agent("lead"), journal, 9)  # type: ignore[arg-type]

        assert lines(transcript) == [
            "@lead  on it",
            "@lead  asks for approval  Bash: rm -rf",
            "allowed by @you via tui",
            "@lead  asks for approval  Go on?",
            "denied by policy",
            "@lead  asks for approval  Delete it?",
            "turn interrupted",
        ]
        assert [block.said.mark.plain for block in transcript.blocks] == ["", "◉ ", "✓ ", "◉ ", "✗ ", "◉ ", "■ "]
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


async def test_a_spawn_is_drawn_under_the_call_whose_id_its_anchor_holds():
    """Two calls at once, each spawning a child, and each child drawn under its own call, whichever was made first."""
    journal = Journal(
        [
            said(1, "two workers"),
            tool(2, "started", "spawn a", id="toolu_a"),
            tool(3, "started", "spawn b", id="toolu_b"),
            spawned(4, "b", {"claudecode/toolUseId": "toolu_b"}),
            spawned(5, "a", {"claudecode/toolUseId": "toolu_a"}),
            tool(6, "completed", "spawned a", id="toolu_a"),
            tool(7, "completed", "spawned b", id="toolu_b"),
        ]
    )
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)

        await transcript.show(Focus.of_agent("lead"), journal, 7)  # type: ignore[arg-type]

        assert drawn(transcript) == [
            "@lead  two workers",
            "@lead  spawn a",
            "@lead  a spawned as worker",
            "@lead  spawn b",
            "@lead  b spawned as worker",
        ]
        assert shown(transcript) == [
            "@lead",
            "  two workers",
            "  ▸ spawn a",
            "    ↳ a spawned as worker",
            "  ▸ spawn b",
            "    ↳ b spawned as worker",
        ]


async def test_a_spawn_drawn_before_its_call_moves_under_it_once_the_call_is_drawn():
    """A harness's report of its call can land after the spawn it made under that call's id."""
    journal = Journal([said(1, "on it")])
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 1)  # type: ignore[arg-type]

        transcript.take([spawned(2, "w", {"pi/toolCallId": "call_7"})])
        before = shown(transcript)
        transcript.take([said(3, "meanwhile"), tool(4, "started", "spawn w", id="call_7")])

        assert before == ["@lead", "  on it", "", "· w spawned as worker · joins no known call"]
        assert shown(transcript) == ["@lead", "  on it", "  meanwhile", "  ▸ spawn w", "    ↳ w spawned as worker"]


async def test_a_spawn_that_joins_no_call_is_drawn_where_the_journal_has_it_saying_so():
    """OpenHands' calls come through the shim under an id of its own, which no item holds, and a call can come with no
    id at all, as a scripted `Call` step's does. Such a spawn is led as any event's line is, not indented under the line
    above it as one drawn under its call is."""
    journal = Journal(
        [
            tool(1, "started", "spawn", id="oh-tool-1"),
            spawned(2, "oh", {"platoon-harness/callId": "9f1c2e"}),
            spawned(3, "nameless", None),
            tool(4, "completed", "spawned", id="oh-tool-1"),
            said(5, "both started"),
        ]
    )
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)

        await transcript.show(Focus.of_agent("lead"), journal, 5)  # type: ignore[arg-type]

        assert shown(transcript) == [
            "@lead",
            "  ▸ spawn",
            "",
            "· oh spawned as worker · joins no known call",
            "· nameless spawned as worker · joins no known call",
            "",
            "@lead",
            "  both started",
        ]


async def test_a_window_s_edge_takes_a_call_with_the_spawns_drawn_under_it_and_reads_back_nothing_twice(monkeypatch):
    """A call goes with the spawns drawn under it, one made before its item as much as after, whichever end of the
    window lets it go, so a page read again draws each once and each still under its call."""
    history = [
        said(1, "m1"),
        spawned(2, "early", {"claudecode/toolUseId": "toolu_1"}),
        said(3, "m3"),
        tool(4, "started", "spawn", id="toolu_1"),
        spawned(5, "late", {"claudecode/toolUseId": "toolu_1"}),
        said(6, "m6"),
        said(7, "m7"),
    ]
    monkeypatch.setattr(transcript_module, "WINDOW", 3)
    app = Alone()
    async with app.run_test(size=(80, 10)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(history), 7)  # type: ignore[arg-type]
        newest = drawn(transcript)
        transcript.following = False
        await transcript.page_back()
        oldest = drawn(transcript)
        monkeypatch.setattr(transcript_module, "WINDOW", 100)

        while transcript._after is not None:
            await transcript.page_forward()

        assert newest == ["@lead  m6", "@lead  m7"]
        assert oldest == ["@lead  m1"]
        assert drawn(transcript) == [
            "@lead  m1",
            "@lead  m3",
            "@lead  spawn",
            "@lead  early spawned as worker",
            "@lead  late spawned as worker",
            "@lead  m6",
            "@lead  m7",
        ]


def called(seq: int) -> Event:
    return event(seq, "turn/lead", "model.called", "lead called a model", {"call_id": f"c{seq}"})


def span(first: int, last: int, *writes: str) -> Span:
    """A span of `lead`'s turn `t1`, by the seqs of its first call and its last, which are their versions here."""
    return Span(ref=f"turn/lead@{last}", first=f"turn/lead@{first}", turn="t1", writes=writes, claims=(), labels={})


async def test_a_turn_s_cuts_are_drawn_where_its_spans_end(monkeypatch):
    """A cut stands at the first call of the span after it, so it is drawn under what the calls before it made, and it
    names the span it ends by its last call, which it shows. A turn's last span ends with the turn, which says so
    itself. Cuts are read as the agent is shown, in a turn under way too, and again as each turn of its ends, so one
    made while a turn runs is drawn as that turn ends; one whose two calls come on pages read back apart is drawn once,
    where it stands. `spans` answers as the query would at each read, which cuts a turn under way as soon as a call is
    reported after one that chose a write."""
    turn = [
        event(1, "turn/lead", "turn.started", "turn t1 started", {"turn": "t1"}),
        called(2),
        tool(3, "started", "task_complete", id="done-1"),
        tool(4, "completed", "task 1 done", id="done-1"),
        called(5),
        tool(6, "started", "task_complete", id="done-2"),
        tool(7, "completed", "task 2 done", id="done-2"),
        called(8),
        said(9, "both are done"),
    ]
    ended = event(10, "turn/lead", "turn.ended", "turn t1 ended: stopped", {"reason": "stopped"})
    cut = [span(2, 2, "task/q/1@3"), span(5, 8, "task/q/2@3")]
    journal = Journal([*turn, ended])
    journal.cut = [span(2, 2, "task/q/1@3")]
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 4)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()
        transcript.take(turn[4:])
        journal.cut = cut
        await app.workers.wait_for_complete()
        under_way = shown(transcript)
        transcript.take([ended])
        await app.workers.wait_for_complete()
        followed = shown(transcript)
        (cut_at,) = [block for block in transcript.blocks if "ends" in block.line.plain]
        await transcript.show(Focus.of_agent("lead"), journal, 9)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()
        shown_under_way = shown(transcript)
    monkeypatch.setattr(transcript_module, "PAGE", 3)
    app = Alone()
    async with app.run_test(size=(80, 2)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 10)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()
        held = list(transcript._calls)
        transcript.following = False
        while transcript._before:
            await transcript.page_back()
        read_back = shown(transcript)

    assert under_way == ["── turn", "@lead", "  ▸ task_complete", "  ▸ task_complete", "  both are done"]
    assert (
        followed
        == shown_under_way
        == [
            "── turn",
            "@lead",
            "  ▸ task_complete",
            "",
            "── span turn/lead@2 ends",
            "@lead",
            "  ▸ task_complete",
            "  both are done",
        ]
    )
    assert read_back == [*followed[:7], "@lead", followed[7]], "a page read back above keeps the heading it had"
    assert (cut_at.first, f"{cut_at.event.stream}@{cut_at.event.version}") == (5, "turn/lead@2")
    assert held == ["turn/lead@8", "turn/lead@5"], "the page holding the cut's last call is read after its spans"


class Naming(Alone):
    """A transcript alone, keeping each ref a click on a line's words named."""

    def __init__(self) -> None:
        super().__init__()
        self.named: list[str] = []

    def on_transcript_named(self, named: Transcript.Named) -> None:
        self.named.append(named.ref)


async def test_a_ref_in_a_line_s_text_opens_its_provenance():
    """A ref a line's words name is a link, standing apart from the words around it, so none is found in a link's
    address: a click on it opens the provenance of the event it names, whatever lines it names of it. A click on the
    rest of a line chooses it, and opens nothing, chosen already or not: its `▸` opens it."""
    words = "done, as board/notes/spec@3#L1-2 and inbox/you@1 say; https://x/inbox/you@1 is no ref"
    app = Naming()
    async with app.run_test(size=(120, 5)) as pilot:
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal([said(1, "first"), said(2, words)]), 2)  # type: ignore[arg-type]
        assert shown(transcript) == ["@lead", "  first", f"  {words}"]
        for ref in ("board/notes/spec@3#L1-2", "inbox/you@1"):
            await pilot.click(Transcript, offset=(shown(transcript)[2].index(ref) + len(ref) - 1, 2))
        await pilot.click(Transcript, offset=(shown(transcript)[2].index("https://x/inbox") + 12, 2))
        await pilot.pause()
        opened = transcript.blocks[1].open
        await pilot.click(Transcript, offset=(4, 1))
        await pilot.pause()
        chosen, first_opened = transcript.chosen, transcript.blocks[0].open
        await pilot.click(Transcript, offset=(4, 1))
        await pilot.pause()

    assert app.named == ["board/notes/spec@3", "inbox/you@1"]
    assert not opened, "a click on the words of a line, which name no ref, opens nothing"
    assert chosen is transcript.blocks[0] and not first_opened, "a click on another line chooses it"
    assert not transcript.blocks[0].open and not transcript.following


async def test_find_waits_out_a_read_under_way_and_reads_back_each_page_once():
    """A page read as the person scrolls is put in before find reads on, so each page is read once, each line looked at
    once, and the line found is the newest before the chosen one whose words hold the words, whatever their case."""
    history = [said(1, "the old needle"), said(2, "a needle"), *(said(n, f"said {n}") for n in range(3, 701))]
    befores: list[int | None] = []
    journal = Journal(history)
    app = Alone()
    async with app.run_test(size=(80, 10)) as pilot:
        transcript = app.query_one(Transcript)
        journal.reading = lambda: befores.append(journal.before)
        await transcript.show(Focus.of_agent("lead"), journal, 700)  # type: ignore[arg-type]
        journal.held = held = asyncio.Event()
        journal.asked.clear()
        scrolled = asyncio.ensure_future(transcript.page_back())
        await journal.asked.wait()

        finding = transcript.find("A NEEDLE")
        await pilot.pause()
        held.set()
        await scrolled
        await finding.wait()

        assert transcript.chosen is not None and transcript.chosen.event.gist == "a needle"
        assert not transcript.following
        assert befores == [701, 701, 445, 445, 189, 189], "a page is a read for each of the focus's globs"
        assert [block.first for block in transcript.blocks] == list(range(1, 701))


def test_a_thread_holds_its_messages_alone_and_a_reply_goes_where_the_page_s_reply_goes():
    """A thread is the message it began with and every message sent in it. A reply goes to the topic or the group a
    message is on, or to the other of a direct exchange the person is in, a runtime's report standing for the agent it
    is about, which the chip names as that report, and nowhere for one between others."""

    def sent(seq: int, stream: str, sender: str, **data: Any) -> Event:
        return event(seq, stream, "message.sent", "words", {"sender": sender, "thread": None, **data})

    began = Focus.of_thread(sent(3, "channel/notes", "@you"), "human:you")
    replied = Focus.of_thread(sent(5, "inbox/lead", "@you", thread="channel/notes@3"), "human:you")
    held = [sent(3, "channel/notes", "@you"), sent(5, "inbox/lead", "@you", thread="channel/notes@3")]
    others = [sent(4, "channel/notes", "@lead"), event(6, "channel/notes", "item.recorded", "x", {"thread": "x"})]

    assert began.thread == replied.thread == "channel/notes@3" and began.title == "Thread channel/notes@3"
    assert all(began.holds(one) for one in held) and not any(began.holds(other) for other in others)

    def to(stream: str, sender: str, **data: Any) -> str | None:
        return Focus.of_thread(sent(1, stream, sender, **data), "human:you").to

    assert [to("channel/notes", "@lead"), to("channel/+crew", "@lead")] == ["#notes", "+crew"]
    assert [to("inbox/you", "@lead"), to("inbox/lead", "@you")] == ["@lead", "@lead"]
    assert to("inbox/you", "runtime", subject="worker") == "@worker"
    assert to("inbox/lead", "@worker") is None and to("inbox/you", "runtime") is None
    assert replying_to(sent(1, "inbox/you", "runtime", subject="worker")) == "the runtime's report on @worker"
    assert replying_to(sent(1, "inbox/you", "@lead")) == "@lead"


def test_a_line_s_text_is_what_it_shows_and_what_it_opens_on_each_control_as_its_escape():
    """What `/copy` sends: the line, who says it and its words without its mark, and while it is open its body as read,
    its gist whole while the body is read, which the line says it is, or an approval's ask as it was asked, with the
    words below it, never as Markdown."""
    asked = event(2, "approval/a1", "approval.requested", "rm -rf \x1b[2J", {"body": "b"})
    said = event(3, "inbox/you", "message.sent", "the  **gist**\x07", {"sender": "@lead", "body": "c"})
    ask = Ask(agent="lead", gist="rm -rf", text="rm -rf \x1b[2J /\nand more", below="cut at 64 KiB")
    request, message = line_of(asked), line_of(said)
    assert request is not None and message is not None
    shown = Block(2, asked, request, open=True, ask=ask)
    reading = Block(3, said, message, open=True)
    read = Block(3, said, message, open=True, text="# the body\n\\x1b[31m")

    assert reading.reading and not read.reading and not shown.reading and not Block(3, said, message).reading
    assert Block(2, asked, request, open=True).reading
    assert text_of(Block(3, said, message)) == "@lead → @you  the gist\\x07"
    assert text_of(shown) == "@lead  asks for approval  rm -rf \\x1b[2J\nrm -rf \\x1b[2J /\nand more\ncut at 64 KiB"
    assert text_of(reading) == "@lead → @you  the gist\\x07\nthe  **gist**\\x07"
    assert text_of(read) == "@lead → @you  the gist\\x07\n# the body\n\\x1b[31m"


async def test_an_agent_s_lines_run_under_one_heading_and_a_turn_stands_apart():
    """Who says a run of lines heads it once, the lines under it; a line of the runtime's own stands alone; a new
    speaker's heading and a rule have a blank row before them, but at the top and under a rule."""
    journal = Journal(
        [
            event(1, "turn/lead", "turn.started", "turn t1 started", {"turn": "t1"}),
            said(2, "reading"),
            tool(3, "started", 'mcp__ph__board_get {"board": "notes"}', id="get-1"),
            tool(4, "completed", "mcp__ph__board_get completed", id="get-1"),
            event(5, "agent/w", "agent.ended", "w finished: done", {"status": "finished"}, agent="w"),
            event(6, "inbox/lead", "message.sent", "your wait holds", {"sender": "runtime"}, agent=None),
            event(7, "inbox/lead", "message.sent", "and **more**", {"sender": "runtime"}, agent=None),
            said(8, "Done. **Summary:** `parse` fixed"),
            event(9, "turn/lead", "turn.started", "turn t2 started", {"turn": "t2"}),
            said(10, "again"),
        ]
    )
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)

        await transcript.show(Focus.of_agent("lead", ["w"]), journal, 10)  # type: ignore[arg-type]

        assert shown(transcript) == [
            "── turn",
            "@lead",
            "  reading",
            "  ▸ board_get  notes",
            "",
            "✓ w finished: done",
            "",
            "runtime → @lead",
            "  your wait holds",
            "  and more",
            "",
            "@lead",
            "  Done. Summary: parse fixed",
            "",
            "── turn",
            "@lead",
            "  again",
        ]
        styles = {segment.text.strip(): segment.style for segment in transcript._strip(transcript.blocks[6], 0, 80)}
        assert styles["Summary:"].bold and styles["parse"].color != styles["Done."].color


async def test_a_tool_s_line_drops_our_surface_s_prefix_and_opens_on_its_whole_name():
    """A tool is named as its model calls it but for `mcp__ph__`, with its input dim and a glyph and a word for how
    it ended, and opened, the line says its whole name."""
    journal = Journal(
        [
            tool(1, "started", 'mcp__ph__wait {"agents": ["@w"]}', id="wait-1"),
            event(
                2, "turn/lead", "item.recorded", "mcp__ph__wait failed",
                {"kind": "tool", "phase": "completed", "native_id": "wait-1", "outcome": "failed"},
            ),
            tool(3, "started", "bash ls", id="bash-1"),
        ]
    )  # fmt: skip
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 3)  # type: ignore[arg-type]
        transcript.toggle(transcript.blocks[0])

        assert shown(transcript)[:3] == ["@lead", "  ▾ wait  @w  ✗ failed", "    mcp__ph__wait failed"]
        assert "item.recorded · tool mcp__ph__wait · runtime · seq 2" in shown(transcript)[3]
        assert shown(transcript)[4] == "  ▸ bash ls"


def body_of(seq: int, gist: str, body: str | None) -> Event:
    return event(seq, "turn/lead", "item.recorded", gist, {"kind": "message", "body": body})


class Bodies(Journal):
    """A journal whose body `sha256:gone` cannot be read."""

    async def get_body(self, ref: str, *, limit: int | None = None) -> bytes:
        if ref == "sha256:gone":
            raise Refused("not_found", "no such body")
        return await super().get_body(ref, limit=limit)


async def test_what_an_agent_says_that_is_whitespace_alone_is_no_line_once_its_body_is_known_blank():
    """As the page's chats leave it out: a gist of whitespace with no body says nothing, nor does one whose body is
    blank once that is read, but one whose body says something, or cannot be read, is drawn, as unknown is not blank."""
    history = [
        said(1, "first"),
        body_of(2, "\n\n", None),
        body_of(3, "\n\n", "sha256:blank"),
        body_of(4, "  ", "sha256:blank"),
        body_of(5, " ", "sha256:said"),
        body_of(6, " ", "sha256:gone"),
        said(7, "last"),
    ]
    journal = Bodies(history, bodies={"sha256:blank": b"\n \n", "sha256:said": b"   words"})
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 7)  # type: ignore[arg-type]
        unread = [block.first for block in transcript.blocks]
        await app.workers.wait_for_complete()

        assert unread == [1, 3, 4, 5, 6, 7], "a body unread is not known to be blank"
        assert [block.first for block in transcript.blocks] == [1, 5, 6, 7]
        assert not transcript.reading_bodies
        assert transcript.blocks[1].text == "   words"


async def test_a_message_that_has_a_body_is_drawn_open_on_it_as_it_comes():
    """A message says what its body says, and its gist is the first 280 characters of it, cut, so its line is drawn
    open as it comes: the whole of it is there with no key pressed, once, on the rows under its mark."""
    said = "the parser is fixed, and its tests pass"
    journal = Journal([body_of(1, "the parser is fixed", "sha256:said")], bodies={"sha256:said": said.encode()})
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 1)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()

        assert transcript.blocks[0].open
        assert shown(transcript)[:3] == ["@lead", "   ▾", f"    {said}"]


async def test_enter_on_a_message_s_line_closes_it_on_its_gist_alone():
    journal = Journal([body_of(1, "the parser is fixed", "sha256:said")], bodies={"sha256:said": b"and its tests"})
    app = Alone()
    async with app.run_test(size=(80, 20)) as pilot:
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 1)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()
        transcript.focus()
        await pilot.press("enter")

        assert not transcript.blocks[0].open
        assert shown(transcript) == ["@lead", "  the parser is fixed ▸"]


async def test_a_tool_call_s_line_is_drawn_shut_as_it_comes():
    """A call's input is what opening it shows, not what it says, so its line waits for a key as it always has."""
    journal = Journal([tool(1, "started", "bash ls")])
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 1)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()

        assert not transcript.blocks[0].open
        assert shown(transcript) == ["@lead", "  ▸ bash ls"]


async def test_a_message_whose_gist_is_whitespace_alone_is_drawn_open_on_the_body_it_says():
    """Its gist says nothing, so its body is all it says: read as it comes, drawn under a gist row of whitespace and
    laid out again for it, and gone once its body is known to be blank too."""
    journal = Bodies(
        [body_of(1, " ", "sha256:said"), body_of(2, "\n", "sha256:blank")],
        bodies={"sha256:said": b"words\n\nmore\n\nmost", "sha256:blank": b"\n \n"},
    )
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 2)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()

        assert [block.first for block in transcript.blocks] == [1]
        assert transcript.blocks[0].open
        assert shown(transcript)[1:5] == ["   ▾", "    words", "", "    more"]


async def test_a_page_of_messages_is_read_and_laid_out_once(monkeypatch):
    """One worker reads the bodies a page draws open and the page is laid out once, rather than once a line, so a
    page of messages costs what a page costs."""
    history = [body_of(seq, f"said {seq}", f"sha256:{seq}") for seq in range(1, 6)]
    bodies = {f"sha256:{seq}": f"body {seq}".encode() for seq in range(1, 6)}
    read, settled = [], []
    reading = Journal.get_body

    async def counted(self, ref, *, limit=None):
        read.append(ref)
        return await reading(self, ref, limit=limit)

    laying = Transcript._settle

    def sneaked(self, blocks):
        settled.append(list(blocks))
        laying(self, blocks)

    monkeypatch.setattr(Journal, "get_body", counted)
    monkeypatch.setattr(Transcript, "_settle", sneaked)
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(history, bodies=bodies), 5)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()

        assert read == sorted(bodies) and len(settled) == 1 and len(settled[0]) == 5
        assert [block.open for block in transcript.blocks] == [True] * 5


def did(seq: int, gist: str, data: dict[str, Any]) -> Event:
    """Something the lead did, or said, in its turn `t1`."""
    return event(seq, "turn/lead", "item.recorded", gist, data, turn="t1")


def call(seq: int, phase: str, gist: str, id: str, **data: Any) -> Event:
    return did(seq, gist, {"kind": "tool", "phase": phase, "native_id": id, **data})


A_TURN = [
    event(1, "turn/lead", "turn.started", "turn t1 started", {"turn": "t1"}, turn="t1"),
    did(2, "check the parser", {"kind": "thought", "body": "sha256:thought"}),
    call(3, "started", 'read {"path": "parser.py"}', "r1", body="sha256:input"),
    call(4, "completed", "read completed", "r1", outcome="completed", body="sha256:output"),
    call(5, "started", 'bash {"command": "pytest"}', "b1"),
    call(6, "completed", "bash failed", "b1", outcome="failed"),
    call(7, "started", 'mcp__ph__agent_spawn {"name": "w"}', "s1"),
    event(
        8, "agent/w", "agent.spawned", "w spawned as worker", {"parent": "agent:lead", "name": "w"},
        agent=None, actor="agent:lead", native={"pi/toolCallId": "s1"}, turn="t1",
    ),
    call(9, "completed", "mcp__ph__agent_spawn completed", "s1", outcome="completed"),
    did(10, "Fixed: the parser, and its tests pass.", {"kind": "message"}),
    event(11, "turn/lead", "turn.ended", "turn ended: finished", {"reason": "finished"}, turn="t1"),
]  # fmt: skip
"""A turn of the lead's: it thinks, reads a file, runs a command that fails, spawns a worker, and says it is done."""
BODIES = {
    "sha256:thought": b"I will check the parser first.",
    "sha256:input": b'{"path": "parser.py"}',
    "sha256:output": b"def parse(text):\n    return text.split()\n",
}
FOLDED = [
    "── turn",
    "@lead",
    "  ▸ 3 tool calls · ✗ 1 failed · 1 thought · 1 spawn",
    "  Fixed: the parser, and its tests pass.",
]


async def test_a_turn_shows_what_its_agent_said_and_folds_all_else_it_did_into_one_line_that_counts_it():
    """What the lead said stands; its calls, its thought and its spawn are one line that counts them exactly, the call
    that failed among them, which opens one level on each, a call by its name and its input in short, a thought dim,
    and the spawn under its call, and a call opens on its whole input and what it gave back. Its end, finished, is no
    line."""
    app = Alone()
    async with app.run_test(size=(80, 30)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN, bodies=BODIES), 11)  # type: ignore[arg-type]
        folded = shown(transcript)
        fold = next(block for block, _ in transcript._rows if isinstance(block, Fold))
        transcript.toggle(fold)
        opened = shown(transcript)
        transcript.toggle(next(block for block in transcript.blocks if block.event.gist.startswith("read")))
        await app.workers.wait_for_complete()
        whole = shown(transcript)
        transcript.toggle(fold)

        assert folded == FOLDED
        assert opened == [
            "── turn",
            "@lead",
            "  ▾ 3 tool calls · ✗ 1 failed · 1 thought · 1 spawn",
            "    ▸ ∴ check the parser",
            "    ▸ read  parser.py",
            "    ▸ bash  pytest  ✗ failed",
            "    ▸ agent_spawn  w",
            "      ↳ w spawned as worker",
            "  Fixed: the parser, and its tests pass.",
        ]
        assert whole[4:12] == [
            "    ▾ read  parser.py",
            "      input",
            "      {",
            '        "path": "parser.py"',
            "      }",
            "",
            "      output",
            "      def parse(text):",
        ]
        assert shown(transcript) == FOLDED and transcript.chosen is fold


async def test_a_turn_that_finished_or_was_stopped_draws_no_line_for_its_end_and_one_that_failed_does():
    """With steps or none, a turn's ordinary end says nothing the next turn's rule and the agent's state do not, and
    a fold has nothing of it to hide; an end that is no ordinary one stands among what was said."""
    turns = [
        A_TURN[0],
        did(2, "Done.", {"kind": "message"}),
        event(3, "turn/lead", "turn.ended", "turn ended: finished", {"reason": "finished"}, turn="t1"),
        event(4, "turn/lead", "turn.started", "turn t2 started", {"turn": "t2"}, turn="t2"),
        event(5, "turn/lead", "turn.ended", "turn ended: stopped", {"reason": "stopped"}, turn="t2"),
        event(6, "turn/lead", "turn.started", "turn t3 started", {"turn": "t3"}, turn="t3"),
        event(7, "turn/lead", "turn.ended", "turn ended: failed", {"reason": "failed"}, turn="t3"),
    ]
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(turns), 7)  # type: ignore[arg-type]

        assert shown(transcript) == ["── turn", "@lead", "  Done.", "", "── turn", "", "── turn", "■ turn failed"]


async def test_a_turn_under_way_shows_its_latest_step_and_rests_folded_once_it_ends():
    """While a runtime holds the session and the turn has no end, the fold says what is running and its latest step
    shows under it; once the turn ends it rests folded, and a call that never ended is said to have ended unknown, as
    no end of it is known."""
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        transcript.held(True)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN[:7]), 7)  # type: ignore[arg-type]
        under_way = shown(transcript)
        transcript.take([event(12, "turn/lead", "turn.lost", "turn lost", {}, turn="t1")])

        assert under_way == [
            "── turn",
            "@lead",
            "  ▸ 3 tool calls · ✗ 1 failed · 1 running · 1 thought",
            "    ▸ agent_spawn  w  running",
        ]
        assert shown(transcript)[2:] == [
            "  ▸ 3 tool calls · ✗ 1 failed · ? 1 ended unknown · 1 thought",
            "",
            "■ turn lost: the runtime went in the middle of it",
        ]


async def test_a_session_that_is_history_has_no_turn_under_way():
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN[:7]), 7)  # type: ignore[arg-type]

        assert shown(transcript) == [
            "── turn",
            "@lead",
            "  ▸ 3 tool calls · ✗ 1 failed · ? 1 ended unknown · 1 thought",
        ]


async def test_a_call_says_how_it_ended_whatever_its_phase_and_ended_unknown_where_its_end_says_not():
    """A harness may report a call with no phase, or end one naming no outcome: one that failed says so on its line as
    its fold counts it, and one whose end says not how it ended is said to have ended unknown, never counted a
    success."""
    turn = [
        A_TURN[0],
        did(2, 'bash {"command": "x"}', {"kind": "tool", "outcome": "failed"}),
        call(3, "started", 'read {"path": "a.py"}', "r1"),
        call(4, "completed", "read", "r1"),
        did(5, "Done.", {"kind": "message"}),
    ]
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(turn), 5)  # type: ignore[arg-type]
        transcript.toggle(transcript._folds["t1"])

        assert shown(transcript)[2:5] == [
            "  ▾ 2 tool calls · ✗ 1 failed · ? 1 ended unknown",
            "    ▸ bash  x  ✗ failed",
            "    ▸ read  a.py  ? ended unknown",
        ]


async def test_enter_and_right_open_a_line_one_level_and_left_and_esc_close_it_one_level(monkeypatch):
    """On the fold, Right opens it and Right again goes into it; Left on a step goes out to the fold's line, and Left
    or Esc closes that; Esc with nothing open goes back to the composer, as it does from any other part."""
    backs = []
    app = Alone()
    async with app.run_test(size=(80, 30)) as pilot:
        transcript = app.query_one(Transcript)
        monkeypatch.setattr(app.screen, "action_back", lambda: backs.append(True), raising=False)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN, bodies=BODIES), 11)  # type: ignore[arg-type]
        fold = transcript._folds["t1"]
        transcript.focus()
        await pilot.press("up")
        chose = transcript.chosen
        await pilot.press("right")
        opened = fold.open
        await pilot.press("right")
        into = transcript.chosen
        await pilot.press("enter")
        step_open = into.open if into else None
        await pilot.press("left")
        await pilot.press("left")
        out = transcript.chosen
        await pilot.press("escape")
        closed = not fold.open
        await pilot.press("escape")

    assert chose is fold and opened and into is not None and into.fold is fold and step_open
    assert out is fold and closed and backs == [True]


async def test_one_key_opens_every_fold_of_the_focus_and_each_that_comes_and_again_closes_them_all():
    second = [
        event(20, "turn/lead", "turn.started", "turn t2 started", {"turn": "t2"}, turn="t2"),
        event(
            21, "turn/lead", "item.recorded", "ls", {"kind": "tool", "phase": "started", "native_id": "x"}, turn="t2"
        ),
    ]
    app = Alone()
    async with app.run_test(size=(80, 40)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN), 11)  # type: ignore[arg-type]
        transcript.unfold()
        transcript.take(second)
        opened = [block.open for block in transcript._folds.values()]
        transcript.unfold()

        assert opened == [True, True]
        assert shown(transcript) == [*FOLDED, "", "── turn", "@lead", "  ▸ 1 tool call · ? 1 ended unknown"]


async def test_a_click_on_a_line_s_open_mark_opens_or_closes_it_and_on_its_words_chooses_it():
    app = Alone()
    async with app.run_test(size=(80, 20)) as pilot:
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN), 11)  # type: ignore[arg-type]
        fold = transcript._folds["t1"]
        await pilot.click(Transcript, offset=(GUTTER + 6, 2))
        chosen, still = transcript.chosen, fold.open
        await pilot.click(Transcript, offset=(GUTTER + 2, 2))
        opened = fold.open
        await pilot.click(Transcript, offset=(GUTTER + 2, 2))

    assert chosen is fold and not still and opened and not fold.open


async def test_find_opens_the_fold_of_a_step_it_finds():
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN), 11)  # type: ignore[arg-type]
        transcript.find("pytest")
        await app.workers.wait_for_complete()

        assert transcript._folds["t1"].open
        assert transcript.chosen is not None and transcript.chosen.event.gist == "bash failed"
        assert "    ▸ bash  pytest  ✗ failed" in shown(transcript)


async def test_a_folded_line_copies_what_it_shows_and_a_line_wrapped_is_selected_as_one_line():
    long = "the parser is fixed, " * 8
    app = Alone()
    async with app.run_test(size=(60, 20)) as pilot:
        transcript = app.query_one(Transcript)
        journal = Journal([*A_TURN, did(12, long.strip(), {"kind": "message"})])
        await transcript.show(Focus.of_agent("lead"), journal, 12)  # type: ignore[arg-type]
        copied = transcript.copied(transcript._folds["t1"])
        rows = [row for row, (block, line) in enumerate(transcript._rows) if block.event.seq == 12 and line >= 0]
        await pilot.mouse_down(Transcript, offset=(0, rows[0]))
        await pilot.hover(Transcript, offset=(59, rows[-1]))
        await pilot.mouse_up(Transcript, offset=(59, rows[-1]))

        assert len(rows) > 1, "a long line of what is said wraps"
        assert copied == "@lead  3 tool calls · ✗ 1 failed · 1 thought · 1 spawn"
        assert app.screen.get_selected_text() == long.strip()


async def test_a_turn_whose_start_the_window_lets_go_says_more_came_before():
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN), 11)  # type: ignore[arg-type]
        transcript._before = 3
        transcript._began.clear()
        transcript._forget(transcript._folds["t1"])

        assert "more before, not read yet" in shown(transcript)[2]


async def test_a_turn_the_window_holds_no_end_of_says_more_comes_after_and_no_call_of_it_ended_unknown(monkeypatch):
    """Read from the journal's first line, the window holds a turn's start and a call's, but not their ends: the fold
    says more comes after, not read yet, and the call that its end is not read yet, never that it ended unknown, until
    the window reads down to them."""
    monkeypatch.setattr(transcript_module, "PAGE", 4)
    history = [
        A_TURN[0],
        did(2, "check the parser", {"kind": "thought"}),
        call(3, "started", 'bash {"command": "pytest"}', "b1"),
        *[did(seq, f"said {seq}", {"kind": "message"}) for seq in range(4, 40)],
        call(40, "completed", "bash failed", "b1", outcome="failed"),
        event(41, "turn/lead", "turn.ended", "turn ended: finished", {"reason": "finished"}, turn="t1"),
    ]
    app = Alone()
    async with app.run_test(size=(80, 10)) as pilot:
        transcript = app.query_one(Transcript)
        transcript.held(True)
        await transcript.show(Focus.of_agent("lead"), Journal(history), 41)  # type: ignore[arg-type]
        await transcript.action_oldest()
        transcript.toggle(transcript._folds["t1"])
        oldest = shown(transcript)[2:5]
        while transcript._after is not None:
            transcript.scroll_end(animate=False, immediate=True, force=True)
            await pilot.pause()

        assert oldest == [
            "  ▾ 1 tool call · 1 thought · more after, not read yet",
            "    ∴ check the parser",
            "    ▸ bash  pytest  end not read yet",
        ]
        assert shown(transcript)[2:5] == [
            "  ▾ 1 tool call · ✗ 1 failed · 1 thought",
            "    ∴ check the parser",
            "    ▸ bash  pytest  ✗ failed",
        ]


async def test_a_call_read_back_from_its_end_is_one_line_with_its_start(monkeypatch):
    """A page read back holds a call's end, and the page before it its start: the two are one call, which the end's
    line takes, and nothing says a call ended unknown."""
    monkeypatch.setattr(transcript_module, "PAGE", 4)
    app = Alone()
    async with app.run_test(size=(80, 30)) as pilot:
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN), 11)  # type: ignore[arg-type]
        while transcript._before:
            await pilot.pause()
        folded = shown(transcript)
        transcript.toggle(transcript._folds["t1"])

        assert folded == FOLDED
        assert shown(transcript)[3:8] == [
            "    ▸ ∴ check the parser",
            "    ▸ read  parser.py",
            "    ▸ bash  pytest  ✗ failed",
            "    ▸ agent_spawn  w",
            "      ↳ w spawned as worker",
        ]


@pytest.mark.parametrize("comes", ["its end", "its turn's end", "history"])
async def test_a_call_drawn_running_is_drawn_again_as_its_end_comes_its_turn_ends_or_the_session_is_history(comes):
    """Open on a call that runs, a fold is drawn again once that changes, so neither the call's line nor what it opens
    on says it runs once it does not."""
    app = Alone()
    async with app.run_test(size=(80, 30)):
        transcript = app.query_one(Transcript)
        transcript.held(True)
        await transcript.show(Focus.of_agent("lead"), Journal(A_TURN[:7]), 7)  # type: ignore[arg-type]
        transcript.toggle(transcript._folds["t1"])
        transcript.toggle(transcript.blocks[-1])
        await app.workers.wait_for_complete()
        running = shown(transcript)[6:15]
        if comes == "its end":
            transcript.take([A_TURN[8]])
        elif comes == "its turn's end":
            transcript.take([event(12, "turn/lead", "turn.lost", "turn lost", {}, turn="t1")])
        else:
            transcript.held(False)
        await app.workers.wait_for_complete()
        now = shown(transcript)[6:15]

    assert running[0] == "    ▾ agent_spawn  w  running" and running[7] == "      (nothing yet: it is running)"
    if comes == "its end":
        assert now[0] == "    ▾ agent_spawn  w" and now[7] == "      mcp__ph__agent_spawn completed"
    else:
        assert now[0] == "    ▾ agent_spawn  w  ? ended unknown"
        assert now[7] == "      (unknown: the window holds no end of this call)"


def test_a_tool_is_named_only_where_its_input_follows_its_name_as_json():
    """As a model's call is reported; a command a harness ran, such as Codex's, names no tool, and is its words."""
    assert tool_named('mcp__ph__board_get {"board": "notes"}') == ("board_get", '{"board": "notes"}')
    assert tool_named("/bin/bash -lc 'ls -la'") == (None, "/bin/bash -lc 'ls -la'")
    assert tool_named("pytest") == (None, "pytest")
    assert summary('{"agents": ["@w", "@v"], "timeout": 600, "why": "to  see"}') == "@w, @v  600  to see"
    assert summary('{"cut": "short') == '{"cut": "short'


def test_markdown_in_a_line_shows_no_control_an_entity_or_an_escape_decodes_to():
    """Markdown decodes an entity to the character it names, a bidi control among them, which is made safe after, as a
    control in the text is, so neither reaches the screen or the clipboard."""
    said = inline("**bold** &#x202e;exe.gnp and \x1b[2J and `\x07` and &#x2066;").plain

    assert said == "bold \\u202eexe.gnp and \\x1b[2J and \\x07 and \\u2066"


async def test_a_body_read_to_learn_whether_it_is_blank_opens_said_cut_where_it_was_cut():
    long = b"x" * transcript_module.BODY_LIMIT
    journal = Bodies([body_of(1, " ", "sha256:long")], bodies={"sha256:long": long})
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 1)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()

        assert transcript.blocks[0].text is not None and transcript.blocks[0].text.endswith("(cut at 256 KiB)")
