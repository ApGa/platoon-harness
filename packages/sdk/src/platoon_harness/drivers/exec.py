"""The `exec` driver: a one-shot CLI runs from config, with no code, and coordinates through `ph`."""

from collections.abc import Sequence

from platoon_harness.kernel import GIST_LIMIT
from platoon_harness.primitives import Verdict

from . import (
    AgentSpec,
    Capabilities,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
    Item,
    Ready,
    Receipt,
    Reconciled,
    Reporter,
    Started,
    TurnEnded,
    TurnStarted,
)
from .env import Held
from .process import Process, exit_reason

GOAL = "{goal}"

_CHUNK = 64 * 1024
_KEPT = 1024 * 1024
_INTERRUPT_GRACE = 2.0
_CAPABILITIES = Capabilities(interrupt="turn", tool_paths={"shell"})

__all__ = ["GOAL", "ExecDriver"]


class ExecDriver:
    """One process, one turn. `{goal}` in `command` becomes the goal. All it can say is what stdout and an exit say:
    the model it ran stays unknown, so nothing is reported as if it were not."""

    def __init__(self, command: Sequence[str]) -> None:
        self._command = tuple(command)
        self._process: Process | None = None
        self._interrupted = False

    def describe(self) -> DriverInfo:
        return DriverInfo(name="exec", capabilities=_CAPABILITIES)

    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        if spec.resume is not None:
            raise DriverError("a one-shot harness cannot resume")
        if not spec.goal:
            raise DriverError("a one-shot harness takes nothing after its goal: set `count = 0` and spawn it with one")
        if spec.effort is not None:
            raise DriverError("a one-shot command takes no effort from here: put it in the command")
        if GOAL in self._command and spec.goal.startswith("-"):
            raise DriverError("a goal that starts with `-` would reach this program as an option: reword it")
        command = [part.replace(GOAL, spec.goal) for part in self._command]
        self._process = await Process.launch(command, spec, report, read=self._read)
        return Started()

    async def _read(self, process: Process) -> None:
        """Pass stdout on as it comes, and when the process ends, end its turn with the last of what it said. A forked
        child can hold stdout open past that, so the process cancels this rather than wait for it."""
        process.stdin.close()
        process.put(Ready())
        process.put(TurnStarted(turn="1"))
        output = bytearray()
        held = Held(process.redact)
        try:
            while chunk := await process.stdout.read(_CHUNK):
                masked = held.feed(chunk)
                process.put(Delta(text=masked.decode(errors="replace")))
                output += masked
                del output[:-_KEPT]
            await process.exited()
        finally:
            if rest := held.flush():
                process.put(Delta(text=rest.decode(errors="replace")))
                output += rest
            if text := output.decode(errors="replace").strip():
                process.put(Item(kind="message", gist=text[-GIST_LIMIT:], body=text))
            process.put(TurnEnded(reason=self._ending(process.returncode)))

    def _ending(self, code: int | None) -> str:
        if self._interrupted:
            return "interrupted"
        return "stopped" if code == 0 else exit_reason(code)

    async def deliver(self, delivery: Delivery) -> Receipt:
        raise DriverError("a one-shot harness takes nothing after its goal")

    async def interrupt(self) -> Receipt:
        """Its one turn is the process, so stopping the turn stops the process."""
        if self._process is None:
            raise DriverError("this driver has not started")
        self._interrupted = True
        await self._process.stop(_INTERRUPT_GRACE)
        return Receipt(boundary="turn")

    async def answer(self, approval: str, verdict: Verdict) -> None:
        raise DriverError("a one-shot harness asks for no approvals")

    async def reconcile(self, input_id: str) -> Reconciled:
        return "unknown"

    async def stop(self, grace: float) -> None:
        if self._process is not None:
            await self._process.stop(grace)
