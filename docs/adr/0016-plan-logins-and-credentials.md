# 0016. Plan logins and credentials

**Status:** Accepted, 2026-11-02. Its `web --remote` line is amended by [0027](0027-the-browser-on-our-backend.md), 2026-11-04:
no such flag exists, `web` serves loopback unless `--host` names another address with TLS, a control link is the owner's
alone to use and a view link is what another person gets, and refusing an address other than loopback to a session on a
plan login is planned

## Context

Most users already have a harness signed in on a plan, and the brief says not to force them onto a shared API key. Provider terms limit how that login may be used. Third parties may not collect or intermediate plan credentials, and advertised limits assume "ordinary, individual usage", which is undefined. Enforcement can come without notice and would land on the user's account. Credentials also escape in quiet ways: a path-form URL is a key, and `repr(ctx.endpoint)` prints it.

## Decision

- **We spawn the user's own harness under its own login.** We never read, copy, store or proxy a credential, and we build no login flow. `doctor` shows only that a login exists and its kind.
- **Headless multi-agent on a plan login exits 78** and names the fix, unless the user opts in. `web --remote` refuses a second person on a plan-login session, which ADR 0027 amends.
- **Secrets are handled by type.** Config holds env var names. `Secret` refuses serialization. Redaction covers values, their encoded forms, and URLs. A path-form URL is normalized to origin plus bearer before a driver sees it.
- **Harness env is an allowlist,** per process. Nothing is inherited by default. `ANTHROPIC_BASE_URL` is never set without a gateway credential, because alone it leaves the login active.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A credential broker, our own sign-in, or a plan token in our client | The terms forbid intermediating, the brief forbids reuse as an API credential, and it would create a secret store to defend |
| Requiring API keys | The brief forbids that too, and a native-login agent stays useful even when it is not trainable |
| Warning only on unattended teams | The first recommendation in the research. Headless, nobody reads a warning, and the risk is to the user's account. Opt-in keeps the choice and makes it deliberate |
| Refusing all multi-agent use on plan logins | That would assert a limit no provider states. A person at the keyboard can watch and stop |
| Inheriting the parent environment | Variables change harness behavior or leak a parent's identity. `ANTHROPIC_API_KEY` in `-p` would silently change billing |

## Consequences

- Native login is Operational and Observable, never Trainable. Claude-generated traces are never offered as training data.
- This is engineering policy, not legal advice. "Ordinary, individual usage" remains undefined, and OpenAI's clauses came from search snippets and need review.
- Training through Claude Code against a non-Claude policy stays blocked pending an owner decision.

## Evidence

- [adapter-claude-code.md](../research/adapter-claude-code.md), sections 6 and 7: terms quoted verbatim and the may and must-not rules. [adapter-codex.md](../research/adapter-codex.md): login modes and third-party use.
- [tools-and-parking.md](../research/spikes/tools-and-parking.md), clean environment: `PATH`, `HOME` and a supplied `TMPDIR` were enough for Claude Code in one trial. [platoon-training.md](../research/platoon-training.md), section 5, and [research index](../research/README.md), claim 5 and new finding 4. [Architecture sections 14 and 15](../architecture.md), [brief section 4](../spec/BRIEF.md).
