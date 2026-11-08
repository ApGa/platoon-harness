"""Labels: a team's vocabulary for its work, each label a name with the values it may take, given to a task as it is
added and to an agent as it is spawned, checked against that vocabulary, recorded on the event, and shown to a model in
each tool that takes them, as architecture section 7 says."""

from typing import Any

import pytest

from platoon_harness import ConfigError, Team
from platoon_harness.kernel import Kernel
from platoon_harness.tools import list_tools

from .support import agent, channel, of_type, refusal, result_of, spawn

VOCABULARY = {"difficulty": ["easy", "medium", "hard"], "kind": ["design", "execution", "search", "verification"]}


@pytest.fixture
def labels() -> dict[str, list[str]]:
    return VOCABULARY


def team(labels: str) -> Team:
    return Team.loads(f'[roles.lead]\nharness = "claude"\n\n[labels]\n{labels}\n')


async def adding(kernel: Kernel, labels: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """A task added to `tasks` and an agent spawned, each by `lead`, with `labels`: the op and its arguments."""
    await channel(kernel, "tasks", kind="queue")
    task = {"queue": "tasks", "gist": "find the recipe", "labels": labels}
    return [("task.add", task), ("agent.spawn", {"name": "w", "child_role": "worker", "labels": labels})]


# The vocabulary.


def test_a_team_declares_each_label_with_the_values_it_may_take_in_its_order():
    declared = team('kind = ["search", "design"]\ndifficulty = ["easy", "hard"]')

    assert declared.labels == {"difficulty": ("easy", "hard"), "kind": ("search", "design")}
    assert Team.loads(declared.show(resolved=True)).labels == declared.labels


@pytest.mark.parametrize(
    ("values", "why"),
    [
        ("[]", "labels.kind: Tuple should have at least 1 item"),
        ('["search", "design", "search"]', "a label takes each value once, and search is given twice"),
        ('["no..dots"]', "labels.kind.0: String should match pattern"),
    ],
    ids=["no value", "a value twice", "no name"],
)
def test_a_label_with_no_value_a_value_given_twice_or_a_value_that_is_no_name_is_refused(values, why):
    with pytest.raises(ConfigError) as refused:
        team(f"kind = {values}")

    assert why in str(refused.value)


# Given, checked and recorded.


async def test_a_task_and_an_agent_record_the_labels_they_were_given(kernel):
    lead = await spawn(kernel, "lead", role="lead")

    for op, args in await adding(kernel, {"kind": "search", "difficulty": "hard"}):
        result_of(await kernel.submit(lead, op, args))

    added, spawned = of_type(kernel, "task.added")[-1], of_type(kernel, "agent.spawned")[-1]
    assert (added.v, added.data["labels"]) == (2, {"difficulty": "hard", "kind": "search"})
    assert (spawned.v, spawned.data["labels"]) == (4, {"difficulty": "hard", "kind": "search"})


async def test_labels_are_optional_and_work_given_none_records_none(kernel):
    lead = await spawn(kernel, "lead", role="lead")

    for op, args in await adding(kernel, {"kind": "search"}):
        result_of(await kernel.submit(lead, op, args))
    result_of(await kernel.submit(lead, "task.add", {"queue": "tasks", "gist": "and this"}))

    assert [event.data["labels"] for event in of_type(kernel, "task.added")] == [{"kind": "search"}, {}]


@pytest.mark.parametrize(
    ("given", "why"),
    [
        ({"size": "big"}, "this team has no label size: its labels are difficulty, kind"),
        ({"kind": "search", "difficulty": "trivial"}, "difficulty takes easy, medium or hard, and not trivial"),
    ],
    ids=["no such label", "no such value"],
)
async def test_a_label_outside_the_team_s_is_refused_saying_what_may_be_given(kernel, given, why):
    lead = await spawn(kernel, "lead", role="lead")

    for op, args in await adding(kernel, given):
        found = refusal(await kernel.submit(lead, op, args))
        assert (found.code, found.detail) == ("invalid", why)

    assert not of_type(kernel, "task.added") and [event.data["name"] for event in of_type(kernel, "agent.spawned")] == [
        "lead"
    ]


@pytest.mark.parametrize("labels", [{}])
async def test_any_label_is_refused_where_the_team_declares_none(kernel):
    lead = await spawn(kernel, "lead", role="lead")

    for op, args in await adding(kernel, {"kind": "search"}):
        found = refusal(await kernel.submit(lead, op, args))
        assert (found.code, found.detail) == ("invalid", "this team has no label kind: it declares none")


async def test_no_reader_is_shown_a_task_s_labels(kernel):
    """Labels are for the record and a training system: a claimant is shown a task as it was before them."""
    lead = await spawn(kernel, "lead", role="lead")
    worker = await spawn(kernel, "w")
    [(op, args), _] = await adding(kernel, {"kind": "search"})
    result_of(await kernel.submit(lead, op, args))

    claimed = result_of(await kernel.submit(worker, "task.claim", {"queue": "tasks"}))
    listed = result_of(await kernel.submit(worker, "task.list", {"queue": "tasks"}))

    assert "labels" not in claimed and "labels" not in listed["tasks"][0]
    assert "search" not in str(claimed) + str(listed)


# Shown to a model.


async def test_a_tool_that_takes_labels_shows_each_with_the_values_it_may_take(kernel):
    await spawn(kernel, "w")

    tools = {tool["title"]: tool["inputSchema"] for tool in list_tools(kernel, agent("w"))}

    enums = {label: {"type": "string", "enum": values} for label, values in VOCABULARY.items()}
    for name in ("task.add", "agent.spawn"):
        shown = tools[name]["properties"]["labels"]
        assert shown["properties"] == enums
        assert shown["type"] == "object" and shown["additionalProperties"] is False
        assert shown["description"] == (
            "What kind of work this is, by your team's labels, each with one of its values. Its labels: difficulty, "
            "one of easy, medium or hard; kind, one of design, execution, search or verification."
        )
        assert "labels" not in tools[name].get("required", ())


@pytest.mark.parametrize("labels", [{}])
async def test_a_tool_shows_no_labels_where_the_team_declares_none(kernel):
    await spawn(kernel, "w")

    tools = {tool["title"]: tool["inputSchema"] for tool in list_tools(kernel, agent("w"))}

    assert not [name for name, schema in tools.items() if "labels" in schema["properties"]]
