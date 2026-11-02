"""SDK independence: a headless script imports `platoon_harness` and nothing else of ours, and runs a session."""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.timeout(60)

SCRIPT = """
import asyncio
import json
import sys

from platoon_harness import Session, Team

FORBIDDEN = ("platoon_harness_cli", "textual", "platoon", "torch", "tinker")

team = Team.model_validate(
    {
        "roles": {
            "helper": {
                "harness": {"command": [sys.executable, "-c", "print('hello from {goal}')"], "mode": "oneshot"},
                "count": 0,
            }
        }
    }
)


async def main() -> None:
    async with Session.start(team, root=sys.argv[1], cwd=sys.argv[1]) as session:
        await session.spawn("helper-1", "helper", "a headless script")
        ending = await session.settled(timeout="30s")
        items = [event.gist async for event in session.events() if event.type == "item.recorded"]
    imported = [name for name in FORBIDDEN if any(found.split(".")[0] == name for found in sys.modules)]
    status = ending.agents[0]["status"]
    print(json.dumps({"reason": ending.reason, "status": status, "items": items, "imported": imported}))


asyncio.run(main())
"""


def test_a_headless_script_needs_no_cli_no_tui_and_no_platoon(tmp_path: Path):
    script = tmp_path / "headless.py"
    script.write_text(SCRIPT)

    done = subprocess.run(
        [sys.executable, str(script), str(tmp_path)], capture_output=True, text=True, timeout=50, check=False
    )

    assert done.returncode == 0, done.stderr
    assert '"reason": "settled"' in done.stdout
    assert '"status": "finished"' in done.stdout
    assert "hello from a headless script" in done.stdout
    assert '"imported": []' in done.stdout
