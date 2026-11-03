"""The workspace on scripted harnesses: a session the test owns, and the TUI attached to it as a guest over its
socket."""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from rich.cells import cell_len

from platoon_harness import Session, Team
from platoon_harness.testing import Ask, Call, Hang, Say, ScriptedDriver
from platoon_harness_cli.ops import _command, person_ops
from platoon_harness_cli.tui import live as live_module
from platoon_harness_cli.tui import transcript as transcript_module
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.composer import Composer
from platoon_harness_cli.tui.keymap import keys
from platoon_harness_cli.tui.transcript import Transcript
from platoon_harness_cli.tui.workspace import Dock

from ..runtime.support import harness, in_state, of_type, until
from .support import drawn, workspace

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

        await pilot.press(*"yes", "y", "n", "alt+y")

        assert app.focused is composer and composer.text == "yesyn"
        assert await of_type(owner, "approval.resolved") == [], "a place nobody chose answered a key"

        await pilot.press("alt+a", "alt+y")
        await drawn(pilot, lambda text: "shipped" in text)

        resolved = await of_type(owner, "approval.resolved")
        assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("allow", "tui")]
        assert app.focused is composer


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
        await pilot.press("alt+y")
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

        await pilot.press("alt+s")
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


async def test_the_palette_s_session_commands_are_the_command_line_s_worded_for_a_person(root):
    """Each command a person may run, as the command line words it, but a takeover, whose terminal is not built. A read
    is what the screen draws, so the palette offers none."""
    async with attached(team(), root) as (owner, app, pilot):
        commands = {title: said for title, said, _ in workspace(app).commands()}
        for name, operation in person_ops().items():
            title = name.replace(".", " ")
            if operation.query or operation.exposes:
                assert title not in commands
            elif name == "agent.takeover":
                assert commands[title].startswith("Not built yet: driving an agent's own terminal is planned")
            else:
                assert commands[title] == _command(operation).__doc__.split("\n\n")[0]

        await pilot.press("ctrl+p", *"agent retire")
        await pilot.press("enter")
        await drawn(pilot, lambda text: "agent:" in text)
        await pilot.press("enter")
        await drawn(pilot, lambda text: "cannot be taken back" in text)
        await pilot.press("y")
        ended = await until(lambda: of_type(owner, "agent.ended"), owner)

        assert [(event.agent, event.data["status"]) for event in ended] == [("lead", "retired")]


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
            ("channel/notes", "@nobody look"),
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


async def test_the_inspector_says_why_an_agent_waits_what_it_runs_on_and_what_it_spent(root):
    async with attached(team([Ask("May I?")]), root) as (_, _, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "May I?" in text)
        await pilot.press("f2")
        text = await drawn(pilot, lambda text: "why asks you to approve" in text)

        for said in ("role lead, parent none", "harness driver_", "model its default", "operational unverified"):
            assert said in text


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


async def test_alt_a_goes_round_every_place_and_alt_y_answers_the_one_it_is_at(root):
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
        assert "Alt+Y or /yes Allow" in row_text(dock_of(app), row)
        assert next(iter(dock_of(app).render_line(row))).style.reverse
        await pilot.press("alt+y")
        resolved = await until(lambda: of_type(owner, "approval.resolved"), owner)
        assert [event.stream for event in resolved] == [at]


def row_text(dock: Dock, index: int) -> str:
    return dock.rows[index].line.plain


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
        await pilot.press("alt+y")
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


def test_a_yes_or_no_field_takes_only_yes_or_no():
    from platoon_harness_cli.ops import flags
    from platoon_harness_cli.tui.workspace import _value

    below = next(field for field in flags(person_ops()["agent.interrupt"]) if field.name == "below")

    assert (_value(below, "yes"), _value(below, "No"), _value(below, "1")) == (True, False, True)
    with pytest.raises(ValueError, match="below is yes or no"):
        _value(below, "ture")


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
    """Nothing measures what changed yet, which is said. Each shared limit shows what is spent against it, and how
    many turns nobody measured whole is said once."""
    given = team([Say("done")]).canonical()
    limited = Team.model_validate({**given, "budget": {"turns": 8, "tokens": 1000, "estimate": {"tokens": 10}}})
    async with attached(limited, root, size=(140, 32)) as (_, _, pilot):
        await pilot.press(*"go", "enter")
        header = (await drawn(pilot, lambda text: "turns 1/8" in text.splitlines()[0])).splitlines()[0]

        assert "changes not measured" in header and "/1,000" in header
        assert "turns unmeasured" not in header
        assert header.rstrip().endswith(("1 turn unmeasured)", "/1,000", "turns 1/8"))
