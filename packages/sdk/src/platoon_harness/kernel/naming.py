"""The naming law, as far as a machine can check it."""

from functools import lru_cache

from .model import Refused

# Words that read as past tense without ending in -ed.
# fmt: off
_PAST_FORMS = frozenset({
    "begun", "built", "chosen", "cut", "done", "drawn", "found", "given", "held", "kept", "left", "lost", "made", "met",
    "paid", "put", "read", "run", "seen", "sent", "set", "shown", "spent", "split", "taken", "told", "woken", "won",
    "written",
})
# fmt: on
_SAME_IN_THE_IMPERATIVE = frozenset({"cut", "put", "read", "run", "set", "split"})
_VERBS_ENDING_IN_ED = frozenset({"embed", "exceed", "feed", "need", "proceed", "seed", "shed", "succeed"})


def _past_tense(word: str) -> bool:
    return word in _PAST_FORMS or (word.endswith("ed") and word not in _VERBS_ENDING_IN_ED)


def check_op_name(name: str, extension: str) -> None:
    """Refuse an op outside its extension's namespace, or named in the past tense."""
    namespace, _, verb = name.partition(".")
    if namespace != extension:
        raise Refused("invalid", f"op {name} is outside namespace {extension}")
    word = verb.rpartition(".")[2] or namespace
    if _past_tense(word) and word not in _SAME_IN_THE_IMPERATIVE:
        raise Refused("invalid", f"op {name} must be imperative")


@lru_cache(maxsize=4096)
def check_event_type(event_type: str) -> None:
    """Refuse an event type that is not `<namespace>.<past tense>`. `effect.uncertain` names a state."""
    namespace, _, word = event_type.rpartition(".")
    if event_type != "effect.uncertain" and (not namespace or not _past_tense(word)):
        raise Refused("invalid", f"event {event_type} must be past tense under a namespace")
