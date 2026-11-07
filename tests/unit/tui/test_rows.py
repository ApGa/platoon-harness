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
