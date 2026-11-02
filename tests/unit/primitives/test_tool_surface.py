"""What a model reads: every tool describes each argument, says what a refusal means, and names real ops."""

import re

import pytest

from platoon_harness.kernel import Kernel, ManualClock, Op
from platoon_harness.primitives import PRIMITIVES

TOOLS = [operation for extension in PRIMITIVES for operation in extension.ops if operation.tool]
NEVER_REFUSED = {"agent.finish", "channel.list", "peers", "session.status", "wait.progress"}
OP_NAME = re.compile(r"`([a-z]+\.[a-z]+)`")


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
def test_every_argument_a_model_sees_is_described(tool: Op):
    shown = tool.input.model_json_schema().get("properties", {})

    assert [name for name, field in shown.items() if not field.get("description")] == []


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
def test_a_description_says_what_a_refusal_means(tool: Op):
    assert tool.name in NEVER_REFUSED or "Refused" in tool.fn.__doc__


def test_a_description_never_names_an_op_that_is_not_there(tmp_path):
    kernel = Kernel.open(tmp_path / "session", clock=ManualClock(1.0), extensions=PRIMITIVES)
    loaded = set(kernel.ops)
    kernel.close()

    named = {name for tool in TOOLS for name in OP_NAME.findall(tool.fn.__doc__)}

    assert named - loaded == set()


def test_a_tool_shows_no_stream_names_or_queue_settings():
    tools = {tool.name: tool.input.model_json_schema()["properties"] for tool in TOOLS}

    assert "on" not in tools["wait"]
    assert set(tools["channel.create"]) == {"name", "kind", "readers", "writers", "delivery"}
    assert "cause" not in tools["message.send"]
