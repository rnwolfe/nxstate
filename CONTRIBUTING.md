# Contributing to nxstate

Thanks for your interest! nxstate is a **read-only** Cisco Nexus state-gathering CLI built for
agents and humans. Contributions that add curated `show` commands, improve parsing, or harden
safety are very welcome.

## Ground rules

- **Read-only forever.** nxstate must never gain configuration/mutation capability. New
  commands must be reads, and the `show`/`debug` passthrough must keep refusing non-read input
  (`WRITE_REFUSED`). PRs that weaken this will be declined.
- Keep secrets out of code, tests, and the inventory format.
- Device output is untrusted — keep the fencing behavior for raw text.

## Dev setup (uv)

```bash
uv sync --extra dev            # create the venv + install deps
uv run pytest -q               # run the test suite (network is stubbed; no device needed)
uv run ruff check .            # lint
uv run ruff format .           # format
```

Tests must pass offline. Live tests against a real switch are manual (e.g. a Cisco DevNet
NX-OS sandbox); never commit credentials — pass them via `NXSTATE_PASSWORD`.

## Adding a curated command

1. Map the job to a single `show` command; add a noun-verb subcommand in `src/nxstate/cli.py`.
2. List commands return arrays — call `rt.show("show ...", rows=True)` so the primary table is
   extracted and `--select`/`--limit`/tsv work.
3. Update the embedded `src/nxstate/SKILL.md` and the README cookbook.
4. Add/extend a test in `tests/` (stub `NexusClient.run_show`).

## Pull requests

- Use **Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`…).
- One logical change per PR; include tests and update docs/`CHANGELOG.md` (`[Unreleased]`).
- CI (lint + tests on supported Python versions) must be green.
- By contributing you agree your work is licensed under `MIT OR Apache-2.0`. We use the
  [DCO](https://developercertificate.org/) — sign commits with `git commit -s`. No CLA.

## Reporting bugs / security

Use the issue forms for bugs and features. **Do not file security issues publicly** — see
[`SECURITY.md`](SECURITY.md).
