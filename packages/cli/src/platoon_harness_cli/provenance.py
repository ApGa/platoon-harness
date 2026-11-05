"""How provenance reads, which the terminal and the browser say alike: one event's sources, its uses and the
contributors to it, each link labelled by how it is known, from the four queries alone, and what estimators said of
it, each by its producer and version. Every answer says the head it was read at, where it stops counting, whether its
turn was still open, and what its page left out."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from platoon_harness import Session
from platoon_harness.kernel import Event

Answer = Mapping[str, Any]
"""A query's answer, or an annotation, as JSON."""

_SCRIPT = "callId"
"""Codex's anchor, which names the Code Mode script that made a call, so what a call under it returned went to that
script, which may never have shown it to the model."""


@dataclass(frozen=True)
class Line:
    """One line of a provenance panel: a part's `heading`; a fact of an answer, which has no kind; a link of the kind
    it is known by, `declared`, `observed`, `cause`, `ancestry` or `gap`, or an `unresolved` citation; or what an
    estimator said, a `credit` or a `reward`. Its words; the ref following it opens, or None, where its words say why;
    and whether it says something is unknown, missing or cut, which a client draws as a warning."""

    kind: str
    text: str
    ref: str | None = None
    warn: bool = False


@dataclass(frozen=True)
class Panel:
    """What a provenance panel shows of one event: the event, as lineage names it, and its lines."""

    event: Answer
    lines: list[Line]


def shows(event: Event) -> str:
    """The ref a line made of `event` opens on: the event whose words a message carries, or its own."""
    carried = event.data.get("carries") if isinstance(event.data, dict) else None
    return carried or f"{event.stream}@{event.version}"


async def read(session: Session, ref: str) -> Panel:
    """What a panel shows of one event, asked of `session` now, each answer at a head of its own."""
    lineage = (await session.lineage(ref)).model_dump(mode="json")
    asked = lineage["event"]["ref"]
    uses, contributors = await session.uses(asked), await session.contributors(asked)
    said = [annotation.model_dump(mode="json") for annotation in await session.annotations(asked)]
    answers = (answer.model_dump(mode="json") for answer in (uses, contributors))
    return Panel(lineage["event"], lines_of(session.name, lineage, *answers, said))


def lines_of(
    session: str, lineage: Answer, uses: Answer, contributors: Answer, estimates: Sequence[Answer]
) -> list[Line]:
    """The lines of one event's panel: the event, then its sources, its uses, its contributors and what estimators
    said of it."""
    event = lineage["event"]
    asked = event["ref"]
    return [
        Line("", f"{event['type']} {asked}: {event['gist']}"),
        *_sources(session, lineage),
        *_uses(session, asked, uses),
        *_contributors(session, asked, contributors),
        *_estimates(estimates),
    ]


def _who(principal: str | None) -> str:
    """A principal as a person reads one, `@bob` or `@you`, or the runtime, or for a commit no one workspace of the
    session made, nobody the record names."""
    if principal is None:
        return "nobody the record names"
    return "the runtime" if principal == "runtime" else f"@{principal.partition(':')[2] or principal}"


def _some(count: int, what: str) -> str:
    return f"{count:,} {what}{'' if count == 1 else 's'}"


def _read_at(name: str, answer: Answer, counting: str) -> Line:
    """When an answer was read and what it counts, and whether a later report can still change it."""
    said = f"{name} read at head {answer['head']:,}{counting}"
    if answer["open"]:
        later = "its turn had not ended, so a later report can still confirm an offer or join a call"
        return Line("", f"{said}; {later}", warn=True)
    return Line("", said)


def _bound(bound: Answer) -> str:
    """Where lineage stops counting what an event's maker was handed over, in words."""
    if bound["by"] == "call":
        return f", counting what was handed over below the model call {bound['call']} that chose it"
    if bound["by"] == "look":
        return (
            f", counting what was handed over below the look that recorded it, at seq {bound['seq']:,}: git made the "
            "commit earlier, at a time the record does not hold"
        )
    return f", counting what was handed over below where the journal recorded it, at seq {bound['seq']:,}"


def _more(
    session: str, query: str, asked: str, shown: int, total: int | None, cursor: str | None, order: str
) -> list[Line]:
    """What a page left out, and the command that reads on from it."""
    if cursor is None:
        return []
    counted = f"{shown:,} of {total:,} shown" if total is not None else f"{shown:,} shown, and more"
    command = f"`platoon-harness {query} {session} --ref {asked} --after {cursor}`"
    return [Line("", f"{counted}, {order}: {command} reads on", warn=True)]


def _step(step: Answer) -> str:
    """An event an edge leads to, as a line names it."""
    sha = f", commit {step['sha'][:12]}" if step.get("sha") else ""
    return f"{step['ref']} {step['type']} by {_who(step['maker'])}{sha}: {step['gist']}"


def _offer(offer: Answer) -> str:
    """One offer: how it was made, what it showed, and whether its harness said it took it below the bound, with each
    compaction since."""
    shown = ", ".join(f"{item['ref']} {item['form']}" for item in offer["shown"])
    said = f"{offer['how']} {offer['ref']} showed {shown}"
    if (confirmed := offer["confirmed"]) is None:
        return f"{said}, and its harness had not said it took it below the bound"
    said += f", {_taken(confirmed, offer['anchor'])}"
    if marks := offer.get("compactions"):
        said += f", then {_some(offer['compacted'], 'compaction')}: {', '.join(mark['mark'] for mark in marks)}"
    return said


def _taken(confirmed: Answer, anchor: Answer | None) -> str:
    """How its harness said it took an offer: for a read, where its result returned, which is no model's reading."""
    if confirmed["evidence"] == "tool_item" and anchor is not None:
        script = anchor["key"] == _SCRIPT
        to = f"the Code Mode script that made call {anchor['id']}" if script else f"its harness, under {anchor['id']}"
        shared = f", which {anchor['ops']:,} of its agent's commands share" if anchor["ops"] > 1 else ""
        return f"its result returned to {to}{shared}"
    if confirmed["evidence"] is None:
        return "taken, as a report of its harness's says, naming no evidence"
    native = f" {confirmed['native_id']}" if confirmed["native_id"] else ""
    return f"taken, as its harness's {confirmed['evidence']} report{native} says"


def _exposure(exposure: Answer | None, citer: str | None) -> str:
    """What a citer had been handed of what it cites, as exposure says it, and never as a boolean."""
    if exposure is None and citer is None:
        return "its citer is nobody the record names, so no reading of it is evidence"
    if exposure is None:
        return "its citer is no agent, and a person's or a program's reading is no evidence"
    match exposure["answer"]:
        case "seen":
            more = exposure["total"] - len(exposure["edges"])
            return "seen: " + "; ".join(map(_offer, exposure["edges"])) + (f"; and {more:,} more" if more else "")
        case "not_seen":
            return (
                "not seen: nothing offered it below the bound, every surface of its harness is proved observed, and no "
                "gap below it could have let content through"
            )
    handed = exposure["totals"]["handed"]
    reasons = [
        f"handed {_some(handed, 'time')} and not said taken below the bound"
        if handed
        else "not handed over through us below the bound"
    ]
    if standing := exposure["standing"]:
        reasons.append(f"{_some(len(standing), 'surface')} of its harness no stored conformance result proves observed")
    if incidents := exposure["totals"]["incidents"]:
        reasons.append(f"{_some(incidents, 'gap')} content could have come through")
    if older := exposure["older_offers"]:
        reasons.append(f"{_some(older, 'offer')} from before offer payload 3, which no event can be tied to")
    return "unknown: " + "; ".join(reasons)


def _declared(declared: Answer, citer: str | None) -> Line:
    """A citation, with what its citer had been handed of it, and for a range whether those lines were shown. It opens
    the event it cites, as lines of a body have no provenance of their own."""
    exposure, ranged = declared["exposure"], "#" in declared["ref"]
    said = f"{declared['ref']} by {_who(declared['maker'])}: {declared['gist']}; {_exposure(exposure, citer)}"
    if ranged:
        shown = {True: "its lines were shown", False: "its lines were not shown"}
        said += f"; {shown.get(declared['lines_shown'], 'whether its lines were shown is unknown')}"
    unshown = exposure is None or exposure["answer"] != "seen" or (ranged and declared["lines_shown"] is not True)
    return Line("declared", said, declared["ref"].partition("#")[0], unshown)


def _made(event: Answer, made: Answer) -> list[Line]:
    """Who made an event and in which turn, and for an agent's the model call that chose it, or why none is joined: an
    agent's command is joined by the tool call it came under, and a harness's report of an item by its own ids."""
    driven = f", which {_who(made['by'])} drove holding it" if made["by"] else ""
    turn = f" in turn {made['turn']}{driven}" if made["turn"] else ""
    lines = [Line("", f"made by {_who(made['maker'])}{turn}")]
    if not (made["maker"] or "").startswith("agent:"):
        return lines
    if event["type"] == "item.recorded":
        return lines + _reported(made)
    if event["type"] == "repo.committed":
        return [*lines, Line("", "no model call is joined: a look found it in git, which names no tool call")]
    if not event["actor"].startswith("agent:"):
        return [*lines, Line("", "no model call is joined: the runtime recorded it, not a command of its agent's")]
    anchor, item, call = made["anchor"], made["item"], made["call"]
    if anchor is None:
        return [*lines, Line("", "no model call is joined: its command came with no tool call's id")]
    tool = f"{anchor['key']} {anchor['id']}" + (
        f", which {anchor['ops']:,} of its agent's commands share" if anchor["ops"] > 1 else ""
    )
    if item is None:
        return [*lines, Line("", f"no model call is joined: no tool item holds its tool call's id, {tool}", warn=True)]
    if call is None:
        return [*lines, Line("", f"no model call is joined: its tool item {item}, of {tool}, names none", item, True)]
    return [*lines, Line("", f"chosen by the model call {call}, through its tool item {item}, of {tool}", call)]


def _reported(made: Answer) -> list[Line]:
    """A harness's report of an item: the call it names, and for a tool item what each command of its agent's under
    its tool call's id made, which opens that command's own event."""
    call = made["call"]
    if call is None:
        lines = [Line("", "no model call is joined: its harness's reports of it name none", warn=True)]
    else:
        lines = [Line("", f"chosen by the model call {call}, which its harness's report of it names", call)]
    if (commands := made["commands"]) is None:
        return lines
    if not commands:
        said = "no command of its agent's is joined to it: none came under an id its harness gave this tool call"
        return [*lines, Line("", said, warn=True)]
    anchor = made["anchor"]
    lines += [Line("", f"under tool call {anchor['id']}, its agent's command made {ref}", ref) for ref in commands]
    if more := anchor["ops"] - len(commands):
        lines.append(Line("", f"and {_some(more, 'more command')} of its agent's under it", warn=True))
    return lines


def _unresolved(value: Answer, maker: str | None) -> Line:
    """An `Informed-By` value that cites nothing, and why, as the commit's record keeps it. One that names an event
    opens it."""
    named = value["written"].partition("#")[0]
    match value["why"]:
        case "unrecorded":
            said, ref = f"names commit {value['sha'][:12]}, which git holds and the journal held no record of", None
        case "no_event":
            said, ref = "names no commit git could resolve and no event of the session", None
        case "no_lines":
            said, ref = "names lines its event's body does not hold", named
        case "unread" if maker is None:
            said = "names an event, and nobody the record names made the commit, so nobody can be shown to have read it"
            ref = named
        case "unread":
            said, ref = f"names an event {_who(maker)} had neither made nor been handed when the look ran", named
        case _:
            said, ref = "was recorded before a commit could cite an event, by a look that sought commits alone", None
    return Line("unresolved", f"Informed-By {value['written']!r} cites nothing: it {said}", ref, warn=True)


def _sources(session: str, lineage: Answer) -> list[Line]:
    """One hop back: who made it, what it cites, what it follows from, what came before it, and what its maker was
    handed below the bound."""
    asked, made = lineage["event"]["ref"], lineage["made"]
    maker = _who(made["maker"])
    lines = [Line("heading", "Sources"), *_made(lineage["event"], made)]
    lines.append(_read_at("lineage", lineage, "" if lineage["totals"] is None else _bound(lineage["bound"])))
    lines += [_declared(declared, made["maker"]) for declared in lineage["declared"]]
    lines += [_unresolved(value, made["maker"]) for value in lineage["unresolved"]]
    if lineage["cut"]:
        lines.append(Line("", f"{_some(lineage['cut'], 'more Informed-By value')} not kept", warn=True))
    lines += [Line("cause", _step(step), step["ref"]) for step in lineage["cause"]]
    for step in lineage["ancestry"]:
        if step["ref"] is None:
            said = f"commit {step['sha'][:12]}, which git holds and the journal has no record of"
            lines.append(Line("ancestry", said))
        else:
            lines.append(Line("ancestry", _step(step), step["ref"]))
    if (totals := lineage["totals"]) is not None:
        said = (
            f"{maker} was handed {_some(totals['handed'], 'offer')} below the bound, {totals['confirmed']:,} said "
            f"taken there and {totals['unconfirmed']:,} not, with {_some(totals['gaps'], 'gap')} in its record"
        )
        lines.append(Line("", said, warn=bool(totals["unconfirmed"] or totals["gaps"])))
        for row in lineage["history"]:
            if row["kind"] == "gap":
                through = ", which content could have come through unseen" if row["carries"] else ""
                said = f"{row['ref']} {row['what']} on the {row['plane']} plane, from seq {row['began']:,}{through}"
                lines.append(Line("gap", said, row["ref"], row["carries"]))
            else:
                lines.append(Line("observed", _offer(row), row["ref"], row["confirmed"] is None))
        total = totals["handed"] + totals["gaps"]
        lines += _more(session, "lineage", asked, len(lineage["history"]), total, lineage["cursor"], "newest first")
    return lines


def _uses(session: str, asked: str, uses: Answer) -> list[Line]:
    """One hop forward: what cites it, what follows from it, what came after it, and whom it was handed to."""
    totals = uses["totals"]
    counting = (
        f": {totals['declared']:,} citing it, {totals['cause']:,} following from it, {totals['ancestry']:,} after "
        f"it, and handed to {_some(totals['observed'], 'agent')}"
    )
    lines = [Line("heading", "Uses"), _read_at("uses", uses, counting)]
    for row in uses["rows"]:
        if row["kind"] != "observed":
            lines.append(Line(row["kind"], _step(row), row["ref"]))
            continue
        taken = "said it took an offer of it" if row["confirmed"] else "has not said it took any offer of it"
        said = f"@{row['agent']}, first by {row['offer']}, and its harness {taken}"
        lines.append(Line("observed", said, row["offer"], not row["confirmed"]))
    total = sum(totals.values())
    return lines + _more(session, "uses", asked, len(uses["rows"]), total, uses["cursor"], "oldest first")


def _contributors(session: str, asked: str, contributors: Answer) -> list[Line]:
    """Each maker a walk back along citations, causes and ancestry reaches, and apart from them each maker whose work
    was only handed to one of them. Nobody is weighed or ranked."""
    walked = (
        f", walking back along citations, causes and ancestry over {_some(contributors['walked'], 'event')}, and "
        "weighing and ranking nobody"
    )
    lines = [Line("heading", "Contributors"), _read_at("contributors", contributors, walked)]
    if contributors["stopped_short"]:
        lines.append(Line("", "the walk stopped at its limit, so more may lie beyond what it reached", warn=True))
    for row in contributors["rows"]:
        kinds = ", ".join(row["kinds"])
        how = kinds if row["hops"] else "made it" + (f", and reached by {kinds}" if kinds else "")
        said = f"{_who(row['maker'])}: {how}, {_some(row['reached'], 'event')}, the first {row['first']}"
        said += f", {_some(row['hops'], 'hop')} back"
        if row["unproved"]:
            said += f"; {_some(len(row['unproved']), 'surface')} of its harness unproved"
        if row["incidents"]:
            said += "; gaps " + ", ".join(f"{what} {count:,}" for what, count in sorted(row["incidents"].items()))
        lines.append(Line("", said, row["first"], bool(row["incidents"])))
    shown = len(contributors["rows"])
    lines += _more(session, "contributors", asked, shown, None, contributors["cursor"], "in the order reached")
    for row in contributors["handed_only"]:
        said = f"{_who(row['maker'])}: only handed to {', '.join(map(_who, row['to']))}, first by {row['first']}"
        lines.append(Line("observed", said, row["first"]))
    return lines


def _estimates(estimates: Sequence[Answer]) -> list[Line]:
    """What estimators said of the event, each its producer's at its version and params, never a fact, and never
    summed."""
    lines = [
        Line("heading", "Credit and rewards"),
        Line("", "what estimators said of it, beside the record: each an estimate by its producer at its version"),
    ]
    for said in estimates:
        by = f"by {said['producer']}, version {said['producer_version']}, params {said['params_hash'][:8]}"
        value = f"{said['value']:g} {by}" if said["status"] == "scored" else f"no value, {said['status']}, {by}"
        lines.append(Line(said["kind"], f"{value}, {said['scope']}, of the trace at head {said['head_seq']:,}"))
    if not estimates:
        lines.append(Line("", "no estimator has said anything of it"))
    return lines
