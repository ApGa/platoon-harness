# Python API reference

<!-- Made from `tests/public_api.txt` and the docstrings by
`uv run python -m platoon_harness_cli.reference python > docs/reference/python.md`. Do not edit: change the code or the
list, and make it again. A test holds it to them. -->

Every name `tests/public_api.txt` lists, under the module whose `__all__` holds it: the SDK's, `platoon_harness` and
the modules beneath it, and the ACP extension's, `platoon_harness_acp`.

By default, pending the owner's ruling, the public API is each name `tests/public_api.txt` lists, and each attribute and
method without a leading underscore that a class it lists defines, of which the list records only some, and nothing
else is, whatever its spelling. 0.1.0 promises it under the policy below 1.0 that [CHANGELOG](../../CHANGELOG.md)
states, so a minor release may change any of it and a patch release only fixes bugs, and there is no experimental
namespace.

Each name is shown as a stub declares it, in its source's own words without comments, then its docstring: a function by
its signature, a class by its attributes whose names have no leading underscore and its `__init__`, then each method of
its own whose name has no leading underscore, and anything else by its assignment. A name that a module imports from
another that lists it links there.

A module or name marked **Experimental** is one that a row of [STATUS](../STATUS.md) calls experimental, by its state,
which says it works but rests on an unstable upstream surface or lacks coverage, or in its own words, whatever its
state. The mark quotes the start of the row, so it says which.

## Contents

- [`platoon_harness`](#platoon_harness)
- [`platoon_harness.annotations`](#platoon_harnessannotations)
- [`platoon_harness.bwrap`](#platoon_harnessbwrap)
- [`platoon_harness.config`](#platoon_harnessconfig)
- [`platoon_harness.credit`](#platoon_harnesscredit)
- [`platoon_harness.drivers`](#platoon_harnessdrivers)
- [`platoon_harness.drivers.claude`](#platoon_harnessdriversclaude)
- [`platoon_harness.drivers.codex`](#platoon_harnessdriverscodex)
- [`platoon_harness.drivers.env`](#platoon_harnessdriversenv)
- [`platoon_harness.drivers.exec`](#platoon_harnessdriversexec)
- [`platoon_harness.drivers.levels`](#platoon_harnessdriverslevels)
- [`platoon_harness.drivers.openhands`](#platoon_harnessdriversopenhands)
- [`platoon_harness.drivers.pi`](#platoon_harnessdriverspi)
- [`platoon_harness.drivers.process`](#platoon_harnessdriversprocess)
- [`platoon_harness.drivers.wire`](#platoon_harnessdriverswire)
- [`platoon_harness.extensions`](#platoon_harnessextensions)
- [`platoon_harness.http`](#platoon_harnesshttp)
- [`platoon_harness.kernel`](#platoon_harnesskernel)
- [`platoon_harness.patterns`](#platoon_harnesspatterns)
- [`platoon_harness.primitives`](#platoon_harnessprimitives)
- [`platoon_harness.rpc`](#platoon_harnessrpc)
- [`platoon_harness.runtime`](#platoon_harnessruntime)
- [`platoon_harness.runtime.authority`](#platoon_harnessruntimeauthority-1)
- [`platoon_harness.runtime.control`](#platoon_harnessruntimecontrol)
- [`platoon_harness.runtime.diffs`](#platoon_harnessruntimediffs)
- [`platoon_harness.runtime.git`](#platoon_harnessruntimegit)
- [`platoon_harness.runtime.host`](#platoon_harnessruntimehost)
- [`platoon_harness.runtime.isolation`](#platoon_harnessruntimeisolation)
- [`platoon_harness.runtime.looks`](#platoon_harnessruntimelooks)
- [`platoon_harness.runtime.opening`](#platoon_harnessruntimeopening)
- [`platoon_harness.runtime.paths`](#platoon_harnessruntimepaths)
- [`platoon_harness.runtime.recovery`](#platoon_harnessruntimerecovery)
- [`platoon_harness.runtime.workspaces`](#platoon_harnessruntimeworkspaces)
- [`platoon_harness.schema`](#platoon_harnessschema)
- [`platoon_harness.session`](#platoon_harnesssession-1)
- [`platoon_harness.team`](#platoon_harnessteam-1)
- [`platoon_harness.testing`](#platoon_harnesstesting)
- [`platoon_harness.tools`](#platoon_harnesstools)
- [`platoon_harness.topology`](#platoon_harnesstopology)
- [`platoon_harness_acp`](#platoon_harness_acp)

## `platoon_harness`

Durable multi-agent sessions over the agent harnesses you already use.

### `platoon_harness.ConfigError`

Imported from [`platoon_harness.schema.ConfigError`](#platoon_harnessschemaconfigerror).

### `platoon_harness.Ending`

Imported from [`platoon_harness.session.Ending`](#platoon_harnesssessionending).

### `platoon_harness.JournalError`

Imported from [`platoon_harness.kernel.JournalError`](#platoon_harnesskerneljournalerror).

### `platoon_harness.load_team`

Imported from [`platoon_harness.config.load_team`](#platoon_harnessconfigload_team).

### `platoon_harness.on`

Imported from [`platoon_harness.primitives.on`](#platoon_harnessprimitiveson).

### `platoon_harness.Refused`

Imported from [`platoon_harness.kernel.Refused`](#platoon_harnesskernelrefused).

### `platoon_harness.Role`

Imported from [`platoon_harness.team.Role`](#platoon_harnessteamrole).

### `platoon_harness.Session`

Imported from [`platoon_harness.session.Session`](#platoon_harnesssessionsession).

### `platoon_harness.Team`

Imported from [`platoon_harness.team.Team`](#platoon_harnessteamteam).

### `platoon_harness.told`

Imported from [`platoon_harness.runtime.opening.told`](#platoon_harnessruntimeopeningtold).

## `platoon_harness.annotations`

Annotations: what an estimator says of the record, a reward or a credit, kept in `annotations.sqlite` beside the
journal and never in it, as `git notes` attach to commits. Each is one producer's statement at one version about one
event at one head, never a fact. `Session.annotate` writes one, checked against the journal, and `Session.annotations`
reads them: the one way in and out. Nothing an agent can reach opens the file. See RFC 0011.

### `platoon_harness.annotations.Annotate`

```python
class Annotate(Args):
    target: Annotated[EventRef, Field(description="The event it is about, by its ref, `stream@version`.")]
    kind: Annotated[Literal["reward", "credit"], Field(description="`reward` or `credit`.")]
    producer: Annotated[str, Field(min_length=1, max_length=256, description="The estimator that made it, by name.")]
    producer_version: Annotated[str, Field(min_length=1, max_length=256, description="The estimator's version.")]
    params: Annotated[
        dict[str, JsonValue], Field(description="What the estimator was run with, kept as `params_hash`.")
    ] = {}
    scope: Annotated[
        Literal["local", "team"], Field(description="`local` for the target's own, `team` for what its team shares.")
    ]
    status: Annotated[Status, Field(description="`scored`, `invalid`, `error`, `timeout` or `cancelled`.")]
    value: Annotated[
        float | None, Field(allow_inf_nan=False, description="The estimate, given when `status` is `scored` alone.")
    ] = None
    evidence: Annotated[tuple[EventRef, ...], Field(description="The refs of the events it rests on.")] = ()
    head_seq: Annotated[
        int, Field(ge=1, lt=2**63, description="The head the estimator read at, which names the trace it is about.")
    ]
```

One statement about one event of the record, by a named estimator. It is unique on its producer, version, params,
target and kind, so a second estimator, or a second version, writes beside the first.

### `platoon_harness.annotations.Annotation`

```python
class Annotation(Model):
    id: int
    target: str
    kind: Literal["reward", "credit"]
    producer: str
    producer_version: str
    params_hash: str
    scope: Literal["local", "team"]
    status: Status
    value: float | None
    evidence: tuple[str, ...]
    head_seq: int
    wall_time: float
```

A statement as `annotations.sqlite` holds it. A client shows its `value` only with its `producer` and
`producer_version`, beside any other estimate of the same target, and never sums two into a fact.

### `platoon_harness.annotations.ANNOTATIONS`

```python
ANNOTATIONS = "annotations.sqlite"
```

### `platoon_harness.annotations.Status`

```python
Status = Literal["scored", "invalid", "error", "timeout", "cancelled"]
```

How an estimate came out. Only `scored` has a value, so the other four are never zero, and with no statement at all a
target is unscored, which no status says.

## `platoon_harness.bwrap`

**Experimental.** [STATUS](../STATUS.md): `bwrap`, the SDK's own extension, under the `platoon_harness.extensions` group.

`bwrap`: an isolation on Linux's bubblewrap, which an isolated agent's harness, and the runtime's own git in its
tree, run in. It needs unprivileged user namespaces, and keeps the network. Nothing in the SDK imports this module: a
team that names `bwrap` among its extensions loads it.

### `platoon_harness.bwrap.Bubblewrap`

```python
class Bubblewrap: ...
```

An isolation on `bwrap`. The probe and every wrap make the same namespaces and the same view of the system.

**`refusal`**

```python
def refusal(self) -> str | None: ...
```

Why bwrap cannot confine here: it is not on `PATH`, or it fails to confine `true`, as where user namespaces
are blocked, by a kernel setting, AppArmor or a container's seccomp.

**`wrap`**

```python
def wrap(self, writable: Path, readable: Sequence[Path], hidden: Sequence[Path]) -> tuple[str, ...]: ...
```

`bwrap`'s argv: an empty tmpfs over /tmp, then over each of `hidden`; each link a `readable` path or
`writable` passes through in those, made again as it is written, but in a folder bound whole, which holds it
already; what each readable path comes to there, bound read-only at its own path; what `writable` comes to,
bound where it can be written; and each hidden folder made read-only, so that only what is bound in it shows.

### `platoon_harness.bwrap.extension`

```python
extension = Extension("bwrap", isolation=Bubblewrap())
```

## `platoon_harness.config`

Where a team comes from: layered configuration, credentials by name, and the reproducibility manifest.

### `platoon_harness.config.credentials`

```python
def credentials(team: Team, role: str, environ: Mapping[str, str] = os.environ) -> dict[str, Secret]: ...
```

The values a role's auth profile names, read from `environ`. A missing variable is a problem, not a blank.

### `platoon_harness.config.ENVIRONMENT_VARIABLE`

```python
ENVIRONMENT_VARIABLE = "PLATOON_HARNESS_CONFIG"
```

### `platoon_harness.config.forms`

```python
def forms(secret: Secret) -> set[bytes]: ...
```

A secret as text may carry it: plain, JSON-escaped, URL-quoted, and base64 in either alphabet.

### `platoon_harness.config.load_team`

```python
def load_team(
    path: Path | None = None,
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] = os.environ,
    sets: Sequence[str] = (),
    trust_project: bool = False,
) -> Team: ...
```

Layer config, low to high: defaults, user, project, team file, environment, command line.

The environment and each of `sets` are TOML text, such as `budget.usd = 5`. A project is untrusted, so what would
run code or pass a credential is refused from a project or team file without `trust_project`. Every problem is
reported at once.

### `platoon_harness.config.load_trusted`

```python
def load_trusted(
    path: Path | None = None,
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] = os.environ,
    sets: Sequence[str] = (),
) -> tuple[Team, tuple[Problem, ...]]: ...
```

The team `load_team` loads with `trust_project`, and what that trust took: each value of a project or team file
an untrusted load refuses, as the problem it would be. Both come from one read of the files, so what a person is
asked to trust is what the team runs.

### `platoon_harness.config.Manifest`

```python
class Manifest(Model):
    team: str
    topology_hash: str
    components: tuple[Component, ...]
    principal: str = "human:you"
    approvals: Literal["ask", "deny", "allow"] | None = None
    cwd: str = "."
    plan_login: bool = False
    trainable: bool = False
    sdk_version: str = __version__
    team_schema: int = TEAM_SCHEMA
    wire_protocol: int = WIRE_PROTOCOL
```

What reproduces a session, and all a runtime needs to take one up: `team` is the sanitized resolved form, which
reloads alone, `principal` the person or the program who started it, `approvals` a policy stated over every role's
own, `cwd` where a shared workspace is, `plan_login` whether its owner said several agents may run on one plan
login, and `trainable` whether it was started as a training system starts one.

**`of`**

```python
@classmethod
def of(cls, team: Team, environ: Mapping[str, str] = os.environ, **started: Any) -> Self: ...
```

The manifest of a resolved team, with versions from metadata. Nothing is imported.

**`drift`**

```python
def drift(self) -> tuple[str, ...]: ...
```

What is installed now that differs from what was recorded, in words. Nothing is imported. A resume is
labelled with this and not refused, since a session survives an upgrade.

### `platoon_harness.config.merge`

```python
def merge(low: Mapping[str, Any], high: Mapping[str, Any]) -> dict[str, Any]: ...
```

Overlay `high` on `low`. Mappings merge and everything else, lists included, is replaced.

### `platoon_harness.config.PROJECT_FILE`

```python
PROJECT_FILE = "platoon-harness.toml"
```

### `platoon_harness.config.sanitized`

```python
def sanitized(team: Team, environ: Mapping[str, str] = os.environ) -> str: ...
```

The resolved form, refused if it holds the value of a variable an auth profile names. It looks at the strings
themselves, since rendering escapes them, and an empty value holds no secret.

### `platoon_harness.config.Secret`

```python
class Secret:
    def __init__(self, value: str) -> None: ...
```

A credential value. It prints as a mask, leaves only through `reveal`, refuses every serialization, and equals a
secret of the same value.

**`reveal`**

```python
def reveal(self) -> str: ...
```

### `platoon_harness.config.TEAM_SCHEMA`

```python
TEAM_SCHEMA = 1
```

### `platoon_harness.config.WIRE_PROTOCOL`

```python
WIRE_PROTOCOL = 2
```

## `platoon_harness.credit`

Credit: producers that estimate what each agent's work in an episode was worth, written beside the journal.

Every producer is `async def produce(session, episode, *, judge, **params) -> None`, named by `module:attr`, run on an
ended session, and writes only through `Session.annotate`: an estimate by a named producer at a version, never a fact.
`judge` is model access for a producer that asks a model, or None. See architecture section 14.

### `platoon_harness.credit.propagate`

**Experimental.** [STATUS](../STATUS.md): `platoon_harness.credit.propagate`, `propagate@4`, experimental and heuristic, in the one producer signature, at version 4 in place of 1 and 2, with version 3 kept for a run recorded on it.

```python
async def propagate(
    session: Session, episode: str, *, judge: Gateway | None, retained: float, version: int = 4
) -> None: ...
```

`propagate@4`, a heuristic: split an episode's one team reward back along the record's own edges, and what its
spans took, and write each agent it reaches a local credit row on its first `agent.started`, and each span it
reaches one on its name.

The reward on the episode's `episode.closed` splits equally over the refs the episode closed on. Each event it
reaches keeps `retained` of what reached it for its maker, an agent's or nobody's, and the rest splits equally over
its edges, one share for each: its causes, its previous version or a commit's parents, its citations, an agent's
only where its exposure says Seen, and its takes. An event with no edge keeps it all. What an agent's event keeps is
that agent's, and also its span's when the event lies in one: the span holding the model call that made it, for an
entry that carries an event that event's, and for an event tied to no call its turn's when that turn is one span.
But what a claimant's event of a claim keeps, the claim, and the completion, failure or release that ended it, is
shared equally by the spans that held the claim, as `Span.claims` names them, and kept by the event's own span only
where none did. So an agent's row is its spans' rows and what it kept in no span. An agent that never started, as
one whose launch failed, has no start for a row to target, so what its events keep is in no row. An event's takes
are the events, but its own agent's, shown by each offer that agent's harness confirmed taking before a call of its
span, after the call before and the agent's latest start or resume, and below the event's bound; an event in no
span has none, nor has an entry that carries an event, whose words it repeats and which, with what it took, it
reaches as its cause; and an offer its harness never confirmed is no edge. The walk takes events newest first, so a
path that reconverges adds once. It stops at 4,096 events, or at an edge to an event no older than its own, when
every row is `invalid`. A team reward that is not scored passes its status to each row, and an agent or a span it
never reaches gets no row, so is unscored. What nobody's events kept, and an agent's that never started, is the
reward less the agents' rows, and is no row. Citing or taking gives away all but `retained` of what reaches the
event, and work nobody cites or takes earns nothing from it, unless it was done under a claim whose events are
reached.

`version` 3 writes `propagate@3`'s rows, which keep a claimant's event of a claim in its own span too, for a run
recorded on it. `judge` is not read. Refused `invalid` for a `retained` outside [0, 1], a `version` other than 3 or
4, or a reward on an episode that closed on no ref, and `conflict` for several team rewards.

### `platoon_harness.credit.PROPAGATE`

```python
PROPAGATE = "platoon_harness.credit:propagate"
```

The producer `propagate` writes as, the name an entry runs it by.

## `platoon_harness.drivers`

The driver contract: how one harness session is presented to the runtime, whoever wrote the driver.

### `platoon_harness.drivers.Access`

```python
Access = Annotated[Mapping[str, Secret] | Gateway, PlainSerializer(_refused)]
```

Model access: variable names to values, URLs included, or a gateway. Either holds a `Secret`, so it refuses
serialization whole, as none would be left to the union's guesses.

### `platoon_harness.drivers.AgentSpec`

```python
class AgentSpec(Model):
    agent: str
    role: str
    goal: Delivery | None = None
    cwd: Path
    folder: Path
    model: str | None = None
    effort: str | None = None
    sandbox: str | None = None
    allow_native_children: bool = False
    tools: ToolBinding | None = None
    access: Access = {}
    env: Mapping[str, str] = {}
    instructions: str | None = None
    resume: str | None = None
    wrap: tuple[str, ...] = ()
```

One agent to start, or to resume from the native id in `resume`. `goal` is the first delivery of a fresh start,
under the id of the offer that launched it, so its harness says it landed as it says any input did, and None when
there is none, as on a resume. `folder` is the agent's own directory, for its record, log and native home. `access`
is model access: variable names to values, URLs included, that reach only the harness's environment, or a gateway,
which only a driver that declares `sealed` is given. `effort` goes to the harness as it stands, and `sandbox` is one
of the values the driver declared. `allow_native_children` lets the harness start agents of its own. A `HOME` in
`env` is the harness's home. `wrap` is the argv of the isolation it runs in, which `Process` puts before its
command, so that all it starts is confined with it, and is empty for a harness that runs unconfined.

### `platoon_harness.drivers.ApprovalRequested`

Imported from [`platoon_harness.primitives.ApprovalRequested`](#platoon_harnessprimitivesapprovalrequested).

### `platoon_harness.drivers.BEARER_VARIABLE`

```python
BEARER_VARIABLE = "PLATOON_HARNESS_BEARER"
```

Where a sealed launch puts its gateway's bearer: the harness's environment is the one place the bearer goes, and a
file the launch writes names this variable, never its value.

### `platoon_harness.drivers.Boundary`

Imported from [`platoon_harness.primitives.Boundary`](#platoon_harnessprimitivesboundary).

### `platoon_harness.drivers.Capabilities`

Imported from [`platoon_harness.primitives.Capabilities`](#platoon_harnessprimitivescapabilities).

### `platoon_harness.drivers.ChildSeen`

Imported from [`platoon_harness.primitives.ChildSeen`](#platoon_harnessprimitiveschildseen).

### `platoon_harness.drivers.Compacted`

Imported from [`platoon_harness.primitives.Compacted`](#platoon_harnessprimitivescompacted).

### `platoon_harness.drivers.Delivery`

```python
class Delivery(Model):
    input: str
    boundary: Boundary
    text: str
    items: tuple[Offered, ...]
    behind: int = 0
```

One handover. `input` is the id `input.delivered` echoes, `boundary` is one the driver declared, `text` is the
handover as a harness's prompt reads it, in the words of its surface, and `behind` counts entries left for the
next.

### `platoon_harness.drivers.Delta`

Imported from [`platoon_harness.primitives.Delta`](#platoon_harnessprimitivesdelta).

### `platoon_harness.drivers.Driver`

```python
@runtime_checkable
class Driver(Protocol): ...
```

One harness session, one instance per agent. A method it cannot honor raises `DriverError`.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

**`deliver`**

```python
async def deliver(self, delivery: Delivery) -> None: ...
```

**`interrupt`**

```python
async def interrupt(self) -> None: ...
```

**`answer`**

```python
async def answer(self, approval: str, verdict: Verdict) -> None: ...
```

**`reconcile`**

```python
async def reconcile(self, input_id: str) -> Reconciled: ...
```

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

### `platoon_harness.drivers.DriverError`

```python
class DriverError(Exception): ...
```

A driver cannot do what was asked, and says why.

### `platoon_harness.drivers.DriverInfo`

```python
class DriverInfo(Model):
    name: str
    login: Login | None = None
    version: str | None = None
    capabilities: Capabilities = Capabilities()
    installed: tuple[Path, ...] = ()
    credentials: tuple[Path, ...] = ()
    check: str | None = None
```

What a driver says of itself before anything starts. `login` is None when it cannot tell without reading one, and
`version` is the harness version it would run, None when it cannot tell without starting one: `ready` says the
version that runs. `installed` is the paths its harness reads to run, as it reaches them, which an isolation shows
it of what it hides: none for a harness in this process, which nothing can confine. `credentials` is where, beneath
the folder its spec names, its harness keeps a credential, which goes when the agent ends. `check` names the check
that ships with a driver outside the SDK, as `module:function`, imported only to run it: a coroutine function that
takes the folder to run in and returns what `check_driver` found of the harness against FakeModel and on no account,
which `platoon-harness doctor --check` runs and keeps. The SDK's own drivers name none, as `levels.CHECKED` holds
theirs.

### `platoon_harness.drivers.ENVIRONMENT`

```python
ENVIRONMENT = "environment"
```

The name a sealed launch gives the environment's own MCP server, which a harness reaches beside ours.

### `platoon_harness.drivers.Exited`

Imported from [`platoon_harness.primitives.Exited`](#platoon_harnessprimitivesexited).

### `platoon_harness.drivers.GapReport`

Imported from [`platoon_harness.primitives.GapReport`](#platoon_harnessprimitivesgapreport).

### `platoon_harness.drivers.Gateway`

```python
class Gateway(Model):
    origin: str
    bearer: Secret
    model: str
    tools: str | None = None
    compaction_headers: Mapping[str, str] = {}
```

Model access through a training system's gateway: its models at `origin`, a scheme and a host with nothing more,
under `bearer`, serving `model`. `tools` is the URL of the environment's own MCP server at the same origin under the
same bearer, when there is one, and `compaction_headers` go with each call a harness makes to compact its context,
so that the gateway tells that call apart as it is made.

### `platoon_harness.drivers.InputDelivered`

Imported from [`platoon_harness.primitives.InputDelivered`](#platoon_harnessprimitivesinputdelivered).

### `platoon_harness.drivers.Item`

Imported from [`platoon_harness.primitives.Item`](#platoon_harnessprimitivesitem).

### `platoon_harness.drivers.keys_of`

```python
def keys_of(spec: AgentSpec) -> Mapping[str, Secret]: ...
```

A spec's model access as variables by name, which is all a driver with no sealed launch reads, so it refuses a
gateway.

### `platoon_harness.drivers.Login`

```python
Login = Literal["plan", "key", "gateway"]
```

### `platoon_harness.drivers.ModelCall`

Imported from [`platoon_harness.primitives.ModelCall`](#platoon_harnessprimitivesmodelcall).

### `platoon_harness.drivers.Native`

Imported from [`platoon_harness.primitives.Native`](#platoon_harnessprimitivesnative).

### `platoon_harness.drivers.Offered`

```python
class Offered(Model):
    ref: str
    gist: str
    sender: str | None = None
    body: bool = False
```

One entry handed over: its ref, who sent it, what a reader sees first, and whether it has a body, which
`blob.get` reads by its ref.

### `platoon_harness.drivers.RAW_LIMIT`

Imported from [`platoon_harness.primitives.RAW_LIMIT`](#platoon_harnessprimitivesraw_limit).

### `platoon_harness.drivers.Ready`

Imported from [`platoon_harness.primitives.Ready`](#platoon_harnessprimitivesready).

### `platoon_harness.drivers.Reconciled`

```python
Reconciled = Literal["landed", "not_landed", "unknown"]
```

### `platoon_harness.drivers.refuse_other_effort`

```python
def refuse_other_effort(spec: AgentSpec, effort: str | None) -> None: ...
```

A harness warns of an effort it cannot honor and runs on, so hold what it says it runs at to what was asked.

### `platoon_harness.drivers.refuse_unset_model`

```python
def refuse_unset_model(spec: AgentSpec) -> None: ...
```

On a harness's own login its default is the user's. Where access was given, it may go somewhere nobody chose.

### `platoon_harness.drivers.Report`

Imported from [`platoon_harness.primitives.Report`](#platoon_harnessprimitivesreport).

### `platoon_harness.drivers.Reporter`

```python
Reporter = Callable[[Report], Awaitable[None]]
```

### `platoon_harness.drivers.SHORT_LIMIT`

Imported from [`platoon_harness.primitives.SHORT_LIMIT`](#platoon_harnessprimitivesshort_limit).

### `platoon_harness.drivers.text_of`

```python
def text_of(content: str | Sequence[Mapping[str, Any]]) -> str: ...
```

What a message or a tool's result says, in either of its shapes.

### `platoon_harness.drivers.ToolBinding`

```python
class ToolBinding(Model):
    url: str
    token: Secret
    namespace: str
    bin: Path
```

Our tools as one agent reaches them. `namespace` prefixes their names in the harness, and `bin` holds `ph`.

### `platoon_harness.drivers.TurnEnded`

Imported from [`platoon_harness.primitives.TurnEnded`](#platoon_harnessprimitivesturnended).

### `platoon_harness.drivers.TurnStarted`

Imported from [`platoon_harness.primitives.TurnStarted`](#platoon_harnessprimitivesturnstarted).

### `platoon_harness.drivers.unknown_frame`

```python
def unknown_frame(kind: str, raw: str) -> tuple[Native, GapReport]: ...
```

What a frame nobody's vocabulary covers becomes: the frame, as far as it fits, and the gap it leaves.

### `platoon_harness.drivers.UNREADABLE`

```python
UNREADABLE = (AttributeError, KeyError, TypeError, ValueError, RecursionError)
```

What reading a harness's frame raises, whichever part of it would not read.

### `platoon_harness.drivers.Usage`

Imported from [`platoon_harness.primitives.Usage`](#platoon_harnessprimitivesusage).

### `platoon_harness.drivers.Verdict`

Imported from [`platoon_harness.primitives.Verdict`](#platoon_harnessprimitivesverdict).

## `platoon_harness.drivers.claude`

**Experimental.** [STATUS](../STATUS.md): The `claude` driver.

The `claude` driver: `claude -p` in stream-json, with the control protocol on the same pipes.

A role runs in the user's own setup: this writes none of their configuration, and what it adds goes in beside theirs.
Every approval the harness asks for comes to the runtime, and a role's budget is what limits it.

### `platoon_harness.drivers.claude.ClaudeDriver`

```python
class ClaudeDriver:
    def __init__(self) -> None: ...
```

One `claude -p` process. A turn runs from the input that began it to its `result`.

Frames are translated on the read loop, which never waits, so the pipe drains. An agent is parked at turn end and
never at its `wait` call, since Claude batches `wait` with sibling tools, and that is the runtime's to do.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

**`deliver`**

```python
async def deliver(self, delivery: Delivery) -> None: ...
```

Hand the text over, and return when the harness says it is queued. It lands at the next tool boundary, or
else as the next turn. A harness that has stopped reading holds this up until the host drops it, and what was
written stays in the pipe, to land if it ever reads again.

**`interrupt`**

```python
async def interrupt(self) -> None: ...
```

Stop the turn, or the one an input on its way is about to begin. The harness drops what it has queued, which
the runtime offers again, as it would begin a turn by itself otherwise, and it has done both by the time it
answers, so a turn open then is the one cut, and one that ends with no turn open labels nothing.

**`answer`**

```python
async def answer(self, approval: str, verdict: Verdict) -> None: ...
```

**`reconcile`**

```python
async def reconcile(self, input_id: str) -> Reconciled: ...
```

What came of an input after a crash is in the harness's own transcript, the one record that survives it. Its
format is internal, so a miss proves nothing, and this never says `not_landed`.

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

Ask first, then end what is left: only the harness can end a tool that leads a group of its own, and stdin
ending does not stop a running one. It exits 1 after this, which is normal.

## `platoon_harness.drivers.codex`

**Experimental.** [STATUS](../STATUS.md): The `codex` driver.

The `codex` driver: `codex app-server` on stdio, JSON-RPC with no `jsonrpc` member.

A role runs in the user's own setup: `thread/start.config` overlays their configuration for one thread and writes none
of it. Every approval the harness asks for comes to the runtime, and a role's budget is what limits it.

### `platoon_harness.drivers.codex.CodexDriver`

```python
class CodexDriver:
    def __init__(self) -> None: ...
```

One `codex app-server` with one thread. Our turn runs from the input that began it until the thread and every
native child of it have stopped, since a child can outlive its parent's turn, and nothing else says it is at work.
A child counts from the first frame that names it, which can be its spawn, as its turn can start after its parent's
has ended.

Frames are translated on the read loop, which never waits, so the pipe drains. An approval waits in a task of its
own, which is what `Peer` gives a request.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

**`deliver`**

```python
async def deliver(self, delivery: Delivery) -> None: ...
```

**`interrupt`**

```python
async def interrupt(self) -> None: ...
```

Stop the turn, on this thread and on every child of it, as `turn/interrupt` stops one thread alone. A turn
yet to start, of an input on its way or of a child its spawn named, has no id yet, so it is cut as it starts. A
tool may run on, as an exec session outlives a turn. What was steered and never landed is lost to the harness at
this, and the runtime offers it again.

**`answer`**

```python
async def answer(self, approval: str, verdict: Verdict) -> None: ...
```

**`reconcile`**

```python
async def reconcile(self, input_id: str) -> Reconciled: ...
```

What came of an input after a crash is in the thread's newest turns, which carry the id it went out under. A
miss proves nothing, as an older turn is on a later page, so this never says `not_landed`.

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

End of stdin ends the app-server and whatever tool it has running, even one in a session of its own.

## `platoon_harness.drivers.env`

The environment of a harness: an allowlist, and redaction of what it had to hold.

### `platoon_harness.drivers.env.harness_env`

```python
def harness_env(spec: AgentSpec, *names: str, environ: Mapping[str, str] = os.environ) -> dict[str, str]: ...
```

The whole environment of one harness process: what it inherits, a `TMPDIR` of its own, and what `spec` names.
Later entries win: `spec.env` over the inherited, and model access over both, each variable it names or a gateway's
bearer under `BEARER_VARIABLE`. A `HOME` that `spec.env` names is the harness's home, so none of `names` that would
keep its state elsewhere is inherited.

### `platoon_harness.drivers.env.Held`

```python
class Held:
    def __init__(self, redact: Redactor) -> None: ...
```

One stream through a `Redactor`. What could be the start of a secret waits for the next chunk, and a cut never
falls inside a character.

**`feed`**

```python
def feed(self, chunk: bytes) -> bytes: ...
```

**`flush`**

```python
def flush(self) -> bytes: ...
```

### `platoon_harness.drivers.env.homedir`

```python
def homedir(folder: Path) -> Path: ...
```

An isolated harness's own `HOME`, in its folder, where it keeps its state as it would in yours.

### `platoon_harness.drivers.env.inherited`

```python
def inherited(*names: str, environ: Mapping[str, str] = os.environ) -> dict[str, str]: ...
```

All a process takes from ours: what any process needs, and `names`, what a harness needs to sign in as it does in
the shell, which is where its login lives and its way out to the network. A variable that would change a harness's
behavior, or that leaks a parent's identity, has no way through, and provider keys stay in auth profiles.

### `platoon_harness.drivers.env.on_path`

```python
def on_path(*programs: str) -> tuple[Path, ...]: ...
```

Where `PATH` finds each of `programs`, as a harness reaches it, for those it finds.

### `platoon_harness.drivers.env.open_beneath`

```python
def open_beneath(folder: Path, path: Path, flags: int, mode: int = 0o600) -> int: ...
```

Open `path`, which lies at or beneath `folder`, following no symlink below `folder`, and return the descriptor.
So a confined agent that plants a symlink in its own folder cannot send the runtime's read or write through it to a
path outside the folder. `folder`'s own path is the runtime's and is opened as it reads, symlinks and all.

### `platoon_harness.drivers.env.PYTHON`

```python
PYTHON = tuple(dict.fromkeys(map(Path, (sys.executable, sys.prefix, sys.base_prefix, Path(__file__).parents[2]))))
```

What the runtime's own Python reads to run our modules, as our shim and the OpenHands worker do: the interpreter,
its environment, the installation that is made from, and the folder our package is in.

### `platoon_harness.drivers.env.private`

```python
def private(folder: Path, path: Path, text: str) -> str: ...
```

Write a file under `folder` that nobody else may read, following no symlink an agent could plant below `folder`,
and return where.

### `platoon_harness.drivers.env.Redactor`

```python
class Redactor:
    def __init__(self, secrets: Iterable[Secret]) -> None: ...
```

Masks secrets, in their encoded forms too, wherever a harness's words go next. `reach` is one byte short of the
longest form, so holding that much back keeps a secret from straddling two chunks, and `Held` does.

**`masked`**

```python
def masked(self, report: Report) -> Report: ...
```

A report with every text in it masked.

### `platoon_harness.drivers.env.secrets_of`

```python
def secrets_of(spec: AgentSpec) -> tuple[Secret, ...]: ...
```

Every credential a spec holds: a gateway's bearer, or each value of its access, and its token.

### `platoon_harness.drivers.env.tmpdir`

```python
def tmpdir(folder: Path) -> Path: ...
```

A harness's own `TMPDIR`, which whatever it starts inherits, and so carries the name of its folder.

## `platoon_harness.drivers.exec`

The `exec` driver: a one-shot CLI runs from config, with no code, and coordinates through `ph`.

### `platoon_harness.drivers.exec.ExecDriver`

```python
class ExecDriver:
    def __init__(self, command: Sequence[str]) -> None: ...
```

One process, one turn. `{goal}` in `command` becomes the goal. All it can say is what stdout and an exit say:
the model it ran stays unknown, so nothing is reported as if it were not.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

**`deliver`**

```python
async def deliver(self, delivery: Delivery) -> None: ...
```

**`interrupt`**

```python
async def interrupt(self) -> None: ...
```

Its one turn is the process, so stopping the turn stops the process.

**`answer`**

```python
async def answer(self, approval: str, verdict: Verdict) -> None: ...
```

**`reconcile`**

```python
async def reconcile(self, input_id: str) -> Reconciled: ...
```

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

### `platoon_harness.drivers.exec.GOAL`

```python
GOAL = "{goal}"
```

## `platoon_harness.drivers.levels`

The three levels of an agent, computed from what was verified. No driver can claim one.

### `platoon_harness.drivers.levels.CHECKED`

```python
CHECKED: Mapping[str, str] = {
    "claude": "platoon_harness.drivers.claude:ClaudeDriver",
    "codex": "platoon_harness.drivers.codex:CodexDriver",
    "openhands": "platoon_harness.drivers.openhands:OpenHandsDriver",
    "pi": "platoon_harness.drivers.pi:PiDriver",
}
```

Each harness a check of ships with the SDK, which `platoon-harness doctor --check` checks where it finds it, by the
class that drives it.

### `platoon_harness.drivers.levels.Check`

```python
class Check(Model):
    name: str
    state: Literal["passed", "failed", "skipped"]
    reason: str = ""
```

One named check. A skipped check is no pass, and `reason` says why it did not run.

### `platoon_harness.drivers.levels.Checks`

```python
class Checks(Model):
    checks: tuple[Check, ...]
```

Named checks, every failure at once.

**`failed`**

```python
@property
def failed(self) -> tuple[Check, ...]: ...
```

**`get`**

```python
def get(self, name: str) -> Check | None: ...
```

### `platoon_harness.drivers.levels.Conformance`

```python
class Conformance(Checks):
    driver: str
    implementation: str
    version: str | None
    sdk: str
    host: str
```

What `check_driver` found, pinned to one driver, by the name it gave and the class that implements it, at the
harness version it said, under one SDK, on one host, since the checks prove the driver's code and the binary
together, where they ran.

### `platoon_harness.drivers.levels.implementation`

```python
def implementation(driver: object) -> str: ...
```

The class that implements a driver, by module and name, which a result is pinned to, as a name is the driver's
own to give, and the release of each installed distribution outside the SDK whose driver entry points name the
package of that class or of a class it is built on, which release apart from the SDK, so that an upgrade of any of
them reads as one.

### `platoon_harness.drivers.levels.Level`

```python
class Level(Model):
    state: Standing
    reasons: tuple[str, ...] = ()
```

Whether a level holds, and why, or why not. `unverified` is not `unmet`: nobody has looked.

### `platoon_harness.drivers.levels.levels`

```python
def levels(capabilities: Capabilities, profile: Profile, conformance: Conformance | None) -> Levels: ...
```

What this agent has earned. Pure: all it knows arrives as arguments, and a capability counts only as far as a
check that speaks for this agent proved it. A training system still decides what trains.

### `platoon_harness.drivers.levels.Levels`

```python
class Levels(Model):
    operational: Level
    observable: Level
    trainable: Level
```

### `platoon_harness.drivers.levels.Profile`

```python
class Profile(Model):
    driver: str
    implementation: str
    version: str | None = None
    sdk: str = __version__
    host: str = Field(default_factory=socket.gethostname)
    login: Login | None = None
    tools: Visibility = "unverified"
    allow_native_children: bool = False
```

One agent as it runs: which driver, by name and class, at which harness version, under which SDK on which host,
on which login, whether its tools were seen, and whether its role lets its harness start agents of its own.

### `platoon_harness.drivers.levels.speaks_for`

```python
def speaks_for(profile: Profile, conformance: Conformance | None) -> bool: ...
```

Whether a result was made of the agent's driver, by name and class, at its harness version, under its SDK, on
its host, as only such a result counts toward a level.

### `platoon_harness.drivers.levels.Standing`

```python
Standing = Literal["met", "unmet", "unverified"]
```

### `platoon_harness.drivers.levels.SURFACES`

```python
SURFACES = ("prompt", "tool_results", "shell_reads", "files", "native_children", "compaction", "external")
```

### `platoon_harness.drivers.levels.tool_visibility`

```python
def tool_visibility(shown: tuple[str, ...] | None, ours: Sequence[str]) -> Visibility: ...
```

Whether a harness shows our tools. `shown` comes from `ready`, and is None unless it was observed. A harness may
prefix a name with `mcp__<ns>__`, so a tool is seen by its name or that ending. With no tools to look for, nothing
was seen.

### `platoon_harness.drivers.levels.unearned`

```python
def unearned(
    profile: Profile, conformance: Conformance | None, level: Literal["operational", "observable", "trainable"]
) -> tuple[str, ...]: ...
```

Why a result does not prove what `level` stands on for the harness a profile names, naming what makes one that
does, or nothing when it proves it.

### `platoon_harness.drivers.levels.unmet_by`

```python
def unmet_by(conformance: Conformance) -> tuple[str, ...]: ...
```

The levels a result's failed checks leave unmet for any agent it speaks for.

### `platoon_harness.drivers.levels.Visibility`

```python
Visibility = Literal["visible", "hidden", "unverified"]
```

## `platoon_harness.drivers.openhands`

**Experimental.** [STATUS](../STATUS.md): OpenHands as a wire worker.

The `openhands` driver: a wire worker per agent, which the runtime runs on its own interpreter as this package.

Only the worker loads OpenHands, which comes with the SDK's `openhands` extra, so importing this loads none of it.

### `platoon_harness.drivers.openhands.OpenHandsDriver`

```python
class OpenHandsDriver(WireDriver):
    def __init__(self) -> None: ...
```

One OpenHands agent, through the worker that drives its conversation. The worker finds its modules where the
runtime does, its key comes from the role's auth profile, and its way out to the network from the shell, as it
would there.

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

Start the worker with a directory of its own for the sockets of the tmux its agents start, short enough for
one, as OpenHands falls back to the one every tmux of the user's shares past that.

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

Stop the worker, then take its tmux directory back, which a worker killed outright cannot.

## `platoon_harness.drivers.pi`

**Experimental.** [STATUS](../STATUS.md): The `pi` driver.

The `pi` driver: `pi --mode rpc`, JSON records on stdio, with a response to each command and events between.

A role runs in the user's own setup: pi keeps its own agent directory, so their login, settings and extensions stay
theirs, and what we add comes in beside them, by the one extension `-e` loads. Pi asks for no approval of its own, so
that extension asks, and every approval comes to the runtime. A role's budget is what limits it.

On a gateway the launch is sealed: an agent directory of the agent's own, holding settings that retry nothing and warm
no cache, none of the user's extensions, skills, templates, themes or project instructions, no built-in tool, and the
gateway's model, our tools and the environment's beside them. Pi still compacts, through our extension, which runs pi's
own `compact` with the gateway's compaction headers and keeps the id the model gave each of its calls.

### `platoon_harness.drivers.pi.PiDriver`

```python
class PiDriver:
    def __init__(self) -> None: ...
```

One `pi --mode rpc` process. A turn runs from the first `agent_start` to `agent_settled`, since retries, a
compaction and queued input can each follow an `agent_end`.

Frames are translated on the read loop, which never waits, so the pipe drains. An agent is parked at turn end, which
is the runtime's to do. An input that lands is reported under the id of the entry pi wrote it down as, and a
compaction with what it forgot, which pi gives only when asked, so whatever pi says after either waits behind it:
the reports keep pi's order.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

**`deliver`**

```python
async def deliver(self, delivery: Delivery) -> None: ...
```

**`interrupt`**

```python
async def interrupt(self) -> None: ...
```

Stop the turn. A dialog open on a gate of the user's would hold up `abort`, so it is cancelled first. What
pi queued stays behind in its queue, where no run takes it, so `_ended` clears that, and the runtime offers it
again.

**`answer`**

```python
async def answer(self, approval: str, verdict: Verdict) -> None: ...
```

**`reconcile`**

```python
async def reconcile(self, input_id: str) -> Reconciled: ...
```

What came of an input after a crash is in the session's entries, whole and on disk, and the text of each
names its input. A miss proves nothing, as the id may be an approval's, so this never says `not_landed`.

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

End of stdin ends pi and the tool it has running, which leads a group of its own, as a `SIGTERM` does and a
`SIGKILL` does not.

## `platoon_harness.drivers.process`

What every subprocess driver shares: a process group recorded before exec, with pipes that always drain.

### `platoon_harness.drivers.process.clean`

```python
def clean(folder: Path, credentials: Iterable[Path]) -> tuple[str, ...]: ...
```

Remove from an ended agent's `folder` what its harness kept that is no record: its `TMPDIR`, and `credentials`,
where beneath the folder its driver says its harness keeps one. Return what stays of them, in words.

### `platoon_harness.drivers.process.exit_reason`

```python
def exit_reason(code: int | None) -> str: ...
```

How a leader's end reads.

### `platoon_harness.drivers.process.GroupState`

```python
GroupState = Literal["ours", "gone", "unproven"]
```

### `platoon_harness.drivers.process.LOG`

```python
LOG = "stderr.log"
```

### `platoon_harness.drivers.process.LOG_LIMIT`

```python
LOG_LIMIT = 1024 * 1024
```

### `platoon_harness.drivers.process.Process`

**Experimental.** [STATUS](../STATUS.md): `Process` on macOS.

```python
class Process:
    def __init__(
        self,
        transport: asyncio.SubprocessTransport,
        streams: _Streams,
        record: Record,
        log: _Log,
        spec: AgentSpec,
        report: Reporter,
        read: Reader,
        quota: int,
    ) -> None: ...
```

One harness process and its group, from before exec until verified gone.

`read` is called once, at once, and returns the driver's reader of `stdout`, which must wait only on the pipe, so
that the pipe drains. It hands what it finds to `put`, which never waits either. A harness's end reaches `report` as
`exited`. If nothing stops it, a closing loop or interpreter takes the group down rather than leave it. The host
masks what `put` passes on, and text cut to fit is masked first, as a cut can split a secret: `gist`, `reason` and
`unknown` do both.

**`launch`**

```python
@classmethod
async def launch(
    cls,
    command: Sequence[str],
    spec: AgentSpec,
    report: Reporter,
    *,
    read: Reader,
    env: Mapping[str, str] | None = None,
    quota: int = REPORT_QUOTA,
) -> "Process": ...
```

Start `command` in its own group, on the allowlisted environment, or on `env`, which a driver builds from
that one, under `spec.wrap`, whose program is then the group's leader. The harness cannot exec until its record
is on disk: `sh` waits for one line on stdin, and exits unexecuted if we die first.

**`returncode`**

```python
@property
def returncode(self) -> int | None: ...
```

How the leader ended, once it has.

**`exited`**

```python
async def exited(self) -> None: ...
```

Wait for the leader. A forked child may live on, and only `stop` ends it.

**`put`**

```python
def put(self, *reports: Report) -> None: ...
```

Queue reports, without waiting, so that a pipe always drains. Past the quota a delta is dropped, as deltas
may be, and anything else stops this agent with a gap.

**`gist`**

```python
def gist(self, text: str) -> str: ...
```

**`reason`**

```python
def reason(self, text: str) -> str: ...
```

**`unknown`**

```python
def unknown(self, kind: str, raw: str) -> None: ...
```

Report a frame nobody's vocabulary covers.

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

End the whole tree: end of stdin, wait, TERM, wait, KILL, then verify, and what left the group too. A harness
under a wrap gets no TERM, as its confiner passes none on and dies of one, which kills the harness outright. A
stop that came to KILL reports `crash_window`. A second call waits for the first.

### `platoon_harness.drivers.process.Reader`

```python
Reader = Callable[["Process"], Coroutine[Any, Any, None]]
```

### `platoon_harness.drivers.process.reap`

```python
async def reap(folder: Path, grace: float) -> tuple[str, ...]: ...
```

End what a crash left in an agent's `folder` and return what was left alone, in words: a group not provably ours,
or a record that cannot be read. A reused pid can never make this signal a stranger. Only the driver's own record
and a wire program's are read, following no symlink a confined agent could plant, because a harness can write under
its folder. What left a group is found by the `TMPDIR` it inherited, which proves it ours, so a group that outlived
its leader is named for what that misses.

### `platoon_harness.drivers.process.run`

```python
async def run(
    command: Sequence[str],
    *,
    cwd: Path,
    folder: Path,
    env: Mapping[str, str],
    output: Path,
    limit: float,
    clock: Clock,
    grace: float,
) -> int | None: ...
```

Run `command` in `cwd` as a harness is run, in a group of its own recorded in `folder` before it can exec, on
`env`, which should give it `folder`'s `TMPDIR`, with nothing on stdin and all it prints in `output`, until it exits
or `limit` seconds pass on `clock`. Then what is left of it is ended, as `reap` ends it, whichever way it went. Its
exit code, negative for the signal that ended it, or None when its limit came first.

### `platoon_harness.drivers.process.Record`

```python
class Record(Model):
    pid: int
    started: str
```

A process group, written down before its leader could exec, so that no harness can exist unrecorded.

**`of`**

```python
@classmethod
def of(cls, pid: int) -> Self | None: ...
```

The record of the process that holds `pid` now, or None when none does.

**`write`**

```python
def write(self, folder: Path) -> None: ...
```

Replace the record in one step, on disk before this returns, following no symlink a confined agent could
plant in its folder.

**`read`**

```python
@classmethod
def read(cls, folder: Path) -> Self | None: ...
```

**`state`**

```python
def state(self) -> GroupState: ...
```

Whether this group is still ours. A leader with the recorded start time proves it, and one without shows the
pid was reused, so nothing of ours is left. With the leader gone and members alive it stays `unproven`: a group
keeps its id only while it has members, so those may belong to a stranger that reused the pid and exited too.

### `platoon_harness.drivers.process.RECORD`

```python
RECORD = "proc.json"
```

### `platoon_harness.drivers.process.REPORT_QUOTA`

```python
REPORT_QUOTA = 64 * 1024 * 1024
```

### `platoon_harness.drivers.process.status`

```python
def status(command: Sequence[str], env: Mapping[str, str]) -> subprocess.CompletedProcess[bytes] | None: ...
```

What a harness says of itself in a short run of its own, or None if it says nothing in time.

### `platoon_harness.drivers.process.WIRE`

```python
WIRE = "wire"
```

## `platoon_harness.drivers.wire`

A driver in another process or language: line-delimited JSON-RPC 2.0 on stdio, its verbs equal to the Python methods.

Credentials never travel in a frame. `start` names them, and the program finds their values in its own environment: a
gateway's bearer under the variable its frame names, beside the gateway's origin, model, tools and compaction headers.

### `platoon_harness.drivers.wire.DRIVER_ERROR`

```python
DRIVER_ERROR = -32001
```

### `platoon_harness.drivers.wire.serve`

```python
def serve(driver: Driver) -> None: ...
```

Serve one driver on this process's stdio until stdin ends, which is all a wire driver in Python needs. Stdout
belongs to the protocol, so anything else goes to stderr, which the runtime keeps in the agent's log.

### `platoon_harness.drivers.wire.UNKNOWN_PROTOCOL`

```python
UNKNOWN_PROTOCOL = -32002
```

### `platoon_harness.drivers.wire.WireDriver`

```python
class WireDriver:
    def __init__(self, command: Sequence[str], inherited: Sequence[str] = ()) -> None: ...
```

The one adapter for a driver in another process. One instance runs one program for one agent, on the environment
every harness has and the variables of ours that `inherited` names, such as what a harness needs to sign in, both to
describe it and to start it.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

Ask the program, which stays up only long enough to answer, so no harness starts, add where `PATH` finds it
to the paths it says its harness reads, and say where it keeps credentials beneath its own folder, which sits
inside the agent's. This blocks, as the method is synchronous, and the answer is kept.

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

**`deliver`**

```python
async def deliver(self, delivery: Delivery) -> None: ...
```

**`interrupt`**

```python
async def interrupt(self) -> None: ...
```

**`answer`**

```python
async def answer(self, approval: str, verdict: Verdict) -> None: ...
```

**`reconcile`**

```python
async def reconcile(self, input_id: str) -> Reconciled: ...
```

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

Ask the program to end what it owns and to exit when its stdin ends, within `grace`. Then `grace` more ends
what is left, so this takes at most twice `grace`.

## `platoon_harness.extensions`

Installed components: found from metadata alone, imported only by exact name, active only when named.

### `platoon_harness.extensions.check_installed`

```python
def check_installed() -> tuple[Problem, ...]: ...
```

Duplicates and incompatible SDK requirements across everything installed, before any import.

### `platoon_harness.extensions.Component`

```python
@dataclass(frozen=True)
class Component:
    group: str
    name: str
    value: str
    distribution: str | None = None
    version: str | None = None
    requires: tuple[str, ...] = ()
```

An installed entry point as metadata states it. A `module:attr` reference has no distribution.

### `platoon_harness.extensions.discover`

```python
def discover() -> tuple[Component, ...]: ...
```

Every component the environment declares, read from metadata. Nothing is imported.

### `platoon_harness.extensions.DRIVERS`

```python
DRIVERS = "platoon_harness.drivers"
```

### `platoon_harness.extensions.EXTENSIONS`

```python
EXTENSIONS = "platoon_harness.extensions"
```

### `platoon_harness.extensions.find`

```python
def find(group: str, reference: str) -> Component: ...
```

Resolve `name`, `name@version` or `module:attr` from metadata. Nothing is imported.

### `platoon_harness.extensions.Installed`

```python
class Installed(Mapping[str, Any]):
    def __init__(self, group: str = EXTENSIONS) -> None: ...
```

One group's components. Listing reads metadata; indexing imports that one component and no other.

### `platoon_harness.extensions.load`

```python
def load(group: str, reference: str) -> Any: ...
```

Import one component by exact reference, and nothing else.

### `platoon_harness.extensions.NotInstalled`

```python
class NotInstalled(ConfigError, KeyError): ...
```

No component has this name, which is also why `Installed` has no such key.

## `platoon_harness.http`

HTTP/1.1 as the SDK's servers speak it: one request per connection, each bounded before it is believed.

A head of at most 16 KiB comes first, then whatever names who is asking, and only then a body of a stated length, never
chunked. A head has `SECONDS` on the server's clock to arrive, and then each part of a body, and of an answer as it
leaves, has as long from the part before: a client that keeps going is served however slow its link, and one that stops
is cut. Past `CONNECTIONS` open at once the server answers 503. So an idle client holds no task, socket or state here.

### `platoon_harness.http.bearer`

```python
def bearer(head: Head) -> str: ...
```

The bearer token of a request. Nothing else is a credential.

### `platoon_harness.http.check_site`

```python
def check_site(head: Head, authorities: tuple[str, ...], *, scheme: str = "http", origin: bool = False) -> None: ...
```

Refuse what a browser could be tricked into sending. `Host` must name an authority this server serves, which
defeats DNS rebinding, and `Origin`, which `origin` requires, must be the origin of that same authority.

### `platoon_harness.http.CONNECTIONS`

```python
CONNECTIONS = 1024
```

### `platoon_harness.http.Cut`

```python
class Cut(Exception): ...
```

What was being awaited lost its race, and has been dropped.

### `platoon_harness.http.Head`

```python
class Head(NamedTuple):
    method: str
    path: str
    query: str
    headers: Mapping[str, str]
```

A request's line and headers. A header that decides anything may appear once.

### `platoon_harness.http.HEAD_LIMIT`

```python
HEAD_LIMIT = 16 * 1024
```

### `platoon_harness.http.Rejected`

```python
class Rejected(Exception):
    def __init__(self, status: int, *headers: str, why: str = "") -> None: ...
```

A request refused at the HTTP layer: its status, any headers that say how to ask again, and why.

### `platoon_harness.http.response`

```python
def response(status: int, body: bytes = b"", *headers: str) -> bytes: ...
```

A whole answer, which closes its connection.

### `platoon_harness.http.SECONDS`

```python
SECONDS = 10.0
```

### `platoon_harness.http.Server`

```python
class Server[R]:
    def __init__(self, clock: Clock, *, connections: int = CONNECTIONS) -> None: ...
```

One request per connection. A subclass says how a request is `received` once its head is in, reading any body
with `body`, how it is `answered`, unless the client goes first, how a refusal is said, and what follows once an
answer has left, which is when anyone is told of it.

**`listen`**

```python
async def listen(self, host: str, port: int = 0, *, tls: ssl.SSLContext | None = None) -> None: ...
```

Bind every address `host` names, all on `port`, or for 0 on one port free on each, which may take a few
tries, and start answering, over TLS with a context. A name such as `localhost` can name two addresses, and a
port left free on either is anyone's to take.

**`port`**

```python
@property
def port(self) -> int: ...
```

**`stop`**

```python
async def stop(self) -> None: ...
```

Stop listening and drop every request under way.

**`receive`**

```python
async def receive(self, head: Head, reader: asyncio.StreamReader) -> R: ...
```

Check a request whose head is in, and read the rest of it.

**`body`**

```python
async def body(self, head: Head, reader: asyncio.StreamReader, limit: int) -> bytes: ...
```

A request's body, whose length it must state, up to `limit`, each part of it within `SECONDS` of the last.

**`answer`**

```python
async def answer(self, request: R) -> bytes: ...
```

**`refuse`**

```python
def refuse(self, rejected: Rejected) -> bytes: ...
```

**`sent`**

```python
async def sent(self, request: R) -> None: ...
```

What follows once the answer to `request` has left.

### `platoon_harness.http.unless`

```python
async def unless[T](rival: Awaitable[Any], work: Coroutine[Any, Any, T]) -> T: ...
```

`work`'s result, unless `rival` finishes first, which drops the work and raises `Cut`.

## `platoon_harness.kernel`

The session kernel: streams, principals, grants and effects.

It knows nothing of messages, boards, tasks or harnesses; those are extensions on this same public contract.

### `platoon_harness.kernel.Args`

```python
class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
```

An op's arguments. Undeclared fields are refused, and no type is coerced.

### `platoon_harness.kernel.Clock`

```python
class Clock(Protocol): ...
```

A source of time. Time decides timers and leases; it never orders events.

**`now`**

```python
def now(self) -> float: ...
```

**`sleep`**

```python
async def sleep(self, seconds: float) -> None: ...
```

### `platoon_harness.kernel.Daemon`

```python
@dataclass(frozen=True)
class Daemon:
    name: str
    run: Callable[["Kernel"], Awaitable[None]]
```

A named task. `run` reads views, touches the world and reports through ops.

### `platoon_harness.kernel.Delta`

```python
class Delta(BaseModel, frozen=True):
    agent: str
    frame: int
    text: str
    lag: int = 0
    ended: int | None = None
```

Live text an agent said past a reader's frame, joined, through `frame`. `ended` is the seq of the event that
replaced what it said before this text, an item or an end, which the journal holds through that seq, so a reader
drops its own copy. `lag` counts frames of this text that are no longer held.

### `platoon_harness.kernel.Effect`

```python
class Effect(BaseModel, frozen=True):
    id: int
    kind: str
    state: Literal["requested", "started", "finished", "failed", "uncertain", "cancelled"]
    on_uncertain: Literal["retry", "reconcile", "surface"]
    timeout: float | None
    priority: int
    agent: str | None
    attempts: int
    after: int | None
    data: Any
```

One row of the outbox.

### `platoon_harness.kernel.Effects`

```python
class Effects(View):
    schema = """
    CREATE TABLE v_effects(
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        state TEXT NOT NULL,
        on_uncertain TEXT NOT NULL CHECK (on_uncertain IN ('retry', 'reconcile', 'surface')),
        timeout REAL,
        priority INTEGER NOT NULL,
        agent TEXT,
        attempts INTEGER NOT NULL,
        after INTEGER,
        data TEXT NOT NULL
    ) STRICT;
    CREATE INDEX v_effects_state ON v_effects(state, priority);
    """
```

The outbox and the input to recovery.

**`requested`**

```python
@fold("effect.requested")
def requested(self, event: Event) -> None: ...
```

**`started`**

```python
@fold("effect.started")
def started(self, event: Event) -> None: ...
```

**`moved`**

```python
@fold("effect.finished", "effect.failed", "effect.uncertain", "effect.retried", "effect.cancelled")
def moved(self, event: Event) -> None: ...
```

**`get`**

```python
def get(self, id: int) -> Effect | None: ...
```

**`in_state`**

```python
def in_state(self, state: str) -> list[Effect]: ...
```

**`requested_for`**

```python
def requested_for(self, agent: str) -> list[Effect]: ...
```

**`last`**

```python
def last(self, agent: str, *kinds: str) -> Effect | None: ...
```

The newest of an agent's effects of these kinds, or None if it had none.

**`ready`**

```python
def ready(self, kind: str | None = None) -> list[Effect]: ...
```

Requested effects a daemon may start now: per agent in order, unless priority bypasses that.

### `platoon_harness.kernel.Event`

```python
class Event(BaseModel, frozen=True):
    v: int
    seq: int
    stream: str
    version: int
    type: str
    actor: str
    agent: str | None
    turn: str | None
    context_version: int | None
    episode: str | None
    topology_rev: int
    correlation: str | None
    cause: tuple[int, ...]
    based_on: tuple[str, ...]
    native: Mapping[str, str]
    model: ModelRef | None
    wall_time: float
    gist: str
    data: Any
    outcome: Outcome | None
```

One immutable fact, on exactly one stream.

### `platoon_harness.kernel.Extension`

```python
@dataclass(frozen=True)
class Extension:
    name: str
    ops: Sequence[Op] = ()
    views: Sequence[type[View]] = ()
    daemons: Sequence[Daemon] = ()
    presets: Sequence[Callable[..., Any]] = ()
    isolation: Any = None
```

A named set of ops, views, daemons and topology presets, and the `isolation` that confines an isolated agent, if
it gives one. The name is the ops' namespace.

### `platoon_harness.kernel.filesystem`

**Experimental.** [STATUS](../STATUS.md): macOS filesystem detection and `F_FULLFSYNC`.

```python
def filesystem(path: str | os.PathLike[str]) -> Filesystem: ...
```

Say what holds `path`, or its nearest existing ancestor. The kernel resolves links and bind mounts.

### `platoon_harness.kernel.Filesystem`

```python
class Filesystem(NamedTuple):
    name: str
    kind: str
```

What holds a path. `kind` is local, network, memory or unknown.

### `platoon_harness.kernel.first`

```python
async def first(work: Awaitable[Any], *rivals: Awaitable[Any]) -> bool: ...
```

Race `work` against `rivals` and drop whatever is left. True if `work` finished first, and if it failed this
raises what it raised.

### `platoon_harness.kernel.fold`

```python
def fold[F: Callable[..., None]](*types: str) -> Callable[[F], F]: ...
```

Mark a view method as the fold for these event types. `*` folds every event, for a view that cannot name them.

### `platoon_harness.kernel.DATA_LIMIT`

```python
DATA_LIMIT = 16 * 1024
```

### `platoon_harness.kernel.Gauges`

```python
class Gauges(BaseModel, frozen=True):
    seconds: float
    events: int
    commits: int
    depth: int
    deepest: int
    in_flight: dict[str, int]
    busy: int
    acks: int
    ack_p50: float | None
    ack_p99: float | None
    ack_max: float | None
    cpu_seconds: float
    peak_resident_bytes: int | None
```

What a kernel holding its journal for writing has measured since it opened it, as a runtime does as it starts,
and what the process holding it has used.

A write is what the writer takes: a command, a body or a rebuild. In `seconds` it committed `events` in `commits`
transactions, one fsync each. `depth` writes are queued or in the open transaction now, and at most `deepest` were;
`in_flight` counts the commands among them by principal, and `busy` the writes refused for want of room, which no
journal holds. `acks` writes were answered, each timed from joining the queue to its answer after the commit that
made it durable: `ack_p50` and `ack_p99` are read from buckets a quarter octave wide, so each is never below the
true one and at most 19% above it, or 10 µs, and each is None until a write has been answered. `cpu_seconds` is the
process's, user and system, since it started, and `peak_resident_bytes` the most memory it has held, None where the
system gives it in no unit checked here, which is anywhere but Linux.

### `platoon_harness.kernel.GIST_LIMIT`

```python
GIST_LIMIT = 280
```

### `platoon_harness.kernel.Grant`

```python
class Grant(Args):
    who: str
    ops: str
    on: str = "*"
```

Who may run which ops on what. Absence means deny.

### `platoon_harness.kernel.Grants`

```python
class Grants(View):
    schema = """
    CREATE TABLE v_grants(
        who TEXT NOT NULL,
        ops TEXT NOT NULL,
        "on" TEXT NOT NULL,
        rev INTEGER NOT NULL,
        PRIMARY KEY (who, ops, "on")
    ) WITHOUT ROWID, STRICT;
    """
```

The compiled topology: `(who, ops, on)`, the only authorization input.

**`added`**

```python
@fold("grant.added")
def added(self, event: Event) -> None: ...
```

**`removed`**

```python
@fold("grant.removed")
def removed(self, event: Event) -> None: ...
```

**`held_by`**

```python
def held_by(self, me: Principal) -> list[Grant]: ...
```

Every grant naming `me` by id, by kind, by role or as `all`.

**`authorize`**

```python
def authorize(self, principal: Principal, operation: Op, target: str | None = None) -> Principal: ...
```

Return the live principal if it may run `operation` on `target`, or refuse.

With no target this asks about any object. The runtime is trusted and takes no grant; runtime-only and
agent-only ops are kept to their kind, so no glob reaches them for anyone else. Scopes only attenuate.

**`permits`**

```python
def permits(self, principal: Principal, name: str, target: str) -> bool: ...
```

Whether the op called `name` is open to this principal on `target`: a question, where `authorize` refuses.

### `platoon_harness.kernel.hash_token`

```python
def hash_token(token: str) -> str: ...
```

The form in which a credential may be stored.

### `platoon_harness.kernel.is_held`

```python
def is_held(folder: Path) -> bool: ...
```

Whether a live runtime holds this folder's lock, which is how anyone can tell a session is live.

### `platoon_harness.kernel.JournalError`

```python
class JournalError(Exception): ...
```

A commit failed, so the kernel took nothing more, as after a kill. What the batch left is unknown: a resume
recovers the session, and a retry under its key answers from the journal if it landed.

### `platoon_harness.kernel.Kernel`

```python
class Kernel:
    runtime = Principal(id="runtime")
    def __init__(
        self,
        folder: Path,
        clock: Clock,
        loaded: Loaded,
        uri: str,
        *,
        frozen: bool = False,
        writing: tuple[sqlite3.Connection, int] | None = None,
    ) -> None: ...
```

One session's journal, reached through `submit`, `query`, `read`, `follow` and `deltas`.

Closing checkpoints the WAL to empty, which is what makes the folder portable.

**`open`**

```python
@classmethod
def open(
    cls,
    path: str | os.PathLike[str],
    *,
    clock: Clock | None = None,
    extensions: Iterable[Extension] = (),
    read_only: bool = False,
) -> "Kernel": ...
```

Open a session folder as its one live writer, or read-only.

Read-only opens a closed journal anywhere, since `immutable=1` takes no locks; a live one, only on a local disk.

**`submit`**

```python
async def submit(
    self,
    principal: Principal,
    op: str,
    args: Mapping[str, Any],
    *,
    key: str | None = None,
    expected_version: int | None = None,
    native: Mapping[str, str] | None = None,
) -> Outcome: ...
```

Run one command and return its outcome once durable. A refusal is an outcome, not an exception. A read-only
kernel answers only a command its journal answered under the same key, as any retry is answered.

`native` holds a backend's ids for this command, stamped on its events as evidence and read by nothing.

**`recover`**

```python
async def recover(self, *drift: str) -> Outcome: ...
```

Begin a new incarnation: started effects become uncertain, a turn in flight is lost, policies apply.
`drift` says what runs now that differs from what the session began under, which `runtime.started` keeps.

**`rebuild`**

```python
async def rebuild(self, view: type[View]) -> None: ...
```

Drop one view and refold it.

**`rebuild_all`**

```python
async def rebuild_all(self) -> None: ...
```

Drop every view and refold it. Identical contents are the point.

**`put_body`**

```python
async def put_body(self, body: bytes) -> str: ...
```

Store a body and return its sha256, durable before this returns. An orphan is harmless.

**`get_body`**

```python
def get_body(self, sha256: str, *, limit: int | None = None) -> bytes: ...
```

Read a body, or refuse `not_found` with the reason. An op decides who may; this checks no grant.

One past `limit` bytes is refused `unsupported` before any of it is read.

**`erase_body`**

```python
async def erase_body(self, sha256: str) -> None: ...
```

Remove a tombstoned body's bytes from the journal, `blobs/` and the WAL. A daemon does this.

Refuses `busy` while a reader holds the WAL, so the erase effect stays open until the bytes are gone.

**`query`**

```python
def query(self, principal: Principal, op: str, args: Mapping[str, Any]) -> Outcome: ...
```

Run a read-only op on a read connection. It enters no history.

**`authenticate`**

```python
def authenticate(self, token: str) -> Principal: ...
```

Resolve a credential by its hash, or refuse.

**`read`**

```python
def read(
    self,
    principal: Principal,
    *,
    after: int = 0,
    before: int | None = None,
    match: str | None = None,
    streams: Collection[str] | None = None,
    limit: int = 512,
) -> Page: ...
```

Read a page past `after` in one short transaction, oldest first, or with `before` the newest below it, still
in order. `match` globs stream names and `streams` names them, and a page holds what either takes. `cursor` is
where to go on: the next `after`, or going back the next `before`, which is `after` once nothing is left
between.

This is for the runtime and live principals other than agents, whose reads are ops, checked against grants.

**`follow`**

```python
async def follow(self, principal: Principal, *, after: int, match: str | None = None) -> AsyncIterator[Page]: ...
```

Yield pages past `after` while the kernel is open. Catch-up and live are one loop.

Near the head, followers share one read per pulse. One that has fallen behind pages by SQL, as does a page
holding a revocation, so a revoked reader is refused there.

**`head`**

```python
@property
def head(self) -> int: ...
```

The newest committed seq.

**`session_id`**

```python
@property
def session_id(self) -> str: ...
```

The constant of this journal.

**`changed`**

```python
async def changed(self, after: int) -> None: ...
```

Sleep until the head passes `after`, or the kernel closes.

**`push_delta`**

```python
def push_delta(self, agent: str, text: str) -> None: ...
```

Offer a frame of an agent's live text. It may be lost and is never journaled.

**`end_delta`**

```python
def end_delta(self, agent: str, seq: int) -> None: ...
```

Say that the event at `seq` replaced an agent's live text so far: an item it said, or an end of its turn or
of itself.

**`deltas`**

```python
async def deltas(self, agent: str, *, after: int | None = None) -> AsyncGenerator[Delta]: ...
```

Follow an agent's live text past frame `after`, or from what it is saying now, each delta joining what came
since the last. An agent's text ends when its principal is revoked, at that seq, so a reader is told so once.
It ends when the kernel closes, or once an agent that has ended has had all it said told. A reader looks for the
revocation in the tail every follower shares, so a commit costs it no read of its own.

**`supervise`**

```python
async def supervise(self) -> None: ...
```

Run every daemon, one for one, until cancelled. Cancel this before `close`.

**`closed`**

```python
@property
def closed(self) -> bool: ...
```

**`failure`**

```python
@property
def failure(self) -> JournalError | None: ...
```

Why this kernel took nothing more: a commit that failed, which closed it as a kill would.

**`read_only`**

```python
@property
def read_only(self) -> bool: ...
```

**`gauges`**

```python
def gauges(self) -> Gauges | None: ...
```

What this kernel has measured since it opened its journal for writing, as a runtime does as it starts, and
what its process has used. A read-only kernel measures nothing, so it has None.

**`close`**

```python
def close(self) -> None: ...
```

Finish queued commands, checkpoint the WAL to empty, and let go of the lock. One a failed commit closed lets
go of it too, and closing again does nothing.

### `platoon_harness.kernel.ManualClock`

```python
class ManualClock:
    def __init__(self, now: float = 0.0) -> None: ...
```

A clock that moves only when told to.

**`now`**

```python
def now(self) -> float: ...
```

**`sleep`**

```python
async def sleep(self, seconds: float) -> None: ...
```

**`advance`**

```python
def advance(self, seconds: float) -> None: ...
```

Move time forward and wake whoever is due.

**`sleeping`**

```python
async def sleeping(self) -> None: ...
```

Wait until a task is asleep, so that `advance` cannot race it.

**`slept_until`**

```python
async def slept_until(self, due: float) -> None: ...
```

Wait until a task sleeps until `due`.

**`wakes`**

```python
@property
def wakes(self) -> list[float]: ...
```

When each sleeper is due.

### `platoon_harness.kernel.ModelRef`

```python
class ModelRef(BaseModel, frozen=True):
    call_id: str
```

The model call behind an event, by the id its harness gave it, verbatim. Present only when real. Its policy,
version and tokens are the gateway's to know, so none is here. It stays a type of one field, as the envelope's
`model` is a column of every journal.

### `platoon_harness.kernel.NAME`

```python
NAME = (
    rf"[A-Za-z0-9_]{_LETTER}*(?:(?:\.{_LETTER}+)*\.(?:{_LETTER}{{1,3}}|{_LETTER}{{5,}}|[A-Za-km-z0-9_-]{_LETTER}{{3}}"
    rf"|l[A-Za-np-z0-9_-]{_LETTER}{{2}}|lo[A-Zabd-z0-9_-]{_LETTER}|loc[A-Za-jl-z0-9_-]))?"
)
```

A name: words of letters, digits, `_` and `-` joined by single dots, starting with no `-`, whose last word after a
dot is not `lock`. So every name is a path part and a git branch part. Lookarounds would say it shorter, and the engine
that checks a schema's pattern has none.

### `platoon_harness.kernel.op`

```python
def op(
    name: str,
    *,
    on: Callable[[Any], str | None] = _session,
    query: bool = False,
    exposes: bool = False,
    tool: bool = False,
    runtime: bool = False,
    agent: bool = False,
) -> Callable[[Callable[..., Any]], Op]: ...
```

Define an op from `def fn(txn: Txn, a: SomeArgs)`. `runtime` puts it out of reach of every grant, and `agent`
out of reach of everyone but an agent.

### `platoon_harness.kernel.Op`

```python
@dataclass(frozen=True)
class Op:
    name: str
    fn: Callable[[Txn, Any], Any]
    input: type[Args]
    on: Callable[[Any], str | None] = _session
    query: bool = False
    exposes: bool = False
    tool: bool = False
    runtime: bool = False
    agent: bool = False
```

An op definition. `on` names the object of one invocation, or None for an op that checks its objects itself.

`query` keeps an op out of history. `exposes` marks a read that is a command for agents and a query for everyone
else. An op is at most one of the two. `runtime` and `agent` keep an op to principals of that kind.

### `platoon_harness.kernel.Outcome`

```python
class Outcome(BaseModel, frozen=True):
    op: str
    key: str | None = None
    args_hash: str
    result: Any = None
    refusal: Refusal | None = None
    seq: int | None = None
```

How a command or query ended. `seq` is that of the event carrying it, if it has one.

### `platoon_harness.kernel.Page`

```python
class Page(BaseModel, frozen=True):
    events: tuple[Event, ...]
    cursor: int
    head: int
```

A run of events. Pass `cursor` as the next `after`.

### `platoon_harness.kernel.Principal`

```python
class Principal(BaseModel, frozen=True):
    id: str = Field(pattern=rf"^(runtime|{ENROLLED_ID})$")
    role: str | None = None
    parent: str | None = None
    path: str = "/"
    state: Literal["live", "revoked"] = "live"
    scopes: tuple[str, ...] = ("*",)
```

An authenticated actor. The id is `runtime`, or `<kind>:<name>`.

**`kind`**

```python
@property
def kind(self) -> str: ...
```

**`name`**

```python
@property
def name(self) -> str: ...
```

### `platoon_harness.kernel.Principals`

```python
class Principals(View):
    version = 2
    schema = """
    CREATE TABLE v_principals(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        role TEXT,
        parent TEXT,
        path TEXT NOT NULL,
        state TEXT NOT NULL,
        token_hash TEXT,
        scopes TEXT NOT NULL,
        revoked INTEGER
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_principals_parent ON v_principals(parent);
    CREATE UNIQUE INDEX v_principals_token ON v_principals(token_hash);
    """
```

The graph of principals: `authorize` reads it inside the transaction, and `path` makes `descendants` a prefix
test. A name is unique across kinds, so an inbox or a relation can go by the bare name. `revoked` is the seq that
revoked one.

**`added`**

```python
@fold("principal.added")
def added(self, event: Event) -> None: ...
```

**`issued`**

```python
@fold("principal.issued")
def issued(self, event: Event) -> None: ...
```

**`revoked`**

```python
@fold("principal.revoked")
def revoked(self, event: Event) -> None: ...
```

**`agent_ended`**

```python
@fold("agent.ended")
def agent_ended(self, event: Event) -> None: ...
```

**`agent_adopted`**

```python
@fold("agent.adopted")
def agent_adopted(self, event: Event) -> None: ...
```

An orphan's subtree hangs from the session now, so its old ancestors lose their relations to it.

**`get`**

```python
def get(self, id: str) -> Principal | None: ...
```

**`named`**

```python
def named(self, name: str) -> Principal | None: ...
```

The principal called `name`, of any kind.

**`live`**

```python
def live(self, id: str) -> Principal: ...
```

The principal with this id, or refuse if it is unknown or revoked.

**`revoked_at`**

```python
def revoked_at(self, id: str) -> int | None: ...
```

The seq that revoked a principal, or None while it is live or unknown.

**`by_token`**

```python
def by_token(self, token_hash: str) -> Principal | None: ...
```

**`related`**

```python
def related(self, me: Principal, relation: str, name: str) -> bool: ...
```

Whether a principal called `name` stands in `relation` to `me`, even once it has ended, so that an op on an
ended agent gives its own answer. A revoked `me` never gets here.

**`select`**

```python
def select(self, me: Principal, relation: str) -> list[Principal]: ...
```

The live principals standing in `relation` to `me`, or refuse a relation with no evaluator.

### `platoon_harness.kernel.Refusal`

```python
class Refusal(BaseModel, frozen=True):
    code: RefusalCode
    op: str | None = None
    object: str | None = None
    reachable: tuple[str, ...] | None = None
    retry_after: float | None = None
    detail: JsonValue = ""
```

Why a command or query did not happen. A refusal is data.

### `platoon_harness.kernel.Refused`

```python
class Refused(Exception):
    def __init__(
        self,
        code: RefusalCode,
        detail: JsonValue = "",
        *,
        reachable: tuple[str, ...] | None = None,
        retry_after: float | None = None,
    ) -> None: ...
```

Raised to refuse. `submit` and `query` return the refusal; `read` and `follow` raise it.

**`of`**

```python
@classmethod
def of(cls, refusal: Refusal) -> "Refused": ...
```

Raise what an outcome holds, for a caller that wants its refusals as exceptions.

### `platoon_harness.kernel.registry`

```python
def registry(extensions: Iterable[Extension] = ()) -> dict[str, Op]: ...
```

Every op a kernel holding `extensions` has, its own among them, by name: what every surface derives from.

### `platoon_harness.kernel.Stamps`

```python
class Stamps(View):
    schema = "CREATE TABLE v_stamps(scope TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID, STRICT;"
```

What `emit` stamps: the open turn of each agent, the open episode, and the version of any stream.

**`opened`**

```python
@fold("turn.started", "episode.opened")
def opened(self, event: Event) -> None: ...
```

**`closed`**

```python
@fold("turn.ended", "turn.lost", "episode.closed")
def closed(self, event: Event) -> None: ...
```

**`turn`**

```python
def turn(self, agent: str | None) -> str | None: ...
```

**`open_turns`**

```python
def open_turns(self) -> dict[str, str]: ...
```

Each agent with a turn in flight, and that turn.

**`began`**

```python
def began(self, agent: str | None) -> int | None: ...
```

The seq of the `turn.started` that opened an agent's open turn, or None while it has none.

**`episode`**

```python
def episode(self) -> str | None: ...
```

**`version_of`**

```python
def version_of(self, stream: str) -> int: ...
```

A stream's version: a group's generation, a board object's version. Read it before emitting.

A command's last event is written when the op returns, so this cannot see that one.

**`at`**

```python
def at(self, stream: str, version: int) -> Event | None: ...
```

The event a ref names, by its stream and version, or None. Read it before emitting, too.

**`event`**

```python
def event(self, seq: int) -> Event | None: ...
```

The event at a seq, as a `cause` names it, or None.

**`events`**

```python
def events(self, stream: str | None = None, *, after: int = 0) -> Iterator[Event]: ...
```

The events past `after`, oldest first, on one stream or all of them. Read it before emitting, too.

**`head`**

```python
def head(self) -> int: ...
```

The newest seq this transaction can see.

### `platoon_harness.kernel.SystemClock`

```python
class SystemClock: ...
```

The operating system's clock.

**`now`**

```python
def now(self) -> float: ...
```

**`sleep`**

```python
async def sleep(self, seconds: float) -> None: ...
```

### `platoon_harness.kernel.Timer`

```python
class Timer(BaseModel, frozen=True):
    due: float
    op: str = Field(max_length=NAME_LIMIT)
    args: dict[str, JsonValue]
    key: str = Field(max_length=NAME_LIMIT)
```

The data of a `timer.set` event: run `op` at `due`. `key` names one firing and is its idempotency key.

### `platoon_harness.kernel.Timers`

```python
class Timers(View):
    schema = """
    CREATE TABLE v_timers(
        key TEXT PRIMARY KEY,
        due REAL NOT NULL,
        op TEXT NOT NULL,
        args TEXT NOT NULL,
        seq INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_timers_due ON v_timers(due, seq);
    """
```

Timers set and not yet cleared.

**`set`**

```python
@fold("timer.set")
def set(self, event: Event) -> None: ...
```

**`cleared`**

```python
@fold("timer.cleared")
def cleared(self, event: Event) -> None: ...
```

**`next`**

```python
def next(self) -> list[Timer]: ...
```

The soonest timers.

**`besides`**

```python
def besides(self, *ops: str) -> bool: ...
```

Whether a timer is set for anything but `ops`, however many of those come first.

### `platoon_harness.kernel.Tombstones`

```python
class Tombstones(View):
    schema = "CREATE TABLE v_tombstones(sha256 TEXT PRIMARY KEY, seq INTEGER NOT NULL) WITHOUT ROWID, STRICT;"
```

Bodies redacted for good. The event and its hash survive; the bytes do not.

**`tombstoned`**

```python
@fold("body.tombstoned")
def tombstoned(self, event: Event) -> None: ...
```

**`has`**

```python
def has(self, sha256: str) -> bool: ...
```

**`inline`**

```python
def inline(self, sha256: str) -> bytes | None: ...
```

A body's bytes if the journal holds them; None if they are in `blobs/`, which an op may not read.

### `platoon_harness.kernel.tool_name`

```python
def tool_name(op: str) -> str: ...
```

An op as an MCP server lists it: `task_claim`. Two ops can share one, which `load` refuses.

### `platoon_harness.kernel.Txn`

```python
class Txn:
    def __init__(
        self,
        db: sqlite3.Connection,
        me: Principal,
        now: float,
        apply: Callable[[Event], None] | None = None,
        native: Mapping[str, str] | None = None,
        gauges: Callable[[], Gauges | None] | None = None,
    ): ...
```

What an op receives, and all an op receives. Fixed for one command: `me` and `now`.

**`view`**

```python
def view[V: View](self, view: type[V]) -> V: ...
```

Read a view inside this transaction.

**`gauges`**

```python
def gauges(self) -> Gauges | None: ...
```

What the kernel running this query has measured of its writer and its process, as they stand now, or None
from one that holds no writer, which measures nothing. A command cannot read them, so nothing it does or records
rests on what no journal holds.

**`emit`**

```python
def emit(
    self,
    type: str,
    stream: str,
    *,
    gist: str,
    data: Any = None,
    agent: str | None = None,
    cause: Iterable[int] = (),
    based_on: Iterable[str] = (),
    refs: Iterable[str] = (),
    correlation: str | None = None,
    native: Mapping[str, str] | None = None,
    model: ModelRef | None = None,
    v: int = 1,
    runtime: bool = False,
) -> Event: ...
```

Append one event and run its folds. `refs` are the refs held in `data`.

`runtime` authors the event as the runtime, for what the runtime posts in the middle of someone else's command.

**`effect`**

```python
def effect(
    self,
    kind: str,
    data: Any = None,
    *,
    on_uncertain: Literal["retry", "reconcile", "surface"] = "surface",
    timeout: float | None = None,
    priority: int = 0,
    agent: str | None = None,
    after: int | None = None,
) -> int: ...
```

Request a touch of the world and return the effect's id.

Effects of one agent run in order; a priority above zero goes first and bypasses that order. With `after`, this
one starts only once that one has finished, so a failure stops what depended on it.

### `platoon_harness.kernel.View`

```python
class View:
    name: ClassVar[str]
    version: ClassVar[int] = 1
    schema: ClassVar[str] = ""
    def __init__(self, db: sqlite3.Connection) -> None: ...
```

A class with a schema, `@fold` methods and typed query methods.

Tables are named `v_<name>`, or start with `v_<name>_`. Bumping `version` drops and refolds the view.

**`bound_folds`**

```python
def bound_folds(self) -> dict[str, list[Callable[[Event], None]]]: ...
```

This instance's folds, by event type.

## `platoon_harness.patterns`

The library tier: compositions of the session's ops, each a program's building block, using the public API alone.
See architecture section 6.

### `platoon_harness.patterns.Outcome`

```python
Outcome = Literal["contribute", "nominate", "abstain", "invalid", "failed"]
```

What a worker came to: commits of its own and no nomination; one nomination, citing one recorded commit, and no
commit; neither; anything else; or an end other than finishing, or a last look that never finished.

### `platoon_harness.patterns.population`

```python
async def population(session: Session, role: str, goal: str, *, attempts: int) -> dict[str, Outcome]: ...
```

Start workers of `role` with `goal`, each in a worktree of its own, as many at once as the session's `max_live`
allows, and all at once with none, until `attempts` have started, and give each one outcome once it has ended and
its stop has looked at what it left: each worker's, by its name, in the order they started.

A worker is `<role>-1`, `<role>-2` and on, the first name no agent has taken, told beside its goal how its outcome
is read and how to build on a peer's commit. Its outcome is recorded once, as an entry of board `outcomes` by its
name, `<outcome>: <what>`, with the outcome in `fields`, and for a contribution or a nomination the `sha` of its
commit, citing the worker's end and what it came to, and the board refuses a second. Every outcome
counts against `attempts`, abstaining and failing too, so a population whose every worker abstains ends. A worker
whose turn ended with nothing more to come for it is retired, and is `failed`, and a refusal to retire it other than
`conflict`, which says it is at work again or has ended, is raised. A spawn refused `not_permitted` is
tried again once an agent has ended. Any other refusal ends the starting, and is raised once each worker started
has its outcome. The population chooses nothing among the nominations: that is the person's.

Refused `invalid` for `attempts` below 1, and `ConfigError` names each reason the session's team cannot run it: no
such role, a role that starts with the session, a workspace other than `worktree`, which alone reaches a peer's
commit, or no topic `nominations` or board `outcomes`.

## `platoon_harness.primitives`

The core primitives, as extensions on the public kernel API and nothing else.

### `platoon_harness.primitives.Agent`

```python
class Agent(BaseModel, frozen=True):
    name: str
    role: str
    parent: str | None
    depth: int
    stays: bool
    asked: bool
    state: AgentState
    status: str | None
    reason: str | None
    harness: Any
    model: str | None
    on_parent_exit: str
    persistent: bool | None
    resume: bool | None
    native: str | None
    tool_timeout_s: float | None
    boundaries: tuple[str, ...]
    held_by: str | None
    goal: str
    goal_body: str | None
    unbegun: bool
    activity: str | None
    final_gist: str | None
    final_body: str | None
    final_ref: str | None
    finishing: bool
    finish_gist: str | None
    finish_body: str | None
    finish_ref: str | None
    stopped: str | None
    failure: str | None
    failures: int
    retry_at: float
    quieted: int
    levels: dict[str, Any]
    idle_since: float | None
    resting: bool
    exits: int
    login: str | None
    instructions: str | None
    workspace: Workspace | None
    removed: bool
    kept: Kept | None
    backend: dict[str, str]
```

One agent. `parent` is the spawner's principal id, and `None` once adopted by the session. `stays` says it is
told to stay after its task for the next message. `asked` says its parent is owed an answer: the spawn asks, and so
does each new message from the parent once it lands in a turn, until a report answers. `native` is the id its
harness resumes by, when it gave one. `unbegun` says it was given a goal and no turn has begun on it. `final_ref` is
the ref of what said its last words: its latest turn's last message, or for a finished agent what its end's report
carries. `finishing` says it called `agent.finish` in a turn that has not ended, and `finish_ref` is that call's
`agent.finished`. `stopped` says why its last turn did not stop on its own, until the next begins. `failure` is what
the last effect to fail for it said, `failures` counts handovers failed in a row, and the next waits until
`retry_at`. `quieted` is the seq of the last interrupt of it or owner's stop, and a handover asked for before it is
no failure of its harness's. `idle_since` is when it was last left between turns, by a start, a turn's end or a
hold's release. `resting` says its harness has no process, which its next handover brings back, and `exits` counts
the exits of its harness on its own since a turn of its last ended. `login` is the kind of login its harness ran on
at its latest start, or None where nobody could tell. `instructions` is the body of what its harness was told last,
or None for nothing. `workspace` is where it works, once made, and `removed` or `kept` say what its stop did with
it. `backend` is the backend's ids for it, as its admit recorded them, empty when its authority named none.

**`id`**

```python
@property
def id(self) -> str: ...
```

**`ended`**

```python
@property
def ended(self) -> bool: ...
```

**`starting`**

```python
@property
def starting(self) -> bool: ...
```

Whether a turn is on its way to this agent.

### `platoon_harness.primitives.Agents`

```python
class Agents(View):
    version = 14
    schema = """
    CREATE TABLE v_agents(
        name TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        parent TEXT,
        depth INTEGER NOT NULL,
        stays INTEGER NOT NULL,
        asked INTEGER NOT NULL,
        state TEXT NOT NULL,
        status TEXT,
        reason TEXT,
        harness TEXT NOT NULL,
        model TEXT,
        on_parent_exit TEXT NOT NULL,
        persistent INTEGER,
        resume INTEGER,
        native TEXT,
        tool_timeout_s REAL,
        boundaries TEXT NOT NULL,
        held_by TEXT,
        goal TEXT NOT NULL,
        goal_body TEXT,
        unbegun INTEGER NOT NULL,
        activity TEXT,
        final_gist TEXT,
        final_body TEXT,
        final_ref TEXT,
        finishing INTEGER NOT NULL DEFAULT 0,
        finish_gist TEXT,
        finish_body TEXT,
        finish_ref TEXT,
        stopped TEXT,
        failure TEXT,
        failures INTEGER NOT NULL DEFAULT 0,
        retry_at REAL NOT NULL DEFAULT 0,
        quieted INTEGER NOT NULL DEFAULT 0,
        levels TEXT NOT NULL DEFAULT '{}',
        idle_since REAL,
        resting INTEGER NOT NULL DEFAULT 0,
        exits INTEGER NOT NULL DEFAULT 0,
        login TEXT,
        instructions TEXT,
        workspace TEXT,
        removed INTEGER NOT NULL DEFAULT 0,
        kept TEXT,
        backend TEXT NOT NULL DEFAULT '{}'
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_agents_parent ON v_agents(parent);
    CREATE INDEX v_agents_state ON v_agents(state);
    """
```

Everyone ever spawned, live or not.

**`spawned`**

```python
@fold("agent.spawned")
def spawned(self, event: Event) -> None: ...
```

The spawn asks, so a child's first report answers it. One the session started has no parent to ask. A v1
spawn said nothing of `stays`, and then a root was told to stay and a child to finish.

**`harness_up`**

```python
@fold("agent.started", "agent.resumed")
def harness_up(self, event: Event) -> None: ...
```

**`instructed`**

```python
@fold("agent.instructed")
def instructed(self, event: Event) -> None: ...
```

A v1 record named its text `instructions`.

**`working`**

```python
@fold("turn.started")
def working(self, event: Event) -> None: ...
```

**`turn_over`**

```python
@fold("turn.ended", "turn.lost")
def turn_over(self, event: Event) -> None: ...
```

A turn that ended forgives its harness's exits, and one that was lost does not.

**`woken`**

```python
@fold("agent.woken")
def woken(self, event: Event) -> None: ...
```

**`handed`**

```python
@fold("context.offered", "context.delivered")
def handed(self, event: Event) -> None: ...
```

A parent's message asks once it lands in a turn: at once in a tool's result, and by a handover once the
harness says it landed, which for a steer can be in the turn after the one it was offered in. A v1 offer or
landing asked nothing, and a confirmation of what a result showed is no second landing.

**`answered`**

```python
@fold("message.sent")
def answered(self, event: Event) -> None: ...
```

A report answers what its parent asked, unless an interrupt or the owner's stop cut its turn. A v1 report
answered whatever it said.

**`failed`**

```python
@fold("effect.failed")
def failed(self, event: Event) -> None: ...
```

A failed handover gives back its wake, and the next waits twice as long as the last. One an interrupt or the
owner's stop cut, asked for before it, is no failure of its harness's, so what comes after wakes as usual.

**`resting_asked`**

```python
@fold("effect.requested")
def resting_asked(self, event: Event) -> None: ...
```

A harness put to rest has no process from here on, as its next handover waits for the rest to finish.

**`made`**

```python
@fold("effect.finished")
def made(self, event: Event) -> None: ...
```

Who an agent is to its backend, where it works, and what its stop did with that. An admit from before named
no backend ids, a workspace from before modes was the session's cwd, and a stop from before kept nothing it
made.

**`handed_back`**

```python
@fold("effect.cancelled")
def handed_back(self, event: Event) -> None: ...
```

A handover cancelled before it started, as the owner's stop does, gives back its wake and is no failure.

**`quiet`**

```python
@fold("wake.quieted")
def quiet(self, event: Event) -> None: ...
```

**`stopped`**

```python
@fold("session.stopped")
def stopped(self, event: Event) -> None: ...
```

A handover under way when the owner stopped is the next runtime's to fail, and that is no failure either.

**`parked`**

```python
@fold("agent.parked")
def parked(self, event: Event) -> None: ...
```

**`held`**

```python
@fold("agent.held")
def held(self, event: Event) -> None: ...
```

**`released`**

```python
@fold("agent.released")
def released(self, event: Event) -> None: ...
```

**`adopted`**

```python
@fold("agent.adopted")
def adopted(self, event: Event) -> None: ...
```

**`finishing`**

```python
@fold("agent.finished")
def finishing(self, event: Event) -> None: ...
```

**`ended`**

```python
@fold("agent.ended")
def ended(self, event: Event) -> None: ...
```

A finished agent's last words are what its end's report carries, or the end itself. An end before v2
recorded nothing it carried, so it says itself.

**`item`**

```python
@fold("item.recorded")
def item(self, event: Event) -> None: ...
```

**`get`**

```python
def get(self, name: str) -> Agent | None: ...
```

**`listed`**

```python
def listed(self) -> list[Agent]: ...
```

**`live`**

```python
def live(self) -> list[Agent]: ...
```

**`children`**

```python
def children(self, parent: str) -> list[Agent]: ...
```

**`failing`**

```python
def failing(self, handovers: int) -> list[Agent]: ...
```

Agents still spawning that an effect failed for, and those out of a turn past `handovers` failed in a row.

**`between_turns`**

```python
def between_turns(self) -> list[Agent]: ...
```

Live agents between turns whose harness has a process and could reopen its session: out of a turn and on
their way to none, with nothing to finish, and on a persistent harness that resumes, by a native id it gave.

**`count_live`**

```python
def count_live(self) -> int: ...
```

### `platoon_harness.primitives.Approval`

```python
class Approval(BaseModel, frozen=True):
    id: str
    agent: str
    gist: str
    state: Literal["pending", "resolved", "moot"]
    verdict: str | None
    resolved_by: str | None
    via: str | None
    effect: int | None
    answered: bool
    outcome: str | None
```

Four facts kept apart: asked, `state` decided, `answered` reached the harness, and the observed `outcome`.

### `platoon_harness.primitives.ApprovalRequested`

```python
class ApprovalRequested(Args):
    type: Literal["approval.requested"] = "approval.requested"
    id: Name
    gist: Gist
    body: str | None = None
    cut: Annotated[int, Field(ge=0)] = 0
```

A harness waits on a decision. `body` is the whole of what it asks to do, the command, the patch or the tool's
input, as it gave it, until the host stores it, and None when the driver cannot say. `cut` counts the bytes of the
whole ask that `body` leaves out: a driver sends the ask whole, and the host, masking it first, keeps its first
`ASK_LIMIT` bytes and counts the rest here. With no body there is nothing to count, and a cut is refused.

### `platoon_harness.primitives.Approvals`

```python
class Approvals(View):
    schema = """
    CREATE TABLE v_approvals(
        id TEXT PRIMARY KEY,
        agent TEXT NOT NULL,
        gist TEXT NOT NULL,
        state TEXT NOT NULL,
        verdict TEXT,
        resolved_by TEXT,
        via TEXT,
        effect INTEGER,
        answered INTEGER NOT NULL,
        outcome TEXT
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_approvals_agent ON v_approvals(agent, state);
    CREATE INDEX v_approvals_effect ON v_approvals(effect);
    """
```

Every approval, whichever fact it has reached.

**`requested`**

```python
@fold("approval.requested")
def requested(self, event: Event) -> None: ...
```

**`resolved`**

```python
@fold("approval.resolved")
def resolved(self, event: Event) -> None: ...
```

**`answered`**

```python
@fold("effect.finished")
def answered(self, event: Event) -> None: ...
```

**`observed`**

```python
@fold("item.recorded")
def observed(self, event: Event) -> None: ...
```

**`moot`**

```python
@fold("agent.ended", "turn.ended", "turn.lost")
def moot(self, event: Event) -> None: ...
```

Nothing waits on an approval once the turn that asked has gone: a resumed harness has forgotten it.

**`get`**

```python
def get(self, id: str) -> Approval | None: ...
```

**`asking`**

```python
def asking(self) -> int: ...
```

How many wait on a human. A stated policy decides in the same command, so anything pending is left to ask.

**`pending_for`**

```python
def pending_for(self, agent: str) -> list[Approval]: ...
```

### `platoon_harness.primitives.Attention`

```python
class Attention(View):
    version = 6
    schema = """
    CREATE TABLE v_attention(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        agent TEXT,
        gist TEXT NOT NULL,
        since_seq INTEGER NOT NULL,
        version INTEGER NOT NULL,
        actions TEXT NOT NULL,
        open INTEGER NOT NULL,
        seq INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_attention_open ON v_attention(open, since_seq);
    CREATE INDEX v_attention_seq ON v_attention(seq);
    CREATE TABLE v_attention_conflicts(workspace TEXT PRIMARY KEY, gist TEXT NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_attention_budgets(scope TEXT PRIMARY KEY, set_to TEXT NOT NULL) WITHOUT ROWID, STRICT;
    """
```

Where a human must act. A row closes in place, so a watcher hears that it went away. Each workspace whose latest
look found conflicted paths is kept, so that its row comes back after the next look that still finds them, and
what each budget scope was last set to, which setting it again replaces whole.

**`approval_asked`**

```python
@fold("approval.requested")
def approval_asked(self, event: Event) -> None: ...
```

**`approval_decided`**

```python
@fold("approval.resolved")
def approval_decided(self, event: Event) -> None: ...
```

**`agent_gone`**

```python
@fold("agent.ended")
def agent_gone(self, event: Event) -> None: ...
```

What only that agent could have settled is moot, a conflict among it, which the Ending names with the
workspace kept for it, and its messages to the person are still theirs to read but take no reply. A final
report nobody received waits for a human.

**`mention`**

```python
@fold("message.sent")
def mention(self, event: Event) -> None: ...
```

A message to a person, which a reply settles, as reading it does in the person's marks. The runtime's report
of an agent takes no reply.

**`uncertain`**

```python
@fold("effect.uncertain")
def uncertain(self, event: Event) -> None: ...
```

**`certain`**

```python
@fold("effect.finished", "effect.retried")
def certain(self, event: Event) -> None: ...
```

**`conflicted`**

```python
@fold("workspace.changed")
def conflicted(self, event: Event) -> None: ...
```

A workspace's latest look found conflicted paths, or none. The shared workspace's row is open while its
latest look found some, and an agent's comes at the end of each look of its agent's that still finds them, so
it never comes for an agent that has ended, whose stop looked last.

**`looked`**

```python
@fold("effect.finished")
def looked(self, event: Event) -> None: ...
```

An agent's conflict needs you again after each look that still finds it, while it rests on it.

**`failed`**

```python
@fold("effect.failed")
def failed(self, event: Event) -> None: ...
```

A failure is news, unless a person said so, who has nothing left to do here. An agent's next turn settles
its own. Nothing tries one of no agent's again, which only the runtime's own error or an extension's daemon
makes, as a test and a diff record their own failures.

**`dead_task`**

```python
@fold("task.died")
def dead_task(self, event: Event) -> None: ...
```

A task past its attempts is added again citing it, its `task.added`, which settles it.

**`task_again`**

```python
@fold("task.added")
def task_again(self, event: Event) -> None: ...
```

A task added citing a dead one takes its place.

**`wake_refused`**

```python
@fold("wake.refused")
def wake_refused(self, event: Event) -> None: ...
```

A wake past `max_hops`, or one a budget refused, naming the scope that refused it, and for a limit no amount
can hold, saying in its gist that it is to be removed.

**`budget_lapsed`**

```python
@fold("budget.lapsed")
def budget_lapsed(self, event: Event) -> None: ...
```

**`budget_set`**

```python
@fold("budget.set")
def budget_set(self, event: Event) -> None: ...
```

**`daemon_failed`**

```python
@fold("daemon.failed")
def daemon_failed(self, event: Event) -> None: ...
```

A daemon that fails is restarted with backoff, and one that fails on every pass leaves no other trace.

**`daemon_recovered`**

```python
@fold("daemon.recovered")
def daemon_recovered(self, event: Event) -> None: ...
```

**`restarted`**

```python
@fold("runtime.started")
def restarted(self, event: Event) -> None: ...
```

A new runtime's daemons have not failed yet.

**`turn_lost`**

```python
@fold("turn.lost")
def turn_lost(self, event: Event) -> None: ...
```

Nobody knows what a lost turn did, until its agent's next turn has looked.

**`approval_moot`**

```python
@fold("turn.ended", "turn.lost")
def approval_moot(self, event: Event) -> None: ...
```

**`turn_started`**

```python
@fold("turn.started")
def turn_started(self, event: Event) -> None: ...
```

An agent at work on its conflict is not resting on it.

**`rows`**

```python
def rows(self) -> list[dict[str, Any]]: ...
```

**`since`**

```python
def since(self, after: int) -> list[dict[str, Any]]: ...
```

### `platoon_harness.primitives.Attribution`

```python
Attribution = Literal["exact", "forked"]
```

How well an agent's model calls are tied to it: `exact` where every start of it recorded its trainable level met and
no other agent's admission names any of its backend ids, and `forked` once a native child of its harness is seen, whose
calls go on its key. Neither is None.

### `platoon_harness.primitives.Bar`

```python
class Bar(Model):
    reason: Literal["not_trainable", "shared_key", "forked", "no_end", "outside_episode", "person", "purpose"]
    refs: tuple[str, ...] = ()
    level: dict[str, Any] | None = None
```

One reason an agent, or one of its calls, cannot train, of a closed set, with the refs of the events that show
it. An agent's: `not_trainable`, a start that recorded its trainable `level` short of met, or with no ref, that no
start recorded one; `shared_key`, the spawns of other agents whose admissions name any of its backend ids, each of
which names one agent alone; `forked`, the native children seen; and `no_end`, as it has not ended. A call's:
`outside_episode`; `person`, the start of its turn, which a person held, or a person's entry its agent was handed
below it, which exposure then never answers `not_seen`; and `purpose`, a purpose its harness gave other than
`compaction`, as a call reported with none is its turn's.

### `platoon_harness.primitives.Boards`

```python
class Boards(View):
    schema = """
    CREATE TABLE v_boards(
        seq INTEGER PRIMARY KEY,
        board TEXT NOT NULL,
        name TEXT NOT NULL,
        version INTEGER NOT NULL,
        actor TEXT NOT NULL,
        gist TEXT NOT NULL,
        body TEXT,
        fields TEXT NOT NULL,
        latest INTEGER NOT NULL
    ) STRICT;
    CREATE UNIQUE INDEX v_boards_version ON v_boards(board, name, version);
    CREATE INDEX v_boards_latest ON v_boards(board, latest, seq);
    """ + ("CREATE VIRTUAL TABLE v_boards_text USING fts5(name, gist, fields);" if FTS5 else "")
```

One row per version. Text search covers names, gists and fields, never a body: a fold cannot read one, and a
tombstoned body must leave nothing behind.

**`versioned`**

```python
@fold("board.posted", "board.revised")
def versioned(self, event: Event) -> None: ...
```

**`get`**

```python
def get(self, board: str, name: str, version: int | None = None) -> sqlite3.Row | None: ...
```

One version, the latest if none is named.

**`find`**

```python
def find(
    self,
    board: str,
    *,
    prefix: str | None,
    author: str | None,
    where: dict[str, Scalar],
    text: str | None,
    history: bool,
    after: int,
    limit: int,
) -> tuple[list[sqlite3.Row], int]: ...
```

A page past `after` in commit order, and the true total, which ignores paging.

### `platoon_harness.primitives.body_of`

```python
def body_of(event: Event) -> str | None: ...
```

The body an event carries: the one its data names `body`. An event that names none has none to read on in.

### `platoon_harness.primitives.BODY_REF`

```python
BODY_REF = r"^sha256:[0-9a-f]{64}$"
```

### `platoon_harness.primitives.Boundary`

```python
Boundary = Literal["turn", "tool", "model_call"]
```

### `platoon_harness.primitives.Budgets`

```python
class Budgets(View):
    version = 4
    schema = """
    CREATE TABLE v_budgets(
        scope TEXT PRIMARY KEY,
        limits TEXT NOT NULL,
        estimate TEXT NOT NULL,
        since REAL NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_budgets_spent(
        scope TEXT NOT NULL,
        unit TEXT NOT NULL,
        amount REAL NOT NULL,
        label TEXT NOT NULL,
        unmeasured INTEGER NOT NULL,
        PRIMARY KEY (scope, unit)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_budgets_reserved(
        agent TEXT NOT NULL,
        unit TEXT NOT NULL,
        role TEXT NOT NULL,
        amount REAL NOT NULL,
        waking INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (agent, unit)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_budgets_turn(
        agent TEXT NOT NULL,
        unit TEXT NOT NULL,
        amount REAL NOT NULL,
        label TEXT NOT NULL,
        PRIMARY KEY (agent, unit)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_budgets_ended(id INTEGER PRIMARY KEY CHECK (id = 1), at REAL) STRICT;
    """
```

Limits per scope, `shared` or `role:x`. Spending is also kept per `agent:x`, for the roster, and when the session
ended, which no wall time is spent past.

**`limits_set`**

```python
@fold("budget.set")
def limits_set(self, event: Event) -> None: ...
```

**`session_ending`**

```python
@fold("session.closed", "session.cancelled")
def session_ending(self, event: Event) -> None: ...
```

**`session_stopped`**

```python
@fold("session.stopped")
def session_stopped(self, event: Event) -> None: ...
```

A session that was closing or cancelled has ended once its owner stops, as nothing more of it will run.

**`session_ended`**

```python
def session_ended(self) -> float | None: ...
```

When the session ended, or None while more of it can run.

**`reserved`**

```python
@fold("budget.reserved")
def reserved(self, event: Event) -> None: ...
```

**`turn_coming`**

```python
@fold("agent.woken", "turn.started")
def turn_coming(self, event: Event) -> None: ...
```

A reservation is a wake's until its turn starts, and only a wake's can come back when a handover fails.

**`usage`**

```python
@fold("usage.reported")
def usage(self, event: Event) -> None: ...
```

A unit with no amount still says how well the turn is known, when its label says it is not known whole.

**`reconciled`**

```python
@fold("budget.reconciled")
def reconciled(self, event: Event) -> None: ...
```

**`started`**

```python
@fold("agent.started")
def started(self, event: Event) -> None: ...
```

**`lost`**

```python
@fold("turn.lost")
def lost(self, event: Event) -> None: ...
```

Nobody measured a lost turn whole, whatever it reported, so it is charged as any such turn is.

**`wake_failed`**

```python
@fold("effect.failed", "effect.cancelled")
def wake_failed(self, event: Event) -> None: ...
```

**`ended`**

```python
@fold("agent.ended")
def ended(self, event: Event) -> None: ...
```

**`spent`**

```python
def spent(self, scope: str, unit: str) -> tuple[float, str, int]: ...
```

The amount spent, its weakest label, and how many turns went unmeasured.

**`held`**

```python
def held(self, scope: str, unit: str) -> float: ...
```

What is reserved in a scope and not yet reconciled.

**`reservation`**

```python
def reservation(self, agent: str) -> dict[str, float]: ...
```

**`turn_usage`**

```python
def turn_usage(self, agent: str) -> dict[str, tuple[float, str]]: ...
```

**`estimate`**

```python
def estimate(self, role: str | None = None) -> dict[str, float]: ...
```

One turn's estimate: the shared one, with a role's own over it.

**`check`**

```python
def check(self, role: str, wanted: dict[str, float], now: float) -> None: ...
```

Refuse `over_budget` past a limit, and `unavailable` when what a limit holds on has no amount, each naming
the scope and the unit.

**`exhausted`**

```python
def exhausted(self, now: float) -> bool: ...
```

Whether the shared budget has run out, which stops every kind of session. A reservation spends nothing.

**`status`**

```python
def status(self, now: float) -> list[dict[str, Any]]: ...
```

Each limit and what is spent against it, which for `wall` is the time since it was set, up to when the
session ended, once it has.

**`usage_of`**

```python
def usage_of(self, scope: str) -> dict[str, dict[str, Any]]: ...
```

What `shared` or one `agent:x` has spent, with labels and how many turns nobody measured whole: a unit no
amount could be stated for has none.

### `platoon_harness.primitives.CallEligibility`

```python
class CallEligibility(Model):
    call: str
    call_id: str | None
    purpose: str | None
    attribution: Attribution | None
    verdict: Verdict
    reasons: tuple[Bar, ...]
```

One model call its agent's harness reported, by the ref of its `model.called`, with the id and the purpose it
gave. Its attribution is its agent's, and it is eligible when its agent is and it has no bar of its own.

### `platoon_harness.primitives.Calls`

```python
class Calls(View):
    schema = """
    CREATE TABLE v_calls(
        agent TEXT NOT NULL, call_id TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (agent, call_id)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_calls_items(
        agent TEXT NOT NULL, native_id TEXT NOT NULL, seq INTEGER NOT NULL, call_id TEXT, PRIMARY KEY (agent, native_id)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_calls_turns(
        agent TEXT NOT NULL, seq INTEGER NOT NULL, by TEXT, PRIMARY KEY (agent, seq)
    ) WITHOUT ROWID, STRICT;
    """
```

What each agent's harness reported of its model calls, by the id it gave each, of its tool items, by theirs,
and where each of its turns began and who drove it.

**`called`**

```python
@fold("model.called")
def called(self, event: Event) -> None: ...
```

**`item`**

```python
@fold("item.recorded")
def item(self, event: Event) -> None: ...
```

A tool item is found by its first report, and names the call its harness said made it in any report.

**`turn`**

```python
@fold("turn.started")
def turn(self, event: Event) -> None: ...
```

**`item_for`**

```python
def item_for(self, agent: str, native_id: str) -> sqlite3.Row | None: ...
```

**`call`**

```python
def call(self, agent: str, call_id: str) -> int | None: ...
```

**`began`**

```python
def began(self, agent: str, upto: int) -> sqlite3.Row | None: ...
```

The start of an agent's latest turn at or below `upto`.

### `platoon_harness.primitives.Capabilities`

```python
class Capabilities(Model):
    persistent: bool = False
    resume: bool = False
    boundaries: frozenset[Boundary] = frozenset()
    tool_paths: frozenset[Literal["mcp-http", "mcp-stdio", "shell"]] = frozenset()
    tool_names: Literal["namespaced", "bare"] = "namespaced"
    tool_timeout_s: float | None = None
    interrupt: bool = False
    approvals: Literal["none", "gated", "native"] = "none"
    native_children: Literal["none", "observed", "opaque"] = "none"
    native_children_off: bool = False
    call_ids: Literal["none", "agent", "call"] = "none"
    dialects: frozenset[Literal["chat", "responses", "messages"]] = frozenset()
    coverage: Mapping[Surface, Literal["observed", "partial", "none"]] = {}
    measures: frozenset[Literal["tokens", "usd"]] = frozenset()
    sandboxes: frozenset[str] = frozenset()
    sealed: bool = False
```

What a driver declares of a harness. Absence means unsupported, and `levels` believes only what was verified.
`native_children_off` says it turns the harness's own agents off for a launch whose role does not allow them, so a
role on a harness with agents of its own that its driver cannot turn off must allow them. `sealed` says it launches
on a gateway's access with nothing of the user's, which is the one launch a gateway admission gets.

### `platoon_harness.primitives.Changes`

```python
class Changes(View):
    version = 3
    schema = """
    CREATE TABLE v_changes(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        workspace TEXT,
        row TEXT NOT NULL,
        open INTEGER NOT NULL,
        seq INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_changes_seq ON v_changes(seq);
    CREATE INDEX v_changes_workspace ON v_changes(workspace, kind);
    """
```

What changed, as looks found it, a row for each recorded commit, with the seq that `recorded` it, its `tests`,
the outcome of the latest runtime test at it, or None while none ran, and that test's `tested` ref, `tests_why` and
`tests_exit` where it has them, so a client says why it failed and can open its record; for each workspace's last
reading; and for each path it holds uncommitted, keyed by `id`, each with the `seq` that last moved it, which a
client compares with the person's mark on `repo/<name>`. A newer reading replaces its workspace's paths whole, and a
row closes in place, so a watcher hears that it went away.

**`committed`**

```python
@fold("repo.committed")
def committed(self, event: Event) -> None: ...
```

**`rewritten`**

```python
@fold("repo.rewritten")
def rewritten(self, event: Event) -> None: ...
```

**`tested`**

```python
@fold("repo.tested")
def tested(self, event: Event) -> None: ...
```

**`changed`**

```python
@fold("workspace.changed")
def changed(self, event: Event) -> None: ...
```

A path whose row says the same as before keeps the seq that last moved it, so it is not news again. A
reading that recorded no uncommitted state, as of your checkout when no role works in it, shows nothing.

**`rows`**

```python
def rows(self) -> list[dict[str, Any]]: ...
```

**`since`**

```python
def since(self, after: int) -> tuple[list[dict[str, Any]], list[str]]: ...
```

The rows that moved past `after`, and the keys of those that went away.

### `platoon_harness.primitives.channel_grants`

```python
def channel_grants(kind: str, name: str, *, write: bool) -> list[tuple[str, str]]: ...
```

The `(ops, on)` pairs that writing or reading one channel takes. Whoever reads a channel may wait on it, and
whoever adds to a queue may wait on its tasks.

### `platoon_harness.primitives.Channels`

```python
class Channels(View):
    schema = "CREATE TABLE v_channels(stream TEXT PRIMARY KEY, settings TEXT NOT NULL) WITHOUT ROWID, STRICT;"
```

Every channel. An agent's inbox is one, made at spawn from its role.

**`created`**

```python
@fold("channel.created")
def created(self, event: Event) -> None: ...
```

**`inbox`**

```python
@fold("agent.spawned")
def inbox(self, event: Event) -> None: ...
```

A spawn is its spawner's event, so the child is the one it names.

**`get`**

```python
def get(self, stream: str) -> Channel | None: ...
```

**`require`**

```python
def require(self, stream: str) -> Channel: ...
```

**`listed`**

```python
def listed(self) -> list[Channel]: ...
```

### `platoon_harness.primitives.ChildSeen`

```python
class ChildSeen(Args):
    type: Literal["child.seen"] = "child.seen"
    native: str
    parent: str | None = None
```

A native child the harness made on its own, which stays on its parent's credential: its native id, and the tool
call of its parent's that started it. How well a call is tied to an agent is the record's to say, so no driver
claims it.

### `platoon_harness.primitives.cited`

```python
def cited(txn: Txn, refs: Iterable[str]) -> tuple[str, ...]: ...
```

`based_on` as its citer gave it, once each ref names an event and each range lines of that event's text body,
or a refusal of the whole write naming the first that does not. A body in `blobs/`, which an op cannot read, keeps
its range as given. Whether the citer was handed what it cites is exposure's to say, so that is not checked here,
and a citation says only whether an event exists, never what it holds. One that cannot fit an event is refused
before any is looked at, and each ref, each event and each body is looked at once.

### `platoon_harness.primitives.Compacted`

```python
class Compacted(Args):
    type: Literal["compacted"] = "compacted"
    forgotten: tuple[str, ...] | BodyRef | None = None
    summary: str | None = None
```

A harness compacted its context. `forgotten` holds the native ids of what left it, None if nobody can say, and
`summary` the text that took its place. Each is that until the host stores it and journals the hash.

### `platoon_harness.primitives.Condition`

```python
class Condition(Args):
    stream: Annotated[str, Field(max_length=512)]
    types: tuple[str, ...] = ()
    n: Annotated[int, Field(ge=1)] | tuple[str, ...] = 1
    distinct: Literal["actor", "agent", "correlation"] | None = None
```

`on(stream, types, n, distinct)`: join, wait-any, version watch and barrier are this one condition.

`n` counts events. With `distinct`, naming an envelope field, it counts different values, and a tuple names which.

### `platoon_harness.primitives.Contributors`

```python
class Contributors(Model):
    rows: tuple[Contributor, ...]
    handed_only: tuple[HandedOnly, ...]
    walked: int
    stopped_short: bool
    cursor: str | None
    head: int
    open: bool
```

Each maker a walk back from an outcome along citations, causes and ancestry reaches, in the order it reached
them, the outcome's own first, and apart from them each maker whose work was only handed to one of them. It walks
at most 4096 events, `walked` of them, and says when it `stopped_short`. It is reachability in the record and never
credit: nobody is weighed or ranked.

### `platoon_harness.primitives.Counters`

```python
class Counters(View):
    schema = """
    CREATE TABLE v_counters(type TEXT PRIMARY KEY, events INTEGER NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_counters_refused(code TEXT PRIMARY KEY, events INTEGER NOT NULL) WITHOUT ROWID, STRICT;
    """
```

How many events of each type the journal holds, and of the refusals among them how many of each code, counted as
each commits, so reading them walks nothing and writes nothing.

**`counted`**

```python
@fold("*")
def counted(self, event: Event) -> None: ...
```

**`by_type`**

```python
def by_type(self) -> dict[str, int]: ...
```

**`refused`**

```python
def refused(self) -> dict[str, int]: ...
```

### `platoon_harness.primitives.Cursor`

```python
class Cursor(NamedTuple):
    offered: int = 0
    delivered: int = 0
    acked: int = 0
    closed: bool = False
    shown: int = 0
```

A reader's place in one stream, as seqs. `offered` steps back only when a handover failed, and `shown` is how far
a tool's result took it, which unlike a handover needs no confirming.

**`state_of`**

```python
def state_of(self, seq: int) -> str: ...
```

Where one entry stands for this reader. None of these means understood.

### `platoon_harness.primitives.CUT_OFF`

```python
CUT_OFF = {"lost": "a crash", OWNER_STOP: "the owner stopping the session"}
```

The reasons only the runtime can give a turn, each with what cut that turn off, as a notice says it.

### `platoon_harness.primitives.Deliveries`

```python
class Deliveries(View):
    version = 12
    schema = """
    CREATE TABLE v_deliveries(
        seq INTEGER PRIMARY KEY,
        stream TEXT NOT NULL,
        version INTEGER NOT NULL,
        ref TEXT NOT NULL,
        delivery TEXT NOT NULL,
        due REAL NOT NULL,
        entry TEXT NOT NULL,
        answers INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX v_deliveries_stream ON v_deliveries(stream, seq);
    CREATE INDEX v_deliveries_ref ON v_deliveries(ref, seq);
    CREATE TABLE v_deliveries_audience(
        reader TEXT NOT NULL,
        stream TEXT NOT NULL,
        seq INTEGER NOT NULL,
        PRIMARY KEY (reader, stream, seq)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_cursors(
        reader TEXT NOT NULL,
        stream TEXT NOT NULL,
        offered INTEGER NOT NULL DEFAULT 0,
        delivered INTEGER NOT NULL DEFAULT 0,
        acked INTEGER NOT NULL DEFAULT 0,
        closed INTEGER NOT NULL DEFAULT 0,
        shown INTEGER NOT NULL DEFAULT 0,
        offer INTEGER,
        PRIMARY KEY (reader, stream)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_offers(
        input INTEGER PRIMARY KEY,
        reader TEXT NOT NULL,
        how TEXT NOT NULL,
        anchor TEXT,
        positions TEXT NOT NULL,
        before TEXT NOT NULL,
        effect INTEGER,
        delivered INTEGER NOT NULL,
        taken INTEGER NOT NULL DEFAULT 0,
        hops INTEGER NOT NULL,
        asked INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX v_deliveries_offers_effect ON v_deliveries_offers(effect);
    CREATE INDEX v_deliveries_offers_anchor ON v_deliveries_offers(reader, anchor) WHERE delivered = 0;
    CREATE TABLE v_deliveries_heard(agent TEXT PRIMARY KEY, hops INTEGER NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_blocked(agent TEXT PRIMARY KEY, why TEXT NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_quiet(agent TEXT PRIMARY KEY, upto INTEGER NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_launch(agent TEXT PRIMARY KEY, input INTEGER NOT NULL) WITHOUT ROWID, STRICT;
    """
```

Entries, the audience each one recorded, and a cursor per `(reader, stream)`, held here and not by readers. A
cursor keeps the offer that last moved it on, so a read that finds nothing new can say what that offer handed
over.

**`sent`**

```python
@fold("message.sent")
def sent(self, event: Event) -> None: ...
```

A report answers unless an interrupt or the owner's stop cut its turn. A v1 report answered whatever it
said. An entry before v3 carried nothing, so it is shown by its own ref.

**`offered`**

```python
@fold("context.offered")
def offered(self, event: Event) -> None: ...
```

An offer is kept with the anchor of the call it was made under, as the tool item that answers that call
confirms it. A launch hands over no entry, so it is heard as nothing.

**`instructed`**

```python
@fold("agent.instructed")
def instructed(self, event: Event) -> None: ...
```

Each launch and each resume is instructed, so a launch offer made before is a process's that has gone, and no
input to the one that follows can confirm it.

**`handing_over`**

```python
@fold("effect.requested")
def handing_over(self, event: Event) -> None: ...
```

**`taken`**

```python
@fold("effect.finished")
def taken(self, event: Event) -> None: ...
```

The harness has it, which says nothing of whether it will land.

**`handover_failed`**

```python
@fold("effect.failed", "effect.cancelled")
def handover_failed(self, event: Event) -> None: ...
```

What never reached the harness, by a handover that failed or one cancelled before it started, is queued
again. Its reservation has come back too, so a refused wake gets another try.

**`stopped_short`**

```python
@fold("turn.ended", "turn.lost", "agent.resumed")
def stopped_short(self, event: Event) -> None: ...
```

What a harness took and never landed is queued again when its turn stops short, or when it comes back from
a crash, as none of them keeps it for certain. One that stopped on its own lands it in the turn that follows.

**`delivered`**

```python
@fold("context.delivered")
def delivered(self, event: Event) -> None: ...
```

Its offer's hops count in the turn it landed in too, which for a steer can be the one after the offer's. A v1
landing carried none: its offer's counted alone. An offer shown in a tool's result moved its cursors and counted
when it was shown, and a launch hands over no entry, so their confirmations move nothing else. One before v3
was always of a handover.

**`acked`**

```python
@fold("message.acked")
def acked(self, event: Event) -> None: ...
```

**`turn_over`**

```python
@fold("turn.ended", "turn.lost")
def turn_over(self, event: Event) -> None: ...
```

**`reader_gone`**

```python
@fold("agent.ended")
def reader_gone(self, event: Event) -> None: ...
```

**`restored`**

```python
@fold("wake.restored")
def restored(self, event: Event) -> None: ...
```

Entries are named by seq, since one carrying another event's words is shown by that event's ref. A v1
restore named each by its own ref.

**`quieted`**

```python
@fold("wake.quieted")
def quieted(self, event: Event) -> None: ...
```

An interrupt: what came before it wakes its reader no more, and waits for the next turn.

**`refused`**

```python
@fold("wake.refused")
def refused(self, event: Event) -> None: ...
```

**`unblocked`**

```python
@fold("budget.set", "budget.reconciled", "agent.ended", "turn.lost")
def unblocked(self, event: Event) -> None: ...
```

Whatever moved the budget may have made room, so every refused wake gets one more try.

**`cursor`**

```python
def cursor(self, reader: str | None, stream: str) -> Cursor: ...
```

**`holds`**

```python
def holds(self, stream: str, ref: str) -> bool: ...
```

Whether an entry on `stream` is shown by `ref`.

**`handed`**

```python
def handed(self, reader: str, stream: str) -> tuple[int, list[Entry]]: ...
```

What the offer that last moved a reader's cursor on `stream` handed over there, and the cursor before it,
unless that offer was a read of the reader's own, which showed what it gave.

**`entries`**

```python
def entries(self, stream: str, reader: str | None, after: int, *, whole: bool) -> Iterator[Entry]: ...
```

What `reader` may see past `after`. `whole` is the stream, else only entries whose audience held it.

**`shown_by`**

```python
def shown_by(self, ref: str) -> list[Entry]: ...
```

The entries readers were shown by `ref`, newest first. A goal told again after each of two crashes is two.

**`addressed`**

```python
def addressed(self, reader: str, stream: str, seq: int) -> bool: ...
```

Whether an entry's recorded audience held this reader.

**`entries_at`**

```python
def entries_at(self, seqs: Sequence[int]) -> list[Entry]: ...
```

**`depth`**

```python
def depth(self, reader: str, stream: str) -> int: ...
```

Entries still to reach the reader, which is what an inbox cap counts. One a driver confirmed has reached it,
so a harness whose tools are hidden never reads, and its inbox still drains.

**`queued`**

```python
def queued(self, reader: str, modes: Sequence[str]) -> tuple[list[Entry], int]: ...
```

The oldest entries an offer in these modes hands over, and how many there are in all: on each stream, all up
to the newest of those modes, since a cursor cannot pass one left out.

**`waking`**

```python
def waking(self) -> list[tuple[str, float, bool]]: ...
```

Readers with something that may wake them: when it falls due, and whether any of it may steer.

**`answers_queued`**

```python
def answers_queued(self, reader: str) -> list[Entry]: ...
```

The reports of children that answer and wait for this reader's next turn.

**`unread`**

```python
def unread(self, reader: str) -> int: ...
```

**`waiting`**

```python
def waiting(self, reader: str, limit: int) -> list[dict[str, Any]]: ...
```

What `unread` counts, oldest first, each entry with how it would land for this reader now.

**`stops`**

```python
def stops(self, reader: str, shown: Sequence[Entry], *, whole: bool = False) -> dict[str, int]: ...
```

How far each cursor may move for `shown`: up to the first entry left out, and never past it.

**`heard`**

```python
def heard(self, agent: str | None) -> int: ...
```

The largest hops offered to this agent's turn or landed in it, or -1 when nothing has been.

**`blocked`**

```python
def blocked(self, agent: str) -> str | None: ...
```

**`any_blocked`**

```python
def any_blocked(self) -> bool: ...
```

Whether a budget has refused a wake that nothing has given another try.

**`offer`**

```python
def offer(self, input: int) -> Offered | None: ...
```

**`unconfirmed`**

```python
def unconfirmed(self, reader: str, anchor: str) -> list[int]: ...
```

The offers to `reader` made under the call `anchor` names that its harness has not said it took, oldest
first.

**`unlanded`**

```python
def unlanded(self, reader: str) -> bool: ...
```

Whether the harness of `reader` took a handover it has not said landed, which a turn that stopped on its own
lands in the turn that follows.

**`launch`**

```python
def launch(self, reader: str) -> int | None: ...
```

The offer that launched the harness `reader` runs now, while its harness has not said it took any input.

### `platoon_harness.primitives.Delta`

```python
class Delta(Args):
    type: Literal["delta"] = "delta"
    text: str
```

Live text. It is lossy and never journaled: the `item` that follows is authoritative.

### `platoon_harness.primitives.Eligibility`

```python
class Eligibility(Model):
    agent: str
    episode: str
    attribution: Attribution | None
    verdict: Verdict
    reasons: tuple[Bar, ...]
    calls: tuple[CallEligibility, ...]
    total: int
    cursor: str | None
    head: int
```

Whether an agent's work in one episode can train: its attribution, and its verdict with every bar, eligible when
there is none, and a page of its calls, oldest first, `total` of them, with `cursor` to pass as `after` for the next
page. `head` is where the record was read.

### `platoon_harness.primitives.Entry`

```python
class Entry(BaseModel, frozen=True):
    seq: int
    ref: str
    stream: str
    sender: str
    gist: str
    body: str | None = None
    thread: str | None = None
    reply_to: str | None = None
    hops: int = 0
    subject: str | None = None
```

One message on `stream`. `ref` is what readers are shown it by: its own, or that of the event whose words it
carries. `sender` is an address to reply to, or `runtime`, and `body` the hash of any body, which no reader sees.

**`shown`**

```python
def shown(self) -> dict[str, Any]: ...
```

The entry as a reader gets it, saying whether it has a body, which `blob.get` reads by its ref.

### `platoon_harness.primitives.Exited`

```python
class Exited(Args):
    type: Literal["exited"] = "exited"
    reason: str = "the harness exited"
```

### `platoon_harness.primitives.Exposure`

```python
Exposure = Annotated[Seen | NotSeen | Unknown, Field(discriminator="answer")]
```

What `exposure` answers: never a boolean.

### `platoon_harness.primitives.Exposures`

```python
class Exposures(View):
    schema = """
    CREATE TABLE v_exposures(
        offer INTEGER NOT NULL,
        item INTEGER NOT NULL,
        agent TEXT NOT NULL,
        stream TEXT,
        version INTEGER,
        ref TEXT NOT NULL,
        form TEXT NOT NULL,
        PRIMARY KEY (offer, item)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_exposures_event ON v_exposures(stream, version, agent, offer);
    CREATE TABLE v_exposures_offers(
        offer INTEGER PRIMARY KEY,
        ref TEXT NOT NULL,
        agent TEXT NOT NULL,
        how TEXT NOT NULL,
        key TEXT,
        anchor TEXT,
        v INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX v_exposures_offers_agent ON v_exposures_offers(agent, offer);
    CREATE TABLE v_exposures_confirmed(
        offer INTEGER PRIMARY KEY,
        ref TEXT NOT NULL,
        agent TEXT NOT NULL,
        seq INTEGER NOT NULL,
        turn TEXT,
        boundary TEXT,
        evidence TEXT,
        native_id TEXT
    ) STRICT;
    CREATE INDEX v_exposures_confirmed_agent ON v_exposures_confirmed(agent, seq);
    CREATE TABLE v_exposures_compactions(
        seq INTEGER PRIMARY KEY,
        ref TEXT NOT NULL,
        agent TEXT NOT NULL,
        forgotten TEXT
    ) STRICT;
    CREATE INDEX v_exposures_compactions_agent ON v_exposures_compactions(agent, seq);
    CREATE TABLE v_exposures_starts(
        seq INTEGER PRIMARY KEY,
        agent TEXT NOT NULL,
        coverage TEXT NOT NULL,
        levels TEXT NOT NULL,
        assurance TEXT
    ) STRICT;
    CREATE INDEX v_exposures_starts_agent ON v_exposures_starts(agent, seq);
    """
```

What the runtime offered each agent, item by item, what its harness said it took, its compactions and its starts.
A fold sees one event, so an offered event's maker is found by its ref when an answer needs it.

**`offered`**

```python
@fold("context.offered")
def offered(self, event: Event) -> None: ...
```

An offer before payload 3 named a body by its hash, which names no event, so that item has no stream.

**`delivered`**

```python
@fold("context.delivered")
def delivered(self, event: Event) -> None: ...
```

The first confirmation of an offer is the one: a repeat is never written now, and a v1 one changed nothing.
One before payload 3 may name less, and what it does not name stays unknown.

**`compacted`**

```python
@fold("context.compacted")
def compacted(self, event: Event) -> None: ...
```

**`started`**

```python
@fold("agent.started", "agent.resumed")
def started(self, event: Event) -> None: ...
```

A start before assurance was recorded names none.

**`handed`**

```python
def handed(self, agent: str, stream: str, version: int) -> bool: ...
```

Whether an event was ever offered to an agent, whatever an offer showed of it.

**`offers_of`**

```python
def offers_of(
    self, agent: str, stream: str, version: int, bound: int, *, confirmed: bool
) -> tuple[list[sqlite3.Row], int]: ...
```

The offers of one event to an agent made below `bound` that its harness said it took below it, each with that
report, or those it did not, oldest first and as many as a page holds, and how many there are in all.

**`shown`**

```python
def shown(self, offer: int, stream: str | None = None, version: int | None = None) -> list[sqlite3.Row]: ...
```

What an offer showed, of one event or of all it named.

**`history`**

```python
def history(self, agent: str, bound: int, before: int) -> list[sqlite3.Row]: ...
```

An agent's offers below `bound` and `before`, newest first, as many as a page holds and one more, each with
its confirmation when that was reported below `bound`.

**`counts`**

```python
def counts(self, agent: str, bound: int) -> tuple[int, int]: ...
```

How many offers were made to an agent below `bound`, and how many its harness said it took there.

**`older`**

```python
def older(self, agent: str, bound: int) -> int: ...
```

How many offers below `bound` came before offer payload 3.

**`compactions`**

```python
def compactions(self, agent: str, after: int, before: int) -> tuple[list[sqlite3.Row], int]: ...
```

An agent's compactions between two seqs, oldest first and as many as a page holds, and how many in all.

**`start`**

```python
def start(self, agent: str, bound: int) -> sqlite3.Row | None: ...
```

An agent's latest start or resume below `bound`.

**`readers`**

```python
def readers(self, stream: str, version: int) -> list[sqlite3.Row]: ...
```

Each agent an event was offered to, by its first offer, and whether its harness said it took any.

**`events_offered`**

```python
def events_offered(self, agent: str, bound: int) -> list[sqlite3.Row]: ...
```

Each event offered to an agent below `bound`, by its first offer, oldest first.

**`ref_of`**

```python
def ref_of(self, offer: int) -> str: ...
```

### `platoon_harness.primitives.GAPS`

```python
GAPS: Mapping[Gap, Kind] = {
    "stream_lost": Kind("control", ("driver",), carries=True),
    "compaction_opaque": Kind("control", ("runtime",), carries=False),
    "native_child_unattributed": Kind("model", ("driver",), carries=True),
    "usage_lower_bound": Kind("model", ("driver",), carries=False),
    "unknown_update": Kind("control", ("driver", "runtime"), carries=True),
    "hidden_call": Kind("model", ("driver",), carries=True),
    "crash_window": Kind("control", ("driver", "runtime"), carries=True),
    "hold": Kind("control", ("runtime",), carries=True),
    "workspace_unobserved": Kind("control", ("runtime",), carries=True),
}
```

Every gap a `gap.recorded` can name, and what each is.

### `platoon_harness.primitives.Gap`

```python
Gap = Literal[
    "stream_lost",
    "compaction_opaque",
    "native_child_unattributed",
    "usage_lower_bound",
    "unknown_update",
    "hidden_call",
    "crash_window",
    "hold",
    "workspace_unobserved",
]
```

### `platoon_harness.primitives.GapReport`

```python
class GapReport(Args):
    type: Literal["gap"] = "gap"
    what: Gap
```

A gap a driver saw. Its plane is the gap's own.

### `platoon_harness.primitives.Gaps`

```python
class Gaps(View):
    version = 2
    schema = """
    CREATE TABLE v_gaps(
        seq INTEGER PRIMARY KEY,
        agent TEXT NOT NULL,
        what TEXT NOT NULL,
        plane TEXT NOT NULL,
        began INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX v_gaps_began ON v_gaps(agent, began, seq);
    """
```

Every incident gap by its agent and where it `began`: where it stands, or the `since` that a gap recorded after
the fact names. An ending counts them by agent and kind, and an answer takes those below its bound.

**`recorded`**

```python
@fold("gap.recorded")
def recorded(self, event: Event) -> None: ...
```

A v1 gap named no `since`.

**`turn_lost`**

```python
@fold("turn.lost")
def turn_lost(self, event: Event) -> None: ...
```

A v1 lost turn named its gap itself. From v2 it is a `gap.recorded` beside it.

**`rows`**

```python
def rows(self) -> list[dict[str, Any]]: ...
```

How many gaps of each kind each agent has, as an ending states them.

**`below`**

```python
def below(
    self, agent: str, bound: int, *, besides: Collection[str] = (), before: tuple[int, int] | None = None
) -> tuple[list[sqlite3.Row], int]: ...
```

An agent's gaps but those of the kinds `besides` that began below `bound`, newest first by where they began
and going back past `before`, as many as a page holds and one more, and how many began below `bound` in all.

**`counted`**

```python
def counted(self, agent: str, bound: int, *, besides: Collection[str] = ()) -> dict[str, int]: ...
```

How many of an agent's gaps but those of the kinds `besides` began below `bound`, by kind.

**`held`**

```python
def held(self, head: int, *, besides: Collection[str] = ()) -> dict[str, dict[str, int]]: ...
```

How many gaps but those of the kinds `besides` the record held of each agent at `head`, by agent and kind.

### `platoon_harness.primitives.Groups`

```python
class Groups(View):
    schema = """
    CREATE TABLE v_groups(name TEXT PRIMARY KEY, rule TEXT NOT NULL) WITHOUT ROWID, STRICT;
    """
```

Named membership rules. A group's generation is the version of its stream.

**`changed`**

```python
@fold("group.changed")
def changed(self, event: Event) -> None: ...
```

**`get`**

```python
def get(self, name: str) -> Group: ...
```

**`listed`**

```python
def listed(self) -> list[Group]: ...
```

### `platoon_harness.primitives.hold_open`

```python
async def hold_open(kernel: Kernel, placed: dict[str, Any]) -> dict[str, Any]: ...
```

Keep a `wait` call open as a tool surface does, given its `pending` result. It returns how the wait stands: the
way it closed, or `pending` with the wait still registered, so the agent may call again or end its turn.

A wait that holds comes back `released` and still open: the surface closes it with `wait.release{told}` once its
answer has left, so an answer that is lost costs no wake. While a stop of a child of its waiter's is under way, it
is not said to hold, as nothing reaches that waiter until the stop has finished. The call was authorized when it was
placed, so this asks as the runtime.

### `platoon_harness.primitives.IN_A_RESULT`

```python
IN_A_RESULT = ("read", "notice")
```

### `platoon_harness.primitives.Injection`

```python
Injection = Literal["pull", "next-turn", "wake", "steer"]
```

### `platoon_harness.primitives.InputDelivered`

```python
class InputDelivered(Args):
    type: Literal["input.delivered"] = "input.delivered"
    input: Short
    boundary: Boundary
    evidence: str | None = None
    native_id: Short | None = None
```

A delivery reached the harness. `evidence` names what showed it, which is what makes this observed exposure, and
`native_id` is the harness's own id for what landed.

### `platoon_harness.primitives.Interactions`

```python
class Interactions(Model):
    pairs: tuple[Pair, ...]
    total: int
    unknowns: tuple[Unknowns, ...]
    cursor: str | None
    head: int
    open: bool
```

Who reached whom, as the record held it at `head`: a page of pairs, oldest first by the first edge the record
learned of each, `total` of them, and of the agents spawned by then, in the order they were, with each one's
`unknowns`, and `cursor` to pass as `after` for the next page, read at the same head, until both are through. It is
`open` while an offer a pair counts as unconfirmed went to an agent that had not ended there, whose harness can
still say it took it. It counts reach in the record and never weighs it: nothing here is credit or influence.

### `platoon_harness.primitives.Item`

```python
class Item(Args):
    type: Literal["item"] = "item"
    kind: Literal["message", "thought", "tool", "patch"]
    gist: Gist
    phase: Literal["started", "completed"] | None = None
    native_id: Short | None = None
    call_id: Short | None = None
    body: str | None = None
    approval: Name | None = None
    outcome: str | None = None
```

One thing a harness did or began. A tool or a patch is `started` while under way, so `activity` can say what is
running, then `completed`, and a message or a thought has no `phase`. `approval` names the approval an outcome
answers. `call_id` names the model call that made it, when the harness says so. `body` is its whole text until the
host stores it and journals the hash.

### `platoon_harness.primitives.Kept`

```python
class Kept(BaseModel, frozen=True):
    path: str
    host: str | None
    branch: str | None
    bytes: int | None
    why: tuple[str, ...]
    release: tuple[str, ...] = ()
```

A workspace its agent's stop left in place, on `host` at `path`, on `branch`, taking `bytes` on disk, and `why`:
what removing it would lose, or why that could not be told. `release` is the commands that let it go and lose
nothing it was kept for but the ignored files `why` names, and is empty when no commands would: then `why` says
what to save first.

### `platoon_harness.primitives.Lineage`

```python
class Lineage(Model):
    event: Node
    made: Made
    declared: tuple[Declared, ...]
    unresolved: tuple[Unresolved, ...]
    cut: int
    cause: tuple[Step, ...]
    ancestry: tuple[Step, ...]
    standing: tuple[Coverage, ...] | None
    history: tuple[Annotated[Offer | Incident, Field(discriminator="kind")], ...] | None
    totals: dict[str, int] | None
    cursor: str | None
    bound: Bound
    head: int
    open: bool
```

One hop back from an event: the `event`, who `made` it, what it `declared`, a commit's `unresolved` trailers and
how many more it had than were kept (`cut`), each `cause`, its `ancestry`, its maker's `standing` coverage, and a
page of what its maker was offered and the gaps in its record below the bound, `history`, newest first, with true
`totals`. A maker that is no agent has no context, so those three are None.

### `platoon_harness.primitives.Lines`

```python
class Lines(NamedTuple):
    text: str | None
    total: int
    range: str = ""
    rest: str | None = None
```

What a result can show of a text body. `text` is None if one line alone will not fit, `total` counts every line,
`range` is `#L<first>-<last>` unless this is the whole body, and `rest` is the ref of the lines after these.

**`shown`**

```python
def shown(self) -> dict[str, Any]: ...
```

### `platoon_harness.primitives.lines_of`

```python
def lines_of(body: str, text: str, wanted: str | None, room: int) -> Lines: ...
```

The lines of `wanted` that fit in `room`, from the text of the body whose ref is `body`. A range no line stands
in is refused with how many there are.

### `platoon_harness.primitives.Looks`

```python
class Looks(View):
    version = 4
    schema = """
    CREATE TABLE v_looks(workspace TEXT PRIMARY KEY, reading TEXT NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_looks_commits(
        sha TEXT PRIMARY KEY, ref TEXT NOT NULL, isolated TEXT, found_in TEXT
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_looks_isolated(workspace TEXT PRIMARY KEY) WITHOUT ROWID, STRICT;
    CREATE TABLE v_looks_diffs(sha TEXT PRIMARY KEY, effect INTEGER NOT NULL, ref TEXT) WITHOUT ROWID, STRICT;
    """
```

Each workspace's last look, which the next one starts from, every isolated workspace, the ref of each commit the
journal holds, with the workspace it was `found_in` and the isolated workspace that confines its code: that one
where it was found, or an isolated commit the journal holds that it is built on, and each commit's diff: the
`effect` asked to read it, then the `ref` of its patch once kept.

**`asked`**

```python
@fold("effect.requested")
def asked(self, event: Event) -> None: ...
```

**`diffed`**

```python
@fold("repo.diffed")
def diffed(self, event: Event) -> None: ...
```

A record that says why it could not be read holds no patch, so the next ask reads again.

**`made`**

```python
@fold("effect.finished")
def made(self, event: Event) -> None: ...
```

**`committed`**

```python
@fold("repo.committed")
def committed(self, event: Event) -> None: ...
```

A commit's code runs only in an isolation when the look that found it was of an isolated workspace, which is
where its code is, or when a parent the journal holds is confined. Attribution does not decide this, since an
isolated agent writes its own reflog. A commit's parents the journal holds are recorded before it.

**`changed`**

```python
@fold("workspace.changed")
def changed(self, event: Event) -> None: ...
```

**`ref`**

```python
def ref(self, sha: str) -> str | None: ...
```

The ref of the event that recorded a commit, or None while the journal holds none.

**`named`**

```python
def named(self, given: str) -> list[sqlite3.Row]: ...
```

The recorded commits whose SHA begins with `given`, two at most, as one is all a name may name.

**`isolated`**

```python
def isolated(self, sha: str) -> sqlite3.Row | None: ...
```

A recorded commit's `isolated` workspace, the one that confines its code, and the workspace it was
`found_in`, or None for a commit the journal does not hold. `isolated` is None for one whose code may leave
every isolation, equals `found_in` for one found in an isolated workspace, and names an ancestor's for one
built on an isolated commit.

**`diff`**

```python
def diff(self, sha: str) -> sqlite3.Row | None: ...
```

A commit's diff: the `effect` last asked to read it and the `ref` of its patch once kept, or None while
nobody asked.

**`reading`**

```python
def reading(self, workspace: str) -> dict[str, Any] | None: ...
```

**`readings`**

```python
def readings(self) -> dict[str, dict[str, Any]]: ...
```

### `platoon_harness.primitives.maker`

```python
def maker(event: Event) -> str | None: ...
```

Whose an event is: its actor, and for an event the runtime writes, the agent it is about. A commit is the agent's
whose workspace made it, and nobody's, None, when that was the shared one or no single workspace did.

### `platoon_harness.primitives.Metrics`

```python
class Metrics(Model):
    head: int
    events: dict[str, int]
    refused: dict[str, int]
    agents: dict[Group, int]
    trainable: dict[str, int]
    coverage: dict[Surface, dict[str, int]]
    proved: tuple[Surface, ...]
    gaps: dict[str, int]
    gauges: Gauges | None
    unknown: dict[str, str]
```

How a session runs, read at `head`.

Counted from the record as each event commits: `events`, how many of each type the journal holds, and `refused`,
how many commands it holds refused, by code. Read from its views: `agents`, how many agents stand in each of the
roster's groups; `trainable`, how many agents' latest start recorded their trainable level `met`, `unmet` or
`unverified`, or recorded none, `unrecorded`; `coverage`, for each surface, how many agents' latest start declared
it `observed`, `partial` or `none`, or declared nothing, `undeclared`, beside `proved`, the surfaces a stored result
proves observed; and `gaps`, how many the record holds, by kind. Measured by the runtime holding the session, as
they stand now: `gauges`, of its writer and its process since it started. None is unknown and never zero, and
`unknown` names each metric nothing measured, with why.

### `platoon_harness.primitives.Mode`

```python
Mode = Literal["shared", "worktree", "snapshot", "isolated"]
```

### `platoon_harness.primitives.ModelCall`

```python
class ModelCall(Args):
    type: Literal["model.call"] = "model.call"
    call_id: Short | None = None
    model: str | None = None
    purpose: Short | None = None
```

A model call the harness made. `call_id` is present only when it is real, and `purpose` only when the harness
said why, in its own word, such as `compaction`.

### `platoon_harness.primitives.Native`

```python
class Native(Args):
    type: Literal["native"] = "native"
    kind: Short
    raw: Annotated[str, Field(max_length=RAW_LIMIT)]
    cut: int = 0
```

A frame nobody's vocabulary covers, as it came, up to 2 KiB. `cut` says how many characters did not fit.

### `platoon_harness.primitives.NotSeen`

```python
class NotSeen(Model):
    answer: Literal["not_seen"] = "not_seen"
    proved: tuple[Surface, ...]
    bound: Bound
    head: int
    open: bool
```

Nothing offered the event to the agent below the bound, a stored conformance result proves every surface in
`proved` observed, which is all of them, and no gap content could come through lies below it.

### `platoon_harness.primitives.on`

```python
def on(stream: str, types: tuple[str, ...] = (), n: int | tuple[str, ...] = 1, distinct: Any = None) -> Condition: ...
```

One condition of a wait.

### `platoon_harness.primitives.OWNER_STOP`

```python
OWNER_STOP = "stopped by its owner"
```

### `platoon_harness.primitives.Pair`

```python
class Pair(Model):
    who: str | None
    whom: str | None
    declared: int
    observed: int
    cause: int
    ancestry: int
    unconfirmed: int
    first: dict[str, str]
```

Who reached whom: how many edges of each kind lead from events `who` made to events `whom` made, each kind
counted apart and never summed. `declared` counts citations, which their citers claim; `observed`, offers whose
harness said it took them; `cause`, causes an event names; and `ancestry`, an object's next versions and the
commits that name a commit their parent. `unconfirmed` counts the offers whose harness had not said it took them,
which are unknown, neither observed nor none. `first` names, by the count's name, the event holding the first of
each the record learned, an offer for `observed` and `unconfirmed`. A maker is as `maker` names it, and None is
nobody the record names, as for a commit no single workspace made.

### `platoon_harness.primitives.Plane`

```python
Plane = Literal["control", "tool", "model"]
```

### `platoon_harness.primitives.Policy`

```python
Policy = Literal["ask", "deny", "allow"]
```

### `platoon_harness.primitives.PRIMITIVES`

```python
PRIMITIVES = (
    Extension(
        "session",
        ops=[
            sessions.open_session,
            sessions.show_manifest,
            sessions.show_labels,
            lifecycle.session_status,
            lifecycle.session_ending,
            metrics.session_metrics,
            lifecycle.close,
            lifecycle.cancel_session,
            lifecycle.stop,
        ],
        views=[SessionRecord, Counters],
    ),
    Extension("episode", ops=[sessions.open_episode, sessions.close_episode]),
    Extension("budget", ops=[budgets.set_budget, budgets.lapse, budgets.budget_status], views=[Budgets]),
    Extension(
        "agent",
        ops=[
            lifecycle.spawn,
            lifecycle.finish,
            lifecycle.conclude,
            lifecycle.interrupt,
            lifecycle.cancel,
            lifecycle.retire,
            lifecycle.hold,
            lifecycle.release,
            lifecycle.start,
            lifecycle.instruct,
            lifecycle.retell,
            lifecycle.rest,
            lifecycle.report,
            lifecycle.list_agents,
            lifecycle.agent_records,
            lifecycle.agent_status,
            lifecycle.agent_unread,
        ],
        views=[Agents],
    ),
    Extension("peers", ops=[lifecycle.peers]),
    Extension("channel", ops=[channels.create, channels.list_channels], views=[Channels]),
    Extension("group", ops=[channels.define_group], views=[Groups]),
    Extension("message", ops=[messages.send, messages.read], views=[Deliveries]),
    Extension(
        "delivery",
        ops=[delivery.offer, delivery.pending, delivery.delivery_ready],
        daemons=[courier],
    ),
    Extension("wait", ops=[waits.wait_for, waits.cancel, waits.release, waits.progress_of], views=[Waits]),
    Extension("board", ops=[boards.post, boards.revise, boards.get, boards.query], views=[Boards]),
    Extension(
        "task",
        ops=[tasks.add, tasks.claim, tasks.renew, tasks.release, tasks.complete, tasks.fail, tasks.list_tasks],
        views=[Tasks],
    ),
    Extension("lease", ops=[tasks.expire_lease, tasks.leases_due]),
    Extension("approval", ops=[approvals.request, approvals.resolve], views=[Approvals]),
    Extension("blob", ops=[blobs.get, blobs.hash_of, blobs.offer]),
    Extension(
        "repo", ops=[repo.report, repo.record, repo.looks, repo.commit, repo.test, repo.diff, repo.keep], views=[Looks]
    ),
    Extension("attention", ops=[clients.attention_list], views=[Attention]),
    Extension("view", ops=[clients.watch], views=[Changes, Gaps]),
    Extension("exposure", ops=[provenance.exposure], views=[Exposures]),
    Extension("lineage", ops=[provenance.lineage], views=[Calls]),
    Extension("uses", ops=[provenance.uses], views=[References]),
    Extension("contributors", ops=[provenance.contributors]),
    Extension("eligibility", ops=[eligibility.eligibility]),
    Extension("spans", ops=[provenance.spans]),
    Extension("context", ops=[provenance.show]),
    Extension("interactions", ops=[provenance.interactions]),
)
```

### `platoon_harness.primitives.RAW_LIMIT`

```python
RAW_LIMIT = 2048
```

### `platoon_harness.primitives.REF`

```python
REF = rf"^[^\s@#]+@[1-9]\d{{0,17}}(#{LINE_RANGE})?$"
```

A ref, `stream@version`, with `#La-b` naming lines of that event's body: the one form a citation takes.

### `platoon_harness.primitives.Ready`

```python
class Ready(Args):
    type: Literal["ready"] = "ready"
    native: str | None = None
    version: str | None = None
    effective_model: str | None = None
    tools_visible: tuple[str, ...] | None = None
```

A harness is up. `tools_visible` is a list only when it comes from an observed source.

### `platoon_harness.primitives.References`

```python
class References(View):
    schema = """
    CREATE TABLE v_references_cited(stream TEXT NOT NULL, version INTEGER NOT NULL, seq INTEGER NOT NULL) STRICT;
    CREATE INDEX v_references_cited_event ON v_references_cited(stream, version, seq);
    CREATE TABLE v_references_caused(
        cause INTEGER NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (cause, seq)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_references_parents(
        sha TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (sha, seq)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_references_anchors(
        agent TEXT NOT NULL, anchor TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (agent, anchor, seq)
    ) WITHOUT ROWID, STRICT;
    """
```

The references events hold, by what they point at: what cites an event, what follows from one, which commits
name a commit as a parent, and which of an agent's events came under one tool call's id.

**`held`**

```python
@fold("*")
def held(self, event: Event) -> None: ...
```

Any event can cite or follow from another, an extension's too, so this cannot name what it folds.

**`committed`**

```python
@fold("repo.committed")
def committed(self, event: Event) -> None: ...
```

**`citing`**

```python
def citing(self, stream: str, version: int, after: int) -> tuple[list[int], int]: ...
```

The seqs of the events that cite one, past `after`, as many as a page holds and one more, and how many in
all.

**`caused`**

```python
def caused(self, cause: int, after: int) -> tuple[list[int], int]: ...
```

The seqs of the events that follow from one, past `after`, as `citing` gives them.

**`children`**

```python
def children(self, sha: str) -> list[int]: ...
```

The seqs of the recorded commits that name a commit as a parent.

**`anchored`**

```python
def anchored(self, agent: str, anchor: str | None = None) -> list[int]: ...
```

The seqs of an agent's events that came under one tool call's id, or with none under any, oldest first.

### `platoon_harness.primitives.Repo`

```python
class Repo(Args):
    name: str
    top: str
    prefix: str
    head: str | None
    branch: str | None
    repository: str
    tips: BodyRef
```

The repository the session's cwd is in, as git said at open: `name` for its stream `repo/<name>`, the `top` of
its work tree and the session's `prefix` within it, `head` and `branch` then, the `repository` that holds its refs
and objects, and `tips`, a body naming every ref and its tip, one `<sha> <ref>` a line.

### `platoon_harness.primitives.Report`

```python
type Report = Annotated[
    Ready
    | TurnStarted
    | TurnEnded
    | Delta
    | Item
    | InputDelivered
    | ApprovalRequested
    | ModelCall
    | Usage
    | Compacted
    | ChildSeen
    | GapReport
    | Native
    | Exited,
    Field(discriminator="type"),
]
```

### `platoon_harness.primitives.REPORTS`

```python
REPORTS: TypeAdapter[Report] = TypeAdapter(Report)
```

The vocabulary as a parser: `REPORTS.validate_json(text)`. Anything it refuses is an unknown frame.

### `platoon_harness.primitives.Seen`

```python
class Seen(Model):
    answer: Literal["seen"] = "seen"
    edges: tuple[Offer, ...]
    total: int
    bound: Bound
    head: int
    open: bool
```

The event reached the agent through us below the bound: `edges` holds a page of the offers of it its harness said
it took there, `total` of them. Seen means handed over and taken, never understood: a read's result returned to
its harness, or under a Codex `callId` to the Code Mode script that made the call.

### `platoon_harness.primitives.SessionRecord`

```python
class SessionRecord(View):
    name = "session"
    version = 2
    schema = """
    CREATE TABLE v_session(id INTEGER PRIMARY KEY CHECK (id = 1), state TEXT NOT NULL, settings TEXT NOT NULL) STRICT;
    """
```

One row, once the session is open. A session that was closing is `closed` once its owner has stopped, as nothing
more of it will run.

**`opened`**

```python
@fold("session.opened")
def opened(self, event: Event) -> None: ...
```

**`moved`**

```python
@fold("session.closed", "session.cancelled")
def moved(self, event: Event) -> None: ...
```

**`stopped`**

```python
@fold("session.stopped")
def stopped(self, event: Event) -> None: ...
```

**`resumed`**

```python
@fold("runtime.started")
def resumed(self, event: Event) -> None: ...
```

A shutdown keeps the folder resumable, so the next incarnation takes up an open session where it stopped.

**`state`**

```python
def state(self) -> str: ...
```

**`settings`**

```python
def settings(self) -> Settings: ...
```

**`accepting`**

```python
def accepting(self) -> bool: ...
```

Whether new work may start. A session that is closing only drains.

### `platoon_harness.primitives.Settings`

```python
class Settings(Args):
    roles: dict[Name, Role] = {}
    limits: Limits = Limits()
    until: Annotated[str, Field(pattern=rf"^(settled|program|role:{NAME})$")] = "settled"
    manifest: BodyRef | None = None
    repo: Repo | None = None
    test: tuple[str, ...] | None = None
    labels: dict[Name, tuple[Name, ...]] = {}
```

What a session states at open. `manifest` is a stored body. `repo` is None when the session's cwd is in no
repository, and when a session opened before it was recorded, which is not observed. `test` is the command a
runtime test of a commit runs, or None when the team names none. `labels` are its team's labels, each with the
values it may take, and none for a session opened before they were recorded, which had none.

### `platoon_harness.primitives.SHORT_LIMIT`

```python
SHORT_LIMIT = 256
```

### `platoon_harness.primitives.Span`

```python
class Span(Model):
    ref: str
    first: str
    turn: str
    writes: tuple[str, ...]
    claims: tuple[str, ...] | None
    labels: dict[str, str] | None
```

A stretch of one turn of an agent, named by `ref`, the `model.called` of its last call, which a credit row about
it targets: its calls are those its harness reported on its turn stream from `first` to `ref`, in the turn named
`turn`, and `writes` are the writes of content the record ties to them, which one of them chose. `claims` are the
claims its agent held while one of its calls was made, by the ref of each `task.claimed`, oldest first, and None
where the record cannot place a claim or its end to say whether it did. `labels` are the labels of the work it was
done for: those of the task of each claim it held or may have held, and those its agent was spawned with unless it
surely held one, even for its calls made before it did; None, unknown, where these differ.

### `platoon_harness.primitives.Spans`

```python
class Spans(Model):
    agent: str
    spans: tuple[Span, ...]
    total: int
    cursor: str | None
    head: int
    open: bool
```

Each span of an agent, oldest first: a page of them, `total` in all, with `cursor` to pass as `after` for the
next page, `open` while its latest turn has not ended, as a late report can still join a write to a call and cut
that turn again, and `head` where the record was read.

### `platoon_harness.primitives.stream_of`

```python
def stream_of(address: str) -> str: ...
```

The stream an address names: `@agent`, `#channel` or `+group`.

### `platoon_harness.primitives.Task`

```python
class Task(BaseModel, frozen=True):
    queue: str
    id: str
    state: TaskState
    gist: str
    body: str | None
    owner: str | None
    fence: int | None
    lease_until: float | None
    claimed_at: float | None
    attempts: int
    seq: int
    result: str | None
    result_body: str | None
    result_ref: str | None
```

One task. `fence` and `lease_until` belong to its latest claim. A failed task may be claimed again. `result` is
what its latest attempt reported, and `result_ref` the ref of that report. `body` and `result_body` are hashes,
which no reader sees.

**`stream`**

```python
@property
def stream(self) -> str: ...
```

**`ref`**

```python
@property
def ref(self) -> str: ...
```

The task as a ref: its `task.added`.

**`shown`**

```python
def shown(self) -> dict[str, Any]: ...
```

The task as a reader gets it, by its ref, saying whether it and its result have a body, which `blob.get`
reads by `ref` and `result_ref`.

**`live`**

```python
def live(self, now: float) -> bool: ...
```

Whether its lease holds by this clock. Time passing is enough: no event need have said so.

### `platoon_harness.primitives.Tasks`

```python
class Tasks(View):
    version = 2
    schema = """
    CREATE TABLE v_tasks(
        queue TEXT NOT NULL,
        id TEXT NOT NULL,
        state TEXT NOT NULL,
        gist TEXT NOT NULL,
        body TEXT,
        owner TEXT,
        fence INTEGER,
        lease_until REAL,
        claimed_at REAL,
        attempts INTEGER NOT NULL,
        seq INTEGER NOT NULL,
        result TEXT,
        result_body TEXT,
        result_ref TEXT,
        PRIMARY KEY (queue, id)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_tasks_state ON v_tasks(queue, state, seq);
    CREATE INDEX v_tasks_owner ON v_tasks(owner, state);
    CREATE TABLE v_tasks_claims(
        owner TEXT NOT NULL,
        queue TEXT NOT NULL,
        id TEXT NOT NULL,
        claimed INTEGER NOT NULL,
        ended INTEGER,
        PRIMARY KEY (owner, claimed)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_tasks_claims_open ON v_tasks_claims(queue, id, ended);
    """
```

Tasks by queue, oldest first, and each claim by its claimant, with the event that ended it: its completion,
failure, release or lapse, or its claimant's end.

**`added`**

```python
@fold("task.added")
def added(self, event: Event) -> None: ...
```

**`claimed`**

```python
@fold("task.claimed")
def claimed(self, event: Event) -> None: ...
```

**`renewed`**

```python
@fold("task.renewed")
def renewed(self, event: Event) -> None: ...
```

**`released`**

```python
@fold("task.released")
def released(self, event: Event) -> None: ...
```

**`expired`**

```python
@fold("lease.expired")
def expired(self, event: Event) -> None: ...
```

**`reported`**

```python
@fold("task.completed", "task.failed")
def reported(self, event: Event) -> None: ...
```

**`died`**

```python
@fold("task.died")
def died(self, event: Event) -> None: ...
```

**`owner_gone`**

```python
@fold("agent.ended")
def owner_gone(self, event: Event) -> None: ...
```

**`get`**

```python
def get(self, queue: str, id: str) -> Task | None: ...
```

**`next_open`**

```python
def next_open(self, queue: str) -> Task | None: ...
```

**`lapsed`**

```python
def lapsed(self, queue: str, now: float) -> list[Task]: ...
```

Claimed tasks whose lease has run out by this clock, whether or not its timer has fired.

**`held_by`**

```python
def held_by(self, queue: str, owner: str) -> list[Task]: ...
```

**`owned`**

```python
def owned(self, owner: str) -> list[Task]: ...
```

**`claims`**

```python
def claims(self, owner: str) -> list[tuple[str, str, int, int | None]]: ...
```

Each claim `owner` made, oldest first: its queue, its task, the seq of its claim and of the event that ended
it, or None while it holds.

**`any_claimed`**

```python
def any_claimed(self) -> bool: ...
```

**`listed`**

```python
def listed(self, queue: str, state: str | None, after: int, limit: int) -> tuple[list[Task], int]: ...
```

A page past `after`, oldest first, and the true total.

**`count`**

```python
def count(self, queue: str) -> int: ...
```

### `platoon_harness.primitives.TurnEnded`

```python
class TurnEnded(Args):
    type: Literal["turn.ended"] = "turn.ended"
    reason: Short = "stopped"
```

`stopped` if it stopped on its own, `interrupted` if someone stopped it, and otherwise what went wrong. A driver
cannot say a reason in `CUT_OFF`, which are the runtime's own.

### `platoon_harness.primitives.TurnStarted`

```python
class TurnStarted(Args):
    type: Literal["turn.started"] = "turn.started"
    turn: Short
```

### `platoon_harness.primitives.Unknown`

```python
class Unknown(Model):
    answer: Literal["unknown"] = "unknown"
    handed: tuple[Offer, ...]
    standing: tuple[Coverage, ...]
    incidents: tuple[Incident, ...]
    older_offers: int
    totals: dict[str, int]
    bound: Bound
    head: int
    open: bool
```

Whether the event reached the agent below the bound is not known, and these are why: the offers of it made below
the bound that its harness had not said there it took, `handed`, empty when none was made through us below it; the
surfaces no result proves observed, `standing`; the gaps content could have come through, `incidents`; and
`older_offers`, from before offer payload 3, which named bodies by hash and announces by their own refs, so none can
be tied to this event.

### `platoon_harness.primitives.Unknowns`

```python
class Unknowns(Model):
    agent: str
    unproved: tuple[Surface, ...]
    incidents: dict[str, int]
    older_offers: int
```

Why what reached an agent beyond the edges counted is unknown: the surfaces no result proves observed,
`unproved`; the gaps content could come through that its record held, by kind, `incidents`; and its offers from
before offer payload 3, `older_offers`, which no event can be tied to.

### `platoon_harness.primitives.Usage`

```python
class Usage(Args):
    type: Literal["usage"] = "usage"
    tokens: int | None = None
    usd: float | None = None
    label: Label
    scope: Literal["call", "turn", "tree"] = "turn"
    call_id: Short | None = None
```

What was spent, once: `scope` says what the amounts cover, one `call`, this agent's `turn`, or its whole `tree`
with native children. A driver reports each spend at one scope. `tokens` counts input and output, cached input
included. `call_id` names the model call, when the harness says so.

### `platoon_harness.primitives.Uses`

```python
class Uses(Model):
    rows: tuple[Annotated[Step | Handed, Field(discriminator="kind")], ...]
    totals: dict[str, int]
    cursor: str | None
    head: int
    open: bool
```

One hop forward from an event, oldest first: what cites it, what follows from it, its next version or the
commits that name it a parent, and each agent it was offered to, with true `totals` by kind.

### `platoon_harness.primitives.Verdict`

```python
Verdict = Literal["allow", "deny"]
```

### `platoon_harness.primitives.Waits`

```python
class Waits(View):
    version = 2
    schema = """
    CREATE TABLE v_waits(
        id INTEGER PRIMARY KEY,
        waiter TEXT NOT NULL,
        mode TEXT NOT NULL,
        left INTEGER NOT NULL,
        after INTEGER,
        deadline REAL,
        hops INTEGER NOT NULL,
        closed TEXT
    ) STRICT;
    CREATE INDEX v_waits_waiter ON v_waits(waiter);
    CREATE INDEX v_waits_holding ON v_waits(left) WHERE closed IS NULL;
    CREATE INDEX v_waits_due ON v_waits(deadline) WHERE closed IS NULL;
    CREATE TABLE v_waits_conditions(
        wait INTEGER NOT NULL,
        position INTEGER NOT NULL,
        stream TEXT NOT NULL,
        progress TEXT NOT NULL,
        PRIMARY KEY (wait, position)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_waits_conditions_stream ON v_waits_conditions(stream);
    """
```

Waits, how each closed, and the folded progress of those still open.

**`registered`**

```python
@fold("wait.registered")
def registered(self, event: Event) -> None: ...
```

**`progressed`**

```python
@fold("*")
def progressed(self, event: Event) -> None: ...
```

**`closed`**

```python
@fold("wait.released", "wait.expired", "wait.cancelled")
def closed(self, event: Event) -> None: ...
```

**`waiter_gone`**

```python
@fold("agent.ended")
def waiter_gone(self, event: Event) -> None: ...
```

**`get`**

```python
def get(self, id: int) -> WaitRecord | None: ...
```

**`open_for`**

```python
def open_for(self, waiter: str) -> list[WaitRecord]: ...
```

**`closing`**

```python
def closing(self, now: float) -> tuple[list[WaitRecord], float | None]: ...
```

Waits whose condition holds or whose deadline has passed, and when the next deadline falls. Each is found
through an index of the open waits, so a pass reads none that closed before it.

### `platoon_harness.primitives.WAKING`

```python
WAKING: tuple[Injection, ...] = ("wake", "steer")
```

### `platoon_harness.primitives.WALK_LIMIT`

```python
WALK_LIMIT = 4096
```

How many events a walk back from an outcome reaches before it stops and says so.

### `platoon_harness.primitives.Why`

```python
Why = Approval | Wait | Budget | Lease | Peer | Timer | Infra | Lost
```

### `platoon_harness.primitives.Workspace`

```python
class Workspace(BaseModel, frozen=True):
    mode: Mode
    path: str
    host: str | None = None
    branch: str | None = None
    base: str | None = None
    repository: str | None = None
    objects: str | None = None
    assurance: Literal["cooperative", "isolated"] = "cooperative"
```

Where an agent works, as its `workspace` effect made it: in `mode`, its harness runs in the folder `path` on
`host`, on `branch` made at the commit `base`, with the git directory `repository` holding its refs, and `objects`
the object directory a snapshot reads. `assurance` is how well what runs there is tied to its credential. What a
mode does not have is None.

## `platoon_harness.rpc`

One line-delimited JSON-RPC 2.0 peer on asyncio streams, split on LF only.

### `platoon_harness.rpc.BUSY`

```python
BUSY = -32000
```

### `platoon_harness.rpc.Closed`

```python
class Closed(ConnectionError): ...
```

The connection ended, so a call will never be answered.

### `platoon_harness.rpc.Handler`

```python
Handler = Callable[[str, Any], Awaitable[Any]]
```

### `platoon_harness.rpc.INVALID_PARAMS`

```python
INVALID_PARAMS = -32602
```

### `platoon_harness.rpc.LINE_LIMIT`

```python
LINE_LIMIT = 16 * 1024 * 1024
```

### `platoon_harness.rpc.Lines`

```python
class Lines:
    def __init__(self, lost: Callable[[], Exception]) -> None: ...
```

JSON lines on one stream, with answers arriving among the other end's events, for a protocol that is no JSON-RPC.
`lost` makes what a frame with nowhere to go raises, and `settle` is how a reader gives an answer to its waiter.

**`open`**

```python
def open(self, writer: asyncio.StreamWriter) -> None: ...
```

**`run`**

```python
async def run(self, reader: asyncio.StreamReader, heard: Callable[[bytes], None]) -> None: ...
```

Hear every line that holds anything. When none are left, nothing can be answered, so every waiter is told.

**`write`**

```python
def write(self, frame: Mapping[str, Any]) -> None: ...
```

Send a frame and do not wait, as a reader must not. With nowhere to go, it goes nowhere.

**`send`**

```python
async def send(self, frame: Mapping[str, Any]) -> None: ...
```

Send a frame, and wait until it has left.

**`exchange`**

```python
async def exchange(self, id: str, frame: Mapping[str, Any]) -> Any: ...
```

Send a frame and wait for the answer to its id.

**`settle`**

```python
def settle(self, id: str, answer: Any) -> None: ...
```

Give a waiter its answer, or an `Exception` to raise. One nobody waits for any more has nobody to reach.

### `platoon_harness.rpc.LineTooLong`

```python
class LineTooLong(Closed): ...
```

A line passed the limit, which ends the connection, since what it held may have been the answer to a call.

### `platoon_harness.rpc.METHOD_NOT_FOUND`

```python
METHOD_NOT_FOUND = -32601
```

### `platoon_harness.rpc.Peer`

```python
class Peer:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        handler: Handler = _unknown_method,
        *,
        stray: Stray | None = None,
        jsonrpc: bool = True,
    ) -> None: ...
```

Both ends of JSON-RPC on one connection. Nothing moves until `run` reads.

`handler` takes `(method, params)`. Each request runs in its own task, so a slow one holds up no other, and
notifications run in order on the read loop, so that handler must not wait on the world: it would stop the reads.
`stray` hears the raw line of what no method took and no call awaits.
`jsonrpc=False` drops the `jsonrpc` member, which Codex omits.

**`run`**

```python
async def run(self) -> None: ...
```

Read until the stream ends, however it ends, then fail every pending call. Past the line limit it raises
`LineTooLong`.

**`call`**

```python
async def call(self, method: str, params: Any = None) -> Any: ...
```

Send a request and await its result. Raises `RpcError` if refused, `Closed` if it can never be answered.

**`notify`**

```python
async def notify(self, method: str, params: Any = None) -> None: ...
```

Send a notification, which nothing answers. Raises `Closed` once the connection has ended.

**`close`**

```python
def close(self) -> None: ...
```

Close this end. The other reads EOF, and `run` returns when the transport has gone.

### `platoon_harness.rpc.read_lines`

```python
async def read_lines(reader: asyncio.StreamReader, limit: int = LINE_LIMIT) -> AsyncIterator[bytes]: ...
```

Each line of a stream, split on LF and nothing else, so U+2028 stays inside a string. A last line needs no LF.

Raises `LineTooLong` past `limit`, having held no more than that.

### `platoon_harness.rpc.RpcError`

```python
class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None: ...
```

A JSON-RPC error: a handler raises one to answer with it, and `call` raises what the other side answered.

**`frame`**

```python
def frame(self) -> dict[str, Any]: ...
```

### `platoon_harness.rpc.Stray`

```python
Stray = Callable[[bytes], None]
```

### `platoon_harness.rpc.strict_loads`

```python
def strict_loads(text: str | bytes) -> Any: ...
```

JSON as JSON is, which has no NaN and no Infinity, whatever Python's parser lets through.

## `platoon_harness.runtime`

The runtime: one live session's kernel, daemons, tool plane and control socket. Nothing here is global, so several
can share a process, and `Session` is how anyone uses one.

### `platoon_harness.runtime.Admission`

Imported from [`platoon_harness.runtime.authority.Admission`](#platoon_harnessruntimeauthorityadmission).

### `platoon_harness.runtime.AgentOutcome`

Imported from [`platoon_harness.runtime.authority.AgentOutcome`](#platoon_harnessruntimeauthorityagentoutcome).

### `platoon_harness.runtime.AgentRef`

Imported from [`platoon_harness.runtime.authority.AgentRef`](#platoon_harnessruntimeauthorityagentref).

### `platoon_harness.runtime.Authority`

Imported from [`platoon_harness.runtime.authority.Authority`](#platoon_harnessruntimeauthorityauthority).

### `platoon_harness.runtime.Gateway`

Imported from [`platoon_harness.drivers.Gateway`](#platoon_harnessdriversgateway).

### `platoon_harness.runtime.GRACE`

Imported from [`platoon_harness.runtime.host.GRACE`](#platoon_harnessruntimehostgrace).

### `platoon_harness.runtime.LocalAuthority`

Imported from [`platoon_harness.runtime.authority.LocalAuthority`](#platoon_harnessruntimeauthoritylocalauthority).

### `platoon_harness.runtime.Runtime`

```python
class Runtime:
    def __init__(self, folder: Path, *, authority: Authority | None = None, clock: Clock | None = None) -> None: ...
```

One live session. `start` is one path for a new session and a resumed one: recover, open under keys that answer
from the journal, then per agent reap, resume and reconcile.

`stop` is the owner's shutdown: interrupt turns, wait `grace`, end the process trees, hand back what will not
happen, append `session.stopped`, and keep the folder resumable, holding no credential. A journal that stops
answering holds up none of it past `grace`, and nothing a driver does keeps it from letting go.

**`start`**

```python
async def start(self) -> None: ...
```

**`ask_to_stop`**

```python
def ask_to_stop(self) -> None: ...
```

Ask `run` to return. A signal handler may call this.

**`run`**

```python
async def run(self) -> None: ...
```

Serve until asked to stop, or until the session has drained: nothing is left for a detached runtime to do. A
commit that fails ends it with `JournalError`, as nothing more can be recorded.

**`stop`**

```python
async def stop(self, grace: float = GRACE) -> None: ...
```

The owner's shutdown. After a failed commit only the process trees end, and nothing is recorded, as after a
kill: the next runtime finds the turns that were open and tells their agents they were cut off.

### `platoon_harness.runtime.SpawnRequest`

Imported from [`platoon_harness.runtime.authority.SpawnRequest`](#platoon_harnessruntimeauthorityspawnrequest).

### `platoon_harness.runtime.told`

Imported from [`platoon_harness.runtime.opening.told`](#platoon_harnessruntimeopeningtold).

## `platoon_harness.runtime.authority`

Who admits an agent: the session itself, or in managed mode a training system's authority.

### `platoon_harness.runtime.authority.Admission`

```python
class Admission(Model):
    token: Secret
    access: Access = {}
    backend: Mapping[str, str] = {}
```

What admission gives an agent: its token on the tool plane, which stays in memory, and its model access, as
variables by name or as a gateway. `backend` is the backend's ids for this agent, which its admit records: each
entry is this agent's alone, so one another admission of the session shares bars both from training, no key or
value holds a secret of its own in any form, and a gateway admission names them, as nothing else ties the agent to
what its gateway records of it.

### `platoon_harness.runtime.authority.AgentOutcome`

```python
class AgentOutcome(Model):
    status: Status
    report: str | None = None
```

How an agent ended: its `status`, and its `report`, the words its end keeps, or None when it said nothing: the
gist, which is the agent's own for a finish and the session's for any other end, and then the body, its last
words, unless a person redacted them.

### `platoon_harness.runtime.authority.AgentRef`

```python
class AgentRef(Model):
    agent: str
    role: str
```

An agent by name and role.

### `platoon_harness.runtime.authority.Authority`

```python
@runtime_checkable
class Authority(Protocol): ...
```

What a kernel with no training branch asks of whoever owns identity and model access. A managed authority's
refusal wins: `admit` raises, and the spawn fails.

**`admit`**

```python
async def admit(self, spawn: SpawnRequest) -> Admission: ...
```

**`finish`**

```python
async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None: ...
```

### `platoon_harness.runtime.authority.Gateway`

Imported from [`platoon_harness.drivers.Gateway`](#platoon_harnessdriversgateway).

### `platoon_harness.runtime.authority.LocalAuthority`

```python
class LocalAuthority:
    def __init__(self, team: Team, environ: Mapping[str, str] = os.environ) -> None: ...
```

Issues session-scoped identity and leaves the harness's own auth alone: model access is what a role's auth
profile names, and with none the harness signs itself in.

**`admit`**

```python
async def admit(self, spawn: SpawnRequest) -> Admission: ...
```

**`finish`**

```python
async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None: ...
```

### `platoon_harness.runtime.authority.SpawnRequest`

```python
class SpawnRequest(AgentRef):
    parent: str | None = None
    goal: str = ""
    resumed: bool = False
```

An agent to admit. `parent` is the principal that spawned it, as its `agent.spawned` records it, and None for one
the session started, and `goal` is what it was given to do. `resumed` says it was admitted once, and a restart needs
its access again.

## `platoon_harness.runtime.control`

The one link a `Session` has, in its two forms, and the control socket that joins them.

`Local` is the kernel in-process and `Remote` is the socket, and the server is a `Local` per connection, so the methods
mirror by construction. Law 8 holds because a client only ever pulls: `read` is a page, `changed` and `delta` are
long-polls on the shared pulse, and there is no queue or subscription here for a client to fill.

### `platoon_harness.runtime.control.BODY_LIMIT`

```python
BODY_LIMIT = LINE_LIMIT // 4 * 3 - 1024
```

The largest body this socket carries, as base64 in one line.

### `platoon_harness.runtime.control.Control`

```python
class Control:
    def __init__(self, kernel: Kernel, principal: Principal, folder: Path) -> None: ...
```

The control socket of one runtime: JSON-RPC lines on a Unix socket in a private directory. A connection costs a
task and a socket. Pages leave only when asked for, and a client that stops reading is dropped by its `Peer`, so it
costs its own lag and can hold up nobody else.

**`start`**

```python
async def start(self) -> None: ...
```

**`stop`**

```python
async def stop(self) -> None: ...
```

Stop listening and drop every client. Each reads EOF, which is how it learns the runtime went.

**`clients`**

```python
def clients(self) -> int: ...
```

How many clients hold a credential that can act.

**`bind`**

```python
def bind(self, token: str) -> tuple[Local, bool, str]: ...
```

The link a credential earns. A view token reads and never writes. An agent's token is no client's: its reads
are ops, and the tool plane is its way in.

### `platoon_harness.runtime.control.History`

```python
class History(Local):
    def __init__(self, kernel: Kernel, principal: Principal, resume_with: str) -> None: ...
```

The link with no runtime: a read-only kernel, closed along with the link.

**`submit`**

```python
async def submit(self, op: str, args: Mapping[str, Any], *, key: str | None = None) -> Outcome: ...
```

A command the journal answered under `key` gets that answer, as a retry would from a runtime, so one whose
runtime went after it committed stays one operation. Any other write is refused, naming what restarts it.

**`stale`**

```python
def stale(self) -> bool: ...
```

Whether a writer has changed the journal, which an immutable reader cannot read past.

**`close`**

```python
async def close(self) -> None: ...
```

### `platoon_harness.runtime.control.Link`

```python
class Link(Protocol): ...
```

Everything a `Session` does to a session, once. A method raises `Refused`, except that `submit` and `query`
return an `Outcome`, and `Closed` means the runtime went, so the caller may try again under the same key.

**`clock`**

```python
@property
def clock(self) -> Clock: ...
```

**`principal`**

```python
@property
def principal(self) -> str: ...
```

Who this link acts as.

**`submit`**

```python
async def submit(self, op: str, args: Mapping[str, Any], *, key: str | None = None) -> Outcome: ...
```

**`query`**

```python
async def query(self, op: str, args: Mapping[str, Any]) -> Outcome: ...
```

**`read`**

```python
async def read(
    self,
    after: int = 0,
    *,
    before: int | None = None,
    match: str | None = None,
    streams: Sequence[str] | None = None,
    limit: int = _PAGE_LIMIT,
) -> Page: ...
```

**`put_body`**

```python
async def put_body(self, body: bytes) -> str: ...
```

**`get_body`**

```python
async def get_body(self, sha256: str, limit: int | None = None) -> bytes: ...
```

**`changed`**

```python
async def changed(self, after: int) -> int | None: ...
```

The head, once it passes `after`, or None if nothing more can come.

**`delta`**

```python
async def delta(self, agent: str, after: int | None) -> Delta | None: ...
```

The next frame of an agent's live text past `after`, or None if no more can come.

**`others`**

```python
async def others(self) -> int: ...
```

How many other clients could act on this session now.

**`close`**

```python
async def close(self) -> None: ...
```

### `platoon_harness.runtime.control.Local`

```python
class Local:
    def __init__(
        self,
        kernel: Kernel,
        principal: Principal,
        *,
        denied: Refusal | None = None,
        others: Callable[[], int] = lambda: 0,
    ) -> None: ...
```

The link as the kernel in-process. `denied` is the refusal for every write, which a view credential and a session
with no runtime have; a command otherwise cannot tell those apart from a mistake in its arguments. A query runs on a
reader of its own off the event loop, so however long one takes, no harness's report waits behind it.

**`clock`**

```python
@property
def clock(self) -> Clock: ...
```

**`principal`**

```python
@property
def principal(self) -> str: ...
```

**`submit`**

```python
async def submit(self, op: str, args: Mapping[str, Any], *, key: str | None = None) -> Outcome: ...
```

A read is answered as a query, since no client is an agent, so it writes nothing and a view may ask it.

**`query`**

```python
async def query(self, op: str, args: Mapping[str, Any]) -> Outcome: ...
```

**`read`**

```python
async def read(
    self,
    after: int = 0,
    *,
    before: int | None = None,
    match: str | None = None,
    streams: Sequence[str] | None = None,
    limit: int = _PAGE_LIMIT,
) -> Page: ...
```

**`put_body`**

```python
async def put_body(self, body: bytes) -> str: ...
```

**`get_body`**

```python
async def get_body(self, sha256: str, limit: int | None = None) -> bytes: ...
```

**`changed`**

```python
async def changed(self, after: int) -> int | None: ...
```

**`delta`**

```python
async def delta(self, agent: str, after: int | None) -> Delta | None: ...
```

The next frame. A name nobody holds is refused, or asking for it would keep a ring for ever.

**`others`**

```python
async def others(self) -> int: ...
```

**`close`**

```python
async def close(self) -> None: ...
```

### `platoon_harness.runtime.control.PROTOCOL`

```python
PROTOCOL = 1
```

### `platoon_harness.runtime.control.REFUSED`

```python
REFUSED = -32010
```

### `platoon_harness.runtime.control.Remote`

```python
class Remote:
    def __init__(self, peer: Peer, running: asyncio.Task[None]) -> None: ...
```

The link as the control socket. The credential is said once, by `hello`, and binds the principal to this
connection. A long-poll comes back empty now and then, and goes round again, so that a client that gave up frees the
server's task within one poll.

**`connect`**

```python
@classmethod
async def connect(cls, folder: Path, *, view: bool = False) -> Self: ...
```

Connect to the runtime a folder names. `Closed` means there is none to reach.

**`hello`**

```python
async def hello(self, token: str) -> None: ...
```

Say the credential that binds this connection. It is said once.

**`clock`**

```python
@property
def clock(self) -> Clock: ...
```

**`principal`**

```python
@property
def principal(self) -> str: ...
```

**`submit`**

```python
async def submit(self, op: str, args: Mapping[str, Any], *, key: str | None = None) -> Outcome: ...
```

**`query`**

```python
async def query(self, op: str, args: Mapping[str, Any]) -> Outcome: ...
```

**`read`**

```python
async def read(
    self,
    after: int = 0,
    *,
    before: int | None = None,
    match: str | None = None,
    streams: Sequence[str] | None = None,
    limit: int = _PAGE_LIMIT,
) -> Page: ...
```

**`put_body`**

```python
async def put_body(self, body: bytes) -> str: ...
```

**`get_body`**

```python
async def get_body(self, sha256: str, limit: int | None = None) -> bytes: ...
```

**`changed`**

```python
async def changed(self, after: int) -> int | None: ...
```

**`delta`**

```python
async def delta(self, agent: str, after: int | None) -> Delta | None: ...
```

**`others`**

```python
async def others(self) -> int: ...
```

**`close`**

```python
async def close(self) -> None: ...
```

## `platoon_harness.runtime.diffs`

A diff: what git shows of a recorded commit's patch, or of a workspace's uncommitted work, for `repo.keep`, read
without changing any ref, index or file, with no external diff, textconv or hook, and each object as it is stored. See
architecture section 13.

### `platoon_harness.runtime.diffs.Diff`

```python
@dataclass(frozen=True)
class Diff:
    text: bytes
    cut: bool
    untracked_repositories: int = 0
```

A diff as its record keeps it: its patch as `text`, to the end of the last line within `PATCH_LIMIT` bytes where
it was longer, which `cut` says, and how many `untracked_repositories` in the work tree it shows no file of.

### `platoon_harness.runtime.diffs.patch`

```python
def patch(root: Path, sha: str, *, wrap: Sequence[str] = ()) -> Diff: ...
```

A commit's patch, from the tree of the first parent its own object names, or from no tree for a root, to its own,
as git run under `wrap` shows it in the repository whose work tree is at `root`. Its parent is read from the object,
so no graft or shallow list changes it, and no porcelain reads it, so no signature is verified.

### `platoon_harness.runtime.diffs.uncommitted`

```python
def uncommitted(root: Path, *, wrap: Sequence[str] = ()) -> tuple[str | None, Diff]: ...
```

The HEAD the work tree at `root` holds, None before its first commit, and what it holds uncommitted against that,
as git run under `wrap` shows it: its tracked files, staged or not, then each untracked file git does not ignore, as
a new one, until the patch passes its bound. An untracked repository in the tree is passed over, as git shows no
file of it, and counted. It is read only where git finds the work tree's own repository at `root`.

## `platoon_harness.runtime.git`

The runtime's own git: one runner, which runs no hook, no fsmonitor and no gc, reaches no remote, and asks nothing
of a terminal.

An agent's git is its own and is never touched. Paths come from `rev-parse`, never from a literal `.git/`.

### `platoon_harness.runtime.git.git`

```python
def git(
    *args: str,
    cwd: Path,
    input: str | None = None,
    ok: Sequence[int] = (0,),
    env: Mapping[str, str] | None = None,
    wrap: Sequence[str] = (),
    limit: int | None = None,
) -> str: ...
```

Run git in `cwd` and return what it printed, or raise `GitError` with what it said for an exit not in `ok`. Your
config applies, as it would to your own git, but for the settings that would run something or start a gc. `env`
is what this one call sets besides, such as the index and object store a snapshot's capture writes instead. `wrap`
is the isolation git runs in, in an isolated agent's tree, whose config the agent writes: there it runs on the same
allowlist its harness gets, never the runtime's whole environment, since the agent's config may name a program to
run on it. With `limit`, what it printed past `limit` bytes and one more is not read: git is ended there, as a
reader that stops ends what it reads from, and what comes back is then one byte longer than `limit`, whatever its
exit.

### `platoon_harness.runtime.git.GitError`

```python
class GitError(Exception): ...
```

What git said, or holds, that stops a workspace: its own words where it failed, ours where it holds what the
runtime did not make.

### `platoon_harness.runtime.git.head_at`

```python
def head_at(root: Path, *, wrap: Sequence[str] = ()) -> str | None: ...
```

The commit HEAD names in the work tree at `root`, as git run under `wrap` reads it, or None before its first
commit. Raises `GitError` where the work tree git finds is not the one at `root`, as around a folder that lost its
own repository, so another repository is never read as this one.

### `platoon_harness.runtime.git.SECONDS`

```python
SECONDS = 300.0
```

## `platoon_harness.runtime.host`

The host: what the journal asks of the world, one task per effect, and each harness heard in order.

### `platoon_harness.runtime.host.DriverLink`

```python
class DriverLink:
    def __init__(
        self, agent: str, role: str, driver: Driver, info: DriverInfo, *, pinned: str | None, login: Login | None
    ) -> None: ...
```

One harness as the host holds it. Links live on the `Host` and not in the daemon, so a restarted daemon loses
none. `pinned` is the model it must run and `login` what it runs on, as its access says. `leaving` means its end is
our doing. `ready` is set once `agent.start` commits, or nobody needs it to, or `refused` says why it never will.
`handing` is set to drop a handover under way.

**`refuse`**

```python
def refuse(self, why: str) -> None: ...
```

### `platoon_harness.runtime.host.GRACE`

```python
GRACE = 5.0
```

### `platoon_harness.runtime.host.Host`

```python
class Host:
    def __init__(
        self,
        kernel: Kernel,
        tools: ToolServer,
        team: Team,
        authority: Authority,
        folder: Path,
        cwd: Path,
        *,
        plan_login: bool,
        isolation: Isolation | None = None,
    ) -> None: ...
```

Performs effects from `v_effects`, level-triggered, so it holds no position that must survive a restart. One
agent's effects start in the order `effect.ready` allows, and `interrupt`, `stop` and `answer` go around that order
by their priority, each in its own task, so Esc works while a delivery hangs.

**`link`**

```python
def link(self, agent: str | None) -> DriverLink | None: ...
```

**`run`**

```python
async def run(self) -> None: ...
```

The daemon: notice what is ready, start it, and sleep until the journal moves.

**`insist`**

```python
async def insist(self, op: str, args: Mapping[str, Any]) -> Outcome: ...
```

Submit as the runtime. What left no event may be tried again, so it is, until the kernel closes, under one
key: a commit that failed may have landed all the same, and then the key answers from the journal.

**`admit`**

```python
async def admit(self, spawn: SpawnRequest) -> Admission: ...
```

Admit an agent and give it its credential: the raw token stays in memory, and only its hash is journaled. The
access it was admitted on is kept for this runtime's life, as a resume gives it back and no other agent shares a
gateway's bearer. A resumed admission that would not hold its agent to what it was is refused, and the agent is
lost, since its calls would go on an identity its record does not name.

**`workspace`**

```python
async def workspace(self, effect: Effect) -> dict[str, Any]: ...
```

Make an agent's workspace, or adopt what an earlier attempt of this effect made, since no agent starts in
one before its effect has finished. A mode that cannot be given fails loudly and never degrades: an isolated
one is a snapshot made only where its isolation can confine it now.

**`connect`**

```python
async def connect(
    self,
    agent: str,
    role: str,
    admission: Admission,
    *,
    goal: Mapping[str, Any] | None = None,
    resume: str | None = None,
) -> None: ...
```

Bring a harness up on its own binding, with `goal`, a spawn's goal and body, as its first delivery, under
the id of the offer that launched it. A gateway goes only to a driver that declares a sealed launch. An isolated
harness runs in its isolation, on access it was given, as a login of its own would be in your home, which it
never sees. A harness that never says it is ready is a failure, not a hang.

**`resume`**

```python
async def resume(self, agent: Mapping[str, Any]) -> None: ...
```

Bring an agent's harness back, as its record holds it, on a fresh credential: on its native session, or anew
when it took no turn, as it has written no session to reopen. With no native id or no resume it cannot come
back.

**`describe`**

```python
async def describe(self, role: str) -> DriverInfo: ...
```

What a role's driver says of itself, kept, because a wire program says it by running.

**`capabilities`**

```python
async def capabilities(self) -> dict[str, Capabilities]: ...
```

What each role's driver says it can do, by role. One that cannot say is left out, as unknown.

**`check_plan_login`**

```python
async def check_plan_login(self) -> None: ...
```

Refuse to bring back several agents headless on one plan login, before anything runs, unless the session was
started saying so, as a harness can be signed in on a plan between runs.

**`bundle`**

```python
async def bundle(self) -> dict[str, Any] | None: ...
```

Keep the commits the journal recorded in a bundle in the session folder, or None when it recorded none, as
git may prune one an agent rewrote. Git runs in an isolated agent's repository under its wrap.

**`reconcile`**

```python
async def reconcile(self, agent: str | None, key: str) -> Reconciled: ...
```

What a harness says became of what it was sent. With no harness to ask, or none that says in time, nobody
knows.

**`closing`**

```python
def closing(self) -> None: ...
```

Start nothing new but interrupts, and take no harness's end from here on as an agent's. A turn interrupted
from here on was the owner's doing, which a resume tells its agent.

**`close`**

```python
async def close(self, grace: float) -> None: ...
```

End every process tree, whatever a driver does, and drop whatever was in flight. A dropped effect stays
`started`, so the next runtime marks it uncertain, which is the truth. A launch cut short stays so too: a
harness that never said it was ready has not started.

## `platoon_harness.runtime.isolation`

**Experimental.** [STATUS](../STATUS.md): `isolated`.

Isolated workspaces: snapshots whose harness, and the runtime's own git in their tree, an extension's isolation
confines. The core says what an isolated agent may write and read, and the isolation makes it so. See architecture
section 13.

### `platoon_harness.runtime.isolation.hidden`

```python
def hidden(session: Path) -> tuple[Path, ...]: ...
```

What an isolated agent of `session` sees nothing of, of what is there: your home, as `HOME` names it and as your
account does, every session under its root, and the runtime directory sockets are made in.

### `platoon_harness.runtime.isolation.Isolation`

```python
class Isolation(Protocol): ...
```

What confines an isolated agent, which an extension gives as its `isolation`.

**`refusal`**

```python
def refusal(self) -> str | None: ...
```

Why it cannot confine anything on this machine now, or None when it can.

**`wrap`**

```python
def wrap(self, writable: Path, readable: Sequence[Path], hidden: Sequence[Path]) -> tuple[str, ...]: ...
```

The argv that runs a command after it so that it writes only in `writable` and a /tmp of its own, finds each
of `hidden` empty but for the `readable` paths in it, each as it resolves outside, and sees only the processes
it starts, which all end when it does. It keeps the network.

### `platoon_harness.runtime.isolation.isolation_of`

```python
def isolation_of(extensions: Iterable[Extension]) -> Isolation | None: ...
```

The isolation of the one extension among `extensions` that gives one, or None where none does or several do,
which a check before any cost refuses.

### `platoon_harness.runtime.isolation.problems`

```python
def problems(
    team: Team, known: Mapping[str, DriverInfo], extensions: Sequence[Extension], *, trainable: bool
) -> list[Problem]: ...
```

What stops a team's isolated roles before any cost: no extension the team names gives an isolation, or several
do; its isolation cannot confine here; a harness declares no installed path, so it would not run; or a harness
would sign itself in, as its login is in your home, which an isolated harness never sees. `known` is what each
role's driver says of itself, and `trainable` that a training system's gateway is every agent's access.

## `platoon_harness.runtime.looks`

A look: what git shows of one workspace now, read without changing any ref, index or file, for `repo.report`.

A look reads HEAD once and uses that commit in every later step. A commit is the agent's whose workspace's HEAD reflog
records making it: an entry that moved HEAD onto it at its own committer time, which git writes when the commit is made,
so it does not depend on which look runs first. See architecture section 13.

### `platoon_harness.runtime.looks.look`

```python
def look(
    root: Path,
    *,
    base: str | None,
    tips: Sequence[str],
    last: Mapping[str, Any] | None,
    makers: Mapping[str, tuple[Path, Sequence[str]]],
    record: bool,
    wrap: Sequence[str] = (),
) -> Seen: ...
```

Look at the workspace whose work tree is at `root`, with git run under `wrap`. Its new commits are those its HEAD
reaches that neither the session's `tips` at open, its `base` nor its `last` look's head reach. `makers` is every
workspace still on disk by name, with the wrap git runs under there, whose HEAD reflogs say who made each. With
`record`, its uncommitted state is read too.

### `platoon_harness.runtime.looks.PAGE`

```python
PAGE = 64
```

How many commits one `repo.report` carries.

### `platoon_harness.runtime.looks.Seen`

```python
@dataclass(frozen=True)
class Seen:
    commits: list[dict[str, Any]]
    rewrite: dict[str, Any] | None
    reading: dict[str, Any]
    whole: str | None
```

What a look found in one workspace: the commits it holds that are new, parents first and each after what it
cites, what its branch no longer reaches of what it did, its reading, and its whole list of paths, as text, when
the reading holds only part of it.

### `platoon_harness.runtime.looks.tips_of`

```python
def tips_of(text: str) -> list[str]: ...
```

The commits named in the tips a session opened on, one `<sha> <ref>` a line.

## `platoon_harness.runtime.opening`

From a team to a live session: checked before any cost, then journaled through ops, safe to repeat after a crash.

### `platoon_harness.runtime.opening.check`

```python
def check(
    team: Team,
    *,
    plan_login: bool = False,
    trainable: bool = False,
    approvals: Policy | None = None,
    cwd: str | Path | None = None,
    root: str | Path | None = None,
    name: str | None = None,
) -> tuple[Problem, ...]: ...
```

Every problem a session would meet in a team, errors and warnings, at once and before any cost, asking each
role's driver what it is, git what the session's `cwd` is in, and an isolated role's isolation whether it can
confine here. `root` and `name` say where the session's folder would be. A team that cannot be resolved raises
`ConfigError`.

`trainable` checks it as a training system starts it: what keeps the team from training, `trainable_problems`, under
the `approvals` it would run, and each role's driver for a sealed launch and a result kept under `root` that proves
trainable. Its agents run on the authority's gateway, so no plan login is theirs.

This blocks, because a driver may describe itself by running something, and git runs.

### `platoon_harness.runtime.opening.make_driver`

```python
def make_driver(role: Role, cwd: Path) -> Driver: ...
```

A new driver for a role's harness, by exact name, since a driver is one instance per agent. A relative program in
a command is the session's, so it resolves against the session's `cwd`, whatever its agent's workspace and wherever
it is described.

### `platoon_harness.runtime.opening.open_session`

```python
async def open_session(
    kernel: Kernel,
    team: Team,
    manifest: Manifest,
    text: str,
    capabilities: Mapping[str, Capabilities],
    repo: Mapping[str, Any] | None,
) -> None: ...
```

Journal a session through ops. Each step has a fixed key, so a crash part of the way is finished by the next
runtime, which runs this again, and a session that opened long ago is not disturbed, nor the `repo` it opened on.
`capabilities` is what each role's driver says, by role, and a role missing from it is unknown.

### `platoon_harness.runtime.opening.PLAN_LOGIN_FIX`

```python
PLAN_LOGIN_FIX = (
    "say this is your own work with `plan_login=True`, or `--plan-login` on the command line, or give each role an "
    "auth profile"
)
```

### `platoon_harness.runtime.opening.prepare`

```python
def prepare(
    team: Team,
    *,
    name: str | None = None,
    root: str | Path | None = None,
    principal: str = "human:you",
    approvals: Policy | None = None,
    cwd: str | Path | None = None,
    plan_login: bool = False,
    trainable: bool = False,
) -> Path: ...
```

Check a team and write down how it starts, before any cost, and who starts it, `principal`, a person or a
program. A session left to its program, under `until = "program"`, is a program's to start. `trainable` checks it as
a training system starts it. The folder is all a runtime then needs.

This blocks, because a driver may describe itself by running something.

### `platoon_harness.runtime.opening.repository`

```python
async def repository(kernel: Kernel, cwd: Path) -> dict[str, Any] | None: ...
```

The repository a session's `cwd` is in, as git says now, with its refs and tips stored as a body, or None.

### `platoon_harness.runtime.opening.told`

```python
async def told(team: Team) -> dict[str, str | None]: ...
```

What an agent of each role would be told at launch, which is all the runtime adds to its harness. It is rendered
on a session of its own, in a folder thrown away after, and no harness starts. A role nothing starts is shown as an
agent of its own name, started by an agent of a role that may start it, as an agent's name is its spawner's.

## `platoon_harness.runtime.paths`

Where a session lives: its root, its folder, its socket, and what a live runtime leaves beside its journal.

### `platoon_harness.runtime.paths.agent_folder`

```python
def agent_folder(session: Path, agent: str) -> Path: ...
```

An agent's own directory: its process record, its log, its native home, its `ph`.

### `platoon_harness.runtime.paths.CONFORMANCE`

```python
CONFORMANCE = "conformance"
```

### `platoon_harness.runtime.paths.find_root`

```python
def find_root(
    chosen: str | os.PathLike[str] | None = None, environ: Mapping[str, str] = os.environ, *, writing: bool = False
) -> Path: ...
```

Where sessions live: `chosen`, then `$PLATOON_HARNESS_HOME`, then `$XDG_STATE_HOME/platoon-harness`. One given
relatively is made absolute here, against the folder it was given in.

A default on a network filesystem falls back to a local directory, with a notice. A root someone chose stays theirs,
so `writing` there is refused: a closed session is portable, and a live journal is not. To write, a root must be
this user's and nobody else's to change, since what its folders say can run as this user on a resume.

### `platoon_harness.runtime.paths.HOME_VARIABLE`

```python
HOME_VARIABLE = "PLATOON_HARNESS_HOME"
```

### `platoon_harness.runtime.paths.Listed`

```python
class Listed(NamedTuple):
    name: str
    folder: Path
    live: bool
```

One session on disk. `live` is whether a runtime holds it now.

### `platoon_harness.runtime.paths.listing`

```python
def listing(root: Path) -> list[Listed]: ...
```

Every session under a root. There is no registry: a scan finds them, and `flock` says which are live.

### `platoon_harness.runtime.paths.LOG`

```python
LOG = "runtime.log"
```

### `platoon_harness.runtime.paths.MANIFEST`

```python
MANIFEST = "manifest.json"
```

### `platoon_harness.runtime.paths.MARKS`

```python
MARKS = "marks.sqlite"
```

### `platoon_harness.runtime.paths.new_folder`

```python
def new_folder(root: Path, manifest: str, name: str | None = None) -> Path: ...
```

Make a session's folder with its manifest in it. The folder is built aside and renamed into place, so a name is
claimed whole or not at all: no two sessions can share one, and a crash here burns none.

### `platoon_harness.runtime.paths.open_log`

```python
def open_log(folder: Path) -> int: ...
```

A descriptor on a runtime's log, for whichever side has to point stderr at it first.

### `platoon_harness.runtime.paths.OWNER_TOKEN`

```python
OWNER_TOKEN = "owner.token"
```

### `platoon_harness.runtime.paths.read_conformance`

```python
def read_conformance(root: Path, driver: str) -> Conformance | None: ...
```

What was kept under a root for a driver, or None when nothing was or what was is no result. Whether it speaks
for an agent is for its pin to say.

### `platoon_harness.runtime.paths.read_running`

```python
def read_running(folder: Path) -> Running | None: ...
```

The runtime a folder names, which may be a dead one's until the next takes over.

### `platoon_harness.runtime.paths.Running`

```python
class Running(Model):
    pid: int
    started: float
    socket: str
    incarnation: int
```

What a live runtime says of itself in `runtime.json`. Only the lock proves it is true.

### `platoon_harness.runtime.paths.RUNNING`

```python
RUNNING = "runtime.json"
```

### `platoon_harness.runtime.paths.root_of`

```python
def root_of(session: Path) -> Path: ...
```

The root a session's folder lives under, as `sessions_of` places it.

### `platoon_harness.runtime.paths.session_folder`

```python
def session_folder(root: Path, name: str) -> Path: ...
```

The folder of an existing session, or refuse. One made before names were held to git's grammar is named as no
longer valid, with the way to rename it.

### `platoon_harness.runtime.paths.sessions_of`

```python
def sessions_of(root: Path) -> Path: ...
```

The folder every session under a root lives in.

### `platoon_harness.runtime.paths.socket_path`

```python
def socket_path(session: Path, environ: Mapping[str, str] = os.environ) -> Path: ...
```

Where a session's socket goes: a hash of its folder, since a copy of a closed session keeps its journal and has a
folder of its own, in a private directory, never inside a folder of any depth, since a `bind` takes 107 bytes on
Linux and 103 on macOS. A runtime directory that cannot be used falls through to the next.

### `platoon_harness.runtime.paths.TESTS`

```python
TESTS = "tests"
```

Where in a session's folder each runtime test of a commit runs, in a folder named for its effect, gone once its
outcome is recorded.

### `platoon_harness.runtime.paths.VIEW_TOKEN`

```python
VIEW_TOKEN = "view.token"
```

### `platoon_harness.runtime.paths.write_conformance`

```python
def write_conformance(root: Path, result: Conformance) -> Path: ...
```

Keep what `check_driver` found of a driver's harness under a root, replacing what was kept for that driver, as
one result speaks for the binary that runs. A driver's name is a path part.

### `platoon_harness.runtime.paths.write_private`

```python
def write_private(path: Path, text: str) -> None: ...
```

Replace a file in one step, readable by this user alone, and on disk before this returns.

## `platoon_harness.runtime.recovery`

Recovery, after `Kernel.recover()`: per agent reap, resume and reconcile. Dispatch is the host's own loop.

Each effect kind follows its row in architecture section 5.4. Nothing here guesses: what cannot be known stays
uncertain, and is shown.

### `platoon_harness.runtime.recovery.recover_agents`

```python
async def recover_agents(kernel: Kernel, host: Host, folder: Path) -> None: ...
```

Take a session up again. A session that has stopped accepting work spends nothing: it is reaped and no more.

## `platoon_harness.runtime.workspaces`

Workspaces from git and the filesystem alone: checked before any cost, made in steps git keeps a fact of, so a retry
adopts what an earlier attempt made, and ended only when nothing would go with them.

Every git call goes through the one runner, which runs no hook, no fsmonitor and no gc. See architecture section 13.

### `platoon_harness.runtime.workspaces.BRANCHES`

```python
BRANCHES = "platoon-harness"
```

### `platoon_harness.runtime.workspaces.branch_of`

```python
def branch_of(session: str, agent: str) -> str: ...
```

An agent's branch, which no other session's can be, since a session's name is its own.

### `platoon_harness.runtime.workspaces.checkout`

```python
def checkout(sha: str, root: Path, repositories: Sequence[str]) -> None: ...
```

Check `sha` out at `root`, clean and detached, in a repository of its own that borrows the objects of those of
`repositories` still there, so nothing is written into any of them and none of their own config applies. A commit
none of them holds fails, saying so.

### `platoon_harness.runtime.workspaces.BUNDLE`

```python
BUNDLE = "commits.bundle"
```

### `platoon_harness.runtime.workspaces.end_snapshot`

```python
def end_snapshot(
    workspace: Workspace, folder: Path, checkout: Path, left: Sequence[str], *, retried: bool, wrap: Sequence[str] = ()
) -> dict[str, Any]: ...
```

Remove an ended agent's snapshot only when nothing would go with it, as git says, by the rule a worktree's end
follows, where the commits it alone holds are those of all its refs, its stash and its reflogs: it is renamed aside
first, so a crash part of the way leaves it whole or going, and its folder gone is taken as removed only where
that began or this stop is `retried`, since only a stop removes it. Otherwise it stays, made whole, so that your
repository's pruning cannot take what it borrowed. Git runs in it under `wrap`.

### `platoon_harness.runtime.workspaces.end_worktree`

```python
def end_worktree(workspace: Workspace, folder: Path, checkout: Path, left: Sequence[str]) -> dict[str, Any]: ...
```

Remove an ended agent's worktree only when nothing would go with it, as git says: its processes gone, which
`left` says were not, no path in its status, ignored ones included, no operation under way, no index entry hidden
from status while its file is there, and no commit its own HEAD, reflog or refs hold that is not its base or
reachable from a ref of your repository. Otherwise it stays, locked, and is named with why. Its branch always
stays. Each step is safe to repeat, so a stop retried after a crash finishes what the last one began.

### `platoon_harness.runtime.workspaces.make_snapshot`

```python
def make_snapshot(repo: Repo, folder: Path, branch: str, tips: Sequence[str], made_for: str) -> Workspace: ...
```

Make an agent's snapshot at `<folder>/workspace`: a repository of its own, on `branch`, holding your tree as your
git sees it now, uncommitted and untracked work included, as your HEAD or one runtime commit over it, captured
under your repository's own config, reading your objects through alternates and holding in its own store every
object the session's `tips` at open did not reach. It has no remote. It is built aside and renamed into place last,
so it is whole or absent: an attempt adopts a whole one, and takes back a part, which only the runtime writes, as
does one that fails. What `team check` refuses for a snapshot is refused again here, since your checkout may have
changed since. `made_for` names the session and the agent in its capture commit's message.

### `platoon_harness.runtime.workspaces.make_worktree`

```python
def make_worktree(repo: Repo, folder: Path, branch: str, effect: int) -> Workspace: ...
```

Make an agent's worktree at `<folder>/workspace`, on a new `branch` at your checkout's HEAD, in three steps git
keeps a fact of: the branch, made with a reflog naming `effect`; the registration, locked from its start with our
reason; and the fill. An attempt adopts what an earlier one of the same effect made, and fails, naming it, on a
branch, registration or folder the runtime did not make. No agent has run in it, which is what lets a fill reset
it, a half-written registration be made again, and a fill that failed take its worktree back. A branch is made only
where the session's subfolder is committed, so a spawn with nowhere to work makes nothing.

### `platoon_harness.runtime.workspaces.operations`

```python
def operations(root: Path, wrap: Sequence[str] = ()) -> dict[str, Path]: ...
```

What git keeps of each operation under way in a work tree, by its name in `UNDER_WAY`, in that table's order, as
git run under `wrap` says.

### `platoon_harness.runtime.workspaces.present`

```python
def present(workspace: Workspace, wrap: Sequence[str] = ()) -> None: ...
```

Refuse a git workspace a harness cannot run in: its folder gone, or no longer a work tree of its repository, as
git run under `wrap` says. Its branch and commits stay either way.

### `platoon_harness.runtime.workspaces.problems`

```python
def problems(team: Team, *, cwd: Path, folder: Path, session: str | None, approvals: Policy | None) -> list[Problem]: ...
```

What stops a team's workspaces, before any cost, and what a workspace will not carry, as warnings. `folder` is
where the session's folder will be, and `session` its name, when it has one yet. A mode that cannot be given is
refused here, wherever that can be seen, and never degrades to another. An isolated workspace is a snapshot, and
what its isolation needs is the isolation's to check.

### `platoon_harness.runtime.workspaces.read_repo`

```python
def read_repo(cwd: Path) -> tuple[dict[str, Any], str] | None: ...
```

The repository `cwd` is in, as git says now, all but its `tips`, and the text that names every ref and its tip,
to store as the body `tips` cites. None outside any work tree, and with no git to ask, where nothing is observed.

### `platoon_harness.runtime.workspaces.STATUS`

```python
STATUS = ("status", "--porcelain=v2", "-z", "--untracked-files=normal", "--ignore-submodules=none")
```

How the runtime asks for a work tree's status, whatever your config says of untracked files and submodules, so that
a look and a stop read the same paths.

### `platoon_harness.runtime.workspaces.status_of`

```python
def status_of(text: str) -> list[tuple[str, str, str]]: ...
```

Each path `git status --porcelain=v2 -z` names, as the kind of its entry, its index and work tree letters where
it has them, and the path: a rename's other path and the headers are passed over.

### `platoon_harness.runtime.workspaces.UNDER_WAY`

```python
UNDER_WAY = MappingProxyType(
    {
        "MERGE_HEAD": "merge",
        "rebase-merge": "rebase",
        "rebase-apply": "rebase",
        "CHERRY_PICK_HEAD": "cherry-pick",
        "REVERT_HEAD": "revert",
        "BISECT_LOG": "bisect",
        "sequencer": "sequence",
    }
)
```

What git keeps under a work tree's git directory while an operation is under way, and which operation it is. A
`sequence` is a cherry-pick or revert of several commits, between its picks.

### `platoon_harness.runtime.workspaces.write_bundle`

```python
def write_bundle(
    folder: Path, repo: Repo, commits: Sequence[str], repositories: Mapping[str, Sequence[str]]
) -> dict[str, Any]: ...
```

Keep every commit the journal recorded, past the session's starting HEAD, in one bundle in the session folder,
so that a commit an agent rewrote outlives git's pruning. It replaces the last one, and holds what that held, and
it is built in a repository of its own beside it that borrows the objects of `repositories`, each named with the
wrap git runs under there, so nothing is written into yours.

## `platoon_harness.schema`

What all configuration shares: frozen models, problems that name their place, and a TOML writer.

### `platoon_harness.schema.ConfigError`

```python
class ConfigError(ValueError):
    def __init__(self, problems: Collection[Problem]) -> None: ...
```

Configuration that cannot be used, with every problem found.

### `platoon_harness.schema.dumps`

```python
def dumps(data: Mapping[str, Any]) -> str: ...
```

TOML for nested mappings of strings, numbers, booleans and lists. A mapping of lists stays on one line.

### `platoon_harness.schema.Duration`

```python
Duration = Annotated[str, AfterValidator(_duration)]
```

A duration such as `30m`, held in its largest exact unit, so `60m` and `1h` are one value.

### `platoon_harness.schema.Model`

```python
class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
```

A configuration object: immutable, and refusing keys it does not declare. Input stays out of an error, even a
chained one, since a mistaken key may hold a secret.

**`canonical`**

```python
def canonical(self) -> dict[str, Any]: ...
```

Plain data with defaults left out, so a new default never disturbs an old form.

### `platoon_harness.schema.Name`

```python
Name = Annotated[str, StringConstraints(pattern=f"^{NAME}$")]
```

### `platoon_harness.schema.nearest`

```python
def nearest(name: str, known: Collection[str]) -> str: ...
```

A did-you-mean clause, or nothing when no known name is close.

### `platoon_harness.schema.Positive`

```python
Positive = Annotated[StrictInt, Field(gt=0)]
```

### `platoon_harness.schema.Problem`

```python
@dataclass(frozen=True)
class Problem:
    where: str
    what: str
    level: Literal["error", "warning"] = "error"
```

One thing wrong, at a dotted path into the configuration.

### `platoon_harness.schema.problems_in`

```python
def problems_in(
    error: ValidationError, model: type[BaseModel] | None = None, *, where: str = "", keys: Collection[str] = ()
) -> list[Problem]: ...
```

A validation error as problems. Input values stay out, since a mistaken key may hold a secret.

### `platoon_harness.schema.seconds`

```python
def seconds(duration: Duration | float) -> float: ...
```

A duration as seconds. A number already is one.

### `platoon_harness.schema.Sorted`

```python
Sorted = AfterValidator(_sorted)
```

Keeps a mapping in key order, so that equal configurations print alike.

## `platoon_harness.session`

The Session: one durable thing you start, attach to and resume, through one link, in-process or over a socket.

    async with Session.start(team, name="fix-auth") as session:
        await session.send("@lead", "Fix the flaky test")
        ending = await session.settled(timeout="30m")
    print(ending.agents[0]["report"]["gist"])

The owner's leaving stops the agents and keeps the folder. A guest's leaving only disconnects. `submit` returns the
kernel's `Outcome` and never raises a refusal; every typed method returns the result and raises `Refused`. A commit that
fails ends an owner's runtime, as a kill would, and from then on every call raises `JournalError`: `Session.resume` goes
on from what the journal holds.

### `platoon_harness.session.Ending`

```python
class Ending(BaseModel, frozen=True):
    state: str
    reason: Reason
    agents: tuple[dict[str, Any], ...]
    usage: dict[str, dict[str, Any]]
    gaps: tuple[dict[str, Any], ...]
    workspaces: tuple[dict[str, Any], ...] = ()
    unobserved: tuple[str, ...] = ()
```

What a session came to. `reason` is what an exit code is made from. Each of `agents` has its last `report`, a
`gist` and the ref of any `body`, or None if it said nothing. `usage` keeps its labels: a unit nobody measured has
no amount, which is not zero. Each of `workspaces` is one an agent's end did not take, with where it is, what it
takes on disk, why it stayed and, where some lose nothing it stayed for, the commands that let it go. `unobserved`
names the agents whose last look never finished, so what they last changed was not recorded.

### `platoon_harness.session.Reason`

```python
Reason = Literal["settled", "agent_failed", "budget_exhausted", "timed_out", "needs_human", "cancelled"]
```

### `platoon_harness.session.Session`

```python
class Session:
    def __init__(self, enter: Callable[["Session"], Awaitable[None]]) -> None: ...
```

A session, as its owner or as a guest. `Session.start`, `Session.attach` and `Session.resume` give one, to
`await` or to use in `async with`. The class holds one link, so everything below is written once.

**`start`**

```python
@classmethod
def start(
    cls,
    team: Team,
    *,
    name: str | None = None,
    principal: str = "human:you",
    approvals: Policy | None = None,
    authority: Authority | None = None,
    detach: bool = False,
    cwd: str | Path | None = None,
    root: str | Path | None = None,
    clock: Clock | None = None,
    plan_login: bool = False,
    trainable: bool = False,
) -> Self: ...
```

Start a team. You own it, unless `detach` starts a runtime of its own and gives you a guest.

`principal` is who you are in the journal, a name and not a claim, as identity comes from the credential: a
person, `human:<name>`, or a program, `program:<name>`. A program's session issues no owner credential, as
whoever held it would act as that program, so a guest of it holds a view credential, and it cannot detach.
`approvals` states a policy over every role's own, which is durable, so it is said here and not when you wait.
`plan_login` says several agents may run headless on one plan login, which is refused otherwise. `trainable`
checks the team as a training system starts it, which an `authority` admits through its gateway, before any
harness launches.

**`resume`**

```python
@classmethod
def resume(
    cls, name: str, *, detach: bool = False, root: str | Path | None = None, clock: Clock | None = None
) -> Self: ...
```

Restart a session whose runtime has gone. This is its own verb because restarting can spend money. Harnesses
come back on fresh credentials, which the session issues, or their agents are lost, with a gap. A session
started trainable, or whose agents an authority admitted with the backend's ids, is refused: their keys went
with it. A program's session cannot detach, as at its start.

**`attach`**

```python
@classmethod
def attach(cls, name: str, *, view: bool = False, root: str | Path | None = None) -> Self: ...
```

Join a session as a guest. It has no side effects: with no live runtime it gives read-only history, and a
write is refused `unavailable`, naming the command that restarts it. `view` holds a view credential, which reads
and never writes.

**`name`**

```python
@property
def name(self) -> str: ...
```

**`owner`**

```python
@property
def owner(self) -> bool: ...
```

Whether leaving stops the agents.

**`leave`**

```python
async def leave(self, grace: Duration | float = GRACE) -> None: ...
```

Go. An owner interrupts turns, waits `grace` and ends the process trees, keeping the folder resumable. A
guest only disconnects, and changes nothing.

**`submit`**

```python
async def submit(self, op: str, /, *, key: str | None = None, **args: Any) -> Outcome: ...
```

Run an op by name and return the kernel's `Outcome`, refusal and all. A retry under one `key` is one
operation, and the link retries under this one on its own when a runtime goes.

**`spawn`**

```python
async def spawn(
    self,
    name: str,
    role: str,
    goal: str = "",
    *,
    body: str | bytes | None = None,
    stays: bool | None = None,
    labels: Mapping[str, str] | None = None,
    based_on: Sequence[str] = (),
) -> dict[str, Any]: ...
```

Start an agent in a role, and give its `ref`. With no `goal` and no `body` it starts idle until a message
wakes it. `stays` says whether it is told to stay after its task for the next message, rather than to finish:
left out, its role decides, else it does not. `labels` say what kind of work it is to do, by the team's.

**`status`**

```python
async def status(self, agent: str | None = None) -> dict[str, Any]: ...
```

How this session stands, or one agent.

**`agents`**

```python
async def agents(self) -> list[dict[str, Any]]: ...
```

**`unread`**

```python
async def unread(self, agent: str) -> dict[str, Any]: ...
```

What waits for an agent's next handover, oldest first, which the roster's `unread` counts: each entry with
the `delivery` it would land by now, and the true `total`.

**`interrupt`**

```python
async def interrupt(self, agent: str, *, below: bool = False) -> dict[str, Any]: ...
```

Stop an agent's turn, and with `below` the turns of every agent below it, and say whose. It stops turns, not
waits, and every agent lives on.

**`cancel_agent`**

```python
async def cancel_agent(self, agent: str) -> None: ...
```

End one agent now.

**`retire`**

```python
async def retire(self, agent: str) -> None: ...
```

Take an agent that has stopped working out of the team. Its history stays.

**`hold`**

```python
async def hold(self, agent: str) -> None: ...
```

Hold an agent's deliveries until `release`.

**`release`**

```python
async def release(self, agent: str) -> None: ...
```

Hand a held agent back.

**`close`**

```python
async def close(self) -> None: ...
```

Drain: nothing new starts, and what is in flight finishes.

**`cancel`**

```python
async def cancel(self) -> None: ...
```

Stop now: every live agent ends.

**`open_episode`**

```python
async def open_episode(self, episode: str) -> None: ...
```

**`close_episode`**

```python
async def close_episode(self, *, based_on: Sequence[str] = ()) -> None: ...
```

Close the open episode on the refs of what it came to. What it is worth is an annotation's to say.

**`wait`**

```python
async def wait(
    self,
    *,
    on: Sequence[Condition] = (),
    agents: Sequence[str] = (),
    senders: Sequence[str] = (),
    tasks: Sequence[str] = (),
    board: Sequence[str] = (),
    channels: Sequence[str] = (),
    queue: Sequence[str] = (),
    mode: Literal["all", "any"] = "all",
    after: int | None = None,
    timeout: Duration | float | None = None,
) -> dict[str, Any]: ...
```

Wait until the condition holds or `timeout` passes, and say how it closed. The wait lives in the service, so
losing this client loses nothing.

**`cancel_wait`**

```python
async def cancel_wait(self, id: int | None = None) -> None: ...
```

**`wait_progress`**

```python
async def wait_progress(self, id: int | None = None) -> dict[str, Any] | None: ...
```

**`metrics`**

```python
async def metrics(self) -> Metrics: ...
```

How this session runs: what its record counts, the roster's groups, and what its runtime has measured since
it started, each None where nothing measured it, with why in `unknown`.

**`ending`**

```python
async def ending(self) -> Ending: ...
```

What this session has come to so far.

**`settled`**

```python
async def settled(self, timeout: Duration | float | None = None) -> Ending: ...
```

Wait for `session.status` to say done, close at `until`, and say what the session came to. Past `timeout` it
says `timed_out`, and with something only a person can move it says `needs_human`. Both leave it as it is.

**`send`**

```python
async def send(
    self,
    to: str,
    gist: str,
    *,
    body: str | bytes | None = None,
    thread: str | None = None,
    reply_to: str | None = None,
    based_on: Sequence[str] = (),
) -> dict[str, Any]: ...
```

Send to `@agent`, `#channel` or `+group`. `gist` is what readers see first, and `body` anything longer.

**`reply`**

```python
async def reply(self, entry: Mapping[str, Any], gist: str, *, body: str | bytes | None = None) -> dict[str, Any]: ...
```

Answer an entry from `read`.

**`read`**

```python
async def read(
    self,
    channel: str | None = None,
    *,
    after: int | None = None,
    limit: int = 32,
    sender: str | None = None,
    thread: str | None = None,
    bodies: bool = False,
) -> dict[str, Any]: ...
```

Read your inbox, `#channel` or `+group`. A human's read writes nothing and moves no cursor.

**`channels`**

```python
async def channels(self, *, after: str | None = None) -> dict[str, Any]: ...
```

**`peers`**

```python
async def peers(self, *, after: str | None = None) -> dict[str, Any]: ...
```

**`create_channel`**

```python
async def create_channel(
    self,
    name: str,
    kind: Literal["topic", "queue", "board"],
    *,
    readers: Sequence[str] = (),
    writers: Sequence[str] = (),
    delivery: str | None = None,
) -> dict[str, Any]: ...
```

**`board_post`**

```python
async def board_post(
    self,
    board: str,
    name: str,
    gist: str,
    *,
    body: str | bytes | None = None,
    fields: Mapping[str, Any] | None = None,
    based_on: Sequence[str] = (),
) -> dict[str, Any]: ...
```

Create an object on a board, at version 1.

**`board_revise`**

```python
async def board_revise(
    self,
    board: str,
    name: str,
    gist: str,
    expected_version: int,
    *,
    body: str | bytes | None = None,
    fields: Mapping[str, Any] | None = None,
    based_on: Sequence[str] = (),
) -> dict[str, Any]: ...
```

Add a version, if `expected_version` is still the latest. Nothing is ever overwritten.

**`board_get`**

```python
async def board_get(
    self, board: str, name: str, *, version: int | None = None, range: str | None = None
) -> dict[str, Any]: ...
```

**`board_query`**

```python
async def board_query(
    self,
    board: str,
    *,
    prefix: str | None = None,
    author: str | None = None,
    where: Mapping[str, Any] | None = None,
    text: str | None = None,
    history: bool = False,
    after: int = 0,
    limit: int = 20,
) -> dict[str, Any]: ...
```

Find objects on a board. Results carry exact refs and the true total.

**`task_add`**

```python
async def task_add(
    self,
    queue: str,
    gist: str,
    *,
    body: str | bytes | None = None,
    labels: Mapping[str, str] | None = None,
    based_on: Sequence[str] = (),
) -> dict[str, Any]: ...
```

Add a task to a queue. `labels` say what kind of task it is, by the team's.

**`task_claim`**

```python
async def task_claim(self, queue: str, *, task: str | None = None) -> dict[str, Any]: ...
```

**`task_renew`**

```python
async def task_renew(self, queue: str, *, task: str | None = None, fence: int | None = None) -> dict[str, Any]: ...
```

**`task_release`**

```python
async def task_release(self, queue: str, *, task: str | None = None, fence: int | None = None) -> None: ...
```

Give a task back, which spends no attempt.

**`task_complete`**

```python
async def task_complete(
    self,
    queue: str,
    *,
    task: str | None = None,
    fence: int | None = None,
    gist: str = "",
    body: str | bytes | None = None,
    based_on: Sequence[str] = (),
) -> None: ...
```

**`task_fail`**

```python
async def task_fail(
    self,
    queue: str,
    *,
    task: str | None = None,
    fence: int | None = None,
    gist: str = "",
    body: str | bytes | None = None,
    based_on: Sequence[str] = (),
) -> None: ...
```

**`task_list`**

```python
async def task_list(
    self, queue: str, *, state: str | None = None, after: int = 0, limit: int = 32
) -> dict[str, Any]: ...
```

**`attention`**

```python
async def attention(self) -> list[dict[str, Any]]: ...
```

Where a human must act now, each with the actions that would settle it.

**`approvals`**

```python
async def approvals(self) -> list[dict[str, Any]]: ...
```

What waits on a decision. `id` and `version` are what `resolve` takes.

**`resolve`**

```python
async def resolve(
    self, id: str, verdict: Verdict, *, expected_version: int, via: str | None = None
) -> dict[str, Any]: ...
```

Decide an approval. The first commit wins, and the loser is refused `conflict`, told who won.

**`settle_effect`**

```python
async def settle_effect(self, id: int, happened: bool) -> None: ...
```

Say whether an uncertain effect happened, which is what an `uncertain` row of `attention` asks.

**`budgets`**

```python
async def budgets(self) -> list[dict[str, Any]]: ...
```

**`set_budget`**

```python
async def set_budget(
    self,
    scope: str = "shared",
    *,
    limits: Mapping[str, float] | None = None,
    estimate: Mapping[str, float] | None = None,
) -> None: ...
```

Set a scope's limits and what a turn is estimated at, which a `tokens` or `usd` limit needs.

**`manifest`**

```python
async def manifest(self) -> dict[str, Any]: ...
```

**`ops`**

```python
async def ops(self) -> list[dict[str, Any]]: ...
```

**`events`**

```python
async def events(
    self,
    after: int = 0,
    match: str | None = None,
    *,
    streams: Sequence[str] | None = None,
    follow: bool = False,
) -> AsyncGenerator[Event]: ...
```

Each event past `after` whose stream `match` globs, or `streams` names. Resume from any event's `seq`. With
`follow` this goes on as the journal grows, until nothing more can come. It is a read plus a long-poll,
in-process or not.

**`page`**

```python
async def page(
    self,
    *,
    after: int = 0,
    before: int | None = None,
    match: str | None = None,
    streams: Sequence[str] | None = None,
    limit: int = 256,
) -> Page: ...
```

A page of events past `after`, or with `before` the newest below it, in order, so a transcript pages back
without reading the journal whole. A filtered page scans at most 4,096 events, so it can be empty with more to
come: pass `cursor` as the next `after`, or as the next `before`, which is `after` once nothing is left.

**`head`**

```python
async def head(self) -> int: ...
```

The `seq` of the newest event now, after which a follower of only what comes next starts.

**`deltas`**

```python
async def deltas(self, agent: str) -> AsyncIterator[Delta]: ...
```

An agent's live text as it comes. It is lossy: `lag` counts what was lost, and the item that follows is the
truth.

**`watch`**

```python
async def watch(self, view: Literal["roster", "attention", "changes"]) -> AsyncIterator[dict[str, Any]]: ...
```

A snapshot of a view, then its keyed changes, until nothing more can come.

**`marks`**

```python
async def marks(self) -> dict[str, int]: ...
```

How far you have read each stream, as you marked it, by stream: where a badge counts from. A mark is neither
evidence nor a view, and an agent's cursor is no mark, so losing `marks.sqlite` loses only these.

**`mark`**

```python
async def mark(self, stream: str, seq: int) -> None: ...
```

Mark that you have read `stream` through `seq`. A mark only moves forward. It writes no event and
acknowledges nothing an agent was handed, with a runtime or without one, and a view credential moves none.

**`put_body`**

```python
async def put_body(self, body: bytes) -> str: ...
```

Store a body and return its ref, which `body=` takes. An orphan is harmless.

**`get_body`**

```python
async def get_body(self, ref: str, *, limit: int | None = None) -> bytes: ...
```

A stored body's bytes, by a `body` from any result.

**`blob`**

```python
async def blob(self, ref: str) -> dict[str, Any]: ...
```

The text of the body an event carries, by the event's ref or a `rest` from any result.

**`tombstone`**

```python
async def tombstone(self, ref: str) -> None: ...
```

Redact a body: reads stop now, and its bytes follow. Events citing its hash stay whole.

**`repo_commit`**

```python
async def repo_commit(self, sha: str) -> dict[str, Any]: ...
```

A recorded commit's `ref`, which `based_on` cites, its full `sha`, its `gist` and the workspace it was
`made_in`, by its SHA or its first 4 or more hex digits.

**`repo_test`**

```python
async def repo_test(self, commit: str) -> int: ...
```

Ask for a runtime test of a recorded commit, which runs that commit's maker's code as you, unconfined: the
team's `test` command, in a clean detached checkout of it. Its effect, which `repo.tested` names with what it
came to.

**`repo_diff`**

```python
async def repo_diff(self, of: str) -> dict[str, Any]: ...
```

Ask for the patch of a recorded commit, by its SHA or its first 4 or more hex digits, or for what a
workspace, `@ada` or `shared`, holds uncommitted, which the runtime reads where that workspace lives and keeps
as `repo.diffed`: the `effect` that reads it, which that names, and for a commit whose patch is kept, its
`ref` too.

**`exposure`**

```python
async def exposure(self, agent: str, ref: str, *, before: str | None = None) -> Seen | NotSeen | Unknown: ...
```

Whether the event `ref` reached `agent` through us before the event `before`, or by now: `Seen`, `NotSeen` or
`Unknown`, each with why, and never a boolean.

**`shown`**

```python
async def shown(self, offer: str) -> tuple[str | None, ...]: ...
```

The text each item of an offer showed, by the offer's ref, in its order: a gist as it was shown, with any
fields beside it, and a body or the lines of one, where the journal proves it by the item's digest, and None
where it does not, as for a body redacted since or one past 64 KiB.

**`lineage`**

```python
async def lineage(self, ref: str, *, after: str | None = None) -> Lineage: ...
```

One hop back from an event: who made it, what it cites with its citer's exposure, what it followed from, its
ancestry, and a page of what its maker was offered and the gaps in its record. Pass `cursor` as `after`.

**`uses`**

```python
async def uses(self, ref: str, *, after: str | None = None) -> Uses: ...
```

One hop forward from an event: what cites it, what follows from it, its next version or the commits it is a
parent of, and each agent it was offered to. Pass `cursor` as `after`.

**`contributors`**

```python
async def contributors(self, ref: str, *, after: str | None = None) -> Contributors: ...
```

Each maker a walk back from an outcome reaches, and apart from them each maker whose work was only handed to
one of them: reachability in the record, never credit. Pass `cursor` as `after`.

**`eligibility`**

```python
async def eligibility(self, agent: str, episode: str, *, after: str | None = None) -> Eligibility: ...
```

Whether an agent's work in one episode can train, from the record alone: its attribution, `exact`, `forked`
or None, and its verdict with every bar, and the same for a page of its model calls. It reads the levels its
starts recorded, never a result kept since. Pass `cursor` as `after` for the next page.

**`spans`**

```python
async def spans(self, agent: str, *, after: str | None = None) -> Spans: ...
```

Each span of an agent, oldest first: each turn of it cut after each model call that chose a write of
content, as the record joins them, each span named by its last call's `model.called`, with its first call, its
turn, its writes, the claims its agent held while its calls were made and the labels of the work it was done
for, None where unknown. Pass `cursor` as `after` for the next page.

**`interactions`**

```python
async def interactions(self, *, after: str | None = None) -> Interactions: ...
```

Who reached whom, from the record: a page of pairs of makers, each with how many edges of each kind lead
from the first's events to the second's, counted apart and never summed, and how many offers between them are
unknown, with each agent's unknowns. Every page is read at the first one's head: pass `cursor` as `after`.

**`annotate`**

```python
async def annotate(
    self,
    target: str,
    *,
    kind: Literal["reward", "credit"],
    producer: str,
    producer_version: str,
    scope: Literal["local", "team"],
    status: Status,
    head_seq: int,
    value: float | None = None,
    params: Mapping[str, Any] | None = None,
    evidence: Sequence[str] = (),
) -> Annotation: ...
```

Say what an estimator found of an event, a `reward` or a `credit`, in `annotations.sqlite` beside the journal
and never in it, on a live session or a closed one, with no runtime. It is `producer`'s at `producer_version`,
run with `params`, of the trace up to `head_seq`, at or below which the target and each ref of `evidence` lie:
an estimate, never a fact. `status` is `scored`, `invalid`, `error`, `timeout` or `cancelled`, and `value` is
given when it is `scored` alone, so no other is ever zero; with no statement a target is unscored. The same
statement again is answered with the first, and another under the same producer, version, params, target and
kind is refused `conflict`.

**`annotations`**

```python
async def annotations(self, target: str | None = None) -> list[Annotation]: ...
```

What estimators said of one event, or of every one, oldest first, each with its producer and version and
never summed. Nothing an agent can reach reads these.

## `platoon_harness.team`

A team: roles plus a topology, as a file or a Python object.

### `platoon_harness.team.AuthProfile`

```python
class AuthProfile(Model):
    env: tuple[EnvName, ...]
```

Which environment variables a harness receives. Names only: a value never enters configuration.

### `platoon_harness.team.Budget`

```python
class Budget(Model):
    tokens: Positive | None = None
    usd: Amount | None = None
    turns: Positive | None = None
    agents: Positive | None = None
    wall: Duration | None = None
    estimate: Annotated[Mapping[Literal["tokens", "usd"], Amount], Sorted] = {}
```

Limits on a session or a role. `estimate` is what one turn is reserved in `tokens` or `usd` before it is
measured, and charged on top of what was measured when nobody measured it whole, so a limit in either needs one.

### `platoon_harness.team.Capabilities`

Imported from [`platoon_harness.primitives.Capabilities`](#platoon_harnessprimitivescapabilities).

### `platoon_harness.team.Command`

```python
class Command(Model):
    command: Annotated[tuple[str, ...], Field(min_length=1)]
    mode: Literal["oneshot", "wire"] = "oneshot"
```

A harness given as a command line: a `oneshot` CLI run by the `exec` driver, or a `wire` driver program.

### `platoon_harness.team.Role`

```python
class Role(Model):
    harness: str | Command
    model: str | None = None
    effort: str | None = None
    preamble: Template | None = None
    instructions: str | None = None
    auth: str | None = None
    workspace: Literal["shared", "worktree", "snapshot", "isolated"] = "shared"
    sandbox: str | None = None
    allow_native_children: StrictBool = False
    tools: tuple[str, ...] = ("*",)
    delivery: Injection = "wake"
    inbox_depth: Positive = 1024
    may_spawn: tuple[str, ...] = ()
    count: Annotated[StrictInt, Field(ge=0)] | None = None
    stays: StrictBool | None = None
    on_parent_exit: Literal["cancel-subtree", "adopt"] = "cancel-subtree"
    approvals: Policy = "ask"
    budget: Budget = Budget()
```

A template for agents. `tools` lists op globs, and only ever narrows what the topology grants.

`count` is how many start with the session: left out, one, or none if another role spawns this one. `delivery` is
how a message reaches this role's inboxes, and `inbox_depth` how many entries one holds before refusing more.
`effort` goes to the harness as it stands, and a harness that cannot honor it fails the spawn. `stays` says whether
an agent is told to stay after its task for the next message, rather than to finish, which one that does not stay
does with a turn that leaves nothing more to come for it: left out, one the session started stays and one spawned
does not, and a spawn may say otherwise either way. `on_parent_exit` says what becomes
of an agent whose parent ends: `cancel-subtree` ends it too, `cancelled` if a turn of its was cut off and `retired`
otherwise, and `adopt` gives it to the session. `allow_native_children` lets its harness start agents of its own,
beside ours, which a role on a harness whose driver cannot turn them off, as on ACP, must say. `preamble` is the
template of what its agents are told before `instructions`, its own words, in place of the team's.

**`driver`**

```python
@property
def driver(self) -> str: ...
```

The name this role's harness goes by among drivers.

### `platoon_harness.team.Team`

```python
class Team(Model):
    extensions: tuple[str, ...] = ()
    preamble: Template = PREAMBLE
    roles: Annotated[Mapping[Name, Role], Field(min_length=1), Sorted]
    auth: Annotated[Mapping[Name, AuthProfile], Sorted] = {}
    budget: Budget = Budget()
    topology: Topology = Topology()
    test: Test | None = None
    labels: Annotated[Mapping[Name, Values], Sorted] = {}
```

Roles plus a topology. It says what may happen, never what happens next. `preamble` is the template of what every
agent is told before its role's words, unless its role gives its own. `test` is what a runtime test of a commit
runs, if the team names one. `labels` say what kinds of work it does: each label a name with the values it may
take, of which whoever adds a task or spawns an agent may give one for each label, and nothing outside them.

**`loads`**

```python
@classmethod
def loads(cls, text: str) -> Self: ...
```

A team from TOML text alone. `load_team` layers one over the user's and project's config.

**`spawners`**

```python
def spawners(self, role: str) -> set[str]: ...
```

The roles that may spawn `role`, by `may_spawn` or by a written grant, which is the same thing.

**`starts`**

```python
def starts(self, role: str) -> list[str]: ...
```

The agents of `role` that start with the session: one by the role's name, or a numbered one for each of
its `count`.

**`recipients`**

```python
def recipients(self, to: str | None = None) -> tuple[str, ...]: ...
```

Whom a session's prompt goes to, as `@agent`: the agent `to` names, which the session must start, or else
every agent it starts.

**`preamble_of`**

```python
def preamble_of(self, role: str) -> str: ...
```

The template of what `role`'s agents are told before its words: its own, else the team's.

**`resolved`**

```python
def resolved(self, extensions: Mapping[str, Extension] | None = None) -> Self: ...
```

This team with every preset expanded, using the extensions it names from `extensions`.

**`show`**

```python
def show(self, *, resolved: bool = False) -> str: ...
```

English sentences, or with `resolved` the TOML expansion, which is valid input.

### `platoon_harness.team.team_check`

```python
def team_check(
    team: Team, *, capabilities: Mapping[str, Capabilities], extensions: Mapping[str, Extension] | None = None
) -> tuple[Problem, ...]: ...
```

Every problem with a team, at once, before any cost. Pure: all it knows arrives as arguments.

`capabilities` maps harness names, or a role's own name where its command decides, to what is known of them, and
`extensions` maps the references a team may name to their extensions. Errors stop a team from running; warnings do
not.

### `platoon_harness.team.Test`

```python
class Test(Model):
    command: Annotated[tuple[str, ...], Field(min_length=1)]
    timeout: Duration
```

What the runtime runs at a recorded commit when a person or a program asks: `command`, in a clean detached
checkout of that commit, as you and unconfined, ended at `timeout`, which is then an error and not a failure.

### `platoon_harness.team.trainable_problems`

```python
def trainable_problems(team: Team, *, approvals: Policy | None = None) -> tuple[Problem, ...]: ...
```

What keeps a team from training, read from the team alone, with no driver to ask: a model or an auth profile a
role names, as a training system's gateway gives both; approvals left to `ask`, which nobody answers in a rollout,
by `approvals`, a session's policy over every role's own, or else by a role's; a harness's own agents allowed, whose
calls go on their parent's key; a workspace other than `shared` or `isolated`; and an `until` only a person
reaches.

## `platoon_harness.testing`

What proves a driver or an extension: a deterministic harness, a loopback model, and named checks.

### `platoon_harness.testing.Ask`

```python
@dataclass(frozen=True)
class Ask:
    gist: str
    body: str | None = None
```

Ask for an approval, and hold the turn until it is answered. `body` is the whole of what it asks, and None says
nothing of it.

### `platoon_harness.testing.AskModel`

```python
@dataclass(frozen=True)
class AskModel: ...
```

Behave like a harness: ask the model at `spec.access`, run what it calls, and go on until it only talks. A tool
that is neither ours nor the environment's is gated, as a harness gates its shell, and on a gateway is no tool at
all, as a sealed launch has none of its own.

### `platoon_harness.testing.Call`

```python
@dataclass(frozen=True)
class Call:
    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
```

Call a tool by the name the model is shown, as real MCP: one of ours, or on a gateway one of the environment's.
Its result lands in `ScriptedDriver.results`.

### `platoon_harness.testing.chat_access`

```python
def chat_access(model: FakeModel) -> dict[str, Secret]: ...
```

Model access for a harness that speaks Chat Completions, with a dummy key.

### `platoon_harness.testing.check_driver`

```python
async def check_driver(
    factory: Factory,
    *,
    folder: Path,
    access: Access = chat_access,
    garble: Garble | None = None,
    gated: Gated = _gated,
    shell: Shell | None = None,
    tool: Tool = _tool,
    child: ToolCall | None = None,
    kept: Sequence[str] = (),
    model: str = _MODEL,
    timeout: float = 10.0,
) -> Conformance: ...
```

Run every check on fresh instances of a driver, and report all failures at once, pinned to the driver, the
harness version it reported, the class that implements it, this SDK and this host. `levels` reads the result.

`factory` makes one instance per check. `access` says how a harness reaches the model. `garble` makes the harness
write a frame no parser knows, and with none that check is skipped. `gated` turns a command into a tool call this
harness asks approval for, and `shell` into one that runs it, with none of which the check of a stop during a
running tool is skipped. `tool` turns a note into a call of our tool, by the name this harness's model knows it by.
`child` is a tool call that starts a native child, and with none that check is skipped. `kept` names each tool of
the harness's own that a sealed launch keeps, which acts on nothing. `model` is what a role names FakeModel by on
this harness, which asks FakeModel for it by its own name. `timeout` bounds each check, so one wedged harness costs
only its own checks.

### `platoon_harness.testing.check_extension`

```python
async def check_extension(extension: Extension, *, folder: Path, scenario: Scenario | None = None) -> ExtensionChecks: ...
```

Load an extension beside the primitives and report every problem the checks find at once, and each part no check
runs. `scenario` runs some of it on a live kernel in `folder`, so that its views can be compared with a rebuild. A
check that could not run is skipped, saying why, which is no pass: `rebuild_equals_live` with no scenario or where
the kernel refuses the extension, and, as the kernel stops loading at its first fault, the other of `names` and
`naming_law` where one fails. A folder no kernel can open is refused, as `Kernel.open` refuses it.

### `platoon_harness.testing.check_harness`

```python
async def check_harness(name: str, folder: Path) -> Conformance: ...
```

Run every check on the harness `name` as it is installed here, against FakeModel, in `folder`, and say what it
found, pinned to the driver, the harness version that answered, this SDK and this host: the SDK's own check of a
harness `CHECKED` names, or else the check the installed driver of that name names in its `DriverInfo.check`. What
that check found is refused if it names another harness, or another class than that driver's, as it would speak for
a driver it did not check, and a check that breaks, or finds no `Conformance`, is refused, saying why. A harness no
check ships for is refused.

### `platoon_harness.testing.Compact`

```python
@dataclass(frozen=True)
class Compact: ...
```

Compact the context as a harness does: one model call asks for a summary, with the compaction headers a gateway
gave, and what was said gives way to that summary.

### `platoon_harness.testing.Do`

```python
@dataclass(frozen=True)
class Do:
    act: Callable[[AgentSpec, Callable[[str, Mapping[str, Any]], Awaitable[Any]]], Awaitable[None]]
```

Run code of the harness's own, as `act(spec, call)`: `spec` is the agent's, and `call(tool, arguments)` calls a
tool as a `Call` step does and returns its result, so what the code does next can rest on what each call answered.
Each call goes under an id of its own, as a harness's own calls do, so no two are one call.

### `platoon_harness.testing.EndTurn`

```python
@dataclass(frozen=True)
class EndTurn:
    reason: str = "stopped"
```

End the turn here, and drop its other steps.

### `platoon_harness.testing.ENVIRONMENT_TOOL`

```python
ENVIRONMENT_TOOL = "ping"
```

The environment's tool that FakeModel serves as a gateway, at `/mcp`, for a test to call.

### `platoon_harness.testing.ENVIRONMENT_TOOLS`

```python
ENVIRONMENT_TOOLS = (ENVIRONMENT_TOOL, "finish", "think")
```

Every tool of the environment's own that FakeModel serves, each answering pong: `finish` and `think` are named as
harnesses name tools of their own, which a harness that showed the environment's tools bare would collide with.

### `platoon_harness.testing.every_turn_asks_the_model`

```python
def every_turn_asks_the_model() -> Iterable[Sequence[Step]]: ...
```

The script conformance uses, so the model's replies decide everything, as they do for a real harness.

### `platoon_harness.testing.Exit`

```python
@dataclass(frozen=True)
class Exit:
    reason: str = "the harness exited"
```

The harness exits, in the middle of whatever it was doing.

### `platoon_harness.testing.ExtensionChecks`

```python
class ExtensionChecks(Checks):
    unchecked: tuple[str, ...]
```

What `check_extension` found, and `unchecked`: each part the extension declares that no check runs, its
daemons, its presets and its isolation, saying what that leaves unknown, so a pass never reads as more than the
checks ran.

### `platoon_harness.testing.Fail`

```python
@dataclass(frozen=True)
class Fail:
    reason: str = "failed"
```

End the turn on an error of the harness's own.

### `platoon_harness.testing.goal`

```python
def goal(text: str) -> Delivery | None: ...
```

A goal as the runtime hands one to a harness on a fresh start: its first delivery, under the id of the offer that
launched it, which `input.delivered` echoes, or None for no goal.

### `platoon_harness.testing.FakeModel`

```python
class FakeModel:
    def __init__(self, *replies: Reply) -> None: ...
```

A scripted model. Each model call takes the next reply, and past the script's end the model says "ok".

`async with FakeModel("hello", ToolCall("ping")) as model:` serves on loopback at `model.url`. `model.requests` logs
everything that arrived, with its bearer and headers, and `model.calls` what was a model call. `await model.call(0)`
waits for one. `model.gateway(bearer)` is access to it as a training system's gateway gives it. `model.answer` has
a function reply to the calls whose request says a text, such as one agent's name, in place of the script.

**`url`**

```python
@property
def url(self) -> str: ...
```

The server's origin. Clients differ on whether a base holds `/v1`, and a path that ends right routes.

**`calls`**

```python
@property
def calls(self) -> list[Request]: ...
```

**`tool_calls`**

```python
@property
def tool_calls(self) -> list[Request]: ...
```

Each call of the environment's tool its MCP server answered.

**`gateway`**

```python
def gateway(self, bearer: str) -> Gateway: ...
```

Access to this model as a training system's gateway gives it, under `bearer`: its models at its origin, the
environment's tools at `/mcp`, which answer only a bearer it gave, and `COMPACTION_HEADERS` for each call that
compacts a context.

**`script`**

```python
def script(self, replies: Iterable[Reply]) -> None: ...
```

Add to what the model will say.

**`answer`**

```python
def answer(self, saying: str, reply: Callable[[Request], Reply]) -> None: ...
```

Answer each model call whose request says `saying` with what `reply` gives for that request, and not from the
script. A call goes to the first such function whose text it says, in the order they were given.

**`release`**

```python
def release(self) -> None: ...
```

Let every stalled response go on, now and from now on.

**`call`**

```python
async def call(self, index: int) -> Request: ...
```

The model call at `index`, once it has arrived.

### `platoon_harness.testing.FakeTools`

```python
class FakeTools:
    def __init__(self) -> None: ...
```

One tool over Streamable HTTP with a bearer, shaped as the tool plane serves. `calls` logs the arguments of each
`tools/call`, and `binding` is how an agent reaches it.

**`binding`**

```python
def binding(self, bin: Path) -> ToolBinding: ...
```

### `platoon_harness.testing.Hang`

```python
@dataclass(frozen=True)
class Hang: ...
```

Do nothing, until interrupted.

### `platoon_harness.testing.NAMESPACE`

```python
NAMESPACE = "conformance"
```

### `platoon_harness.testing.Overflow`

```python
@dataclass(frozen=True)
class Overflow: ...
```

Refuse the request as longer than the model's context window, in the dialect's own error form, which names no
response.

### `platoon_harness.testing.Request`

```python
@dataclass(frozen=True)
class Request:
    message: Message
    dialect: Dialect | None = None
    response_id: str | None = None
```

One request, logged exactly as it arrived. `dialect` is None for what is no model call.

**`json`**

```python
@cached_property
def json(self) -> Any: ...
```

**`model`**

```python
@property
def model(self) -> str | None: ...
```

**`bearer`**

```python
@property
def bearer(self) -> str | None: ...
```

The bearer it was sent under, if any.

**`carries`**

```python
def carries(self, headers: Mapping[str, str]) -> bool: ...
```

Whether it carries each of these headers with its value.

**`tool_method`**

```python
@property
def tool_method(self) -> str | None: ...
```

What it asked of the environment's MCP server, or None for a request of any other kind.

**`says`**

```python
def says(self, text: str) -> bool: ...
```

Whether this text is anywhere in what the harness sent.

**`offers`**

```python
def offers(self, tool: str) -> bool: ...
```

Whether the model is shown this tool, in any dialect's shape: a harness prefixes or nests the name.

**`tools`**

```python
@cached_property
def tools(self) -> tuple[str, ...]: ...
```

The names of the tools the model is shown, exactly, in any dialect's shape. A namespace's tools go by their
own names, and a Responses client can list tools in its input, as Codex does for a catalog model.

### `platoon_harness.testing.Say`

```python
@dataclass(frozen=True)
class Say:
    text: str
```

Stream some text, then record it as a message.

### `platoon_harness.testing.ScriptedDriver`

```python
class ScriptedDriver:
    def __init__(
        self,
        turns: Iterable[Sequence[Step]] = (),
        *,
        capabilities: Capabilities = _DEFAULT,
        name: str = "scripted",
        version: str | None = "1",
    ) -> None: ...
```

A harness made of `turns`, each a list of steps: the first runs on the goal if it has one, and each next on a
delivery. A turn with no steps left ends, and turns run out into empty ones. A turn whose step raises ends failed,
saying what was raised, as a harness's own error ends its turn.

Its capabilities are data, and it holds to them: one that is not `persistent` exits after its first turn, one with
no `resume` refuses to resume, and a boundary it does not declare is refused. A turn's name counts within one
instance and carries that instance's own mark, so that no two of an agent's turns share one across a resume.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

**`deliver`**

```python
async def deliver(self, delivery: Delivery) -> None: ...
```

**`interrupt`**

```python
async def interrupt(self) -> None: ...
```

**`answer`**

```python
async def answer(self, approval: str, verdict: Verdict) -> None: ...
```

**`reconcile`**

```python
async def reconcile(self, input_id: str) -> Reconciled: ...
```

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

### `platoon_harness.testing.SHELL`

```python
SHELL = "shell"
```

The one tool of a scripted harness's own, which runs its `command` once allowed.

### `platoon_harness.testing.Stall`

```python
@dataclass(frozen=True)
class Stall: ...
```

Hold the response until `FakeModel.release` or the client goes away. What follows it in a reply comes after.

### `platoon_harness.testing.Text`

```python
@dataclass(frozen=True)
class Text:
    text: str
```

The model says this.

### `platoon_harness.testing.Think`

```python
@dataclass(frozen=True)
class Think:
    text: str
```

### `platoon_harness.testing.Thought`

```python
@dataclass(frozen=True)
class Thought:
    text: str
```

The model thinks this, in dialects that carry thinking.

### `platoon_harness.testing.TOOL`

```python
TOOL = "conformance_ping"
```

### `platoon_harness.testing.ToolCall`

```python
@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    id: str | None = None
    namespace: str | None = None
```

The model calls a tool. `id` is the id the model gives the call, and left out FakeModel gives it
`call_<reply>_<place>`, by the reply's number and its place in it, so no two calls share one, as a model's never
do. `namespace` is how a Responses client names an MCP server's tools.

### `platoon_harness.testing.Wait`

```python
@dataclass(frozen=True)
class Wait: ...
```

Hold the turn until a delivery comes in it, the way a harness sits blocked in a tool.

## `platoon_harness.tools`

The tool plane: an agent's operations as tools, over MCP and `ph`, from one derivation.

### `platoon_harness.tools.delivery_heading`

```python
def delivery_heading(input: object) -> str: ...
```

The line a handover opens with, which holds its id, because a handover can come twice.

### `platoon_harness.tools.delivery_text`

```python
def delivery_text(handed: dict[str, Any], surface: Surface, ops: Collection[str], held: Collection[str]) -> str: ...
```

A handover as a harness's prompt reads it.

### `platoon_harness.tools.harness_name`

```python
def harness_name(namespace: str) -> Surface: ...
```

An op as a harness shows a server's tools to its model: `mcp__<namespace>__task_claim`.

### `platoon_harness.tools.held_tools`

```python
def held_tools(kernel: Kernel, principal: Principal) -> set[str]: ...
```

The tool ops this principal holds now. An ended agent holds none.

### `platoon_harness.tools.instructions`

```python
def instructions(
    kernel: Kernel, agent: Principal, surface: Surface | None, template: str, words: str | None
) -> str | None: ...
```

What the runtime adds to an agent's harness: its preamble filled into `template`, then `words`, its role's own,
last, so that a role has the last word, or `words` alone on a harness that reaches none of our tools. A tool either
names in backticks is named as `surface` names it. None is nothing to add.

### `platoon_harness.tools.list_tools`

```python
def list_tools(kernel: Kernel, principal: Principal, surface: Surface = tool_name) -> list[dict[str, Any]]: ...
```

What this principal holds, as MCP tools. `title` keeps the op's name, which is what `ph` goes by.

`readOnlyHint` is true only for what journals nothing: an agent's read moves its cursor and records exposure.

### `platoon_harness.tools.NAMESPACE`

```python
NAMESPACE = "ph"
```

What our tools go by on a harness that shows a server's tools by MCP, as `mcp__ph__task_claim`, and as a command.

### `platoon_harness.tools.OP_NAMED`

```python
OP_NAMED = re.compile(r"`([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*)`")
```

A name in backticks, as words name an op or an argument, with the name as its one group.

### `platoon_harness.tools.PH`

```python
PH = Path(__file__).with_name("ph.py")
```

### `platoon_harness.tools.preamble`

```python
def preamble(kernel: Kernel, agent: Principal, surface: Surface = tool_name, template: str = PREAMBLE) -> str: ...
```

This agent's exact tools, and who it can reach, because no harness's tool discovery can be relied on and tool
schemas never enumerate targets, filled into `template`. A harness has it once, at launch, so it is a snapshot:
`peers` is what stays current.

### `platoon_harness.tools.PREAMBLE`

```python
PREAMBLE = """\
You are @{name}. You coordinate with this session through these tools, by exactly these names: {tools}.
{help}
You can message: {peers}.
You can start agents in these roles: {roles}.
Channels: {channels}.
{waiting}
{citing}
{ending}"""
```

The template every agent's preamble fills unless its team or its role gives another. A slot is a word in braces, and
`{{` and `}}` write a brace. A line whose slots all come out empty is left out, words and all, and a line with no slot
is never dropped.

### `platoon_harness.tools.shell_name`

```python
def shell_name(op: str) -> str: ...
```

An op as a command: `ph task.claim`.

### `platoon_harness.tools.SHIM`

```python
SHIM = Path(__file__).with_name("shim.py")
```

### `platoon_harness.tools.slots`

```python
def slots(template: str) -> tuple[str, ...]: ...
```

The slots a preamble template fills, in order, or `ValueError` naming what is wrong with it.

### `platoon_harness.tools.Surface`

```python
type Surface = Callable[[str], str]
```

### `platoon_harness.tools.surface_of`

```python
def surface_of(capabilities: Capabilities) -> Surface | None: ...
```

How a harness names our tools to its model, from what it declares: by MCP, under `NAMESPACE` or by their own
names, by `ph`, or not at all.

### `platoon_harness.tools.taught`

```python
def taught(text: str, surface: Surface, ops: Collection[str], held: Collection[str]) -> str: ...
```

Text in the words of a surface, on one line, with no sentence that names a tool outside `held`, as anything a
reader is told is.

### `platoon_harness.tools.tool_name`

Imported from [`platoon_harness.kernel.tool_name`](#platoon_harnesskerneltool_name).

### `platoon_harness.tools.ToolServer`

```python
class ToolServer(Server[_Request]):
    def __init__(self, kernel: Kernel) -> None: ...
```

A kernel's tool ops over loopback HTTP. Everything is per request, from a bearer token, so an idle client holds
nothing here: not a session, not a task, not a socket.

**`start`**

```python
async def start(self) -> None: ...
```

Bind a free port on loopback and start answering. Stopping drops every open call, and waits stay
registered: they live in the service, not in a call.

**`url`**

```python
@property
def url(self) -> str: ...
```

Where to reach this server. A client may add `?surface=` for how tools are named to its model.

**`receive`**

```python
async def receive(self, head: Head, reader: asyncio.StreamReader) -> _Request: ...
```

Nothing past the head is read for a client that has not proved who it is.

**`refuse`**

```python
def refuse(self, rejected: Rejected) -> bytes: ...
```

**`sent`**

```python
async def sent(self, request: _Request) -> None: ...
```

Only now is anyone told. A wait left open closes with its turn, and wakes its agent.

**`answer`**

```python
async def answer(self, request: _Request) -> bytes: ...
```

## `platoon_harness.topology`

Topology: who may reach whom. Presets make fragments, `|` mixes them, and `compile` gives one grant table.

### `platoon_harness.topology.blackboard`

```python
def blackboard(role: Roles, *, board: str = "notes", queue: str | None = None) -> Topology: ...
```

Agents coordinate through shared artifacts alone, and may share a queue of open work.

### `platoon_harness.topology.Board`

```python
class Board(_Channel):
    kind: Literal["board"] = "board"
    delivery: Injection = "pull"
```

Named objects with immutable versions.

### `platoon_harness.topology.Channel`

```python
Channel = Annotated[Topic | Queue | Board, Field(discriminator="kind")]
```

### `platoon_harness.topology.compile`

```python
def compile(team: Team) -> tuple[Grant, ...]: ...
```

The grant table of a resolved team, sorted. Humans and programs hold every op; an agent holds what is listed.

### `platoon_harness.topology.expand`

```python
def expand(table: Mapping[str, Any], presets: Mapping[str, Preset] = PRESETS) -> Topology: ...
```

A `[topology]` table as one fragment: its own keys, in union with each preset table beside them.

### `platoon_harness.topology.git_swarm`

```python
def git_swarm(role: str, *, live: int) -> Topology: ...
```

A population coordinating through a shared repository alone: no messages, only commits and nominations, with at
most `live` agents at once. Its program, a script, owns the session, writes each worker's outcome on `outcomes` and
closes it.

### `platoon_harness.topology.Group`

```python
class Group(Model):
    roles: tuple[Name, ...] = ()
    members: tuple[Member, ...] = ()
    order: tuple[Name, ...] = ()
```

A named membership rule: some roles, some principals, or roles in an order that `next` and `prev` walk.

### `platoon_harness.topology.Limits`

```python
class Limits(Model):
    max_depth: Positive | None = None
    max_children: Positive | None = None
    max_live: Positive | None = None
    max_hops: Positive | None = None
```

Bounds on the live graph, and on how far a chain of messages may run.

### `platoon_harness.topology.manager_worker`

```python
def manager_worker(
    manager: str,
    workers: Roles,
    *,
    queue: str = "tasks",
    board: str = "notes",
    lease: str = "30m",
    max_hops: int = 8,
) -> Topology: ...
```

A manager fills a queue that workers claim from. Workers answer to their parent and share a board.

### `platoon_harness.topology.mesh`

```python
def mesh(role: Roles, *, board: str | None = None, group: str = "peers", max_hops: int = 8) -> Topology: ...
```

Peers message each other directly and share their group's topic, which wakes no one.

### `platoon_harness.topology.pipeline`

```python
def pipeline(stages: Sequence[str], *, back: bool = False, max_hops: int | None = None) -> Topology: ...
```

Each stage feeds a queue for the next. `back` lets every later stage return work to the first.

### `platoon_harness.topology.preset_name`

```python
def preset_name(preset: Preset) -> str: ...
```

The name a preset goes by in TOML.

### `platoon_harness.topology.PRESETS`

```python
PRESETS: dict[str, Preset] = {
    preset_name(preset): preset for preset in (manager_worker, tree, mesh, star, blackboard, pipeline, ring, git_swarm)
}
```

### `platoon_harness.topology.Queue`

```python
class Queue(_Channel):
    kind: Literal["queue"] = "queue"
    delivery: Injection = "pull"
    lease: Duration | None = None
    lease_max: Duration | None = None
    max_attempts: Positive = 3
    max_inflight: Positive = 1
```

Tasks leased to one claimant at a time. Unless `pull`, `delivery` announces work; it never assigns it.

### `platoon_harness.topology.ring`

```python
def ring(stages: Sequence[str], *, laps: int) -> Topology: ...
```

A pipeline whose last stage feeds the first, for at most `laps` times round.

### `platoon_harness.topology.scopes`

```python
def scopes(role: Role) -> tuple[str, ...]: ...
```

A token's scopes: the role's op globs, always with `ops.list`, which every surface derives from.

### `platoon_harness.topology.star`

```python
def star(hub: str, spokes: Roles, *, topic: str | None = None, max_hops: int = 8) -> Topology: ...
```

Every message goes through the hub, which may also announce on a topic. Spokes never reach each other.

### `platoon_harness.topology.Topic`

```python
class Topic(_Channel):
    kind: Literal["topic"] = "topic"
    delivery: Injection = "next-turn"
    history: Literal["from-join", "full"] = "from-join"
    coalesce: Duration | None = None
```

A log every reader follows by cursor.

### `platoon_harness.topology.Topology`

```python
class Topology(Model):
    until: Until | None = None
    edges: Annotated[
        Mapping[Name, Annotated[tuple[Selector, ...], BeforeValidator(_as_list)]], AfterValidator(_normal_edges)
    ] = {}
    groups: Annotated[Mapping[Name, Group], Sorted] = {}
    channels: Annotated[Mapping[Name, Channel], Sorted] = {}
    limits: Limits = Limits()
    grants: Annotated[tuple[Grant, ...], AfterValidator(_normal_grants)] = ()
    unexpanded: tuple[Unexpanded, ...] = ()
```

What may happen: a set of fragments merged by union. Presets make fragments; `a | b` mixes them.

**`hash`**

```python
@property
def hash(self) -> str: ...
```

The sha256 of the resolved form, which no order of mixing can change.

### `platoon_harness.topology.tree`

```python
def tree(
    role: str, *, max_depth: int, max_children: int | None = None, until: str | None = None, max_hops: int = 8
) -> Topology: ...
```

Agents delegate downward and report upward. It closes when its root finishes, unless `until` says otherwise.

### `platoon_harness.topology.Unexpanded`

```python
class Unexpanded(Model):
    preset: str
    params: Mapping[str, JsonValue] = {}
```

A preset table no known definition could expand yet, because an extension must supply one.

### `platoon_harness.topology.union`

```python
def union(parts: Iterable[tuple[str, Topology]]) -> Topology: ...
```

Merge named fragments. Edges and grants add up; anything defined twice must be defined alike.

## `platoon_harness_acp`

The ACP driver of platoon-harness, a first-party extension that uses the SDK's public names alone (RFC 0072).

### `platoon_harness_acp.AcpDriver`

```python
class AcpDriver:
    name = "acp"
    inherits: tuple[str, ...] = ()
    def __init__(self, command: Sequence[str]) -> None: ...
```

One agent that speaks ACP, run as `command`, with one session of its own.

A delivery that comes during a turn waits for its end and goes as the next prompt, and one for any other boundary
is refused, as no fixture has shown an agent taking one. Frames are taken on the read loop, which never waits, so
the pipe drains, and a permission request waits for its verdict in a task of its own, which is what `Peer` gives a
request.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

**`deliver`**

```python
async def deliver(self, delivery: Delivery) -> None: ...
```

**`interrupt`**

```python
async def interrupt(self) -> None: ...
```

Cancel the prompt under way, and answer each permission request it waits on `cancelled`, as ACP asks of a
client. What waits for the next turn never reached the agent, and the runtime offers it again.

**`answer`**

```python
async def answer(self, approval: str, verdict: Verdict) -> None: ...
```

Answer with the request's option of the verdict's kind for this once. Where it offers none, the answer is
`cancelled`, which runs nothing: a denial holds, and an allow fails, saying it was not carried out.

**`reconcile`**

```python
async def reconcile(self, input_id: str) -> Reconciled: ...
```

ACP keeps no id of a prompt, so what is known is what this driver saw land, or holds still.

**`stop`**

```python
async def stop(self, grace: float) -> None: ...
```

End of stdin ends the agent, and whatever it has running with it.

### `platoon_harness_acp.CAPABILITIES`

```python
CAPABILITIES = Capabilities(
    persistent=True,
    resume=True,
    boundaries=frozenset({"turn"}),
    tool_paths=frozenset({"mcp-http"}),
    interrupt=True,
    approvals="native",
    native_children="opaque",
    coverage={"prompt": "partial", "tool_results": "partial", "compaction": "partial"},
)
```

What an ACP agent is driven with. ACP names no model call and says no spend of one, so there are no call ids and no
measures, and stable ACP neither shows an agent's own agents nor turns them off.

### `platoon_harness_acp.OpenCodeDriver`

```python
class OpenCodeDriver(AcpDriver):
    name = "opencode"
    inherits = (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
    )
    def __init__(self) -> None: ...
```

OpenCode, by `opencode acp`, on the user's own setup with ours beside it, reaching the network as the shell
does. A start that names no model is refused, as OpenCode with none set sends prompts to a hosted model nobody
chose.

**`describe`**

```python
def describe(self) -> DriverInfo: ...
```

As any ACP agent's, naming the check `doctor --check` runs on it.

**`start`**

```python
async def start(self, spec: AgentSpec, report: Reporter) -> None: ...
```

### `platoon_harness_acp.PROTOCOL`

```python
PROTOCOL = 1
```

The one version of ACP this driver speaks: an agent that answers with another is refused.
