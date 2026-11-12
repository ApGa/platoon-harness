# RFC 0017: TOML config, pydantic, and two entry-point groups

| | |
|---|---|
| Status | Accepted, 2026-11-02; amended by [RFC 0081](0081-platoon-harness-is-one-distribution-with-the-command-line-as-its-cli-extra.md) |

**Amended by [RFC 0081](0081-platoon-harness-is-one-distribution-with-the-command-line-as-its-cli-extra.md)**, 2026-11-12: the SDK and the command line are one distribution, `platoon-harness`, so an extension's
requirement names `platoon-harness` where this says `platoon-harness-sdk`, a name never published.

## Summary

TOML, frozen pydantic, two entry-point groups, nothing active until named

## Motivation

A team must be both a file and a Python object. Problems must surface before any cost. The SDK's only runtime dependency is pydantic. Extensions must be explicit: installing a package may not change an unrelated session, and project config is untrusted, so it can never install anything.

## Proposal

Config is pydantic, frozen, `extra="forbid"`, loaded from TOML with stdlib `tomllib` or built in Python. Precedence, low to high: defaults, user config, project config, team file, environment, command line. Mappings merge and lists replace. Every problem is reported at once, with did-you-mean. There are two entry-point groups: `platoon_harness.drivers` and `platoon_harness.extensions`. Discovery reads metadata with no import, so duplicates and incompatible `platoon-harness-sdk` requirements are caught before code loads. Installing activates nothing: a role names a harness, a team names `extensions = [...]`, and `module:attr` is always accepted.

## Alternatives

| Alternative | Why not |
|---|---|
| YAML | It needs a parser dependency the SDK does not otherwise have, while `tomllib` is stdlib. Platoon's harness specs are TOML too |
| A hand-written validator | Platoon's reached about 1,800 lines. Pydantic also gives the JSON Schema that every op surface needs |
| One group for everything | A role's `harness = "claude"` selects one adapter per agent by short name, and `extensions` selects ops and views for a whole team. They resolve to different things at different times |
| A group per kind: primitives, presets, workspaces, exporters | The bar is that a kind gets a group when a second independent user needs a short name. Until then these are fields of `Extension` |
| Duplicate detection at registration, as in Platoon | It fires only when the name is used, after import. Metadata lets us catch it before any code loads or any cost is spent |
| Activating on install | An installed package must not change a run that does not select it |

## Consequences

- The SDK stays at one runtime dependency.
- `tomllib` only reads, so `team show --resolved` needs our own small TOML writer.
- The sanitized resolved form reloads alone. The manifest records it with component, schema and protocol versions.
- First-party and third-party extensions use the same contract.
- A `command` harness in a project file needs an explicit trust step.

## Evidence

- Platoon 0.5.0's extensions, read at `efe3b277c82c`: components selected explicitly and loaded lazily, a duplicate name caught only once used, and a hand-written validator of about 1,800 lines.
- [Architecture sections 15 and 17](../architecture.md).
