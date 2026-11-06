"""One derivation from `ops.list`: what each surface shows a model, for the token that asks."""

import json
import re

import pytest

from platoon_harness.kernel import Args, Extension, Kernel, ManualClock, Op, Outcome, Principal, Refusal, Txn, op
from platoon_harness.kernel.model import RefusalCode
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime.opening import _one_of_each, _rehearsed
from platoon_harness.team import Capabilities
from platoon_harness.tools import (
    PREAMBLE,
    Surface,
    harness_name,
    instructions,
    list_tools,
    preamble,
    shell_name,
    slots,
    surface_of,
    tool_name,
)
from platoon_harness.tools.surface import (
    _CITING,
    _PARKING,
    _ending,
    _held,
    _listed,
    _teacher,
    delivery_text,
    describe,
    named_surface,
    notices_text,
    refusal_text,
)

from ..kernel.support import grant
from ..primitives.support import spawn
from ..primitives.test_tool_surface import NEVER_REFUSED
from ..topology.support import PRESET_TEAMS
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


@pytest.mark.parametrize(
    ("declared", "shown"),
    [
        ({}, None),
        ({"tool_paths": {"shell"}}, "ph task.claim"),
        ({"tool_paths": {"mcp-http", "shell"}}, "mcp__ph__task_claim"),
        ({"tool_paths": {"mcp-stdio"}, "tool_names": "bare"}, "task_claim"),
    ],
)
def test_a_harness_names_our_tools_as_it_declares(declared, shown):
    surface = surface_of(Capabilities(**declared))

    assert (surface and surface("task.claim")) == shown


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


CEILINGS = {"lead": 24_400, "worker": 23_500, "narrow": 7_000}


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


async def test_the_preamble_teaches_parking_as_waiting_for_something_named(kernel, lead):
    assert "call `wait` naming it and end your turn" in preamble(kernel, lead[0])
    assert "call `ph wait` naming it and end your turn" in preamble(kernel, lead[0], shell_name)
    assert "nothing to do" not in preamble(kernel, lead[0])


async def test_the_preamble_tells_an_agent_how_to_end_by_whether_it_stays(kernel, server, lead, worker):
    keeper, _ = await enrolled(kernel, server, "keeper", by=lead[0], stays=True)
    leaver, _ = await enrolled(kernel, server, "leaver", stays=False)

    assert "make `agent_finish` your last call, with your report" in preamble(kernel, worker[0])
    assert "make `ph agent.finish` your last call" in preamble(kernel, worker[0], shell_name)
    assert "When told to finish, make `agent_finish` your last call" in preamble(kernel, lead[0])
    assert "When your goal is done" not in preamble(kernel, lead[0])
    assert "When your goal is done" in preamble(kernel, leaver)
    staying = preamble(kernel, keeper)
    assert "Answer by ending your turn: what you say last in it goes to @lead" in staying
    assert "a turn that only ends leaves you here for the next message" in staying
    assert "Make `agent_finish` your last call only when told to finish" in staying
    assert "When your goal is done" not in staying


async def test_the_preamble_points_a_shell_at_help(kernel, lead):
    assert "`ph --help`" in preamble(kernel, lead[0], shell_name)
    assert "`ph --help`" not in preamble(kernel, lead[0])


@pytest.mark.parametrize("query", ["peers", "channel.list"])
async def test_a_refused_query_leaves_its_line_out_of_the_preamble(kernel, lead, worker, query, monkeypatch):
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
    item = {"ref": "inbox/a@1", "gist": "read this", "sender": "@lead", "body": True}

    text = delivery_text({"input": 41, "items": [item], "behind": 0}, harness_name("ph"), OPS, OPS)

    assert text.splitlines() == [
        "New messages (delivery 41):",
        "- inbox/a@1 from @lead: read this",
        "  It has a body: pass its ref as `ref` to `mcp__ph__blob_get`.",
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


def before_templates(kernel: Kernel, agent: Principal, surface: Surface) -> str:
    """The preamble as the code said it before it was a template, kept to hold the default template to it, but for a
    line that would name no peer or no channel, which goes as any line whose slots all come out empty does, and the line
    that asks an agent holding a write of content to cite, which the default says since it had a slot for it."""
    tools = _held(kernel, agent)
    held = sorted(op["name"] for op in tools)
    names = ", ".join(f"`{surface(op)}`" for op in held)
    lines = [
        f"You are @{agent.name}. You coordinate with this session through these tools, by exactly these names: {names}."
    ]
    if surface is shell_name:
        lines.append("Run `ph --help`, or `ph <tool> --help` for one tool's arguments.")
    if "peers" in held and (peers := kernel.query(agent, "peers", {})).refusal is None:
        reach = _listed(peers.result, "peers", lambda peer: peer["address"], surface("peers"))
        if reach:
            lines.append(f"You can message: {reach}.")
        if peers.result["roles"]:
            lines.append(f"You can start agents in these roles: {', '.join(peers.result['roles'])}.")
    if "channel.list" in held and (channels := kernel.query(agent, "channel.list", {})).refusal is None:
        kept = _listed(
            channels.result, "channels", lambda found: f"{found['name']} ({found['kind']})", surface("channel.list")
        )
        if kept:
            lines.append(f"Channels: {kept}.")
    teach = _teacher(surface, kernel.ops, held)
    citing = _CITING if any(_cites(op) for op in tools) else ""
    return "\n".join(filter(None, (*lines, teach(_PARKING), citing, teach(_ending(kernel, agent)))))


def _cites(op: dict) -> bool:
    return "based_on" in op["schema"].get("properties", {})


TEAMS = {**PRESET_TEAMS, "built": BUILT}


@pytest.mark.parametrize("name", TEAMS)
async def test_the_default_template_says_what_the_preamble_said(name):
    """Byte for byte, for every preset's roles and a team with a narrow role and a child that stays, on each surface."""
    team = TEAMS[name].resolved()
    capabilities = dict.fromkeys(team.roles, Capabilities(persistent=True))
    async with _rehearsed(team, capabilities) as kernel:
        agents = {role: agent async for role, agent in _one_of_each(kernel, team)}
        if name == "built":
            args = {"name": "keeper", "child_role": "worker", "stays": True}
            assert (await kernel.submit(agents["lead"], "agent.spawn", args)).refusal is None
            agents["keeper"] = Principal(id="agent:keeper")
        for agent in agents.values():
            for surface in SURFACES.values():
                assert preamble(kernel, agent, surface) == before_templates(kernel, agent, surface)


async def test_a_template_fills_its_slots_with_values_and_sentences(kernel, server, lead, worker):
    template = "{{{name}}} holds {tools}\n\nStart {roles}.\nWrite to {peers} on {channels}.\n {help} \nEnd: {ending}"

    text = preamble(kernel, worker[0], harness_name("coord"), template)

    lines = text.split("\n")
    assert lines[0].startswith("{w1} holds `mcp__coord__agent_finish`")
    assert lines[1:] == [
        "",
        "Write to @lead on notes (board), tasks (queue).",
        "End: When your goal is done, make `mcp__coord__agent_finish` your last call, with your report: a turn that "
        "only ends leaves you idle, and whoever waits on you still waiting.",
    ]


async def test_a_line_whose_slots_all_come_out_empty_is_left_out_words_and_all(kernel, server, lead):
    """A line with no slot is never dropped, and its words name a tool as the surface does. One with a slot that says
    something is kept whole."""
    narrow, _ = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])
    template = "Call `task.claim`, then `wait`.\nIn French: {peers} {channels}\nYou are {name}. {help}\n{ending}"

    text = preamble(kernel, narrow, harness_name("coord"), template)

    assert text == "Call `mcp__coord__task_claim`, then `mcp__coord__wait`.\nYou are n1. "


async def test_a_value_with_nothing_to_name_is_empty_so_a_line_around_it_goes(kernel, lead, monkeypatch):
    """`channels` with no channel in it holds no word of ours, so a template's own words around it go with it."""
    real = kernel.query

    def none(principal, op, args):
        empty = {"channels": [], "total": 0, "cursor": None}
        return Outcome(op=op, args_hash="", result=empty) if op == "channel.list" else real(principal, op, args)

    monkeypatch.setattr(kernel, "query", none)

    assert preamble(kernel, lead[0], tool_name, "You are {name}.\nPost to {channels}.") == "You are lead."


async def test_an_empty_template_tells_nothing_but_a_role_s_words(kernel, server, lead):
    narrow, _ = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])

    assert instructions(kernel, narrow, harness_name("coord"), "", None) is None
    assert instructions(kernel, narrow, harness_name("coord"), "", "Use `wait`.") == "Use `mcp__coord__wait`."


def test_a_slot_nobody_fills_is_refused_with_the_nearest():
    with pytest.raises(ValueError, match=r"no slot `\{tool\}`. Did you mean `tools`\?"):
        slots("{name} holds {tool}")
    with pytest.raises(ValueError, match="takes no"):
        slots("{tools!r}")
    with pytest.raises(ValueError, match="write a brace"):
        slots("a } alone")


def test_the_default_template_fills_every_slot():
    every = {"name", "tools", "help", "peers", "roles", "channels", "waiting", "citing", "ending"}
    assert set(slots(PREAMBLE)) == every


@pytest.mark.parametrize("name", TEAMS)
async def test_the_citing_sentence_is_said_to_every_agent_holding_a_citing_tool(name):
    """Asking to cite is on by default, for every preset's roles on each surface, and only an agent that holds a write
    of content, an op taking `based_on`, is asked."""
    team = TEAMS[name].resolved()
    capabilities = dict.fromkeys(team.roles, Capabilities(persistent=True))
    async with _rehearsed(team, capabilities) as kernel:
        agents = {role: agent async for role, agent in _one_of_each(kernel, team)}
        for agent in agents.values():
            cites = any(_cites(op) for op in _held(kernel, agent))
            for surface in SURFACES.values():
                assert (_CITING in preamble(kernel, agent, surface)) is cites


async def test_with_no_citing_slot_no_surface_text_asks_to_cite(kernel, server, lead):
    """A template without the slot turns asking off: no tool's description or argument asks, on any surface, and a
    citation is still taken."""
    template = PREAMBLE.replace("{citing}\n", "")

    for surface in SURFACES.values():
        told = preamble(kernel, lead[0], surface, template)
        texts = [told, *(text for tool in list_tools(kernel, lead[0], surface) for text in _described(tool))]
        assert _CITING not in told
        assert not [text for text in texts if re.search(r"(?i)\bcite\b|`ref` in", text)]
    assert "based_on" in {name for tool in list_tools(kernel, lead[0]) for name in tool["inputSchema"]["properties"]}


def _described(tool: dict) -> list[str]:
    """What a tool says of itself and of each of its arguments."""
    fields = tool["inputSchema"]["properties"].values()
    return [tool["description"], *(field["description"] for field in fields if "description" in field)]


async def test_a_role_s_words_come_last_naming_tools_as_the_surface_does(kernel, server, lead):
    narrow, _ = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])

    text = instructions(kernel, narrow, harness_name("coord"), PREAMBLE, "Use `task.claim`,\n  never `peers`.")

    told = preamble(kernel, narrow, harness_name("coord"))
    assert text == f"{told}\n\nUse `mcp__coord__task_claim`,\n  never `mcp__coord__peers`."
