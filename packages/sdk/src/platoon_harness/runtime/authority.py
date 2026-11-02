"""Who admits an agent: the session itself, or in managed mode an authority such as Platoon's."""

import os
import secrets
from collections.abc import Mapping
from typing import Literal, Protocol, runtime_checkable

from platoon_harness.config import Secret, credentials
from platoon_harness.schema import Model
from platoon_harness.team import Team

__all__ = ["Admission", "AgentOutcome", "AgentRef", "Authority", "LocalAuthority", "SpawnRequest"]


class AgentRef(Model):
    """An agent by name and role."""

    agent: str
    role: str


class SpawnRequest(AgentRef):
    """An agent to admit. `resumed` says it was admitted once, and a restart needs its access again."""

    resumed: bool = False


class Admission(Model):
    """What admission gives an agent: its token on the tool plane, which stays in memory, and its model access."""

    token: Secret
    access: Mapping[str, Secret] = {}


class AgentOutcome(Model):
    """How an agent ended."""

    status: str | None


@runtime_checkable
class Authority(Protocol):
    """What a kernel with no Platoon branch asks of whoever owns identity, model routing and budgets. A managed
    authority's refusal wins: `admit` raises, and the spawn fails."""

    async def admit(self, spawn: SpawnRequest) -> Admission: ...

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None: ...

    def budget_owner(self, resource: str) -> Literal["session", "authority"]: ...


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

    def budget_owner(self, resource: str) -> Literal["session", "authority"]:
        return "session"
