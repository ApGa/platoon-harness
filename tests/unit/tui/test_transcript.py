"""The transcript alone, over a journal of a few events the test writes, read through the kernel's cursor rule."""

import asyncio
from collections.abc import Callable
from typing import Any

from textual.app import App, ComposeResult
from textual.content import Content

from platoon_harness.kernel import Event, Page
from platoon_harness.primitives import Span, Spans
from platoon_harness_cli.approvals import Ask
from platoon_harness_cli.tui import transcript as transcript_module
from platoon_harness_cli.tui.transcript import Block, Focus, Transcript, replying_to, text_of


def event(
    seq: int,
    stream: str,
    type: str,
    gist: str,
    data: dict[str, Any],
    agent: str = "lead",
    actor: str = "runtime",
    native: dict[str, str] | None = None,
) -> Event:
    return Event(
        v=1,
        seq=seq,
        stream=stream,
        version=seq,
        type=type,
        actor=actor,
        agent=agent,
        turn=None,
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
    return event(seq, "turn/lead", "item.recorded", gist, {"kind": "tool", "phase": phase, "native_id": id})


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
        assert lines(transcript)[5].strip() == "· w spawned as worker · joins no known call"


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
            "· mine spawned · joins no known call",
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
            "@lead asks for approval  Bash: rm -rf ▸",
            "✓ allowed by @you via tui",
            "@lead asks for approval  Go on?",
            "✗ denied by policy",
            "@lead asks for approval  Delete it?",
            "■ turn interrupted",
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

        assert [line.strip() for line in drawn(transcript)] == [
            "@lead  two workers",
            "✓ spawned a",
            "↳ a spawned as worker",
            "✓ spawned b",
            "↳ b spawned as worker",
        ]


async def test_a_spawn_drawn_before_its_call_moves_under_it_once_the_call_is_drawn():
    """A harness's report of its call can land after the spawn it made under that call's id."""
    journal = Journal([said(1, "on it")])
    app = Alone()
    async with app.run_test(size=(80, 20)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 1)  # type: ignore[arg-type]

        transcript.take([spawned(2, "w", {"pi/toolCallId": "call_7"})])
        before = [line.strip() for line in drawn(transcript)]
        transcript.take([said(3, "meanwhile"), tool(4, "started", "spawn w", id="call_7")])

        assert before == ["@lead  on it", "· w spawned as worker · joins no known call"]
        assert [line.strip() for line in drawn(transcript)] == [
            "@lead  on it",
            "@lead  meanwhile",
            "▸ spawn w",
            "↳ w spawned as worker",
        ]


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

        assert drawn(transcript) == [
            "✓ spawned",
            "· oh spawned as worker · joins no known call",
            "· nameless spawned as worker · joins no known call",
            "@lead  both started",
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
        newest = [line.strip() for line in drawn(transcript)]
        transcript.following = False
        await transcript.page_back()
        oldest = [line.strip() for line in drawn(transcript)]
        monkeypatch.setattr(transcript_module, "WINDOW", 100)

        while transcript._after is not None:
            await transcript.page_forward()

        assert newest == ["@lead  m6", "@lead  m7"]
        assert oldest == ["@lead  m1"]
        assert [line.strip() for line in drawn(transcript)] == [
            "@lead  m1",
            "@lead  m3",
            "▸ spawn",
            "↳ early spawned as worker",
            "↳ late spawned as worker",
            "@lead  m6",
            "@lead  m7",
        ]


def called(seq: int) -> Event:
    return event(seq, "turn/lead", "model.called", "lead called a model", {"call_id": f"c{seq}"})


def span(first: int, last: int, *writes: str) -> Span:
    """A span of `lead`'s turn `t1`, by the seqs of its first call and its last, which are their versions here."""
    return Span(ref=f"turn/lead@{last}", first=f"turn/lead@{first}", turn="t1", writes=writes)


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
        under_way = [line.strip() for line in drawn(transcript)]
        transcript.take([ended])
        await app.workers.wait_for_complete()
        followed = [line.strip() for line in drawn(transcript)]
        (shown,) = [block for block in transcript.blocks if "ends" in block.line.plain]
        await transcript.show(Focus.of_agent("lead"), journal, 9)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()
        shown_under_way = [line.strip() for line in drawn(transcript)]
    monkeypatch.setattr(transcript_module, "PAGE", 3)
    app = Alone()
    async with app.run_test(size=(80, 1)):
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), journal, 10)  # type: ignore[arg-type]
        await app.workers.wait_for_complete()
        held = list(transcript._calls)
        transcript.following = False
        while transcript._before:
            await transcript.page_back()
        read_back = [line.strip() for line in drawn(transcript)]

    assert under_way == ["── turn ──", "✓ task 1 done", "✓ task 2 done", "@lead  both are done"]
    assert (
        followed
        == shown_under_way
        == read_back
        == [
            "── turn ──",
            "✓ task 1 done",
            "── span turn/lead@2 ends ──",
            "✓ task 2 done",
            "@lead  both are done",
        ]
    )
    assert (shown.first, f"{shown.event.stream}@{shown.event.version}") == (5, "turn/lead@2")
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
    address: a click on it opens the provenance of the event it names, whatever lines it names of it, and a click on the
    rest of the line opens the line."""
    words = "done, as board/notes/spec@3#L1-2 and inbox/you@1 say; https://x/inbox/you@1 is no ref"
    app = Naming()
    async with app.run_test(size=(120, 5)) as pilot:
        transcript = app.query_one(Transcript)
        await transcript.show(Focus.of_agent("lead"), Journal([said(1, words)]), 1)  # type: ignore[arg-type]
        (line,) = drawn(transcript)
        for ref in ("board/notes/spec@3#L1-2", "inbox/you@1"):
            await pilot.click(Transcript, offset=(line.index(ref) + len(ref) - 1, 0))
        await pilot.click(Transcript, offset=(line.index("https://x/inbox") + 12, 0))
        await pilot.pause()

    assert app.named == ["board/notes/spec@3", "inbox/you@1"]
    assert transcript.blocks[0].open, "a click on words that name no ref opens the line"


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
    """What `/copy` sends: the line, and while it is open its body as read, its gist whole while the body is read, which
    the line says it is, or an approval's ask as it was asked, with the words below it, never as Markdown."""
    asked = event(2, "approval/a1", "approval.requested", "rm -rf \x1b[2J", {"body": "b"})
    said = event(3, "inbox/you", "message.sent", "the  **gist**\x07", {"sender": "@lead", "body": "c"})
    ask = Ask(agent="lead", gist="rm -rf", text="rm -rf \x1b[2J /\nand more", below="cut at 64 KiB")
    shown = Block(2, asked, Content("@lead asks for approval  rm -rf \\x1b[2J"), open=True, ask=ask)
    reading = Block(3, said, Content("@lead → @you  the **gist**\\x07 ▸"), open=True)
    read = Block(3, said, reading.line, open=True, text="# the body\n\\x1b[31m")

    assert reading.reading and not read.reading and not shown.reading and not Block(3, said, reading.line).reading
    assert Block(2, asked, shown.line, open=True).reading
    assert text_of(Block(3, said, reading.line)) == "@lead → @you  the **gist**\\x07 ▸"
    assert text_of(shown) == "@lead asks for approval  rm -rf \\x1b[2J\nrm -rf \\x1b[2J /\nand more\ncut at 64 KiB"
    assert text_of(reading) == "@lead → @you  the **gist**\\x07 ▸\nthe  **gist**\\x07"
    assert text_of(read) == "@lead → @you  the **gist**\\x07 ▸\n# the body\n\\x1b[31m"
