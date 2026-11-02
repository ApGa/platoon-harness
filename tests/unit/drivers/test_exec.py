"""The exec driver: a one-shot CLI from config, with no code, and nothing claimed that an exit cannot show."""

import sys

import pytest

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    Delivery,
    Delta,
    Driver,
    DriverError,
    Exited,
    Item,
    Offered,
    Ready,
    ToolBinding,
    TurnEnded,
    TurnStarted,
)
from platoon_harness.drivers.exec import ExecDriver
from platoon_harness.drivers.process import Record
from platoon_harness.team import Command, Role
from platoon_harness.tools.ph import URL_VARIABLE

from .support import Heard, group_of, make_spec

pytestmark = pytest.mark.timeout(30)


async def run(tmp_path, *command, **fields) -> tuple[ExecDriver, Heard]:
    driver, heard = ExecDriver(command), Heard()
    await driver.start(make_spec(tmp_path, **fields), heard)
    await heard.until(Exited)
    await driver.stop(1)
    return driver, heard


def test_it_is_a_driver_and_describes_itself_with_nothing_started():
    driver = ExecDriver(["no-such-program"])
    info = driver.describe()

    assert isinstance(driver, Driver)
    assert info.name == "exec"
    assert not info.capabilities.persistent
    assert info.capabilities.boundaries == frozenset()
    assert info.capabilities.tool_paths == {"shell"}


def test_a_command_harness_means_the_exec_driver():
    role = Role(harness=Command(command=("my-agent", "{goal}"), mode="oneshot"))
    wire = Role(harness=Command(command=("my-driver",), mode="wire"))

    assert (role.driver, wire.driver) == ("exec", "wire")


async def test_one_process_is_one_turn(tmp_path):
    _, heard = await run(tmp_path, "sh", "-c", "echo the answer")

    assert [type(report) for report in heard.reports] == [Ready, TurnStarted, Delta, Item, TurnEnded, Exited]
    item = heard.of(Item)[0]
    assert (item.kind, item.gist, item.body) == ("message", "the answer", "the answer")
    assert heard.of(TurnEnded)[0].reason == "stopped"


async def test_nothing_is_claimed_that_an_exit_cannot_show(tmp_path):
    _, heard = await run(tmp_path, "true", model="m")

    ready = heard.of(Ready)[0]
    assert (ready.native, ready.version, ready.effective_model, ready.tools_visible) == (None, None, None, None)


async def test_the_goal_goes_where_the_command_says(tmp_path):
    _, heard = await run(tmp_path, "sh", "-c", 'echo "goal: $1"', "sh", "{goal}", goal="fix the tests")

    assert heard.of(Item)[0].gist == "goal: fix the tests"


async def test_a_goal_inside_an_argument_is_replaced_in_place(tmp_path):
    _, heard = await run(tmp_path, "echo", "--task={goal}!", goal="plan")

    assert heard.of(Item)[0].gist == "--task=plan!"


async def test_stdin_is_closed_so_a_cli_cannot_hang_on_it(tmp_path):
    _, heard = await run(tmp_path, "cat")

    assert heard.of(TurnEnded)[0].reason == "stopped"


async def test_a_failure_ends_the_turn_with_its_code(tmp_path):
    _, heard = await run(tmp_path, "sh", "-c", "exit 3")

    assert heard.of(TurnEnded)[0].reason == "exited with code 3"
    assert heard.of(Exited)[0].reason == "exited with code 3"


async def test_silence_says_nothing(tmp_path):
    _, heard = await run(tmp_path, "true")

    assert heard.of(Item) == []


async def test_long_output_keeps_the_tail_and_a_gist_of_its_end(tmp_path):
    script = "print('x' * 3_000_000); print('the conclusion')"

    _, heard = await run(tmp_path, sys.executable, "-I", "-c", script)

    item = heard.of(Item)[0]
    assert item.gist.endswith("the conclusion")
    assert len(item.body) == 1024 * 1024 - 1
    assert "".join(delta.text for delta in heard.of(Delta)).endswith("the conclusion\n")


async def test_output_that_is_not_text_stays_a_report(tmp_path):
    _, heard = await run(tmp_path, sys.executable, "-I", "-c", "import os; os.write(1, b'\\xff\\xfe ok')")

    assert "ok" in heard.of(Item)[0].gist


async def test_interrupt_ends_the_tree_and_says_so(tmp_path):
    spec = make_spec(tmp_path)
    driver, heard = ExecDriver(["sh", "-c", "echo started; sleep 100 & wait"]), Heard()
    await driver.start(spec, heard)
    await heard.until(Delta)
    record = Record.read(spec.folder)

    receipt = await driver.interrupt()

    assert receipt.boundary == "turn"
    assert (await heard.until(TurnEnded)).reason == "interrupted"
    assert await heard.until(Exited)
    assert group_of(record.pid) is None


async def test_a_forked_child_cannot_keep_the_turn_open(tmp_path):
    spec = make_spec(tmp_path)
    driver, heard = ExecDriver(["sh", "-c", "echo said; sleep 100 &"]), Heard()
    await driver.start(spec, heard)

    assert (await heard.until(TurnEnded)).reason == "stopped"
    await heard.until(Exited)
    assert heard.of(Item)[0].gist == "said"
    record = Record.read(spec.folder)
    await driver.stop(1)

    assert group_of(record.pid) is None


async def test_what_a_one_shot_cannot_do_is_refused_with_why(tmp_path):
    driver = ExecDriver(["true"])
    delivery = Delivery(input="1", boundary="turn", text="x", items=(Offered(ref="inbox/a@1", gist="x"),))

    with pytest.raises(DriverError, match="takes nothing after its goal"):
        await driver.deliver(delivery)
    with pytest.raises(DriverError, match="asks for no approvals"):
        await driver.answer("a", "allow")
    with pytest.raises(DriverError, match="has not started"):
        await driver.interrupt()
    with pytest.raises(DriverError, match="cannot resume"):
        await driver.start(make_spec(tmp_path, resume="s-1"), Heard())
    with pytest.raises(DriverError, match="spawn it with one"):
        await driver.start(make_spec(tmp_path, goal=""), Heard())
    assert await driver.reconcile("1") == "unknown"
    await driver.stop(1)


async def test_ph_is_on_the_path_of_the_one_shot(tmp_path):
    bin = tmp_path / "bin"
    bin.mkdir()
    ph = bin / "ph"
    ph.write_text(f'#!/bin/sh\necho "ph reached $@ at ${URL_VARIABLE}"\n')
    ph.chmod(0o755)
    tools = ToolBinding(url="http://tools", token=Secret("a-long-token"), namespace="n", bin=bin)

    _, heard = await run(tmp_path, "sh", "-c", "ph task.claim", tools=tools)

    assert heard.of(Item)[0].gist == "ph reached task.claim at http://tools"


async def test_a_goal_that_would_be_an_option_is_refused(tmp_path):
    driver = ExecDriver(["echo", "{goal}"])

    with pytest.raises(DriverError, match="option"):
        await driver.start(make_spec(tmp_path, goal="--delete-everything"), Heard())


async def test_a_goal_inside_an_argument_cannot_be_an_option(tmp_path):
    driver = ExecDriver(["echo", "--task={goal}"])
    heard = Heard()

    await driver.start(make_spec(tmp_path, goal="--delete-everything"), heard)

    assert (await heard.until(Item)).gist == "--task=--delete-everything"
    await driver.stop(1)


async def test_a_gist_and_live_text_never_hold_part_of_a_credential(tmp_path):
    secret = "s3cret-" + "k" * 40
    tail = "t" * 270
    driver = ExecDriver(["printf", f"before {secret}{tail}"])
    heard = Heard()

    await driver.start(make_spec(tmp_path, access={"KEY": Secret(secret)}), heard)

    item = await heard.until(Item)
    await driver.stop(1)
    live = "".join(delta.text for delta in heard.of(Delta))
    assert secret not in (item.body or "") and secret[-8:] not in item.gist
    assert item.gist.startswith("before ***") and secret not in live


async def test_a_credential_split_across_two_writes_is_masked_in_live_text(tmp_path):
    secret = "s3cret-" + "k" * 40
    script = (
        f"import sys,time\nsys.stdout.write({secret[:9]!r});sys.stdout.flush();time.sleep(.05);"
        f"sys.stdout.write({secret[9:]!r})"
    )
    driver = ExecDriver([sys.executable, "-I", "-c", script])
    heard = Heard()

    await driver.start(make_spec(tmp_path, access={"KEY": Secret(secret)}), heard)

    await heard.until(TurnEnded)
    await driver.stop(1)
    assert "".join(delta.text for delta in heard.of(Delta)) == "***"
