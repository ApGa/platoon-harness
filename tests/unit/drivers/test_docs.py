"""The driver guide is true: its example runs through the conformance suite, and its tables match the code."""

import re
import sys
from pathlib import Path

import pytest

from platoon_harness.drivers.wire import DRIVER_ERROR, UNKNOWN_PROTOCOL, WireDriver
from platoon_harness.primitives import Capabilities
from platoon_harness.testing import check_driver
from platoon_harness.testing.conformance import _CHECKS
from platoon_harness.testing.scripted import ScriptedDriver

GUIDE = Path(__file__).parents[3] / "docs" / "drivers.md"
TEXT = GUIDE.read_text()

pytestmark = pytest.mark.timeout(60)


async def test_the_guide_s_wire_driver_conforms(tmp_path):
    block = TEXT.partition("<!-- example: the wire driver a test runs -->\n```python\n")[2].partition("```\n")[0]
    program = tmp_path / "one_call.py"
    program.write_text(block)

    result = await check_driver(lambda: WireDriver([sys.executable, str(program)]), folder=tmp_path / "run", timeout=20)

    assert result.failed == (), str(result)
    assert (result.driver, result.version) == ("one-call", "1.0")
    passed = {check.name for check in result.checks if check.state == "passed"}
    assert {
        "ready_with_pinned_model",
        "delivered_text_in_next_prompt",
        "turn_end_reported",
        "exit_reported",
        "stop_leaves_no_process",
        "dialects_spoken",
    } <= passed


async def test_the_guide_s_conformance_test_passes_as_written(tmp_path):
    driver = TEXT.partition("<!-- example: the wire driver a test runs -->\n```python\n")[2].partition("```\n")[0]
    block = TEXT.partition("<!-- example: the conformance test a test runs -->\n```python\n")[2].partition("```\n")[0]
    (tmp_path / "my_driver.py").write_text(driver)
    written = {"__file__": str(tmp_path / "test_it.py")}

    exec(compile(block, written["__file__"], "exec"), written)

    await written["test_my_driver_conforms"](tmp_path / "run")


def test_the_guide_names_every_check():
    table = TEXT.partition("| Check | What it proves |")[2].partition("\n\n")[0]

    assert re.findall(r"^\| `(\w+)`", table, re.MULTILINE) == [definition.name for definition in _CHECKS]


def test_the_guide_names_every_capability():
    table = TEXT.partition("| Field | Values |")[2].partition("\n\n")[0]

    assert re.findall(r"^\| `(\w+)`", table, re.MULTILINE) == list(Capabilities.model_fields)


def test_the_guide_gives_the_error_codes_the_wire_uses():
    assert f"`{DRIVER_ERROR}`" in TEXT
    assert f"`{UNKNOWN_PROTOCOL}`" in TEXT


def test_the_guide_s_script_is_a_script():
    block = TEXT.partition("driver = ScriptedDriver(")[2].partition("\n")[0]

    assert ScriptedDriver(eval(block.rpartition(")")[0], vars(sys.modules["platoon_harness.testing"])))
