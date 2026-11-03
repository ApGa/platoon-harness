"""Operations: named, typed, synchronous functions, the only way to change a session."""

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict

from .txn import Txn

_IDENTITY_FIELDS = frozenset(
    {
        "actor",
        "agentid",
        "apikey",
        "apitoken",
        "authorization",
        "bearer",
        "caller",
        "callerrole",
        "credential",
        "identity",
        "onbehalfof",
        "policy",
        "principal",
        "role",
        "session",
        "token",
        "user",
    }
)


class Args(BaseModel):
    """An op's arguments. Undeclared fields are refused, and no type is coerced."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _session(args: Args) -> str | None:
    return "session"


def _claims(input: type[Args]) -> list[str]:
    """Fields that claim the caller's identity, nested ones and aliases too. A denylist, so it catches the usual
    spellings and no more: what stops a spoof is that identity comes from a credential."""
    schema = input.model_json_schema()
    names = {*input.model_fields}
    for table in (schema, *schema.get("$defs", {}).values()):
        names |= table.get("properties", {}).keys()

    def claims(name: str) -> bool:
        plain = re.sub(r"[\W_]", "", name).casefold()
        return plain in _IDENTITY_FIELDS or plain.removesuffix("id") in _IDENTITY_FIELDS

    return sorted(filter(claims, names))


@dataclass(frozen=True)
class Op:
    """An op definition. `on` names the object of one invocation, or None for an op that checks its objects itself.

    `query` keeps an op out of history. `exposes` marks a read that is a command for agents and a query for everyone
    else. An op is at most one of the two. `runtime` and `agent` keep an op to principals of that kind.
    """

    name: str
    fn: Callable[[Txn, Any], Any]
    input: type[Args]
    on: Callable[[Any], str | None] = _session
    query: bool = False
    exposes: bool = False
    tool: bool = False
    runtime: bool = False
    agent: bool = False


def op(
    name: str,
    *,
    on: Callable[[Any], str | None] = _session,
    query: bool = False,
    exposes: bool = False,
    tool: bool = False,
    runtime: bool = False,
    agent: bool = False,
) -> Callable[[Callable[..., Any]], Op]:
    """Define an op from `def fn(txn: Txn, a: SomeArgs)`. `runtime` puts it out of reach of every grant, and `agent`
    out of reach of everyone but an agent."""

    def define(fn: Callable[..., Any]) -> Op:
        if inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn) or inspect.isgeneratorfunction(fn):
            raise TypeError(f"op {name} must be a plain function: operations cannot wait on the world")
        _, parameter = inspect.signature(fn).parameters
        input = get_type_hints(fn).get(parameter)
        if not (isinstance(input, type) and issubclass(input, Args)) or input.model_config.get("extra") != "forbid":
            raise TypeError(f"op {name} must take Args that refuse undeclared fields")
        if query and exposes:
            raise TypeError(f"op {name} cannot be both a query and an exposed read")
        if runtime and agent:
            raise TypeError(f"op {name} cannot be kept to both the runtime and agents")
        if tool and (claims := _claims(input)):
            raise TypeError(f"tool op {name} declares identity fields: {claims}")
        if tool and not fn.__doc__:
            raise TypeError(f"tool op {name} needs a description")
        return Op(name, fn, input, on, query, exposes, tool, runtime, agent)

    return define
