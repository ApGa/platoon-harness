"""FakeModel against the real clients it claims to speak to. Free: dummy keys, an isolated home, and loopback only."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from platoon_harness.testing import FakeModel, Text, Thought, ToolCall

pytestmark = [pytest.mark.slow, pytest.mark.timeout(120)]

MODEL = "fake-model"
DUMMY_KEY = "dummy-key"


def binary(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        pytest.skip(f"{name} is not installed, so this dialect met no real client here")
    return found


def isolated(home: Path, **extra: str) -> dict[str, str]:
    """A home of its own, so that no login or setting of the person running this can take part."""
    home.mkdir(exist_ok=True)
    return {"PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(home), **extra}


async def run(*command: str, env: dict[str, str], cwd: Path) -> str:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=cwd,
        start_new_session=True,
    )
    output, _ = await asyncio.wait_for(process.communicate(), 100)
    return output.decode(errors="replace")


def codex_command(prompt: str, url: str) -> list[str]:
    provider = f'model_providers.fake={{name="fake",base_url="{url}/v1",env_key="FAKE_KEY",wire_api="responses"}}'
    return [
        binary("codex"),
        "exec",
        "--skip-git-repo-check",
        "--json",
        "-m",
        MODEL,
        "-c",
        'model_provider="fake"',
        "-c",
        provider,
        prompt,
    ]


async def test_codex_speaks_responses_with_fake_model(tmp_path):
    async with FakeModel("the answer is forty two") as model:
        env = isolated(tmp_path / "home", CODEX_HOME=str(tmp_path / "home"), FAKE_KEY=DUMMY_KEY)

        output = await run(*codex_command("what is the answer?", model.url), env=env, cwd=tmp_path)

    assert "the answer is forty two" in output, output
    call = model.calls[0]
    assert (call.dialect, call.model) == ("responses", MODEL)
    assert call.says("what is the answer?")
    assert call.message.header("authorization") == f"Bearer {DUMMY_KEY}"


async def test_codex_runs_a_tool_fake_model_called(tmp_path):
    arguments = {"cmd": "echo fake-model-ran-this", "justification": "test"}
    call = ToolCall("exec_command", arguments, id="call_shell")
    async with FakeModel(call, "done") as model:
        env = isolated(tmp_path / "home", CODEX_HOME=str(tmp_path / "home"), FAKE_KEY=DUMMY_KEY)

        output = await run(
            *codex_command("run it", model.url), "--dangerously-bypass-approvals-and-sandbox", env=env, cwd=tmp_path
        )

    assert len(model.calls) >= 2, output
    assert model.calls[1].says("call_shell")


def claude_env(home: Path, url: str) -> dict[str, str]:
    return isolated(
        home,
        ANTHROPIC_BASE_URL=url,
        ANTHROPIC_API_KEY=DUMMY_KEY,
        CLAUDE_CONFIG_DIR=str(home / ".claude"),
        DISABLE_TELEMETRY="1",
        DISABLE_ERROR_REPORTING="1",
        DISABLE_AUTOUPDATER="1",
    )


async def test_claude_speaks_messages_with_fake_model(tmp_path):
    async with FakeModel([Thought("thinking it over"), Text("the answer is forty two")]) as model:
        output = await run(
            binary("claude"),
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--model",
            MODEL,
            "what is the answer?",
            env=claude_env(tmp_path / "home", model.url),
            cwd=tmp_path,
        )

    assert "the answer is forty two" in output, output
    prompted = [call for call in model.calls if call.says("what is the answer?")]
    assert prompted[0].dialect == "messages"
    assert prompted[0].model == MODEL


async def test_claude_runs_a_tool_fake_model_called(tmp_path):
    call = ToolCall("Bash", {"command": "echo fake-model-ran-this", "description": "say"}, id="toolu_fake")
    async with FakeModel(call, "done") as model:
        output = await run(
            binary("claude"),
            "-p",
            "run it",
            "--output-format",
            "stream-json",
            "--verbose",
            "--model",
            MODEL,
            "--allowedTools",
            "Bash",
            env=claude_env(tmp_path / "home", model.url),
            cwd=tmp_path,
        )

    assert any(call.says("fake-model-ran-this") and call.says("tool_result") for call in model.calls[1:]), output


async def test_pi_speaks_chat_with_fake_model(tmp_path):
    agent = tmp_path / "agent"
    agent.mkdir()
    async with FakeModel("the answer is forty two") as model:
        provider = {
            "baseUrl": f"{model.url}/v1",
            "api": "openai-completions",
            "apiKey": DUMMY_KEY,
            "models": [{"id": MODEL, "contextWindow": 100000, "maxTokens": 1000}],
        }
        (agent / "models.json").write_text(json.dumps({"providers": {"fake": provider}}))
        env = isolated(tmp_path / "home", PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE="1", PI_TELEMETRY="0")

        output = await run(
            binary("pi"),
            "--mode",
            "json",
            "--provider",
            "fake",
            "--model",
            MODEL,
            "-p",
            "what is it?",
            env=env,
            cwd=tmp_path,
        )

    assert "the answer is forty two" in output, output
    assert model.calls[0].dialect == "chat"
    assert model.calls[0].says("what is it?")
