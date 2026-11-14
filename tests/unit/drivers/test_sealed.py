"""Sealed launches: a gateway's model under its bearer, the environment's tools beside ours, and each compaction call
sent with the gateway's compaction headers and reported by the id the model gave it; and on a gateway that says its
session runs in the environment, the harness's own tools kept, its commands on the `PATH` the environment gives its
own."""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    BEARER_VARIABLE,
    ENVIRONMENT,
    AgentSpec,
    ApprovalRequested,
    Compacted,
    Driver,
    DriverError,
    Gateway,
    ModelCall,
    Ready,
    Report,
    TurnEnded,
)
from platoon_harness.drivers.openhands import OpenHandsDriver
from platoon_harness.drivers.pi import _SEALED, _SEALED_SETTINGS, PiDriver
from platoon_harness.drivers.process import Record
from platoon_harness.drivers.wire import WireDriver
from platoon_harness.testing import (
    ENVIRONMENT_TOOL,
    ENVIRONMENT_TOOLS,
    SHELL,
    TOOL,
    AskModel,
    Compact,
    FakeModel,
    FakeTools,
    ScriptedDriver,
    ToolCall,
    every_turn_asks_the_model,
)

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)

BEARER = "bearer-of-ada"
FAKE_PI = Path(__file__).with_name("fake_pi.py")
ENVIRONMENT_PATH = os.pathsep.join(("/opt/task/bin", "/usr/bin", "/bin"))
"""The `PATH` an environment gives its own commands, which its gateway names."""
SLOW = (pytest.mark.slow, pytest.mark.timeout(300))
"""A real harness's marks: the slow pass, and as long as one takes to come up and take a turn beside other tests."""
HARNESSES = ["scripted", "wire", pytest.param("openhands", marks=SLOW), pytest.param("pi", marks=SLOW)]
"""Each harness with a launch in the environment: the scripted one, here or on the wire, OpenHands on its real SDK, and
pi on its real binary."""


@dataclass(frozen=True)
class Own:
    """What a harness keeps of its own on a launch in the environment, by the names its model is shown, the one of them
    that runs a command, and what it keeps on every sealed launch, as it acts on nothing."""

    tools: frozenset[str]
    shell: str
    kept: frozenset[str] = frozenset()


OWN = {
    "scripted": Own(frozenset({SHELL}), SHELL),
    "wire": Own(frozenset({SHELL}), SHELL),
    "openhands": Own(
        frozenset({"terminal", "file_editor", "task_tracker"}), "terminal", kept=frozenset({"finish", "think"})
    ),
    "pi": Own(frozenset({"read", "bash", "edit", "write"}), "bash"),
}


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


def asking(kind: str, tmp_path: Path) -> Driver:
    """A harness that runs what the model calls each turn, as a harness does: the scripted one, here or on the wire, or
    a real one."""
    if kind == "wire":
        return served(tmp_path, "every_turn_asks_the_model()")
    if kind == "openhands":
        return OpenHandsDriver()
    if kind == "pi":
        if shutil.which("pi") is None:
            pytest.skip("pi is not installed, so this met no real harness here")
        return PiDriver()
    return ScriptedDriver(every_turn_asks_the_model())


def theirs(shown: Iterable[str]) -> set[str]:
    """What of the tools a request shows is the harness's own: no tool of ours, whatever a harness puts before its name,
    and none of the environment's, which every harness names by their server."""
    environment = re.compile(rf"(.*_)?{ENVIRONMENT}_+({'|'.join(ENVIRONMENT_TOOLS)})")
    return {name for name in shown if not name.endswith(TOOL) and environment.fullmatch(name) is None}


class Allowing(Heard):
    """Hears a harness, and allows each approval it asks for."""

    def __init__(self, driver: Driver) -> None:
        super().__init__()
        self._driver = driver

    async def __call__(self, report: Report) -> None:
        await super().__call__(report)
        if isinstance(report, ApprovalRequested):
            await self._driver.answer(report.id, "allow")


def path_of(kind: str, spec: AgentSpec) -> str:
    """The `PATH` a harness runs on: this process's for one in it, and else the one its process began with."""
    if kind == "scripted":
        return os.environ["PATH"]
    record = Record.read(spec.folder)
    assert record is not None
    began = Path(f"/proc/{record.pid}/environ").read_bytes().split(b"\0")
    return next(entry.removeprefix(b"PATH=").decode() for entry in began if entry.startswith(b"PATH="))


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


async def test_a_sealed_scripted_harness_shows_the_environment_s_tools_named_by_its_server_and_calls_them_on_its_bearer(
    tmp_path,
):
    """Beside ours, by their own names, each of the environment's tools is named by its server, so its `finish` and
    `think` collide with nothing, and a call of one reaches the server by the name the server lists."""
    called = ToolCall(f"mcp__environment__{ENVIRONMENT_TOOL}", {"note": "hi"})
    async with FakeModel(called, "done") as model, FakeTools() as tools:
        gateway = model.gateway(BEARER)
        spec = make_spec(tmp_path, model=gateway.model, access=gateway, tools=tools.binding(tmp_path))
        driver, heard = ScriptedDriver([[AskModel()]]), Heard()
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        await driver.stop(1)

    shown = {TOOL, *(f"mcp__environment__{tool}" for tool in ENVIRONMENT_TOOLS)}
    assert set(model.calls[0].tools) == set((await heard.until(Ready)).tools_visible or ()) == shown
    assert [(call.bearer, call.json["params"]["name"]) for call in model.tool_calls] == [(BEARER, ENVIRONMENT_TOOL)]
    assert driver.results[0]["content"][0]["text"] == "pong"


async def test_a_sealed_scripted_harness_runs_no_tool_of_its_own(tmp_path):
    """On a gateway that does not say its session runs in the environment its shell is no tool at all: a model that
    calls it is told so, nothing asks an approval and nothing runs, so the bearer in its environment never reaches a
    file."""
    shell = ToolCall(SHELL, {"command": f"printenv {BEARER_VARIABLE} > leaked"})
    async with FakeModel(shell, "done") as model:
        gateway = model.gateway(BEARER)
        driver, heard = ScriptedDriver([[AskModel()]]), Heard()
        await driver.start(make_spec(tmp_path, model=gateway.model, access=gateway), heard)
        ended = await heard.until(TurnEnded)
        await driver.stop(1)

    assert ended.reason == "stopped" and not heard.of(ApprovalRequested)
    assert not list(tmp_path.rglob("leaked"))
    assert model.calls[1].says(f"there is no tool {SHELL}")


async def test_a_harness_with_no_sealed_launch_refuses_a_gateway(tmp_path):
    unsealed = ScriptedDriver().describe().capabilities.model_copy(update={"sealed": False})
    gateway = Gateway(origin="http://127.0.0.1:9", bearer=Secret(BEARER), model="m")

    with pytest.raises(DriverError, match="no sealed launch"):
        await ScriptedDriver(capabilities=unsealed).start(make_spec(tmp_path, model="m", access=gateway), Heard())


async def test_a_harness_with_no_launch_in_the_environment_refuses_a_gateway_in_it(tmp_path):
    sealed = ScriptedDriver().describe().capabilities.model_copy(update={"in_environment": False})
    gateway = Gateway(origin="http://127.0.0.1:9", bearer=Secret(BEARER), model="m", in_environment=True)

    with pytest.raises(DriverError, match="no launch in the environment"):
        await ScriptedDriver(capabilities=sealed).start(make_spec(tmp_path, model="m", access=gateway), Heard())


@pytest.mark.parametrize("kind", HARNESSES)
async def test_a_sealed_launch_keeps_the_harness_s_own_tools_only_on_a_gateway_in_the_environment(tmp_path, kind):
    """On a gateway that does not say its session runs in the environment, a sealed launch shows the model no tool of
    the harness's own but those that act on nothing, and a call of its shell asks nothing and runs nothing. On one that
    does, the launch keeps its own tools, shown beside ours and the environment's, and a call of its shell asks first
    and, once allowed, runs in the agent's workspace. The harness has a home of its own, so no startup file of yours
    changes where its shell runs."""
    own, found = OWN[kind], []
    for in_environment in (False, True):
        folder = tmp_path / str(in_environment)
        (folder / "home").mkdir(parents=True)
        async with FakeModel(ToolCall(own.shell, {"command": "touch made"}), "done") as model, FakeTools() as tools:
            gateway = model.gateway(BEARER).model_copy(update={"in_environment": in_environment})
            home = {"HOME": str(folder / "home")}
            spec = make_spec(folder, model=gateway.model, access=gateway, tools=tools.binding(folder), env=home)
            driver = asking(kind, folder)
            heard = Allowing(driver)
            await driver.start(spec, heard)
            await heard.until(TurnEnded)
            await driver.stop(1)
        found.append((theirs(model.calls[0].tools), len(heard.of(ApprovalRequested)), (folder / "made").exists()))

    assert found == [(own.kept, 0, False), (own.kept | own.tools, 1, True)]


@pytest.mark.parametrize("kind", HARNESSES)
async def test_in_the_environment_a_command_runs_on_the_environment_s_path(tmp_path, kind):
    """On a launch in the environment whose gateway names the `PATH` the environment gives its own commands, a command
    the model runs gets that one behind the agent's `bin`, which holds `ph` alone, so a task's `python3` is the
    environment's, while the harness keeps the runtime's, on which it found what it runs: the scripted harness runs in
    this process, so of it that holds by construction, and the others show it. The harness has a home of its own, so no
    startup file of yours changes what its shell starts on."""
    runtime = os.environ["PATH"]
    printing = ToolCall(OWN[kind].shell, {"command": 'printf %s "$PATH" > path'})
    home = tmp_path / "home"
    home.mkdir()
    async with FakeModel(printing, "done") as model, FakeTools() as tools:
        placing = {"in_environment": True, "environment_path": ENVIRONMENT_PATH}
        gateway = model.gateway(BEARER).model_copy(update=placing)
        binding = tools.binding(tmp_path / "bin")
        spec = make_spec(tmp_path, model=gateway.model, access=gateway, tools=binding, env={"HOME": str(home)})
        driver = asking(kind, tmp_path)
        heard = Allowing(driver)
        await driver.start(spec, heard)
        await heard.until(TurnEnded)
        harness = path_of(kind, spec)
        await driver.stop(1)

    assert (tmp_path / "path").read_text() == os.pathsep.join((str(tmp_path / "bin"), ENVIRONMENT_PATH))
    assert harness.endswith(runtime) and ENVIRONMENT_PATH not in harness


@pytest.mark.parametrize(
    ("origin", "tools", "headers"),
    [
        ("http://127.0.0.1:9/s/the-bearer", None, {}),
        ("http://127.0.0.1:9", "http://127.0.0.1:9/s/the-bearer/mcp", {}),
        ("http://127.0.0.1:9", "http://127.0.0.1:9/s/dGhlLWJlYXJlcg/mcp", {}),
        ("http://127.0.0.1:9", "http://127.0.0.1:9/mcp?key=the-bearer", {}),
        ("http://127.0.0.1:9", "http://10.0.0.1:9/mcp", {}),
        ("http://127.0.0.1:9", None, {"X-Call-Purpose": "the-bearer"}),
        ("http://127.0.0.1:9", None, {"the-bearer": "compaction"}),
        ("http://127.0.0.1:9", None, {"Authorization": "Bearer another"}),
    ],
)
def test_a_gateway_whose_urls_or_headers_carry_a_credential_never_reaches_a_driver(origin, tools, headers):
    """A credential goes by the bearer alone, to the gateway's origin alone: a gateway whose origin has a path, whose
    URLs or compaction headers hold its bearer in any form, whose headers would authorize a call, or whose tools are
    elsewhere, is refused before any driver sees it. A secret it cannot know, such as another agent's key in a tools
    path, is its authority's to keep out."""
    with pytest.raises(ValidationError, match=r"bearer (goes|alone)"):
        Gateway(origin=origin, bearer=Secret("the-bearer"), model="m", tools=tools, compaction_headers=headers)


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


async def test_pi_in_the_environment_keeps_its_default_tools_and_sets_each_command_s_path(tmp_path, monkeypatch):
    """In the environment pi's sealed launch keeps its default tools, and the rest of it stands: every flag that keeps
    out what pi would find of the user's or the project's, and the sealed settings, which gain only a line pi puts
    before each command its `bash` runs, as pi runs one, that sets the `PATH` `command_path` gives, while pi runs on
    the runtime's."""
    script = _stand(tmp_path, monkeypatch)
    placing = {"in_environment": True, "environment_path": ENVIRONMENT_PATH}
    async with FakeModel() as model, FakeTools() as tools:
        gateway = model.gateway(BEARER).model_copy(update=placing)
        spec = make_spec(tmp_path, goal="", model=gateway.model, access=gateway, tools=tools.binding(tmp_path / "bin"))
        driver, heard = PiDriver(), Heard()
        await driver.start(spec, heard)
        await heard.until(Ready)
        await driver.stop(1)

    launch: dict[str, Any] = json.loads(script.with_suffix(".launch").read_text())
    settings = json.loads((Path(launch["env"]["PI_CODING_AGENT_DIR"]) / "settings.json").read_text())
    command = f'{settings.pop("shellCommandPrefix")}\nprintf %s "$PATH"'
    ran = await asyncio.to_thread(subprocess.run, ["bash", "-c", command], capture_output=True, text=True, check=True)
    assert "--no-builtin-tools" not in launch["argv"]
    assert set(_SEALED) <= set(launch["argv"]) and settings == _SEALED_SETTINGS
    assert ran.stdout == os.pathsep.join((str(tmp_path / "bin"), ENVIRONMENT_PATH))
    assert launch["env"]["PATH"] == os.pathsep.join((str(tmp_path / "bin"), os.environ["PATH"]))
