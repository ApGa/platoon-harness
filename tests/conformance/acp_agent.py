"""A scripted ACP agent for the conformance suite: `ScriptedDriver` behind ACP's protocol 1 on stdio, on FakeModel.

Its session is a `ScriptedDriver` whose every turn asks the model, started at the first prompt with the model its config
option holds, the instructions its system prompt gave and our tools from the MCP server `session/new` gave, keeping its
state in its harness's folder where `reap` looks for a program's own. What the scripted harness reports goes back as ACP
updates, an approval as a permission request whose tool call holds the whole ask, and a turn's end as the prompt's
answer. It follows the version 1 schema as read, so it shows what the driver does with ACP, and nothing of a real agent.
"""

import asyncio
import contextlib
import os
import uuid
from pathlib import Path
from typing import Any

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    Item,
    Report,
    ToolBinding,
    TurnEnded,
)
from platoon_harness.drivers.process import WIRE
from platoon_harness.rpc import INTERNAL_ERROR, INVALID_PARAMS, METHOD_NOT_FOUND, Closed, Peer, RpcError
from platoon_harness.testing import ScriptedDriver, every_turn_asks_the_model
from platoon_harness.testing.scripted import API_KEY, BASE_URL

MODEL = "fake-model"
OPTIONS = [
    {"optionId": "allow", "name": "Allow once", "kind": "allow_once"},
    {"optionId": "always", "name": "Always allow", "kind": "allow_always"},
    {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
]
FOLDER = Path(os.environ["TMPDIR"]).parent / WIRE
"""The scripted harness's own folder: in its agent's, where `reap` finds a program's record and what it started."""
GRACE = 0.5


class Agent:
    """One connection, which holds one session."""

    def __init__(self) -> None:
        self.peer: Peer | None = None
        self.session = ""
        self.resume: str | None = None
        self.cwd = Path()
        self.tools: ToolBinding | None = None
        self.instructions: str | None = None
        self.model = MODEL
        self.driver: ScriptedDriver | None = None
        self.turn: asyncio.Future[str] | None = None
        self.calls: dict[str, str] = {}
        self.asking: set[asyncio.Task[None]] = set()

    async def handle(self, method: str, params: Any) -> Any:
        match method:
            case "initialize":
                sessions = {"resume": {}, "systemPrompt": {}}
                capabilities = {
                    "loadSession": False,
                    "mcpCapabilities": {"http": True},
                    "sessionCapabilities": sessions,
                }
                agent = {"name": "acp-scripted", "version": "1"}
                return {"protocolVersion": 1, "agentCapabilities": capabilities, "agentInfo": agent, "authMethods": []}
            case "session/new":
                self.setup(params)
                self.session = f"s-{uuid.uuid4().hex[:8]}"
                return {"sessionId": self.session, "configOptions": self.options()}
            case "session/resume":
                self.setup(params)
                self.session = params["sessionId"]
                self.resume = f"scripted-{self.session}"
                return {"configOptions": self.options()}
            case "session/set_config_option":
                if params["configId"] != "model" or params["value"] != MODEL:
                    raise RpcError(INVALID_PARAMS, f"no option {params['configId']} of {params['value']}")
                self.model = params["value"]
                return {"configOptions": self.options()}
            case "session/prompt":
                return await self.prompt("".join(block.get("text", "") for block in params["prompt"]))
            case "session/cancel":
                if self.driver is not None:
                    await self.driver.interrupt()
            case _:
                raise RpcError(METHOD_NOT_FOUND, f"no method {method}")

    def options(self) -> list[dict[str, Any]]:
        model = [{"value": MODEL, "name": MODEL}]
        return [
            {
                "id": "model",
                "name": "Model",
                "category": "model",
                "type": "select",
                "currentValue": self.model,
                "options": model,
            }
        ]

    def setup(self, params: dict[str, Any]) -> None:
        """The session's folder, our tools and the role's instructions, as `session/new` or `session/resume` said."""
        self.cwd = Path(params["cwd"])
        for server in params.get("mcpServers") or ():
            [bearer] = [header["value"] for header in server["headers"] if header["name"] == "Authorization"]
            token = Secret(bearer.removeprefix("Bearer "))
            self.tools = ToolBinding(url=server["url"], token=token, namespace=server["name"], bin=self.cwd)
        if (prompt := params.get("systemPrompt")) is not None:
            self.instructions = "".join(block["text"] for block in prompt["content"])

    async def prompt(self, text: str) -> dict[str, Any]:
        """A turn of the scripted harness on the prompt's text, started on the first, and its end as a stop reason."""
        if self.driver is None:
            self.driver = ScriptedDriver(every_turn_asks_the_model(), name="acp-scripted")
            access = {name: Secret(os.environ[name]) for name in (BASE_URL, API_KEY)}
            fields = {"cwd": self.cwd, "folder": FOLDER, "tools": self.tools, "access": access, "resume": self.resume}
            spec = AgentSpec(
                agent=self.session, role="agent", model=self.model, instructions=self.instructions, **fields
            )
            await self.driver.start(spec, self.report)
        self.turn = asyncio.get_running_loop().create_future()
        await self.driver.deliver(Delivery(input=uuid.uuid4().hex, boundary="turn", text=text, items=()))
        reason = await self.turn
        if reason.startswith("failed"):
            raise RpcError(INTERNAL_ERROR, reason)
        return {"stopReason": "cancelled" if reason == "interrupted" else "end_turn"}

    async def update(self, update: dict[str, Any]) -> None:
        assert self.peer is not None
        with contextlib.suppress(Closed):
            await self.peer.notify("session/update", {"sessionId": self.session, "update": update})

    async def report(self, report: Report) -> None:
        """What the scripted harness said, as ACP says it."""
        match report:
            case Delta(text=text):
                await self.update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}})
            case Item(kind="thought", body=str(body)):
                await self.update({"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": body}})
            case Item(kind="tool", phase="started", native_id=str(id), gist=gist):
                await self.update(
                    {"sessionUpdate": "tool_call", "toolCallId": id, "title": gist, "status": "in_progress"}
                )
            case Item(kind="tool", phase="completed", native_id=str(id), outcome=outcome):
                await self.update({"sessionUpdate": "tool_call_update", "toolCallId": id, "status": outcome})
            case Item(kind="tool", phase="completed", approval=str(approval), outcome=outcome):
                status = "completed" if outcome == "allow" else "failed"
                await self.update(
                    {"sessionUpdate": "tool_call_update", "toolCallId": self.calls.pop(approval), "status": status}
                )
            case ApprovalRequested():
                task = asyncio.create_task(self.ask(report))
                self.asking.add(task)
                task.add_done_callback(self.asking.discard)
            case Compacted(summary=summary):
                done = {
                    "compactionId": uuid.uuid4().hex,
                    "status": "completed",
                    "summary": [{"type": "text", "text": summary or ""}],
                }
                await self.update({"sessionUpdate": "compaction_update", **done})
            case TurnEnded(reason=reason):
                if self.turn is not None and not self.turn.done():
                    self.turn.set_result(reason)

    async def ask(self, asked: ApprovalRequested) -> None:
        """An approval as a tool call the agent says first, then a permission request naming it by its id, which holds
        the whole ask as its content."""
        assert self.peer is not None and self.driver is not None
        id = f"call-{uuid.uuid4().hex[:8]}"
        self.calls[asked.id] = id
        await self.update(
            {
                "sessionUpdate": "tool_call",
                "toolCallId": id,
                "title": asked.gist,
                "kind": "execute",
                "status": "pending",
            }
        )
        content = [{"type": "content", "content": {"type": "text", "text": asked.body or ""}}]
        call = {"toolCallId": id, "content": content}
        try:
            answer = await self.peer.call(
                "session/request_permission", {"sessionId": self.session, "toolCall": call, "options": OPTIONS}
            )
        except Closed:
            return
        allowed = answer["outcome"] == {"outcome": "selected", "optionId": "allow"}
        with contextlib.suppress(DriverError, asyncio.InvalidStateError):
            await self.driver.answer(asked.id, "allow" if allowed else "deny")


async def main() -> None:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(0, "rb", 0))
    transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, os.fdopen(1, "wb", 0))
    agent = Agent()
    agent.peer = Peer(reader, asyncio.StreamWriter(transport, protocol, None, loop), agent.handle)
    await agent.peer.run()
    if agent.driver is not None:
        await agent.driver.stop(GRACE)


asyncio.run(main())
