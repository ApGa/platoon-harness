"""`/provenance` on a session of scripted harnesses: the chosen line's sources, its uses and its contributors, each link
labelled by how it is known, followed a hop at a time and back, and what estimators said of it, by producer and
version."""

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness import Session, Team
from platoon_harness.testing import Call, Say
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.composer import Composer
from platoon_harness_cli.tui.provenance import Provenance
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.transcript import Focus, Transcript

from ..runtime.support import in_state, of_type, scripted, until
from .support import drawn, workspace

pytestmark = pytest.mark.timeout(60)

ASKED = "inbox/lead@1"
"""The person's message that wakes `lead`, which its answer replies to and cites."""
ANSWER = {"to": "@you", "gist": "the tests pass", "reply_to": ASKED, "based_on": [ASKED]}
ANSWERED = "inbox/you@1"
SPAWN = {"name": "w", "child_role": "worker", "goal": "fix the parser"}


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def team(*turns) -> Team:
    """`lead`, on `turns`, which may start a `worker` that finishes with its report."""
    lead = {"harness": scripted(*turns), "may_spawn": ["worker"]}
    finishing = [Say("parser fixed"), Call("agent_finish", {"gist": "the parser is fixed"})]
    worker = {"harness": scripted(finishing), "count": 0}
    topology = {"edges": {"lead": ["children", "human"]}, "limits": {"max_depth": 1, "max_hops": 4}}
    return Team.model_validate({"roles": {"lead": lead, "worker": worker}, "topology": topology})


@contextlib.asynccontextmanager
async def answered(root: Path, *turns) -> AsyncIterator[tuple[Session, TerminalUI, object]]:
    """A session whose `lead`, woken by the person's message, has taken its turns, with the TUI attached."""
    async with Session.start(team(*turns), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "check the tests")
        await until(owner.status, owner, lambda status: status["settled"])
        app = TerminalUI("s")
        async with app.run_test(size=(140, 40)) as pilot:
            await drawn(pilot, lambda text: "check the tests" in text)
            yield owner, app, pilot


async def choose(pilot, app: TerminalUI, said: str) -> None:
    """Choose the transcript's line that says `said`, with the arrows, as a person would."""
    transcript = app.screen.query_one(Transcript)
    transcript.focus()
    while said not in (transcript.chosen.line.plain if transcript.chosen else ""):
        await pilot.press("up")


async def asked(pilot, ref: str) -> str:
    """Run `/provenance` from the part with focus, as the plain keys a person types, and say what its panel says of
    `ref` once it has drawn it."""
    await pilot.press("slash", *"provenance", "enter")
    await drawn(pilot, lambda text: f"Provenance of {ref}" in text and "Credit and rewards" in text)
    return said(pilot.app)


def panel(app: TerminalUI) -> Provenance:
    screen = app.screen
    assert isinstance(screen, Provenance), type(screen)
    return screen


def chosen(app: TerminalUI) -> str:
    """What the panel's chosen link says, all its rows."""
    rows = app.screen.query_one(Rows)
    return " ".join(" ".join(row.line.plain.split()) for row in rows.rows if row.key == rows.cursor)


async def pick(pilot, app: TerminalUI, said: str) -> None:
    """Choose the panel's link that says `said`, with the arrows."""
    seen = set()
    while said not in chosen(app):
        assert chosen(app) not in seen, f"no link says {said!r}"
        seen.add(chosen(app))
        await pilot.press("down")


def said(app: TerminalUI) -> str:
    """What the panel says, a line each, each with the kind of link it is."""
    return "\n".join(f"{line.kind} {line.text}".strip() for line in panel(app).lines)


async def test_provenance_on_a_chosen_line_shows_sources_uses_and_contributors_each_labelled(root):
    async with answered(root, [Call("message_send", ANSWER)]) as (_, app, pilot):
        await choose(pilot, app, "check the tests")
        text = await asked(pilot, ASKED)
        links = [(line.kind, line.ref) for line in panel(app).lines if line.ref is not None]

    assert text.startswith("message.sent inbox/lead@1: check the tests")
    for words in (
        "heading Sources\nmade by @you\nlineage read at head",
        "heading Uses\nuses read at head",
        "1 citing it, 1 following from it, 0 after it, and handed to 1 agent",
        "observed @lead by context/lead@",
        "and its harness said it took it",
        f"declared {ANSWERED} message.sent by @lead: the tests pass",
        f"cause {ANSWERED} message.sent by @lead: the tests pass",
        "heading Contributors\ncontributors read at head",
        "weighing and ranking nobody",
        "@you: made it, 1 event, the first inbox/lead@1, 0 hops back",
        "no estimator has said anything of it",
    ):
        assert words in text, words
    assert [(kind, ref.partition("@")[0]) for kind, ref in links] == [
        ("observed", "context/lead"),
        ("declared", ANSWERED.partition("@")[0]),
        ("cause", ANSWERED.partition("@")[0]),
        ("", "inbox/lead"),
    ]


async def test_following_an_edge_shows_its_lineage_and_escape_comes_back(root):
    async with answered(root, [Call("message_send", ANSWER)]) as (_, app, pilot):
        await choose(pilot, app, "check the tests")
        await asked(pilot, ASKED)
        await pick(pilot, app, f"declared {ANSWERED}")
        await pilot.press("enter")
        await drawn(pilot, lambda text: f"Provenance of {ANSWERED}, 1 hop" in text and "Credit" in text)
        followed = said(app)
        await pilot.press("escape")
        await drawn(pilot, lambda text: f"Provenance of {ASKED}" in text and "Credit" in text)
        back, again = said(app), chosen(app)
        await pilot.press("escape")
        await drawn(pilot, lambda _: not isinstance(app.screen, Provenance))
        left = app.focused

    for words in (
        f"message.sent {ANSWERED}: the tests pass",
        "made by @lead in turn t1-",
        "no model call is joined: no tool call's id came with it",
        "counting what was handed over below its commit, at seq",
        "declared inbox/lead@1 by @you: check the tests; seen: wake context/lead@",
        "taken by turn_start",
        "cause inbox/lead@1 message.sent by @you: check the tests",
        "@lead was handed 2 offers below the bound, 2 said taken and 0 never",
        "@lead: made it, 1 event, the first inbox/you@1, 0 hops back",
        "@you: declared, cause, 1 event, the first inbox/lead@1, 1 hop back",
    ):
        assert words in followed, words
    assert "message.sent inbox/lead@1: check the tests" in back and f"declared {ANSWERED}" in again
    assert isinstance(left, Composer), "the panel was opened from the composer, which a typed command runs in"


async def test_a_carried_message_opens_on_what_it_carries(root):
    async with answered(root, [Call("agent_spawn", SPAWN)]) as (owner, app, pilot):
        report = next(event for event in await of_type(owner, "message.sent") if event.data["carries"])
        carried = report.data["carries"]
        await drawn(pilot, lambda text: "the parser is fixed" in text)
        await choose(pilot, app, "the parser is fixed")
        text = await asked(pilot, carried)

    assert carried.startswith("agent/w@") and f"{report.stream}@{report.version}" != carried
    assert text.startswith(f"agent.finished {carried}: ")
    assert "made by @w in turn" in text
    assert f"cause {report.stream}@{report.version} message.sent by @w: the parser is fixed" in text


async def test_a_line_with_no_event_says_why(root):
    async with answered(root, [Call("message_send", ANSWER)]) as (_, app, pilot):
        screen = workspace(app)
        await screen.show(Focus.of_agent("nobody"))
        await drawn(pilot, lambda _: not screen.query_one(Transcript).blocks)

        await pilot.press("slash", *"provenance", "enter")
        await drawn(pilot, lambda _: any("No line is chosen" in notice.message for notice in app._notifications))

        assert not isinstance(app.screen, Provenance)
        assert app.focused is app.screen.query_one(Composer)
    said = next(notice.message for notice in app._notifications if "No line is chosen" in notice.message)
    assert "What an agent is saying now is no event until the journal holds it." in said


async def test_credit_is_shown_only_as_what_each_estimator_said_by_its_producer_and_version(root):
    async with answered(root, [Call("message_send", ANSWER)]) as (owner, app, pilot):
        head = await owner.head()
        common = {"kind": "credit", "scope": "team", "head_seq": head}
        await owner.annotate(ASKED, producer="even-split", producer_version="0", status="scored", value=0.5, **common)
        await owner.annotate(ASKED, producer="judge", producer_version="2", status="unscored", **common)
        await choose(pilot, app, "check the tests")
        text = await asked(pilot, ASKED)

    assert f"credit 0.5 by even-split 0, team, of the trace at head {head:,}" in text
    assert f"credit no value, unscored, by judge 2, team, of the trace at head {head:,}" in text
    assert "each an estimate by its producer at its version" in text
    assert " 0.5 " not in text.replace("credit 0.5 by", "")


async def test_provenance_reads_a_session_s_history_as_it_reads_a_live_one(root):
    async with Session.start(team([Call("message_send", ANSWER)]), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "check the tests")
        await until(owner.status, owner, lambda status: status["settled"])
    app = TerminalUI("s")
    async with app.run_test(size=(140, 40)) as pilot:
        await drawn(pilot, lambda text: "check the tests" in text and "history" in text)
        await choose(pilot, app, "check the tests")
        text = await asked(pilot, ASKED)

    assert f"declared {ANSWERED} message.sent by @lead" in text and "@you: made it" in text
