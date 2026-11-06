"""The wire: a driver in another process, and everything such a process can get wrong."""

import asyncio
import json
import sys
import textwrap
from pathlib import Path

import pytest

from platoon_harness.config import WIRE_PROTOCOL, Secret
from platoon_harness.drivers import (
    Delivery,
    DriverError,
    Exited,
    GapReport,
    Item,
    Native,
    Offered,
    Ready,
    ToolBinding,
    TurnEnded,
)
from platoon_harness.drivers.process import LOG, RECORD, Record
from platoon_harness.drivers.wire import UNKNOWN_PROTOCOL, WireDriver
from platoon_harness.tools.ph import TOKEN_VARIABLE

from .support import Heard, group_of, make_spec, running

pytestmark = pytest.mark.timeout(30)

SERVED = """
    import os, sys
    from platoon_harness.drivers import *
    from platoon_harness.drivers.wire import serve
    from platoon_harness.testing import *
"""

RAW = """
    import json, os, sys

    def send(frame):
        print(json.dumps({"jsonrpc": "2.0", **frame}), flush=True)

    def reply(frame, result):
        send({"id": frame["id"], "result": result})

    def frames():
        for line in sys.stdin:
            yield json.loads(line)
"""

DESCRIBING = """
    for frame in frames():
        if frame["method"] == "describe":
            reply(frame, {"protocol": 2, "name": "raw"})
        elif frame["method"] == "start":
            reply(frame, {"native": "n"})
            break
"""


def program(tmp_path, *parts: str) -> list[str]:
    path = tmp_path / "program.py"
    path.write_text("".join(map(textwrap.dedent, parts)))
    return [sys.executable, str(path)]


def raw_program(tmp_path, *parts: str) -> list[str]:
    return [*program(tmp_path, RAW, *parts)[:1], "-I", *program(tmp_path, RAW, *parts)[1:]]


async def started(tmp_path, command, **fields) -> tuple[WireDriver, Heard]:
    driver, heard = WireDriver(command), Heard()
    await driver.start(make_spec(tmp_path, **fields), heard)
    return driver, heard


DELIVERY = Delivery(input="d1", boundary="turn", text="hello", items=(Offered(ref="inbox/ada@1", gist="hello"),))


async def test_a_python_driver_on_the_wire_is_a_few_lines(tmp_path):
    command = program(
        tmp_path,
        SERVED,
        """
        serve(ScriptedDriver([[Say("first")], [Say("second")]], name="tiny"))
    """,
    )
    driver, heard = await started(tmp_path, command)

    assert (await heard.until(Item)).gist == "first"
    await heard.until(TurnEnded)
    await driver.deliver(DELIVERY)
    await heard.until(Item, lambda item: item.gist == "second")
    await driver.stop(2)

    assert driver.describe().name == "tiny"
    assert await heard.until(Exited)


async def test_every_verb_equals_its_method(tmp_path):
    log = tmp_path / "verbs.jsonl"
    command = raw_program(
        tmp_path,
        f"""
        for frame in frames():
            with open({str(log)!r}, "a") as file:
                file.write(json.dumps(frame) + "\\n")
            match frame["method"]:
                case "start" | "deliver" | "interrupt" | "answer" | "stop":
                    reply(frame, None)
                case "reconcile":
                    reply(frame, "landed")
    """,
    )
    driver, _ = await started(tmp_path, command)

    await driver.deliver(DELIVERY)
    await driver.interrupt()
    await driver.answer("a1", "allow")
    assert await driver.reconcile("d1") == "landed"
    await driver.stop(2)

    frames = [json.loads(line) for line in log.read_text().splitlines()]
    assert [frame["method"] for frame in frames] == ["start", "deliver", "interrupt", "answer", "reconcile", "stop"]
    assert frames[0]["params"]["protocol"] == WIRE_PROTOCOL
    assert frames[0]["params"]["spec"]["agent"] == "ada"
    assert frames[1]["params"]["input"] == "d1"
    assert frames[3]["params"] == {"approval": "a1", "verdict": "allow"}
    assert frames[4]["params"] == {"input": "d1"}
    assert frames[5]["params"] == {"grace": 2}


async def test_describe_starts_no_harness_and_is_asked_once(tmp_path):
    count = tmp_path / "count"
    command = raw_program(
        tmp_path,
        f"""
        open({str(count)!r}, "a").write("x")
        for frame in frames():
            reply(frame, {{"protocol": 2, "name": "raw", "capabilities": {{"persistent": True}}}})
    """,
    )
    driver = WireDriver(command)

    assert driver.describe().capabilities.persistent
    assert driver.describe().name == "raw"
    assert count.read_text() == "x"


async def test_a_program_is_installed_where_path_finds_it_and_where_it_says(tmp_path):
    command = raw_program(
        tmp_path,
        """
        for frame in frames():
            reply(frame, {"protocol": 2, "name": "raw", "installed": ["/opt/my-agent"]})
    """,
    )

    assert WireDriver(command).describe().installed == (Path(sys.executable), Path("/opt/my-agent"))


async def test_a_program_runs_inside_what_wraps_it_and_its_frame_names_no_wrap(tmp_path):
    log, marker = tmp_path / "frames.jsonl", tmp_path / "wrapped"
    command = raw_program(
        tmp_path,
        f"""
        for frame in frames():
            with open({str(log)!r}, "a") as file:
                file.write(json.dumps(frame) + "\\n")
            reply(frame, None)
    """,
    )
    wrap = ("/bin/sh", "-c", 'echo wrapped > "$0"; exec "$@"', str(marker))
    driver, _ = await started(tmp_path, command, wrap=wrap)
    await driver.stop(2)

    start = json.loads(log.read_text().splitlines()[0])
    assert marker.read_text() == "wrapped\n"
    assert start["method"] == "start" and "wrap" not in start["params"]["spec"]


async def test_a_program_takes_what_its_driver_names_of_ours_to_describe_itself_as_to_start(tmp_path, monkeypatch):
    monkeypatch.setenv("NAMED", "named")
    monkeypatch.setenv("UNNAMED", "unnamed")
    seen = tmp_path / "seen.jsonl"
    command = raw_program(
        tmp_path,
        f"""
        for frame in frames():
            with open({str(seen)!r}, "a") as file:
                file.write(json.dumps([frame["method"], os.environ.get("NAMED"), os.environ.get("UNNAMED")]) + "\\n")
            reply(frame, {{"protocol": 2, "name": "raw"}} if frame["method"] == "describe" else None)
    """,
    )
    driver = WireDriver(command, ["NAMED"])

    driver.describe()
    await driver.start(make_spec(tmp_path), Heard())
    await driver.stop(2)

    lines = [json.loads(line) for line in seen.read_text().splitlines()]
    assert lines == [["describe", "named", None], ["start", "named", None], ["stop", "named", None]]


async def test_an_unknown_protocol_is_refused_both_ways(tmp_path):
    older = raw_program(
        tmp_path,
        """
        for frame in frames():
            reply(frame, {"protocol": 999, "name": "raw"})
    """,
    )
    with pytest.raises(DriverError, match="speaks protocol 999"):
        WireDriver(older).describe()

    served = program(
        tmp_path,
        SERVED,
        """
        serve(ScriptedDriver())
    """,
    )
    frame = {"jsonrpc": "2.0", "id": 1, "method": "describe", "params": {"protocol": 999}}
    process = await asyncio.create_subprocess_exec(
        *served, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
    )
    stdout, _ = await process.communicate(json.dumps(frame).encode() + b"\n")

    assert json.loads(stdout.splitlines()[0])["error"]["code"] == UNKNOWN_PROTOCOL


@pytest.mark.parametrize(
    "command",
    [
        "print('not json', flush=True)",
        "print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'error': {'code': -1, 'message': 'no'}}), flush=True)",
        "pass",
    ],
    ids=["garbage", "refusal", "silence"],
)
async def test_a_program_that_cannot_describe_itself_is_refused(tmp_path, command):
    with pytest.raises(DriverError, match=r"did not describe itself|speaks protocol"):
        WireDriver(raw_program(tmp_path, command)).describe()


async def test_a_program_that_does_not_exist_is_refused(tmp_path):
    with pytest.raises(DriverError, match="did not describe itself"):
        WireDriver([str(tmp_path / "missing")]).describe()


async def test_a_program_that_crashes_at_import_says_what_it_said(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text("import no_such_module\n")

    with pytest.raises(DriverError, match=r"(?s)exited with code 1.*no_such_module"):
        WireDriver([sys.executable, str(path)]).describe()


async def test_a_file_python_cannot_find_says_so(tmp_path):
    with pytest.raises(DriverError, match=r"(?s)exited with code 2.*gone\.py"):
        WireDriver([sys.executable, str(tmp_path / "gone.py")]).describe()


@pytest.mark.parametrize(
    "answer",
    [
        "print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'protocol': 2, 'name': 5}}), flush=True)",
        "print(json.dumps([1, 2]), flush=True)",
        "print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'error': 'no'}), flush=True)",
        "print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': 'yes'}), flush=True)",
    ],
    ids=["a bad field", "no object", "a bad error", "a bad result"],
)
async def test_a_malformed_description_names_the_program(tmp_path, answer):
    with pytest.raises(DriverError, match="did not describe itself"):
        WireDriver(raw_program(tmp_path, answer)).describe()
    with pytest.raises(DriverError, match="not an executable"):
        await WireDriver([str(tmp_path / "missing")]).start(make_spec(tmp_path), Heard())


@pytest.mark.parametrize(
    "frame",
    [
        "this is no frame",
        "{]",
        '{"jsonrpc":"2.0","method":"report","params":{"type":"dreamed","what":"x"}}',
        '{"jsonrpc":"2.0","method":"report","params":{"type":"turn.ended","reason":1}}',
        '{"jsonrpc":"2.0","method":"report","params":{"type":"item","kind":"message"}}',
        '{"jsonrpc":"2.0","method":"report"}',
        '{"jsonrpc":"2.0","method":"mystery"}',
        '{"jsonrpc":"2.0","id":99,"method":"mystery"}',
        '{"jsonrpc":"2.0","id":99,"result":"nobody asked"}',
    ],
)
async def test_an_unknown_frame_is_native_plus_a_gap(tmp_path, frame):
    command = raw_program(
        tmp_path,
        DESCRIBING,
        f"""
        print({frame!r}, flush=True)
        sys.stdin.read()
    """,
    )
    driver, heard = await started(tmp_path, command)

    native = await heard.until(Native)
    await heard.until(GapReport, lambda gap: gap.what == "unknown_update")
    await driver.stop(2)

    assert native.kind == "frame"
    assert native.raw == frame


async def test_a_long_unknown_frame_keeps_what_fits_and_says_what_was_cut(tmp_path):
    command = raw_program(
        tmp_path,
        DESCRIBING,
        """
        print("x" * 10000, flush=True)
        sys.stdin.read()
    """,
    )
    driver, heard = await started(tmp_path, command)

    native = await heard.until(Native)
    await driver.stop(2)

    assert (len(native.raw), native.cut) == (2048, 7952)


async def test_a_credential_is_masked_before_a_frame_is_cut_so_no_part_survives(tmp_path):
    secret = "k3y" + "z" * 40
    command = raw_program(
        tmp_path,
        DESCRIBING,
        f"""
        print("a" * 2040 + {secret!r}, flush=True)
        sys.stdin.read()
    """,
    )
    driver, heard = await started(tmp_path, command, access={"KEY": Secret(secret)})

    native = await heard.until(Native)
    await driver.stop(2)

    assert native.raw.rstrip("*").endswith("a") and secret[:8] not in native.raw


async def test_an_unknown_report_sent_as_a_request_is_native_plus_a_gap_too(tmp_path):
    frame = {"id": 99, "method": "report", "params": {"type": "nonsense"}}
    command = raw_program(
        tmp_path,
        DESCRIBING,
        f"""
        send({frame!r})
        sys.stdin.read()
    """,
    )
    driver, heard = await started(tmp_path, command)

    native = await heard.until(Native)
    await heard.until(GapReport)
    await driver.stop(2)

    assert "nonsense" in native.raw


async def test_a_program_that_goes_points_at_what_it_said(tmp_path):
    command = raw_program(tmp_path, DESCRIBING)
    driver, heard = await started(tmp_path, command)
    await heard.until(Exited)

    with pytest.raises(DriverError, match=LOG):
        await driver.interrupt()
    await driver.stop(1)


async def test_a_driver_cannot_claim_a_level(tmp_path):
    claim = {"type": "ready", "levels": {"trainable": True}, "declared": {"call_ids": "call"}}
    command = raw_program(
        tmp_path,
        DESCRIBING,
        f"""
        print(json.dumps({{"jsonrpc": "2.0", "method": "report", "params": {claim!r}}}), flush=True)
        sys.stdin.read()
    """,
    )
    driver, heard = await started(tmp_path, command)

    native = await heard.until(Native)
    await driver.stop(2)

    assert "trainable" in native.raw
    assert heard.of(Ready) == []


async def test_a_refused_verb_says_why(tmp_path):
    command = program(
        tmp_path,
        SERVED,
        """
        serve(ScriptedDriver(capabilities=Capabilities()))
    """,
    )
    driver, _ = await started(tmp_path, command)

    with pytest.raises(DriverError, match="cannot be interrupted"):
        await driver.interrupt()
    await driver.stop(2)


async def test_bad_params_are_refused_and_survived(tmp_path):
    command = program(
        tmp_path,
        SERVED,
        """
        serve(ScriptedDriver([[Hang()]]))
    """,
    )
    driver, _ = await started(tmp_path, command)

    with pytest.raises(DriverError, match="bad params"):
        await driver._call("deliver", {"nonsense": True})
    assert await driver.reconcile("x") == "unknown"
    await driver.stop(2)


async def test_eof_mid_request_fails_the_call_and_reports_the_exit(tmp_path):
    command = raw_program(
        tmp_path,
        DESCRIBING,
        """
        next(frames())
        os._exit(9)
    """,
    )
    driver, heard = await started(tmp_path, command)

    with pytest.raises(DriverError, match="is gone"):
        await driver.deliver(DELIVERY)

    assert (await heard.until(Exited)).reason == "exited with code 9"
    await driver.stop(2)


async def test_a_program_that_closes_stdout_and_lingers_is_ended(tmp_path):
    command = raw_program(
        tmp_path,
        DESCRIBING,
        """
        import time
        os.close(1)
        time.sleep(100)
    """,
    )
    driver, heard = await started(tmp_path, command)

    assert (await heard.until(Native)).raw == "the harness closed stdout and ran on"
    await heard.until(GapReport, lambda gap: gap.what == "stream_lost")
    await heard.until(Exited)
    with pytest.raises(DriverError, match="is gone"):
        await driver.deliver(DELIVERY)
    await driver.stop(1)


async def test_an_oversized_line_stops_the_agent_with_a_gap(tmp_path):
    command = raw_program(
        tmp_path,
        DESCRIBING,
        """
        sys.stdout.write("x" * (17 * 1024 * 1024))
        sys.stdout.flush()
        sys.stdin.read()
    """,
    )
    driver, heard = await started(tmp_path, command)

    assert "a line passed" in (await heard.until(Native)).raw
    await heard.until(GapReport, lambda gap: gap.what == "stream_lost")
    await heard.until(Exited)
    await driver.stop(2)


async def test_a_program_that_ignores_stop_is_killed(tmp_path):
    spec = make_spec(tmp_path)
    command = raw_program(
        tmp_path,
        """
        import signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        """,
        DESCRIBING,
        """
        for frame in frames():
            pass
        while True:
            pass
    """,
    )
    driver, heard = WireDriver(command), Heard()
    await driver.start(spec, heard)
    record = Record.read(spec.folder)

    await driver.stop(0.05)

    assert group_of(record.pid) is None
    assert await heard.until(Exited)


async def test_a_program_that_forks_leaves_nothing_after_stop(tmp_path):
    marker = tmp_path / "child"
    command = raw_program(
        tmp_path,
        f"""
        import subprocess
        child = subprocess.Popen(["sleep", "100"], stdout=subprocess.DEVNULL)
        open({str(marker)!r}, "w").write(str(child.pid))
        """,
        DESCRIBING,
        """
        sys.stdin.read()
    """,
    )
    driver, _ = await started(tmp_path, command)
    child = int(marker.read_text())

    await driver.stop(1)

    assert not running(child)


async def test_a_program_gets_to_end_on_the_end_of_its_stdin(tmp_path):
    marker = tmp_path / "cleaned"
    command = raw_program(
        tmp_path,
        DESCRIBING,
        f"""
        import signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        for frame in frames():
            reply(frame, None)
        time.sleep(0.05)
        open({str(marker)!r}, "w").write("cleaned up")
    """,
    )
    driver, heard = await started(tmp_path, command)

    await driver.stop(5)

    assert marker.read_text() == "cleaned up"
    assert (await heard.until(Exited)).reason == "exited with code 0"


async def test_a_report_with_nobody_to_hear_it_is_no_crash(tmp_path):
    spec = make_spec(tmp_path)
    command = program(
        tmp_path,
        SERVED,
        """
        serve(ScriptedDriver([[Hang()]]))
    """,
    )
    driver, heard = WireDriver(command), Heard()
    await driver.start(spec, heard)

    driver._peer.close()
    await heard.until(Exited)
    await driver.stop(1)

    assert (await heard.until(Exited)).reason == "exited with code 0"
    assert "Traceback" not in (spec.folder / LOG).read_text()


async def test_stop_before_start_does_nothing():
    await WireDriver(["true"]).stop(1)


async def test_a_verb_before_start_is_refused():
    with pytest.raises(DriverError, match="has not started"):
        await WireDriver(["true"]).deliver(DELIVERY)


async def test_credentials_reach_the_program_s_environment_and_no_frame(tmp_path):
    log = tmp_path / "frames.jsonl"
    secret, token = "model-key-value", "tool-token-value"
    bin = tmp_path / "bin"
    bin.mkdir()
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret(token), namespace="ph", bin=bin)
    command = raw_program(
        tmp_path,
        f"""
        for frame in frames():
            with open({str(log)!r}, "a") as file:
                seen = {{"frame": frame, "key": os.environ["MODEL_KEY"], "tok": os.environ[{TOKEN_VARIABLE!r}]}}
                file.write(json.dumps(seen) + "\\n")
            reply(frame, {{"native": "n"}})
            break
        sys.stdin.read()
    """,
    )
    driver, _ = await started(tmp_path, command, access={"MODEL_KEY": Secret(secret)}, tools=tools)
    await driver.stop(1)

    seen = json.loads(log.read_text())
    assert (seen["key"], seen["tok"]) == (secret, token)
    frame = json.dumps(seen["frame"])
    assert secret not in frame and token not in frame
    assert seen["frame"]["params"]["spec"]["access"] == ["MODEL_KEY"]
    assert "token" not in seen["frame"]["params"]["spec"]["tools"]


async def test_a_served_driver_gets_its_credentials_back_from_the_environment(tmp_path):
    bin = tmp_path / "bin"
    bin.mkdir()
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret("tool-token"), namespace="ph", bin=bin)
    command = program(
        tmp_path,
        SERVED,
        """
        class Showing(ScriptedDriver):
            async def start(self, spec, report):
                await report(Item(kind="message", gist=spec.access["MODEL_KEY"].reveal()))
                await report(Item(kind="message", gist=spec.tools.token.reveal()))
                await report(Item(kind="message", gist=str(spec.folder)))

        serve(Showing())
    """,
    )
    spec = make_spec(tmp_path, access={"MODEL_KEY": Secret("model-key")}, tools=tools)
    driver, heard = WireDriver(command), Heard()
    await driver.start(spec, heard)
    await heard.until(Item, lambda item: item.gist.endswith("wire"))
    await driver.stop(1)

    assert [item.gist for item in heard.of(Item)] == ["model-key", tools.token.reveal(), str(spec.folder / "wire")]


async def test_stderr_is_the_program_s_log(tmp_path):
    spec = make_spec(tmp_path)
    command = raw_program(
        tmp_path,
        DESCRIBING,
        """
        print("a log line", file=sys.stderr, flush=True)
    """,
    )
    driver, heard = WireDriver(command), Heard()
    await driver.start(spec, heard)
    await heard.until(Exited)
    await driver.stop(1)

    assert (spec.folder / LOG).read_text() == "a log line\n"


async def test_stop_removes_the_record(tmp_path):
    spec = make_spec(tmp_path)
    driver, _ = WireDriver(raw_program(tmp_path, DESCRIBING, "sys.stdin.read()")), None
    await driver.start(spec, Heard())
    assert (spec.folder / RECORD).exists()

    await driver.stop(1)

    assert not (spec.folder / RECORD).exists()


async def test_eof_on_stdin_stops_a_served_driver(tmp_path):
    marker = tmp_path / "stopped"
    command = program(
        tmp_path,
        SERVED,
        f"""
        class Marking(ScriptedDriver):
            async def stop(self, grace):
                open({str(marker)!r}, "w").write("stopped")
                await super().stop(grace)

        serve(Marking([[Hang()]]))
    """,
    )
    driver, heard = await started(tmp_path, command)

    driver._peer.close()
    await heard.until(Exited)
    await driver.stop(1)

    assert marker.read_text() == "stopped"
