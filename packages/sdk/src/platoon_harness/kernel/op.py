"""Operations: named, typed, synchronous functions, the only way to change a session."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict

from .txn import Txn

_IDENTITY_FIELDS = frozenset(
    {"actor", "caller", "credential", "identity", "policy", "principal", "session", "session_id", "token"}
)


class Args(BaseModel):
    """An op's arguments. Unknown fields are refused, and no field may claim who is calling."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        claims = _IDENTITY_FIELDS & set(cls.model_fields)
        if claims:
            raise TypeError(f"{cls.__name__} declares identity fields: {sorted(claims)}")


@dataclass(frozen=True)
class Op:
    """An op definition. `exposes` marks a read that is a command for agents and a query for everyone else."""

    name: str
    fn: Callable[[Txn, Any], Any]
    input: type[Args]
    on: Callable[[Any], str] | None = None
    query: bool = False
    exposes: bool = False
    tool: bool = False
    runtime: bool = False

    def target(self, args: Args) -> str:
        """The object stream this invocation is about."""
        return "session" if self.on is None else self.on(args)


def op(
    name: str,
    *,
    on: Callable[[Any], str] | None = None,
    query: bool = False,
    exposes: bool = False,
    tool: bool = False,
    runtime: bool = False,
) -> Callable[[Callable[..., Any]], Op]:
    """Define an op from `def fn(txn: Txn, a: SomeArgs)`. `runtime` puts it out of reach of every grant."""

    def define(fn: Callable[..., Any]) -> Op:
        if inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn) or inspect.isgeneratorfunction(fn):
            raise TypeError(f"op {name} must be a plain function: operations cannot wait on the world")
        _, parameter = inspect.signature(fn).parameters
        return Op(name, fn, get_type_hints(fn)[parameter], on, query, exposes, tool, runtime)

    return define
