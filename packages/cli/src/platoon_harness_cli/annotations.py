"""`annotate` and `annotations`: what an estimator says of a session's record, written and read beside its journal as
`Session.annotate` and `Session.annotations` do, the first made from the schema those check."""

from collections.abc import Mapping
from typing import Any

from platoon_harness import Session
from platoon_harness.annotations import Annotate

from .ops import derived
from .output import say, shown


async def _annotate(attached: Session, args: dict[str, Any], given: Mapping[str, Any]) -> int:
    target = args.pop("target")
    say(shown((await attached.annotate(target, **args)).model_dump(mode="json")))
    return 0


annotate = derived("annotate", Annotate, Session.annotate.__doc__ or "", _annotate, reads=False)


async def annotations(session: str, /, *, target: str | None = None) -> int:
    """List what estimators said of one event, or of every one, oldest first, each with its producer and version and
    never summed. Nothing an agent can reach reads these.

    For example:

        platoon-harness annotations fix-auth --target agent/lead@1

    Parameters
    ----------
    session
        A session, by name. `platoon-harness session list` shows them.
    target
        The event they are about, by its ref, `stream@version`.
    """
    async with Session.attach(session, view=True) as attached:
        found = await attached.annotations(target)
    say(shown([annotation.model_dump(mode="json") for annotation in found]))
    return 0
