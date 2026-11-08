"""A list of rows alone, in an app of its own."""

from textual.app import App, ComposeResult
from textual.content import Content

from platoon_harness_cli.tui.rows import SPIN, SPINNER, Row, Rows


class Alone(App[None]):
    def compose(self) -> ComposeResult:
        yield Rows()


async def test_a_scrollbar_shown_once_a_row_is_chosen_is_drawn_at_that_row():
    app = Alone()
    async with app.run_test(size=(40, 5)) as pilot:
        rows = app.query_one(Rows)

        rows.show([Row(Content(f"row {n}"), key=str(n)) for n in range(20)])
        rows.move_to("19")
        await pilot.pause()

        assert rows.scroll_y == rows.max_scroll_y > 0
        assert rows.vertical_scrollbar.position == rows.scroll_y


async def test_a_working_row_s_glyph_turns_while_animation_is_on_and_stands_still_with_it_off():
    """The spinner decides nothing: it turns the glyph of a row that spins, and its timer goes once none does."""
    app = Alone()
    async with app.run_test(size=(40, 5)) as pilot:
        rows = app.query_one(Rows)
        working = [Row(Content.assemble(("● ", "green"), "@lead"), "@lead", lead=2, spins=True)]
        rows.show(working)
        turned = {rows.render_line(0).text[0]}
        for _ in range(3):
            await pilot.pause(SPIN)
            turned.add(rows.render_line(0).text[0])
        rows.show([Row(Content("○ @lead"), "@lead", lead=2)])
        stopped = rows._spinning is None
        app.animation_level = "none"
        rows.show(working)

        assert turned <= set(SPINNER) and len(turned) > 1 and stopped
        assert rows._spinning is None and rows.render_line(0).text[0] == "●"
