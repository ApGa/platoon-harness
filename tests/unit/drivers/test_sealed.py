"""Sealed launches: a gateway's model under its bearer, the environment's tools beside ours, and each compaction call
sent with the gateway's compaction headers and reported by the id the model gave it."""

import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    BEARER_VARIABLE,
    Compacted,
    Driver,
    DriverError,
    Gateway,
    ModelCall,
    Ready,
    TurnEnded,
)
from platoon_harness.drivers.pi import PiDriver
from platoon_harness.drivers.wire import WireDriver
from platoon_harness.testing import (
    ENVIRONMENT_TOOL,
    TOOL,
    AskModel,
    Compact,
    FakeModel,
    FakeTools,
    ScriptedDriver,
    ToolCall,
)

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

BEARER = "bearer-of-ada"
FAKE_PI = Path(__file__).with_name("fake_pi.py")


def served(tmp_path: Path, script: str) -> WireDriver:
    """A program on the wire that serves a scripted harness of `script`."""
    path = tmp_path / "program.py"
    body = f"""
        from platoon_harness.drivers.wire import serve
        from platoon_harness.testing import *

        serve(ScriptedDriver({script}))
    """
    path.write_text(textwrap.dedent(body))
    return WireDriver([sys.executable, str(path)])


def compacting(kind: str, tmp_path: Path) -> Driver:
    """A harness that asks the model once and then compacts, here or on the wire."""
    if kind == "wire":
        return served(tmp_path, "[[AskModel(), Compact()]]")
    return ScriptedDriver([[AskModel(), Compact()]])


@pytest.mark.parametrize("kind", ["scripted", "wire"])
async def test_each_sealed_driver_sends_the_compaction_headers_and_reports_each_compaction_with_its_id(tmp_path, kind):
    async with FakeModel("worked", "the summary") as model:
        gateway = model.gateway(BEARER)
        driver, heard = compacting(kind, tmp_path), Heard()
        await driver.start(make_spec(tmp_path, model=gateway.model, access=gateway), heard)
        await heard.until(TurnEnded)
        await driver.stop(1)

    worked, compacted = model.calls
    calls = heard.of(ModelCall)
    assert [call.bearer for call in model.calls] == [BEARER, BEARER]
    assert not worked.carries(gateway.compaction_headers) and compacted.carries(gateway.compaction_headers)
    assert [(call.call_id, call.purpose) for call in calls] == [
        (worked.response_id, None),
        (compacted.response_id, "compaction"),
    ]
    assert heard.of(Compacted)[0].summary == "the summary"


async def test_a_sealed_scripted_harness_shows_the_environment_s_tools_beside_ours_and_calls_them_on_its_bearer(
    tmp_path,
):
    async with FakeModel(ToolCall(ENVIRONMENT_TOOL, {"note": "hi"}), "done") as model, FakeTools() as tools:
        gateway = model.gateway(BEARER)
        spec = make_spec(tmp_path, model=gateway.model, access=gateway, tools=tools.binding(tmp_path))
        driver, heard = ScriptedDriver([[AskModel()]]), Heard()
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(1)

    assert set(model.calls[0].tools) == {TOOL, ENVIRONMENT_TOOL}
    assert set((await heard.until(Ready)).tools_visible or ()) == {TOOL, ENVIRONMENT_TOOL}
    assert [call.bearer for call in model.tool_calls] == [BEARER]
    assert driver.results[0]["content"][0]["text"] == "pong"


async def test_a_harness_with_no_sealed_launch_refuses_a_gateway(tmp_path):
    unsealed = ScriptedDriver().describe().capabilities.model_copy(update={"sealed": False})
    gateway = Gateway(origin="http://127.0.0.1:9", bearer=Secret(BEARER), model="m")

    with pytest.raises(DriverError, match="no sealed launch"):
        await ScriptedDriver(capabilities=unsealed).start(make_spec(tmp_path, model="m", access=gateway), Heard())


@pytest.mark.parametrize(
    ("origin", "tools"),
    [
        ("http://127.0.0.1:9/s/the-bearer", None),
        ("http://127.0.0.1:9", "http://127.0.0.1:9/s/the-bearer/mcp"),
        ("http://127.0.0.1:9", "http://127.0.0.1:9/mcp?key=the-bearer"),
    ],
)
def test_a_path_form_url_never_reaches_a_driver(origin, tools):
    """A secret in a gateway's URL would route its calls by that secret, whoever's bearer came with them, so a gateway
    whose origin has a path, or whose tools' URL holds its bearer, is refused before any driver sees it."""
    with pytest.raises(ValidationError, match="bearer alone"):
        Gateway(origin=origin, bearer=Secret("the-bearer"), model="m", tools=tools)


def _stand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `pi` first on the PATH that speaks the real frames, and the script it plays."""
    folder = tmp_path / "stand"
    folder.mkdir()
    script = folder / "script.json"
    script.write_text(json.dumps({"provider": "platoon-harness", "model": "fake-model"}))
    program = folder / "pi"
    program.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE_PI}" "{script}" "$@"\n')
    program.chmod(0o700)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    return script


async def test_a_bearer_reaches_a_harness_only_through_its_environment(tmp_path, monkeypatch):
    """Pi's sealed launch writes settings and instructions, and hands its extension what it adds: each names the
    bearer's variable, and the bearer's value is in the harness's environment alone, under that variable."""
    script = _stand(tmp_path, monkeypatch)
    async with FakeModel() as model, FakeTools() as tools:
        gateway = model.gateway(BEARER)
        spec = make_spec(tmp_path, goal="", model=gateway.model, access=gateway, tools=tools.binding(tmp_path))
        spec = spec.model_copy(update={"instructions": "the role's words"})
        driver, heard = PiDriver(), Heard()
        await driver.start(spec, heard)
        await heard.until(Ready)
        await driver.stop(1)

    launch = json.loads(script.with_suffix(".launch").read_text())
    holding = [name for name, value in launch["env"].items() if BEARER in value]
    written = [path for path in spec.folder.rglob("*") if path.is_file() and BEARER.encode() in path.read_bytes()]
    config = json.loads(launch["env"]["PLATOON_HARNESS_PI"])
    assert holding == [BEARER_VARIABLE] and written == [] and BEARER not in " ".join(launch["argv"])
    assert config["provider"][1]["apiKey"] == f"${{{BEARER_VARIABLE}}}"
    assert config["environment"][1]["headers"] == {"Authorization": f"Bearer ${{{BEARER_VARIABLE}}}"}
    assert config["compaction"] == {"bearer": BEARER_VARIABLE, "headers": dict(gateway.compaction_headers)}


async def test_a_sealed_pi_has_an_agent_directory_of_its_own_and_nothing_of_the_user_s(tmp_path, monkeypatch):
    """Its own settings, which retry nothing and warm no cache, none of the user's resources, no built-in tool, and a
    window no context reaches, so that it compacts when its gateway refuses a request as too long."""
    script = _stand(tmp_path, monkeypatch)
    monkeypatch.setenv("PI_CODING_AGENT_SESSION_DIR", str(tmp_path / "the user's sessions"))
    gateway = Gateway(origin="http://127.0.0.1:9", bearer=Secret(BEARER), model="fake-model", tools=None)
    spec = make_spec(tmp_path, goal="", model=gateway.model, access=gateway)
    driver, heard = PiDriver(), Heard()
    await driver.start(spec, heard)
    await heard.until(Ready)
    await driver.stop(1)

    launch: dict[str, Any] = json.loads(script.with_suffix(".launch").read_text())
    home = Path(launch["env"]["PI_CODING_AGENT_DIR"])
    argv = launch["argv"]
    config = json.loads(launch["env"]["PLATOON_HARNESS_PI"])
    assert home == spec.folder / "pi"
    assert json.loads((home / "settings.json").read_text()) == {"retry": {"enabled": False}, "cacheWarming": "off"}
    assert {"--no-builtin-tools", "--no-context-files", "--no-skills", "--no-approve", "--offline"} <= set(argv)
    assert argv[argv.index("--provider") + 1] == config["provider"][0] == "platoon-harness"
    assert config["provider"][1]["baseUrl"] == "http://127.0.0.1:9/v1"
    assert config["provider"][1]["models"][0]["contextWindow"] == 2**53 - 1
    assert "environment" not in config and "PI_CODING_AGENT_SESSION_DIR" not in launch["env"]
