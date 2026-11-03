"""One `run` of the command line on each real harness, against FakeModel: a dummy key, an isolated home and loopback
only, so it spends nothing. Each skips where its binary is not installed, and a skip proves nothing."""

import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.testing import FakeModel

from .cli import Cli, checked

pytestmark = [pytest.mark.slow, pytest.mark.timeout(180)]

KEYS = {
    "claude": {"ANTHROPIC_BASE_URL": "{url}", "ANTHROPIC_API_KEY": "dummy-key"},
    "codex": {"OPENAI_BASE_URL": "{url}/v1", "OPENAI_API_KEY": "dummy-key"},
    "pi": {"OPENAI_BASE_URL": "{url}/v1", "OPENAI_API_KEY": "dummy-key", "PI_OFFLINE": "yes"},
}
HOMES = {"claude": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME"}


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    made = Cli(tmp_path)
    yield made
    await asyncio.to_thread(made.end)


def keyed(cli: Cli, harness: str, model: FakeModel) -> str:
    """A team of one on the real binary, reaching FakeModel the way an auth profile would, in a home of its own."""
    home = cli.folder / "home-of-the-harness"
    keys = {name: value.format(url=model.url) for name, value in KEYS[harness].items()}
    cli.env |= {"HOME": str(home), **keys}
    if harness in HOMES:
        (home / f".{harness}").mkdir(parents=True)
        cli.env[HOMES[harness]] = str(home / f".{harness}")
    names = ", ".join(f'"{name}"' for name in keys)
    return cli.write(
        "team.toml",
        f'[roles.bob]\nharness = "{harness}"\nmodel = "fake-model"\nauth = "fake"\n\n[auth.fake]\nenv = [{names}]\n',
    )


@pytest.mark.parametrize("harness", sorted(KEYS))
async def test_a_run_on_a_real_harness_settles_and_says_so_in_jsonl(cli: Cli, harness: str):
    if shutil.which(harness) is None:
        pytest.skip(f"{harness} is not installed, so the command line met no real {harness} here")
    async with FakeModel("Hello from the model.") as model:
        team = keyed(cli, harness, model)

        done = await cli.run("run", "Say hello", "--team", team, "--trust", "--json")

    events = checked(done)
    assert (done.code, done.lines()[-1]["reason"]) == (0, "settled"), done.stderr
    types = [event["type"] for event in events]
    assert {"agent.instructed", "model.called", "turn.ended"} <= set(types)
    assert any(event["gist"] == "Hello from the model." for event in events if event["type"] == "item.recorded")
    assert model.calls[0].says("Say hello")
