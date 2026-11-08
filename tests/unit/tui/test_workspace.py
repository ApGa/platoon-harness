"""The workspace on scripted harnesses: a session the test owns, and the TUI attached to it as a guest over its
socket."""

import asyncio
import base64
import contextlib
import re
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from rich.cells import cell_len
from textual.strip import Strip
from textual.widgets import Input

from platoon_harness import Session, Team
from platoon_harness import session as session_module
from platoon_harness.kernel import ManualClock
from platoon_harness.primitives import delivery
from platoon_harness.primitives.approvals import ASK_LIMIT
from platoon_harness.testing import Ask, Call, Hang, Say, ScriptedDriver
from platoon_harness_cli.ops import _command, person_ops
from platoon_harness_cli.output import safe
from platoon_harness_cli.provenance import Line, shows
from platoon_harness_cli.tui import live as live_module
from platoon_harness_cli.tui import transcript as transcript_module
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.approvals import Approval
from platoon_harness_cli.tui.composer import Composer
from platoon_harness_cli.tui.dialogs import Form
from platoon_harness_cli.tui.keymap import keys
from platoon_harness_cli.tui.provenance import Provenance
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.transcript import Transcript
from platoon_harness_cli.tui.workspace import CHOOSE, Dock, Workspace, _asked, _value

from ..runtime.support import BALLOT, SECONDS, extension, harness, in_state, of_type, until
from ..runtime.test_recovery import HangsOnAnswers, asked_then_crashed
from .support import at_once, drawn, workspace

pytestmark = pytest.mark.timeout(60)


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def team(*turns, **roles) -> Team:
    """`lead`, the one agent the session starts, on a scripted harness, and any other roles."""
    lead = {"harness": harness(lambda: ScriptedDriver(turns)), "may_spawn": list(roles)}
    others = {
        name: {"harness": harness(lambda turns=turns: ScriptedDriver(turns)), "count": 0}
        for name, turns in roles.items()
    }
    topology = {"edges": {"lead": ["children", "human"]}, "limits": {"max_depth": 2}}
    return Team.model_validate({"roles": {"lead": lead, **others}, "topology": topology})


@contextlib.asynccontextmanager
async def attached(team: Team, root: Path, *, size=(120, 32)) -> AsyncIterator[tuple[Session, TerminalUI, object]]:
    """A session the test owns, with `lead` up, and the TUI attached to it."""
    async with Session.start(team, name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=size) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            yield owner, app, pilot


async def test_a_message_from_the_composer_reaches_the_target_shown_once(root):
    async with attached(team([Say("on it")]), root) as (owner, app, pilot):
        assert app.focused is app.screen.query_one(Composer)

        await pilot.press(*"fix the flaky test", "enter")
        await drawn(pilot, lambda text: "@lead  on it" in text)

        sent = [event for event in await of_type(owner, "message.sent") if event.actor == "human:you"]
        assert [(event.stream, event.gist) for event in sent] == [("inbox/lead", "fix the flaky test")]
        lines = [block.line.plain for block in app.screen.query_one(Transcript).blocks]
        assert sum("fix the flaky test" in line for line in lines) == 1
        assert app.screen.query_one(Composer).text == ""


async def test_an_approval_never_takes_focus_so_a_key_meant_for_the_composer_never_answers_it(root):
    async with attached(team([Ask("Ship the fix?"), Say("shipped")]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Ship the fix?" in text)
        composer = app.screen.query_one(Composer)

        await pilot.press(*"yes", "y", "n")

        assert app.focused is composer and composer.text == "yesyn"
        assert await of_type(owner, "approval.resolved") == [], "a place nobody chose answered a key"

        await pilot.press(*["backspace"] * 5, "alt+a", *"/yes", "enter")
        await drawn(pilot, lambda text: "shipped" in text)

        resolved = await of_type(owner, "approval.resolved")
        assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("allow", "tui")]
        assert app.focused is composer


async def test_esc_then_a_word_typed_at_once_answers_and_stops_nothing(root, monkeypatch):
    """A terminal sends Alt and a letter as Esc then that letter, so no chord decides or stops anything. In the dock the
    letter lets go of the place chosen there, and the dock reads its keys in the order they came, however late, so a
    `y` or `n` later in the word answers nothing."""
    reading, read = Dock.on_key, asyncio.Event()
    read.set()

    async def late(self, event):
        await read.wait()
        await reading(self, event)

    monkeypatch.setattr(Dock, "on_key", late)
    async with attached(team([Ask("Ship the fix?"), Hang()]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Ship the fix?" in text)
        await pilot.press(*"/next-place", "enter")
        await drawn(pilot, lambda _: dock_of(app).cursor is not None)
        composer = app.screen.query_one(Composer)

        for word in ("no wait", "yes", "stop"):
            at_once(app, f"\x1b{word}")
            await drawn(pilot, lambda _, word=word: composer.text.endswith(word))
        assert composer.text == "no waityesstop"

        await pilot.press("shift+tab", "down")
        await drawn(pilot, lambda text: "y Allow  n Deny" in text)
        read.clear()
        at_once(app, "\x1bplease continue")
        await pilot.pause()
        read.set()
        await drawn(pilot, lambda _: any(CHOOSE in notice.message for notice in app._notifications))
        assert await of_type(owner, "approval.resolved") == [] and await of_type(owner, "turn.ended") == []


async def test_a_second_client_s_answer_shows_as_theirs_and_its_message_shows_once(root):
    async with attached(team([Ask("Ship the fix?"), Say("shipped")]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Ship the fix?" in text)
        await pilot.press("alt+a")
        second = await Session.attach("s", root=root)
        asked = (await second.approvals())[0]

        await asyncio.gather(
            second.resolve(asked["id"], "deny", expected_version=asked["version"], via="web"),
            second.send("@lead", "from the browser"),
        )
        await pilot.press(*"/yes", "enter")
        await drawn(pilot, lambda text: "from the browser" in text)

        resolved = await of_type(owner, "approval.resolved")
        assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("deny", "web")]
        lines = [block.line.plain for block in app.screen.query_one(Transcript).blocks]
        assert sum("from the browser" in line for line in lines) == 1
        shown = [notice.message for notice in app._notifications]
        assert not any("conflict" in said for said in shown)
        await second.leave()


async def test_esc_interrupts_the_agent_in_view_and_is_disabled_with_the_runtime_s_reason_when_it_would_stop_nothing(
    root,
):
    async with attached(team([Hang()], [Say("again")]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await in_state(owner, "lead", "running")

        await pilot.press("escape")
        ended = await until(lambda: of_type(owner, "turn.ended"), owner)
        assert [event.data["reason"] for event in ended] == ["interrupted"]
        await in_state(owner, "lead", "idle")
        await drawn(pilot, lambda text: "turn interrupted" in text)

        def told(app) -> int:
            return sum("neither in a turn" in notice.message for notice in app._notifications)

        await pilot.press("escape")
        await drawn(pilot, lambda _: told(app) == 1)
        await pilot.press("escape")
        await drawn(pilot, lambda _: told(app) == 2)
        refused = [event for event in await of_type(owner, "op.refused") if event.data["op"] == "agent.interrupt"]
        assert len(refused) == 1, "a refused act submitted again"

        await pilot.press(*"again", "enter")
        await drawn(pilot, lambda text: "@lead  again" in text)
        assert workspace(app)._refused == {}


async def test_stop_below_stops_the_turns_below_the_agent_in_view_and_says_it_stops_turns_not_waits(root):
    spawning = [Call("agent_spawn", {"name": "w", "child_role": "worker", "goal": "work"}), Hang()]
    async with attached(team(spawning, worker=[[Hang()]]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await in_state(owner, "w", "running")

        await pilot.press(*"/stop-below", "enter")
        ended = await until(lambda: of_type(owner, "turn.ended"), owner, lambda found: len(found) == 2)

        assert {event.agent: event.data["reason"] for event in ended} == {"lead": "interrupted", "w": "interrupted"}
        notices = [notice.message for notice in app._notifications]
        assert any("It stops turns, not waits" in said for said in notices)


def with_notes(base: Team) -> Team:
    """`base`, with a topic `notes` that wakes nobody, for a long history that costs no turn."""
    given = base.canonical()
    channels = {"notes": {"kind": "topic", "writers": "all", "readers": "all", "delivery": "pull"}}
    topology = {**given.get("topology", {}), "channels": channels}
    return Team.model_validate({**given, "topology": topology})


async def post(session: Session, count: int, start: int = 0) -> None:
    """Post notes 30 at a time, within what one principal may have in flight."""
    for first in range(start, start + count, 30):
        last = min(first + 30, start + count)
        await asyncio.gather(*(session.send("#notes", f"note {n}") for n in range(first, last)))


async def show_notes(pilot) -> Transcript:
    await pilot.press("alt+down", "alt+down")
    await drawn(pilot, lambda text: "#notes" in text.splitlines()[1])
    return pilot.app.screen.query_one(Transcript)


def top_line(transcript: Transcript) -> str:
    return transcript.render_line(0).text


async def test_a_history_far_larger_than_the_screen_is_read_back_a_page_at_a_time(root):
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 1500)
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 1499" in text)
            assert len(transcript.blocks) <= 2 * 256

            await pilot.press("pageup")
            while transcript.blocks[0].event.gist != "note 0":
                loaded = len(transcript.blocks)
                transcript.scroll_to(y=0, animate=False, immediate=True)
                oldest = top_line(transcript)
                await drawn(pilot, lambda text, loaded=loaded: len(transcript.blocks) > loaded)
                assert top_line(transcript) == oldest, "a page read back moved what was on screen"

            assert [block.event.gist for block in transcript.blocks] == [f"note {n}" for n in range(1500)]


async def test_scroll_is_kept_while_reading_and_what_comes_is_counted_until_the_person_follows_again(root):
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 300)
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 299" in text)

            await pilot.press("pageup", "pageup")
            await pilot.pause()
            reading = top_line(transcript)
            assert not transcript.following

            await post(owner, 7, start=300)
            await drawn(pilot, lambda text: "7 new" in text)
            assert top_line(transcript) == reading

            await pilot.press("ctrl+end")
            await drawn(pilot, lambda text: "note 306" in text)
            assert transcript.following and transcript.unseen == 0


SIZES = [(120, 32), (100, 30), (79, 24), (59, 20), (100, 15), (45, 12), (120, 32)]


@pytest.mark.parametrize("reading", [False, True], ids=["following", "reading"])
async def test_a_resize_never_changes_scroll_position_focus_or_the_composer_s_target(root, reading):
    """Under 16 rows the dock gives way, though a place waits there."""
    async with Session.start(with_notes(team([Ask("May I?")])), name="s", root=root, cwd=root) as owner:
        await post(owner, 200)
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "go")
        await until(lambda: owner.approvals(), owner)
        app = TerminalUI("s")
        async with app.run_test(size=SIZES[0]) as pilot:
            await drawn(pilot, lambda text: "May I?" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 199" in text)
            if reading:
                await pilot.press("pageup", "pageup")
            await pilot.press(*"half a thought")
            screen = workspace(app)
            before = (top_line(transcript).strip(), app.focused, screen.target, transcript.following)

            for width, height in SIZES[1:]:
                await pilot.resize_terminal(width, height)
                text = await drawn(pilot, lambda text, width=width: len(text.splitlines()[0]) == width)

                assert app.focused is before[1] and screen.target == before[2] and transcript.following == before[3]
                assert screen.query_one("#navigator").display == (width >= 80)
                assert screen.query_one("#dock").display == (height >= 16)
                assert ("May I?" in text) == (height >= 16)
                assert "need you" in text.splitlines()[0] or width < 60
                if reading:
                    assert top_line(transcript).strip() == before[0]
                else:
                    assert transcript.scroll_y == transcript.max_scroll_y
            assert screen.query_one(Composer).text == "half a thought"


async def test_wide_combining_emoji_and_right_to_left_text_keeps_every_line_its_width(root):
    said = ["中文の行 全角", "é combining", "family 👨‍👩‍👧 and 🇯🇵", "שלום עולם and مرحبا"]
    async with attached(team([Say(text) for text in said]), root, size=(61, 24)) as (_, app, pilot):
        await pilot.press(*"go", "enter")
        text = await drawn(pilot, lambda text: "שלום עולם" in text)

        for line in said:
            assert line.split()[0] in text
        transcript = app.screen.query_one(Transcript)
        width = transcript.scrollable_content_region.width
        assert all(transcript.render_line(y).cell_length == width for y in range(transcript.size.height))
        assert all(cell_len(row) == 61 for row in text.splitlines())


HOSTILE = "\x1b]0;owned\x1b\\ \x1b[2J \x9b31m ‮evil‬ [/x] [@click=app.quit]x[/] \x1b]52;c;ZXZpbA==\x07"
UNSAFE = [chr(code) for code in (*range(0x09), *range(0x0B, 0x20), 0x7F, *range(0x80, 0xA0), 0x202E, 0x202C)]


async def test_hostile_text_from_an_agent_reaches_no_renderer_unescaped(root):
    hostile = team([Say(HOSTILE), Call("message_send", {"to": "@you", "gist": HOSTILE}), Ask(HOSTILE)])
    async with attached(hostile, root) as (_, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: text.count("\\x1b]0;owned") >= 2)
        await pilot.press("f2")
        await pilot.press("ctrl+o")
        await pilot.press("alt+down")
        text = await drawn(pilot, lambda text: "\\u202eevil" in text)

        assert app.is_running
        assert not [char for char in UNSAFE if char in text]
        assert "[/x]" in text and "[@click=app.quit]x[/]" in text
        await pilot.press("ctrl+p")
        await pilot.press(*"agent")
        await pilot.press("escape")
        assert app.is_running


async def test_a_slow_screen_drops_frames_and_never_events(root, monkeypatch):
    monkeypatch.setattr(live_module, "PENDING", 64)
    async with attached(with_notes(team()), root) as (owner, app, _):
        live = workspace(app).live
        assert live is not None
        draw, sizes, seen, gate = live._draw, [], [], asyncio.Event()

        async def slow(events, deltas):
            sizes.append(len(events))
            seen.extend(event.seq for event in events)
            await gate.wait()
            await draw(events, deltas)

        live._draw = slow
        after, frames, began = live._read_through, live.frames, time.monotonic()
        await post(owner, 600)
        head = await owner.head()
        gate.set()
        while not seen or seen[-1] < head:
            await live.next_frame(live.frames)
        spent = time.monotonic() - began

        assert seen == [event.seq async for event in owner.events(seen[0] - 1)] and seen[0] <= after + 1
        assert max(sizes) <= 64
        assert live.frames - frames <= spent * 15 + 2
        assert live.frames - frames < len(seen) / 10


async def test_a_frame_cut_short_by_its_screen_going_is_dropped(root, monkeypatch):
    """Taking a screen down removes its widgets before it cancels its workers, so a frame drawn in between finds them
    gone, and that alone fails nothing."""
    gone = asyncio.Event()
    monkeypatch.setattr(Transcript, "on_unmount", lambda self: gone.set(), raising=False)
    async with attached(team(), root) as (_, app, _):
        screen = workspace(app)
        live = screen.live
        assert live is not None
        draw, waiting, running = live._draw, asyncio.Event(), []

        async def late(events, said):
            waiting.set()
            await gone.wait()
            running.append(screen.is_running)
            await draw(events, said)

        live._draw = late
        live._dirty.set()
        await waiting.wait()
        await app.pop_screen()

        assert running == [False] and app.is_running


async def test_the_palette_offers_each_write_op_the_person_holds_as_ops_list_gives_it(root):
    """After the session's acts by their typed commands, each op `ops.list` says the person holds that is no query and
    no wait, named with a space for its dot and worded as its command's help, a hold among them, which holds an
    agent's deliveries as the command line's does; and each runs through its form."""
    async with attached(team(), root) as (owner, app, pilot):
        held = await owner.ops()
        acts = {key.typed for key in (*keys("everywhere"), *keys("workspace"))}
        commands = {title: said for title, said, _ in workspace(app).commands() if title not in acts}
        writes = [entry["name"] for entry in held if not (entry["query"] or entry["exposes"] or _waits(entry))]

        assert sorted(commands) == sorted(name.replace(".", " ") for name in writes)
        for name in writes:
            assert commands[name.replace(".", " ")] == _command(person_ops()[name]).__doc__.split("\n\n")[0]
        assert "agent hold" in commands

        await pilot.press("ctrl+p", *"agent retire")
        await pilot.press("enter")
        await drawn(pilot, lambda text: "agent (needed): An agent, as `@agent`." in text)
        await pilot.press("enter")
        await drawn(pilot, lambda text: "agent retire @lead? It cannot be taken back." in text)
        await pilot.press("y")
        ended = await until(lambda: of_type(owner, "agent.ended"), owner)

        assert [(event.agent, event.data["status"]) for event in ended] == [("lead", "retired")]


async def test_the_palette_offers_no_wait_and_no_query(root):
    """A person holds `wait`, the ops on a wait and every query, as `ops.list` says, and the palette offers none of
    them: a wait parks a turn and a person has none, and a query is what the screen draws and the command line
    prints."""
    async with attached(team(), root) as (owner, app, _):
        held = await owner.ops()
        titles = {title for title, _, _ in workspace(app).commands()}
        left = {entry["name"] for entry in held if entry["query"] or entry["exposes"] or _waits(entry)}

        assert {"wait", "wait.cancel", "wait.progress", "attention.list", "blob.get", "view.watch"} <= left
        assert titles.isdisjoint(name.replace(".", " ") for name in left)


def _waits(entry: dict) -> bool:
    return entry["name"].partition(".")[0] == "wait"


def balloting() -> Team:
    """The team of `team()`, naming an extension no core code knows."""
    return team().model_copy(update={"extensions": (extension(BALLOT),)})


async def test_the_palette_offers_an_extension_s_op_with_no_core_edit_and_never_asks_about_it(root):
    """An op a team's extension adds is in the palette as `ops.list` gives it, worded by its own description, and runs
    through its form with no question, as what is asked about first is the command line's list: the keys sent answer
    the form alone, so a question would have left the vote unsent."""
    async with attached(balloting(), root) as (owner, app, pilot):
        commands = {title: said for title, said, _ in workspace(app).commands()}
        await pilot.press("ctrl+p", *"ballot cast")
        await pilot.press("enter")
        await drawn(pilot, lambda text: "agent (needed): The agent whose work it is on" in text)
        await pilot.press("enter", *"yes", "enter")
        voted = await until(lambda: of_type(owner, "ballot.voted"), owner)
        done = 'ballot cast: done. {"choice":"yes"}'
        await drawn(pilot, lambda _: any(notice.message == done for notice in app._notifications))

    assert commands["ballot cast"] == "Cast a vote on an agent's work, kept among that agent's own events."
    assert [(event.actor, event.data) for event in voted] == [("human:you", {"agent": "@lead", "choice": "yes"})]


async def test_an_extension_s_event_is_drawn_by_its_gist(root):
    """The TUI knows nothing of an extension's event, and draws it by its gist where its stream is shown."""
    async with attached(balloting(), root) as (owner, _, pilot):
        await owner.submit("ballot.cast", agent="@lead", choice="no")

        await drawn(pilot, lambda text: "· a vote on @lead's work: no" in text)


@pytest.mark.parametrize("width", [120, 59])
async def test_the_footer_says_how_to_reach_the_typed_commands_then_the_keymap_table_s_keys(root, width):
    """F1 belongs to the editor in some terminals, and `/` reaches every act in any."""
    async with attached(team(), root, size=(width, 32)) as (_, _, pilot):
        footer = (await drawn(pilot, lambda text: "commands" in text.splitlines()[-1])).splitlines()[-1]

        shown = [key for key in (*keys("everywhere"), *keys("workspace")) if key.footer]
        said = [part for key in shown for part in ((key.shown, key.name) if width >= 60 else (key.shown,))]
        assert footer.split() == ["/", "commands", *said]


async def test_a_transcript_holds_a_window_of_lines_read_from_the_journal_either_way(root, monkeypatch):
    monkeypatch.setattr(transcript_module, "WINDOW", 600)
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 1500)
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 1499" in text)

            await pilot.press("pageup")
            while transcript.blocks[0].event.gist != "note 0":
                transcript.scroll_to(y=0, animate=False, immediate=True, force=True)
                oldest = top_line(transcript)
                await drawn(pilot, lambda text, oldest=oldest: top_line(transcript) == oldest)
                assert len(transcript.blocks) <= 600
            assert transcript.blocks[-1].event.gist == "note 599"

            await post(owner, 5, start=1500)
            while not transcript.following:
                await pilot.press("pagedown", "pagedown", "pagedown", "pagedown")
                await drawn(pilot, lambda text: True)
                assert len(transcript.blocks) <= 600
            assert transcript.blocks[-1].event.gist == "note 1504"

            await pilot.press("pageup", "pageup")
            await pilot.press("ctrl+end")
            await drawn(pilot, lambda text: "note 1504" in text)
            assert transcript.following

            await post(owner, 700, start=1505)
            await drawn(pilot, lambda text: "note 2204" in text)
            assert len(transcript.blocks) <= 600


async def test_the_composer_retargets_recalls_attaches_a_file_and_asks_before_sending_elsewhere(root, tmp_path):
    attachment = tmp_path / "spec.md"
    attachment.write_text("# The spec\n\nAll of it.")
    async with attached(with_notes(team([Say("one")], [Say("two")], [Say("three")])), root) as (owner, app, pilot):
        screen = workspace(app)
        await pilot.press(*"#notes ", *"for the channel", "enter")
        await drawn(pilot, lambda text: "to: #notes" in text)
        assert screen.target == "#notes"

        await pilot.press("up")
        assert screen.query_one(Composer).text == "for the channel"
        await pilot.press("down")
        assert screen.query_one(Composer).text == ""
        await pilot.press(*"a draft", "up")
        assert screen.query_one(Composer).text == "a draft"
        await pilot.press("end", *["backspace"] * 7)

        await pilot.press("alt+f")
        await pilot.press(*str(attachment), "enter")
        await drawn(pilot, lambda text: "+ spec.md" in text)
        await pilot.press(*"@nobody look", "enter")
        await drawn(pilot, lambda text: "goes to #notes, as shown" in text)
        await pilot.press("y")
        await until(lambda: of_type(owner, "message.sent"), owner, lambda sent: len(sent) == 2)

        sent = [event for event in await of_type(owner, "message.sent") if event.actor == "human:you"]
        assert [(event.stream, event.gist) for event in sent] == [
            ("channel/notes", "for the channel"),
            ("channel/notes", "@nobody look (file spec.md)"),
        ]
        assert (await owner.get_body(sent[1].data["body"])) == attachment.read_bytes()


def noting(count: int, *more) -> list[Call]:
    """A turn of the lead's posting `count` notes, then whatever else it does."""
    return [*(Call("message_send", {"to": "#notes", "gist": f"the lead's note {n}"}) for n in range(count)), *more]


async def test_a_channel_s_unread_count_and_a_mention_come_from_the_person_s_marks(root):
    """What you wrote yourself is no line you have not read."""
    mentioning = team(noting(3), [Call("message_send", {"to": "@you", "gist": "a question for you"})])
    async with Session.start(with_notes(mentioning), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "note something")
        await until(lambda: of_type(owner, "turn.ended"), owner)
        await post(owner, 2)
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "#notes 3" in text)
            assert workspace(app).unread["#notes"] == 3
            await pilot.press(*"go", "enter")
            text = await drawn(pilot, lambda text: "a question for you" in text and "⚠ 1 need you" in text)
            assert "@lead@" in text

            head = await owner.head()
            await pilot.press("alt+a")
            await drawn(pilot, lambda text: "⚠ 0 need you" in text)
            await pilot.press("alt+down")
            text = await drawn(pilot, lambda text: "the lead's note 2" in text)
            assert "#notes 3" not in text

        marked = await owner.marks()
        assert marked["inbox/you"] >= marked["channel/notes"] >= head
        assert await owner.head() == head, "reading wrote nothing to the journal"


async def test_a_mark_still_being_written_as_you_leave_is_kept(root, monkeypatch):
    """Leaving takes the screen down, which cancels the workers writing marks, so leaving writes what they had not."""
    real, began, release = session_module._mark, threading.Event(), threading.Event()

    def held(folder: Path, person: str, stream: str, seq: int) -> None:
        if not began.is_set():  # The first write is still under way as you leave.
            began.set()
            release.wait(SECONDS)
        real(folder, person, stream, seq)

    monkeypatch.setattr(session_module, "_mark", held)
    async with Session.start(team(), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        try:
            async with app.run_test(size=(120, 32)) as pilot:
                await drawn(pilot, lambda text: "@lead" in text)
                assert await asyncio.to_thread(began.wait, SECONDS)
                read = dict(workspace(app).marks)
                await pilot.press("ctrl+q")
            marked = await owner.marks()
        finally:
            release.set()

    assert read and marked == read


async def test_an_agent_s_row_counts_what_waits_for_its_next_handover(root):
    lead = {"harness": harness(lambda: ScriptedDriver([[Hang()]])), "delivery": "next-turn"}
    async with attached(Team.model_validate({"roles": {"lead": lead}}), root) as (owner, _, pilot):
        await owner.create_channel("news", "topic", readers=["role:lead"])
        await owner.send("#news", "for the lead's next turn")

        text = await drawn(pilot, lambda text: "↧1" in text)

        assert "@lead" in next(line for line in text.splitlines() if "↧1" in line)


async def test_the_inspector_says_why_an_agent_waits_what_it_runs_on_and_what_it_spent(root):
    async with attached(team([Ask("May I?")]), root) as (_, _, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "May I?" in text)
        await pilot.press("f2")
        text = await drawn(pilot, lambda text: "why asks you to approve" in text)

        for said in (
            "role lead, parent none",
            "harness driver_",
            "model its default",
            "login unknown",
            "operational unverified",
        ):
            assert said in text


async def test_the_inspector_says_an_agent_rests_while_its_harness_has_no_process(root):
    """Ten minutes between turns end a harness's process, and the agent in view says so, and what brings it back."""
    clock = ManualClock(1000.0)
    async with Session.start(team(), name="s", root=root, cwd=root, clock=clock) as owner:
        await in_state(owner, "lead", "idle")
        await asyncio.wait_for(clock.slept_until(1600.0), SECONDS)
        clock.advance(600)
        await until(lambda: of_type(owner, "effect.finished"), owner, lambda done: done[-1].data["kind"] == "rest")
        async with TerminalUI("s").run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            await pilot.press("f2")
            await drawn(pilot, lambda text: "resting: its harness has no process," in text)


async def test_showing_another_focus_draws_only_its_lines(root):
    async with attached(team([Say("words only the lead said")]), root) as (_, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "words only the lead said" in text)

        await pilot.press("alt+down")
        text = await drawn(pilot, lambda text: "@you" in text.splitlines()[1])

        transcript = app.screen.query_one(Transcript)
        assert {id(block) for block, _ in transcript._rows} <= {id(block) for block in transcript.blocks}
        assert "words only the lead said" not in text.partition("│")[2]


def asking() -> Team:
    """A lead that spawns two workers and asks, and workers that each ask: three places to act."""
    spawns = [Call("agent_spawn", {"name": name, "child_role": "worker", "goal": "work"}) for name in ("w1", "w2")]
    return team([*spawns, Ask("May the lead?")], worker=[[Ask("May a worker?")]])


def dock_of(app) -> Dock:
    return app.screen.query_one(Dock)


async def test_alt_a_goes_round_every_place_and_yes_answers_the_one_it_is_at(root):
    async with attached(asking(), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: len(workspace(app)._places(workspace(app).live)) == 3)
        places = [place["id"] for place in workspace(app)._places(workspace(app).live)]

        visited = []
        for _ in range(4):
            await pilot.press("alt+a")
            visited.append(dock_of(app).cursor)
        assert visited == [*places, places[0]]

        await pilot.press("alt+a")
        at = dock_of(app).cursor
        row = dock_of(app).rows.index(next(row for row in dock_of(app).rows if row.key == at))
        gist = workspace(app).live.attention[at]["gist"]
        assert row_text(dock_of(app), row).endswith(f"/yes Allow  /no Deny  /ask Read it whole  {gist}")
        assert next(iter(dock_of(app).render_line(row))).style.reverse
        await pilot.press(*"/yes", "enter")
        resolved = await until(lambda: of_type(owner, "approval.resolved"), owner)
        assert [event.stream for event in resolved] == [at]


def row_text(dock: Dock, index: int) -> str:
    return dock.rows[index].line.plain


async def test_a_daemon_that_keeps_failing_is_a_place_in_the_dock(root, monkeypatch):
    """A courier that fails on every pass hands nothing over, so the dock says so where a quiet session would show."""

    async def broken(kernel) -> float | None:
        raise RuntimeError("no luck")

    async with attached(team([Say("hi")]), root) as (_, app, pilot):
        monkeypatch.setattr(delivery, "_pass", broken)
        await pilot.press(*"go", "enter")
        text = await drawn(pilot, lambda text: "daemon courier failed" in text)

        assert "⚠ daemon courier failed and is restarted with backoff, its traceback in the session folder's" in text
        assert [place["kind"] for place in workspace(app)._places(workspace(app).live)] == ["daemon"]


async def test_an_uncertain_effect_is_settled_from_the_dock_once(root):
    """An answer a crash left in flight, which its harness cannot say landed, waits in the dock with what settles it,
    and `/yes` there says it happened, once."""
    unknown = type("Unknown", (HangsOnAnswers,), {"answer_found": "unknown"})
    await asked_then_crashed(root, lambda: unknown([[Ask("may I?")]]))

    async with Session.resume("s", root=root) as owner:
        rows = await until(owner.attention, owner, lambda rows: _effects(rows))
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "answer uncertain: the runtime restarted" in text)
            while dock_of(app).cursor not in _effects(rows):
                await pilot.press(*"/next-place", "enter")
            await drawn(pilot, lambda text: "/yes It happened  /no It did not  answer uncertain" in text)
            await pilot.press(*"/yes", "enter")
            settled = await until(lambda: of_type(owner, "effect.finished"), owner, lambda found: _said_so(found))
            await until(owner.attention, owner, lambda rows: not _effects(rows))

    assert _said_so(settled) == ["answer finished: human:you says so"]


def _effects(rows: list[dict]) -> list[str]:
    return [row["id"] for row in rows if row["id"].startswith("effect/")]


def _said_so(events: list) -> list[str]:
    return [event.gist for event in events if event.gist.endswith("says so")]


async def test_an_action_that_leaves_arguments_opens_its_op_s_form_prefilled(root):
    """A wake a spent budget refused waits in the dock, and `/yes` there opens `budget set`'s form filled in with what
    its action fixes, the scope and what it was set to, for the person to change, and runs it as the palette's form
    would."""
    limited = Team.model_validate({**team([Say("done")], [Say("again")]).canonical(), "budget": {"turns": 1}})
    async with attached(limited, root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await until(lambda: of_type(owner, "turn.ended"), owner)
        await pilot.press(*"more", "enter")
        await drawn(pilot, lambda text: "budget @lead" in text)
        await pilot.press(*"/next-place", "enter")
        await drawn(pilot, lambda text: "/yes Set the budget  wake of lead refused: over_budget" in text)
        await pilot.press(*"/yes", "enter")
        await drawn(pilot, lambda _: isinstance(app.screen, Form))
        filled = {name: app.screen.query_one(f"#field-{name}", Input).value for name in ("scope", "limits", "estimate")}
        await pilot.press("enter", *'{"turns": 5}', "enter", "enter")
        set_it = (await until(lambda: of_type(owner, "budget.set"), owner, lambda found: len(found) == 2))[-1]
        await until(owner.attention, owner, lambda rows: not rows)

    assert filled == {"scope": "shared", "limits": '{"turns": 1.0}', "estimate": ""}
    assert (set_it.actor, set_it.data["scope"], set_it.data["limits"]) == ("human:you", "shared", {"turns": 5})


async def test_a_chosen_place_shows_its_actions_before_its_gist_so_a_narrow_screen_cuts_only_the_gist(root):
    gist = "Run the migration against the staging database, then the one in production?"
    async with attached(team([Ask(gist), Hang()]), root, size=(80, 32)) as (_, _, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Run the migration" in text)
        await pilot.press(*"/next-place", "enter")
        text = await drawn(pilot, lambda text: "/yes Allow  /no Deny  /ask Read it whole  Run the migration" in text)

        assert gist not in text


async def test_an_approval_s_whole_ask_opens_from_the_dock_before_it_is_answered(root):
    """What follows a gist's 280 characters is what a person most needs to see, so `/ask`, or `a` in the dock, opens
    the whole of it, each line as it was asked and never as Markdown, answering nothing; an ask past what the record
    keeps says where it was cut, and one with no body says that what more it asks is unknown."""
    command = "cd build && " + "make target_%d && " * 40 % tuple(range(40)) + "rm -rf *_old_* ~/.cache"
    big = "y" * (ASK_LIMIT + 10)
    asks = [Ask("Run the build?", body=f"Bash\n{command}"), Ask("Write the big file?", body=big), Ask("Go on?")]
    async with attached(team(asks), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Run the build?" in text)
        await pilot.press("alt+a", *"/ask", "enter")
        await drawn(pilot, lambda _: isinstance(app.screen, Approval))
        text = await drawn(pilot, lambda text: "rm -rf *_old_* ~/.cache" in text)

        assert "What @lead asks" in text and "Bash" in text and "Cut here" not in text
        assert await of_type(owner, "approval.resolved") == []
        await pilot.press("escape", "shift+tab", "down", "a")
        await drawn(pilot, lambda text: "rm -rf *_old_* ~/.cache" in text)
        await pilot.press("escape")
        await drawn(pilot, lambda _: isinstance(app.screen, Workspace))
        await pilot.press("y")
        await drawn(pilot, lambda text: "Write the big file?" in text)
        await pilot.click("#composer")
        await pilot.press("alt+a", *"/ask", "enter")
        await drawn(pilot, lambda text: "yyyy" in text)
        await pilot.press("end")
        await drawn(pilot, lambda text: "Cut here" in text)
        below = " ".join(
            row.line.plain for row in app.screen.query_one(Rows).rows if not row.line.plain.startswith("y")
        )

        assert app.screen.ask.text == "y" * ASK_LIMIT
        assert below == "Cut here: it asks 10 bytes more, which the record does not keep, and Allow allows them too."
        await pilot.press("escape", *"/no", "enter")
        await drawn(pilot, lambda text: "Go on?" in text)
        await pilot.press("alt+a", *"/ask", "enter")
        await drawn(pilot, lambda _: isinstance(app.screen, Approval) and app.screen.ask is not None)
        said = [row.line.plain for row in app.screen.query_one(Rows).rows]
        await pilot.press("escape", *"/yes", "enter")
        resolved = await until(lambda: of_type(owner, "approval.resolved"), owner, lambda found: len(found) == 3)

    assert said == ["Go on?", "What it asks beyond its gist is unknown: the record holds no more of it."]
    assert [event.data["verdict"] for event in resolved] == ["allow", "deny", "allow"]
    assert {event.data["via"] for event in resolved} == {"tui"}


async def test_a_place_another_client_answered_takes_the_cursor_with_it(root):
    """A key meant for the place you were at answers no other, though another took its place at the top."""
    async with attached(asking(), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: len(workspace(app)._places(workspace(app).live)) == 3)
        await pilot.press("alt+a")
        at = workspace(app).live.attention[dock_of(app).cursor]
        second = await Session.attach("s", root=root)
        action = at["actions"][1]
        await second.submit(action["op"], **{**action["args"], "via": "web"})

        await drawn(pilot, lambda text: at["id"] not in dock_of(app).keys)
        assert dock_of(app).cursor is None
        await pilot.press(*"/yes", "enter")
        await drawn(pilot, lambda _: any("Nothing here" in notice.message for notice in app._notifications))

        resolved = await of_type(owner, "approval.resolved")
        assert [(event.stream, event.data["via"]) for event in resolved] == [(at["id"], "web")]
        await second.leave()


def topics(base: Team, **readers: str) -> Team:
    """`base`, with topics that wake nobody, each read by whom it names."""
    given = base.canonical()
    channels = {
        name: {"kind": "topic", "writers": "all", "readers": who, "delivery": "pull"} for name, who in readers.items()
    }
    return Team.model_validate({**given, "topology": {**given.get("topology", {}), "channels": channels}})


async def test_an_unread_count_beyond_a_long_stretch_of_other_streams_is_counted(root):
    """A filtered page scans at most 4,096 events, so a count that read one page, from the mark or back from the
    newest, would say none here."""

    async def others() -> None:
        for first in range(0, 4200, 30):
            await asyncio.gather(*(owner.send("#other", f"other {n}") for n in range(first, first + 30)))

    noted = topics(team(noting(3)), notes="all", other="human")
    async with Session.start(noted, name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        await others()
        await owner.send("@lead", "note something")
        await until(lambda: owner.status(), owner, lambda status: status["settled"])
        await others()
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "#notes 3" in text)

            assert workspace(app).unread["#notes"] == 3


async def test_a_channel_made_and_posted_to_in_one_frame_counts_each_line_once(root):
    making = [
        Call("channel_create", {"name": "late", "kind": "topic"}),
        Call("message_send", {"to": "#late", "gist": "one"}),
        Call("message_send", {"to": "#late", "gist": "two"}),
    ]
    async with attached(team(making), root) as (owner, app, pilot):
        screen = workspace(app)
        live = screen.live
        draw, holding, gate = live._draw, asyncio.Event(), asyncio.Event()

        async def held(events, said):
            holding.set()
            await gate.wait()
            await draw(events, said)

        live._draw = held
        live._dirty.set()
        await holding.wait()  # A frame held before the lead acts, so all it does is read into the next one.
        await owner.send("@lead", "make a channel")
        await until(lambda: of_type(owner, "message.sent"), owner, lambda sent: len(sent) == 3)
        head = await owner.head()
        gate.set()
        await drawn(pilot, lambda text: screen.query_one(Transcript).through >= head)

        assert screen.unread["#late"] == 2


async def test_a_spoiled_marks_file_loses_only_badges(root):
    async with Session.start(team([Say("still here")]), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        (owner.folder / "marks.sqlite").write_bytes(b"this is no database")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text and "Channels" in text)
            await pilot.press(*"go", "enter")
            await drawn(pilot, lambda text: "@lead  still here" in text)

            assert app.is_running
            told = [notice.message for notice in app._notifications]
            assert sum("Your read marks cannot be kept" in said for said in told) == 1


async def test_a_closed_session_in_a_folder_nobody_may_write_opens_as_history(root):
    """A closed session is a portable artifact, opened read-only: its marks go unkept, and that is said."""
    async with Session.start(team([Say("before it closed")]), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "go")
        await until(lambda: of_type(owner, "item.recorded"), owner)
    folder = root / "sessions" / "s"
    folder.chmod(0o500)
    try:
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "before it closed" in text and "history" in text)
            await drawn(pilot, lambda _: any("cannot be kept" in notice.message for notice in app._notifications))
            assert app.is_running
    finally:
        folder.chmod(0o700)


async def test_an_edited_recall_is_a_draft_neither_key_replaces(root):
    async with attached(team([Say("one")], [Say("two")]), root) as (_, app, pilot):
        composer = app.screen.query_one(Composer)
        await pilot.press(*"fix the flaky test", "enter")
        await drawn(pilot, lambda text: "@lead  one" in text)

        await pilot.press("up", *" and the docs", "down")
        assert composer.text == "fix the flaky test and the docs"
        await pilot.press("up")
        assert composer.text == "fix the flaky test and the docs"


async def test_ctrl_d_away_from_the_composer_keeps_a_draft(root):
    async with attached(team(), root) as (_, app, pilot):
        await pilot.press(*"half a thought")
        app.screen.query_one(Transcript).focus()
        await pilot.press("ctrl+d")
        await drawn(pilot, lambda _: any("holds a draft" in notice.message for notice in app._notifications))

        assert app.is_running and app.screen.query_one(Composer).text == "half a thought"


async def test_a_typed_command_never_reaches_an_agent_and_any_other_slash_is_asked_about(root):
    async with attached(team([Say("ok")]), root) as (owner, app, pilot):
        screen = workspace(app)
        await pilot.press(*"/inspector", "enter")
        await drawn(pilot, lambda text: "Choose an agent to see why it waits" in text or "role lead" in text)
        assert screen.has_class("inspector-shown") and screen.query_one(Composer).text == ""
        await pilot.press(*"/yes", "enter")
        await drawn(pilot, lambda _: any("Nothing here" in notice.message for notice in app._notifications))
        await pilot.press("/", "enter")
        await drawn(pilot, lambda text: "/stop-below" in text)
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press(*"/compact", "enter")
        await drawn(pilot, lambda text: "is none of our commands" in text)
        await pilot.press("n")
        await pilot.pause()
        assert [event for event in await of_type(owner, "message.sent") if event.actor == "human:you"] == []

        await pilot.press("enter")
        await drawn(pilot, lambda text: "Send it?" in text)
        await pilot.press("y")
        sent = await until(lambda: of_type(owner, "message.sent"), owner)
        assert [event.gist for event in sent if event.actor == "human:you"] == ["/compact"]
        await pilot.press("up", "up")
        assert screen.query_one(Composer).text == "/"


def drawing(app: TerminalUI, part) -> list:
    """How the screen draws a part, a cell at a time: its text and its style."""
    region = part.region
    update = app.screen._compositor.render_full_update()
    return [list(Strip.join(line).crop(region.x, region.right)) for line in update.strips[region.y : region.bottom]]


async def test_tab_goes_round_the_parts_and_esc_from_one_goes_back_to_the_composer_interrupting_nothing(root):
    """Each part shows that it has focus, the footer names Esc by what it does from there, and `/` from a part begins a
    typed command in the composer."""
    async with attached(team([Ask("Ship the fix?"), Hang()]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Ship the fix?" in text)
        screen = workspace(app)
        composer, transcript, dock = screen.query_one(Composer), screen.query_one(Transcript), dock_of(app)
        navigator = screen.query_one("#navigator")

        visited = []
        for _ in range(4):
            await pilot.press("tab")
            visited.append(app.focused)
        assert visited == [navigator, transcript, dock, composer]
        await pilot.press("shift+tab")
        assert app.focused is dock

        for part, shown in ((navigator, navigator), (transcript, screen.query_one("#focus")), (dock, dock)):
            await pilot.press("escape")
            footer = (await drawn(pilot, lambda text: "Esc interrupt" in text.splitlines()[-1])).splitlines()[-1]
            unfocused, back = drawing(app, shown), footer.replace("Esc interrupt", "Esc back").split()
            part.focus()
            await drawn(pilot, lambda text, back=back: text.splitlines()[-1].split() == back)
            assert drawing(app, shown) != unfocused, f"{part} shows no mark of its focus"
        await pilot.press("escape")
        assert app.focused is composer
        assert await of_type(owner, "turn.ended") == [], "Esc from a part interrupted the agent"

        transcript.focus()
        await pilot.press("slash", *"inspector", "enter")
        await drawn(pilot, lambda _: screen.has_class("inspector-shown"))
        assert app.focused is composer and composer.text == ""


async def test_the_dock_takes_focus_with_no_place_chosen_so_its_letters_answer_only_a_place_chosen_in_it(root):
    """A place chosen from the composer is let go once Tab or Shift+Tab reaches the dock, so a stray one from a draft,
    then the draft going on, answers nothing. A click chooses a place and gives no focus. A dock with nothing left gives
    focus back."""
    async with attached(team([Ask("Ship the fix?"), Hang()]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Ship the fix?" in text)
        composer, dock = app.screen.query_one(Composer), dock_of(app)

        await pilot.press(*"/next-place", "enter", "shift+tab")
        await drawn(pilot, lambda text: CHOOSE in text)
        await pilot.press(*"no rush, yes")
        await drawn(pilot, lambda _: any(CHOOSE in notice.message for notice in app._notifications))
        assert app.focused is dock and dock.cursor is None

        await pilot.press("escape")
        await pilot.click("#dock")
        await pilot.press(*"no wait")
        assert app.focused is composer and composer.text == "no wait" and dock.cursor is not None
        assert await of_type(owner, "approval.resolved") == []

        await pilot.press(*["backspace"] * 7, "shift+tab", "down")
        await drawn(pilot, lambda text: "y Allow  n Deny" in text)
        await pilot.press("n")
        resolved = await until(lambda: of_type(owner, "approval.resolved"), owner)
        assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("deny", "tui")]
        await drawn(pilot, lambda _: app.focused is composer)


async def test_a_part_hidden_while_it_has_focus_gives_focus_back_to_the_composer(root):
    """A resize under 80 columns hides the navigator, which lies over the focus pane there once shown, until Esc or a
    row chosen in it closes it."""
    async with attached(team([Hang()]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await in_state(owner, "lead", "running")
        screen = workspace(app)
        composer, navigator = screen.query_one(Composer), screen.query_one("#navigator")

        await pilot.press("tab")
        assert app.focused is navigator
        await pilot.resize_terminal(79, 32)
        await drawn(pilot, lambda _: app.focused is composer)
        await pilot.press(*"hello")
        assert composer.text == "hello"

        await pilot.press(*["backspace"] * 5, *"/navigator", "enter", "tab")
        assert navigator.display and app.focused is navigator
        await pilot.press("down", "enter")
        await drawn(pilot, lambda _: not navigator.display and app.focused is composer)
        await pilot.press(*"/navigator", "enter", "tab", "escape")
        await drawn(pilot, lambda _: not navigator.display and app.focused is composer)
        assert await of_type(owner, "turn.ended") == [], "Esc from the navigator interrupted the agent"


async def test_body_tombstone_from_the_palette_asks_once(root):
    async with attached(team(), root) as (owner, _, pilot):
        ref = await owner.put_body(b"something to erase")
        await pilot.press("ctrl+p", *"body tombstone")
        await pilot.press("enter")
        await drawn(pilot, lambda text: "sha256:" in text)
        await pilot.press(*ref.removeprefix("sha256:"), "enter")
        await drawn(pilot, lambda text: "cannot be taken back" in text)
        await pilot.press("n")
        await pilot.pause()

        assert await of_type(owner, "body.tombstoned") == []


async def test_a_body_field_cites_a_ref_as_it_stands_and_stores_any_other_text(root):
    """A form's body takes what the command line's flag takes: a body's ref, which it cites, or any other text, which
    it stores as a body of its own."""
    async with attached(team(), root) as (owner, _, pilot):
        cited = await owner.put_body(b"stored before")
        for gist, body in (("cited", cited), ("stored", "The whole of it.")):
            await pilot.press("ctrl+p", *"message send")
            await pilot.press("enter")
            await drawn(pilot, lambda text: "Anything longer than the gist." in text)
            await pilot.press("enter", *gist, "enter", *body, "enter", "enter", "enter", "enter")
            sent = await until(
                lambda: of_type(owner, "message.sent"), owner, lambda found, gist=gist: gist in [e.gist for e in found]
            )

        bodies = [await owner.get_body(event.data["body"]) for event in sent if event.actor == "human:you"]
        assert bodies == [b"stored before", b"The whole of it."]


async def test_a_yes_or_no_field_takes_only_yes_or_no(root):
    async with attached(team(), root) as (_, app, _):
        interrupt = next(form for form in workspace(app).forms if form.op == "agent.interrupt")
        below = next(field for field in interrupt.fields if field.name == "below")

        assert (_value(below, "yes"), _value(below, "No"), _value(below, "1")) == (True, False, True)
        with pytest.raises(ValueError, match="below is yes or no"):
            _value(below, "ture")


async def test_a_field_says_whether_it_is_needed_what_it_takes_and_what_stands_left_empty_as_the_page_does(root):
    """The terminal's form asks for a field as the page's shows it: whether it is needed, the choices it takes, which
    are all it takes, and the op's own default, which stands for it left empty."""
    async with attached(team(), root) as (_, app, _):
        forms = {form.op: {field.name: field for field in form.fields} for form in workspace(app).forms}
        kind = forms["channel.create"]["kind"]

        assert _asked(kind) == "kind (needed): What sort of channel this is. One of topic, queue, board."
        assert _asked(forms["budget.set"]["scope"]).endswith(" Left empty: shared.")
        assert _asked(forms["agent.interrupt"]["below"]).endswith(" One of yes, no. Left empty: no.")
        assert _value(kind, "queue") == "queue"
        with pytest.raises(ValueError, match="--kind is one of topic, queue, board"):
            _value(kind, "forum")


async def test_the_palette_says_what_an_op_answered(root):
    """Done, with the op's answer as the page and the command line give it, so a person sees the task or ref they
    made."""
    async with attached(team(), root) as (owner, app, pilot):
        await pilot.press("ctrl+p", *"channel create")
        await pilot.press("enter")
        await drawn(pilot, lambda text: "What sort of channel this is." in text)
        await pilot.press(*"ideas", "enter", *"topic", "enter", "enter", "enter", "enter")
        await until(lambda: of_type(owner, "channel.created"), owner)
        done = 'channel create: done. {"name":"#ideas","kind":"topic"}'
        await drawn(pilot, lambda _: any(notice.message == done for notice in app._notifications))


async def test_ctrl_home_goes_to_the_start_of_the_transcript(root):
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 1500)
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 1499" in text)

            await pilot.press("ctrl+home")
            await drawn(pilot, lambda text: "note 0" in text)
            assert top_line(transcript).strip().endswith("note 0") and not transcript.following

            await pilot.press("ctrl+end")
            await drawn(pilot, lambda text: "note 1499" in text)
            assert transcript.following


async def test_live_text_goes_with_the_runtime_that_said_it(root):
    """What a harness was saying when its runtime went is said no more, and the next runtime's text stands alone."""
    async with attached(team(), root) as (owner, app, pilot):
        transcript = app.screen.query_one(Transcript)
        owner._runtime.kernel.push_delta("lead", "I will now run the te")
        await drawn(pilot, lambda text: "I will now run the te" in text)

        await owner.leave()
        await drawn(pilot, lambda text: "this is its history" in text)
        assert transcript._tail_text == ""

        async with Session.resume("s", root=root) as again:
            await in_state(again, "lead", "idle")
            await drawn(pilot, lambda text: "this is its history" not in text, within=30)
            again._runtime.kernel.push_delta("lead", "Resuming where I was.")
            await drawn(pilot, lambda text: "Resuming where I was." in text)
            assert transcript._tail_text == "Resuming where I was."


async def test_the_header_says_what_changed_and_each_limit_in_a_few_characters(root):
    """A session whose cwd is in no repository observes no change, which is said. Each shared limit shows what is
    spent against it, and how many turns nobody measured whole is said once."""
    given = team([Say("done")]).canonical()
    limited = Team.model_validate({**given, "budget": {"turns": 8, "tokens": 1000, "estimate": {"tokens": 10}}})
    async with attached(limited, root, size=(140, 32)) as (_, _, pilot):
        await pilot.press(*"go", "enter")
        header = (await drawn(pilot, lambda text: "turns 1/8" in text.splitlines()[0])).splitlines()[0]

        assert "changes not observed" in header and "/1,000" in header
        assert "turns unmeasured" not in header
        assert header.rstrip().endswith(("1 turn unmeasured)", "/1,000", "turns 1/8"))


async def test_provenance_given_a_ref_opens_it_or_says_why_not(root):
    """`/provenance` opens its form, filled in with the chosen line's ref, which a person sends as it is or changes: a
    ref that names an event opens its panel, as a link followed does, one that names none opens one that says why, and
    with none given nothing opens, saying why."""
    async with attached(team([Say("on it")]), root) as (_, app, pilot):
        await pilot.press(*"fix the flaky test", "enter")
        await drawn(pilot, lambda text: "@lead  on it" in text)
        chosen = app.screen.query_one(Transcript).chosen
        assert chosen is not None
        filled, opened = [], {}
        for given in (None, "inbox/lead@1", "nothing/here@1", ""):
            await pilot.press("slash", *"provenance", "enter")
            await drawn(pilot, lambda _: isinstance(app.screen, Form))
            filled.append(app.screen.query_one(Input).value)
            await pilot.press(*(() if given is None else ("home", "ctrl+k", *given)), "enter")
            if given == "":
                await drawn(pilot, lambda _: any("No ref was given" in notice.message for notice in app._notifications))
                continue
            await drawn(pilot, lambda _: isinstance(app.screen, Provenance) and app.screen.lines)
            opened[given] = app.screen.lines[0]
            await pilot.press("escape")
            await drawn(pilot, lambda _: not isinstance(app.screen, Provenance))
        left = app.screen

    assert filled == [shows(chosen.event)] * 4
    assert opened[None].text.startswith(f"{chosen.event.type} {shows(chosen.event)}: on it")
    assert opened["inbox/lead@1"] == Line("", "message.sent inbox/lead@1: fix the flaky test")
    missing = "nothing/here@1 has no provenance to show: not_found: nothing is nothing/here@1"
    assert opened["nothing/here@1"] == Line("", missing, warn=True)
    assert isinstance(left, Workspace), "a form sent with no ref opens nothing"


async def test_find_goes_back_a_page_at_a_time_to_the_next_line_whose_words_match(root, monkeypatch):
    """`/find`, or Ctrl+F, opens a form for the words, filled in with the last ones found. Sent, the transcript takes
    focus and chooses the line before the chosen one whose words hold them, whatever their case and spacing, read back
    from the journal a page at a time and keeping its window, or says none does and goes back to the line it began
    from."""
    monkeypatch.setattr(transcript_module, "WINDOW", 600)
    paging, reads = transcript_module.page_of, []

    async def page_of(session, focus, *, after=0, before=None):
        reads.append(before)
        return await paging(session, focus, after=after, before=before)

    monkeypatch.setattr(transcript_module, "page_of", page_of)
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 40)
        await owner.send("#notes", "a Needle in the hay")
        await post(owner, 1400, start=40)
        await owner.send("#notes", "the needle again")
        await post(owner, 60, start=1440)
        await in_state(owner, "lead", "idle")
        head = await owner.head()
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 1499" in text)

            async def find(*typed: str, holds) -> str:
                await pilot.press("ctrl+f")
                await drawn(pilot, lambda _: isinstance(app.screen, Form))
                filled = app.screen.query_one(Input).value
                await pilot.press(*typed, "enter")
                await drawn(pilot, lambda text: isinstance(app.screen, Workspace) and holds(text))
                return filled

            def chosen() -> str:
                assert transcript.chosen is not None
                return transcript.chosen.event.gist

            assert await find(*"needle", holds=lambda _: chosen() == "the needle again") == ""
            assert app.focused is transcript and not transcript.following

            reads.clear()
            filled = await find("home", "ctrl+k", *"NEEDLE   in", holds=lambda _: chosen() == "a Needle in the hay")
            await drawn(pilot, lambda text: "a Needle in the hay" in text)
            assert filled == "needle"
            assert len(reads) >= 1400 // transcript_module.PAGE and None not in reads, "it read back a page at a time"
            assert len(transcript.blocks) <= 600

            said = "No line before the chosen one holds “NEEDLE   in”, back to the first line of #notes."
            await find(holds=lambda _: any(notice.message == said for notice in app._notifications))
            assert chosen() == "a Needle in the hay"

        moved = [event.type async for event in owner.events(head) if event.actor == "human:you"]
        assert moved == [], "finding did something"


async def test_a_thread_opens_on_its_message_and_the_composer_replies_in_it(root):
    """`/thread` shows the chosen line's message's thread, every message sent in it on any inbox or channel, and the
    composer answers that message where the page's Reply sends one: in its channel, or back to whom it came from. What
    an agent says in its turn is no message, and has no thread."""
    asked = Call("message_send", {"to": "#notes", "gist": "a question on the plan", "reply_to": "channel/notes@1"})
    told = Call("message_send", {"to": "@you", "gist": "and one for you"})
    async with Session.start(with_notes(team([asked, told, Say("asked")])), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        assert (await owner.send("#notes", "the plan"))["ref"] == "channel/notes@1"
        await owner.send("#notes", "unrelated")
        await owner.send("@lead", "go")
        await until(lambda: of_type(owner, "turn.ended"), owner)
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead  asked" in text)
            screen = workspace(app)
            transcript = screen.query_one(Transcript)

            await pilot.press(*"/thread", "enter")
            said = await drawn(
                pilot, lambda _: any("Only a message" in notice.message for notice in app._notifications)
            )
            assert "@lead" in said.splitlines()[1]

            await show_notes(pilot)
            await drawn(pilot, lambda text: "a question on the plan" in text)
            transcript.focus()
            await pilot.press("up", "up", "slash", *"thread", "enter")
            text = await drawn(pilot, lambda text: "Thread channel/notes@1" in text)
            assert "to: #notes  replying to @you" in text
            assert [block.line.plain for block in transcript.blocks] == [
                "@you → #notes  the plan",
                "@lead → #notes  a question on the plan",
            ]

            await pilot.press(*"agreed", "enter")
            await drawn(pilot, lambda text: "@you → #notes  agreed" in text)

            await pilot.press("alt+up")
            await drawn(pilot, lambda text: "and one for you" in text)
            await pilot.press(*"/thread", "enter")
            text = await drawn(pilot, lambda text: "Thread inbox/you@" in text)
            assert "to: @lead  replying to @lead" in text
            await pilot.press(*"thanks", "enter")
            await drawn(pilot, lambda text: "@you → @lead  thanks" in text)

        sent = [event for event in await of_type(owner, "message.sent") if event.actor == "human:you"]
        replies = [(event.stream, event.gist, event.data["reply_to"], event.data["thread"]) for event in sent[3:]]
        to_you = next(event for event in await of_type(owner, "message.sent") if event.gist == "and one for you")
        assert replies == [
            ("channel/notes", "agreed", "channel/notes@1", "channel/notes@1"),
            ("inbox/lead", "thanks", shows(to_you), shows(to_you)),
        ]


async def test_copy_sends_the_chosen_line_s_text_as_osc_52_with_no_escape_in_it(root):
    """`/copy` sends the chosen line's text as the transcript shows it, and once the line is open the text it opens on,
    as text, each control shown as its escape, so pasting it acts on no terminal, or its gist while that is still being
    read, saying so. It says that whether it reaches the clipboard is the terminal's."""
    body = f"# a heading\n\n{HOSTILE}\n\x1b[31mred\x1b[0m"
    async with attached(with_notes(team()), root) as (owner, app, pilot):
        written: list[str] = []
        app._driver.write = written.append  # type: ignore[union-attr]
        await owner.send("#notes", HOSTILE, body=body.encode())
        await show_notes(pilot)
        await drawn(pilot, lambda text: "\\x1b]0;owned" in text)

        def copied() -> list[str]:
            sent = re.findall("\x1b\\]52;c;([A-Za-z0-9+/=]*)\x07", "".join(written))
            return [base64.b64decode(said).decode() for said in sent]

        await pilot.press(*"/copy", "enter")
        await drawn(pilot, lambda _: len(copied()) == 1)
        await pilot.press(*"/open-line", "enter")
        await drawn(pilot, lambda text: "a heading" in text)
        await pilot.press(*"/copy", "enter")
        await drawn(pilot, lambda _: len(copied()) == 2)
        chosen = app.screen.query_one(Transcript).chosen
        assert chosen is not None
        chosen.text = None  # As while its body is being read.
        await pilot.press(*"/copy", "enter")
        await drawn(pilot, lambda _: len(copied()) == 3)
        notices = [notice.message for notice in app._notifications]

    line = f"@you → #notes  {safe(HOSTILE)} ▸"
    assert copied() == [line, f"{line}\n{safe(body)}", f"{line}\n{safe(HOSTILE)}"]
    assert not [char for char in UNSAFE if char in "".join(copied())]
    terminal_s = "whether they reach your clipboard is your terminal's."
    assert f"Sent the chosen line's {len(line)} characters as OSC 52: {terminal_s}" in notices
    reading = "What it opens on is still being read, so its gist went in its place: /copy again once that shows."
    assert notices[-1] == f"Sent the chosen line's {len(copied()[2])} characters as OSC 52: {terminal_s} {reading}"
