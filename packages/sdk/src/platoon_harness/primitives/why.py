"""Why an agent is where it is, typed, so no client has to guess from a string."""

from typing import Literal

from pydantic import BaseModel


class Approval(BaseModel, frozen=True):
    kind: Literal["approval"] = "approval"
    id: str


class Wait(BaseModel, frozen=True):
    kind: Literal["wait"] = "wait"
    have: int
    need: int
    missing: tuple[str, ...]


class Budget(BaseModel, frozen=True):
    kind: Literal["budget"] = "budget"
    code: str


class Lease(BaseModel, frozen=True):
    kind: Literal["lease"] = "lease"
    id: str


class Peer(BaseModel, frozen=True):
    kind: Literal["peer"] = "peer"
    id: str


class Timer(BaseModel, frozen=True):
    kind: Literal["timer"] = "timer"
    at: float


class Infra(BaseModel, frozen=True):
    kind: Literal["infra"] = "infra"
    detail: str


class Lost(BaseModel, frozen=True):
    kind: Literal["lost"] = "lost"
    reason: str


Why = Approval | Wait | Budget | Lease | Peer | Timer | Infra | Lost
