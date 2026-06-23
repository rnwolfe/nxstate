<!-- Use a Conventional Commit title, e.g. "feat: add `nxstate ospf neighbors`" -->

## What & why

<!-- What does this change and why? Link any issue. -->

## Checklist

- [ ] Stays **read-only** (no config/mutation; passthrough still refuses non-read input)
- [ ] No secrets in code/tests/inventory; passwords only via stdin/env/keyring
- [ ] Tests added/updated and `uv run pytest` passes offline
- [ ] `uv run ruff check .` passes
- [ ] Updated `CHANGELOG.md` (`[Unreleased]`) and docs / embedded `SKILL.md` if behavior changed
- [ ] Commits signed off (`git commit -s`, DCO)
