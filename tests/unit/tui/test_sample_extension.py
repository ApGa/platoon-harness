"""The sample extension package, `examples/extension-package`, in the terminal UI, which has no code for it: its op run
from the palette through its form, and its vote drawn by its gist. The sample is loaded from its source, as this
environment does not install it, and `tests/integration/test_installed_extensions.py` installs its wheel."""

from pathlib import Path

import pytest

from ..runtime.support import of_type, until
from .support import drawn, workspace
from .test_workspace import attached, team

pytestmark = pytest.mark.timeout(60)

SOURCE = Path(__file__).parents[3] / "examples" / "extension-package" / "src"


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.syspath_prepend(SOURCE)
    return tmp_path


async def test_the_sample_s_op_runs_from_the_palette_and_its_event_is_drawn_by_its_gist(root):
    """`ballot cast`, worded by the sample's docstring, runs through its form, which takes `@lead` from where you are,
    with no question; and the vote, on `lead`'s stream, is drawn in its transcript by its gist."""
    balloting = team().model_copy(update={"extensions": ("ballot:extension",)})
    async with attached(balloting, root) as (owner, app, pilot):
        commands = {title: said for title, said, _ in workspace(app).commands()}
        await pilot.press("ctrl+p", *"ballot cast")
        await pilot.press("enter")
        await drawn(pilot, lambda text: "agent (needed): The agent whose work it is on, as `@agent`." in text)
        await pilot.press("enter", *"yes", "enter")
        voted = await until(lambda: of_type(owner, "ballot.voted"), owner)
        await drawn(pilot, lambda text: "· a vote on @lead's work: yes" in text)

    assert commands["ballot cast"] == "Cast a vote on an agent's work, kept among that agent's own events."
    assert [(event.actor, event.stream, event.data) for event in voted] == [
        ("human:you", "agent/lead", {"agent": "@lead", "choice": "yes"})
    ]
