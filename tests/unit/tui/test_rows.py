"""A list of rows alone, in an app of its own."""

from textual.app import App, ComposeResult
from textual.content import Content

from platoon_harness_cli.tui.rows import Row, Rows


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


async def test_a_selection_copies_a_row_s_words_without_what_leads_them_and_a_row_cut_short_whole():
    app = Alone()
    async with app.run_test(size=(20, 5)) as pilot:
        rows = app.query_one(Rows)
        rows.show(
            [
                Row(Content("● @lead"), "@lead", lead=2),
                Row(Content("  idle · pi · reading a file far too long to show"), "@lead", lead=2),
                Row(Content("channels")),
            ]
        )
        await pilot.mouse_down(Rows, offset=(0, 0))
        await pilot.hover(Rows, offset=(4, 2))
        await pilot.mouse_up(Rows, offset=(4, 2))

        assert app.screen.get_selected_text() == "@lead\nidle · pi · reading a file far too long to show\nchann"
