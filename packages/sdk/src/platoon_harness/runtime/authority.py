"""Who admits an agent: the session itself, or in managed mode a training system's authority."""

import os
import secrets
from collections.abc import Mapping
from typing import Protocol, Self, runtime_checkable

from pydantic import model_validator

from platoon_harness.config import Secret, credentials, forms
from platoon_harness.drivers import Access, Gateway
from platoon_harness.primitives.lifecycle import Status
from platoon_harness.schema import Model
from platoon_harness.team import Team

__all__ = ["Admission", "AgentOutcome", "AgentRef", "Authority", "Gateway", "LocalAuthority", "SpawnRequest"]


class AgentRef(Model):
    """An agent by name and role."""

    agent: str
    role: str


class SpawnRequest(AgentRef):
    """An agent to admit. `parent` is the principal that spawned it, as its `agent.spawned` records it, and None for one
    the session started, and `goal` is what it was given to do. `resumed` says it was admitted once, and a restart needs
    its access again."""

    parent: str | None = None
    goal: str = ""
    resumed: bool = False


class Admission(Model):
    """What admission gives an agent: its token on the tool plane, which stays in memory, and its model access, as
    variables by name or as a gateway. `backend` is the backend's ids for this agent, which its admit records: each
    entry is this agent's alone, so one another admission of the session shares bars both from training, no key or
    value holds a secret of its own in any form, and a gateway admission names them, as nothing else ties the agent to
    what its gateway records of it."""

    token: Secret
    access: Access = {}
    backend: Mapping[str, str] = {}

    @model_validator(mode="after")
    def _named(self) -> Self:
        held = {self.token, *((self.access.bearer,) if isinstance(self.access, Gateway) else self.access.values())}
        found = {form for secret in held if secret.reveal() for form in forms(secret)}
        if any(form in text.encode() for text in (*self.backend, *self.backend.values()) for form in found):
            raise ValueError("a backend id names an agent, never a key")
        if isinstance(self.access, Gateway) and not self.backend:
            raise ValueError("a gateway admission names the backend's ids for its agent")
        return self


class AgentOutcome(Model):
    """How an agent ended: its `status`, and its `report`, the words its end keeps, or None when it said nothing: the
    gist, which is the agent's own for a finish and the session's for any other end, and then the body, its last
    words, unless a person redacted them."""

    status: Status
    report: str | None = None


@runtime_checkable
class Authority(Protocol):
    """What a kernel with no training branch asks of whoever owns identity and model access. A managed authority's
    refusal wins: `admit` raises, and the spawn fails."""

    async def admit(self, spawn: SpawnRequest) -> Admission: ...

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None: ...


class LocalAuthority:
    """Issues session-scoped identity and leaves the harness's own auth alone: model access is what a role's auth
    profile names, and with none the harness signs itself in."""

    def __init__(self, team: Team, environ: Mapping[str, str] = os.environ) -> None:
        self._team = team
        self._environ = environ

    async def admit(self, spawn: SpawnRequest) -> Admission:
        access = credentials(self._team, spawn.role, self._environ)
        return Admission(token=Secret(secrets.token_urlsafe(32)), access=access)

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        return None
