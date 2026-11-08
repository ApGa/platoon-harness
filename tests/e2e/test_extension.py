"""The sample extension package, `examples/extension-package`, in SwarmChat's page in a real browser, which has no code
for it: its op run from Commands through its form, and its vote, opened in the Provenance pane, drawn by its gist. The
sample is loaded from its source, as this environment does not install it, and
`tests/integration/test_installed_extensions.py` installs its wheel."""

from pathlib import Path

import pytest
from playwright.async_api import Browser, expect

from platoon_harness import Session

from ..unit.runtime.support import in_state, of_type, until
from .support import SECONDS, opened, serving
from .test_acts import acting, fill, form

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

SOURCE = Path(__file__).parents[2] / "examples" / "extension-package" / "src"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.syspath_prepend(SOURCE)
    return tmp_path


async def test_the_sample_s_op_runs_from_the_page_s_form_and_its_event_opens_in_the_provenance_pane(
    browser: Browser, root: Path
):
    """`ballot cast` is among Commands, worded by the sample's docstring, and runs through its form with no question.
    Its vote, on `lead`'s stream, opens in the Provenance pane, whose first line is the event by its type, its ref and
    its gist."""
    team = acting().model_copy(update={"extensions": ("ballot:extension",)})
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "lead", "idle")
        link = web.link("control")
        page, errors = await opened(browser, link)
        await form(page, "ballot cast")
        about = await page.locator("#pane .x-about").text_content()
        await fill(page, {"--agent": "@lead", "--choice": "yes"})
        await page.locator("#pane [data-x-run]").click()
        await expect(page.locator("#pane .x-said")).to_have_text('ballot cast: done. {"choice":"yes"}', timeout=SECONDS)
        asked = await page.locator(".x-ask").count()
        [voted] = await until(lambda: of_type(session, "ballot.voted"), session)
        ref = f"{voted.stream}@{voted.version}"
        await page.goto(f"{link.partition('#')[0]}#provenance={ref}")
        await expect(page.locator("#pane h2")).to_have_text(f"Provenance of {ref}", timeout=SECONDS)
        first = page.locator("#pane .x-provenance .x-line").first
        await expect(first).to_have_text(f"ballot.voted {ref}: a vote on @lead's work: yes", timeout=SECONDS)
        await page.context.close()

    assert about == (
        "Cast a vote on an agent's work, kept among that agent's own events. Refused `not_found` when there is no such "
        "agent, and `conflict` when you have voted on its work already."
    )
    assert asked == 0
    assert (voted.actor, voted.stream, voted.data) == ("human:you", "agent/lead", {"agent": "@lead", "choice": "yes"})
    assert errors == []
