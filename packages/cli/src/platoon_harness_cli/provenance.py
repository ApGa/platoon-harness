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
    return f", counting what was handed over below its commit, at seq {bound['seq']:,}"


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
    """One offer: how it was made, what it showed, and whether its harness said it took it, with each compaction
    since."""
    shown = ", ".join(f"{item['ref']} {item['form']}" for item in offer["shown"])
    said = f"{offer['how']} {offer['ref']} showed {shown}"
    if (confirmed := offer["confirmed"]) is None:
        return f"{said}, and its harness never said it took it"
    native = f" {confirmed['native_id']}" if confirmed["native_id"] else ""
    said += f", taken by {confirmed['evidence']}{native}"
    if marks := offer.get("compactions"):
        said += f", then {_some(offer['compacted'], 'compaction')}: {', '.join(mark['mark'] for mark in marks)}"
    return said


def _exposure(exposure: Answer | None) -> str:
    """What a citer had been handed of what it cites, as exposure says it, and never as a boolean."""
    if exposure is None:
        return "its citer is no agent, and a person's or a program's reading is no evidence"
    match exposure["answer"]:
        case "seen":
            more = exposure["total"] - len(exposure["edges"])
            return "seen: " + "; ".join(map(_offer, exposure["edges"])) + (f"; and {more:,} more" if more else "")
        case "not_seen":
            return (
                "not seen: nothing offered it below the bound, every surface of its harness is proved observed, and no "
                "gap content could come through lies below it"
            )
    handed = exposure["totals"]["handed"]
    reasons = [f"handed {_some(handed, 'time')}, never said taken" if handed else "never handed over through us"]
    if standing := exposure["standing"]:
        reasons.append(f"{_some(len(standing), 'surface')} of its harness no stored conformance result proves observed")
    if incidents := exposure["totals"]["incidents"]:
        reasons.append(f"{_some(incidents, 'gap')} content could have come through")
    if older := exposure["older_offers"]:
        reasons.append(f"{_some(older, 'offer')} from before offer payload 3, which no event can be tied to")
    return "unknown: " + "; ".join(reasons)


def _declared(declared: Answer) -> Line:
    """A citation, with what its citer had been handed of it, and for a range whether those lines were shown. It opens
    the event it cites, as lines of a body have no provenance of their own."""
    exposure, ranged = declared["exposure"], "#" in declared["ref"]
    said = f"{declared['ref']} by {_who(declared['maker'])}: {declared['gist']}; {_exposure(exposure)}"
    if ranged:
        shown = {True: "its lines were shown", False: "its lines were not shown"}
        said += f"; {shown.get(declared['lines_shown'], 'whether its lines were shown is unknown')}"
    unshown = exposure is None or exposure["answer"] != "seen" or (ranged and declared["lines_shown"] is not True)
    return Line("declared", said, declared["ref"].partition("#")[0], unshown)


def _made(made: Answer) -> list[Line]:
    """Who made an event and in which turn, and for an agent's the model call that chose it, or why none is joined."""
    driven = f", which {_who(made['by'])} drove holding it" if made["by"] else ""
    turn = f" in turn {made['turn']}{driven}" if made["turn"] else ""
    lines = [Line("", f"made by {_who(made['maker'])}{turn}")]
    if not (made["maker"] or "").startswith("agent:"):
        return lines
    anchor, item, call = made["anchor"], made["item"], made["call"]
    if anchor is None:
        return [*lines, Line("", "no model call is joined: no tool call's id came with it")]
    tool = f"{anchor['key']} {anchor['id']}" + (
        f", which {anchor['ops']:,} of its agent's commands share" if anchor["ops"] > 1 else ""
    )
    if item is None:
        return [*lines, Line("", f"no model call is joined: no tool item holds its tool call's id, {tool}", warn=True)]
    if call is None:
        return [*lines, Line("", f"no model call is joined: its tool item {item}, of {tool}, names none", item, True)]
    return [*lines, Line("", f"chosen by the model call {call}, through its tool item {item}, of {tool}", call)]


def _sources(session: str, lineage: Answer) -> list[Line]:
    """One hop back: who made it, what it cites, what it follows from, what came before it, and what its maker was
    handed below the bound."""
    asked, maker = lineage["event"]["ref"], _who(lineage["made"]["maker"])
    lines = [Line("heading", "Sources"), *_made(lineage["made"])]
    lines.append(_read_at("lineage", lineage, "" if lineage["totals"] is None else _bound(lineage["bound"])))
    lines += [_declared(declared) for declared in lineage["declared"]]
    for value in lineage["unresolved"]:
        resolved = f", which git resolved to {value['sha'][:12]}," if value["sha"] else ""
        said = f"Informed-By {value['written']!r}{resolved} names no recorded commit and no event of the session"
        lines.append(Line("unresolved", said, warn=True))
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
            f"taken and {totals['unconfirmed']:,} never, with {_some(totals['gaps'], 'gap')} in its record"
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
        taken = "its harness said it took it" if row["confirmed"] else "its harness never said it took it"
        said = f"@{row['agent']} by {row['offer']}, and {taken}"
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
        how = ", ".join(row["kinds"]) or "made it"
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
    """What estimators said of the event, each its producer's at its version, never a fact, and never summed."""
    lines = [
        Line("heading", "Credit and rewards"),
        Line("", "what estimators said of it, beside the record: each an estimate by its producer at its version"),
    ]
    for said in estimates:
        by = f"by {said['producer']} {said['producer_version']}"
        value = f"{said['value']:g} {by}" if said["status"] == "scored" else f"no value, {said['status']}, {by}"
        lines.append(Line(said["kind"], f"{value}, {said['scope']}, of the trace at head {said['head_seq']:,}"))
    if not estimates:
        lines.append(Line("", "no estimator has said anything of it"))
    return lines
