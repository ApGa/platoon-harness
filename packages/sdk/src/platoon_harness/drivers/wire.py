"""A driver in another process or language: line-delimited JSON-RPC 2.0 on stdio, its verbs equal to the Python methods.

Credentials never travel in a frame. `start` names them, and the program finds their values in its own environment.
"""

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from platoon_harness.config import WIRE_PROTOCOL, Secret
from platoon_harness.primitives import REPORTS, Report, Verdict
from platoon_harness.rpc import INVALID_PARAMS, METHOD_NOT_FOUND, Closed, Peer, RpcError
from platoon_harness.tools.ph import TOKEN_VARIABLE

from . import (
    AgentSpec,
    Delivery,
    Driver,
    DriverError,
    DriverInfo,
    Receipt,
    Reconciled,
    Reporter,
    Started,
    ToolBinding,
    unknown_frame,
)
from .env import inherited
from .process import Process

DRIVER_ERROR = -32001
UNKNOWN_PROTOCOL = -32002

_DESCRIBE_TIMEOUT = 30.0
_END_GRACE = 5.0

__all__ = ["DRIVER_ERROR", "UNKNOWN_PROTOCOL", "WireDriver", "serve"]


def _to_frame(spec: AgentSpec) -> dict[str, Any]:
    """A spec with credentials by name. The program's own folder sits inside the agent's, so that its record and ours
    stay apart, and `reap` finds both."""
    tools = None if spec.tools is None else spec.tools.model_dump(mode="json", exclude={"token"})
    fields = spec.model_dump(mode="json", exclude={"access", "tools", "folder"})
    return {**fields, "folder": str(spec.folder / "wire"), "tools": tools, "access": sorted(spec.access)}


def _from_frame(frame: Mapping[str, Any], environ: Mapping[str, str]) -> AgentSpec:
    access = {name: Secret(environ[name]) for name in frame["access"]}
    tools = frame["tools"]
    binding = None if tools is None else ToolBinding(**tools, token=Secret(environ[TOKEN_VARIABLE]))
    return AgentSpec.model_validate({**frame, "access": access, "tools": binding})


class WireDriver:
    """The one adapter for a driver in another process. One instance runs one program for one agent."""

    def __init__(self, command: Sequence[str]) -> None:
        self._command = tuple(command)
        self._info: DriverInfo | None = None
        self._process: Process | None = None
        self._peer: Peer | None = None

    def describe(self) -> DriverInfo:
        """Ask the program, which stays up only long enough to answer, so no harness starts. This blocks, as the method
        is synchronous, and the answer is kept."""
        if self._info is None:
            self._info = self._ask_for_description()
        return self._info

    def _ask_for_description(self) -> DriverInfo:
        request = {"jsonrpc": "2.0", "id": 1, "method": "describe", "params": {"protocol": WIRE_PROTOCOL}}
        try:
            done = subprocess.run(
                self._command,
                input=json.dumps(request).encode() + b"\n",
                capture_output=True,
                env=inherited(),
                timeout=_DESCRIBE_TIMEOUT,
                check=False,
            )
            frame = json.loads(done.stdout.partition(b"\n")[0])
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            raise DriverError(f"{self._command[0]} did not describe itself: {error}") from error
        if "error" in frame:
            raise DriverError(f"{self._command[0]} did not describe itself: {frame['error'].get('message')}")
        result = frame.get("result", {})
        if result.get("protocol") != WIRE_PROTOCOL:
            raise DriverError(f"{self._command[0]} speaks protocol {result.get('protocol')}, not {WIRE_PROTOCOL}")
        return DriverInfo.model_validate({key: value for key, value in result.items() if key != "protocol"})

    def _read(self, process: Process) -> Any:
        self._process = process
        self._peer = Peer(process.stdout, process.stdin, self._inbound, stray=self._stray)
        return self._peer.run()

    async def _inbound(self, method: str, params: Any) -> None:
        if method != "report":
            raise RpcError(METHOD_NOT_FOUND, f"no method {method}")
        assert self._process is not None
        try:
            self._process.put(REPORTS.validate_json(json.dumps(params)))
        except ValidationError as error:
            raise RpcError(INVALID_PARAMS, "not a report in the vocabulary") from error

    def _stray(self, line: bytes, why: str) -> None:
        assert self._process is not None
        for report in unknown_frame("frame", line.decode(errors="replace")):
            self._process.put(report)

    async def _call(self, verb: str, params: Any = None) -> Any:
        if self._peer is None:
            raise DriverError("this driver has not started")
        try:
            return await self._peer.call(verb, params)
        except RpcError as error:
            raise DriverError(error.message) from error
        except Closed as error:
            raise DriverError(f"{self._command[0]} is gone: {error}") from error

    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        await Process.launch(self._command, spec, report, read=self._read)
        return Started.model_validate(await self._call("start", {"protocol": WIRE_PROTOCOL, "spec": _to_frame(spec)}))

    async def deliver(self, delivery: Delivery) -> Receipt:
        return Receipt.model_validate(await self._call("deliver", delivery.model_dump(mode="json")))

    async def interrupt(self) -> Receipt:
        return Receipt.model_validate(await self._call("interrupt"))

    async def answer(self, approval: str, verdict: Verdict) -> None:
        await self._call("answer", {"approval": approval, "verdict": verdict})

    async def reconcile(self, input_id: str) -> Reconciled:
        return await self._call("reconcile", {"input": input_id})

    async def stop(self, grace: float) -> None:
        """Ask the program to end what it owns and to exit when its stdin ends, within `grace`. Then `grace` more ends
        what is left, so this takes at most twice `grace`."""
        if self._process is None or self._peer is None:
            return
        with contextlib.suppress(DriverError, TimeoutError):
            async with asyncio.timeout(grace):
                await self._call("stop", {"grace": grace})
                self._peer.close()
                await self._process.exited()
        self._peer.close()
        await self._process.stop(grace)


async def _stdio() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
    return reader, asyncio.StreamWriter(transport, protocol, None, loop)


class _Server:
    """The seven verbs of one driver, as a `Peer` handler."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._peer: Peer | None = None
        self._running = False

    async def run(self) -> None:
        self._peer = Peer(*await _stdio(), self._handle)
        await self._peer.run()
        if self._running:
            await self._driver.stop(_END_GRACE)

    async def _report(self, report: Report) -> None:
        """Send a report. With the runtime gone nobody can hear it, which is no fault of the driver's."""
        assert self._peer is not None
        with contextlib.suppress(Closed):
            await self._peer.notify("report", report.model_dump(mode="json"))

    async def _handle(self, method: str, params: Any) -> Any:
        try:
            return await self._verb(method, params or {})
        except DriverError as error:
            raise RpcError(DRIVER_ERROR, str(error)) from error
        except (KeyError, TypeError, ValidationError) as error:
            raise RpcError(INVALID_PARAMS, f"bad params for {method}: {error}") from error

    def _check_protocol(self, params: Mapping[str, Any]) -> None:
        if params["protocol"] != WIRE_PROTOCOL:
            raise RpcError(
                UNKNOWN_PROTOCOL, f"protocol {params['protocol']} is unknown here: this speaks {WIRE_PROTOCOL}"
            )

    async def _verb(self, method: str, params: Mapping[str, Any]) -> Any:
        driver = self._driver
        match method:
            case "describe":
                self._check_protocol(params)
                return {"protocol": WIRE_PROTOCOL, **driver.describe().model_dump(mode="json")}
            case "start":
                self._check_protocol(params)
                self._running = True
                started = await driver.start(_from_frame(params["spec"], os.environ), self._report)
                return started.model_dump(mode="json")
            case "deliver":
                return (await driver.deliver(Delivery.model_validate(params))).model_dump(mode="json")
            case "interrupt":
                return (await driver.interrupt()).model_dump(mode="json")
            case "answer":
                await driver.answer(params["approval"], params["verdict"])
                return None
            case "reconcile":
                return await driver.reconcile(params["input"])
            case "stop":
                self._running = False
                await driver.stop(params["grace"])
                return None
            case _:
                raise RpcError(METHOD_NOT_FOUND, f"no method {method}")


def serve(driver: Driver) -> None:
    """Serve one driver on this process's stdio until stdin ends, which is all a wire driver in Python needs. Stdout
    belongs to the protocol, so anything else goes to stderr, which the runtime keeps in the agent's log."""
    asyncio.run(_Server(driver).run())
