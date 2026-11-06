"""One OpenHands conversation for one agent: OpenHands' coding tools and ours, the project's instructions and ours, and
every action but ours asked about, or on a gateway a sealed one, with ours and the environment's tools alone. Importing
this loads the OpenHands SDK, which takes seconds."""

import sys
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from typing import Any, ClassVar
from uuid import UUID

from litellm import get_supported_openai_params
from openhands.sdk import LLM, Agent, AgentContext, LocalConversation, Tool
from openhands.sdk.context.condenser import default_condenser
from openhands.sdk.conversation.cancellation import CancellationToken
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event.llm_convertible import ActionEvent
from openhands.sdk.mcp import MCPClient, MCPServer, MCPToolAction, MCPToolDefinition, create_mcp_tools
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.confirmation_policy import ConfirmRisky
from openhands.sdk.security.risk import SecurityRisk
from openhands.sdk.tool import ToolDefinition, ToolExecutor
from openhands.sdk.tool.builtins.think import ThinkAction
from openhands.sdk.tool.registry import register_tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.preset.default import register_builtins_agents
from openhands.tools.task import TaskToolSet
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool

from platoon_harness.config import Secret
from platoon_harness.tools import SHIM

from .. import ENVIRONMENT, AgentSpec, DriverError, Gateway

Asked = Callable[[str, list[ActionEvent]], bool | None]
"""Whether a native child's step may run, or None to stop the child."""

_CALLING_RUN: ContextVar[CancellationToken | None] = ContextVar("calling_run", default=None)
"""The cancellation of the run whose call of `task` runs the child under way here."""

__all__ = ["pending", "ready", "start"]


def ours(action: ActionEvent) -> bool:
    """Whether an action calls our tools, which are the agent's only MCP tools, as nothing else gives it a server."""
    return isinstance(action.action, MCPToolAction)


class AllButOursAsk(SecurityAnalyzerBase):
    """The risk of an action as the approval rule reads it: ours are low, as the runtime authorizes each call itself,
    and every other is unknown, which asks."""

    def security_risk(self, action: ActionEvent) -> SecurityRisk:
        return SecurityRisk.LOW if ours(action) else SecurityRisk.UNKNOWN


class AskingTasks(TaskToolSet):
    """OpenHands' `task` tool, whose native children ask before a step as their parent does, through `asked`, as the
    tool alone would let them run. An interrupt that cuts off the call that started one stops it at its next ask, as
    nothing else reaches it. One agent runs per process, so the class holds it."""

    asked: ClassVar[Asked]

    @classmethod
    def create(
        cls, conv_state: ConversationState, confirmation_handler: Asked | None = None, sub_agent_scope: Any = None
    ) -> list[ToolDefinition]:
        tools = super().create(conv_state, _may_run, sub_agent_scope)
        return [tool.set_executor(_TaskExecutor(tool.executor)) for tool in tools]


class _TaskExecutor(ToolExecutor):
    """OpenHands' executor of a call of `task`, which keeps for the child the call runs the cancellation of the run
    that made it."""

    def __init__(self, executor: Any) -> None:
        self._executor = executor

    def __call__(self, action: Any, conversation: LocalConversation | None = None) -> Any:
        _CALLING_RUN.set(None if conversation is None else conversation.cancel_token)
        return self._executor(action, conversation)

    def close(self) -> None:
        self._executor.close()


def _may_run(task: str, actions: list[ActionEvent]) -> bool:
    """Whether a native child's step may run: a call of ours may, and the runtime decides the rest. A child whose call
    an interrupt cut off, or that the runtime stops, ends here, as raising is the one way the task tool lets one end."""
    run = _CALLING_RUN.get()
    cut = run is not None and run.is_cancelled
    allowed = None if cut else all(map(ours, actions)) or AskingTasks.asked(task, actions)
    if allowed is None:
        raise DriverError("the turn that started this agent was cut off")
    return allowed


register_tool(AskingTasks.name, AskingTasks)


def _llm(spec: AgentSpec, key: Secret, url: Secret | None) -> LLM:
    """The role's model on an endpoint that speaks Chat Completions. The SDK retries nothing, as a retry is a second
    call a gateway records. An effort is refused for a model litellm's catalog says takes none, as litellm would drop
    it unsaid."""
    effort: dict[str, Any] = {} if spec.effort is None else {"reasoning_effort": spec.effort}
    if effort and "reasoning_effort" not in (get_supported_openai_params(spec.model, "openai") or ()):
        raise DriverError(f"{spec.model} takes no effort, so {spec.effort} would be dropped")
    return LLM(
        model=f"openai/{spec.model}",
        base_url=None if url is None else url.reveal(),
        api_key=key.reveal(),
        usage_id="agent",
        api_mode="chat",
        num_retries=0,
        stream=True,
        **effort,
    )


def start(
    spec: AgentSpec,
    key: Secret,
    url: Secret | None,
    shim_env: Mapping[str, str],
    *,
    on_event: Callable[[Any], None],
    on_token: Callable[[Any], None],
    on_request: Callable[[str, str], None],
    asked: Asked,
) -> LocalConversation:
    """A conversation for `spec`, new or reopened by its id. The terminal runs commands in a subprocess, as a tmux one
    can outlive its agent, and the step cap is lifted, as a role's budget is what limits it. Only the agent's own LLM
    logs its requests, to `on_request`: the condenser's copy of it gets telemetry of its own, and a child's copy logs
    nothing, as `log_completions` would have either write a file where it runs. The agent starts agents of its own only
    if its role allows them, with OpenHands' built-in kinds.

    On a gateway the launch is sealed: none of OpenHands' coding tools, so ours, and the environment's once `ready`
    adds them, beside its own `finish` and `think`, which act on nothing, none of the project's instructions, and a
    condenser whose every call carries the gateway's compaction headers."""
    llm = _llm(spec, key, url)
    gateway = spec.access if isinstance(spec.access, Gateway) else None
    headers = None if gateway is None else dict(gateway.compaction_headers) or None
    condensing = llm.model_copy(update={"usage_id": "condenser", "extra_headers": headers})
    condensing.reset_metrics()
    llm.telemetry.log_enabled = True
    llm.telemetry.set_log_completions_callback(on_request)
    tools = [
        Tool(name=TerminalTool.name, params={"terminal_type": "subprocess"}),
        Tool(name=FileEditorTool.name),
        Tool(name=TaskTrackerTool.name),
    ]
    if gateway is not None:
        tools = []
    if spec.allow_native_children:
        AskingTasks.asked = asked
        register_builtins_agents(enable_browser=False)
        tools.append(Tool(name=AskingTasks.name))
    servers: dict[str, Any] = {}
    if spec.tools is not None:
        servers[spec.tools.namespace] = {"command": sys.executable, "args": ["-I", str(SHIM)], "env": dict(shim_env)}
    agent = Agent(
        llm=llm,
        tools=tools,
        mcp_config=servers,
        agent_context=AgentContext(load_project_skills=gateway is None, system_message_suffix=spec.instructions),
        condenser=default_condenser(condensing),
        critic=None,
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=str(spec.cwd),
        persistence_dir=str(spec.folder),
        conversation_id=None if spec.resume is None else UUID(spec.resume),
        callbacks=[on_event],
        token_callbacks=[on_token],
        max_iteration_per_run=sys.maxsize,
        visualizer=None,
        delete_on_close=False,
    )
    conversation.set_security_analyzer(AllButOursAsk())
    conversation.set_confirmation_policy(ConfirmRisky())
    return conversation


def ready(
    conversation: LocalConversation, spec: AgentSpec, key: Secret
) -> tuple[tuple[str, ...], tuple[str, ...], MCPClient | None]:
    """Ready the agent, which starts our server and the terminal, and say the tools it offers its model, which of them
    are ours, and on a gateway the client of the environment's server, whose tools it adds. That server is a client's
    own, so ours go by their own names, and its tools are each named `environment_<tool>`, as the SDK's client of two
    servers names a server's tools, so none collides with OpenHands' `finish` and `think`. The SDK readies an agent on a
    message, a run or a tool: `think` is the one with no other effect. This blocks."""
    conversation.execute_tool("think", ThinkAction(thought="ready"))
    ours = tuple(name for name, tool in conversation.agent.tools_map.items() if isinstance(tool, MCPToolDefinition))
    environment = None
    if isinstance(gateway := spec.access, Gateway) and gateway.tools is not None:
        server = MCPServer(url=gateway.tools, headers={"Authorization": f"Bearer {key.reveal()}"})
        environment = create_mcp_tools({ENVIRONMENT: server})
        conversation.agent.add_runtime_tools([_named_by(ENVIRONMENT, tool) for tool in environment.tools])
    return tuple(conversation.agent.tools_map), ours, environment


def _named_by(server: str, tool: MCPToolDefinition) -> MCPToolDefinition:
    """`tool` shown to the model as `<server>_<tool>`, and still called on its server by the name the server lists."""
    return tool.model_copy(update={"mcp_tool": tool.mcp_tool.model_copy(update={"name": f"{server}_{tool.name}"})})


def pending(conversation: LocalConversation) -> list[ActionEvent]:
    """The actions the agent took and nothing has answered yet."""
    return ConversationState.get_unmatched_actions(conversation.state.active_branch())
