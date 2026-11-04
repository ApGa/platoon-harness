"""How a roster row reads, which the terminal and the browser say alike, from what the view says and nothing else."""

from typing import Any

GROUPS = {
    "needs_you": "needs you",
    "working": "working",
    "blocked": "blocked",
    "idle": "idle",
    "done": "done",
    "failed": "failed",
}
"""Each of the roster's groups as a person says it."""


def why_said(why: dict[str, Any] | None) -> str:
    """What an agent waits on, in words, from the roster's typed `why`."""
    if why is None:
        return ""
    match why["kind"]:
        case "approval":
            return "asks you to approve"
        case "wait":
            missing = ", ".join(why["missing"][:3]) + ("…" if len(why["missing"]) > 3 else "")
            return f"waits {why['have']} of {why['need']}" + (f", for {missing}" if missing else "")
        case "peer":
            return f"waits on @{why['id']}"
        case "budget":
            return f"held by the budget: {why['code']}"
        case "lease":
            return f"holds {why['id']}"
        case "timer":
            return "a wake is due"
        case "infra":
            return why["detail"]
        case "lost":
            return f"lost: {why['reason']}"
    return why["kind"]


def detail_of(row: dict[str, Any]) -> str:
    """What a row says beside its group: what it waits on while it is held up, and what it is doing otherwise."""
    return why_said(row["why"]) if row["group"] in ("blocked", "needs_you", "failed") else row["activity"] or ""


def status_of(row: dict[str, Any]) -> str:
    """A row as one short status: its group, then its detail."""
    detail = " ".join(detail_of(row).split())
    return f"{GROUPS[row['group']]}: {detail}" if detail else GROUPS[row["group"]]
