"""The provenance guide runs: each of its Python blocks, on a session of a scripted harness."""

import re
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.testing import Call

from .support import in_state, of_type, scripted, until

pytestmark = pytest.mark.timeout(30)

GUIDE = Path(__file__).parents[3] / "docs" / "how-to" / "provenance.md"
BLOCK = re.compile(r"^```python\n(.*?)^```$", re.M | re.S)


async def test_the_guide_s_code_runs_on_a_session(tmp_path):
    namespace: dict[str, Any] = {}
    for block in BLOCK.findall(GUIDE.read_text()):
        exec(block, namespace)
    cite = {"to": "@you", "gist": "done, as you asked", "based_on": ["inbox/bob@1"]}
    roles = {"bob": {"harness": scripted([Call("message_send", cite)])}}
    team = Team.model_validate({"roles": roles, "topology": {"edges": {"bob": ["human"]}}})

    async with Session.start(team, root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.open_episode("e")
        await session.send("@bob", "please do it")
        sent = await until(lambda: of_type(session, "message.sent"), session, lambda found: len(found) == 2)
        answer = f"{sent[-1].stream}@{sent[-1].version}"

        cited = await namespace["citations"](session, answer)
        estimates = await namespace["even_split"](session, answer)
        trains = await namespace["what_can_train"](session, "@bob", "e")
        reached = await namespace["who_reached_whom"](session)
        labelled = await namespace["labelled_spans"](session, "@bob")

    assert cited == [("inbox/bob@1", "human:you", "seen")]
    assert [(found.target, found.producer, found.value) for found in estimates] == [(answer, "even-split", 1.0)]
    assert trains == (None, "ineligible", ["not_trainable", "no_end"])
    assert labelled == {}, "a scripted call is no model call, so bob has no span"
    assert reached == (
        [("human:you", "agent:bob", {"declared": 1, "observed": 1, "cause": 0, "ancestry": 0, "unconfirmed": 0})],
        ["bob"],
    )
