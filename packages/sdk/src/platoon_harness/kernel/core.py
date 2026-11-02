"""The kernel's own extensions, on the same contract a third party uses."""

from typing import Any

from .auth import Grants, Principals, add_grant, add_principal, issue_credential, remove_grant, revoke_principal
from .bodies import Tombstones, eraser_daemon, tombstone_body
from .effects import (
    Effects,
    expire_effect,
    fail_effect,
    finish_effect,
    list_effects,
    ready_effects,
    start_effect,
    start_runtime,
)
from .extension import Extension
from .model import Refused
from .op import Args, Op, op
from .timers import Timers, clear_timer, clock_daemon, next_timers
from .txn import Stamps, Txn

CORE = (
    Extension("op", views=[Stamps]),
    Extension("principal", ops=[add_principal, issue_credential, revoke_principal], views=[Principals]),
    Extension("grant", ops=[add_grant, remove_grant], views=[Grants]),
    Extension(
        "effect",
        ops=[ready_effects, list_effects, start_effect, finish_effect, fail_effect, expire_effect],
        views=[Effects],
    ),
    Extension("runtime", ops=[start_runtime]),
    Extension("timer", ops=[next_timers, clear_timer], views=[Timers], daemons=[clock_daemon]),
    Extension("body", ops=[tombstone_body], views=[Tombstones], daemons=[eraser_daemon]),
)


def list_ops(ops: dict[str, Op]) -> Op:
    """Define `ops.list`, which every surface derives from, over a table filled once everything has loaded."""

    def permitted(txn: Txn, operation: Op) -> bool:
        try:
            txn.view(Grants).authorize(txn.me, operation)
        except Refused:
            return False
        return True

    @op("ops.list", query=True)
    def list_permitted(txn: Txn, a: Args) -> list[dict[str, Any]]:
        """List the ops this caller holds a grant for, with their schemas."""
        return [
            {
                "name": operation.name,
                "description": operation.fn.__doc__,
                "schema": operation.input.model_json_schema(),
                "tool": operation.tool,
                "query": operation.query,
                "exposes": operation.exposes,
            }
            for operation in ops.values()
            if permitted(txn, operation)
        ]

    return list_permitted
