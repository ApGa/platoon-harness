<!--
Title the pull request like a commit subject: a Conventional Commit with no scope and a summary in sentence case
without a final period, such as "feat: Add leased task queue". CI checks it, and the title becomes the commit subject
on main when the pull request is squash-merged. CONTRIBUTING.md, under "Commits and pull requests", lists the types.
-->

## Summary

<!-- What changes, in a few sentences. -->

## Why

<!-- The problem this solves, or what it makes possible. -->

## Links

<!-- "Fixes #123", or "Implements RFC NNNN, milestone M2". Delete this section when there is nothing to link. -->

## Tests

<!-- The tests you added, the commands you ran with what they showed, and which live tests ran with their budget, or
none. -->

## Checklist

- [ ] The title is a Conventional Commit, `<type>: <summary>`, with no scope and a summary in sentence case without a
      final period
- [ ] Every fix and feature has a test, a fix's test fails without the fix, and each new primitive promise has a test
      named for it
- [ ] `uv run pre-commit run --all-files` (ruff, ty) and `uv run pytest -q -n auto` pass
- [ ] The docs, examples, command-line help, `docs/STATUS.md` and `tests/public_api.txt` that the change affects are
      updated, and generated docs are made again
- [ ] No secrets, local paths, cluster names or account details in code, configs, docs or tests
- [ ] A change that needs an RFC (CONTRIBUTING.md, "When a change needs an RFC") links one, and a commit that breaks a
      public contract has `!` after its type and a `BREAKING CHANGE:` footer
