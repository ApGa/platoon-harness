"""One derivation from `ops.list`: what each surface shows a model, for the token that asks."""

import json
import re

import pytest

from platoon_harness.kernel import Args, Extension, Kernel, ManualClock, Op, Outcome, Principal, Refusal, Txn, op
from platoon_harness.kernel.model import RefusalCode
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.tools import Surface, harness_name, list_tools, preamble, shell_name, tool_name
from platoon_harness.tools.surface import delivery_text, describe, named_surface, notices_text, refusal_text

from ..kernel.support import grant
from ..primitives.support import spawn
from ..primitives.test_tool_surface import NEVER_REFUSED
from .support import BUILT, enrolled

SURFACES: dict[str, Surface] = {"mcp": tool_name, "harness": harness_name("coord"), "shell": shell_name}
TOOLS = [operation for extension in PRIMITIVES for operation in extension.ops if operation.tool]
OPS = {operation.name for extension in PRIMITIVES for operation in extension.ops}
BACKTICKED = re.compile(r"`([^`]+)`")


def test_each_surface_has_its_own_name_for_a_tool():
    assert tool_name("task.claim") == "task_claim"
    assert harness_name("coord")("task.claim") == "mcp__coord__task_claim"
    assert shell_name("task.claim") == "ph task.claim"


@pytest.mark.parametrize(
    ("name", "shown"), [("mcp", "task_claim"), ("ph", "ph task.claim"), ("mcp__coord", "mcp__coord__task_claim")]
)
def test_a_client_names_its_surface(name, shown):
    assert named_surface(name)("task.claim") == shown


@pytest.mark.parametrize("name", ["", "shell", "mcp__", "mcp__a b", "mcp__a/b"])
def test_a_surface_nobody_knows_is_refused(name):
    with pytest.raises(ValueError, match="no surface"):
        named_surface(name)


def _texts(tool: dict) -> list[str]:
    fields = tool["inputSchema"]["properties"].values()
    return [tool["description"], *(field["description"] for field in fields)]


@pytest.fixture
async def every_tool(tmp_path):
    kernel = Kernel.open(tmp_path / "all", clock=ManualClock(1.0), extensions=PRIMITIVES)
    agent = Principal(id="agent:all")
    await kernel.submit(kernel.runtime, "principal.add", {"id": agent.id})
    await grant(kernel, "agent")
    yield kernel, agent
    kernel.close()


async def test_a_reader_holding_only_one_tool_loses_no_fact_with_a_pointer(every_tool):
    kernel, _ = every_tool
    lost = []
    for number, operation in enumerate(TOOLS):
        reader = Principal(id=f"agent:only-{number}")
        scopes = [operation.name, "ops.list"]
        await kernel.submit(kernel.runtime, "principal.add", {"id": reader.id, "scopes": scopes})
        tool = next(tool for tool in list_tools(kernel, reader) if tool["title"] == operation.name)
        lost += [
            f"{operation.name}.{name}"
            for name, field in tool["inputSchema"]["properties"].items()
            if not field["description"]
        ]
        if operation.name not in NEVER_REFUSED and "Refused" not in tool["description"]:
            lost.append(operation.name)

    assert lost == []


async def test_every_tool_is_listed_to_who_holds_it(every_tool):
    assert {tool["title"] for tool in list_tools(*every_tool)} == {operation.name for operation in TOOLS}


@pytest.mark.parametrize("surface", SURFACES.values(), ids=SURFACES)
async def test_a_description_names_ops_as_its_surface_does(every_tool, surface):
    named = set()
    for tool in list_tools(*every_tool, surface):
        for text in _texts(tool):
            for word in BACKTICKED.findall(text):
                assert word not in OPS or surface(word) == word, f"{tool['title']} leaves `{word}` unrendered"
                named.add(word)
    assert {surface(name) for name in OPS} & named, "no description named a tool at all"


@pytest.mark.parametrize("surface", SURFACES.values(), ids=SURFACES)
async def test_every_tool_a_description_names_exists_on_its_surface(every_tool, surface):
    kernel, _ = every_tool
    shown = {surface(name) for name in kernel.ops}
    dotted = re.compile(r"[a-z]+\.[a-z]+")
    for tool in list_tools(*every_tool, surface):
        for text in _texts(tool):
            for word in BACKTICKED.findall(text):
                last = word.removeprefix("ph ")
                assert dotted.fullmatch(last) is None or word in shown, f"{tool['title']} names `{word}`"


@pytest.mark.parametrize("surface", SURFACES.values(), ids=SURFACES)
@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
async def test_every_argument_a_surface_shows_is_described(every_tool, surface, tool: Op):
    shown = {entry["title"]: entry for entry in list_tools(*every_tool, surface)}[tool.name]

    assert [name for name, field in shown["inputSchema"]["properties"].items() if not field.get("description")] == []


async def test_a_description_says_what_a_refusal_means_on_every_surface(every_tool):
    never_refused = {"agent.finish", "channel.list", "peers", "session.status", "wait.progress"}

    for surface in SURFACES.values():
        for tool in list_tools(*every_tool, surface):
            assert tool["title"] in never_refused or "Refused" in tool["description"]


def test_a_description_leaves_what_is_no_op_alone():
    text = "Call `task.claim` with `queue`, or `wait`,\n    then `no.such`."

    assert describe(text, shell_name, {"task.claim", "wait"}) == (
        "Call `ph task.claim` with `queue`, or `ph wait`, then `no.such`."
    )


async def test_a_schema_refuses_what_it_does_not_declare(every_tool):
    assert all(tool["inputSchema"]["additionalProperties"] is False for tool in list_tools(*every_tool))


async def test_a_schema_shows_only_what_a_model_should_see(every_tool):
    shown = {tool["title"]: tool["inputSchema"] for tool in list_tools(*every_tool)}

    assert "on" not in shown["wait"]["properties"] and "from" in shown["wait"]["properties"]
    assert set(shown["channel.create"]["properties"]) == {"name", "kind", "readers", "writers", "delivery"}
    assert "title" not in str(shown["wait"]) and "description" not in shown["session.status"]


async def test_a_body_is_offered_as_text(every_tool):
    shown = {tool["title"]: tool["inputSchema"]["properties"] for tool in list_tools(*every_tool)}
    bodied = {name: fields["body"] for name, fields in shown.items() if "body" in fields}

    assert {"agent.spawn", "agent.finish", "message.send", "board.post", "task.add", "task.complete"} <= bodied.keys()
    assert all(field["type"] == "string" and "sha256" not in str(field) for field in bodied.values())


async def test_a_field_called_body_that_cites_no_hash_is_left_alone(tmp_path):
    class Plain(Args):
        body: str

    @op("plain.keep", tool=True)
    def keep(txn: Txn, a: Plain) -> None:
        """Keep some text. Refused never."""

    kernel = Kernel.open(tmp_path / "plain", clock=ManualClock(1.0), extensions=[Extension("plain", ops=[keep])])
    await kernel.submit(kernel.runtime, "principal.add", {"id": "agent:a"})
    await grant(kernel, "agent")

    shown = list_tools(kernel, Principal(id="agent:a"))[0]["inputSchema"]["properties"]["body"]
    kernel.close()

    assert shown == {"type": "string"}


async def test_read_only_is_set_honestly(every_tool):
    hints = {tool["title"]: tool["annotations"]["readOnlyHint"] for tool in list_tools(*every_tool)}

    assert hints["peers"] and hints["session.status"] and hints["wait.progress"]
    assert not hints["task.claim"] and not hints["message.send"]
    assert not hints["message.read"], "an agent's read moves its cursor and records exposure"


CEILINGS = {"lead": 23_500, "worker": 23_500, "narrow": 7_000}


@pytest.mark.parametrize("role", CEILINGS)
async def test_a_tool_list_stays_under_its_ceiling(kernel, server, lead, role):
    """This text is in every request of every agent, so it has a ceiling, just above where it stands: `json.dumps` of
    `list_tools` on the surface a harness reads. A wording fix passes. A new tool has to argue for its bytes."""
    principal = lead[0] if role == "lead" else (await enrolled(kernel, server, "n1", role=role, by=lead[0]))[0]

    size = len(json.dumps(list_tools(kernel, principal, harness_name("ph"))))

    assert size <= CEILINGS[role], f"{BUILT.roles[role].tools} now costs {size} bytes in every request"


async def test_the_default_roles_do_not_carry_what_only_a_program_needs(every_tool):
    assert not {tool["title"] for tool in list_tools(*every_tool)} & {"task.renew", "agent.list"}


async def test_tools_keep_the_op_as_a_title(every_tool):
    shown = {tool["name"]: tool["title"] for tool in list_tools(*every_tool)}

    assert shown["task_claim"] == "task.claim"


async def test_the_preamble_names_the_exact_tools_an_agent_holds(kernel, server, lead, worker):
    agent, _ = worker

    text = preamble(kernel, agent, harness_name("coord"))

    held = {f"mcp__coord__{tool['name']}" for tool in list_tools(kernel, agent)}
    assert set(re.findall(r"`(mcp__coord__\w+)`", text)) == held


async def test_the_preamble_lists_a_narrow_role_as_narrow(kernel, server, lead):
    agent, _ = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])

    text = preamble(kernel, agent)

    assert "`message_send`" in text and "`task_claim`" not in text and "Channels" not in text


async def test_the_preamble_says_who_can_be_reached_now(kernel, server, lead, worker):
    assert "You can message: @lead." in preamble(kernel, worker[0])
    assert "You can message: @w1." in preamble(kernel, lead[0])
    assert "Channels: notes (board), tasks (queue)." in preamble(kernel, lead[0])


async def test_the_preamble_names_the_roles_an_agent_may_start(kernel, server, lead, worker):
    assert "You can start agents in these roles: narrow, steered, worker." in preamble(kernel, lead[0])
    assert "start agents" not in preamble(kernel, worker[0])


async def test_the_preamble_teaches_parking(kernel, lead):
    assert "call `wait` and end your turn" in preamble(kernel, lead[0])
    assert "call `ph wait` and end your turn" in preamble(kernel, lead[0], shell_name)


async def test_the_preamble_tells_a_spawned_agent_to_finish_and_a_root_to_stay(kernel, lead, worker):
    assert "make `agent_finish` your last call" in preamble(kernel, worker[0])
    assert "make `ph agent.finish` your last call" in preamble(kernel, worker[0], shell_name)
    assert "When told to finish, make `agent_finish` your last call" in preamble(kernel, lead[0])
    assert "When your goal is done" not in preamble(kernel, lead[0])


async def test_the_preamble_points_a_shell_at_help(kernel, lead):
    assert "`ph --help`" in preamble(kernel, lead[0], shell_name)
    assert "`ph --help`" not in preamble(kernel, lead[0])


@pytest.mark.parametrize("query", ["peers", "channel.list"])
async def test_a_refused_query_leaves_its_line_out_of_the_preamble(kernel, lead, query, monkeypatch):
    real = kernel.query

    def refusing(principal, op, args):
        return (
            Outcome(op=op, args_hash="", refusal=Refusal(code="unavailable"))
            if op == query
            else real(principal, op, args)
        )

    monkeypatch.setattr(kernel, "query", refusing)

    text = preamble(kernel, lead[0])

    assert ("You can message" in text) == (query != "peers") and ("Channels" in text) == (query != "channel.list")


async def test_the_preamble_says_when_there_are_more_than_it_shows(kernel, server, lead):
    for number in range(300):
        await spawn(kernel, f"worker-with-a-long-name-{number:03}", by=lead[0])

    text = preamble(kernel, lead[0])

    assert "and more: call `peers`." in text


async def test_the_preamble_journals_nothing(kernel, lead):
    head = kernel.head

    preamble(kernel, lead[0])

    assert kernel.head == head


async def test_a_description_names_only_tools_its_reader_holds(kernel, server, lead, worker):
    narrow, _ = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])

    for principal in (lead[0], worker[0], narrow):
        tools = list_tools(kernel, principal)
        held = {tool["name"] for tool in tools}
        for tool in tools:
            for text in _texts(tool):
                named = {word for word in BACKTICKED.findall(text) if word in {*map(tool_name, kernel.ops)} - {"wait"}}
                assert named <= held, f"{principal.id} is told of {sorted(named - held)} by {tool['title']}"


async def test_no_description_leaves_a_sentence_half_said(kernel, server, lead):
    narrow, _ = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])

    described = {tool["title"]: tool["description"] for tool in list_tools(kernel, narrow)}

    assert "Refused `not_permitted` when you cannot reach the target." in described["message.send"]
    assert "Call `peers`" not in described["message.send"]


def test_every_refusal_code_has_words():
    for code in RefusalCode.__value__.__args__:
        text = refusal_text(Refusal(code=code), tool_name, OPS, OPS)
        assert text.startswith(f"Refused {code}: ") and "Next: " in text


def test_a_refusal_names_only_ops_that_exist():
    for code in RefusalCode.__value__.__args__:
        words = BACKTICKED.findall(refusal_text(Refusal(code=code), lambda op: f"<{op}>", OPS, OPS))
        assert [word for word in words if word.startswith("<") and word[1:-1] not in OPS] == []
        assert [word for word in words if "." in word and not word.startswith("<")] == []


def test_a_refusal_carries_everything_it_was_given():
    refusal = Refusal(code="busy", object="queue/tasks", retry_after=1.5, reachable=("@a", "@b"), detail={"depth": 3})

    assert refusal_text(refusal, tool_name, OPS, OPS).splitlines() == [
        "Refused busy on queue/tasks: The session is too busy to take this now, and nothing ran.",
        'Why: {"depth": 3}',
        "Next: Try the same call again shortly.",
        "Retry after 1.500 seconds.",
        "You can reach: @a, @b.",
    ]


def test_notices_say_how_many_more_are_waiting():
    handed = {"items": [{"ref": "inbox/a@1", "gist": "stop", "sender": "@a", "body": None}], "behind": 2}

    assert notices_text(handed, shell_name, OPS, OPS).splitlines()[1:] == [
        "- inbox/a@1 from @a: stop",
        "2 more are waiting: call `ph message.read`.",
    ]


def test_a_handover_points_only_at_tools_its_reader_holds():
    item = {"ref": "inbox/a@1", "gist": "read this", "sender": "@lead", "body": "sha256:abc"}

    text = delivery_text({"input": 41, "items": [item], "behind": 2}, tool_name, OPS, {"wait"})

    assert text.splitlines() == ["New messages (delivery 41):", "- inbox/a@1 from @lead: read this"]


def test_a_delivery_reads_in_the_words_of_its_surface_and_names_its_input():
    item = {"ref": "inbox/a@1", "gist": "read this", "sender": "@lead", "body": "sha256:abc"}

    text = delivery_text({"input": 41, "items": [item], "behind": 0}, harness_name("ph"), OPS, OPS)

    assert text.splitlines() == [
        "New messages (delivery 41):",
        "- inbox/a@1 from @lead: read this",
        "  Its body is sha256:abc: pass that as `ref` to `mcp__ph__blob_get`.",
    ]


def test_a_refusal_never_sends_a_model_to_a_tool_it_does_not_hold():
    text = refusal_text(Refusal(code="not_permitted"), tool_name, OPS, {"message.send"})

    assert "channel_list" not in text and "peers" not in text
    assert text.splitlines()[-1] == "Next: Carry on without it, and say so."


def test_a_refusal_s_reason_never_sends_a_model_to_a_tool_it_does_not_hold():
    detail = "lead has children at work. `wait` lets them finish. `agent.cancel` stops one now. They are @w1"

    text = refusal_text(Refusal(code="conflict", detail=detail), tool_name, OPS, {"wait"})

    assert "Why: lead has children at work. `wait` lets them finish. They are @w1" in text


def test_a_refusal_keeps_a_next_step_a_model_can_take():
    text = refusal_text(Refusal(code="queue_empty"), tool_name, OPS, {"wait"})

    assert "Next: Call `wait` with `queue` and end your turn." in text
