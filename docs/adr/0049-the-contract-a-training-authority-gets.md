# 0049. The contract a training authority gets

**Status:** Accepted, 2026-11-05

## Context

[ADR 0013](0013-platoon-bridge.md) put a Platoon bridge in an extension of ours, `platoon-harness-platoon`. The owner decided that
the bridge is a first-party extension of Platoon's, `platoon-teams`, built in Platoon's repository, and that this repository holds
only the contract it builds on, naming nothing after Platoon. That contract was too thin to build on. `Admission` held a token and
variables by name, so a gateway's origin, bearer and model had no typed home, and a URL with a path secret could have reached a
driver as a variable. `Host._admit` returned None, so nothing in the journal tied an agent of ours to the agent the training system
knows. `SpawnRequest` named no parent and no goal, which a training authority needs to spawn a child through its parent or mint a
peer. `AgentOutcome` held a status alone, with no final message to report. And `Authority.budget_owner` let an authority own a
budget unit, which no authority uses: a training system limits steps per agent at its gateway, not the session's tokens or usd.

## Decision

- **Model access is one typed value:** variables by name, or a `Gateway(origin, bearer, model, tools, compaction_headers)`. `origin`
  is a scheme and a host and nothing more, and no URL a gateway names holds a user, a query or a fragment, so a credential goes by
  the bearer alone. `tools` is the environment's own MCP server as the authority gives it, so no training system's path is written
  into the SDK, and `compaction_headers` are the authority's to name, so its header names stay out of the SDK too. A field
  serializer refuses model access whole, as the `Secret` it holds would, since a union's serializer otherwise guesses past a refusal.
- **A gateway goes only to a driver that declares `sealed`,** and the launch of any other fails, naming why. Its model is the one
  pinned, a role may name only that one, and its login is `gateway`, which is no plan login. `keys_of(spec)` reads variables by
  name and refuses a gateway, so each driver that has no sealed launch says so in the same words.
- **`Admission.backend` is the backend's ids for its agent**, the admit effect's result and the one join key: each entry names that
  agent alone, no key is recorded, an admission whose backend holds one of its own secrets, as a key or a value and in any form text
  carries one, is refused, and a gateway admission must name backend ids, as nothing else ties its agent to what the gateway
  records.
- **An admission holds its agent to one identity.** The host keeps the access each agent was admitted on for the runtime's life.
  A gateway's bearer is one agent's, so an admission on a bearer another agent holds is refused and its spawn fails. A resumed
  admission must give the backend ids the agent's admit recorded and the access this runtime admitted it on; one that gives others
  loses the agent, saying why, as its calls would go on an identity the record does not name. The design left keeping access to the
  authority; a review showed an authority that mints again makes eligibility answer `exact` for calls on a key the record never
  names, so the host holds it, and a `Secret` equals another of the same value so that access compares by what it gives.
- **`SpawnRequest` carries `parent` and `goal`**, read from the agent's `agent.spawned`, which is what a parent's spawn recorded, so
  adoption does not change it. **`AgentOutcome` carries `report`**, the words the agent's end keeps, its gist and then its body,
  and its `status` is one of the five ends.
- **`budget_owner` is deleted**, with its use in opening, so every limit a team states is the session's.
- **`finish` may be told twice:** a stop a crash cut is said again by the next runtime, alike, so an authority takes a second
  telling as the first.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A `gateway` field beside `access` | Two ways to give model access, and an admission holding both would need a rule for which wins |
| `{origin}/mcp` written into the SDK and FakeModel | `/mcp` is one training system's path; the authority gives the URL it serves |
| `Admission.native` for the backend's ids | `native` already names a harness's own ids and agents here |
| Recording a trajectory id beside the agent id | A second key for one join, and a minted agent's is not known when it is admitted |
| The host refusing a gateway alone, with drivers reading access as before | A driver that declared `sealed` by mistake would read a gateway as variables; `keys_of` makes each driver's reading say what it takes |
| Reusing an agent's first admission on a resume, without asking the authority | `LocalAuthority` reads its access again, and an authority hears that a harness came back; holding what it gives to what the agent had keeps both |
| Leaving a resumed admission's access to the authority | Nothing would hold it, and an authority that mints again would put calls on an identity the record never names |
| Keeping `budget_owner` for tokens and usd | No authority owns either, and a limit the session silently does not enforce is a promise nothing keeps |
| Keeping a Platoon extension of ours | The owner's decision: the bridge is Platoon's first-party extension, and ours stays Platoon-agnostic |

## Consequences

- A training system's authority builds on `Authority`, `Admission`, `Gateway`, `SpawnRequest`, `AgentOutcome` and `AgentRef`, all
  in `platoon_harness.runtime`, and on the admit result to find its agents in our journal.
- No shipped driver declares `sealed` yet, so a gateway admission fails every launch until sealed launches land. Until then only a
  test's own sealed harness takes one.
- The agent record is at view version 14, keeping `backend`.
- A role's `budget` is always the session's own limit.

## Evidence

- `tests/unit/runtime/test_authority.py`: `test_the_admit_result_records_backend_ids_and_never_a_key`,
  `test_an_admission_whose_backend_names_a_key_is_refused`, `test_a_gateway_admission_names_the_backend_ids_of_its_agent`,
  `test_a_gateway_s_origin_is_an_origin_and_nothing_more`, `test_an_agent_is_admitted_with_its_parent_and_its_goal`,
  `test_a_resumed_admission_keeps_its_model_access_and_never_mints`, `test_a_resumed_admission_that_mints_anew_loses_its_agent`,
  `test_two_agents_on_one_key_are_refused`, `test_a_driver_without_a_sealed_launch_refuses_a_gateway`,
  `test_a_gateway_admission_is_a_gateway_login_and_no_plan_login`, `test_the_pinned_model_is_checked_against_the_gateways`.
- `tests/unit/runtime/test_recovery.py`: `test_finish_is_idempotent`, and
  `test_an_admit_in_flight_is_never_retried_and_the_spawn_fails_with_a_gap`, whose agent names no backend ids.
- `tests/unit/runtime/test_authority.py`, `test_the_gateway_bearer_is_masked_in_every_form`, and `tests/unit/drivers/test_env.py`,
  `test_a_spec_refuses_to_serialize_a_credential` and `test_a_gateway_s_bearer_is_a_credential_its_spec_holds`.
